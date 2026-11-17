// Package testseed builds a tiny deterministic seed + user DB for tests.
package testseed

import (
	"compress/gzip"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"strata/engine/internal/appshell"

	_ "modernc.org/sqlite"
)

const schema = `
CREATE TABLE books(
  nid INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
  genre TEXT, price_type TEXT, status TEXT, contest TEXT, words INTEGER,
  clicks INTEGER, favs INTEGER, praises INTEGER, featured INTEGER,
  cover_url TEXT, updated_at TEXT, est_year INTEGER NOT NULL,
  est_date TEXT NOT NULL, est_conf TEXT NOT NULL, tags TEXT,
  fav_pctl REAL, click_pctl REAL, praise_pctl REAL, pr REAL, pctl_pr REAL,
  is_licensed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE book_tags(nid INTEGER NOT NULL, tag TEXT NOT NULL);
CREATE TABLE seed_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
`

type book struct {
	nid                          int64
	title, author, genre, status string
	words, favs                  int64
	pctl                         any
	licensed                     int
	year                         int
}

var books = []book{
	{nid: 1001, title: "Long A", author: "Author A", genre: "魔幻", status: "连载中", words: 120000, favs: 500, pctl: 0.9, year: 2010},
	{nid: 1002, title: "Short B", author: "Author B", genre: "都市", status: "已完结", words: 30000, favs: 100, pctl: 0.5, year: 2010},
	{nid: 1003, title: "Long C", author: "Author C", genre: "科幻", status: "连载中", words: 200000, favs: 900, pctl: 0.99, year: 2011},
	{nid: 1004, title: "Short D", author: "Author D", genre: "魔幻", status: "已完结", words: 40000, favs: 50, pctl: 0.1, year: 2010},
	{nid: 2001, title: "Licensed", author: "天闻角川", genre: "魔幻", status: "已完结", words: 90000, favs: 99999, pctl: nil, licensed: 1, year: 2008},
}

// Build writes assets/seed.db.gz + manifest.json and a user.db with one
// observation for nid 1001.
func Build(assetsDir, dataDir string) (*appshell.Manifest, error) {
	if err := os.MkdirAll(assetsDir, 0o700); err != nil {
		return nil, err
	}
	dbPath := filepath.Join(assetsDir, "seed.db")
	_ = os.Remove(dbPath)
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, err
	}
	if _, err := db.Exec(schema); err != nil {
		db.Close()
		return nil, err
	}
	for _, b := range books {
		var pctl any
		if b.pctl != nil {
			pctl = b.pctl
		}
		_, err := db.Exec(`
INSERT INTO books(nid,title,author,genre,price_type,status,contest,words,clicks,
 favs,praises,featured,cover_url,updated_at,est_year,est_date,est_conf,tags,
 fav_pctl,click_pctl,praise_pctl,pr,pctl_pr,is_licensed)
VALUES(?,?,?,?, '免费', ?, NULL, ?, 1000, ?, 10, 0, NULL, '2026-04-01T00:00:00',
 ?, ?, 'high', '热血|战斗', ?,?,?,?,?,?)`,
			b.nid, b.title, b.author, b.genre, b.status, b.words, b.favs,
			b.year, fmt.Sprintf("%d-01-01", b.year),
			pctl, pctl, pctl, pctl, pctl, b.licensed)
		if err != nil {
			db.Close()
			return nil, err
		}
	}
	if _, err := db.Exec(`INSERT INTO book_tags(nid,tag) VALUES
	 (1001,'热血'),(1001,'战斗'),(1004,'战斗'),(2001,'战斗')`); err != nil {
		db.Close()
		return nil, err
	}
	meta := map[string]string{
		"schema_version": "1", "seed_version": "test-1",
		"content_end": "2026-05-03", "built_at": "2026-11-17T00:00:00Z",
		"book_count": "5", "tag_count": "2", "tag_rows": "4",
		"gen_min": "2007", "gen_max": "2025", "licensed_count": "1",
	}
	for k, v := range meta {
		if _, err := db.Exec("INSERT INTO seed_meta(key,value) VALUES(?,?)", k, v); err != nil {
			db.Close()
			return nil, err
		}
	}
	db.Close()

	dbBytes, err := os.ReadFile(dbPath)
	if err != nil {
		return nil, err
	}
	gzPath := filepath.Join(assetsDir, "seed.db.gz")
	if err := writeGzip(gzPath, dbBytes); err != nil {
		return nil, err
	}
	gzBytes, err := os.ReadFile(gzPath)
	if err != nil {
		return nil, err
	}

	m := &appshell.Manifest{
		SchemaVersion: 1,
		SeedVersion:   "test-1",
		ContentEnd:    "2026-05-03",
		BuiltAt:       "2026-11-17T00:00:00Z",
		BookCount:     len(books),
		LicensedCount: 1,
		TagCount:      2,
		TagRows:       4,
		GenMin:        2007,
		GenMax:        2025,
	}
	m.Files.DB = appshell.FileInfo{
		Name: "seed.db", Bytes: int64(len(dbBytes)), SHA256: sha(dbBytes),
	}
	m.Files.Gz = appshell.FileInfo{
		Name: "seed.db.gz", Bytes: int64(len(gzBytes)), SHA256: sha(gzBytes),
	}
	data, err := json.Marshal(m)
	if err != nil {
		return nil, err
	}
	if err := os.WriteFile(filepath.Join(assetsDir, "manifest.json"), data, 0o600); err != nil {
		return nil, err
	}
	_ = os.Remove(dbPath)

	userPath := appshell.UserDBPath(dataDir)
	if err := appshell.EnsureUserDB(userPath); err != nil {
		return nil, err
	}
	if err := addObservation(userPath, 1001, 1700000000, 777); err != nil {
		return nil, fmt.Errorf("add observation: %w", err)
	}
	return m, nil
}

func addObservation(userPath string, nid, observedAt, favs int64) error {
	db, err := sql.Open("sqlite", appshell.FileURI(userPath, "_pragma=journal_mode(WAL)"))
	if err != nil {
		return err
	}
	defer db.Close()
	_, err = db.Exec(`INSERT INTO observations
	 (nid, observed_at, clicks, favs, praises, words, status, updated_at, source)
	 VALUES (?, ?, 1234, ?, 20, 120000, '连载中', '2026-05-01T00:00:00', 'detail')`,
		nid, observedAt, favs)
	return err
}

func writeGzip(path string, data []byte) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	gz := gzip.NewWriter(f)
	if _, err := gz.Write(data); err != nil {
		return err
	}
	return gz.Close()
}

func sha(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// CopyGzip is a small helper for tests that need to corrupt the archive.
func CopyGzip(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}

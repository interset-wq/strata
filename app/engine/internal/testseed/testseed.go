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
  form TEXT NOT NULL DEFAULT 'long',
  is_licensed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE book_tags(nid INTEGER NOT NULL, tag TEXT NOT NULL);
CREATE TABLE deep_ranks(
  est_year INTEGER NOT NULL, metric TEXT NOT NULL, rank_no INTEGER NOT NULL,
  nid INTEGER NOT NULL, title TEXT NOT NULL, author TEXT NOT NULL,
  genre TEXT, value REAL, pctl REAL, cover_url TEXT,
  PRIMARY KEY(est_year, metric, rank_no)
);
CREATE TABLE seed_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE calendar_universe(day TEXT PRIMARY KEY, universe_count INTEGER NOT NULL);
`

type book struct {
	nid                          int64
	title, author, genre, status string
	words, favs                  int64
	pctl                         any
	licensed, featured           int
	year                         int
}

var books = []book{
	{nid: 1001, title: "Long A", author: "Author A", genre: "魔幻", status: "连载中", words: 120000, favs: 500, pctl: 0.9, featured: 1, year: 2010},
	{nid: 1002, title: "Short B", author: "Author B", genre: "都市", status: "已完结", words: 30000, favs: 100, pctl: 0.5, year: 2010},
	{nid: 1003, title: "Long C", author: "Author C", genre: "科幻", status: "连载中", words: 200000, favs: 900, pctl: 0.99, featured: 1, year: 2011},
	{nid: 1004, title: "Short D", author: "Author C", genre: "魔幻", status: "已完结", words: 40000, favs: 50, pctl: 0.6, year: 2010},
	{nid: 2001, title: "Licensed", author: "天闻角川", genre: "魔幻", status: "已完结", words: 90000, favs: 99999, pctl: nil, licensed: 1, year: 2008},
	{nid: 1005, title: "New E", author: "Author E", genre: "都市", status: "连载中", words: 150000, favs: 300, pctl: 0.95, year: 2025},
	{nid: 1006, title: "IP F", author: "Author F", genre: "都市", status: "连载中", words: 80000, favs: 700, pctl: 0.8, featured: 1, year: 2012},
	{nid: 1007, title: "Medium G", author: "Author G", genre: "科幻", status: "已完结", words: 120000, favs: 400, pctl: 0.7, featured: 1, year: 2013},
	{nid: 1008, title: "Dialogue H", author: "Author H", genre: "都市", status: "连载中", words: 50000, favs: 200, pctl: 0.6, year: 2014},
	{nid: 1009, title: "IP J", author: "Author J", genre: "都市", status: "连载中", words: 30000, favs: 100, pctl: 0.5, year: 2014},
	{nid: 1010, title: "IP K", author: "Author K", genre: "科幻", status: "已完结", words: 120000, favs: 80, pctl: 0.5, year: 2015},
	{nid: 1011, title: "IP L", author: "Author L", genre: "奇幻", status: "连载中", words: 20000, favs: 50, pctl: 0.4, year: 2016},
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
VALUES(?,?,?,?, '免费', ?, NULL, ?, 1000, ?, 10, ?, NULL, '2026-04-01T00:00:00',
 ?, ?, 'high', '热血|战斗', ?,?,?,?,?,?)`,
			b.nid, b.title, b.author, b.genre, b.status, b.words, b.favs,
			b.featured, b.year, fmt.Sprintf("%d-01-01", b.year),
			pctl, pctl, pctl, pctl, pctl, b.licensed)
		if err != nil {
			db.Close()
			return nil, err
		}
	}
	if _, err := db.Exec(`UPDATE books SET form='short' WHERE nid IN (1002,1004)`); err != nil {
		db.Close()
		return nil, err
	}
	// 1006/1007 carry the small featured pools that drive the per-form
	// carousel (docs/13): ip_collab and medium each get their own featured
	// book; short deliberately has none (its carousel falls back to IP).
	if _, err := db.Exec(`UPDATE books SET form='ip_collab', contest='崩坏3征文' WHERE nid = 1006`); err != nil {
		db.Close()
		return nil, err
	}
	// 1009–1011 feed the IP tab: 崩坏3征文 tail, 少女前线征文, and
	// 龙之谷征文 (the "other" long tail outside the top-2 by count).
	if _, err := db.Exec(`UPDATE books SET form='ip_collab', contest='崩坏3征文' WHERE nid = 1009`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`UPDATE books SET form='ip_collab', contest='少女前线征文' WHERE nid = 1010`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`UPDATE books SET form='ip_collab', contest='龙之谷征文' WHERE nid = 1011`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`UPDATE books SET form='medium' WHERE nid = 1007`); err != nil {
		db.Close()
		return nil, err
	}
	// 1008 feeds the cover-composed 对话 carousel: a dialogue-form book
	// with a cover (cover-less books are invisible in that pool).
	if _, err := db.Exec(`UPDATE books SET form='dialogue', cover_url='cover-1008.jpg' WHERE nid = 1008`); err != nil {
		db.Close()
		return nil, err
	}
	// 1003 carries a low-confidence est_date to pin the docs/14 conf
	// rule: low rows never enter the day/week views, only the month view.
	if _, err := db.Exec(`UPDATE books SET est_date='2011-01-05', est_conf='low' WHERE nid = 1003`); err != nil {
		db.Close()
		return nil, err
	}
	// calendar_universe (seed schema v4): estimated whole-platform
	// releases per day. Deliberately differs from the bundled counts —
	// the bundled seed is a clickable subset, and the universe counts
	// licensed and low-confidence dates too.
	if _, err := db.Exec(`INSERT INTO calendar_universe(day, universe_count) VALUES
	('2008-01-01', 7), ('2010-01-01', 5), ('2011-01-05', 2),
	('2014-01-01', 4), ('2014-01-02', 1), ('2025-01-01', 9)`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`INSERT INTO book_tags(nid,tag) VALUES
	 (1001,'热血'),(1001,'战斗'),(1004,'战斗'),(2001,'战斗'),(1003,'2020萌神')`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`INSERT INTO deep_ranks
	 (est_year,metric,rank_no,nid,title,author,genre,value,pctl,cover_url) VALUES
	 (2010,'favs',1,1001,'Long A','Author A','魔幻',500,0.9,NULL),
	 (2010,'favs',2,7777,'Deep Only','Author Z','都市',250,0.5,NULL),
	 (2010,'pr',1,1001,'Long A','Author A','魔幻',0.02,0.8,NULL),
	 (2025,'favs',1,1005,'New E','Author E','都市',300,0.95,NULL)`); err != nil {
		db.Close()
		return nil, err
	}
	meta := map[string]string{
		"schema_version": "2", "seed_version": "test-1",
		"content_end": "2026-05-03", "built_at": "2026-11-17T00:00:00Z",
		"book_count": "6", "tag_count": "2", "tag_rows": "4",
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
		SchemaVersion: 2,
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

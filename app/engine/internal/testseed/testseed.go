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
  cover_url TEXT, updated_at TEXT, db_update TEXT, est_year INTEGER NOT NULL,
  est_date TEXT NOT NULL, est_conf TEXT NOT NULL, tags TEXT,
  pr REAL,
  form TEXT NOT NULL DEFAULT 'long',
  cqs REAL, cqs_state TEXT, cps REAL, len_norm REAL,
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
CREATE TABLE contest_awards(
  nid INTEGER NOT NULL, edition TEXT NOT NULL, award TEXT NOT NULL,
  category TEXT, source_nid TEXT NOT NULL,
  PRIMARY KEY(nid, edition)
);
CREATE TABLE author_ranks(
  form TEXT NOT NULL, rank_no INTEGER NOT NULL, author TEXT NOT NULL,
  rep_nid INTEGER NOT NULL, rep_title TEXT NOT NULL,
  PRIMARY KEY(form, rank_no)
);
CREATE TABLE eras_anchors(nid INTEGER PRIMARY KEY, day INTEGER NOT NULL);
CREATE TABLE calib_fav_bounds(
  form TEXT, est_year INTEGER, p50 REAL, p75 REAL, p90 REAL,
  PRIMARY KEY(form, est_year)
);
CREATE TABLE calib_len_anchors(form TEXT PRIMARY KEY, lo REAL, hi REAL);
CREATE TABLE calib_cqs_median(
  form TEXT, est_year INTEGER, genre TEXT, fband TEXT,
  med REAL, cell_n INTEGER,
  PRIMARY KEY(form, est_year, genre, fband)
);
CREATE TABLE calib_cps_median(
  form TEXT, est_year INTEGER, band TEXT, genre TEXT, med REAL,
  PRIMARY KEY(form, est_year, band, genre)
);
INSERT INTO seed_meta(key, value) VALUES('cqs_mu0', '0.232');
INSERT INTO eras_anchors(nid, day) VALUES(400000, 17000), (600000, 17600);
INSERT INTO calib_fav_bounds(form, est_year, p50, p75, p90)
  VALUES('long', 1999, 100, 2000, 10000);
INSERT INTO calib_len_anchors(form, lo, hi) VALUES('long', 263561, 2128618);
INSERT INTO calib_cqs_median(form, est_year, genre, fband, med, cell_n)
  VALUES('long', 1999, '魔幻', 'P75-90', 0.0, 25);
INSERT INTO calib_cps_median(form, est_year, band, genre, med)
  VALUES('long', 1999, 'long', '魔幻', 7.0);
`

type book struct {
	nid                          int64
	title, author, genre, status string
	words, favs                  int64
	pctl                         any
	licensed, featured           int
	year                         int
	// v6 runtime metrics (app/docs/18-runtime-metrics.md): baked in because
	// the store opens the seed read-only — tests cannot UPDATE it.
	cqs, cps, ln float64
	cqsState     string
}

var books = []book{
	// 738162 matches the 2025春征 金奖 nid in the embedded award ledger —
	// exercises the EditionAwards in-seed join (est_year/form backfill,
	// 2026-11-26 bug fix).
	{nid: 738162, title: "希瓦计划", author: "Author S", genre: "科幻", status: "连载中", words: 100000, favs: 800, pctl: 0.9, year: 2019,
		cqs: 1.0, cps: 0.8, ln: 0.5, cqsState: "stable"},
	{nid: 1001, title: "Long A", author: "Author A", genre: "魔幻", status: "连载中", words: 120000, favs: 500, pctl: 0.9, featured: 1, year: 2010,
		cqs: 1.5, cps: 1.0, ln: 0.1, cqsState: "stable"},
	{nid: 1002, title: "Short B", author: "Author B", genre: "都市", status: "已完结", words: 30000, favs: 100, pctl: 0.5, year: 2010},
	{nid: 1003, title: "Long C", author: "Author C", genre: "科幻", status: "连载中", words: 200000, favs: 900, pctl: 0.99, featured: 1, year: 2011,
		cqs: 1.4, cps: 0.5, ln: 0.9, cqsState: "stable"},
	{nid: 1004, title: "Short D", author: "Author C", genre: "魔幻", status: "已完结", words: 40000, favs: 50, pctl: 0.6, year: 2010},
	{nid: 2001, title: "Licensed", author: "天闻角川", genre: "魔幻", status: "已完结", words: 90000, favs: 99999, pctl: nil, licensed: 1, year: 2008,
		cqs: 3.0, cps: 1.0, ln: 0.5, cqsState: "stable"},
	{nid: 1005, title: "New E", author: "Author E", genre: "都市", status: "连载中", words: 150000, favs: 300, pctl: 0.95, year: 2025,
		cqs: 0.6, cps: 0.1, ln: 0.5, cqsState: "low"},
	{nid: 1006, title: "IP F", author: "Author F", genre: "都市", status: "连载中", words: 80000, favs: 700, pctl: 0.8, featured: 1, year: 2012},
	{nid: 1007, title: "Medium G", author: "Author G", genre: "科幻", status: "已完结", words: 120000, favs: 400, pctl: 0.7, featured: 1, year: 2013},
	{nid: 1008, title: "Dialogue H", author: "Author H", genre: "都市", status: "连载中", words: 50000, favs: 200, pctl: 0.6, year: 2014},
	{nid: 1009, title: "IP J", author: "Author J", genre: "都市", status: "连载中", words: 30000, favs: 100, pctl: 0.5, year: 2014},
	{nid: 1010, title: "IP K", author: "Author K", genre: "科幻", status: "已完结", words: 120000, favs: 80, pctl: 0.5, year: 2015},
	{nid: 1011, title: "IP L", author: "Author L", genre: "奇幻", status: "连载中", words: 20000, favs: 50, pctl: 0.4, year: 2016},
	{nid: 3001, title: "Zheng Long X", author: "Author X", genre: "魔幻", status: "连载中", words: 1000000, favs: 3000, pctl: 0.99, year: 2019,
		cqs: 0.8, cps: 2.0, ln: 0.95, cqsState: "stable"},
	{nid: 3002, title: "Zheng Dialogue Y", author: "Author Y", genre: "都市", status: "连载中", words: 40000, favs: 1500, pctl: 0.95, year: 2019},
	{nid: 3003, title: "Spring Short Z", author: "Author Z", genre: "校园", status: "已完结", words: 30000, favs: 800, pctl: 0.9, year: 2025},
	{nid: 3004, title: "Thirteen Long W", author: "Author W", genre: "科幻", status: "连载中", words: 800000, favs: 500, pctl: nil, year: 2025,
		cqs: 0.4, cps: 9.0, ln: 0.5, cqsState: "low"},
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
		var cqs, cps, ln, cqsState any
		if b.cqsState != "" {
			cqs, cqsState, cps, ln = b.cqs, b.cqsState, b.cps, b.ln
		}
		_, err := db.Exec(`
INSERT INTO books(nid,title,author,genre,price_type,status,contest,words,clicks,
	favs,praises,featured,cover_url,updated_at,db_update,est_year,est_date,est_conf,tags,
 pr,
 cqs,cqs_state,cps,len_norm,is_licensed)
VALUES(?,?,?,?, '免费', ?, NULL, ?, 1000, ?, 10, ?, NULL, '2026-04-01T00:00:00',
 '2026-05-27 22:53:10', ?, ?, 'high', '热血|战斗', ?, ?,?,?,?,?)`,
			b.nid, b.title, b.author, b.genre, b.status, b.words, b.favs,
			b.featured, b.year, fmt.Sprintf("%d-01-01", b.year),
			pctl,
			cqs, cqsState, cps, ln, b.licensed)
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
	// 3001–3004 feed the contest archive endpoints (docs/contest-
	// display-in-app.md 形态一): a N征 event with two divisions (incl. the
	// 对话类 spelling the fixed-suffix matcher used to miss), a spring
	// contest, and a 十三征 long book with NULL pr (the v9 favourite for
	// the NULLs-last ordering).
	if _, err := db.Exec(`UPDATE books SET form='long', contest='七征长篇' WHERE nid = 3001`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`UPDATE books SET form='dialogue', contest='七征对话类征文长篇' WHERE nid = 3002`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`UPDATE books SET form='short', contest='2025春季征文' WHERE nid = 3003`); err != nil {
		db.Close()
		return nil, err
	}
	if _, err := db.Exec(`UPDATE books SET form='long', contest='十三征长篇' WHERE nid = 3004`); err != nil {
		db.Close()
		return nil, err
	}
	// 3003/3004 carry contest awards (schema v5, docs/contest-display-
	// in-app.md §6): 2025春季征文 maps to edition 2025春征 (a named award),
	// 十三征 keeps the placeholder the display layer renders as 征文获奖.
	if _, err := db.Exec(`
INSERT INTO contest_awards(nid,edition,award,category,source_nid)
VALUES(3003,'2025春征','金奖','短篇','zw20250301'),
      (3004,'十三征','待逐档标定',NULL,'zw20250504')`); err != nil {
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
	// v10 author boards: two long rows + one dialogue row (form isolation).
	if _, err := db.Exec(`INSERT INTO author_ranks
	 (form,rank_no,author,rep_nid,rep_title) VALUES
	 ('long',1,'Author A',1001,'Long A'),
	 ('long',2,'Author C',1003,'Long C'),
	 ('dialogue',1,'Author H',1008,'Dialogue H')`); err != nil {
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

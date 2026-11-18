package appshell

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
)

const userSchemaVersion = 4

const userSchema = `
CREATE TABLE IF NOT EXISTS observations(
  nid            INTEGER NOT NULL,
  observed_at    INTEGER NOT NULL,
  clicks         INTEGER,
  favs           INTEGER,
  praises        INTEGER,
  words          INTEGER,
  short_comments INTEGER,
  long_comments  INTEGER,
  status         TEXT,
  updated_at     TEXT,
  source         TEXT NOT NULL DEFAULT 'detail',
  PRIMARY KEY(nid, observed_at)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_obs_time ON observations(observed_at DESC);

CREATE TABLE IF NOT EXISTS discovered(
  nid         INTEGER PRIMARY KEY,
  title       TEXT NOT NULL,
  author      TEXT,
  genre       TEXT,
  words       INTEGER,
  favs        INTEGER,
  praises     INTEGER,
  cover_url   TEXT,
  summary     TEXT,
  source      TEXT NOT NULL,
  observed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shelf(
  nid      INTEGER PRIMARY KEY,
  added_at INTEGER NOT NULL,
  list_id  INTEGER,
  note     TEXT
);

CREATE TABLE IF NOT EXISTS shelf_lists(
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS annotations(
  id         INTEGER PRIMARY KEY,
  nid        INTEGER NOT NULL,
  chapter    TEXT,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_anno_nid ON annotations(nid, created_at DESC);

CREATE TABLE IF NOT EXISTS search_history(
  id      INTEGER PRIMARY KEY,
  keyword TEXT NOT NULL,
  at      INTEGER NOT NULL,
  hits    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sh_at ON search_history(at DESC);

CREATE TABLE IF NOT EXISTS prefs(
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS user_stats(
  nid             INTEGER PRIMARY KEY,
  fav_delta_30d   INTEGER,
  click_delta_30d INTEGER,
  obs_count       INTEGER,
  first_seen      INTEGER,
  last_seen       INTEGER
);

CREATE TABLE IF NOT EXISTS watchlist(
  nid           INTEGER PRIMARY KEY,
  role          TEXT NOT NULL DEFAULT 'self',
  added_at      INTEGER NOT NULL,
  poll_enabled  INTEGER NOT NULL DEFAULT 1,
  poll_interval INTEGER NOT NULL DEFAULT 86400,
  last_poll_at  INTEGER,
  note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_watch_poll ON watchlist(poll_enabled, last_poll_at);
CREATE INDEX IF NOT EXISTS idx_watch_role ON watchlist(role);

CREATE TABLE IF NOT EXISTS covers(
  nid         INTEGER PRIMARY KEY,
  cover       TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'app',
  fetched_at  INTEGER NOT NULL
);

-- Latest book metadata from one successful detail fetch. This is the
-- writable overlay for seed.books: every field returned by the request is
-- kept here, including fields the seed has no column for (summary/add_time).
CREATE TABLE IF NOT EXISTS book_meta(
  nid          INTEGER PRIMARY KEY,
  source       TEXT NOT NULL,
  fetched_at   INTEGER NOT NULL,
  title        TEXT,
  author       TEXT,
  author_id    INTEGER,
  genre        TEXT,
  type_id      INTEGER,
  price_type   TEXT,
  status       TEXT,
  cover_url    TEXT,
  summary      TEXT,
  words        INTEGER,
  favs         INTEGER,
  praises      INTEGER,
  clicks       INTEGER,
  updated_at   TEXT,
  add_time     TEXT,
  point        REAL,
  bg_banner    TEXT,
  category_id  INTEGER,
  is_sensitive INTEGER,
  allow_down   INTEGER
);

-- One row per nid records the last outbound detail-fetch attempt. An attempt
-- is stamped BEFORE the request so failures still count against the 24h
-- cooldown; state is updated afterwards for diagnostics.
CREATE TABLE IF NOT EXISTS refresh_attempts(
  nid          INTEGER PRIMARY KEY,
  attempted_at INTEGER NOT NULL,
  state        TEXT NOT NULL DEFAULT 'pending'
);
`

func UserDBPath(dataDir string) string {
	return filepath.Join(dataDir, "user.db")
}

// EnsureUserDB creates the writable database on first launch. It never
// replaces an existing user.db.
func EnsureUserDB(path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	db, err := sql.Open("sqlite", userDSN(path))
	if err != nil {
		return err
	}
	defer db.Close()

	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		return fmt.Errorf("read user_version: %w", err)
	}
	if version >= userSchemaVersion {
		return nil
	}
	if _, err := db.Exec(userSchema); err != nil {
		return fmt.Errorf("create user schema: %w", err)
	}
	if _, err := db.Exec(fmt.Sprintf("PRAGMA user_version=%d", userSchemaVersion)); err != nil {
		return err
	}
	return nil
}

func userDSN(path string) string {
	return FileURI(path,
		"_pragma=busy_timeout(5000)"+
			"&_pragma=journal_mode(WAL)"+
			"&_pragma=synchronous(NORMAL)"+
			"&_pragma=foreign_keys(1)")
}

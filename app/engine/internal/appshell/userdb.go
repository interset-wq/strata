package appshell

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
)

// userSchemaVersion: v11 adds the runtime-metric columns to discovered
// (est_year/form/cqs/cps/len_norm — app/docs/18-runtime-metrics.md P2,
// computed once when a discovered row gains detail numbers). v7 adds
// author_profiles (on-demand author data, docs/author-profile-on-demand
// §4) — purely additive, created by the idempotent DDL replay in
// EnsureUserDB. v8 adds the works cache column to author_profiles (official
// works list replays on cache hits). v9/v10 were the retired
// adaptation-works columns; the number stays at 10 so existing user.db
// files keep opening without a downgrade.
const userSchemaVersion = 11

// userSchemaV5 is the v5-era full user.db DDL: additive across
// versions (v1 → v5), replayed idempotently on every schema pass — a
// fresh database gets the whole v5 set, then migrateV5toV6 folds the
// legacy bookshelf into the watchlist (docs/02 §v6).
const userSchemaV5 = `
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
  observed_at INTEGER NOT NULL,
  est_year    INTEGER,
  form        TEXT,
  cqs         REAL,
  cqs_state   TEXT,
  cps         REAL,
  len_norm    REAL
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

-- Local browsing footprints: one row per nid, viewed_at bumped on every
-- detail-page open. Pure local data, never uploaded.
CREATE TABLE IF NOT EXISTS browsing_history(
  nid       INTEGER PRIMARY KEY,
  viewed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_viewed ON browsing_history(viewed_at DESC);

-- On-demand author profile (v7): fetched from one of the author's book
-- detail pages when the author page opens (docs/author-profile-on-demand).
-- A snapshot, never seed data — intro and avatar change with the author.
-- Keyed by the casefolded display name (project identity convention:
-- case-insensitive, space-sensitive).
CREATE TABLE IF NOT EXISTS author_profiles(
  author_key    TEXT PRIMARY KEY,
  author_name   TEXT NOT NULL,
  author_intro  TEXT,
  author_avatar TEXT,
  verdict       TEXT NOT NULL,
  source_nid    INTEGER,
  observed_at   INTEGER NOT NULL,
  works         TEXT
);

-- Official-ranks response cache (v9): the engine's in-memory official-ranks
-- cache dies with the process; this table survives restarts so the demo-free
-- official boards don't re-fetch upstream on every cold start. Keyed by the
-- same key the API layer uses (monthly:YYYY-MM:rank / pc:current /
-- mobile:slug); TTL is enforced at read time (24h current period, 365d
-- historical — the historical bodies never change).
CREATE TABLE IF NOT EXISTS official_ranks_cache(
  key        TEXT PRIMARY KEY,
  fetched_at INTEGER NOT NULL,
  body       TEXT NOT NULL
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
	if _, err := db.Exec(userSchemaV5); err != nil {
		return fmt.Errorf("create user schema: %w", err)
	}
	if err := migrateV5toV6(db); err != nil {
		return fmt.Errorf("migrate v5→v6: %w", err)
	}
	if err := migrateV7toV8(db); err != nil {
		return fmt.Errorf("migrate v7→v8: %w", err)
	}
	if err := migrateDiscoveredMetrics(db); err != nil {
		return fmt.Errorf("migrate discovered metrics: %w", err)
	}
	if _, err := db.Exec(fmt.Sprintf("PRAGMA user_version=%d", userSchemaVersion)); err != nil {
		return err
	}
	return nil
}

// migrateV7toV8 adds the works cache column to author_profiles (docs/08
// §author-profile: the official works list is part of the snapshot and
// replays on cache hits). Idempotent: the column check tolerates replays.
func migrateV7toV8(db *sql.DB) error {
	rows, err := db.Query("PRAGMA table_info(author_profiles)")
	if err != nil {
		return err
	}
	hasWorks := false
	for rows.Next() {
		var (
			cid       int
			name      string
			typ       string
			notNull   int
			dfltValue any
			pk        int
		)
		if err := rows.Scan(&cid, &name, &typ, &notNull, &dfltValue, &pk); err != nil {
			rows.Close()
			return err
		}
		if name == "works" {
			hasWorks = true
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return err
	}
	if hasWorks {
		return nil
	}
	_, err = db.Exec("ALTER TABLE author_profiles ADD COLUMN works TEXT")
	return err
}

// migrateDiscoveredMetrics adds the runtime-metric columns to discovered
// (app/docs/18-runtime-metrics.md P2): est_year/form/cqs/cps/len_norm are
// computed once when a discovered row gains detail numbers. Idempotent
// per-column check, mirroring migrateV7toV8.
func migrateDiscoveredMetrics(db *sql.DB) error {
	cols := []struct{ name, typ string }{
		{"est_year", "INTEGER"}, {"form", "TEXT"}, {"cqs", "REAL"},
		{"cqs_state", "TEXT"}, {"cps", "REAL"}, {"len_norm", "REAL"},
	}
	for _, c := range cols {
		if !hasColumn(db, "discovered", c.name) {
			if _, err := db.Exec("ALTER TABLE discovered ADD COLUMN " +
				c.name + " " + c.typ); err != nil {
				return err
			}
		}
	}
	return nil
}

// migrateV5toV6 folds the legacy bookshelf into the watchlist
// (docs/02 §v6): the app has no reading feature, so "shelf" (save)
// becomes an inactive (poll_enabled = 0) watchlist entry while
// tracking entries keep their state; shelf_lists is renamed to
// watch_lists and watchlist gains list_id. Every step is idempotent,
// so a migration that crashes mid-way replays safely.
func migrateV5toV6(db *sql.DB) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()

	if !hasColumn(tx, "watchlist", "list_id") {
		if _, err := tx.Exec(`ALTER TABLE watchlist
ADD COLUMN list_id INTEGER NOT NULL DEFAULT 0`); err != nil {
			return err
		}
	}
	if tableExists(tx, "shelf") {
		if _, err := tx.Exec(`
INSERT OR IGNORE INTO watchlist(nid, role, added_at, poll_enabled, poll_interval, note, list_id)
SELECT nid, 'self', added_at, 0, 86400, note, COALESCE(list_id, 0)
FROM shelf`); err != nil {
			return err
		}
		if _, err := tx.Exec(`DROP TABLE shelf`); err != nil {
			return err
		}
	}
	if tableExists(tx, "shelf_lists") && !tableExists(tx, "watch_lists") {
		if _, err := tx.Exec(`ALTER TABLE shelf_lists RENAME TO watch_lists`); err != nil {
			return err
		}
	}
	return tx.Commit()
}

// queryer is satisfied by both *sql.DB and *sql.Tx.
type queryer interface {
	QueryRow(query string, args ...any) *sql.Row
	Query(query string, args ...any) (*sql.Rows, error)
}

func tableExists(q queryer, name string) bool {
	var one int
	err := q.QueryRow(
		`SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?`, name).Scan(&one)
	return err == nil
}

func hasColumn(q queryer, table, column string) bool {
	rows, err := q.Query("PRAGMA table_info(" + table + ")")
	if err != nil {
		return false
	}
	defer rows.Close()
	for rows.Next() {
		var cid, notNull, pk int
		var name, dtype string
		var dflt any
		if err := rows.Scan(&cid, &name, &dtype, &notNull, &dflt, &pk); err != nil {
			return false
		}
		if name == column {
			return true
		}
	}
	return false
}

func userDSN(path string) string {
	return FileURI(path,
		"_pragma=busy_timeout(5000)"+
			"&_pragma=journal_mode(WAL)"+
			"&_pragma=synchronous(NORMAL)"+
			"&_pragma=foreign_keys(1)")
}

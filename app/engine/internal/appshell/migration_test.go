package appshell

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// TestUserDBUpgradesOldVersion: a user.db stamped with an old schema
// version is migrated in place. Versions below v6 had additive-only
// DDL, so replaying the v5 schema is safe; v6 is the first data
// migration (bookshelf folded into the watchlist, docs/02 §v6).
func TestUserDBUpgradesOldVersion(t *testing.T) {
	path := filepath.Join(t.TempDir(), "user.db")
	db, err := sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(userSchemaV5); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("PRAGMA user_version=1"); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	if err := EnsureUserDB(path); err != nil {
		t.Fatal(err)
	}

	db, err = sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var v int
	if err := db.QueryRow("PRAGMA user_version").Scan(&v); err != nil {
		t.Fatal(err)
	}
	if v != userSchemaVersion {
		t.Fatalf("user_version = %d, want %d", v, userSchemaVersion)
	}
	var tables int
	if err := db.QueryRow(`SELECT COUNT(*) FROM sqlite_master
		WHERE type='table' AND name NOT LIKE 'sqlite_%'`).Scan(&tables); err != nil {
		t.Fatal(err)
	}
	// v5 had 13 tables; v6 drops shelf (folded into watchlist) and
	// renames shelf_lists to watch_lists (count-neutral); v7 adds
	// author_profiles (on-demand author data, docs/author-profile-
	// on-demand §4); v9 adds official_ranks_cache (persistent
	// official-boards cache, docs/sfacg-live-ranks.md); v12 adds
	// watch_events (follow-tab notifications).
	if tables != 15 {
		t.Fatalf("tables = %d, want 15", tables)
	}
}

// TestUserDBV5ToV6MigratesShelf: the v5→v6 fold moves every bookshelf
// entry into the watchlist as inactive (poll_enabled=0, list_id and
// note carried over), keeps tracking entries' state, and renames
// shelf_lists to watch_lists.
func TestUserDBV5ToV6MigratesShelf(t *testing.T) {
	path := filepath.Join(t.TempDir(), "user.db")
	db, err := sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(userSchemaV5); err != nil {
		t.Fatal(err)
	}
	stmts := []string{
		`INSERT INTO shelf(nid, added_at, list_id, note) VALUES (1001, 1000, 0, 'note-a')`,
		`INSERT INTO shelf(nid, added_at, list_id) VALUES (1002, 1001, 1)`,
		`INSERT INTO watchlist(nid, role, added_at, poll_enabled) VALUES (1001, 'self', 1002, 1)`,
		`INSERT INTO watchlist(nid, role, added_at) VALUES (1003, 'self', 1003)`,
		`INSERT INTO shelf_lists(id, name, created_at) VALUES (1, 'My Group', 1000)`,
		`PRAGMA user_version=5`,
	}
	for _, s := range stmts {
		if _, err := db.Exec(s); err != nil {
			t.Fatal(err)
		}
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	if err := EnsureUserDB(path); err != nil {
		t.Fatal(err)
	}

	db, err = sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if tableExists(db, "shelf") {
		t.Fatal("shelf table should be dropped")
	}
	if !tableExists(db, "watch_lists") {
		t.Fatal("watch_lists table should exist")
	}
	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM watchlist`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 3 {
		t.Fatalf("watchlist rows = %d, want 3", n)
	}
	// 1001 was both shelved and tracked: the tracked state wins.
	if got := watchPoll(t, db, 1001); got != 1 {
		t.Fatalf("1001 poll_enabled = %d, want 1 (tracked kept)", got)
	}
	// 1002 came from the shelf: inactive, group carried over.
	if got := watchPoll(t, db, 1002); got != 0 {
		t.Fatalf("1002 poll_enabled = %d, want 0 (shelf → inactive)", got)
	}
	if got := watchListID(t, db, 1002); got != 1 {
		t.Fatalf("1002 list_id = %d, want 1", got)
	}
	// 1003 was pure tracking: untouched.
	if got := watchPoll(t, db, 1003); got != 1 {
		t.Fatalf("1003 poll_enabled = %d, want 1", got)
	}
	if got := watchListID(t, db, 1003); got != 0 {
		t.Fatalf("1003 list_id = %d, want 0", got)
	}
	var name string
	if err := db.QueryRow(`SELECT name FROM watch_lists WHERE id = 1`).Scan(&name); err != nil {
		t.Fatal(err)
	}
	if name != "My Group" {
		t.Fatalf("watch_lists name = %q, want %q", name, "My Group")
	}
}

// TestUserDBV5ToV6CrashReplay: a migration that crashed after adding
// list_id (before dropping shelf) replays idempotently to the same
// end state — no duplicate-column error.
func TestUserDBV5ToV6CrashReplay(t *testing.T) {
	path := filepath.Join(t.TempDir(), "user.db")
	db, err := sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(userSchemaV5); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`ALTER TABLE watchlist
ADD COLUMN list_id INTEGER NOT NULL DEFAULT 0`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO shelf(nid, added_at) VALUES (1001, 1000)`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("PRAGMA user_version=5"); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	if err := EnsureUserDB(path); err != nil {
		t.Fatal(err)
	}

	db, err = sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if tableExists(db, "shelf") {
		t.Fatal("shelf table should be dropped")
	}
	if got := watchPoll(t, db, 1001); got != 0 {
		t.Fatalf("1001 poll_enabled = %d, want 0 (shelf → inactive)", got)
	}
}

func watchPoll(t *testing.T, db *sql.DB, nid int) int {
	t.Helper()
	var p int
	if err := db.QueryRow(`SELECT poll_enabled FROM watchlist WHERE nid = ?`, nid).Scan(&p); err != nil {
		t.Fatal(err)
	}
	return p
}

func watchListID(t *testing.T, db *sql.DB, nid int) int {
	t.Helper()
	var l int
	if err := db.QueryRow(`SELECT list_id FROM watchlist WHERE nid = ?`, nid).Scan(&l); err != nil {
		t.Fatal(err)
	}
	return l
}

package appshell

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// TestEnsureUserDBMigratesLegacyRefreshAttempts: the old single-row table
// (nid PRIMARY KEY) must become one row per attempt, otherwise the second
// refresh of the same book fails with UNIQUE constraint failed:
// refresh_attempts.nid (device report 2026-11-28). The version stamp is
// already current, so this exercises the unconditional rebuild path.
func TestEnsureUserDBMigratesLegacyRefreshAttempts(t *testing.T) {
	path := filepath.Join(t.TempDir(), "user.db")
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(userSchemaV5); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`DROP TABLE refresh_attempts;
CREATE TABLE refresh_attempts(
  nid          INTEGER PRIMARY KEY,
  attempted_at INTEGER NOT NULL,
  state        TEXT NOT NULL DEFAULT 'pending'
)`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO refresh_attempts(nid, attempted_at, state)
		VALUES (1555, 1700000000, 'ok')`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("PRAGMA user_version=12"); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}

	if err := EnsureUserDB(path); err != nil {
		t.Fatal(err)
	}
	// Replaying the migration must be a no-op.
	if err := EnsureUserDB(path); err != nil {
		t.Fatal(err)
	}

	db, err = sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var hasID int
	if err := db.QueryRow(`SELECT COUNT(*) FROM pragma_table_info('refresh_attempts')
		WHERE name = 'id'`).Scan(&hasID); err != nil {
		t.Fatal(err)
	}
	if hasID != 1 {
		t.Fatal("refresh_attempts.id missing after migration")
	}
	if _, err := db.Exec(`INSERT INTO refresh_attempts(nid, attempted_at, state)
		VALUES (1555, 1700000001, 'pending')`); err != nil {
		t.Fatalf("second attempt for same nid rejected: %v", err)
	}
	var n int
	if err := db.QueryRow(`SELECT COUNT(*) FROM refresh_attempts WHERE nid = 1555`).
		Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 2 {
		t.Fatalf("refresh_attempts rows = %d, want 2", n)
	}
	var state string
	if err := db.QueryRow(`SELECT state FROM refresh_attempts
		WHERE nid = 1555 AND attempted_at = 1700000000`).Scan(&state); err != nil {
		t.Fatal(err)
	}
	if state != "ok" {
		t.Fatalf("legacy state = %q, want ok", state)
	}
}

// TestEnsureUserDBV6toV7 pins the v7 upgrade path (docs/author-profile-
// on-demand ��4): an existing v6 user.db gets author_profiles created by
// the idempotent DDL replay and is stamped v7; a second pass is a no-op.
func TestEnsureUserDBV6toV7(t *testing.T) {
	legacy := filepath.Join(t.TempDir(), "user.db")

	// A legacy v6 database: the version stamp alone (real devices also
	// carry the v5/v6 tables; the replay is idempotent either way).
	db, err := sql.Open("sqlite", legacy)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("PRAGMA user_version=6"); err != nil {
		t.Fatal(err)
	}
	db.Close()

	if err := EnsureUserDB(legacy); err != nil {
		t.Fatal(err)
	}
	db, err = sql.Open("sqlite", legacy)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		t.Fatal(err)
	}
	if version != userSchemaVersion {
		t.Fatalf("user_version = %d, want %d", version, userSchemaVersion)
	}
	var one int
	err = db.QueryRow(`SELECT 1 FROM sqlite_master
	WHERE type = 'table' AND name = 'author_profiles'`).Scan(&one)
	if err != nil {
		t.Fatalf("author_profiles missing: %v", err)
	}

	// Idempotency: a second pass must be a no-op.
	if err := EnsureUserDB(legacy); err != nil {
		t.Fatal(err)
	}
}

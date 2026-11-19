package appshell

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// TestUserDBUpgradesOldVersion: a user.db stamped with an old schema
// version is migrated in place. The DDL has been stable since a26d508
// (every change so far was a brand-new table, never a column added to an
// existing one — verified by diffing the first userSchema against the
// current one), so replaying the full IF NOT EXISTS schema is a safe
// migration. This test pins that property plus the user_version bump.
func TestUserDBUpgradesOldVersion(t *testing.T) {
	path := filepath.Join(t.TempDir(), "user.db")
	db, err := sql.Open("sqlite", userDSN(path))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(userSchema); err != nil {
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
	if tables != 13 {
		t.Fatalf("tables = %d, want 13 (all user.db tables)", tables)
	}
}

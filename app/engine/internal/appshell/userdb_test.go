package appshell

import (
	"database/sql"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// TestEnsureUserDBV6toV7 pins the v7 upgrade path (docs/author-profile-
// on-demand §4): an existing v6 user.db gets author_profiles created by
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

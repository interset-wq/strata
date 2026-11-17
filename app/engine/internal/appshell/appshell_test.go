package appshell_test

import (
	"os"
	"path/filepath"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/testseed"
)

func TestInstallSeedIsIdempotent(t *testing.T) {
	assets, data := t.TempDir(), t.TempDir()
	m, err := testseed.Build(assets, data)
	if err != nil {
		t.Fatal(err)
	}
	first, err := appshell.InstallSeed(assets, data, m)
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(first)
	if err != nil {
		t.Fatal(err)
	}
	if info.Size() != m.Files.DB.Bytes {
		t.Fatalf("size = %d, want %d", info.Size(), m.Files.DB.Bytes)
	}
	second, err := appshell.InstallSeed(assets, data, m)
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatalf("paths differ: %s / %s", first, second)
	}
}

func TestEnsureUserDBIsIdempotent(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "user.db")
	for i := 0; i < 2; i++ {
		if err := appshell.EnsureUserDB(path); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := os.Stat(path); err != nil {
		t.Fatal(err)
	}
}

func TestLoadManifest(t *testing.T) {
	assets, data := t.TempDir(), t.TempDir()
	if _, err := testseed.Build(assets, data); err != nil {
		t.Fatal(err)
	}
	m, err := appshell.LoadManifest(assets)
	if err != nil {
		t.Fatal(err)
	}
	if m.SeedVersion != "test-1" || m.BookCount != 6 {
		t.Fatalf("manifest = %+v", m)
	}
}

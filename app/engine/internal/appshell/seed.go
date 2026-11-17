package appshell

import (
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var safeVersion = regexp.MustCompile(`^[0-9A-Za-z._-]+$`)

// InstallSeed decompresses the bundled seed once per seed_version and returns
// the installed DB path. The DB is opened read-only by the store.
func InstallSeed(assetsDir, dataDir string, m *Manifest) (string, error) {
	if !safeVersion.MatchString(m.SeedVersion) {
		return "", fmt.Errorf("unsafe seed_version %q", m.SeedVersion)
	}
	dir := filepath.Join(dataDir, "seed")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	target := filepath.Join(dir, "seed-"+m.SeedVersion+".db")

	if info, err := os.Stat(target); err == nil {
		if info.Size() == m.Files.DB.Bytes {
			return target, nil
		}
		if err := os.Remove(target); err != nil {
			return "", fmt.Errorf("remove corrupt seed: %w", err)
		}
	}

	gzPath := filepath.Join(assetsDir, m.Files.Gz.Name)
	src, err := os.Open(gzPath)
	if err != nil {
		return "", fmt.Errorf("open %s: %w", gzPath, err)
	}
	defer src.Close()
	gz, err := gzip.NewReader(src)
	if err != nil {
		return "", fmt.Errorf("gzip %s: %w", gzPath, err)
	}
	defer gz.Close()

	tmp := target + ".tmp"
	_ = os.Remove(tmp)
	dst, err := os.OpenFile(tmp, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return "", err
	}
	hash := sha256.New()
	written, copyErr := io.Copy(io.MultiWriter(dst, hash), gz)
	syncErr := dst.Sync()
	closeErr := dst.Close()
	if copyErr != nil || syncErr != nil || closeErr != nil {
		_ = os.Remove(tmp)
		return "", fmt.Errorf("extract seed: %v %v %v", copyErr, syncErr, closeErr)
	}
	if written != m.Files.DB.Bytes {
		_ = os.Remove(tmp)
		return "", fmt.Errorf("seed size %d != manifest %d", written, m.Files.DB.Bytes)
	}
	got := hex.EncodeToString(hash.Sum(nil))
	if !strings.EqualFold(got, m.Files.DB.SHA256) {
		_ = os.Remove(tmp)
		return "", fmt.Errorf("seed sha256 %s != manifest %s", got, m.Files.DB.SHA256)
	}
	if err := os.Rename(tmp, target); err != nil {
		_ = os.Remove(tmp)
		return "", err
	}

	removeOldSeeds(dir, filepath.Base(target))
	return target, nil
}

func removeOldSeeds(dir, keep string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || name == keep {
			continue
		}
		if strings.HasPrefix(name, "seed-") && strings.HasSuffix(name, ".db") {
			_ = os.Remove(filepath.Join(dir, name))
		}
	}
}

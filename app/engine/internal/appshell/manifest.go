package appshell

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Manifest mirrors app/assets/manifest.json written by the seed builder.
type Manifest struct {
	SchemaVersion int    `json:"schema_version"`
	SeedVersion   string `json:"seed_version"`
	ContentEnd    string `json:"content_end"`
	BuiltAt       string `json:"built_at"`
	BookCount     int    `json:"book_count"`
	LicensedCount int    `json:"licensed_count"`
	TagCount      int    `json:"tag_count"`
	TagRows       int    `json:"tag_rows"`
	GenMin        int    `json:"gen_min"`
	GenMax        int    `json:"gen_max"`
	Counts        struct {
		StatsUniverse int `json:"stats_universe"`
		Base          int `json:"base"`
		ShortAdded    int `json:"short_added"`
		LicensedAdded int `json:"licensed_added"`
		Seed          int `json:"seed"`
	} `json:"counts"`
	Files struct {
		DB FileInfo `json:"db"`
		Gz FileInfo `json:"gz"`
	} `json:"files"`
}

type FileInfo struct {
	Name   string `json:"name"`
	Bytes  int64  `json:"bytes"`
	SHA256 string `json:"sha256"`
}

type Paths struct {
	AssetsDir string
	DataDir   string
}

// ResolvePaths finds the bundled assets and the writable data directory.
func ResolvePaths(assetsFlag, dataFlag string) (Paths, error) {
	assets, err := resolveAssets(assetsFlag)
	if err != nil {
		return Paths{}, err
	}
	data, err := resolveData(dataFlag)
	if err != nil {
		return Paths{}, err
	}
	return Paths{AssetsDir: assets, DataDir: data}, nil
}

func resolveAssets(flag string) (string, error) {
	candidates := []string{flag, os.Getenv("STRATA_ASSETS")}
	cwd, _ := os.Getwd()
	if cwd != "" {
		candidates = append(candidates,
			filepath.Join(cwd, "assets"),
			filepath.Join(cwd, "..", "assets"),
			filepath.Join(cwd, "..", "..", "assets"),
		)
	}
	if exe, err := os.Executable(); err == nil {
		dir := filepath.Dir(exe)
		candidates = append(candidates,
			filepath.Join(dir, "assets"),
			filepath.Join(dir, "..", "assets"),
		)
	}
	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		abs, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}
		if _, err := os.Stat(filepath.Join(abs, "manifest.json")); err == nil {
			return abs, nil
		}
	}
	return "", fmt.Errorf("assets directory not found; pass --assets (looked for manifest.json)")
}

func resolveData(flag string) (string, error) {
	raw := flag
	if raw == "" {
		raw = os.Getenv("STRATA_DATA_DIR")
	}
	if raw == "" {
		base, err := os.UserConfigDir()
		if err != nil {
			return "", fmt.Errorf("resolve user config dir: %w", err)
		}
		raw = filepath.Join(base, "Strata")
	}
	abs, err := filepath.Abs(raw)
	if err != nil {
		return "", err
	}
	return abs, nil
}

func LoadManifest(assetsDir string) (*Manifest, error) {
	path := filepath.Join(assetsDir, "manifest.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", path, err)
	}
	var m Manifest
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	if m.SeedVersion == "" || m.BookCount <= 0 || m.Files.Gz.Name == "" {
		return nil, fmt.Errorf("manifest %s is incomplete", path)
	}
	return &m, nil
}

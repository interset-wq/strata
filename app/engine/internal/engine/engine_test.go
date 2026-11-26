package engine

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"strata/engine/internal/testseed"
)

func TestStartServesAndShutsDown(t *testing.T) {
	assets, data := t.TempDir(), t.TempDir()
	if _, err := testseed.Build(assets, data); err != nil {
		t.Fatal(err)
	}
	e, err := Start(assets, data)
	if err != nil {
		t.Fatal(err)
	}

	resp, err := http.Get(e.Addr() + "/strata/healthz")
	if err != nil {
		t.Fatalf("healthz: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("healthz status = %d", resp.StatusCode)
	}
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["book_count"].(float64) != 17 || body["seed_version"] != "test-1" {
		t.Fatalf("healthz body = %v", body)
	}

	if err := e.Shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
	if err := <-e.Done(); err != nil {
		t.Fatalf("done: %v", err)
	}
	// Port is dynamically assigned on loopback.
	if got := e.Addr(); !strings.HasPrefix(got, "http://127.0.0.1:") {
		t.Fatalf("addr = %q", got)
	}
}

func TestStartRejectsEmptyPaths(t *testing.T) {
	if _, err := Start("", "x"); err == nil {
		t.Fatal("empty assets accepted")
	}
	if _, err := Start("x", ""); err == nil {
		t.Fatal("empty data dir accepted")
	}
}

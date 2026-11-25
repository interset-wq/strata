package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/crawl"
	"strata/engine/internal/store"
	"strata/engine/internal/testseed"
)

// newPreorderTestServer builds the test seed with the seams exposed (the
// preorderFetch override keeps the endpoint tests off the network).
func newPreorderTestServer(t *testing.T) (*httptest.Server, *Server) {
	t.Helper()
	assets, data := t.TempDir(), t.TempDir()
	m, err := testseed.Build(assets, data)
	if err != nil {
		t.Fatal(err)
	}
	seedPath, err := appshell.InstallSeed(assets, data, m)
	if err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(appshell.UserDBPath(data), seedPath, m)
	if err != nil {
		t.Fatal(err)
	}
	srv := NewServer(st)
	ts := httptest.NewServer(srv.engine)
	t.Cleanup(func() {
		ts.Close()
		st.Close()
	})
	return ts, srv
 }

// TestPreorder covers Saturday normalization, the in_seed join against the
// test seed, and the 24h per-issue cache (a failing seam after a successful
// fetch must still be served from cache).
func TestPreorder(t *testing.T) {
	ts, srv := newPreorderTestServer(t)
	srv.preorderFetch = func(ctx context.Context, client *http.Client, l *crawl.Limiter,
		date string, foreground bool) ([]crawl.PreOrderItem, error) {
		if date != "20261128" {
			t.Fatalf("fetch date = %q, want 20261128 (clamped Saturday)", date)
		}
		if !foreground {
			t.Fatalf("preorder must use the foreground limiter lane")
		}
		return []crawl.PreOrderItem{
			{NovelID: 1006, NovelName: "库内精选", IsMainPush: true, Tags: []string{"玄幻"}},
			{NovelID: 99999999, NovelName: "库外精选", Intro: "库外简介"},
		}, nil
	}

	// Wednesday clamps to the Saturday of the same week.
	body := getJSON(t, ts.URL+"/strata/preorder?date=2026-11-25", http.StatusOK)
	if body["date"] != "20261128" {
		t.Fatalf("date = %v, want 20261128", body["date"])
	}
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("len(items) = %d, want 2", len(items))
	}
	first := items[0].(map[string]any)
	if first["in_seed"] != true {
		t.Fatalf("nid 1006 should be in_seed: %v", first)
	}
	lib := first["in_lib"].(map[string]any)
	if lib["author"] == "" {
		t.Fatalf("in_lib.author missing: %v", first)
	}
	second := items[1].(map[string]any)
	if second["in_seed"] != false || second["in_lib"] != nil {
		t.Fatalf("off-library item should not be in_seed: %v", second)
	}

	// Cache: a failing seam after the successful fetch is still served.
	srv.preorderFetch = func(ctx context.Context, client *http.Client, l *crawl.Limiter,
		date string, foreground bool) ([]crawl.PreOrderItem, error) {
		return nil, context.DeadlineExceeded
	}
	body2 := getJSON(t, ts.URL+"/strata/preorder?date=20261128", http.StatusOK)
	if len(body2["items"].([]any)) != 2 {
		t.Fatalf("cached items = %v", body2["items"])
	}
}

// TestPreorderBadDate: non-date input is a 400 without touching upstream.
func TestPreorderBadDate(t *testing.T) {
	ts, srv := newPreorderTestServer(t)
	srv.preorderFetch = func(ctx context.Context, client *http.Client, l *crawl.Limiter,
		date string, foreground bool) ([]crawl.PreOrderItem, error) {
		t.Fatalf("upstream must not be called for a bad date")
		return nil, nil
	}
	getJSON(t, ts.URL+"/strata/preorder?date=notadate", http.StatusBadRequest)
}

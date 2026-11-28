package api

import (
	"context"
	"net/http"
	"testing"

	"strata/engine/internal/crawl"
)

// TestVipPush covers Saturday normalization, the seed join, and the 24h
// per-issue cache — same contract as preorder, different upstream line.
func TestVipPush(t *testing.T) {
	ts, srv := newPreorderTestServer(t)
	srv.vippushFetch = func(ctx context.Context, client *http.Client, l *crawl.Limiter,
		date string, foreground bool) ([]crawl.VipPushItem, error) {
		if date != "20261128" {
			t.Fatalf("fetch date = %q, want 20261128 (clamped Saturday)", date)
		}
		if !foreground {
			t.Fatalf("vippush must use the foreground limiter lane")
		}
		return []crawl.VipPushItem{
			{Nid: 1006, Title: "库内上架", Genre: "玄幻", Tags: []string{"热血"}, Cover: "https://example.test/a.jpg"},
			{Nid: 99999999, Title: "库外上架", Genre: "都市"},
		}, nil
	}

	body := getJSON(t, ts.URL+"/strata/vippush?date=2026-11-25", http.StatusOK)
	if body["date"] != "20261128" {
		t.Fatalf("date = %v, want 20261128", body["date"])
	}
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("len(items) = %d, want 2", len(items))
	}
	first := items[0].(map[string]any)
	if first["in_seed"] != true || first["genre"] != "玄幻" {
		t.Fatalf("first item = %v", first)
	}
	if first["in_lib"].(map[string]any)["author"] == "" {
		t.Fatalf("in_lib.author missing: %v", first)
	}
	if second := items[1].(map[string]any); second["in_seed"] != false || second["in_lib"] != nil {
		t.Fatalf("off-library item = %v", second)
	}

	// Cache: a failing seam after a successful fetch is still served.
	srv.vippushFetch = func(ctx context.Context, client *http.Client, l *crawl.Limiter,
		date string, foreground bool) ([]crawl.VipPushItem, error) {
		return nil, context.DeadlineExceeded
	}
	body2 := getJSON(t, ts.URL+"/strata/vippush?date=20261128", http.StatusOK)
	if len(body2["items"].([]any)) != 2 {
		t.Fatalf("cached items = %v", body2["items"])
	}
}

func TestVipPushBadDate(t *testing.T) {
	ts, srv := newPreorderTestServer(t)
	srv.vippushFetch = func(ctx context.Context, client *http.Client, l *crawl.Limiter,
		date string, foreground bool) ([]crawl.VipPushItem, error) {
		t.Fatalf("upstream must not be called for a bad date")
		return nil, nil
	}
	getJSON(t, ts.URL+"/strata/vippush?date=notadate", http.StatusBadRequest)
}

package api

import (
	"net/http"
	"testing"
)

// TestSearchByNID pins the nid-search boundary: only a '#id' query is an
// exact lookup (testseed nid 1001 "Long A" — no title/author LIKE would
// match the bare digits, so this proves the nid branch); a bare number is a
// keyword query like any other, and an unknown #nid misses so the UI can
// render the 未收录 row.
func TestSearchByNID(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/search?q=%231001", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("q=#1001 items = %v", items)
	}
	it := items[0].(map[string]any)
	if it["nid"].(float64) != 1001 || it["in_seed"] != true {
		t.Fatalf("q=#1001 item = %v", it)
	}
	// Bare number → keyword path: the digits match no title/author, so the
	// result list is empty (and NOT the nid branch — no in_seed row).
	body = getJSON(t, srv.URL+"/strata/search?q=1001", http.StatusOK)
	if items := body["items"].([]any); len(items) != 0 {
		t.Fatalf("q=1001 (bare) items = %v", items)
	}
	// Miss: unknown #nid → empty items (UI 未收录 row).
	body = getJSON(t, srv.URL+"/strata/search?q=%23999999", http.StatusOK)
	if items := body["items"].([]any); len(items) != 0 {
		t.Fatalf("q=#999999 items = %v", items)
	}
}

package api

import (
	"net/http"
	"net/url"
	"testing"
)

// TestAuthorBooks: author-books rows carry the seed display fields in
// est_date timeline order (docs/17 §3). The retired universe percentile
// column is no longer part of the row (E.30 — the two-DB equality rule).
func TestAuthorBooks(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t,
		srv.URL+"/strata/author-books?author="+url.QueryEscape("Author C")+"&limit=200",
		http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	seen := map[int]bool{}
	for _, raw := range items {
		m := raw.(map[string]any)
		seen[int(m["nid"].(float64))] = true
		if _, has := m["fav_pctl"]; has {
			t.Fatalf("book %v still carries fav_pctl: %v", m["nid"], m)
		}
	}
	if !seen[1003] || !seen[1004] {
		t.Fatalf("want 1003 and 1004, got %v", seen)
	}

	// Licensed author: the row is still served (searchable/detail-visible),
	// just without any score fields.
	body = getJSON(t,
		srv.URL+"/strata/author-books?author="+url.QueryEscape("天闻角川")+"&limit=200",
		http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("licensed author items = %v", items)
	}
	if m := items[0].(map[string]any); m["nid"].(float64) != 2001 {
		t.Fatalf("licensed author book = %v", m)
	}
}

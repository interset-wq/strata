package api

import (
	"net/http"
	"net/url"
	"testing"
)

// TestBookAwardsBadge: the detail response carries the seed award rows
// (schema v5); a book without awards omits the field entirely.
func TestBookAwardsBadge(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/books/3003", http.StatusOK)
	awards, ok := body["awards"].([]any)
	if !ok || len(awards) != 1 {
		t.Fatalf("awards = %v", body["awards"])
	}
	a := awards[0].(map[string]any)
	if a["edition"] != "2025春征" || a["award"] != "金奖" {
		t.Fatalf("award = %v", a)
	}
	// The field is always present on seed-book details; no awards = empty
	// list (a stable contract the client can parse unconditionally).
	body = getJSON(t, srv.URL+"/strata/books/1001", http.StatusOK)
	awards, ok = body["awards"].([]any)
	if !ok || len(awards) != 0 {
		t.Fatalf("book without awards must have an empty list: %v", body["awards"])
	}
}

// TestContestArchiveAwards: the archive block lists in-library award books
// per event (raw award values pass through; the UI renders the placeholder);
// unmapped events yield an empty list and the items shape is unchanged.
func TestContestArchiveAwards(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("2025春季征文"), http.StatusOK)
	awards, ok := body["awards"].([]any)
	if !ok || len(awards) != 1 {
		t.Fatalf("awards = %v", body["awards"])
	}
	a := awards[0].(map[string]any)
	if a["nid"].(float64) != 3003 || a["award"] != "金奖" ||
		a["title"] != "Spring Short Z" || a["category"] != "短篇" {
		t.Fatalf("award row = %v", a)
	}
	body = getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("十三征"), http.StatusOK)
	awards = body["awards"].([]any)
	if len(awards) != 1 || awards[0].(map[string]any)["award"] != "待逐档标定" {
		t.Fatalf("awards = %v", awards)
	}
	// 七征 (summer N征) has no award edition: empty block, still 200.
	body = getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("七征"), http.StatusOK)
	awards = body["awards"].([]any)
	if len(awards) != 0 {
		t.Fatalf("unmapped event must have no awards: %v", awards)
	}
	if items := body["items"].([]any); len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
}

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

// TestContestArchiveAwards: the archive block lists contest-achieve's verified
// winners per event, real award names in an awards[] array (never the old
// '待逐档标定' placeholder), in award-tier order. A winner absent from seed
// still shows title + award with in_seed=false — a verified winner is never
// hidden just because our crawler missed the book. Awards are display-only:
// they never feed admission, ordering or scoring (docs/contest-display-in-app.md §6).
func TestContestArchiveAwards(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("2025春季征文"), http.StatusOK)
	awards, ok := body["awards"].([]any)
	if !ok || len(awards) != 10 {
		t.Fatalf("awards = %v", body["awards"])
	}
	// Award-tier order: 金奖 → 银奖 → 铜奖 → …; the field is an array.
	// nid 738162 is in the test seed (2026-11-26 fixture) — the in-seed
	// join must backfill est_year (old code self-assigned r.EstYear and
	// silently dropped it; same for form).
	a := awards[0].(map[string]any)
	if a["nid"].(float64) != 738162 || a["awards"].([]any)[0] != "金奖" ||
		a["in_seed"] != true || a["title"] == "" {
		t.Fatalf("award row = %v", a)
	}
	if a["est_year"].(float64) != 2019 {
		t.Fatalf("in-seed award row lost est_year: %v", a)
	}
	if _, present := a["form"]; !present {
		t.Fatalf("in-seed award row lost form: %v", a)
	}
	if _, bogus := a["award"]; bogus {
		t.Fatalf("legacy single award field must be gone: %v", a)
	}
	// 七征 (summer N征) has 45 verified winners including the dialogue tracks;
	// the old mapping only knew 七征冬征, so this block used to be empty.
	body = getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("七征"), http.StatusOK)
	awards = body["awards"].([]any)
	if len(awards) != 45 {
		t.Fatalf("七征 awards = %v", awards)
	}
	if items := body["items"].([]any); len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	// 2023 春征 has a nid with two awards — both must survive in one row.
	body = getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("2023春季征文"), http.StatusOK)
	for _, raw := range body["awards"].([]any) {
		a := raw.(map[string]any)
		if a["nid"].(float64) == 635145 {
			got := a["awards"].([]any)
			if len(got) != 2 || got[0] != "推荐奖" || got[1] != "鼓励奖" {
				t.Fatalf("multi-award row = %v", a)
			}
			return
		}
	}
	t.Fatal("nid 635145 missing from 2023春季征文 awards")
}

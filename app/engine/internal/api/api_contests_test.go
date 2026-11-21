package api

import (
	"net/http"
	"net/url"
	"testing"
)

func TestContestArchive(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests", http.StatusOK)
	groups, ok := body["groups"].([]any)
	if !ok || len(groups) < 4 {
		t.Fatalf("groups = %v", body["groups"])
	}
	var sawZheng, sawThirteen bool
	for _, raw := range groups {
		g := raw.(map[string]any)
		switch g["name"] {
		case "七征":
			sawZheng = true
			if g["count"].(float64) != 2 || g["series"] != "x" {
				t.Fatalf("七征 = %v", g)
			}
		case "十三征":
			sawThirteen = true
			if g["start"] != "2025-05-04" || g["end"] != "2025-10-07" {
				t.Fatalf("十三征 = %v", g)
			}
		}
	}
	if !sawZheng || !sawThirteen {
		t.Fatalf("missing groups: zheng=%v thirteen=%v", sawZheng, sawThirteen)
	}
}

func TestContestArchiveBooks(t *testing.T) {
	srv, _ := newTestServer(t)
	// missing contest → 400
	getJSON(t, srv.URL+"/strata/contests/books", http.StatusBadRequest)
	// N征 event: prefix match pulls in both divisions.
	body := getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("七征"), http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	// per caps each form: 崩坏3征文's two ip_collab books → one at per=1.
	body = getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("崩坏3征文")+"&per=1", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 1006 {
		t.Fatalf("items = %v", items)
	}
}

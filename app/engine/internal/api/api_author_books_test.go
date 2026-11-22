package api

import (
	"net/http"
	"net/url"
	"testing"
)

// TestAuthorBooksFavPctl: author-books rows now carry the same-generation
// favourite percentile (docs/17 §3: the only engine change) — seed books
// real values, licensed (NULL pctl in seed) degrade to 0.
func TestAuthorBooksFavPctl(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t,
		srv.URL+"/strata/author-books?author="+url.QueryEscape("Author C")+"&limit=200",
		http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	byNID := map[int]float64{}
	for _, raw := range items {
		m := raw.(map[string]any)
		byNID[int(m["nid"].(float64))] = m["fav_pctl"].(float64)
	}
	if byNID[1003] != 0.99 || byNID[1004] != 0.6 {
		t.Fatalf("fav_pctl = %v, want 1003:0.99 1004:0.6", byNID)
	}

	// Licensed author: NULL percentile degrades to 0 (docs/17 §5: licensed
	// books stay out of quality modules).
	body = getJSON(t,
		srv.URL+"/strata/author-books?author="+url.QueryEscape("天闻角川")+"&limit=200",
		http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("items = %v", items)
	}
	if got := items[0].(map[string]any)["fav_pctl"].(float64); got != 0 {
		t.Fatalf("licensed fav_pctl = %v, want 0", got)
	}
}

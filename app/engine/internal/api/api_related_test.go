package api

import (
	"context"
	"net/http"
	"testing"
)

// TestRelated: GET /strata/related (docs/related-books.md §4) serves the
// tiered rail with its diagnostics in meta and the plain RankItem rows in
// items. Covers are planted only to pin cover_url passthrough; covers are not
// an admission gate (sfacg lost covers of many good books), and the fixture's
// candidates would be returned without them too.
func TestRelated(t *testing.T) {
	srv, st := newTestServer(t)
	for _, nid := range []int64{1001, 1003, 3001} {
		if _, err := st.DB.ExecContext(context.Background(),
			`INSERT INTO covers (nid, cover, fetched_at) VALUES (?, ?, ?)`,
			nid, "related-cover.jpg", 1); err != nil {
			t.Fatal(err)
		}
	}

	body := getJSON(t, srv.URL+"/strata/related?nid=2001&limit=1", http.StatusOK)
	meta := body["meta"].(map[string]any)
	if meta["pool"] != "seed" || meta["form"] != "long" ||
		meta["genre"] != "魔幻" || meta["tier"] != "a" || meta["ordering"] != "cqs" {
		t.Fatalf("meta = %v", meta)
	}
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("items = %v", items)
	}
	first := items[0].(map[string]any)
	if first["nid"].(float64) != 1001 {
		t.Fatalf("A′ item = %v", first)
	}
	if _, has := first["fav_pctl"]; has {
		t.Fatalf("row still carries a retired percentile column: %v", first)
	}
	if first["cover_url"] != "related-cover.jpg" {
		t.Fatalf("cover_url = %v", first["cover_url"])
	}

	// limit 默认 8；库外锚点出空 rail + tier=none，UI 据此整行隐藏。
	body = getJSON(t, srv.URL+"/strata/related?nid=999999", http.StatusOK)
	if len(body["items"].([]any)) != 0 ||
		body["meta"].(map[string]any)["tier"] != "none" {
		t.Fatalf("unknown anchor = %v", body)
	}

	for _, bad := range []string{
		"/strata/related", "/strata/related?nid=0", "/strata/related?nid=-5",
		"/strata/related?nid=abc", "/strata/related?nid=1001&limit=0",
		"/strata/related?nid=1001&limit=21", "/strata/related?nid=1001&limit=x",
	} {
		getJSON(t, srv.URL+bad, http.StatusBadRequest)
	}
}

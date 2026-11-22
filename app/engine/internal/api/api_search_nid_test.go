package api

import (
	"net/http"
	"testing"
)

// TestSearchByNID: a 4+ digit numeric query is an exact nid lookup over
// seed + discovered (docs/08 §search); a miss returns empty items so the
// UI can render the 未收录 row; short digit strings keep the keyword path.
func TestSearchByNID(t *testing.T) {
	srv, _ := newTestServer(t)
	// Exact seed hit (testseed nid 1001 "Long A" — no title/author LIKE
	// would match the bare digits, so this proves the nid branch).
	body := getJSON(t, srv.URL+"/strata/search?q=1001", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("q=1001 items = %v", items)
	}
	it := items[0].(map[string]any)
	if it["nid"].(float64) != 1001 || it["in_seed"] != true {
		t.Fatalf("q=1001 item = %v", it)
	}
	// Miss: unknown nid → empty items (UI 未收录 row).
	body = getJSON(t, srv.URL+"/strata/search?q=999999", http.StatusOK)
	if items := body["items"].([]any); len(items) != 0 {
		t.Fatalf("q=999999 items = %v", items)
	}
}

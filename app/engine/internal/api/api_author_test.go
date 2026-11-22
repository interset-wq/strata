package api

import (
	"context"
	"net/http"
	"net/url"
	"testing"
	"time"

	"strata/engine/internal/store"
)

// TestAuthorProfileOffLibrary: the profile endpoint diffs the mobile
// 作品集 (untruncated full works list, user ruling 2026-11-22) against
// seed membership and serves the off-library remainder in page order;
// works itself stays the official full list (docs/author-profile-on-demand
// §6).
func TestAuthorProfileOffLibrary(t *testing.T) {
	srv, st := newTestServer(t)
	works := `[{"nid":1001,"title":"Long A"},{"nid":9001,"title":"Off X"},{"nid":9002,"title":"Off Y"}]`
	if err := st.SaveAuthorProfile(context.Background(), &store.AuthorProfile{
		AuthorKey: "author a", AuthorName: "Author A", Verdict: "ok",
		SourceNID: 1001, ObservedAt: time.Now().Unix(), Works: &works,
	}); err != nil {
		t.Fatal(err)
	}
	body := getJSON(t, srv.URL+"/strata/author-profile?author="+
		url.QueryEscape("Author A")+"&nid=1001", http.StatusOK)
	if body["source"] != "cache" {
		t.Fatalf("source = %v", body["source"])
	}
	// Full works list unchanged (3 = 1 seed + 2 off-library).
	if w := body["works"].([]any); len(w) != 3 {
		t.Fatalf("works = %v", w)
	}
	off := body["offlibrary"].([]any)
	if len(off) != 2 {
		t.Fatalf("offlibrary = %v", body["offlibrary"])
	}
	if off[0].(map[string]any)["nid"].(float64) != 9001 ||
		off[1].(map[string]any)["nid"].(float64) != 9002 {
		t.Fatalf("offlibrary order = %v", off)
	}
}

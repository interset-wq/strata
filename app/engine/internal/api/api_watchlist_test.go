package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"testing"

	"strata/engine/internal/store"
)

// doBodyJSON is getJSON with an explicit method and JSON body.
func doBodyJSON(t *testing.T, method, url, body string, status int) map[string]any {
	t.Helper()
	req, err := http.NewRequest(method, url, bytes.NewBufferString(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != status {
		t.Fatalf("%s status = %d, want %d", url, resp.StatusCode, status)
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		t.Fatal(err)
	}
	return out
}

// TestWatchlistRole: POST/PUT accept role (docs/07 §1: role 可改、UPDATE
// 一列、历史曲线连续); invalid role → 400; the old {active} contract still
// works with role defaulting to self.
func TestWatchlistRole(t *testing.T) {
	srv, _ := newTestServer(t)
	doBodyJSON(t, http.MethodPost, srv.URL+"/strata/watchlist/1002",
		`{"active":true,"role":"peer"}`, http.StatusOK)
	body := getJSON(t, srv.URL+"/strata/watchlist", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["role"] != "peer" {
		t.Fatalf("items = %v", items)
	}
	// Role switch is a PUT (watchSetActive) — a POST would re-run watchAdd
	// and INSERT OR IGNORE keeps the existing row's role.
	doBodyJSON(t, http.MethodPut, srv.URL+"/strata/watchlist/1002",
		`{"role":"self"}`, http.StatusOK)
	body = getJSON(t, srv.URL+"/strata/watchlist", http.StatusOK)
	if got := body["items"].([]any)[0].(map[string]any)["role"]; got != "self" {
		t.Fatalf("role = %v, want self", got)
	}
	doBodyJSON(t, http.MethodPost, srv.URL+"/strata/watchlist/1003",
		`{"role":"bogus"}`, http.StatusBadRequest)
	doBodyJSON(t, http.MethodPost, srv.URL+"/strata/watchlist/1004", `{"active":true}`, http.StatusOK)
	body = getJSON(t, srv.URL+"/strata/watchlist", http.StatusOK)
	if n := len(body["items"].([]any)); n != 2 {
		t.Fatalf("items = %v", body["items"])
	}
}

// TestWatchlistCap: the 100-book hard cap (docs/07 §1) rejects a NEW entry
// with 409 watchlist_full; re-adding an existing entry stays a no-op.
func TestWatchlistCap(t *testing.T) {
	srv, st := newTestServer(t)
	ctx := context.Background()
	for i := 0; i < store.WatchlistCap-1; i++ {
		if err := st.WatchAdd(ctx, int64(40000+i), int64(1000+i), false, "self"); err != nil {
			t.Fatalf("fill %d: %v", i, err)
		}
	}
	// The 100th slot: still allowed.
	doBodyJSON(t, http.MethodPost, srv.URL+"/strata/watchlist/3001", `{}`, http.StatusOK)
	// A new book at the cap → 409.
	doBodyJSON(t, http.MethodPost, srv.URL+"/strata/watchlist/999999", `{}`, http.StatusConflict)
	// Re-adding an existing entry is a no-op, not a cap error.
	doBodyJSON(t, http.MethodPost, srv.URL+"/strata/watchlist/3001", `{}`, http.StatusOK)
}

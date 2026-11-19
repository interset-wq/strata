package api

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

// Endpoints over the writable user DB (shelf / history / observations /
// settings / watchlist / refresh cooldown). Store-level behaviour is
// covered in internal/store/userdb_test.go; here we pin the HTTP contract:
// request shapes, response envelopes, and error codes.

func reqJSON(t *testing.T, method, url, body string) (int, map[string]any) {
	t.Helper()
	req, err := http.NewRequest(method, url, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("decode %s %s (HTTP %d): %v", method, url, resp.StatusCode, err)
	}
	return resp.StatusCode, out
}

func TestShelfEndpoints(t *testing.T) {
	srv, _ := newTestServer(t)
	code, body := reqJSON(t, "GET", srv.URL+"/strata/shelf", "")
	if code != http.StatusOK || len(body["items"].([]any)) != 0 {
		t.Fatalf("empty shelf = %d %+v", code, body)
	}
	code, body = reqJSON(t, "PUT", srv.URL+"/strata/shelf", `{"nid":1001}`)
	if code != http.StatusOK || body["ok"] != true {
		t.Fatalf("shelf add = %d %+v", code, body)
	}
	// duplicate add stays ok (idempotent)
	code, _ = reqJSON(t, "PUT", srv.URL+"/strata/shelf", `{"nid":1001}`)
	if code != http.StatusOK {
		t.Fatalf("duplicate shelf add = %d", code)
	}
	code, body = reqJSON(t, "GET", srv.URL+"/strata/shelf", "")
	items := body["items"].([]any)
	if code != http.StatusOK || len(items) != 1 ||
		items[0].(map[string]any)["nid"].(float64) != 1001 {
		t.Fatalf("shelf list = %d %+v", code, items)
	}
	code, _ = reqJSON(t, "PUT", srv.URL+"/strata/shelf", `{}`)
	if code != http.StatusBadRequest {
		t.Fatalf("shelf add without nid = %d, want 400", code)
	}
	code, body = reqJSON(t, "DELETE", srv.URL+"/strata/shelf/1001", "")
	if code != http.StatusOK || body["ok"] != true {
		t.Fatalf("shelf remove = %d %+v", code, body)
	}
	code, body = reqJSON(t, "GET", srv.URL+"/strata/shelf", "")
	if code != http.StatusOK || len(body["items"].([]any)) != 0 {
		t.Fatalf("shelf after remove = %d %+v", code, body)
	}
}

func TestHistoryEndpoints(t *testing.T) {
	srv, _ := newTestServer(t)
	code, body := reqJSON(t, "POST", srv.URL+"/strata/history/1001", "")
	if code != http.StatusOK || body["recorded"] != true {
		t.Fatalf("record = %d %+v", code, body)
	}
	// viewed_at is second-granular: keep the order deterministic
	time.Sleep(1100 * time.Millisecond)
	code, _ = reqJSON(t, "POST", srv.URL+"/strata/history/1002", "")
	if code != http.StatusOK {
		t.Fatalf("record 1002 = %d", code)
	}
	code, body = reqJSON(t, "GET", srv.URL+"/strata/history?limit=5", "")
	items, _ := body["items"].([]any)
	if code != http.StatusOK || len(items) != 2 ||
		items[0].(map[string]any)["nid"].(float64) != 1002 ||
		items[1].(map[string]any)["nid"].(float64) != 1001 {
		t.Fatalf("history = %d %+v, want [1002 1001] newest first", code, items)
	}
	code, _ = reqJSON(t, "POST", srv.URL+"/strata/history/abc", "")
	if code != http.StatusBadRequest {
		t.Fatalf("bad nid = %d, want 400", code)
	}
}

func TestObservationsEndpoint(t *testing.T) {
	srv, _ := newTestServer(t)
	// testseed ships exactly one observation for nid 1001
	code, body := reqJSON(t, "GET", srv.URL+"/strata/books/1001/observations", "")
	items, _ := body["items"].([]any)
	if code != http.StatusOK || len(items) != 1 {
		t.Fatalf("observations = %d %+v", code, body)
	}
	row := items[0].(map[string]any)
	if _, ok := row["observed_at"]; !ok {
		t.Fatalf("observation row missing observed_at: %+v", row)
	}
	// unknown nid: empty list, not an error
	code, body = reqJSON(t, "GET", srv.URL+"/strata/books/999999/observations", "")
	if code != http.StatusOK || len(body["items"].([]any)) != 0 {
		t.Fatalf("unknown nid = %d %+v", code, body)
	}
}

func TestSettingsEndpoints(t *testing.T) {
	srv, _ := newTestServer(t)
	// default: rate limit on, 24h window
	code, body := reqJSON(t, "GET", srv.URL+"/strata/settings", "")
	if code != http.StatusOK || body["detail_rate_limit_enabled"] != true ||
		body["detail_refresh_window_seconds"].(float64) != 86400 {
		t.Fatalf("default settings = %d %+v", code, body)
	}
	code, body = reqJSON(t, "PUT", srv.URL+"/strata/settings", `{"detail_rate_limit_enabled":false}`)
	if code != http.StatusOK || body["detail_rate_limit_enabled"] != false {
		t.Fatalf("disable = %d %+v", code, body)
	}
	// missing field is rejected
	code, _ = reqJSON(t, "PUT", srv.URL+"/strata/settings", `{}`)
	if code != http.StatusBadRequest {
		t.Fatalf("empty settings body = %d, want 400", code)
	}
}

func TestWatchlistEndpoints(t *testing.T) {
	srv, _ := newTestServer(t)
	code, body := reqJSON(t, "GET", srv.URL+"/strata/watchlist", "")
	if code != http.StatusOK || body["meta"].(map[string]any)["pool"] != "user" ||
		len(body["items"].([]any)) != 0 {
		t.Fatalf("empty watchlist = %d %+v", code, body)
	}
	code, body = reqJSON(t, "POST", srv.URL+"/strata/watchlist/1005", "")
	if code != http.StatusOK || body["meta"].(map[string]any)["added"] != true {
		t.Fatalf("watch add = %d %+v", code, body)
	}
	code, body = reqJSON(t, "GET", srv.URL+"/strata/watchlist", "")
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 1005 {
		t.Fatalf("watchlist = %+v", items)
	}
	code, body = reqJSON(t, "DELETE", srv.URL+"/strata/watchlist/1005", "")
	if code != http.StatusOK || body["meta"].(map[string]any)["removed"] != true {
		t.Fatalf("watch remove = %d %+v", code, body)
	}
	code, body = reqJSON(t, "GET", srv.URL+"/strata/watchlist", "")
	if len(body["items"].([]any)) != 0 {
		t.Fatalf("watchlist after remove = %+v", body)
	}
}

// TestRefreshCooldownBlocked: a book refreshed within the last 24h must be
// refused BEFORE any network I/O — the test seeds a fresh attempt and
// expects the ready-made rate_limited envelope (HTTP 200 by design: the
// client renders it as "refreshed, try again later", not an error).
func TestRefreshCooldownBlocked(t *testing.T) {
	srv, st := newTestServer(t)
	if err := st.RecordRefreshAttempt(context.Background(), 1001, time.Now().Unix(), "ok"); err != nil {
		t.Fatal(err)
	}
	code, body := reqJSON(t, "POST", srv.URL+"/strata/books/1001/refresh", "")
	if code != http.StatusOK {
		t.Fatalf("blocked refresh = %d, want 200", code)
	}
	if body["state"] != "rate_limited" || body["written"] != false ||
		body["rate_limit_enabled"] != true {
		t.Fatalf("blocked envelope = %+v", body)
	}
	after := body["retry_after_seconds"].(float64)
	if after <= 0 || after > 86400 {
		t.Fatalf("retry_after_seconds = %v, want (0, 86400]", after)
	}
}

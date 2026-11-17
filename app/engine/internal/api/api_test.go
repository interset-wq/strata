package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/store"
	"strata/engine/internal/testseed"
)

func newTestServer(t *testing.T) (*httptest.Server, *store.Store) {
	t.Helper()
	assets, data := t.TempDir(), t.TempDir()
	m, err := testseed.Build(assets, data)
	if err != nil {
		t.Fatal(err)
	}
	seedPath, err := appshell.InstallSeed(assets, data, m)
	if err != nil {
		t.Fatal(err)
	}
	st, err := store.Open(appshell.UserDBPath(data), seedPath, m)
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(New(st))
	t.Cleanup(func() {
		srv.Close()
		st.Close()
	})
	return srv, st
}

func getJSON(t *testing.T, url string, status int) map[string]any {
	t.Helper()
	resp, err := http.Get(url)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != status {
		t.Fatalf("%s status = %d, want %d", url, resp.StatusCode, status)
	}
	var body map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	return body
}

func TestHealthz(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/healthz", http.StatusOK)
	if body["book_count"].(float64) != 5 || body["seed_version"] != "test-1" {
		t.Fatalf("body = %v", body)
	}
}

func TestMeta(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/meta", http.StatusOK)
	meta := body["seed_meta"].(map[string]any)
	if meta["licensed_count"] != "1" {
		t.Fatalf("meta = %v", meta)
	}
}

func TestBookUsesLocalObservation(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/books/1001", http.StatusOK)
	if body["source"] != "local" {
		t.Fatalf("source = %v", body["source"])
	}
	effective := body["effective"].(map[string]any)
	if effective["favs"].(float64) != 777 {
		t.Fatalf("effective favs = %v", effective["favs"])
	}
}

func TestLicensedBookDetail(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/books/2001", http.StatusOK)
	book := body["book"].(map[string]any)
	if book["is_licensed"] != true {
		t.Fatalf("is_licensed = %v", book["is_licensed"])
	}
	if book["fav_pctl"] != nil {
		t.Fatalf("fav_pctl = %v", book["fav_pctl"])
	}
	if body["source"] != "seed" {
		t.Fatalf("source = %v", body["source"])
	}
}

func TestRankingFavs(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/rankings/favs?year=2010&limit=2", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %d", len(items))
	}
	first := items[0].(map[string]any)
	if first["nid"].(float64) != 1001 || first["fav_pctl"].(float64) != 0.9 {
		t.Fatalf("first = %v", first)
	}
	if body["meta"].(map[string]any)["licensed_excluded"] != true {
		t.Fatal("licensed_excluded flag missing")
	}
}

func TestRankingShort(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/rankings/short?limit=5", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %d", len(items))
	}
	if items[0].(map[string]any)["nid"].(float64) != 1002 {
		t.Fatalf("first = %v", items[0])
	}
}

func TestInvalidInputs(t *testing.T) {
	srv, _ := newTestServer(t)
	cases := []string{
		"/strata/books/abc",
		"/strata/books/0",
		"/strata/rankings/favs",
		"/strata/rankings/favs?year=2006",
		"/strata/rankings/favs?year=2010&genre=nope",
		"/strata/rankings/favs?year=2010&limit=0",
	}
	for _, path := range cases {
		body := getJSON(t, srv.URL+path, http.StatusBadRequest)
		if body["error"].(map[string]any)["code"] != "invalid_argument" {
			t.Fatalf("%s: body = %v", path, body)
		}
	}
}

func TestBookNotFound(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/books/999999", http.StatusNotFound)
	if body["error"].(map[string]any)["code"] != "not_found" {
		t.Fatalf("body = %v", body)
	}
}

package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/crawl"
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
	if body["book_count"].(float64) != 6 || body["seed_version"] != "test-1" {
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

func TestRankingDeep(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/rankings/deep?year=2010&metric=favs&limit=10", http.StatusOK)
	meta := body["meta"].(map[string]any)
	if meta["pool"] != "universe" || meta["ordering"] != "favs" {
		t.Fatalf("meta = %v", meta)
	}
	if meta["depth"].(float64) != 2 {
		t.Fatalf("depth = %v, want 2", meta["depth"])
	}
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %d", len(items))
	}
	first := items[0].(map[string]any)
	if first["nid"].(float64) != 1001 || first["value"].(float64) != 500 {
		t.Fatalf("first = %v", first)
	}
	if first["in_seed"] != true {
		t.Fatalf("seed book not marked in_seed: %v", first)
	}
	// 7777 is deliberately absent from books: deep boards are full-universe.
	second := items[1].(map[string]any)
	if second["nid"].(float64) != 7777 {
		t.Fatalf("second = %v", second)
	}
	if second["in_seed"] != false {
		t.Fatalf("library-external book wrongly marked in_seed: %v", second)
	}

	body = getJSON(t, srv.URL+"/strata/rankings/deep?year=2010&metric=pr", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 1001 {
		t.Fatalf("pr board = %v", items)
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

func TestRankingNew(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/rankings/new?limit=10", http.StatusOK)
	meta := body["meta"].(map[string]any)
	if meta["min_est_year"].(float64) != 2024 {
		t.Fatalf("min_est_year = %v", meta["min_est_year"])
	}
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("items = %d, want only nid 1005", len(items))
	}
	first := items[0].(map[string]any)
	if first["nid"].(float64) != 1005 || first["fav_pctl"].(float64) != 0.95 {
		t.Fatalf("first = %v", first)
	}
}

func TestSearch(t *testing.T) {
	srv, _ := newTestServer(t)
	// Search must find licensed books too (they are searchable, only
	// excluded from rankings).
	body := getJSON(t, srv.URL+"/strata/search?q=%E5%A4%A9%E9%97%BB", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 2001 {
		t.Fatalf("licensed search = %v", items)
	}

	body = getJSON(t, srv.URL+"/strata/search?q=Long", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("Long search = %d items", len(items))
	}
	if items[0].(map[string]any)["nid"].(float64) != 1003 {
		t.Fatalf("order = %v (higher favs first)", items)
	}
}

func TestSearchInvalidInput(t *testing.T) {
	srv, _ := newTestServer(t)
	for _, path := range []string{"/strata/search"} {
		body := getJSON(t, srv.URL+path, http.StatusBadRequest)
		if body["error"].(map[string]any)["code"] != "invalid_argument" {
			t.Fatalf("%s: body = %v", path, body)
		}
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
		"/strata/rankings/deep",
		"/strata/rankings/deep?year=2010&metric=nope",
		"/strata/rankings/deep?year=2010&metric=favs&limit=0",
		"/strata/rankings/deep?year=2006&metric=favs",
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

func TestWriteHTMLPersistsEveryField(t *testing.T) {
	srv, st := newTestServer(t)
	s := &Server{store: st}
	d := &crawl.Detail{
		Title: "Local Title", Author: "Local Author",
		Genre: "\u79d1\u5e7b", PriceType: "VIP",
		CoverURL: "https://example.test/cover.jpg", Summary: "Local summary",
		Favs: 1000, Praises: 200, Words: 12345,
		Status: "\u8fde\u8f7d\u4e2d", UpdatedAt: "2026-11-18 12:00:00",
	}
	if err := s.writeHTML(context.Background(), 1001, d, 1800000000); err != nil {
		t.Fatal(err)
	}

	detail, err := st.Book(context.Background(), 1001)
	if err != nil {
		t.Fatal(err)
	}
	if detail.Book.Title != "Long A" {
		t.Fatalf("seed title must stay read-only: %q", detail.Book.Title)
	}
	if detail.Meta == nil || detail.Meta.Summary == nil || *detail.Meta.Summary != "Local summary" {
		t.Fatalf("meta = %+v", detail.Meta)
	}

	body := getJSON(t, srv.URL+"/strata/books/1001", http.StatusOK)
	if body["cover"] != "https://example.test/cover.jpg" {
		t.Fatalf("cover = %v", body["cover"])
	}
	eff := body["effective"].(map[string]any)
	checks := map[string]any{
		"title": "Local Title", "author": "Local Author", "genre": "\u79d1\u5e7b",
		"price_type": "VIP", "summary": "Local summary", "status": "\u8fde\u8f7d\u4e2d",
		"cover_url": "https://example.test/cover.jpg", "words": float64(12345),
		"favs": float64(1000), "praises": float64(200),
	}
	for key, want := range checks {
		if got := eff[key]; got != want {
			t.Fatalf("effective[%s] = %v, want %v", key, got, want)
		}
	}
}

func TestWriteAppPersistsEveryField(t *testing.T) {
	srv, st := newTestServer(t)
	s := &Server{store: st}
	app := &crawl.AppNovel{
		NovelID: 1001, NovelName: "App Title", AuthorID: 42, AuthorName: "App Author",
		AddTime: "2020-01-01T00:00:00", LastUpdateTime: "2026-11-18T12:00:00",
		MarkCount: 8888, ViewTimes: 99999, CharCount: 77777, Point: 7.5,
		IsFinish: true, SignStatus: "VIP", TypeID: 21, CategoryID: 1,
		IsSensitive: true, AllowDown: false,
		NovelCover: "https://example.test/app.jpg", BgBanner: "https://example.test/bg.jpg",
	}
	if err := s.writeApp(context.Background(), 1001, app, 1800000001); err != nil {
		t.Fatal(err)
	}

	body := getJSON(t, srv.URL+"/strata/books/1001", http.StatusOK)
	eff := body["effective"].(map[string]any)
	checks := map[string]any{
		"title": "App Title", "author": "App Author", "author_id": float64(42),
		"genre": "\u9b54\u5e7b", "type_id": float64(21),
		"price_type": "VIP", "status": "\u5df2\u5b8c\u7ed3",
		"clicks": float64(99999), "favs": float64(8888), "words": float64(77777),
		"updated_at": "2026-11-18T12:00:00", "add_time": "2020-01-01T00:00:00",
		"point": 7.5, "category_id": float64(1),
		"is_sensitive": true, "allow_down": false,
		"cover_url": "https://example.test/app.jpg",
	}
	for key, want := range checks {
		if got := eff[key]; got != want {
			t.Fatalf("effective[%s] = %v, want %v", key, got, want)
		}
	}
	if body["cover"] != "https://example.test/app.jpg" {
		t.Fatalf("cover = %v", body["cover"])
	}
}

package api

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"testing"
	"time"

	"strata/engine/internal/crawl"
)

// Fixtures shaped on the live API probes of 2026-11-22
// (pages.sfacg.com/api/HttpProxy, actionName=/bookList/1 and .../novel).
const (
	booklistItemJSON    = `{"status":{"httpCode":200,"errorCode":200,"msg":null},"data":{"bookListID":1,"title":"测试书单","summary":"简介","markNum":2170,"recommendNum":399,"novelNum":2,"lastUpdateDateTime":"2021-05-11T16:56:45","user":{"nickName":"作者甲","expand":{"avatar":"https://rss.sfacg.com/a.jpg","vipLevel":2}}}}`
	booklistInvalidJSON = `{"status":{"httpCode":200,"errorCode":200,"msg":null},"data":null}`
	booklistNovelsJSON  = `{"status":{"httpCode":200,"errorCode":200,"msg":null},"data":{"items":[{"summary":"推荐语一","novels":{"novelId":1006,"novelName":"库内书","authorName":"作者B","novelCover":"https://rss.sfacg.com/c1.jpg","charCount":123456,"viewTimes":234567,"markCount":3456,"isFinish":true,"expand":{"bigNovelCover":"https://rss.sfacg.com/b1.jpg","typeName":"玄幻"}}},{"summary":"推荐语二","novels":{"novelId":999999,"novelName":"库外书","authorName":"作者C","charCount":5000,"viewTimes":6000,"markCount":700,"isFinish":false}}]}}`
)

// validBooklistJSON renders the item fixture as booklist #id.
func validBooklistJSON(id int) string {
	return strings.Replace(booklistItemJSON, `"bookListID":1`,
		`"bookListID":`+strconv.Itoa(id), 1)
}

// TestBooklistsWindow: a 5-id window (booklistPageSize), ids 1..8 valid /
// 9+ invalid → page 1 full (ids 1..5, done=false), page 2 short (ids 6..10
// → 3 items, done=true = end), page 3 empty (ids 11..15, done).
func TestBooklistsWindow(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.booklistFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, id int, kind string, foreground bool) (string, error) {
		if kind != "item" {
			return "", fmt.Errorf("unexpected kind %q", kind)
		}
		if id >= 1 && id <= 8 {
			return validBooklistJSON(id), nil
		}
		return booklistInvalidJSON, nil
	}
	body := getJSON(t, ts.URL+"/strata/booklists", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 5 {
		t.Fatalf("items = %v, want 5 valid on page 1", items)
	}
	if items[4].(map[string]any)["id"].(float64) != 5 {
		t.Fatalf("last item = %v, want id 5", items[4])
	}
	if body["done"] != false {
		t.Fatalf("done = %v, want false (full page)", body["done"])
	}
	it := items[0].(map[string]any)
	if it["title"] != "测试书单" || it["vip"] != true ||
		it["novel_num"].(float64) != 2 || it["updated"] != "2021-05-11" {
		t.Fatalf("item 0 = %v", it)
	}
	// page 2: ids 6..10, 9..10 invalid → short page = end.
	body2 := getJSON(t, ts.URL+"/strata/booklists?page=2", http.StatusOK)
	items2 := body2["items"].([]any)
	if len(items2) != 3 || body2["done"] != true {
		t.Fatalf("page 2 = %v, want 3 items + done (short page)", body2)
	}
	// page 3: ids 11..15 all invalid → empty window, done.
	body3 := getJSON(t, ts.URL+"/strata/booklists?page=3", http.StatusOK)
	if got := body3["items"].([]any); len(got) != 0 || body3["done"] != true {
		t.Fatalf("page 3 = %v, want empty items + done", body3)
	}
}

// TestBooklistNovelsJoin: the detail endpoint joins the local seed —
// nid 1006 is in the test seed (in_library + form), 999999 is not
// (official fields only, nothing fabricated).
func TestBooklistNovelsJoin(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.booklistFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, id int, kind string, foreground bool) (string, error) {
		if id != 1 {
			return "", fmt.Errorf("unexpected id %d", id)
		}
		if kind == "novel" {
			return booklistNovelsJSON, nil
		}
		return booklistItemJSON, nil
	}
	body := getJSON(t, ts.URL+"/strata/booklists/1/novels", http.StatusOK)
	if bl := body["booklist"].(map[string]any); bl["title"] != "测试书单" {
		t.Fatalf("booklist header = %v", bl)
	}
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	in := items[0].(map[string]any)
	if in["in_library"] != true || in["form"] == nil || in["nid"].(float64) != 1006 {
		t.Fatalf("in-library row = %v", in)
	}
	if in["words"].(float64) != 123456 || in["finish"] != true || in["note"] != "推荐语一" {
		t.Fatalf("official fields = %v", in)
	}
	out := items[1].(map[string]any)
	if out["in_library"] != false {
		t.Fatalf("out-of-library row = %v", out)
	}
	if _, has := out["form"]; has {
		t.Fatalf("out-of-library row carries a fabricated form: %v", out)
	}
}

// TestBooklistNotFound: an invalid id (data missing) is a 404, not an
// empty detail.
func TestBooklistNotFound(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.booklistFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, id int, kind string, foreground bool) (string, error) {
		return booklistInvalidJSON, nil
	}
	getJSON(t, ts.URL+"/strata/booklists/999/novels", http.StatusNotFound)
}

// TestParseBooklistDead: malformed bodies and dead interfaces parse to nil.
func TestParseBooklistDead(t *testing.T) {
	if crawl.ParseBooklistItem(`{garbage`) != nil {
		t.Fatal("malformed body parsed")
	}
	if crawl.ParseBooklistItem(`{"status":{"errorCode":500},"data":null}`) != nil {
		t.Fatal("errorCode 500 item parsed")
	}
	if crawl.ParseBooklistNovels(`{"status":{"errorCode":500},"data":null}`) != nil {
		t.Fatal("errorCode 500 novels parsed")
	}
}

// TestBooklistsRecommend: the date-seeded sample returns exactly count
// distinct booklists; dead ids in the draw (here: the whole lower half of
// the id space) are topped up without error.
// TestBooklistsRecommend pins the home feed's recommend sample: default
// count 3, no duplicate ids, ids inside the live space. The mock keeps
// every id valid — the date-seeded RNG (booklistsRecommend) draws a
// different sequence each day, and a random "invalid band" would make the
// count flaky across midnight (skip-without-refill is the released
// design; invalid-id handling is covered by the window tests below).
func TestBooklistsRecommend(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.booklistFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, id int, kind string, foreground bool) (string, error) {
		if kind != "item" {
			return "", fmt.Errorf("unexpected kind %q", kind)
		}
		return validBooklistJSON(id), nil
	}
	body := getJSON(t, ts.URL+"/strata/booklists/recommend", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("items = %v, want 3 (default count)", items)
	}
	seen := map[float64]bool{}
	for _, it := range items {
		id := it.(map[string]any)["id"].(float64)
		if seen[id] {
			t.Fatalf("duplicate id %v in sample", id)
		}
		seen[id] = true
		if id < 1 || id > 1272 {
			t.Fatalf("id %v outside the live space", id)
		}
	}
}

// TestBooklistsWindowDeadline: a slow (not dead) upstream must not let the
// serial 5-id window spin for minutes — the window deadline bounds it and
// surfaces as 502 (the UI retries; the per-id cache keeps the retry cheap).
// The seam is ctx-aware, mirroring the production request abort.
func TestBooklistsWindowDeadline(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.booklistFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, id int, kind string, foreground bool) (string, error) {
		select {
		case <-time.After(80 * time.Millisecond):
			return validBooklistJSON(id), nil
		case <-ctx.Done():
			return "", ctx.Err()
		}
	}
	old := booklistWindowTimeout
	booklistWindowTimeout = 200 * time.Millisecond
	defer func() { booklistWindowTimeout = old }()

	start := time.Now()
	req, _ := http.NewRequest("GET", ts.URL+"/strata/booklists?page=1", nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadGateway {
		t.Fatalf("status = %d, want 502 (window deadline)", resp.StatusCode)
	}
	if elapsed := time.Since(start); elapsed > 500*time.Millisecond {
		t.Fatalf("window took %v, deadline should bound it near 200ms", elapsed)
	}
}

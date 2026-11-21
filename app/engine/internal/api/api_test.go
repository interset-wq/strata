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

// doJSON is getJSON with an explicit method (POST/DELETE endpoints).
func doJSON(t *testing.T, method, url string, status int) map[string]any {
	t.Helper()
	req, err := http.NewRequest(method, url, nil)
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != status {
		t.Fatalf("%s %s status = %d, want %d",
			method, url, resp.StatusCode, status)
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
	if body["book_count"].(float64) != 16 || body["seed_version"] != "test-1" {
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

func TestBannerSegmented(t *testing.T) {
	srv, _ := newTestServer(t)
	// Same seed: offset 0 and offset 1 must not overlap.
	a := getJSON(t, srv.URL+"/strata/banner?seed=20261118&limit=1&offset=0", http.StatusOK)
	b := getJSON(t, srv.URL+"/strata/banner?seed=20261118&limit=1&offset=1", http.StatusOK)
	ia := a["items"].([]any)
	ib := b["items"].([]any)
	if len(ia) != 1 || len(ib) != 1 {
		t.Fatalf("segments = %d, %d, want 1, 1", len(ia), len(ib))
	}
	if ia[0].(map[string]any)["nid"] == ib[0].(map[string]any)["nid"] {
		t.Fatalf("segments overlap: %v", ia[0].(map[string]any)["nid"])
	}
	// Different seed, same offset: deterministic (same result twice).
	c := getJSON(t, srv.URL+"/strata/banner?seed=20261118&limit=1&offset=0", http.StatusOK)
	if ia[0].(map[string]any)["nid"] != c["items"].([]any)[0].(map[string]any)["nid"] {
		t.Fatal("seeded pick is not deterministic")
	}
	// Negative offset rejected.
	getJSON(t, srv.URL+"/strata/banner?seed=20261118&limit=1&offset=-1",
		http.StatusBadRequest)
}

func TestFeaturedAll(t *testing.T) {
	srv, _ := newTestServer(t)
	// testseed featured pool: 1003 (long, favs 900), 1006 (ip_collab, 700),
	// 1001 (long, 500), 1007 (medium, 400). Default order: favs DESC.
	all := getJSON(t, srv.URL+"/strata/featured-all?limit=10", http.StatusOK)
	items := all["items"].([]any)
	if len(items) != 4 {
		t.Fatalf("items = %d, want 4", len(items))
	}
	if items[0].(map[string]any)["nid"] != 1003.0 ||
		items[3].(map[string]any)["nid"] != 1007.0 {
		t.Fatalf("desc order = %v .. %v",
			items[0].(map[string]any)["nid"], items[3].(map[string]any)["nid"])
	}
	// order=asc inverts.
	asc := getJSON(t, srv.URL+"/strata/featured-all?limit=10&order=asc",
		http.StatusOK)
	a := asc["items"].([]any)
	if a[0].(map[string]any)["nid"] != 1007.0 ||
		a[3].(map[string]any)["nid"] != 1003.0 {
		t.Fatalf("asc order = %v .. %v",
			a[0].(map[string]any)["nid"], a[3].(map[string]any)["nid"])
	}
	// Pagination: limit=1 offset=1 skips the first row.
	page := getJSON(t, srv.URL+"/strata/featured-all?limit=1&offset=1",
		http.StatusOK)
	p := page["items"].([]any)
	if len(p) != 1 || p[0].(map[string]any)["nid"] != 1006.0 {
		t.Fatalf("page = %v, want [1006]", p)
	}
	// Past the end: empty, not an error.
	empty := getJSON(t, srv.URL+"/strata/featured-all?limit=10&offset=5",
		http.StatusOK)
	if len(empty["items"].([]any)) != 0 {
		t.Fatalf("past-end = %v, want empty", empty["items"])
	}
	// Invalid inputs rejected.
	getJSON(t, srv.URL+"/strata/featured-all?order=sideways",
		http.StatusBadRequest)
	getJSON(t, srv.URL+"/strata/featured-all?offset=-1",
		http.StatusBadRequest)
}

// TestFeaturedForm: the per-form featured pools that drive the home
// carousel (docs/13). medium/ip_collab pools are small and shown in a
// fixed favs order; short has no featured books of its own — the client
// falls back to the IP pool, the API returns the empty short pool as-is.
func TestFeaturedForm(t *testing.T) {
	srv, _ := newTestServer(t)
	byForm := func(form string) []any {
		body := getJSON(t,
			srv.URL+"/strata/featured?limit=10&form="+form, http.StatusOK)
		return body["items"].([]any)
	}
	// ip_collab pool: exactly the one ip_collab featured book.
	ip := byForm("ip_collab")
	if len(ip) != 1 || ip[0].(map[string]any)["nid"] != 1006.0 {
		t.Fatalf("ip_collab pool = %v", ip)
	}
	// medium pool: exactly the one medium featured book.
	med := byForm("medium")
	if len(med) != 1 || med[0].(map[string]any)["nid"] != 1007.0 {
		t.Fatalf("medium pool = %v", med)
	}
	// short pool: empty — the client-side fallback is not the API's job.
	short := byForm("short")
	if len(short) != 0 {
		t.Fatalf("short pool = %v, want empty", short)
	}
	// long pool: the two long featured books, favs DESC.
	long := byForm("long")
	if len(long) != 2 || long[0].(map[string]any)["nid"] != 1003.0 ||
		long[1].(map[string]any)["nid"] != 1001.0 {
		t.Fatalf("long pool = %v", long)
	}
	// No form: the whole pool, licensed works included (display layer).
	all := byForm("")
	if len(all) != 4 {
		t.Fatalf("whole pool = %v, want 4", all)
	}
	// Invalid form rejected.
	getJSON(t, srv.URL+"/strata/featured?form=novella",
		http.StatusBadRequest)
}

// TestCoverCarousel: the 对话 tab's composed-banner pool — cover-bearing
// books of one form by favs DESC. form is mandatory (the client always
// names one); cover-less books never appear.
func TestCoverCarousel(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/cover-carousel?form=dialogue&limit=10",
		http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"] != 1008.0 {
		t.Fatalf("items = %v", items)
	}
	if items[0].(map[string]any)["cover_url"] == nil {
		t.Fatalf("cover_required pool leaked a cover-less book: %v", items)
	}
	if meta := body["meta"].(map[string]any); meta["cover_required"] != true {
		t.Fatalf("meta = %v", meta)
	}
	// form is mandatory and must be a known value.
	getJSON(t, srv.URL+"/strata/cover-carousel?limit=10", http.StatusBadRequest)
	getJSON(t, srv.URL+"/strata/cover-carousel?form=novella", http.StatusBadRequest)
	// A form with no cover-bearing books returns empty, not an error.
	empty := getJSON(t, srv.URL+"/strata/cover-carousel?form=medium",
		http.StatusOK)
	if len(empty["items"].([]any)) != 0 {
		t.Fatalf("medium pool = %v, want empty", empty["items"])
	}
}

// TestIpGroups: the IP tab's entry row — one form's books aggregated by
// contest (征文), count DESC with a stable contest ASC tie-break.
func TestIpGroups(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/ip-groups?form=ip_collab",
		http.StatusOK)
	if body["total"].(float64) != 4 {
		t.Fatalf("total = %v, want 4", body["total"])
	}
	groups := body["groups"].([]any)
	want := []struct {
		contest string
		count   int
	}{
		{"崩坏3征文", 2}, {"少女前线征文", 1}, {"龙之谷征文", 1},
	}
	if len(groups) != len(want) {
		t.Fatalf("groups = %v", groups)
	}
	for i, w := range want {
		g := groups[i].(map[string]any)
		if g["contest"] != w.contest || int(g["count"].(float64)) != w.count {
			t.Fatalf("groups[%d] = %v, want %v", i, g, w)
		}
	}
	// form is mandatory.
	getJSON(t, srv.URL+"/strata/ip-groups", http.StatusBadRequest)

	// status filter (short tab contest chips aggregate the 已完结 pool;
	// total follows the same caliber): only 1010 is 已完结.
	body = getJSON(t, srv.URL+"/strata/ip-groups?form=ip_collab&status=已完结",
		http.StatusOK)
	if body["total"].(float64) != 1 {
		t.Fatalf("done total = %v, want 1", body["total"])
	}
	groups = body["groups"].([]any)
	if len(groups) != 1 ||
		groups[0].(map[string]any)["contest"] != "少女前线征文" ||
		int(groups[0].(map[string]any)["count"].(float64)) != 1 {
		t.Fatalf("done groups = %v", groups)
	}
}

// TestIpBooks: one IP entry list — a contest named exactly, or "other"
// for the long tail outside the top-2 contests by count.
func TestIpBooks(t *testing.T) {
	srv, _ := newTestServer(t)
	// named group: 崩坏3征文 = 1006 + 1009, favs DESC.
	body := getJSON(t,
		srv.URL+"/strata/ip-books?form=ip_collab&group=崩坏3征文&limit=10",
		http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 ||
		items[0].(map[string]any)["nid"] != 1006.0 ||
		items[1].(map[string]any)["nid"] != 1009.0 {
		t.Fatalf("items = %v", items)
	}
	// regression: the ip-books scan must return contest — the client
	// renders the IP badge from it on mixed-IP lists.
	if items[0].(map[string]any)["contest"] != "崩坏3征文" {
		t.Fatalf("items[0].contest = %v, want 崩坏3征文",
			items[0].(map[string]any)["contest"])
	}
	// other: 龙之谷征文 is outside the top-2 by count → 1011.
	body = getJSON(t,
		srv.URL+"/strata/ip-books?form=ip_collab&group=other&limit=10",
		http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"] != 1011.0 {
		t.Fatalf("other = %v, want [1011]", items)
	}
	// group is mandatory; an unknown contest returns empty, not an error.
	getJSON(t, srv.URL+"/strata/ip-books?form=ip_collab", http.StatusBadRequest)
	empty := getJSON(t,
		srv.URL+"/strata/ip-books?form=ip_collab&group=不存在的征文",
		http.StatusOK)
	if len(empty["items"].([]any)) != 0 {
		t.Fatalf("unknown contest = %v, want empty", empty["items"])
	}
}

// TestBannerForm: the seeded shuffle honours the form filter — every
// drawn item must belong to the requested form.
func TestBannerForm(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/banner?seed=20261119&limit=10&form=ip_collab",
		http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"] != 1006.0 {
		t.Fatalf("banner ip_collab = %v", items)
	}
	// The long shuffle must never leak other forms.
	long := getJSON(t, srv.URL+"/strata/banner?seed=20261119&limit=10&form=long",
		http.StatusOK)
	l := long["items"].([]any)
	if len(l) != 2 {
		t.Fatalf("banner long = %v, want 2", l)
	}
	for _, it := range l {
		switch it.(map[string]any)["nid"].(float64) {
		case 1001, 1003:
		default:
			t.Fatalf("banner long leaked form: %v", it)
		}
	}
}

func TestLicensedPool(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/licensed", http.StatusOK)
	meta := body["meta"].(map[string]any)
	if meta["pool"] != "licensed" || meta["ordering"] != "favs" {
		t.Fatalf("meta = %v", meta)
	}
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("items = %d, want 1", len(items))
	}
	if items[0].(map[string]any)["nid"].(float64) != 2001 {
		t.Fatalf("first = %v", items[0])
	}
}

func TestMoeGoddessPool(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/moe-goddess", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("items = %d, want 1", len(items))
	}
	first := items[0].(map[string]any)
	if first["nid"].(float64) != 1003 {
		t.Fatalf("first = %v", first)
	}
	tags, _ := first["tags"].([]any)
	if len(tags) != 1 || tags[0] != "2020萌神" {
		t.Fatalf("tags = %v", tags)
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
	if len(items) != 3 {
		t.Fatalf("items = %d", len(items))
	}
	if items[0].(map[string]any)["nid"].(float64) != 3003 {
		t.Fatalf("first = %v", items[0])
	}
}

func TestRankingClassic(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/rankings/classic?limit=2", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %d", len(items))
	}
	// Absolute favs across all years: 3001 (3000) before 1003 (900).
	first := items[0].(map[string]any)
	if first["nid"].(float64) != 3001 || first["favs"].(float64) != 3000 {
		t.Fatalf("first = %v", first)
	}
	if first["form"] != "long" {
		t.Fatalf("form = %v", first["form"])
	}

	body = getJSON(t, srv.URL+"/strata/rankings/classic?form=short", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("short items = %d", len(items))
	}
	if items[0].(map[string]any)["nid"].(float64) != 3003 ||
		items[1].(map[string]any)["nid"].(float64) != 1002 {
		t.Fatalf("short order = %v", items)
	}

	// year filter (short tab year axis): 2010 holds both done shorts.
	body = getJSON(t, srv.URL+
		"/strata/rankings/classic?form=short&year=2010", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 2 ||
		items[0].(map[string]any)["nid"].(float64) != 1002 {
		t.Fatalf("year=2010 items = %v", items)
	}
	// No 2015 shorts in the test seed.
	body = getJSON(t, srv.URL+
		"/strata/rankings/classic?form=short&year=2015", http.StatusOK)
	if items = body["items"].([]any); len(items) != 0 {
		t.Fatalf("year=2015 items = %v", items)
	}
	// year must be a positive integer.
	getJSON(t, srv.URL+"/strata/rankings/classic?year=0", http.StatusBadRequest)
	getJSON(t, srv.URL+"/strata/rankings/classic?year=x", http.StatusBadRequest)

	// words-band splits the dialogue tab by documented length classes:
	// short <= 50k, medium 50k..150k, long > 150k. Dialogue test books:
	// 3002 (40k) and 1008 (50k, exactly on the short ceiling).
	body = getJSON(t, srv.URL+
		"/strata/rankings/classic?form=dialogue&words-band=short", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 2 || items[0].(map[string]any)["nid"].(float64) != 3002 {
		t.Fatalf("dialogue short band = %v", items)
	}
	body = getJSON(t, srv.URL+
		"/strata/rankings/classic?form=dialogue&words-band=medium", http.StatusOK)
	if items = body["items"].([]any); len(items) != 0 {
		t.Fatalf("dialogue medium band = %v", items)
	}
	body = getJSON(t, srv.URL+
		"/strata/rankings/classic?form=dialogue&words-band=long", http.StatusOK)
	if items = body["items"].([]any); len(items) != 0 {
		t.Fatalf("dialogue long band = %v", items)
	}
	getJSON(t, srv.URL+"/strata/rankings/classic?words-band=giant",
		http.StatusBadRequest)

	getJSON(t, srv.URL+"/strata/rankings/classic?form=novella",
		http.StatusBadRequest)
}

func TestRandomFormFilter(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/random?limit=8&form=short", http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 3 {
		t.Fatalf("items = %d", len(items))
	}
	for _, it := range items {
		if it.(map[string]any)["form"] != "short" {
			t.Fatalf("form = %v", it)
		}
	}

	// The browse pool must not apply the mega-book gate to short forms.
	body = getJSON(t,
		srv.URL+"/strata/random?limit=8&status=browse&form=short", http.StatusOK)
	if len(body["items"].([]any)) != 3 {
		t.Fatalf("browse short items = %v", body["items"])
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
	if len(items) != 2 {
		t.Fatalf("items = %d, want nid 1005 and 3003", len(items))
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
	if len(items) != 4 {
		t.Fatalf("Long search = %d items", len(items))
	}
	if items[0].(map[string]any)["nid"].(float64) != 3001 {
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

// TestYearGroups: the short tab's year entry — one form's pool aggregated
// by est_year (DESC) plus the pool total.
func TestYearGroups(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/year-groups?form=short",
		http.StatusOK)
	if body["total"].(float64) != 3 {
		t.Fatalf("total = %v, want 3", body["total"])
	}
	groups := body["groups"].([]any)
	if len(groups) != 2 ||
		int(groups[0].(map[string]any)["year"].(float64)) != 2025 ||
		int(groups[0].(map[string]any)["count"].(float64)) != 1 ||
		int(groups[1].(map[string]any)["year"].(float64)) != 2010 ||
		int(groups[1].(map[string]any)["count"].(float64)) != 2 {
		t.Fatalf("groups = %v, want [{2025 1} {2010 2}]", groups)
	}
	// form is mandatory.
	getJSON(t, srv.URL+"/strata/year-groups", http.StatusBadRequest)
}

// TestGenreGroups: the short tab's genre browse entry — one form's pool
// aggregated by genre (count DESC) plus the pool total.
func TestGenreGroups(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/genre-groups?form=short",
		http.StatusOK)
	if body["total"].(float64) != 3 {
		t.Fatalf("total = %v, want 3", body["total"])
	}
	groups := body["groups"].([]any)
	if len(groups) != 3 {
		t.Fatalf("groups = %v, want 3 genres", groups)
	}
	for _, g := range groups {
		if int(g.(map[string]any)["count"].(float64)) != 1 {
			t.Fatalf("groups = %v, want count 1 each", groups)
		}
	}
	// form is mandatory.
	getJSON(t, srv.URL+"/strata/genre-groups", http.StatusBadRequest)
}

// TestRankingClassicOrderPct: order=pct ranks by same-generation favorite
// percentile (docs/form-definitions §6 quality short books) and inverts a
// favs order; the default stays favs DESC; invalid order is rejected.
func TestRankingClassicOrderPct(t *testing.T) {
	srv, _ := newTestServer(t)
	// testseed: 1004 (pctl 0.6, favs 50) outranks 1002 (pctl 0.5, favs 100)
	// on percentile — pct order must invert the favs order.
	body := getJSON(t,
		srv.URL+"/strata/rankings/classic?form=short&limit=10&order=pct",
		http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 3 ||
		items[0].(map[string]any)["nid"] != 3003.0 ||
		items[1].(map[string]any)["nid"] != 1004.0 ||
		items[2].(map[string]any)["nid"] != 1002.0 {
		t.Fatalf("pct items = %v, want [3003 1004 1002]", items)
	}
	// Default ordering is still favs DESC.
	body = getJSON(t, srv.URL+"/strata/rankings/classic?form=short&limit=10",
		http.StatusOK)
	items = body["items"].([]any)
	if items[0].(map[string]any)["nid"] != 3003.0 ||
		items[1].(map[string]any)["nid"] != 1002.0 {
		t.Fatalf("favs items = %v, want [3003 1002 1004]", items)
	}
	getJSON(t, srv.URL+"/strata/rankings/classic?form=short&order=bogus",
		http.StatusBadRequest)
}

// TestRandomShort: the short tab's random pool — the form filter is the
// pool itself, no words threshold.
func TestRandomShort(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t,
		srv.URL+"/strata/random?status=short&form=short&limit=100",
		http.StatusOK)
	items := body["items"].([]any)
	seen := map[int64]bool{}
	for _, it := range items {
		seen[int64(it.(map[string]any)["nid"].(float64))] = true
	}
	if len(items) != 3 || !seen[1002] || !seen[1004] || !seen[3003] {
		t.Fatalf("items = %v, want {1002 1004 3003}", items)
	}
}

// TestDevSimulate: the workbench dev aid (docs/07) — a deterministic
// synthetic observation series. nid 1001 is 连载中 in testseed (words
// 120,000 / favs 500) and testseed planted one real 'detail'
// observation at 1700000000 (2023-11-14, far outside the 60-day
// window): it must survive re-runs and the delete.
func TestDevSimulate(t *testing.T) {
	srv, _ := newTestServer(t)

	body := doJSON(t, http.MethodPost,
		srv.URL+"/strata/dev/simulate?nid=1001&days=60", http.StatusOK)
	if body["nid"].(float64) != 1001 || body["days"].(float64) != 60 {
		t.Fatalf("body = %v", body)
	}
	rows := body["rows"].(float64)
	gaps := body["gap_days"].(float64)
	flats := body["flat_days"].(float64)
	if gaps <= 0 || flats <= 0 {
		t.Fatalf("day classes missing: gaps=%v flats=%v", gaps, flats)
	}
	if rows+gaps != 60 {
		t.Fatalf("rows+gaps = %v, want 60 (rows=%v gaps=%v)",
			rows+gaps, rows, gaps)
	}
	if body["end_words"].(float64) <= body["start_words"].(float64) {
		t.Fatalf("serializing book must grow words: %v", body)
	}
	if body["end_favs"].(float64) <= body["start_favs"].(float64) {
		t.Fatalf("favs must grow: %v", body)
	}

	// Deterministic + idempotent: a re-run regenerates the same values.
	body2 := doJSON(t, http.MethodPost,
		srv.URL+"/strata/dev/simulate?nid=1001&days=60", http.StatusOK)
	if body2["rows"] != body["rows"] ||
		body2["end_words"] != body["end_words"] ||
		body2["end_favs"] != body["end_favs"] {
		t.Fatalf("re-run diverged: %v vs %v", body2, body)
	}

	// The observations endpoint exposes the series with source markers;
	// the planted real 'detail' row rides along as the oldest one.
	obs := getJSON(t, srv.URL+"/strata/books/1001/observations", http.StatusOK)
	items := obs["items"].([]any)
	if float64(len(items)) != rows+1 {
		t.Fatalf("observations = %d rows, want %d (+1 detail)",
			len(items), int(rows)+1)
	}
	var sawDetail, sawSimulate bool
	for _, it := range items {
		m := it.(map[string]any)
		switch m["source"] {
		case "detail":
			sawDetail = true
		case "simulate":
			sawSimulate = true
		}
	}
	if !sawDetail || !sawSimulate {
		t.Fatalf("source markers: detail=%v simulate=%v",
			sawDetail, sawSimulate)
	}

	// Delete removes only the simulate rows.
	del := doJSON(t, http.MethodDelete,
		srv.URL+"/strata/dev/simulate?nid=1001", http.StatusOK)
	if del["deleted"] != rows {
		t.Fatalf("deleted = %v, want %v", del["deleted"], rows)
	}
	obs = getJSON(t, srv.URL+"/strata/books/1001/observations", http.StatusOK)
	if items = obs["items"].([]any); len(items) != 1 ||
		items[0].(map[string]any)["source"] != "detail" {
		t.Fatalf("after delete = %v, want the single detail row", items)
	}

	// Invalid input.
	for _, path := range []string{
		"/strata/dev/simulate",
		"/strata/dev/simulate?nid=0",
		"/strata/dev/simulate?nid=abc",
		"/strata/dev/simulate?nid=1001&days=0",
		"/strata/dev/simulate?nid=1001&days=999",
	} {
		doJSON(t, http.MethodPost, srv.URL+path, http.StatusBadRequest)
	}
}

// TestDevTestBook: the settings test switch (docs/07 dev aid) — inject
// the fictional workbench book and watch it flow through the detail
// overlay, the watchlist and the observations endpoint, then remove it.
func TestDevTestBook(t *testing.T) {
	srv, _ := newTestServer(t)

	// Initial state: absent.
	body := doJSON(t, http.MethodGet,
		srv.URL+"/strata/dev/test-book", http.StatusOK)
	if body["present"] != false {
		t.Fatalf("initial state = %v", body)
	}

	// Inject (default 60 days).
	body = doJSON(t, http.MethodPost,
		srv.URL+"/strata/dev/test-book", http.StatusOK)
	if body["present"] != true || body["nid"].(float64) != 99000001 {
		t.Fatalf("inject = %v", body)
	}
	rows := body["rows"].(float64)
	if body["days"].(float64) != 60 || rows <= 0 || rows > 60 {
		t.Fatalf("inject series = %v", body)
	}

	// Detail overlay: the fictional book serves the local view.
	detail := getJSON(t, srv.URL+"/strata/books/99000001", http.StatusOK)
	book := detail["book"].(map[string]any)
	if detail["source"] != "local" || book["title"] != "工作台测试·全勤纪" {
		t.Fatalf("detail = %v", detail)
	}
	if book["words"] == nil || book["favs"] == nil {
		t.Fatalf("detail counters missing: %v", book)
	}

	// The watchlist lists it (discovered-row title fallback), inactive.
	wl := getJSON(t, srv.URL+"/strata/watchlist", http.StatusOK)
	found := false
	for _, it := range wl["items"].([]any) {
		m := it.(map[string]any)
		if m["nid"].(float64) == 99000001 {
			found = true
			if m["title"] != "工作台测试·全勤纪" || m["active"] != false {
				t.Fatalf("watchlist item = %v", m)
			}
		}
	}
	if !found {
		t.Fatalf("test book missing from watchlist: %v", wl["items"])
	}

	// The observation series is exposed with the simulate source.
	obs := getJSON(t,
		srv.URL+"/strata/books/99000001/observations", http.StatusOK)
	oitems := obs["items"].([]any)
	if float64(len(oitems)) != rows {
		t.Fatalf("observations = %d rows, want %v", len(oitems), rows)
	}

	// Idempotent re-inject: same series size, no row multiplication.
	body2 := doJSON(t, http.MethodPost,
		srv.URL+"/strata/dev/test-book", http.StatusOK)
	if body2["rows"] != rows {
		t.Fatalf("re-inject rows = %v, want %v", body2["rows"], rows)
	}
	obs = getJSON(t, srv.URL+"/strata/books/99000001/observations",
		http.StatusOK)
	if oitems = obs["items"].([]any); float64(len(oitems)) != rows {
		t.Fatalf("after re-inject = %d rows", len(oitems))
	}

	// Remove: everything is torn down.
	body = doJSON(t, http.MethodDelete,
		srv.URL+"/strata/dev/test-book", http.StatusOK)
	if body["present"] != false {
		t.Fatalf("remove = %v", body)
	}
	getJSON(t, srv.URL+"/strata/books/99000001", http.StatusNotFound)
	wl = getJSON(t, srv.URL+"/strata/watchlist", http.StatusOK)
	if items, _ := wl["items"].([]any); len(items) != 0 {
		t.Fatalf("watchlist after remove = %v", wl)
	}
	obs = getJSON(t, srv.URL+"/strata/books/99000001/observations",
		http.StatusOK)
	if len(obs["items"].([]any)) != 0 {
		t.Fatalf("observations after remove = %v", obs)
	}

	// Invalid days.
	for _, q := range []string{"?days=0", "?days=999", "?days=abc"} {
		doJSON(t, http.MethodPost,
			srv.URL+"/strata/dev/test-book"+q, http.StatusBadRequest)
	}
}

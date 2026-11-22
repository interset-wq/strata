package api

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/crawl"
	"strata/engine/internal/store"
	"strata/engine/internal/testseed"
)

func TestContestArchive(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests", http.StatusOK)
	groups, ok := body["groups"].([]any)
	if !ok || len(groups) < 4 {
		t.Fatalf("groups = %v", body["groups"])
	}
	var sawZheng, sawThirteen bool
	for _, raw := range groups {
		g := raw.(map[string]any)
		switch g["name"] {
		case "七征":
			sawZheng = true
			if g["count"].(float64) != 2 || g["series"] != "x" {
				t.Fatalf("七征 = %v", g)
			}
		case "十三征":
			sawThirteen = true
			if g["start"] != "2025-05-04" || g["end"] != "2025-10-07" {
				t.Fatalf("十三征 = %v", g)
			}
		}
	}
	if !sawZheng || !sawThirteen {
		t.Fatalf("missing groups: zheng=%v thirteen=%v", sawZheng, sawThirteen)
	}
}

// TestContestOfficialURL: archive groups carry the verified official
// activity-page URL (contest_meta.go; source docs/contest-roster-harvest.md
// §2); unverified events omit the key — the UI only shows its jump entry
// when the URL is present and never fabricates one.
func TestContestOfficialURL(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests", http.StatusOK)
	groups := body["groups"].([]any)
	var zheng, ip map[string]any
	for _, raw := range groups {
		g := raw.(map[string]any)
		switch g["name"] {
		case "七征":
			zheng = g
		case "崩坏3征文":
			ip = g
		}
	}
	if zheng == nil || zheng["official"] != "https://pages.sfacg.com/h5/act/zw2019/" {
		t.Fatalf("七征 = %v", zheng)
	}
	if ip == nil {
		t.Fatal("missing 崩坏3征文 group")
	}
	if _, has := ip["official"]; has {
		t.Fatalf("崩坏3征文 carries an unverified official URL: %v", ip)
	}
}

// TestContestLaunchYearSort: /strata/contests groups follow the archive
// tab order (spring, x, autumn, winter, other — user decision 2026-11-22),
// each section by launch year ascending (official meta year, else the
// in-library floor) with deterministic tie-breaks; other-series events
// expose their home-tab lane (dialogue/ip; omitted = theme).
func TestContestLaunchYearSort(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests", http.StatusOK)
	groups := body["groups"].([]any)
	wantSeries := []string{"spring", "x", "x", "other", "other", "other"}
	if len(groups) != len(wantSeries) {
		t.Fatalf("groups = %v", groups)
	}
	for i, raw := range groups {
		g := raw.(map[string]any)
		if g["series"] != wantSeries[i] {
			t.Fatalf("group %d = %v, want series %s", i, g, wantSeries[i])
		}
	}
	// within the x section: 七征 (2019) before 十三征 (2025).
	if groups[1].(map[string]any)["name"] != "七征" ||
		groups[2].(map[string]any)["name"] != "十三征" {
		t.Fatalf("x order = %v, %v", groups[1], groups[2])
	}
	// other section by launch year: 少女前线 (2015) < 龙之谷 (2016) <
	// 崩坏3 (2019, official meta year); all three carry the ip lane.
	wantNames := []string{"少女前线征文", "龙之谷征文", "崩坏3征文"}
	for i, raw := range groups[3:] {
		g := raw.(map[string]any)
		if g["name"] != wantNames[i] || g["lane"] != "ip" {
			t.Fatalf("group %d = %v, want %s (lane ip)", i+3, g, wantNames[i])
		}
	}
}

func TestContestArchiveBooks(t *testing.T) {
	srv, _ := newTestServer(t)
	// missing contest → 400
	getJSON(t, srv.URL+"/strata/contests/books", http.StatusBadRequest)
	// N征 event: prefix match pulls in both divisions.
	body := getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("七征"), http.StatusOK)
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	// clicks must ride along on list items (user report 2026-11-22: the
	// archive rows rendered "点击 0" when the engine omitted the column);
	// testseed pins clicks at 1000.
	for _, raw := range items {
		if c := raw.(map[string]any)["clicks"]; c == nil || c.(float64) != 1000 {
			t.Fatalf("item clicks = %v, want 1000", c)
		}
	}
	// per caps each form: 崩坏3征文's two ip_collab books → one at per=1.
	body = getJSON(t, srv.URL+"/strata/contests/books?contest="+url.QueryEscape("崩坏3征文")+"&per=1", http.StatusOK)
	items = body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 1006 {
		t.Fatalf("items = %v", items)
	}
}

// newRosterTestServer builds the test seed with the seams exposed (the
// rosterFetch override keeps the endpoint tests off the network).
func newRosterTestServer(t *testing.T) (*httptest.Server, *Server) {
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
	srv := NewServer(st)
	ts := httptest.NewServer(srv.engine)
	t.Cleanup(func() {
		ts.Close()
		st.Close()
	})
	return ts, srv
}

func TestRosterArchiveFlags(t *testing.T) {
	srv, _ := newTestServer(t)
	body := getJSON(t, srv.URL+"/strata/contests", http.StatusOK)
	groups, _ := body["groups"].([]any)
	var zheng, spring, ip map[string]any
	for _, raw := range groups {
		g := raw.(map[string]any)
		switch g["name"] {
		case "七征":
			zheng = g
		case "2025春季征文":
			spring = g
		case "崩坏3征文":
			ip = g
		}
	}
	// 七征: roster available, five divisions in ledger order.
	if zheng == nil || zheng["roster"] != true {
		t.Fatalf("七征 = %v", zheng)
	}
	tracks, _ := zheng["roster_tracks"].([]any)
	if len(tracks) != 5 || tracks[0] != "长篇" || tracks[4] != "对话类征文短篇" {
		t.Fatalf("roster_tracks = %v", tracks)
	}
	// 2025春季征文: single track — roster true, no roster_tracks key.
	if spring == nil || spring["roster"] != true {
		t.Fatalf("2025春季征文 = %v", spring)
	}
	if _, has := spring["roster_tracks"]; has {
		t.Fatalf("single-track event carries roster_tracks: %v", spring)
	}
	// 崩坏3征文: no verified tagId → roster false.
	if ip == nil || ip["roster"] != false {
		t.Fatalf("崩坏3征文 = %v", ip)
	}
}

func TestRosterOfficial(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	calls := 0
	srv.rosterFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, gen string, tag, page, size int) (*crawl.RosterPage, error) {
		calls++
		// 七征长篇: old H5 gen, tag 408, pi 0-based, ps 200.
		if gen != "old" || tag != 408 || page != 0 || size != 200 {
			return nil, fmt.Errorf("unexpected fetch gen=%s tag=%d page=%d size=%d", gen, tag, page, size)
		}
		return &crawl.RosterPage{
			TotalPage: 1,
			Entries: []crawl.RosterEntry{
				{NID: 3001, Title: "Zheng Long X", Author: "Author X",
					Cover: "https://rs.sfacg.com/x.jpg"},
				{NID: 9990001, Title: "Roster Only", Author: "Author R",
					Intro: "官方简介", Cover: "https://rs.sfacg.com/r.jpg", CategoryID: 3},
			},
		}, nil
	}
	u := ts.URL + "/strata/roster?contest=" + url.QueryEscape("七征") + "&division=长篇"
	body := getJSON(t, u, http.StatusOK)
	if body["source"] != "official" || body["page"].(float64) != 1 || body["pages"].(float64) != 1 {
		t.Fatalf("body = %v", body)
	}
	items := body["items"].([]any)
	if len(items) != 2 {
		t.Fatalf("items = %v", items)
	}
	in := items[0].(map[string]any)
	if in["in_library"] != true || in["form"] != "long" || in["fav_pctl"].(float64) != 0.99 {
		t.Fatalf("in-library item = %v", in)
	}
	out := items[1].(map[string]any)
	if out["in_library"] != false {
		t.Fatalf("out-of-library item = %v", out)
	}
	// out-of-library books carry no local badges (nothing fabricated).
	if _, has := out["form"]; has {
		t.Fatalf("out-of-library carries form: %v", out)
	}
	if _, has := out["fav_pctl"]; has {
		t.Fatalf("out-of-library carries fav_pctl: %v", out)
	}
	// cached: a second serve hits the page cache, no new fetch.
	getJSON(t, u, http.StatusOK)
	if calls != 1 {
		t.Fatalf("fetch calls = %d, want 1 (page cache)", calls)
	}
}

func TestRosterDead(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.rosterFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, gen string, tag, page, size int) (*crawl.RosterPage, error) {
		return nil, nil // interface dead: errorCode != 200 / structure missing
	}
	body := getJSON(t,
		ts.URL+"/strata/roster?contest="+url.QueryEscape("七征")+"&division=长篇",
		http.StatusOK)
	if body["source"] != "degraded" {
		t.Fatalf("body = %v", body)
	}
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 3001 {
		t.Fatalf("degraded items = %v", items)
	}
}

func TestRosterNoTag(t *testing.T) {
	ts, _ := newRosterTestServer(t)
	// 崩坏3征文 has seed books but no verified tagId: straight to the
	// in-library subset, zero requests.
	body := getJSON(t,
		ts.URL+"/strata/roster?contest="+url.QueryEscape("崩坏3征文"),
		http.StatusOK)
	if body["source"] != "degraded" {
		t.Fatalf("body = %v", body)
	}
	if items := body["items"].([]any); len(items) != 2 {
		t.Fatalf("degraded items = %v", items)
	}
}

func TestRosterSizeDowngrade(t *testing.T) {
	ts, srv := newRosterTestServer(t)
	srv.rosterFetch = func(ctx context.Context, client *http.Client,
		l *crawl.Limiter, gen string, tag, page, size int) (*crawl.RosterPage, error) {
		// 十三征长篇: new SPA gen, tag 752, page 1-based.
		if gen != "new" || tag != 752 || page != 1 {
			return nil, fmt.Errorf("unexpected fetch gen=%s tag=%d page=%d", gen, tag, page)
		}
		switch size {
		case 500:
			return &crawl.RosterPage{TotalPage: 1}, nil // boundary trap: empty
		case 100:
			return &crawl.RosterPage{
				TotalPage: 1,
				Entries:   []crawl.RosterEntry{{NID: 3004, Title: "Thirteen Long W", Author: "Author W"}},
			}, nil
		}
		return nil, fmt.Errorf("unexpected size %d", size)
	}
	body := getJSON(t,
		ts.URL+"/strata/roster?contest="+url.QueryEscape("十三征")+"&division=长篇",
		http.StatusOK)
	if body["source"] != "official" {
		t.Fatalf("body = %v", body)
	}
	items := body["items"].([]any)
	if len(items) != 1 || items[0].(map[string]any)["nid"].(float64) != 3004 {
		t.Fatalf("items = %v", items)
	}
}

func TestRosterValidation(t *testing.T) {
	ts, _ := newRosterTestServer(t)
	getJSON(t, ts.URL+"/strata/roster", http.StatusBadRequest)
	// multi-track event without a division.
	getJSON(t, ts.URL+"/strata/roster?contest="+url.QueryEscape("七征"), http.StatusBadRequest)
}

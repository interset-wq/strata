package store

import (
	"context"
	"errors"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/testseed"
)

func openTestStore(t *testing.T) *Store {
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
	st, err := Open(appshell.UserDBPath(data), seedPath, m)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { st.Close() })
	return st
}

func TestCoverURLs(t *testing.T) {
	st := openTestStore(t)
	got, err := st.CoverURLs(context.Background(), []int64{1008, 999999})
	if err != nil {
		t.Fatal(err)
	}
	if got[1008] != "cover-1008.jpg" {
		t.Fatalf("cover 1008 = %q, want cover-1008.jpg", got[1008])
	}
	if _, ok := got[999999]; ok {
		t.Fatalf("unexpected cover for missing nid: %q", got[999999])
	}
}

func TestSetAdaptation(t *testing.T) {
	st := openTestStore(t)
	if err := st.SetAdaptation(context.Background(), 1001, 2937, 0, nil); err != nil {
		t.Fatal(err)
	}
	m, err := st.BookMeta(context.Background(), 1001)
	if err != nil || m == nil {
		t.Fatalf("meta = %+v, err = %v", m, err)
	}
	if m.ComicID == nil || *m.ComicID != 2937 {
		t.Fatalf("comic_id = %v, want 2937", m.ComicID)
	}
	if m.AlbumID == nil || *m.AlbumID != 0 {
		t.Fatalf("album_id = %v, want 0 (confirmed none)", m.AlbumID)
	}
	// 0 overwrites a previous positive value — confirmed-none is new truth
	// and must clear an earlier adaptation (docs/05 §6: 0 vs NULL).
	folder := "XJYQS"
	if err := st.SetAdaptation(context.Background(), 1001, 0, 97, &folder); err != nil {
		t.Fatal(err)
	}
	m, _ = st.BookMeta(context.Background(), 1001)
	if m.ComicID == nil || *m.ComicID != 0 {
		t.Fatalf("comic_id = %v, want 0 after overwrite", m.ComicID)
	}
	if m.AlbumID == nil || *m.AlbumID != 97 {
		t.Fatalf("album_id = %v, want 97", m.AlbumID)
	}
	if m.ComicFolder == nil || *m.ComicFolder != "XJYQS" {
		t.Fatalf("comic_folder = %v, want XJYQS", m.ComicFolder)
	}
}

func TestBookMergesLatestObservation(t *testing.T) {
	st := openTestStore(t)
	detail, err := st.Book(context.Background(), 1001)
	if err != nil {
		t.Fatal(err)
	}
	if detail.Book.Favs == nil || *detail.Book.Favs != 500 {
		t.Fatalf("seed favs = %v", detail.Book.Favs)
	}
	if detail.Local == nil || detail.Local.Favs == nil || *detail.Local.Favs != 777 {
		t.Fatalf("local favs = %+v", detail.Local)
	}
	if len(detail.Tags) != 2 || detail.Tags[0] != "战斗" && detail.Tags[0] != "热血" {
		t.Fatalf("tags = %v", detail.Tags)
	}
}

func TestLicensedBookHasNoPercentiles(t *testing.T) {
	st := openTestStore(t)
	detail, err := st.Book(context.Background(), 2001)
	if err != nil {
		t.Fatal(err)
	}
	if !detail.Book.IsLicensed {
		t.Fatal("nid 2001 should be licensed")
	}
	if detail.Book.FavPctl != nil || detail.Book.PctlPR != nil {
		t.Fatalf("licensed percentiles = %v / %v", detail.Book.FavPctl, detail.Book.PctlPR)
	}
	if detail.Local != nil {
		t.Fatal("unexpected local observation")
	}
}

func TestBookNotFound(t *testing.T) {
	st := openTestStore(t)
	_, err := st.Book(context.Background(), 999999)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("err = %v", err)
	}
}

func TestRankingFavsExcludesLicensedAndOtherYears(t *testing.T) {
	st := openTestStore(t)
	items, err := st.RankingFavs(context.Background(), 2010, "", "", "", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 3 {
		t.Fatalf("items = %d, want 3", len(items))
	}
	if items[0].NID != 1001 || items[0].FavPctl != 0.9 || items[0].Rank != 1 {
		t.Fatalf("first = %+v", items[0])
	}
	for _, item := range items {
		if item.NID == 2001 {
			t.Fatal("licensed book leaked into A-class ranking")
		}
	}
}

func TestRankingFavsGenreFilter(t *testing.T) {
	st := openTestStore(t)
	items, err := st.RankingFavs(context.Background(), 2010, "魔幻", "", "", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 1001 || items[1].NID != 1004 {
		t.Fatalf("items = %+v", items)
	}
}

func TestRankingShort(t *testing.T) {
	st := openTestStore(t)
	items, err := st.RankingShort(context.Background(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 3 || items[0].NID != 3003 || items[1].NID != 1002 ||
		items[2].NID != 1004 {
		t.Fatalf("items = %+v", items)
	}
	if items[0].Words == nil || *items[0].Words != 30000 {
		t.Fatalf("words = %v", items[0].Words)
	}
}

func TestSeedMeta(t *testing.T) {
	st := openTestStore(t)
	meta, err := st.SeedMeta(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if meta["book_count"] != "6" || meta["licensed_count"] != "1" {
		t.Fatalf("meta = %v", meta)
	}
}

// TestBannerPickDailySeedChangesOrder pins the 2026-11-20 fix: with the
// old additive hash (nid*a + day) the day advanced the cut point by one
// bucket in the 1,000,003-bucket space, so consecutive days returned the
// identical top-k (user reported today == yesterday). The XOR hash must
// reorder the pool on consecutive days and stay deterministic per seed.
func TestBannerPickDailySeedChangesOrder(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	a, err := st.BannerPick(ctx, 20261119, 0, 100, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(a) < 2 {
		t.Fatalf("featured pool too small: %d", len(a))
	}
	b, err := st.BannerPick(ctx, 20261120, 0, 100, "")
	if err != nil {
		t.Fatal(err)
	}
	if sameNidOrder(a, b) {
		t.Fatalf("consecutive-day orders identical: %+v", a)
	}
	// Determinism: the same seed returns the same order.
	c, err := st.BannerPick(ctx, 20261119, 0, 100, "")
	if err != nil {
		t.Fatal(err)
	}
	if !sameNidOrder(a, c) {
		t.Fatalf("same seed, different order: %+v vs %+v", a, c)
	}
}

func sameNidOrder(a, b []FeaturedBook) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i].NID != b[i].NID {
			return false
		}
	}
	return true
}

// TestCoverCarouselDailyRotation pins the 2026-11-20 change: the
// composed-banner carousel draws from the form's favs head pool with the
// BannerPick date hash, so consecutive days differ and the same seed
// stays deterministic.
func TestCoverCarouselDailyRotation(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	// The testseed carries no user.db covers; add observed covers so the
	// long-form head pool (1001, 1003) is non-empty.
	head := []struct {
		nid int64
		url string
	}{{1001, "cover-1001"}, {1003, "cover-1003"}}
	for _, h := range head {
		if _, err := st.DB.ExecContext(ctx,
			`INSERT INTO covers (nid, cover, fetched_at) VALUES (?, ?, ?)`,
			h.nid, h.url, 1); err != nil {
			t.Fatal(err)
		}
	}
	a, err := st.CoverCarousel(ctx, "long", 100, 20261119)
	if err != nil {
		t.Fatal(err)
	}
	if len(a) != 2 {
		t.Fatalf("head pool = %d, want 2", len(a))
	}
	b, err := st.CoverCarousel(ctx, "long", 100, 20261120)
	if err != nil {
		t.Fatal(err)
	}
	same := len(a) == len(b)
	if same {
		for i := range a {
			if a[i].NID != b[i].NID {
				same = false
				break
			}
		}
	}
	if same {
		t.Fatalf("consecutive-day orders identical: %+v", a)
	}
	c, err := st.CoverCarousel(ctx, "long", 100, 20261119)
	if err != nil {
		t.Fatal(err)
	}
	sameAgain := len(a) == len(c)
	if sameAgain {
		for i := range a {
			if a[i].NID != c[i].NID {
				sameAgain = false
				break
			}
		}
	}
	if !sameAgain {
		t.Fatalf("same seed, different order: %+v vs %+v", a, c)
	}
}

// TestAuthorBooks pins the author-page timeline query (docs/author-
// profile-on-demand §1): one author's seed books in est_date DESC order
// with the timeline field filled; unknown authors yield an empty list.
func TestAuthorBooks(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	items, err := st.AuthorBooks(ctx, "Author C", 20, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 1003 || items[1].NID != 1004 {
		t.Fatalf("items = %+v", items)
	}
	// 1003's est_date is '2011-01-05' in the testseed (low-conf docs/14
	// fixture); 1004 keeps the build default '2010-01-01'. DESC: 1003
	// first.
	if items[0].EstDate == nil || *items[0].EstDate != "2011-01-05" {
		t.Fatalf("est_date[0] = %v", items[0].EstDate)
	}
	if items[1].EstDate == nil || *items[1].EstDate != "2010-01-01" {
		t.Fatalf("est_date[1] = %v", items[1].EstDate)
	}

	// Ascending flips the order (timeline sort toggle, docs/08).
	asc, err := st.AuthorBooks(ctx, "Author C", 20, 0, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(asc) != 2 || asc[0].NID != 1004 || asc[1].NID != 1003 {
		t.Fatalf("asc items = %+v", asc)
	}

	none, err := st.AuthorBooks(ctx, "Nobody", 20, 0, true)
	if err != nil {
		t.Fatal(err)
	}
	if len(none) != 0 {
		t.Fatalf("unknown author: %+v", none)
	}
}

// TestAuthorProfileRoundTrip pins the v7 author_profiles cache
// (docs/author-profile-on-demand §4): absent → nil, save → get, upsert
// replaces (NULL intro/avatar survive the round trip).
func TestAuthorProfileRoundTrip(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	got, err := st.GetAuthorProfile(ctx, "author c")
	if err != nil {
		t.Fatal(err)
	}
	if got != nil {
		t.Fatalf("absent profile = %+v", got)
	}

	intro := "新人作者"
	avatar := "https://x/a.jpg"
	if err := st.SaveAuthorProfile(ctx, &AuthorProfile{
		AuthorKey: "author c", AuthorName: "Author C",
		AuthorIntro: &intro, AuthorAvatar: &avatar,
		Verdict: "ok", SourceNID: 1003, ObservedAt: 1700000000,
	}); err != nil {
		t.Fatal(err)
	}
	got, err = st.GetAuthorProfile(ctx, "author c")
	if err != nil {
		t.Fatal(err)
	}
	if got == nil {
		t.Fatal("nil after save")
	}
	if got.AuthorName != "Author C" || got.Verdict != "ok" || got.SourceNID != 1003 {
		t.Fatalf("profile = %+v", got)
	}
	if got.AuthorIntro == nil || *got.AuthorIntro != "新人作者" {
		t.Fatalf("intro = %v", got.AuthorIntro)
	}
	if got.AuthorAvatar == nil || *got.AuthorAvatar != "https://x/a.jpg" {
		t.Fatalf("avatar = %v", got.AuthorAvatar)
	}

	// v8 works cache: the official works list round-trips (docs/08
	// §author-profile — cache hits replay it instead of an empty array).
	worksJSON := `[{"nid":1003,"title":"Long C"}]`
	if err := st.SaveAuthorProfile(ctx, &AuthorProfile{
		AuthorKey: "author c", AuthorName: "Author C", Verdict: "ok",
		SourceNID: 1003, ObservedAt: 1700000002, Works: &worksJSON,
	}); err != nil {
		t.Fatal(err)
	}
	got2, err := st.GetAuthorProfile(ctx, "author c")
	if err != nil {
		t.Fatal(err)
	}
	if got2 == nil || got2.Works == nil || *got2.Works != worksJSON {
		t.Fatalf("works = %v", got2.Works)
	}

	// Upsert: a second save replaces the row; cleared fields go NULL.
	if err := st.SaveAuthorProfile(ctx, &AuthorProfile{
		AuthorKey: "author c", AuthorName: "Author C",
		Verdict: "dead", SourceNID: 1004, ObservedAt: 1700000100,
	}); err != nil {
		t.Fatal(err)
	}
	got, _ = st.GetAuthorProfile(ctx, "author c")
	if got == nil || got.Verdict != "dead" || got.AuthorIntro != nil {
		t.Fatalf("upsert = %+v", got)
	}
}

// TestSearch pins the L1 local search contract (docs/08): title/author
// LIKE with wildcard escaping, favs DESC ordering, licensed included,
// and the cover overlay column scanning without breaking on NULLs.
func TestSearch(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	items, err := st.Search(ctx, "Long", 20)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 4 || items[0].NID != 3001 || items[1].NID != 1003 {
		t.Fatalf("items = %+v", items)
	}
	if items[0].CoverURL != nil {
		t.Fatalf("testseed has no covers, got %v", items[0].CoverURL)
	}

	items, err = st.Search(ctx, "author a", 20)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 1001 {
		t.Fatalf("author match = %+v", items)
	}

	// LIKE wildcards in the query are escaped, not interpreted.
	items, err = st.Search(ctx, "%", 20)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 0 {
		t.Fatalf("escaped %%: %+v", items)
	}

	// Auto-collected out-of-seed books (discovered) are searchable too,
	// flagged in_seed=false (docs/08 §search-remote discovery loop).
	if _, err := st.DB.ExecContext(ctx, `
INSERT INTO discovered(nid, title, author, cover_url, source, observed_at)
VALUES (5555, 'Newly Found', 'Author Z', NULL, 'search', 1700000000)`); err != nil {
		t.Fatal(err)
	}
	items, err = st.Search(ctx, "Newly Found", 20)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 5555 || items[0].InSeed {
		t.Fatalf("discovered hit = %+v", items)
	}
}

// TestSearchHistory pins the search-history contract (docs/08
// §search-history): every submit is stored, reads dedupe by keyword
// with the most recent keyword first.
func TestSearchHistory(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	words, err := st.SearchHistory(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(words) != 0 {
		t.Fatalf("fresh history = %v", words)
	}

	for _, kw := range []string{"英雄", "重生", "英雄"} {
		if err := st.AddSearchHistory(ctx, kw, 3); err != nil {
			t.Fatal(err)
		}
	}
	words, err = st.SearchHistory(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	// 英雄 was re-searched last (highest id), so it comes first.
	if len(words) != 2 || words[0] != "英雄" || words[1] != "重生" {
		t.Fatalf("history = %v", words)
	}
}

// TestWatchListCoversDiscovered pins the discovery-loop integration
// (docs/08 §discovered): an auto-collected out-of-seed book put on the
// watchlist still shows up in the list (LEFT JOIN, discovered supplies
// the metadata the seed has no row for) and keeps tracking on.
func TestWatchListCoversDiscovered(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	if _, err := st.DB.ExecContext(ctx, `
INSERT INTO discovered(nid, title, author, cover_url, source, observed_at)
VALUES (5555, 'Newly Found', 'Author Z', NULL, 'search', 1700000000)`); err != nil {
		t.Fatal(err)
	}
	if err := st.WatchAdd(ctx, 5555, 1700000001, true); err != nil {
		t.Fatal(err)
	}
	items, err := st.WatchList(ctx)
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, it := range items {
		if it.NID == 5555 {
			found = true
			if it.Title != "Newly Found" {
				t.Fatalf("title = %q", it.Title)
			}
		}
	}
	if !found {
		t.Fatalf("discovered nid 5555 missing from watchlist: %+v", items)
	}
}

func TestNormalizeContest(t *testing.T) {
	cases := map[string]string{
		// N征系列：篇幅赛项并入母赛事（用户 2026-11-21：只有 x征 多赛项）
		"六征长篇":          "六征",
		"六征中篇":          "六征",
		"六征短篇":          "六征",
		"十三征长篇":         "十三征",
		"七征对话类征文长篇":     "七征对话类征文",
		"七征对话类征文短篇":     "七征对话类征文",
		"九征对话小说":         "九征对话小说", // 无篇幅后缀：原样
		"十征":             "十征",
		// 非 N征 赛事：一律原样
		"冬季征文":           "冬季征文",
		"怪谈异闻主题征文长篇":    "怪谈异闻主题征文长篇",
		"春节征文长篇":         "春节征文长篇",
		"2025春季征文":        "2025春季征文",
		"“超新星杯”短篇大赛":    "“超新星杯”短篇大赛",
		"崩坏3征文":          "崩坏3征文",
		"征长篇":            "征长篇", // 无数字前缀不算 N征
		"":               "",
	}
	for in, want := range cases {
		if got := NormalizeContest(in); got != want {
			t.Errorf("NormalizeContest(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestClassicTagPtypeFilters(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	// book_tags rows: 1001 热血/战斗, 1004 战斗, 2001 战斗 (licensed, excluded),
	// 1003 2020萌神; every test book is price_type 免费.
	items, err := st.ClassicBooks(ctx, "", "", "", "", "", "", []string{"战斗"}, 0, 100, 0, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 1001 || items[1].NID != 1004 {
		t.Fatalf("tag=战斗: got %+v", items)
	}
	items, err = st.ClassicBooks(ctx, "", "", "", "", "", "", []string{"2020萌神"}, 0, 100, 0, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 1003 {
		t.Fatalf("tag=2020萌神: got %+v", items)
	}
	// 多值 = OR（用户 2026-11-21）：战斗 (1001/1004) ∪ 2020萌神 (1003)。
	items, err = st.ClassicBooks(ctx, "", "", "", "", "", "", []string{"战斗", "2020萌神"}, 0, 100, 0, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 3 {
		t.Fatalf("tag=战斗,2020萌神 (OR): got %+v", items)
	}
	items, err = st.ClassicBooks(ctx, "", "", "", "", "", "VIP", nil, 0, 100, 0, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 0 {
		t.Fatalf("ptype=VIP: want 0 rows, got %+v", items)
	}
	items, err = st.ClassicBooks(ctx, "", "", "", "", "", "免费", []string{"战斗"}, 0, 100, 0, "", "")
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 {
		t.Fatalf("tag=战斗 + ptype=免费: got %+v", items)
	}
}

// TestRecommend pins the quantitative recommendation stream (docs/12
// §3, docs/lqs-ranking-integration.md §3.2): two-level ordering, cover
// hard gate, licensed exclusion, and the group A → group B cursor
// transition. Covers are inserted into user.db (the observed-covers
// channel); 1008 already carries a seed cover.
func TestRecommend(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	for _, nid := range []int64{1001, 1003, 1005, 1007} {
		if _, err := st.DB.ExecContext(ctx,
			`INSERT INTO covers (nid, cover, fetched_at) VALUES (?, ?, ?)`,
			nid, "observed-cover.jpg", 1); err != nil {
			t.Fatal(err)
		}
	}

	// Full stream: group A (lqs DESC): 1001 (0.9), 1003 (0.7 — its higher
	// fav_pctl 0.99 must not outrank lqs); group B (fav_pctl DESC, nid
	// ASC): 1005 (0.95), 1007 (0.7), 1008 (0.6, seed cover). Excluded:
	// 1004/1006 cover-less, 2001 licensed (lqs 1.0 canary), 1002/1009–1011
	// cover-less.
	items, err := st.Recommend(ctx, "", "", 100)
	if err != nil {
		t.Fatal(err)
	}
	want := []int64{1001, 1003, 1005, 1007, 1008}
	if len(items) != len(want) {
		t.Fatalf("items = %+v", items)
	}
	for i, w := range want {
		if items[i].NID != w {
			t.Fatalf("item %d = %d, want %d (stream %+v)", i, items[i].NID, w, items)
		}
	}
	if items[1].LQS == nil || *items[1].LQS != 0.7 {
		t.Fatalf("1003 lqs = %v, want 0.7", items[1].LQS)
	}
	if items[2].LQS != nil {
		t.Fatalf("1005 lqs = %v, want nil (fallback group)", items[2].LQS)
	}

	// Page 1 (limit 2): the two group-A books.
	page, err := st.Recommend(ctx, "", "", 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(page) != 2 || page[0].NID != 1001 || page[1].NID != 1003 {
		t.Fatalf("page1 = %+v", page)
	}
	cur := RecommendCursor(page[1].LQS, page[1].FavPctl, page[1].NID)
	if cur != "0.7|0.99|1003" {
		t.Fatalf("cursor = %q, want 0.7|0.99|1003", cur)
	}

	// Page 2 (cursor at the group-A tail): all of group B follows — the
	// group transition must not skip or repeat.
	page, err = st.Recommend(ctx, cur, "", 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(page) != 2 || page[0].NID != 1005 || page[1].NID != 1007 {
		t.Fatalf("page2 = %+v", page)
	}

	// Page 3 (cursor inside group B): strictly after on (fav_pctl, nid).
	cur = RecommendCursor(page[1].LQS, page[1].FavPctl, page[1].NID)
	if cur != "|0.7|1007" {
		t.Fatalf("cursor = %q, want |0.7|1007 (empty lqs part)", cur)
	}
	page, err = st.Recommend(ctx, cur, "", 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(page) != 1 || page[0].NID != 1008 {
		t.Fatalf("page3 = %+v", page)
	}

	// form=medium: no lqs group (mqs not landed), pure fav_pctl fallback.
	page, err = st.Recommend(ctx, "", "medium", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(page) != 1 || page[0].NID != 1007 {
		t.Fatalf("medium page = %+v", page)
	}

	// Invalid cursors.
	for _, bad := range []string{"abc", "0.7|0.99", "1.5|0.9|1001",
		"0.7|-1|1001", "0.7|0.9|0"} {
		if _, err := st.Recommend(ctx, bad, "", 10); err == nil {
			t.Fatalf("cursor %q: want error", bad)
		}
	}
}

func TestFacets(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	genres, ptypes, tags, years, err := st.Facets(ctx, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(ptypes) != 1 || ptypes[0].Name != "免费" || ptypes[0].Count != 15 {
		t.Fatalf("ptypes: %+v", ptypes)
	}
	if len(genres) != 5 || genres[0].Name != "都市" || genres[0].Count != 6 {
		t.Fatalf("genres: %+v", genres)
	}
	if len(tags) != 3 || tags[0].Name != "战斗" || tags[0].Count != 2 {
		t.Fatalf("tags: %+v", tags)
	}
	if len(years) == 0 {
		t.Fatalf("years empty")
	}
	for i := 1; i < len(years); i++ {
		if years[i-1].Year < years[i].Year {
			t.Fatalf("years not DESC: %+v", years)
		}
	}
}

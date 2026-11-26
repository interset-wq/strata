package store

import (
	"context"
	"slices"
	"testing"
)

// addCovers plants display-only cover values in user.db (seed.db is attached
// read-only). Covers are NOT an admission gate any more (sfacg lost covers of
// many good books): these tests only use them to pin cover_url passthrough.
func addCovers(t *testing.T, st *Store, nids ...int64) {
	t.Helper()
	for _, nid := range nids {
		if _, err := st.DB.ExecContext(context.Background(),
			`INSERT INTO covers (nid, cover, fetched_at) VALUES (?, ?, ?)`,
			nid, "related-cover.jpg", 1); err != nil {
			t.Fatal(err)
		}
	}
}

func relatedIDs(items []RankItem) []int64 {
	ids := make([]int64, len(items))
	for i, it := range items {
		ids[i] = it.NID
	}
	return ids
}

// TestRelatedBooksLongAnchor pins the v5 gates on the long-form anchor 1001:
// 候选准入不再看 cqs/cps（用户 2026-11-26 裁定：指标只排展示顺序、不决定谁被
// 推荐），所以 1005 (cps 0.1) / 3004 (cps 9.0) 不再被中层带挡掉，与 1003 /
// 3001 一起进同-form 末档；2001 仍因授权排除，1001 自己是锚点。选满后按 cqs
// DESC 排展示顺序 → [1003(1.4) 3001(0.8) 1005(0.6) 3004(0.4)]。
func TestRelatedBooksLongAnchor(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	addCovers(t, st, 1003, 1005, 3001, 3004, 738162)

	res, err := st.RelatedBooks(ctx, 1001, 8)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := relatedIDs(res.Items), []int64{1003, 738162, 3001, 1005, 3004}; !slices.Equal(got, want) {
		t.Fatalf("items = %v, want %v", got, want)
	}
	if res.Form != "long" || res.Genre != "魔幻" {
		t.Fatalf("anchor meta = %q/%q", res.Form, res.Genre)
	}
	if res.Tier != "fallback" || res.Ordering != "cqs" {
		t.Fatalf("tier/ordering = %q/%q, want fallback/cqs", res.Tier, res.Ordering)
	}
	// 展示顺序 = cqs DESC（累计值 clicks/favs/praises 不参与排序）；
	// rail 条目不带 cqs 列，回种子表核对。
	for i := 1; i < len(res.Items); i++ {
		if seedCQS(t, st, res.Items[i-1].NID) < seedCQS(t, st, res.Items[i].NID) {
			t.Fatalf("not cqs DESC: %v", relatedIDs(res.Items))
		}
	}
	for _, it := range res.Items {
		if it.NID == 1001 || it.Author == "Author A" || it.Form != "long" ||
			it.CoverURL == nil {
			t.Fatalf("gate leaked: %+v", it)
		}
	}
}

// seedCQS reads the column the rail itself does not carry.
func seedCQS(t *testing.T, st *Store, nid int64) float64 {
	t.Helper()
	var v float64
	if err := st.DB.QueryRowContext(context.Background(),
		"SELECT cqs FROM seed.books WHERE nid = ?", nid).Scan(&v); err != nil {
		t.Fatal(err)
	}
	return v
}

// TestRelatedBooksAPrimeTier: the licensed anchor 2001 (魔幻 long, 战斗 tag)
// has exactly one A′ candidate — 1001 (same genre, Δ2 年, 战斗∩热血 overlap).
// limit=1 must land on it; limit=8 then degrades to the fallback tail, and the
// tier echo follows the last tier that contributed a row. The tail includes
// 1005/3004, which the retired has-cover gate used to drop (sfacg lost their
// covers; missing cover is not a quality signal).
func TestRelatedBooksAPrimeTier(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	addCovers(t, st, 1001, 1003, 3001)

	res, err := st.RelatedBooks(ctx, 2001, 1)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := relatedIDs(res.Items), []int64{1001}; !slices.Equal(got, want) {
		t.Fatalf("A′ items = %v, want %v", got, want)
	}
	if res.Tier != "a" {
		t.Fatalf("tier = %q, want a", res.Tier)
	}
	// 授权书只从候选里排除，作为锚点照样能推。
	if res.Items[0].Author == "天闻角川" {
		t.Fatalf("anchor leaked into its own rail: %+v", res.Items[0])
	}

	res, err = st.RelatedBooks(ctx, 2001, 8)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := relatedIDs(res.Items), []int64{1001, 1003, 738162, 3001, 1005, 3004}; !slices.Equal(got, want) {
		t.Fatalf("degraded items = %v, want %v", got, want)
	}
	if res.Tier != "fallback" {
		t.Fatalf("tier = %q, want fallback", res.Tier)
	}
}

// TestRelatedBooksPRAnchor: short form has no cqs, so the rail orders by the
// Bayes-smoothed pr (18 §1, κ=500). The fixture gives 1002 favs 100 / 3003
// favs 800 with the raw pr column the other way round (0.5 vs 0.9) — 1002 must
// still lead, because smoothing keeps low-favs books from looking great.
func TestRelatedBooksPRAnchor(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	addCovers(t, st, 1002, 3003)

	res, err := st.RelatedBooks(ctx, 1004, 8)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := relatedIDs(res.Items), []int64{1002, 3003}; !slices.Equal(got, want) {
		t.Fatalf("items = %v, want %v", got, want)
	}
	if res.Ordering != "pr" || res.Form != "short" {
		t.Fatalf("ordering/form = %q/%q, want pr/short", res.Ordering, res.Form)
	}
	for _, it := range res.Items {
		if it.Form != "short" || it.CoverURL == nil {
			t.Fatalf("form isolation leaked: %+v", it)
		}
	}
}

// TestRelatedBooksNoCoverGate: cover 不是判断依据（用户 2026-11-26 裁定）。
// sfacg 曾弄丢大量优质书封面，fixture 里 1003/1005/3001/3004 默认无 cover，
// 它们仍必须照常入选；cover_url 为 nil 交给 UI 占位兜底，不是排除理由。
func TestRelatedBooksNoCoverGate(t *testing.T) {
	st := openTestStore(t)
	res, err := st.RelatedBooks(context.Background(), 1001, 8)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := relatedIDs(res.Items), []int64{1003, 738162, 3001, 1005, 3004}; !slices.Equal(got, want) {
		t.Fatalf("no-cover items = %v, want %v", got, want)
	}
	for _, it := range res.Items {
		if it.CoverURL != nil {
			t.Fatalf("fixture should have no cover for %d: %q", it.NID, *it.CoverURL)
		}
	}
}

func TestRelatedBooksUnknownAnchor(t *testing.T) {
	st := openTestStore(t)
	res, err := st.RelatedBooks(context.Background(), 999999, 8)
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Items) != 0 || res.Tier != "none" {
		t.Fatalf("unknown anchor = %+v (tier %q)", res.Items, res.Tier)
	}
}

// TestSortRelatedStrata pins §3.5 档内三步: 每本归入命中的最稀有强标签组，
// 组按 df ASC 整组靠前，组间轮流出一本，组内保持 SQL 的口碑序。
func TestSortRelatedStrata(t *testing.T) {
	df := map[string]int{"师尊": 28, "热血": 600, "战斗": 900}
	cands := []relatedCand{
		{item: RankItem{NID: 1}, hits: []string{"热血", "战斗"}},
		{item: RankItem{NID: 2}, hits: []string{"热血"}},
		{item: RankItem{NID: 3}, hits: []string{"师尊"}},
		{item: RankItem{NID: 4}, hits: []string{"师尊", "战斗"}},
		{item: RankItem{NID: 5}, hits: []string{"战斗"}},
	}
	sortRelatedStrata(df, cands)

	got := relatedIDs(itemsOf(cands))
	// 师尊 (df 28) 先出一本 (3)，再轮到热血 (600) 出 1，再战斗 (900) 出 5，
	// 第二轮师尊组剩 4，热血组剩 2。
	if want := []int64{3, 1, 5, 4, 2}; !slices.Equal(got, want) {
		t.Fatalf("strata order = %v, want %v", got, want)
	}
}

func itemsOf(cands []relatedCand) []RankItem {
	out := make([]RankItem, len(cands))
	for i, c := range cands {
		out[i] = c.item
	}
	return out
}

// TestIsOperationalTag: 年份萌神是活动标记，不能当卖点参与召回。
func TestIsOperationalTag(t *testing.T) {
	for tag, want := range map[string]bool{
		"2020萌神": true,
		"萌神":     false,
		"战斗":     false,
		"热血":     false,
	} {
		if got := isOperationalTag(tag); got != want {
			t.Fatalf("isOperationalTag(%q) = %v, want %v", tag, got, want)
		}
	}
}

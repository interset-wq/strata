package store

import (
	"context"
	"testing"
)

func TestContestEventName(t *testing.T) {
	cases := map[string]string{
		"七征长篇":      "七征",
		"七征对话类征文长篇": "七征",
		"十征对话小说":    "十征",
		"十一征长篇":     "十一征",
		"2025春季征文":  "2025春季征文",
		"冬季征文":      "冬季征文",
	}
	for raw, want := range cases {
		if got := ContestEventName(raw); got != want {
			t.Fatalf("ContestEventName(%q) = %q, want %q", raw, got, want)
		}
	}
}

func TestContestGroups(t *testing.T) {
	st := openTestStore(t)
	groups, err := st.ContestGroups(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	byName := map[string]ContestGroup{}
	for _, g := range groups {
		byName[g.Name] = g
	}
	// 七征 merges the 长篇 and 对话类 divisions (the 对话类 spelling is the
	// one the old fixed-suffix matcher missed).
	z := byName["七征"]
	if z.Count != 2 || z.Series != "x" {
		t.Fatalf("七征 = %+v", z)
	}
	if z.Forms["long"] != 1 || z.Forms["dialogue"] != 1 {
		t.Fatalf("七征 forms = %v", z.Forms)
	}
	if len(z.Tracks) != 2 {
		t.Fatalf("七征 tracks = %v", z.Tracks)
	}
	// metadata joins: 十三征 carries user-verified official dates.
	if g := byName["十三征"]; g.Start == nil || *g.Start != "2025-05-04" ||
		g.End == nil || *g.End != "2025-10-07" || g.Note == nil {
		t.Fatalf("十三征 meta = %+v", g)
	}
	// spring section is recognized; section order follows the archive
	// tabs (spring first — user decision 2026-11-22).
	if g := byName["2025春季征文"]; g.Series != "spring" {
		t.Fatalf("春季 series = %q", g.Series)
	}
	if groups[0].Series != "spring" {
		t.Fatalf("first group = %+v, want spring section first", groups[0])
	}
	// other-series events carry home-tab lanes (dialogue/ip; empty =
	// theme, stays in the list's 其他 tab).
	if g := byName["崩坏3征文"]; g.Lane != "ip" {
		t.Fatalf("崩坏3 lane = %q, want ip", g.Lane)
	}
	// within-section launch-year ascending: 七征 (2019) before 十三征 (2025).
	xIdx := map[string]int{}
	for i, g := range groups {
		if g.Series == "x" {
			xIdx[g.Name] = i
		}
	}
	if xIdx["七征"] >= xIdx["十三征"] {
		t.Fatalf("x order = %v, want 七征 before 十三征", xIdx)
	}
}

func TestContestLane(t *testing.T) {
	cases := map[string]string{
		"点鸭秋色回忆征文活动": "dialogue",
		"对话小说春节征文":     "dialogue",
		"征文大赛对话小说组":   "dialogue",
		"春节征文分支对话":     "dialogue",
		"崩坏3征文":           "ip",
		"少女前线征文":         "ip",
		"失业魔王同人征文":     "ip",
		// edition-level override: dialogue contest despite the IP title
		// (user-verified 2026-11-22).
		"星穹小说家征文": "dialogue",
		"玄幻征文":            "",
		"少年的无限幻想":       "",
		"冬季恋曲征文活动":     "",
		"七征长篇":            "", // lane is caller-gated to other-series
	}
	for in, want := range cases {
		if got := contestLane(in); got != want {
			t.Errorf("contestLane(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestContestOrdinal(t *testing.T) {
	cases := map[string]int{
		"冬季征文":      0,
		"第二届冬季征文": 2,
		"第三届冬季征文": 3,
		"十征长篇":      0,
	}
	for in, want := range cases {
		if got := contestOrdinal(in); got != want {
			t.Errorf("contestOrdinal(%q) = %d, want %d", in, got, want)
		}
	}
}

func TestContestBooks(t *testing.T) {
	st := openTestStore(t)
	// per-form window: 七征 has one long + one dialogue book, both are the
	// head of their form, and fav_pctl orders them 3001 → 3002.
	items, err := st.ContestBooks(context.Background(), "七征", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 3001 || items[1].NID != 3002 {
		t.Fatalf("items = %+v", items)
	}
	// clicks must ride along as a display field (user report 2026-11-22:
	// the archive rows rendered "点击 0" because the SELECT omitted the
	// column). testseed pins clicks at 1000 for every book.
	if items[0].Clicks == nil || *items[0].Clicks != 1000 {
		t.Fatalf("items[0].Clicks = %v, want 1000", items[0].Clicks)
	}
	// window cap: 崩坏3征文 has two ip_collab books (pctl .8 > .5);
	// per=1 keeps only the head of the form.
	items, err = st.ContestBooks(context.Background(), "崩坏3征文", 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 1006 {
		t.Fatalf("items = %+v", items)
	}
	// NULL fav_pctl sorts last but is still returned when alone.
	items, err = st.ContestBooks(context.Background(), "十三征", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 3004 {
		t.Fatalf("items = %+v", items)
	}
	// non-N征 events match exactly.
	items, err = st.ContestBooks(context.Background(), "2025春季征文", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 3003 {
		t.Fatalf("items = %+v", items)
	}
}

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
	// spring section is recognized; x section sorts first.
	if g := byName["2025春季征文"]; g.Series != "spring" {
		t.Fatalf("春季 series = %q", g.Series)
	}
	if groups[0].Series != "x" {
		t.Fatalf("first group = %+v, want x section first", groups[0])
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

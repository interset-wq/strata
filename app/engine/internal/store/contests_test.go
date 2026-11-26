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
	// within-section launch-year DESC: 十三征 (2025) before 七征 (2019).
	xIdx := map[string]int{}
	for i, g := range groups {
		if g.Series == "x" {
			xIdx[g.Name] = i
		}
	}
	if xIdx["十三征"] >= xIdx["七征"] {
		t.Fatalf("x order = %v, want 十三征 before 七征 (newest first)", xIdx)
	}
}

func TestEarlyRosterTags(t *testing.T) {
	// The early static pages do carry rosters: their JS writes the tagIds
	// into list.html / showSysTagDetail. A missing entry here is what makes
	// the UI degrade to the in-library subset (docs/contest-roster-harvest §2.1).
	want := map[string][]RosterTag{
		"四征": {{Division: "长篇", Tag: 275}, {Division: "中篇", Tag: 276},
			{Division: "短篇", Tag: 277}},
		"五征": {{Division: "长篇", Tag: 377}, {Division: "中篇", Tag: 378},
			{Division: "短篇", Tag: 379}, {Division: "对话小说", Tag: 380}},
		"六征": {{Division: "长篇", Tag: 383}, {Division: "中篇", Tag: 384},
			{Division: "短篇", Tag: 385}, {Division: "对话小说", Tag: 386}},
	}
	for event, tags := range want {
		got := RosterTagsFor(event)
		if len(got) != len(tags) {
			t.Fatalf("%s tags = %+v, want %+v", event, got, tags)
		}
		for i, w := range tags {
			if got[i].Division != w.Division || got[i].Tag != w.Tag ||
				got[i].Gen != RosterGenOld {
				t.Fatalf("%s tag[%d] = %+v, want %+v", event, i, got[i], w)
			}
		}
	}
	// 一/二/三征 never had participation tagIds, but upstream publishes
	// their winner lists as tagIds 635-649 (contest-achieve capture
	// 2026-11-24). They ride the same fetch path as award tracks — labelled
	// 获奖名单 by the caller, never counted into roster_total.
	awards := RosterTagsFor("三征")
	if len(awards) != 9 || awards[0].Division != "长篇金奖" ||
		awards[0].Tag != 641 || awards[0].Kind != LedgerKindAward {
		t.Fatalf("三征 award tags = %+v", awards)
	}
	if tr, ok := RosterTagFor("一征", "金奖"); !ok || tr.Tag != 635 ||
		tr.Kind != LedgerKindAward {
		t.Fatalf("一征/金奖 = %+v, %v", tr, ok)
	}
	if got := LedgerListKind("三征"); got != LedgerKindAward {
		t.Fatalf("三征 list kind = %q", got)
	}
	if got := LedgerListKind("七征"); got != LedgerKindRoster {
		t.Fatalf("七征 list kind = %q", got)
	}
	if got := LedgerListKind("没有这届"); got != "" {
		t.Fatalf("unknown event list kind = %q", got)
	}
	// The archive's per-track rows carry the award caliber per row: the
	// winner count, with the tag-list length not posing as one.
	divs := LedgerDivisions("三征")
	if len(divs) != 9 || divs[2].Name != "长篇铜奖" ||
		divs[2].Kind != LedgerKindAward || divs[2].Awards == nil ||
		*divs[2].Awards != 3 {
		t.Fatalf("三征 divisions = %+v", divs)
	}
	// The ledger is now complete for the seed's 99 contest labels: the
	// once-missing divisions and IP/theme events are all mapped.
	more := map[string][]struct {
		div string
		tag int
	}{
		"八征":         {{"长篇", 418}, {"中篇", 419}, {"短篇", 420}},
		"九征":         {{"长篇", 457}, {"中篇", 458}, {"短篇", 459}, {"对话小说", 462}},
		"十征":         {{"长篇", 475}, {"中篇", 476}, {"短篇", 477}, {"对话小说", 479}},
		"龙之谷征文":      {{"", 413}},
		"失业魔王同人征文":   {{"", 468}},
		"对话小说青春幻想征文": {{"", 478}},
		"春节征文短篇":     {{"", 623}},
	}
	for event, tags := range more {
		got := RosterTagsFor(event)
		if len(got) != len(tags) {
			t.Fatalf("%s tags = %+v, want %d", event, got, len(tags))
		}
		for i, w := range tags {
			if got[i].Division != w.div || got[i].Tag != w.tag {
				t.Fatalf("%s tag[%d] = %+v, want %s/%d", event, i, got[i], w.div, w.tag)
			}
		}
	}
}

func TestContestLabelNormalization(t *testing.T) {
	// The label defects the ledger round fixed (2026-11-26): the old numeral
	// list stopped at 十三, so 十四征-长篇 never merged into 十四征; and four
	// events carry two seed spellings, which rendered as two archive rows with
	// the official scale on only one of them.
	cases := map[string]string{
		"十四征-长篇":      "十四征",
		"十四征-短篇":      "十四征",
		"七征-赛道2":      "七征",
		"十征对话小说":      "十征",
		"十五征-长篇":      "十五征", // structural: a future edition needs no code change
		"2026春征":      "2026春季征文",
		"2024主题短篇":    "2024主题短篇征文",
		"少年-二次元创想·短篇": "少年创想短篇",
	}
	for raw, want := range cases {
		if got := ContestEventName(raw); got != want {
			t.Errorf("ContestEventName(%q) = %q, want %q", raw, got, want)
		}
		if got := NormalizeContest(raw); got != want {
			t.Errorf("NormalizeContest(%q) = %q, want %q", raw, got, want)
		}
	}
	// Every alias row of the ledger resolves — including the target whose name
	// carries full-width quotes.
	for alias, canonical := range ledger.Aliases {
		if got := ContestEventName(alias); got != canonical {
			t.Errorf("alias %q resolved to %q, want %q", alias, got, canonical)
		}
	}
}

func TestContestLedgerOfficialScale(t *testing.T) {
	st := openTestStore(t)
	groups, err := st.ContestGroups(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	byName := map[string]ContestGroup{}
	for _, g := range groups {
		byName[g.Name] = g
	}
	// 十三征: three official tracks (3407+767+623 = 4,797 entries against 4
	// in-library books), 25 official winners, and the 公布日 that the old table
	// only carried as prose in note.
	g := byName["十三征"]
	if g.RosterTotal == nil || *g.RosterTotal != 4797 {
		t.Fatalf("十三征 roster_total = %v, want 4797", g.RosterTotal)
	}
	if len(g.Divisions) != 3 || g.Divisions[0].Name != "长篇" ||
		g.Divisions[0].Roster == nil || *g.Divisions[0].Roster != 3407 {
		t.Fatalf("十三征 divisions = %+v", g.Divisions)
	}
	if g.AwardTotal == nil || *g.AwardTotal != 25 {
		t.Fatalf("十三征 award_total = %v, want 25", g.AwardTotal)
	}
	if g.Result == nil || *g.Result != "2026-01-16" {
		t.Fatalf("十三征 result = %v", g.Result)
	}
	// 十四征 is in the ledger now (the round that filled it had no row at all).
	if e, ok := LedgerEventFor("十四征"); !ok || e.RosterTotal == nil ||
		*e.RosterTotal != 4064 {
		t.Fatalf("十四征 ledger = %+v", e)
	}
	// An event whose tracks have no official list has no official scale: nil,
	// never a zero the UI would read as 「这届只有 0 本」.
	if e, ok := LedgerEventFor("三征"); ok && e.RosterTotal != nil {
		t.Fatalf("三征 roster_total = %v, want nil (award tiers only)", *e.RosterTotal)
	}
}

func TestContestLedgerShape(t *testing.T) {
	// The embedded table is the app's only contest fact source, so it has to
	// be self-consistent: known kinds, a production tagId and endpoint
	// generation per row, and an event total that is either complete or absent.
	if len(ledger.Events) < 70 {
		t.Fatalf("ledger events = %d, want the full seed label map", len(ledger.Events))
	}
	for _, e := range ledger.Events {
		if len(e.Tracks) == 0 {
			t.Fatalf("event %s has no tracks", e.Name)
		}
		var sum int
		var roster int
		for _, tr := range e.Tracks {
			switch tr.Kind {
			case LedgerKindRoster:
				roster++
				sum += deref(tr.Roster)
			case LedgerKindAward:
			default:
				t.Fatalf("%s/%s kind = %q", e.Name, tr.Division, tr.Kind)
			}
			if tr.Tag <= 0 {
				t.Fatalf("%s/%s tag = %d", e.Name, tr.Division, tr.Tag)
			}
			if tr.Gen != RosterGenNew && tr.Gen != RosterGenOld {
				t.Fatalf("%s/%s gen = %q", e.Name, tr.Division, tr.Gen)
			}
			if tr.Kind == LedgerKindRoster && tr.Roster == nil {
				t.Fatalf("%s/%s has no official count: the total must stay nil",
					e.Name, tr.Division)
			}
		}
		if e.RosterTotal != nil {
			if roster == 0 || *e.RosterTotal != sum {
				t.Fatalf("%s roster_total = %v, tracks sum = %d", e.Name, *e.RosterTotal, sum)
			}
		} else if roster > 0 {
			t.Fatalf("%s has %d roster tracks but no roster_total", e.Name, roster)
		}
	}
}

// TestRosterTagForDisplayAlias: the archive/roster pages round-trip
// LedgerDivisions' labels back into /roster?division=…, so the blank
// single-track division's display name 「全部」 must resolve to its tagId
// (an unresolved row would 400 the whole page).
func TestRosterTagForDisplayAlias(t *testing.T) {
	tr, ok := RosterTagFor("2025春季征文", "全部")
	if !ok || tr.Division != "" {
		t.Fatalf("2025春季征文/全部 = %+v, %v", tr, ok)
	}
	if _, ok := RosterTagFor("2025春季征文", ""); !ok {
		t.Fatal("blank division must keep resolving (pre-rewrite clients)")
	}
	if _, ok := RosterTagFor("七征", "全部"); ok {
		t.Fatal("multi-track event must not resolve 全部")
	}
}

func TestContestLane(t *testing.T) {
	cases := map[string]string{
		"点鸭秋色回忆征文活动": "dialogue",
		"对话小说春节征文":   "dialogue",
		"征文大赛对话小说组":  "dialogue",
		"春节征文分支对话":   "dialogue",
		"崩坏3征文":      "ip",
		"少女前线征文":     "ip",
		"失业魔王同人征文":   "ip",
		// edition-level override: dialogue contest despite the IP title
		// (user-verified 2026-11-22).
		"星穹小说家征文":  "dialogue",
		"玄幻征文":     "",
		"少年的无限幻想":  "",
		"冬季恋曲征文活动": "",
		"七征长篇":     "", // lane is caller-gated to other-series
	}
	for in, want := range cases {
		if got := contestLane(in); got != want {
			t.Errorf("contestLane(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestContestOrdinal(t *testing.T) {
	cases := map[string]int{
		"冬季征文":    0,
		"第二届冬季征文": 2,
		"第三届冬季征文": 3,
		"十征长篇":    0,
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
	// head of their form, and favs orders them 3001 → 3002.
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
	// window cap: 崩坏3征文 has two ip_collab books (favs 700 > 100);
	// per=1 keeps only the head of the form.
	items, err = st.ContestBooks(context.Background(), "崩坏3征文", 1)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 1006 {
		t.Fatalf("items = %+v", items)
	}
	// 十三征 has a single book; it is returned when alone.
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

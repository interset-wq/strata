package store

// RosterTag is one verified (event, division) -> tagId mapping for the
// contest roster API. Source of truth: docs/contest-roster-harvest.md §2
// (the single tagId authority). Tags are assigned per edition and never
// reused across editions (user ruling), so the table grows by a batch per
// new edition; an event without an entry here degrades to the in-library
// view (docs/contest-display-in-app.md 降级表). Numbers are production
// `pages`-host values (sandbox/test run different pools).
type RosterTag struct {
	Event     string // event-level name (ContestEventName form, matches seed)
	Division  string // roster division label; "" = single-track event
	Tag       int    // production tagId
	Gen       string // RosterGenNew or RosterGenOld
	PageStart int    // first page index: old `pi` is 0-based, new verified page=1
}

const (
	// RosterGenNew is the 2023+ SPA endpoint
	// /api/essay/getNovels?tagIds=&page=&size= (size <= 500).
	RosterGenNew = "new"
	// RosterGenOld is the 2018-2022 H5 endpoint
	// Common.ashx?op=getNovelsByTag&tagId=&ps=&pi= (ps <= 200, pi 0-based).
	RosterGenOld = "old"
)

// rosterTags — verified tag map. Mapping verification (2026-11-21):
//   - 七征 408-412 and 十二征 702-704: join-verified against seed contest
//     strings (probe roster CSV × seed.books, 47-97% in-library match per
//     division);
//   - 十一征 653-655 and 十三征 752-754: inferred from the ascending
//     长篇/中篇/短 convention, verified 2/2 on the two triplets above;
//   - 冬季征文 (bare) = 一征 2018: all 104 seed books est_year 2018;
//   - 724 (点鸭秋色回忆): size boundary trap — size=500 returns empty while
//     size<=8 works; the engine's size-downgrade retry covers it
//     (docs/contest-roster-harvest.md §4).
var rosterTags = []RosterTag{
	// X征（夏）— 早期静态页内嵌 getNovelsByTag（2026-11-22 页面实证）
	// 四征 list.html 的 list.js 写死 275/276/277；五征 list.html 的
	// list.js 写死 377–380；六征活动页 showSysTagDetail 写死 383–386。
	// 三组均走旧 H5 端点，pi 0 基；源码 docs/contest-roster-harvest.md §2.1。
	{Event: "四征", Division: "长篇", Tag: 275, Gen: RosterGenOld, PageStart: 0},
	{Event: "四征", Division: "中篇", Tag: 276, Gen: RosterGenOld, PageStart: 0},
	{Event: "四征", Division: "短篇", Tag: 277, Gen: RosterGenOld, PageStart: 0},
	{Event: "五征", Division: "长篇", Tag: 377, Gen: RosterGenOld, PageStart: 0},
	{Event: "五征", Division: "中篇", Tag: 378, Gen: RosterGenOld, PageStart: 0},
	{Event: "五征", Division: "短篇", Tag: 379, Gen: RosterGenOld, PageStart: 0},
	{Event: "五征", Division: "对话小说", Tag: 380, Gen: RosterGenOld, PageStart: 0},
	{Event: "六征", Division: "长篇", Tag: 383, Gen: RosterGenOld, PageStart: 0},
	{Event: "六征", Division: "中篇", Tag: 384, Gen: RosterGenOld, PageStart: 0},
	{Event: "六征", Division: "短篇", Tag: 385, Gen: RosterGenOld, PageStart: 0},
	{Event: "六征", Division: "对话小说", Tag: 386, Gen: RosterGenOld, PageStart: 0},
	// X征（夏）— 旧 H5 页
	{Event: "七征", Division: "长篇", Tag: 408, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "中篇", Tag: 409, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "短篇", Tag: 410, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "对话类征文长篇", Tag: 411, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "对话类征文短篇", Tag: 412, Gen: RosterGenOld, PageStart: 0},
	{Event: "八征", Division: "", Tag: 418, Gen: RosterGenOld, PageStart: 0},
	// 独立 IP 联动 — tag 278 首本即本地同标注，49/49 拉取中 31/31 本地命中
	{Event: "楚楚动仁同人征文", Division: "", Tag: 278, Gen: RosterGenOld, PageStart: 0},
	// 冬季征文 — 一~五征（旧 H5 页）
	{Event: "冬季征文", Division: "", Tag: 381, Gen: RosterGenOld, PageStart: 0},
	{Event: "第二届冬季征文", Division: "", Tag: 406, Gen: RosterGenOld, PageStart: 0},
	{Event: "第三届冬季征文", Division: "", Tag: 415, Gen: RosterGenOld, PageStart: 0},
	{Event: "第四届冬季征文", Division: "", Tag: 454, Gen: RosterGenOld, PageStart: 0},
	{Event: "第五届冬季征文", Division: "", Tag: 466, Gen: RosterGenOld, PageStart: 0},
	// X征（夏）— 新 SPA 页
	{Event: "十一征", Division: "长篇", Tag: 653, Gen: RosterGenNew, PageStart: 1},
	{Event: "十一征", Division: "中篇", Tag: 654, Gen: RosterGenNew, PageStart: 1},
	{Event: "十一征", Division: "短篇", Tag: 655, Gen: RosterGenNew, PageStart: 1},
	{Event: "十二征", Division: "长篇", Tag: 702, Gen: RosterGenNew, PageStart: 1},
	{Event: "十二征", Division: "中篇", Tag: 703, Gen: RosterGenNew, PageStart: 1},
	{Event: "十二征", Division: "短篇", Tag: 704, Gen: RosterGenNew, PageStart: 1},
	{Event: "十三征", Division: "长篇", Tag: 752, Gen: RosterGenNew, PageStart: 1},
	{Event: "十三征", Division: "中篇", Tag: 753, Gen: RosterGenNew, PageStart: 1},
	{Event: "十三征", Division: "短篇", Tag: 754, Gen: RosterGenNew, PageStart: 1},
	// 冬季征文 — 六~九征（新 SPA / UUID 页）
	{Event: "第六届冬季征文", Division: "", Tag: 485, Gen: RosterGenNew, PageStart: 1},
	{Event: "第七届冬季征文", Division: "", Tag: 692, Gen: RosterGenNew, PageStart: 1},
	{Event: "第八届冬季征文", Division: "", Tag: 726, Gen: RosterGenNew, PageStart: 1},
	{Event: "第九届冬季征文", Division: "", Tag: 774, Gen: RosterGenNew, PageStart: 1},
	// 春季征文（新 SPA / UUID 页；2026 届尚无种子书，预留随种子发版生效）
	{Event: "2024春季征文", Division: "", Tag: 699, Gen: RosterGenNew, PageStart: 1},
	{Event: "2025春季征文", Division: "", Tag: 746, Gen: RosterGenNew, PageStart: 1},
	{Event: "2026春季征文", Division: "", Tag: 789, Gen: RosterGenNew, PageStart: 1},
	// 秋季征文（UUID 页）
	{Event: "2024秋季征文", Division: "", Tag: 725, Gen: RosterGenNew, PageStart: 1},
	{Event: "2025秋季征文", Division: "", Tag: 772, Gen: RosterGenNew, PageStart: 1},
	// 对话线（试号确认 + 用户书名确认，非页面实证）
	{Event: "点鸭秋色回忆征文活动", Division: "", Tag: 724, Gen: RosterGenNew, PageStart: 1},
}

// RosterTagsFor returns the verified roster tags for one event-level name
// in table order (the official division order for display). Nil when the
// event has no verified tags (degrade to the in-library view).
func RosterTagsFor(event string) []RosterTag {
	out := []RosterTag{}
	for _, t := range rosterTags {
		if t.Event == event {
			out = append(out, t)
		}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

// RosterTagFor resolves one (event, division) pair; single-track events use
// division "".
func RosterTagFor(event, division string) (RosterTag, bool) {
	for _, t := range rosterTags {
		if t.Event == event && t.Division == division {
			return t, true
		}
	}
	return RosterTag{}, false
}

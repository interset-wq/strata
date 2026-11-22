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

// rosterTags — verified tags from docs/contest-roster-harvest.md §2. Every
// row is either page-verified (JS / data-tagid) or joined 100% against the
// local contest label by full nid intersection. Gen follows the official
// page's own endpoint (old = pi 0-based, new = page 1-based); both endpoint
// generations currently serve every tag, but their ordering differs, so a
// tag must keep its page's Gen/PageStart. Notable size traps (469/622/624/
// 676/724) are covered by the handler's size-downgrade retry.
var rosterTags = []RosterTag{
	// X征 — 早期静态页内嵌 JS（275–277 / 377–380 / 383–386）
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
	// X征 — 旧 H5 页（七/八/九征）
	{Event: "七征", Division: "长篇", Tag: 408, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "中篇", Tag: 409, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "短篇", Tag: 410, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "对话类征文长篇", Tag: 411, Gen: RosterGenOld, PageStart: 0},
	{Event: "七征", Division: "对话类征文短篇", Tag: 412, Gen: RosterGenOld, PageStart: 0},
	{Event: "八征", Division: "长篇", Tag: 418, Gen: RosterGenOld, PageStart: 0},
	{Event: "八征", Division: "中篇", Tag: 419, Gen: RosterGenOld, PageStart: 0},
	{Event: "八征", Division: "短篇", Tag: 420, Gen: RosterGenOld, PageStart: 0},
	{Event: "九征", Division: "长篇", Tag: 457, Gen: RosterGenOld, PageStart: 0},
	{Event: "九征", Division: "中篇", Tag: 458, Gen: RosterGenOld, PageStart: 0},
	{Event: "九征", Division: "短篇", Tag: 459, Gen: RosterGenOld, PageStart: 0},
	{Event: "九征", Division: "对话小说", Tag: 462, Gen: RosterGenOld, PageStart: 0},
	// X征 — 新 SPA 页（十征起）
	{Event: "十征", Division: "长篇", Tag: 475, Gen: RosterGenNew, PageStart: 1},
	{Event: "十征", Division: "中篇", Tag: 476, Gen: RosterGenNew, PageStart: 1},
	{Event: "十征", Division: "短篇", Tag: 477, Gen: RosterGenNew, PageStart: 1},
	{Event: "十征", Division: "对话小说", Tag: 479, Gen: RosterGenNew, PageStart: 1},
	{Event: "十一征", Division: "长篇", Tag: 653, Gen: RosterGenNew, PageStart: 1},
	{Event: "十一征", Division: "中篇", Tag: 654, Gen: RosterGenNew, PageStart: 1},
	{Event: "十一征", Division: "短篇", Tag: 655, Gen: RosterGenNew, PageStart: 1},
	{Event: "十二征", Division: "长篇", Tag: 702, Gen: RosterGenNew, PageStart: 1},
	{Event: "十二征", Division: "中篇", Tag: 703, Gen: RosterGenNew, PageStart: 1},
	{Event: "十二征", Division: "短篇", Tag: 704, Gen: RosterGenNew, PageStart: 1},
	{Event: "十三征", Division: "长篇", Tag: 752, Gen: RosterGenNew, PageStart: 1},
	{Event: "十三征", Division: "中篇", Tag: 753, Gen: RosterGenNew, PageStart: 1},
	{Event: "十三征", Division: "短篇", Tag: 754, Gen: RosterGenNew, PageStart: 1},
	// 十四征（2026，种子尚未覆盖）：长/短两轨，中篇赛道取消
	{Event: "十四征", Division: "长篇", Tag: 793, Gen: RosterGenNew, PageStart: 1},
	{Event: "十四征", Division: "短篇", Tag: 794, Gen: RosterGenNew, PageStart: 1},
	// 冬季征文（一征 = 裸「冬季征文」）
	{Event: "冬季征文", Division: "", Tag: 381, Gen: RosterGenOld, PageStart: 0},
	{Event: "第二届冬季征文", Division: "", Tag: 406, Gen: RosterGenOld, PageStart: 0},
	{Event: "第三届冬季征文", Division: "", Tag: 415, Gen: RosterGenOld, PageStart: 0},
	{Event: "第四届冬季征文", Division: "", Tag: 454, Gen: RosterGenOld, PageStart: 0},
	{Event: "第五届冬季征文", Division: "", Tag: 466, Gen: RosterGenOld, PageStart: 0},
	{Event: "第六届冬季征文", Division: "", Tag: 485, Gen: RosterGenNew, PageStart: 1},
	{Event: "第七届冬季征文", Division: "", Tag: 692, Gen: RosterGenNew, PageStart: 1},
	{Event: "第八届冬季征文", Division: "", Tag: 726, Gen: RosterGenNew, PageStart: 1},
	{Event: "第九届冬季征文", Division: "", Tag: 774, Gen: RosterGenNew, PageStart: 1},
	// 春征
	{Event: "2022春季征文", Division: "", Tag: 473, Gen: RosterGenNew, PageStart: 1},
	{Event: "2023春季征文", Division: "", Tag: 632, Gen: RosterGenNew, PageStart: 1},
	{Event: "2024春季征文", Division: "", Tag: 699, Gen: RosterGenNew, PageStart: 1},
	{Event: "2025春季征文", Division: "", Tag: 746, Gen: RosterGenNew, PageStart: 1},
	{Event: "2026春季征文", Division: "", Tag: 789, Gen: RosterGenNew, PageStart: 1},
	// 秋征 / 少年主题系列
	{Event: "东方世界秋季征文", Division: "", Tag: 464, Gen: RosterGenNew, PageStart: 1},
	{Event: "异世大陆秋季征文", Division: "", Tag: 465, Gen: RosterGenNew, PageStart: 1},
	{Event: "少年的奇幻冒险", Division: "", Tag: 480, Gen: RosterGenNew, PageStart: 1},
	{Event: "少年的无限幻想", Division: "", Tag: 481, Gen: RosterGenNew, PageStart: 1},
	{Event: "少年的幻想之旅", Division: "", Tag: 660, Gen: RosterGenNew, PageStart: 1},
	{Event: "少年的奇迹历险", Division: "", Tag: 669, Gen: RosterGenNew, PageStart: 1},
	{Event: "“少年的幻想校园”主题征文", Division: "", Tag: 722, Gen: RosterGenNew, PageStart: 1},
	{Event: "少年创想长篇", Division: "", Tag: 747, Gen: RosterGenNew, PageStart: 1},
	{Event: "少年创想短篇", Division: "", Tag: 748, Gen: RosterGenNew, PageStart: 1},
	{Event: "2024秋季征文", Division: "", Tag: 725, Gen: RosterGenNew, PageStart: 1},
	{Event: "2025秋季征文", Division: "", Tag: 772, Gen: RosterGenNew, PageStart: 1},
	{Event: "2026秋季征文", Division: "", Tag: 803, Gen: RosterGenNew, PageStart: 1},
	// 独立赛事：IP / 题材 / 对话节日（100% 本地交集实证）
	{Event: "楚楚动仁同人征文", Division: "", Tag: 278, Gen: RosterGenOld, PageStart: 0},
	{Event: "少女前线征文", Division: "", Tag: 404, Gen: RosterGenNew, PageStart: 1},
	{Event: "崩坏3征文", Division: "", Tag: 405, Gen: RosterGenNew, PageStart: 1},
	{Event: "龙之谷征文", Division: "", Tag: 413, Gen: RosterGenOld, PageStart: 0},
	{Event: "校园恋爱征文", Division: "", Tag: 382, Gen: RosterGenNew, PageStart: 1},
	{Event: "校园都市征文", Division: "", Tag: 414, Gen: RosterGenNew, PageStart: 1},
	{Event: "幻想小说征文", Division: "", Tag: 417, Gen: RosterGenNew, PageStart: 1},
	{Event: "秋季恋爱征文", Division: "", Tag: 453, Gen: RosterGenNew, PageStart: 1},
	{Event: "玄幻征文", Division: "", Tag: 456, Gen: RosterGenNew, PageStart: 1},
	{Event: "穿越主题征文", Division: "", Tag: 463, Gen: RosterGenNew, PageStart: 1},
	{Event: "战斗主题征文", Division: "", Tag: 467, Gen: RosterGenNew, PageStart: 1},
	{Event: "失业魔王同人征文", Division: "", Tag: 468, Gen: RosterGenOld, PageStart: 0},
	{Event: "英雄再临同人征文", Division: "", Tag: 469, Gen: RosterGenNew, PageStart: 1},
	{Event: "奇幻世界主题征文", Division: "", Tag: 755, Gen: RosterGenNew, PageStart: 1},
	{Event: "对话小说春节征文", Division: "", Tag: 471, Gen: RosterGenNew, PageStart: 1},
	{Event: "对话小说情人节征文", Division: "", Tag: 472, Gen: RosterGenNew, PageStart: 1},
	{Event: "对话小说开学季征文", Division: "", Tag: 474, Gen: RosterGenNew, PageStart: 1},
	{Event: "对话小说青春幻想征文", Division: "", Tag: 478, Gen: RosterGenNew, PageStart: 1},
	{Event: "分支对话小说征文", Division: "", Tag: 482, Gen: RosterGenNew, PageStart: 1},
	{Event: "对话小说恋爱主题征文", Division: "", Tag: 484, Gen: RosterGenNew, PageStart: 1},
	{Event: "春节征文长篇", Division: "", Tag: 622, Gen: RosterGenNew, PageStart: 1},
	{Event: "春节征文短篇", Division: "", Tag: 623, Gen: RosterGenNew, PageStart: 1},
	{Event: "春节征文分支对话", Division: "", Tag: 624, Gen: RosterGenNew, PageStart: 1},
	{Event: "星穹小说家征文", Division: "", Tag: 633, Gen: RosterGenNew, PageStart: 1},
	{Event: "“超新星杯”短篇大赛", Division: "", Tag: 634, Gen: RosterGenNew, PageStart: 1},
	{Event: "征文大赛对话小说组", Division: "", Tag: 659, Gen: RosterGenNew, PageStart: 1},
	{Event: "怪谈异闻主题征文长篇", Division: "", Tag: 675, Gen: RosterGenNew, PageStart: 1},
	{Event: "怪谈异闻主题征文短篇", Division: "", Tag: 676, Gen: RosterGenNew, PageStart: 1},
	{Event: "冬季恋曲征文活动", Division: "", Tag: 691, Gen: RosterGenNew, PageStart: 1},
	{Event: "2024主题短篇征文", Division: "", Tag: 693, Gen: RosterGenNew, PageStart: 1},
	{Event: "2024年对话小说春节征文", Division: "", Tag: 698, Gen: RosterGenNew, PageStart: 1},
	{Event: "对话小说梦想季节征文活动", Division: "", Tag: 700, Gen: RosterGenNew, PageStart: 1},
	{Event: "2024夏季征文大赛对话小说组", Division: "", Tag: 701, Gen: RosterGenNew, PageStart: 1},
	{Event: "2025年对话小说新年征文活动", Division: "", Tag: 729, Gen: RosterGenNew, PageStart: 1},
	{Event: "点鸭秋色回忆征文活动", Division: "", Tag: 724, Gen: RosterGenNew, PageStart: 1},
	{Event: "点鸭秋之偶像季征文活动", Division: "", Tag: 661, Gen: RosterGenNew, PageStart: 1},
	// 种子标注异常：这两组 774xxx 书实际落在十四征长/短清单里
	// （793 拉 11 本「征文大赛长篇」、794 拉 4 本「征文大赛短篇」）。
	// 保留别名，避免这几个档案页显示成「无清单」。
	{Event: "征文大赛长篇", Division: "", Tag: 793, Gen: RosterGenNew, PageStart: 1},
	{Event: "征文大赛短篇", Division: "", Tag: 794, Gen: RosterGenNew, PageStart: 1},
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

package store

// Contest event metadata: official launch/announced dates, user-verified
// per edition. Source of truth: analysis/references/contest-editions.md
// (2026-11-16, verified edition by edition against official pages / the
// official App). Re-verify against that file when adding an edition; it is
// the single source of truth, this table is the app's built-in export.
//
// Year = launch year. Start/End = official dates ("", when unknown = show
// edition/year only, never fabricate). Note = later milestones (公布日).
// Official = the official activity-page URL (h5/mobile form), page-verified
// per edition in docs/contest-roster-harvest.md §2 (2026-11-22); "" = no
// verified URL (retired pages / never captured) — the archive page hides
// its jump entry in that case, it never fabricates a URL.
type ContestMeta struct {
	Year     int
	Start    string
	End      string
	Note     string
	Official string
}

var contestMeta = map[string]ContestMeta{
	// X征 series (四征 = first in-dataset edition)
	"四征": {Year: 2016, Start: "2016-07-08", End: "2016-10-06",
		Official: "https://book.sfacg.com/zw2016/rule.html"}, // only official rule-page exact dates
	"五征": {Year: 2017, Official: "https://book.sfacg.com/zw2017/"},
	"六征": {Year: 2018, Official: "https://pages.sfacg.com/h5/act/zw2018/"},
	"七征": {Year: 2019, Official: "https://pages.sfacg.com/h5/act/zw2019/"},
	"八征": {Year: 2020, Official: "https://pages.sfacg.com/h5/act/zw2020/"},
	"九征": {Year: 2021, Official: "https://pages.sfacg.com/h5/act/zw2021/"},
	"十征": {Year: 2022, Official: "https://pages.sfacg.com/h5/act/zw2022/"},
	"十一征": {Year: 2023, Official: "https://pages.sfacg.com/h5/act/zw20230504/pc"},
	"十二征": {Year: 2024, Start: "2024-05-04",
		Official: "https://pages.sfacg.com/h5/act/zw20240504/pc"}, // self-proven by page id zw20240504
	"十三征": {Year: 2025, Start: "2025-05-04", End: "2025-10-07",
		Note: "终审公布 2026-01-16",
		Official: "https://pages.sfacg.com/h5/act/zw20250504/pc"},
	// 冬季征文 (first edition carries no ordinal in the seed string)
	"冬季征文": {Year: 2018,
		Official: "https://pages.sfacg.com/h5/act/djzw2018/"},
	"第二届冬季征文": {Year: 2019,
		Official: "https://pages.sfacg.com/h5/act/djzw2019/"},
	"第三届冬季征文": {Year: 2019,
		Official: "https://pages.sfacg.com/h5/act/djzw2020/"}, // launched 2019-12
	"第四届冬季征文": {Year: 2020,
		Official: "https://pages.sfacg.com/pc/act/djzw2021/"}, // only the pc path is verified
	"第五届冬季征文": {Year: 2021,
		Official: "https://pages.sfacg.com/h5/act/djzw2022/"},
	"第六届冬季征文": {Year: 2022, Start: "2022-12-05",
		Official: "https://pages.sfacg.com/h5/act/zw20221205/"}, // page id zw20221205
	"第七届冬季征文": {Year: 2023, Start: "2023-12-04",
		Official: "https://pages.sfacg.com/h5/act/zw20231204/"}, // page id zw20231204
	"第八届冬季征文": {Year: 2024, Start: "2024-12-06", End: "2025-02-28",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_c49534b9-73b2-46c9-a33f-b8144b448662.html"},
	"第九届冬季征文": {Year: 2025, Start: "2025-12-05", End: "2026-03-06",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_373481c3-8fb0-4113-83fb-5058a816f828.html"},
	// 春/秋征
	"2022春季征文": {Year: 2022,
		Official: "https://pages.sfacg.com/h5/act/zw20220301/"},
	"2023春季征文": {Year: 2023,
		Official: "https://pages.sfacg.com/h5/act/zw20230301/"},
	"2024春季征文": {Year: 2024, Start: "2024-03-01",
		Official: "https://pages.sfacg.com/h5/act/zw20240301/"}, // page id zw20240301
	"2025春季征文": {Year: 2025, Start: "2025-03-01", End: "2025-05-03",
		Note: "公布 2025-07-11",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_d892261b-8719-4e3b-b01a-b84278b2996b.html"},
	"2026春季征文": {Year: 2026, Start: "2026-02-27", End: "2026-05-03",
		Note: "公布 2026-07-10",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_52f25c52-1de0-4608-90fc-293aac35a588.html"},
	"2024秋季征文": {Year: 2024, Start: "2024-09-30", End: "2024-12-05",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_0a10b388-bf92-410c-801a-59c91b853c3f.html"},
	"2025秋季征文": {Year: 2025, Start: "2025-09-30", End: "2025-12-04",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_d568a583-bde8-4f16-809a-8ab7097261be.html"},
	// IP collab / themed
	"崩坏3征文": {Year: 2019, Start: "2019-01-04", End: "2019-02-11",
		Note: "公示 2019-02-22"}, // no verified activity URL (harvest §2.8: 未取)
	"奇幻世界主题征文": {Year: 2025, Start: "2025-06-06", End: "2025-08-31",
		Official: "https://pages.sfacg.com/h5/act/zw/essayActivity_e5950dc7-7f12-4fca-8049-8fd2afd9c0eb.html"},
}

// ContestMetaFor returns the metadata for an event-level name. Exported for
// the roster endpoint's TTL rule (ended events cache 365d, active 24h).
func ContestMetaFor(name string) (ContestMeta, bool) {
	m, ok := contestMeta[name]
	return m, ok
}

package store

// Contest event metadata: official launch/announced dates, user-verified
// per edition. Source of truth: analysis/references/contest-editions.md
// (2026-11-16, verified edition by edition against official pages / the
// official App). Re-verify against that file when adding an edition; it is
// the single source of truth, this table is the app's built-in export.
//
// Year = launch year. Start/End = official dates ("", when unknown = show
// edition/year only, never fabricate). Note = later milestones (公布日).
type ContestMeta struct {
	Year  int
	Start string
	End   string
	Note  string
}

var contestMeta = map[string]ContestMeta{
	// X征 series (四征 = first in-dataset edition)
	"四征":  {Year: 2016, Start: "2016-07-08", End: "2016-10-06"}, // only official rule-page exact dates
	"五征":  {Year: 2017},
	"六征":  {Year: 2018},
	"七征":  {Year: 2019},
	"八征":  {Year: 2020},
	"九征":  {Year: 2021},
	"十征":  {Year: 2022},
	"十一征": {Year: 2023},
	"十二征": {Year: 2024, Start: "2024-05-04"}, // self-proven by page id zw20240504
	"十三征": {Year: 2025, Start: "2025-05-04", End: "2025-10-07",
		Note: "终审公布 2026-01-16"},
	// 冬季征文 (first edition carries no ordinal in the seed string)
	"冬季征文":    {Year: 2018},
	"第二届冬季征文": {Year: 2019},
	"第三届冬季征文": {Year: 2019}, // launched 2019-12
	"第四届冬季征文": {Year: 2020},
	"第五届冬季征文": {Year: 2021},
	"第六届冬季征文": {Year: 2022, Start: "2022-12-05"}, // page id zw20221205
	"第七届冬季征文": {Year: 2023, Start: "2023-12-04"}, // page id zw20231204
	"第八届冬季征文": {Year: 2024, Start: "2024-12-06", End: "2025-02-28"},
	"第九届冬季征文": {Year: 2025, Start: "2025-12-05", End: "2026-03-06"},
	// 春/秋征
	"2022春季征文": {Year: 2022},
	"2023春季征文": {Year: 2023},
	"2024春季征文": {Year: 2024, Start: "2024-03-01"}, // page id zw20240301
	"2025春季征文": {Year: 2025, Start: "2025-03-01", End: "2025-05-03",
		Note: "公布 2025-07-11"},
	"2026春季征文": {Year: 2026, Start: "2026-02-27", End: "2026-05-03",
		Note: "公布 2026-07-10"},
	"2024秋季征文": {Year: 2024, Start: "2024-09-30", End: "2024-12-05"},
	"2025秋季征文": {Year: 2025, Start: "2025-09-30", End: "2025-12-04"},
	// IP collab / themed
	"崩坏3征文": {Year: 2019, Start: "2019-01-04", End: "2019-02-11",
		Note: "公示 2019-02-22"},
	"奇幻世界主题征文": {Year: 2025, Start: "2025-06-06", End: "2025-08-31"},
}

// ContestMetaFor returns the metadata for an event-level name. Exported for
// the roster endpoint's TTL rule (ended events cache 365d, active 24h).
func ContestMetaFor(name string) (ContestMeta, bool) {
	m, ok := contestMeta[name]
	return m, ok
}

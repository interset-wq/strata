package store

import (
	"context"
	"database/sql"
	"sort"
	"strings"
	"unicode/utf8"
)

// ContestGroup is one event-level contest aggregated from seed.books — the
// data for the contest archive list and archive page
// (docs/contest-display-in-app.md 形态一). Count and Forms cover
// in-library (seed-admitted) books only; the roster API (P1) is the only
// source for out-of-library participants.
type ContestGroup struct {
	Name    string         `json:"name"`
	Series  string         `json:"series"` // x|winter|spring|autumn|other
	Count   int            `json:"count"`
	Forms   map[string]int `json:"forms"`
	Tracks  []string       `json:"tracks"` // raw contest strings, count DESC
	YearMin int            `json:"year_min"`
	YearMax int            `json:"year_max"`
	Year    *int           `json:"year,omitempty"`
	Start   *string        `json:"start,omitempty"`
	End     *string        `json:"end,omitempty"`
	Note    *string        `json:"note,omitempty"`
	// Official = the official activity-page URL (contest_meta.go, mobile
	// form); omitted when unverified — the archive page shows its jump
	// entry only when present and never fabricates URLs.
	Official *string `json:"official,omitempty"`
	// Lane classifies other-series events for the home-tab lanes (user
	// decision 2026-11-22: dialogue archives live in the home dialogue
	// area, IP archives in the IP area): "dialogue" / "ip"; omitted
	// (= theme) stays in the archive list's 其他 tab. Never set on the
	// four season series.
	Lane string `json:"lane,omitempty"`
	// Roster = the event has at least one verified tagId (roster_tags.go);
	// the archive page shows the 「查看官方清单」 entry from this flag.
	// RosterTracks = the verified divisions for the roster page chips; empty
	// (omitted) = single-track event.
	Roster       bool     `json:"roster"`
	RosterTracks []string `json:"roster_tracks,omitempty"`
}

// ContestEventName maps a raw contest string to its event-level name: the
// N征 series collapses every division spelling (incl. 对话类:
// 七征对话类征文长篇, 九征/十征对话小说) to the N征 token; every other contest
// is a single event and is returned unchanged.
func ContestEventName(raw string) string {
	for _, n := range []string{"十三征", "十二征", "十一征", "十征", "九征",
		"八征", "七征", "六征", "五征", "四征", "三征", "二征", "一征"} {
		if strings.HasPrefix(raw, n) {
			return n
		}
	}
	return raw
}

// contestEventMatch matches an event-level name against the raw column:
// N征 events match every division spelling (prefix); other events are
// single-division and match exactly.
func contestEventMatch(col, name string) (string, []any) {
	if isZhengEvent(name) {
		return col + " LIKE ? || '%'", []any{name}
	}
	return col + " = ?", []any{name}
}

// contestSeries buckets an event name for the archive list sections.
func contestSeries(name string) string {
	switch {
	case isZhengEvent(name):
		return "x"
	case strings.Contains(name, "冬季征文"):
		return "winter"
	case strings.Contains(name, "春季征文"):
		return "spring"
	case strings.Contains(name, "秋季征文"):
		return "autumn"
	default:
		return "other"
	}
}

// seriesOrder = the archive list's tab order (user decision 2026-11-22:
// 春 / x征 / 秋 / 冬 / 其他), which doubles as the JSON group ordering.
var seriesOrder = map[string]int{
	"spring": 0, "x": 1, "autumn": 2, "winter": 3, "other": 4,
}

var cnOrdinal = map[rune]int{
	'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
	'六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}

// contestOrdinal extracts the 第X届 edition number (0 when the name
// carries none, e.g. first-edition 冬季征文) so same-year editions sort
// in launch order — plain unicode order puts 第三届 before 第二届.
func contestOrdinal(name string) int {
	j := strings.Index(name, "届")
	if j <= 1 {
		return 0
	}
	r, _ := utf8.DecodeLastRuneInString(name[:j])
	if n, ok := cnOrdinal[r]; ok {
		return n
	}
	return 0
}

// contestLane classifies an other-series event for the home-tab lanes
// (user decision 2026-11-22: 对话的归档放对话区、IP 的归档放 IP 区):
// 对话/点鸭 names are the dialogue line (点鸭 is the dialogue product
// line's contest brand); 同人 and known IP titles are the IP line.
// "" = theme, stays in the archive list's 其他 tab.
//
// Edition-level overrides come first: facts about one specific contest
// that no name rule can capture — 星穹小说家征文 is a dialogue contest
// (user-verified 2026-11-22; the IP-titled name would otherwise send it
// to the IP lane).
func contestLane(name string) string {
	switch {
	case strings.Contains(name, "星穹小说家"):
		return "dialogue"
	case strings.Contains(name, "对话"), strings.Contains(name, "点鸭"):
		return "dialogue"
	}
	for _, ip := range []string{"同人", "崩坏3", "少女前线", "龙之谷", "星穹"} {
		if strings.Contains(name, ip) {
			return "ip"
		}
	}
	return ""
}

// startYear is the contest's launch year for the stable ascending sort
// (user decision 2026-11-22): the official meta year when known (a
// 2022 spring contest holds 2019-dated books — the launch year is the
// ordering fact), else the in-library est_year floor.
func (g ContestGroup) startYear() int {
	if g.Year != nil {
		return *g.Year
	}
	return g.YearMin
}

// ContestGroups aggregates seed.books by event-level contest name (the
// archive list; zero requests). Ordering: series section, then the cohort's
// earliest est_year, then name.
func (s *Store) ContestGroups(ctx context.Context) ([]ContestGroup, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT contest, form, COUNT(*) AS n, MIN(est_year), MAX(est_year)
FROM seed.books
WHERE contest != '' AND is_licensed = 0
GROUP BY contest, form`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	type acc struct {
		g        ContestGroup
		trackCnt map[string]int
	}
	byName := map[string]*acc{}
	for rows.Next() {
		var contest, form string
		var n, yMin, yMax int
		if err := rows.Scan(&contest, &form, &n, &yMin, &yMax); err != nil {
			return nil, err
		}
		name := ContestEventName(contest)
		a, ok := byName[name]
		if !ok {
			a = &acc{
				g: ContestGroup{
					Name:    name,
					Series:  contestSeries(name),
					Forms:   map[string]int{},
					YearMin: yMin,
					YearMax: yMax,
				},
				trackCnt: map[string]int{},
			}
			byName[name] = a
		}
		a.g.Count += n
		a.g.Forms[form] += n
		a.trackCnt[contest] += n
		if yMin < a.g.YearMin {
			a.g.YearMin = yMin
		}
		if yMax > a.g.YearMax {
			a.g.YearMax = yMax
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	out := make([]ContestGroup, 0, len(byName))
	for name, a := range byName {
		tracks := make([]string, 0, len(a.trackCnt))
		for raw := range a.trackCnt {
			tracks = append(tracks, raw)
		}
		sort.Slice(tracks, func(i, j int) bool {
			if a.trackCnt[tracks[i]] != a.trackCnt[tracks[j]] {
				return a.trackCnt[tracks[i]] > a.trackCnt[tracks[j]]
			}
			return tracks[i] < tracks[j]
		})
		a.g.Tracks = tracks
		if a.g.Series == "other" {
			a.g.Lane = contestLane(name)
		}
		if m, ok := ContestMetaFor(name); ok {
			if m.Year != 0 {
				y := m.Year
				a.g.Year = &y
			}
			if m.Start != "" {
				v := m.Start
				a.g.Start = &v
			}
			if m.End != "" {
				v := m.End
				a.g.End = &v
			}
			if m.Note != "" {
				v := m.Note
				a.g.Note = &v
			}
			if m.Official != "" {
				v := m.Official
				a.g.Official = &v
			}
		}
		if tags := RosterTagsFor(name); tags != nil {
			a.g.Roster = true
			for _, tg := range tags {
				if tg.Division != "" {
					a.g.RosterTracks = append(a.g.RosterTracks, tg.Division)
				}
			}
		}
		out = append(out, a.g)
	}
	// Stable ordering (user decision 2026-11-22): tab section, then launch
	// year ascending, then 第X届 ordinal (same-year winter editions), then
	// name.
	sort.Slice(out, func(i, j int) bool {
		si, sj := seriesOrder[out[i].Series], seriesOrder[out[j].Series]
		if si != sj {
			return si < sj
		}
		yi, yj := out[i].startYear(), out[j].startYear()
		if yi != yj {
			return yi < yj
		}
		oi, oj := contestOrdinal(out[i].Name), contestOrdinal(out[j].Name)
		if oi != oj {
			return oi < oj
		}
		return out[i].Name < out[j].Name
	})
	return out, nil
}

// ContestBooks lists one contest's representative books: the per-form head
// by favs (classic cumulative, NULLs last — cross-generation approximation
// since the universe percentiles no longer ship, E.30), so long-form volume
// cannot drown the short/dialogue tracks (docs/contest-display-in-app.md
// 形态一). perForm caps each form; the covers overlay applies (docs/05 §3).
func (s *Store) ContestBooks(ctx context.Context, name string, perForm int) ([]RankItem, error) {
	clause, args := contestEventMatch("b.contest", name)
	query := `
SELECT b.nid, b.title, b.author, b.genre, b.est_year, b.clicks, b.favs,
       b.contest, b.form,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url
FROM (
  SELECT b.nid, b.title, b.author, b.genre, b.est_year, b.clicks, b.favs,
         b.contest, b.form, b.cover_url,
         ROW_NUMBER() OVER (PARTITION BY b.form
           ORDER BY (b.favs IS NULL) ASC, b.favs DESC, b.nid) AS rn
  FROM seed.books b
  WHERE b.is_licensed = 0 AND ` + clause + `
) b
LEFT JOIN covers c ON c.nid = b.nid
WHERE b.rn <= ?
ORDER BY (b.favs IS NULL) ASC, b.favs DESC, b.nid`
	all := append([]any{}, args...)
	all = append(all, perForm)

	rows, err := s.DB.QueryContext(ctx, query, all...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, perForm*5)
	for rows.Next() {
		var (
			item    RankItem
			gen     sql.NullString
			clicks  sql.NullInt64
			favs    sql.NullInt64
			contest sql.NullString
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &clicks, &favs, &contest, &item.Form,
			&item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.Contest = contestPtr(contest)
		items = append(items, item)
	}
	return items, rows.Err()
}

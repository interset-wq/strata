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
// (docs/contest-display-in-app.md 形态一). Count/Forms are in-library
// (seed-admitted) books only; the ledger's official numbers are the other
// half of the story and come from the embedded table (zero requests).
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
	// Result = the official 公布 date; in the future for an edition still
	// running, which the archive page words as 预计.
	Result   *string `json:"result,omitempty"`
	Note     *string `json:"note,omitempty"`
	Official *string `json:"official,omitempty"`
	// Lane classifies other-series events for the home-tab lanes (user
	// decision 2026-11-22/27): "dialogue" → home dialogue area, "ip" → IP
	// area, "short" → home 短篇 tab (2024主题短篇 / 超新星杯短篇); omitted
	// (= theme) stays in the archive list's 主题 tab. Never set on the
	// four season series.
	Lane string `json:"lane,omitempty"`
	// Roster = the event has at least one participation-list tag (ledger);
	// the archive page shows the 「官方清单」 entry from this flag. Award-only
	// events (一/二/三征, winner tags 635-649) keep it false and expose
	// ListKind=award instead.
	// Divisions = the verified tracks with their official counts, in
	// official order; the archive page's per-track rows and the roster
	// chips both read it. Single-track events carry one row named 全部.
	Roster    bool             `json:"roster"`
	Divisions []RosterDivision `json:"divisions,omitempty"`
	// ListKind = "roster" | "award" | "" — which official list the event
	// can fetch, so the UI labels entries 官方清单 vs 获奖名单.
	ListKind string `json:"list_kind,omitempty"`
	// RosterTotal = the official entry-list size summed over the event's
	// tracks (contest-achieve, captured per tag): the number that replaces
	// the in-library count as the archive list's headline. Nil when any
	// track is unverified — never a partial sum.
	RosterTotal *int `json:"roster_total,omitempty"`
	// AwardTotal = the official winner count. The winner lists themselves are
	// not in the app (docs/contest-display-in-app.md §6), so the UI sizes a
	// reserved block with it and never renders it as participation.
	AwardTotal *int `json:"award_total,omitempty"`
}

// zhengToEvent extracts the leading N征 token ("" when the name does not
// start with one) — structural, so a new edition needs no code change.
func zhengToEvent(raw string) string {
	i := 0
	for i < len(raw) {
		r, size := utf8.DecodeRuneInString(raw[i:])
		if !strings.ContainsRune("一二三四五六七八九十", r) {
			break
		}
		i += size
	}
	if i == 0 || i >= len(raw) {
		return ""
	}
	r, size := utf8.DecodeRuneInString(raw[i:])
	if r != '征' {
		return ""
	}
	return raw[:i+size]
}

// ContestEventName maps a raw contest string to its event-level name, always
// in OUR 2026-11-27 naming (2025春征 / 崩坏3同人 / 点鸭星穹 / 四征 …).
// The embed table resolves every authored spelling (new name, legacy official
// name, old alias) to one event. Unlisted labels fall back to the structural
// N征 rule (so a future 十五征 needs no code change) then the ledger alias.
func ContestEventName(raw string) string {
	if ev, ok := contestNameEvent(raw); ok {
		return ev
	}
	if tok := zhengToEvent(raw); tok != "" {
		return tok
	}
	return LedgerCanonical(raw)
}

// contestEventMatch matches an event-level name against the raw column:
// N征 events match every division spelling (prefix, so a future 十五征 needs
// no code change); every other event matches all spellings the table maps to
// it — its new name plus legacy/alias spellings (2025春征 and 2025春季征文
// are one event, 2021秋征 spans both 东方世界/异世大陆 rows).
func contestEventMatch(col, name string) (string, []any) {
	name = LedgerCanonical(name) // accept new name, legacy name or raw spelling
	if isZhengEvent(name) {
		return col + " LIKE ? || '%'", []any{name}
	}
	vals := []string{name}
	for _, raw := range contestRawSpellings(name) {
		vals = append(vals, raw)
	}
	// Dedupe: the event's own name is usually also a raw spelling.
	seen := map[string]bool{}
	uniq := vals[:0]
	for _, v := range vals {
		if !seen[v] {
			seen[v] = true
			uniq = append(uniq, v)
		}
	}
	vals = uniq
	if len(vals) == 1 {
		return col + " = ?", []any{vals[0]}
	}
	holders := make([]byte, 0, len(vals)*2)
	args := make([]any, 0, len(vals))
	for i, v := range vals {
		if i > 0 {
			holders = append(holders, ',', ' ')
		}
		holders = append(holders, '?')
		args = append(args, v)
	}
	return col + " IN (" + string(holders) + ")", args
}

// contestSeries buckets an event name for the archive list sections. The
// embedded table carries our naming's bucket directly; string matching stays
// only as a fallback for a future edition not yet in the anchor.
func contestSeries(name string) string {
	if info, ok := contestNameForEvent(name); ok {
		return info.Series
	}
	switch {
	case isZhengEvent(name):
		return "x"
	case strings.Contains(name, "冬征"), strings.Contains(name, "冬季征文"):
		return "winter"
	case strings.Contains(name, "春征"), strings.Contains(name, "春季征文"):
		return "spring"
	case strings.Contains(name, "秋征"), strings.Contains(name, "秋季征文"):
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
// 点鸭 dialogue contests → dialogue; 同人/IP contests → ip; "" = theme,
// stays in the archive list's 主题 tab. Our 2026-11-27 naming encodes the
// lane in the table (点鸭对话 / IP同人 series), so name matching remains only
// a fallback for unlisted future spellings.
func contestLane(name string) string {
	if info, ok := contestNameForEvent(name); ok && info.Lane != "" {
		return info.Lane
	}
	switch {
	case strings.Contains(name, "星穹小说家"), strings.Contains(name, "点鸭"):
		return "dialogue"
	case strings.Contains(name, "对话"):
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

	// 收录书并入在库计数（用户裁定 2026-11-28）：参赛清单点库外书触发
	// 自动收录，book_meta.contest 带回比赛归属，下次进列表计数即更新。
	metaRows, err := s.DB.QueryContext(ctx,
		`SELECT contest, COUNT(*) FROM book_meta WHERE contest != '' GROUP BY contest`)
	if err != nil {
		return nil, err
	}
	defer metaRows.Close()
	for metaRows.Next() {
		var contest string
		var n int
		if err := metaRows.Scan(&contest, &n); err != nil {
			return nil, err
		}
		if a, ok := byName[ContestEventName(contest)]; ok {
			a.g.Count += n
		}
	}
	if err := metaRows.Err(); err != nil {
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
		if e, ok := LedgerEventFor(name); ok {
			a.g.Year = e.Year
			a.g.Start = emptyAsNil(e.Start)
			a.g.End = emptyAsNil(e.End)
			a.g.Result = emptyAsNil(e.Result)
			a.g.Note = emptyAsNil(e.Note)
			a.g.Official = emptyAsNil(e.URL)
			a.g.RosterTotal = e.RosterTotal
			a.g.AwardTotal = e.AwardTotal
			a.g.Divisions = LedgerDivisions(name)
			a.g.ListKind = LedgerListKind(name)
			a.g.Roster = a.g.ListKind == LedgerKindRoster
		}
		out = append(out, a.g)
	}
	// Stable ordering (user decision 2026-11-26, was ascending): tab section,
	// then launch year DESC — the archive is read as 「最近一届在前」 — then
	// 第X届 ordinal DESC (same-year winter editions), then official entry-list
	// size DESC (the 主题 tab has no ordinal: same-year editions rank by
	// scale), then name.
	sort.Slice(out, func(i, j int) bool {
		si, sj := seriesOrder[out[i].Series], seriesOrder[out[j].Series]
		if si != sj {
			return si < sj
		}
		yi, yj := out[i].startYear(), out[j].startYear()
		if yi != yj {
			return yi > yj
		}
		oi, oj := contestOrdinal(out[i].Name), contestOrdinal(out[j].Name)
		if oi != oj {
			return oi > oj
		}
		ri, rj := deref(out[i].RosterTotal), deref(out[j].RosterTotal)
		if ri != rj {
			return ri > rj
		}
		return out[i].Name < out[j].Name
	})
	return out, nil
}

// deref reads an optional int as 0 for ordering (absent = last).
func deref(p *int) int {
	if p == nil {
		return 0
	}
	return *p
}

// emptyAsNil turns an unfilled ledger field into an absent JSON field, so the
// UI can tell 「官方未公示」 from a date.
func emptyAsNil(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// ContestBooks lists one contest's representative books: the per-form head
// by favs (classic cumulative, NULLs last — cross-generation approximation
// since the universe percentiles no longer ship, E.30), so long-form volume
// cannot drown the short/dialogue tracks (docs/contest-display-in-app.md
// 形态一). perForm caps each form; the covers overlay applies (docs/05 §3).
func (s *Store) ContestBooks(ctx context.Context, name string, perForm int) ([]RankItem, error) {
	clause, args := contestEventMatch("b.contest", name)
	// 2026-11-27: rows carry the full classic-ranking field set
	// (status/price_type/words/praises added) — the shared BookRowTile
	// renders the status/price badges and the metric strip, which the old
	// lightweight SELECT silently dropped. 2026-11-27b: plus tags
	// (GROUP_CONCAT book_tags) — the tags row of the shared tile was empty.
	query := `
SELECT b.nid, b.title, b.author, b.genre, b.est_year, b.clicks, b.favs,
       b.contest, b.form, b.status, b.price_type, b.words, b.praises,
       (SELECT GROUP_CONCAT(bt.tag) FROM book_tags bt WHERE bt.nid = b.nid) AS tags,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url,
       b.rn
FROM (
  SELECT b.nid, b.title, b.author, b.genre, b.est_year, b.clicks, b.favs,
         b.contest, b.form, b.status, b.price_type, b.words, b.praises,
         b.cover_url,
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
			status  sql.NullString
			price   sql.NullString
			words   sql.NullInt64
			praises sql.NullInt64
			contest sql.NullString
			tags    sql.NullString
			rn      int
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &clicks, &favs, &contest, &item.Form,
			&status, &price, &words, &praises, &tags,
			&item.CoverURL, &rn); err != nil {
			return nil, err
		}
		// 序号 = form 内排名（rn，用户裁定 2026-11-27：各形态列表序号
		// 都从 1 开始），不是跨 form 的全局行号。
		item.Rank = rn
		item.Genre = strPtr(gen)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.Contest = contestPtr(contest)
		item.Status = strPtr(status)
		item.PriceType = strPtr(price)
		item.Words = intPtr(words)
		item.Praises = intPtr(praises)
		if tags.Valid && tags.String != "" {
			item.Tags = strings.Split(tags.String, ",")
		} else {
			item.Tags = []string{}
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

package store

import (
	"context"
	"database/sql"
	"sort"
	"strings"
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

var seriesOrder = map[string]int{
	"x": 0, "winter": 1, "spring": 2, "autumn": 3, "other": 4,
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
	sort.Slice(out, func(i, j int) bool {
		si, sj := seriesOrder[out[i].Series], seriesOrder[out[j].Series]
		if si != sj {
			return si < sj
		}
		if out[i].YearMin != out[j].YearMin {
			return out[i].YearMin < out[j].YearMin
		}
		return out[i].Name < out[j].Name
	})
	return out, nil
}

// ContestBooks lists one contest's representative books: the per-form head
// by fav_pctl (same-generation percentile, NULLs last), so long-form volume
// cannot drown the short/dialogue tracks (docs/contest-display-in-app.md
// 形态一). perForm caps each form; the covers overlay applies (docs/05 §3).
func (s *Store) ContestBooks(ctx context.Context, name string, perForm int) ([]RankItem, error) {
	clause, args := contestEventMatch("b.contest", name)
	query := `
SELECT b.nid, b.title, b.author, b.genre, b.est_year, b.favs, b.fav_pctl,
       b.contest, b.form,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url
FROM (
  SELECT b.nid, b.title, b.author, b.genre, b.est_year, b.favs, b.fav_pctl,
         b.contest, b.form, b.cover_url,
         ROW_NUMBER() OVER (PARTITION BY b.form
           ORDER BY (b.fav_pctl IS NULL) ASC, b.fav_pctl DESC, b.nid) AS rn
  FROM seed.books b
  WHERE b.is_licensed = 0 AND ` + clause + `
) b
LEFT JOIN covers c ON c.nid = b.nid
WHERE b.rn <= ?
ORDER BY (b.fav_pctl IS NULL) ASC, b.fav_pctl DESC, b.nid`
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
			favs    sql.NullInt64
			pctl    sql.NullFloat64
			contest sql.NullString
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &pctl, &contest, &item.Form, &item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.FavPctl = pctl.Float64
		item.Contest = contestPtr(contest)
		items = append(items, item)
	}
	return items, rows.Err()
}

package store

import (
	"context"
	"database/sql"
)

// Award is one contest_awards row (schema v5; single source
// docs/award-winners-as-seed-source.md). Display-only fact: it never feeds
// admission, ordering, or scoring (docs/contest-display-in-app.md §6 red
// line). The 867 uncalibrated rows carry award='待逐档标定'; the display
// layer renders that placeholder as 征文获奖 (the raw value never shows).
type Award struct {
	NID      int64   `json:"nid"`
	Edition  string  `json:"edition"`
	Award    string  `json:"award"`
	Category *string `json:"category,omitempty"`
}

// AwardRow is an in-library award book for the archive-page block: the
// award row joined to its seed book. The 140 out-of-library award rows have
// no books row and are invisible here by design (v1 does not fetch them).
type AwardRow struct {
	Award
	Title   string   `json:"title"`
	Author  string   `json:"author"`
	Favs    *int64   `json:"favs"`
	FavPctl *float64 `json:"fav_pctl"`
	Cover   *string  `json:"cover_url"`
	EstYear int      `json:"est_year"`
}

// awardEventEditions maps archive event names (ContestEventName form — the
// same names as the roster ledger) to contest_awards.edition values. The 11
// editions are the only award source; an event outside the map simply has no
// award block (graceful, not an error). Note 七征 (summer) has no edition —
// its awards are all 七征冬征, a separate winter event.
var awardEventEditions = map[string]string{
	"十二征":         "十二征",
	"十三征":         "十三征",
	"第六届冬季征文": "六征冬征",
	"第七届冬季征文": "七征冬征",
	"第八届冬季征文": "八征冬征",
	"第九届冬季征文": "九征冬征",
	"2024春季征文": "2024春征",
	"2024秋季征文": "2024秋征",
	"2025春季征文": "2025春征",
	"2025秋季征文": "2025秋征",
	"2026春季征文": "2026春征",
}

// BookAwards returns the award rows of one book (detail-page badge).
// Empty slice when the book has none; the JSON field is then omitted.
func (s *Store) BookAwards(ctx context.Context, nid int64) ([]*Award, error) {
	rows, err := s.DB.QueryContext(ctx,
		`SELECT nid, edition, award, category FROM seed.contest_awards
		 WHERE nid = ? ORDER BY edition`, nid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []*Award{}
	for rows.Next() {
		var (
			a        Award
			category sql.NullString
		)
		if err := rows.Scan(&a.NID, &a.Edition, &a.Award, &category); err != nil {
			return nil, err
		}
		a.Category = strPtr(category)
		out = append(out, &a)
	}
	return out, rows.Err()
}

// EditionAwards returns the in-library award books of one event
// (archive-page block), ordered by fav_pctl DESC, NULLs last — the same
// ordering red line as the representative books: cumulative raw values and
// the award field itself never order.
func (s *Store) EditionAwards(ctx context.Context, event string) ([]*AwardRow, error) {
	edition, ok := awardEventEditions[event]
	if !ok {
		return []*AwardRow{}, nil
	}
	rows, err := s.DB.QueryContext(ctx, `
SELECT a.nid, a.edition, a.award, a.category,
       b.title, b.author, b.favs, b.fav_pctl, b.cover_url, b.est_year
  FROM seed.contest_awards a
  JOIN seed.books b ON b.nid = a.nid
 WHERE a.edition = ?
 ORDER BY CASE WHEN b.fav_pctl IS NULL THEN 1 ELSE 0 END,
          b.fav_pctl DESC, b.nid`, edition)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []*AwardRow{}
	for rows.Next() {
		var (
			r        AwardRow
			category sql.NullString
			favs     sql.NullInt64
			favPctl  sql.NullFloat64
			cover    sql.NullString
		)
		// r.Award is the embedded struct; the string field is r.Award.Award.
		if err := rows.Scan(&r.Award.NID, &r.Award.Edition, &r.Award.Award, &category,
			&r.Title, &r.Author, &favs, &favPctl, &cover, &r.EstYear); err != nil {
			return nil, err
		}
		r.Category = strPtr(category)
		r.Favs = intPtr(favs)
		r.FavPctl = floatPtr(favPctl)
		r.Cover = strPtr(cover)
		out = append(out, &r)
	}
	return out, rows.Err()
}

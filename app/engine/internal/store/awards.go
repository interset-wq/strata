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

// The archive-page award block now reads the verified contest-achieve ledger
// (award_ledger.go), not this seed table; only the detail-page BookAwards
// contract remains here (the UI no longer parses it, user ruling 2026-11-26).

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

package store

import (
	"context"
	"database/sql"
	_ "embed"
	"encoding/json"
	"strings"
)

// The contest-award ledger is the display-only winner list for the archive
// page: verified, real award names keyed by our event name. Authored by
// app/tools/contestledger/build_awards.py from contest-achieve's awards.json
// (AGPL-3.0, 613 verified rows / 609 unique nids across 41 events). Awards
// never feed admission, ordering or scoring (docs/contest-display-in-app.md §6
// red line); they are facts shown next to the event, not ranking signals.
// This is deliberately NOT the seed-side contest_awards table (the old 911-row
// normalized CSV with 867 '待逐档标定' placeholders, which the UI no longer
// parses on the detail page).

type awardLedgerItem struct {
	NID     int64    `json:"nid"`
	Title   string   `json:"title"`
	Awards  []string `json:"awards"`
	Contest string   `json:"contest"`
	Series  string   `json:"series"`
}

type awardLedgerDoc struct {
	Source    map[string]string            `json:"source"`
	TierOrder []string                     `json:"tier_order"`
	Events    map[string][]awardLedgerItem `json:"events"`
}

//go:embed contest_awards.json
var contestAwardsJSON []byte

var awardLedger = func() *awardLedgerDoc {
	var d awardLedgerDoc
	if err := json.Unmarshal(contestAwardsJSON, &d); err != nil {
		panic("store: contest_awards.json: " + err.Error())
	}
	return &d
}()

// AwardRow is one verified winner shown on an event's archive page. A nid may
// hold two awards in the same event; Awards keeps both. Seed fields are joined
// when the book is in the built-in library; a verified winner that is not in
// seed still carries its title/award (in_seed=false, no fake book fields).
type AwardRow struct {
	NID     int64    `json:"nid"`
	Title   string   `json:"title"`
	Awards  []string `json:"awards"`
	Contest string   `json:"contest"`
	Series  string   `json:"series"`
	InSeed  bool     `json:"in_seed"`
	Author  string   `json:"author,omitempty"`
	Favs    *int64   `json:"favs,omitempty"`
	Cover   *string  `json:"cover_url,omitempty"`
	EstYear *int     `json:"est_year,omitempty"`
	Form    string   `json:"form,omitempty"`
}

// EditionAwards returns one event's verified winners in award-tier order (the
// ledger's order — the award name orders the display, never a score). Every
// winner is returned, including ones absent from seed: those show title and
// award only, so a verified winner is never hidden just because our crawler
// missed the book.
func (s *Store) EditionAwards(ctx context.Context, event string) ([]*AwardRow, error) {
	items := awardLedger.Events[LedgerCanonical(event)]
	out := make([]*AwardRow, 0, len(items))
	if len(items) == 0 {
		return out, nil
	}

	nids := make([]any, len(items))
	for i, it := range items {
		nids[i] = it.NID
	}
	// LEFT side is the ledger (authoritative winners); join only fills book
	// metadata. A nid absent from seed keeps its award row with InSeed=false.
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, author, favs, cover_url, est_year, form
  FROM seed.books
 WHERE nid IN (`+strings.TrimSuffix(strings.Repeat("?,", len(nids)), ",")+`)`, nids...)
	if err != nil {
		return nil, err
	}
	joined := make(map[int64]*AwardRow, len(items))
	for rows.Next() {
		var (
			nid    int64
			author string
			favs   sql.NullInt64
			cover  sql.NullString
			year   sql.NullInt64
			form   sql.NullString
		)
		if err := rows.Scan(&nid, &author, &favs, &cover, &year, &form); err != nil {
			rows.Close()
			return nil, err
		}
		j := &AwardRow{NID: nid, Author: author, InSeed: true,
			Favs: intPtr(favs), Cover: strPtr(cover)}
		if year.Valid {
			y := int(year.Int64)
			j.EstYear = &y
		}
		if form.Valid {
			j.Form = form.String
		}
		joined[nid] = j
	}
	if err := rows.Close(); err != nil {
		return nil, err
	}

	for _, it := range items {
		r := &AwardRow{NID: it.NID, Title: it.Title, Awards: it.Awards,
			Contest: it.Contest, Series: it.Series}
		if j, ok := joined[it.NID]; ok {
			// 2026-11-26 fix: the old code wrote r.EstYear/r.Form back from
			// r itself (always nil/empty) — in-seed winners never carried
			// est_year/form even though the join fetched them.
			r.InSeed, r.Author, r.Favs = j.InSeed, j.Author, j.Favs
			r.Cover, r.EstYear, r.Form = j.Cover, j.EstYear, j.Form
		}
		out = append(out, r)
	}
	return out, nil
}

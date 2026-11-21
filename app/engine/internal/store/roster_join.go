package store

import (
	"context"
	"database/sql"
	"strings"
)

// RosterItem is one row of the roster page response
// (docs/contest-display-in-app.md 形态二): the six official roster fields
// plus the local join for in-library books. Out-of-library books keep only
// the roster fields — no form/percentile badges, nothing fabricated
// (docs/12 red line); CategoryID is a division hint only, never form.
type RosterItem struct {
	NID        int      `json:"nid"`
	Title      string   `json:"title"`
	Author     string   `json:"author,omitempty"`
	Intro      string   `json:"intro,omitempty"`
	Cover      string   `json:"cover,omitempty"`
	CategoryID int      `json:"category_id,omitempty"`
	InLibrary  bool     `json:"in_library"`
	Form       string   `json:"form,omitempty"`
	FavPctl    *float64 `json:"fav_pctl,omitempty"`
	Favs       *int64   `json:"favs,omitempty"`
	Status     string   `json:"status,omitempty"`
	EstYear    int      `json:"est_year,omitempty"`
	Words      *int64   `json:"words,omitempty"`
}

// BookLite is the enrichment subset of one seed.books row for the roster
// join (the join runs on every serve: the official page is cached, the
// local layer is live).
type BookLite struct {
	NID     int64
	Form    string
	FavPctl *float64
	Favs    *int64
	Status  string
	EstYear int
	Words   *int64
}

// BooksByNIDs returns one BookLite per seed book among nids (empty map when
// none are in the seed). A roster page carries at most one official page of
// nids (<=500), so a single IN list is the right shape.
func (s *Store) BooksByNIDs(ctx context.Context, nids []int64) (map[int64]BookLite, error) {
	out := map[int64]BookLite{}
	if len(nids) == 0 {
		return out, nil
	}
	marks := strings.TrimSuffix(strings.Repeat("?,", len(nids)), ",")
	args := make([]any, len(nids))
	for i, n := range nids {
		args[i] = n
	}
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, form, fav_pctl, favs, status, est_year, words
FROM seed.books WHERE nid IN (`+marks+`)`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var (
			nid64         int64
			year          int
			form, status  string
			pctl          sql.NullFloat64
			favs, words   sql.NullInt64
		)
		if err := rows.Scan(&nid64, &form, &pctl, &favs, &status, &year, &words); err != nil {
			return nil, err
		}
		out[nid64] = BookLite{
			NID: nid64, Form: form, FavPctl: float64Ptr(pctl),
			Favs: intPtr(favs), Status: status, EstYear: year, Words: intPtr(words),
		}
	}
	return out, rows.Err()
}

// RosterLocalBooks lists the in-library books of one event (optionally one
// division) by same-gen percentile — the degraded roster shape when the
// event has no verified tag or the upstream is dead (docs/
// contest-display-in-app.md 降级表). Single-shot list (cap 2000), not a
// paginated feed: the in-library subset is the fallback, the official page
// is the primary.
func (s *Store) RosterLocalBooks(ctx context.Context, event, division string) ([]RosterItem, error) {
	clause, args := contestEventMatch("b.contest", event)
	if division != "" {
		clause += " AND b.contest = ?"
		args = append(args, event+division)
	}
	query := `
SELECT b.nid, b.title, b.author, b.form, b.fav_pctl, b.favs, b.status,
       b.est_year, b.words,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover
FROM seed.books b
LEFT JOIN covers c ON c.nid = b.nid
WHERE b.is_licensed = 0 AND ` + clause + `
ORDER BY (b.fav_pctl IS NULL) ASC, b.fav_pctl DESC, b.nid
LIMIT 2000`
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RosterItem, 0, 64)
	for rows.Next() {
		var (
			item    RosterItem
			pctl    sql.NullFloat64
			favs    sql.NullInt64
			words   sql.NullInt64
			cover   sql.NullString
			author  sql.NullString
			status  sql.NullString
		)
		var nid int64
		if err := rows.Scan(&nid, &item.Title, &author, &item.Form, &pctl, &favs,
			&status, &item.EstYear, &words, &cover); err != nil {
			return nil, err
		}
		item.NID = int(nid)
		item.Author = author.String
		item.Status = status.String
		item.Cover = cover.String
		item.InLibrary = true
		item.FavPctl = float64Ptr(pctl)
		item.Favs = intPtr(favs)
		item.Words = intPtr(words)
		items = append(items, item)
	}
	return items, rows.Err()
}

// float64Ptr is the nullable counterpart of intPtr for REAL columns
// (fav_pctl is NULL for out-of-universe books; a NULL stays absent in the
// roster JSON instead of rendering as 0).
func float64Ptr(n sql.NullFloat64) *float64 {
	if !n.Valid {
		return nil
	}
	return &n.Float64
}

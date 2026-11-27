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
	Favs       *int64   `json:"favs,omitempty"`
	Status     string   `json:"status,omitempty"`
	EstYear    int      `json:"est_year,omitempty"`
	Words      *int64   `json:"words,omitempty"`
	// Full classic-row fields for the 仅库内 direct-db view (user ruling
	// 2026-11-27): the shared BookRowTile renders them.
	Genre     *string  `json:"genre,omitempty"`
	PriceType *string  `json:"price_type,omitempty"`
	Clicks    *int64   `json:"clicks,omitempty"`
	Praises   *int64   `json:"praises,omitempty"`
	Tags      []string `json:"tags,omitempty"`
}

// BookLite is the enrichment subset of one seed.books row for the roster
// join (the join runs on every serve: the official page is cached, the
// local layer is live).
type BookLite struct {
	NID     int64
	Form    string
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
SELECT nid, form, favs, status, est_year, words
FROM seed.books WHERE nid IN (`+marks+`)`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var (
			nid64        int64
			year         int
			form, status string
			favs, words  sql.NullInt64
		)
		if err := rows.Scan(&nid64, &form, &favs, &status, &year, &words); err != nil {
			return nil, err
		}
		out[nid64] = BookLite{
			NID: nid64, Form: form,
			Favs: intPtr(favs), Status: status, EstYear: year, Words: intPtr(words),
		}
	}
	return out, rows.Err()
}

// RosterLocalBooks lists the in-library books of one event (optionally one
// division) by favs (classic cumulative, E.30) — the degraded roster shape
// when the event has no verified tag or the upstream is dead (docs/
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
SELECT b.nid, b.title, b.author, b.form, b.favs, b.status,
       b.est_year, b.words,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover
FROM seed.books b
LEFT JOIN covers c ON c.nid = b.nid
WHERE b.is_licensed = 0 AND ` + clause + `
ORDER BY (b.favs IS NULL) ASC, b.favs DESC, b.nid
LIMIT 2000`
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RosterItem, 0, 64)
	for rows.Next() {
		var (
			item   RosterItem
			favs   sql.NullInt64
			words  sql.NullInt64
			cover  sql.NullString
			author sql.NullString
			status sql.NullString
		)
		var nid int64
		if err := rows.Scan(&nid, &item.Title, &author, &item.Form, &favs,
			&status, &item.EstYear, &words, &cover); err != nil {
			return nil, err
		}
		item.NID = int(nid)
		item.Author = author.String
		item.Status = status.String
		item.Cover = cover.String
		item.InLibrary = true
		item.Favs = intPtr(favs)
		item.Words = intPtr(words)
		items = append(items, item)
	}
	return items, rows.Err()
}

// RosterLocalBooksPaged is the paginated, full-field variant of
// RosterLocalBooks for the roster page's 仅库内 view (user ruling
// 2026-11-27: query the seed directly instead of walking the official
// list's pages — the contest tag already carries the event, so the
// in-library view is a plain db page over favs DESC). Returns the page
// rows and the total row count for the pager.
func (s *Store) RosterLocalBooksPaged(ctx context.Context, event, division string, limit, offset int) ([]RosterItem, int, error) {
	clause, args := contestEventMatch("b.contest", event)
	if division != "" {
		clause += " AND b.contest = ?"
		args = append(args, event+division)
	}
	base := `FROM seed.books b LEFT JOIN covers c ON c.nid = b.nid
WHERE b.is_licensed = 0 AND ` + clause
	var total int
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) `+base, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	query := `
SELECT b.nid, b.title, b.author, b.genre, b.form, b.favs, b.status,
       b.est_year, b.words, b.clicks, b.praises, b.price_type,
       (SELECT GROUP_CONCAT(bt.tag) FROM book_tags bt WHERE bt.nid = b.nid) AS tags,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover
FROM seed.books b
LEFT JOIN covers c ON c.nid = b.nid
WHERE b.is_licensed = 0 AND ` + clause + `
ORDER BY (b.favs IS NULL) ASC, b.favs DESC, b.nid
LIMIT ? OFFSET ?`
	args = append(args, limit, offset)
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	items := make([]RosterItem, 0, limit)
	for rows.Next() {
		var (
			item    RosterItem
			gen     sql.NullString
			favs    sql.NullInt64
			words   sql.NullInt64
			clicks  sql.NullInt64
			praises sql.NullInt64
			price   sql.NullString
			tags    sql.NullString
			cover   sql.NullString
			author  sql.NullString
			status  sql.NullString
		)
		var nid int64
		if err := rows.Scan(&nid, &item.Title, &author, &gen, &item.Form,
			&favs, &status, &item.EstYear, &words, &clicks, &praises,
			&price, &tags, &cover); err != nil {
			return nil, 0, err
		}
		item.NID = int(nid)
		item.Author = author.String
		item.Status = status.String
		item.Cover = cover.String
		item.InLibrary = true
		item.Favs = intPtr(favs)
		item.Words = intPtr(words)
		item.Genre = strPtr(gen)
		item.PriceType = strPtr(price)
		item.Clicks = intPtr(clicks)
		item.Praises = intPtr(praises)
		if tags.Valid && tags.String != "" {
			item.Tags = strings.Split(tags.String, ",")
		} else {
			item.Tags = []string{}
		}
		items = append(items, item)
	}
	return items, total, rows.Err()
}

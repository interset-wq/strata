package store

import (
	"context"
	"strings"
)

// InLibBook is the in-library metadata joined into preorder responses for
// nids that exist in seed.books.
type InLibBook struct {
	Author string
	Favs   int64
	Cover  string
}

// PreorderInLib returns library metadata for the given nids; nids missing
// from seed.books are absent from the result (they are the 库外 upstream
// picks the detail page cannot open).
func (s *Store) PreorderInLib(ctx context.Context, nids []int64) (map[int64]InLibBook, error) {
	out := make(map[int64]InLibBook, len(nids))
	if len(nids) == 0 {
		return out, nil
	}
	ph := make([]string, len(nids))
	args := make([]any, len(nids))
	for i, n := range nids {
		ph[i] = "?"
		args[i] = n
	}
	rows, err := s.DB.QueryContext(ctx,
		"SELECT nid, author, favs, COALESCE(cover_url, '') FROM seed.books"+
			" WHERE nid IN ("+strings.Join(ph, ",")+")", args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var nid int64
		var b InLibBook
		if err := rows.Scan(&nid, &b.Author, &b.Favs, &b.Cover); err != nil {
			return nil, err
		}
		out[nid] = b
	}
	return out, rows.Err()
}

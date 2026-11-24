// Generation explorer (est_year × genre): offline aggregates over the seed
// universe for the "how did genres fare across generations" view. The
// median-favourite figure is the favs median of the seed-pool cell (E.30:
// the build-time P50-band mean needed the universe percentile columns,
// which no longer ship; the seed-pool median is the device-computable
// calibre).
package store

import (
	"context"
	"database/sql"
)

// ErasExploreRow is one est_year × genre aggregate cell.
type ErasExploreRow struct {
	EstYear    int      `json:"est_year"`
	Genre      string   `json:"genre"`
	Books      int64    `json:"books"`
	MedianFavs *float64 `json:"median_favs"` // seed-pool favs median (rank (n+1)/2)
}

// ErasExplore returns every universe cell (2007..2026 × non-empty genre).
// Upper bound mirrors build_seed.GEN_MAX (E.30: 2026 is a normal generation).
func (s *Store) ErasExplore(ctx context.Context) ([]ErasExploreRow, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT est_year, genre, n AS books, favs AS median_favs FROM (
  SELECT est_year, genre,
         COUNT(*) OVER (PARTITION BY est_year, genre) AS n,
         favs,
         ROW_NUMBER() OVER (PARTITION BY est_year, genre
                            ORDER BY favs ASC, nid ASC) AS rn
  FROM seed.books
  WHERE is_licensed = 0
    AND est_year BETWEEN 2007 AND 2026
    AND genre IS NOT NULL AND genre != ''
) WHERE rn = (n + 1) / 2
ORDER BY est_year, genre`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []ErasExploreRow
	for rows.Next() {
		var (
			r   ErasExploreRow
			gen sql.NullString
			n   sql.NullInt64
			med sql.NullInt64
		)
		if err := rows.Scan(&r.EstYear, &gen, &n, &med); err != nil {
			return nil, err
		}
		r.Genre = gen.String
		r.Books = n.Int64
		if med.Valid {
			v := float64(med.Int64)
			r.MedianFavs = &v
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

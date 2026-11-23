// Generation explorer (est_year × genre): offline aggregates over the seed
// universe for the "how did genres fare across generations" view. The
// median-favourite figure is the mean of books in the same-generation
// percentile band 0.45–0.55 — fav_pctl is computed per est_year at build
// time, so that band is the P50 in the build's own calibre.
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
	MedianFavs *float64 `json:"median_favs"` // same-generation P50 band mean
}

// ErasExplore returns every universe cell (2007..2025 × non-empty genre).
func (s *Store) ErasExplore(ctx context.Context) ([]ErasExploreRow, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT est_year, genre, COUNT(*) AS books,
       AVG(CASE WHEN fav_pctl BETWEEN 0.45 AND 0.55 THEN favs END) AS median_favs
FROM seed.books
WHERE is_licensed = 0
  AND est_year BETWEEN 2007 AND 2025
  AND genre IS NOT NULL AND genre != ''
GROUP BY est_year, genre
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
			med sql.NullFloat64
		)
		if err := rows.Scan(&r.EstYear, &gen, &r.Books, &med); err != nil {
			return nil, err
		}
		r.Genre = gen.String
		if med.Valid {
			v := med.Float64
			r.MedianFavs = &v
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

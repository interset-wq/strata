// Watchlist heatmap (docs/07 §4): the tracked-books activity calendar —
// per-day aggregates of the observations the background poller recorded.
// Aggregate only: no fabricated full-library series.
package store

import "context"

// HeatmapDay is one day's watchlist activity cell: how many tracked books
// had observations recorded, and how many observation rows landed.
type HeatmapDay struct {
	Day   int64 `json:"day"` // epoch days (observed_at / 86400)
	Books int64 `json:"books"`
	Rows  int64 `json:"rows"`
}

// WatchHeatmap aggregates per-day observation activity across the
// watchlist since the given unix second. Days without activity are
// absent — the client fills the gaps.
func (s *Store) WatchHeatmap(ctx context.Context,
	since int64) ([]HeatmapDay, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT observed_at / 86400 AS day,
       COUNT(DISTINCT nid)  AS books,
       COUNT(*)             AS rows
FROM observations
WHERE nid IN (SELECT nid FROM watchlist)
  AND observed_at >= ?
GROUP BY day
ORDER BY day`, since)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []HeatmapDay
	for rows.Next() {
		var d HeatmapDay
		if err := rows.Scan(&d.Day, &d.Books, &d.Rows); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

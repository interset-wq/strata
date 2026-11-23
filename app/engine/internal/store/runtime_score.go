// Runtime scoring for discovered books (app/docs/18-runtime-metrics.md P2,
// report 24 §8.3): est_year (eras anchors) → conservative form → cps → cqs
// → len_norm, computed once when a discovered row gains detail numbers and
// stored on the row. The conservative form is the words length band — the
// mobile detail page carries no dialogue marker (2026-11-23 probe) — and
// 同人 rows stay unscored: the estimator cannot see their dialogue marker,
// and the E.17 lesson is that misfiled 同人 books are the main cqs pollution.
package store

import (
	"context"
	"database/sql"
	"math"
	"strconv"
	"strings"
)

// scorePendingDiscovered scores every discovered row that gained detail
// numbers (words/favs) but carries no est_year yet. Idempotent and cheap:
// at most a handful of rows exist between detail refreshes.
func (s *Store) scorePendingDiscovered(ctx context.Context) error {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, genre, words, favs, praises FROM discovered
WHERE est_year IS NULL AND words IS NOT NULL AND words >= 2000
  AND favs IS NOT NULL`)
	if err != nil {
		return err
	}
	var batch []struct {
		nid     int64
		genre   sql.NullString
		words   sql.NullInt64
		favs    sql.NullInt64
		praises sql.NullInt64
	}
	for rows.Next() {
		var p struct {
			nid     int64
			genre   sql.NullString
			words   sql.NullInt64
			favs    sql.NullInt64
			praises sql.NullInt64
		}
		if err := rows.Scan(&p.nid, &p.genre, &p.words, &p.favs, &p.praises); err != nil {
			rows.Close()
			return err
		}
		batch = append(batch, p)
	}
	if err := rows.Err(); err != nil {
		return err
	}
	rows.Close()

	for _, p := range batch {
		if err := s.scoreDiscovered(ctx, p.nid, p.genre, p.words, p.favs, p.praises); err != nil {
			return err
		}
	}
	return nil
}

// scoreDiscovered scores one row; every table lookup misses gracefully
// (the calib tables only carry cells the analysis universe could support,
// and μ0 comes from seed_meta so the runtime never recomputes it).
func (s *Store) scoreDiscovered(ctx context.Context, nid int64, genre sql.NullString, words, favs, praises sql.NullInt64) error {
	year, _, ok, err := s.EstimateYear(ctx, nid)
	if err != nil || !ok {
		return err
	}
	w := words.Int64
	band := "long"
	if w <= 50_000 {
		band = "short"
	} else if w <= 150_000 {
		band = "medium"
	}
	form := band
	tongRen := genre.Valid && strings.Contains(genre.String, "同人")

	var cqs, cps, ln any
	var cqsState any
	if !tongRen && genre.Valid && favs.Int64 >= 10 {
		var med sql.NullFloat64
		if err := s.DB.QueryRowContext(ctx, `
SELECT med FROM seed.calib_cps_median
WHERE form = ? AND est_year = ? AND band = ? AND genre = ?`,
			form, year, band, genre.String).Scan(&med); err == nil && med.Valid {
			cps = math.Log1p(float64(favs.Int64)) - med.Float64
		}
	}
	if !tongRen && genre.Valid && favs.Int64 >= 1000 && praises.Valid {
		var p50, p75, p90 sql.NullFloat64
		if err := s.DB.QueryRowContext(ctx, `
SELECT p50, p75, p90 FROM seed.calib_fav_bounds
WHERE form = ? AND est_year = ?`, form, year).
			Scan(&p50, &p75, &p90); err == nil && p50.Valid {
			f := float64(favs.Int64)
			fband := "P50-"
			if f >= p90.Float64 {
				fband = "P90+"
			} else if f >= p75.Float64 {
				fband = "P75-90"
			} else if f >= p50.Float64 {
				fband = "P50-75"
			}
			if fband != "P50-" {
				var med sql.NullFloat64
				var cellN int
				if err := s.DB.QueryRowContext(ctx, `
SELECT med, cell_n FROM seed.calib_cqs_median
WHERE form = ? AND est_year = ? AND genre = ? AND fband = ?`,
					form, year, genre.String, fband).Scan(&med, &cellN); err == nil && med.Valid {
					mu0 := 0.232
					var m string
					if err := s.DB.QueryRowContext(ctx,
						"SELECT value FROM seed.seed_meta WHERE key = 'cqs_mu0'").
						Scan(&m); err == nil {
						if v, perr := strconv.ParseFloat(m, 64); perr == nil {
							mu0 = v
						}
					}
					logPrS := math.Log((float64(praises.Int64) + 500*mu0) /
						(float64(favs.Int64) + 500))
					cqs = logPrS - med.Float64
					if cellN >= 20 {
						cqsState = "stable"
					} else {
						cqsState = "low"
					}
					var lo, hi sql.NullFloat64
					if err := s.DB.QueryRowContext(ctx, `
SELECT lo, hi FROM seed.calib_len_anchors WHERE form = ?`, form).
						Scan(&lo, &hi); err == nil && lo.Valid && hi.Valid && lo.Float64 > 0 {
						clipped := math.Min(math.Max(float64(w), lo.Float64), hi.Float64)
						ln = math.Log(clipped/lo.Float64) / math.Log(hi.Float64/lo.Float64)
					}
				}
			}
		}
	}
	_, err = s.DB.ExecContext(ctx, `
UPDATE discovered SET est_year = ?, form = ?, cqs = ?, cqs_state = ?,
  cps = ?, len_norm = ? WHERE nid = ?`,
		year, form, cqs, cqsState, cps, ln, nid)
	return err
}

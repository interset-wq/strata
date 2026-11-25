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
	sc, err := s.compute(ctx, nid, genre, words, favs, praises)
	if err != nil {
		return err
	}
	if sc.year == 0 {
		return nil
	}
	_, err = s.DB.ExecContext(ctx, `
UPDATE discovered SET est_year = ?, form = ?, cqs = ?, cqs_state = ?,
  cps = ?, len_norm = ? WHERE nid = ?`,
		sc.year, sc.form, sc.cqs, sc.state, sc.cps, sc.lenN, nid)
	return err
}

// RescoreDiscovered re-scores one discovered row after its numbers change.
// A missing row (ErrNoRows) is a no-op.
func (s *Store) RescoreDiscovered(ctx context.Context, nid int64) error {
	var genre sql.NullString
	var words, favs, praises sql.NullInt64
	err := s.DB.QueryRowContext(ctx,
		"SELECT genre, words, favs, praises FROM discovered WHERE nid = ?", nid).
		Scan(&genre, &words, &favs, &praises)
	if err != nil {
		return err
	}
	return s.scoreDiscovered(ctx, nid, genre, words, favs, praises)
}

// RescoreBookMeta recomputes the runtime metrics for one book_meta row (the
// record a detail refresh just wrote) and stores them on the row — this is
// what makes 自动收录 compute every derived column (user 2026-11-25). No-op
// when the row lacks scoreable numbers or the anchors cannot date the book.
func (s *Store) RescoreBookMeta(ctx context.Context, nid int64) error {
	var genre sql.NullString
	var words, favs, praises sql.NullInt64
	err := s.DB.QueryRowContext(ctx,
		"SELECT genre, words, favs, praises FROM book_meta WHERE nid = ?", nid).
		Scan(&genre, &words, &favs, &praises)
	if err != nil {
		return err
	}
	sc, err := s.compute(ctx, nid, genre, words, favs, praises)
	if err != nil {
		return err
	}
	if sc.year == 0 {
		return nil
	}
	_, err = s.DB.ExecContext(ctx, `
UPDATE book_meta SET est_year = ?, form = ?, cqs = ?, cqs_state = ?,
  cps = ?, len_norm = ? WHERE nid = ?`,
		sc.year, sc.form, sc.cqs, sc.state, sc.cps, sc.lenN, nid)
	return err
}

// ScorePendingBookMeta backfills every book_meta row admitted before the
// metric columns existed (cqs IS NULL). Idempotent — rows whose numbers the
// calib tables cannot support stay NULL and are retried on next start.
func (s *Store) ScorePendingBookMeta(ctx context.Context) error {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid FROM book_meta
WHERE cqs IS NULL AND words IS NOT NULL AND words >= 2000
  AND favs IS NOT NULL`)
	if err != nil {
		return err
	}
	var nids []int64
	for rows.Next() {
		var n int64
		if err := rows.Scan(&n); err != nil {
			rows.Close()
			return err
		}
		nids = append(nids, n)
	}
	rows.Close()
	for _, n := range nids {
		if err := s.RescoreBookMeta(ctx, n); err != nil {
			return err
		}
	}
	return nil
}

// score carries the runtime-metric outputs for one row. A zero year means
// "nothing to store" — the anchors could not date the row.
type score struct {
	year  int
	form  string
	cqs   any
	state any
	cps   any
	lenN  any
}

// compute runs the metric formulas over one row's inputs. Every table
// lookup misses gracefully (the calib tables only carry cells the analysis
// universe could support, and μ0 comes from seed_meta so the runtime never
// recomputes it).
func (s *Store) compute(ctx context.Context, nid int64, genre sql.NullString, words, favs, praises sql.NullInt64) (score, error) {
	var sc score
	year, _, ok, err := s.EstimateYear(ctx, nid)
	if err != nil || !ok {
		return sc, err
	}
	if !words.Valid || words.Int64 < 2000 {
		// Nothing scoreable: keep the dated year but no metrics.
		sc.year = year
		sc.form = "long"
		return sc, nil
	}
	w := words.Int64
	band := "long"
	if w <= 50_000 {
		band = "short"
	} else if w <= 150_000 {
		band = "medium"
	}
	sc.year = year
	sc.form = band
	tongRen := genre.Valid && strings.Contains(genre.String, "同人")

	if !tongRen && genre.Valid && favs.Int64 >= 10 {
		var med sql.NullFloat64
		if err := s.DB.QueryRowContext(ctx, `
SELECT med FROM seed.calib_cps_median
WHERE form = ? AND est_year = ? AND band = ? AND genre = ?`,
			band, year, band, genre.String).Scan(&med); err == nil && med.Valid {
			sc.cps = math.Log1p(float64(favs.Int64)) - med.Float64
		}
	}
	if !tongRen && genre.Valid && favs.Int64 >= 1000 && praises.Valid {
		var p50, p75, p90 sql.NullFloat64
		if err := s.DB.QueryRowContext(ctx, `
SELECT p50, p75, p90 FROM seed.calib_fav_bounds
WHERE form = ? AND est_year = ?`, band, year).
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
					band, year, genre.String, fband).Scan(&med, &cellN); err == nil && med.Valid {
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
					sc.cqs = logPrS - med.Float64
					if cellN >= 20 {
						sc.state = "stable"
					} else {
						sc.state = "low"
					}
					var lo, hi sql.NullFloat64
					if err := s.DB.QueryRowContext(ctx, `
SELECT lo, hi FROM seed.calib_len_anchors WHERE form = ?`, band).
						Scan(&lo, &hi); err == nil && lo.Valid && hi.Valid && lo.Float64 > 0 {
						clipped := math.Min(math.Max(float64(w), lo.Float64), hi.Float64)
						sc.lenN = math.Log(clipped/lo.Float64) / math.Log(hi.Float64/lo.Float64)
					}
				}
			}
		}
	}
	return sc, nil
}

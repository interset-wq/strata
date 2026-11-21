package store

import (
	"context"
	"database/sql"
	"time"
)

const simulateSource = "simulate"

// SimulationSummary describes one dev-simulation run (docs/07 workbench
// dev aid, /strata/dev/simulate).
type SimulationSummary struct {
	NID        int64  `json:"nid"`
	Days       int    `json:"days"`
	Rows       int    `json:"rows"`      // observation rows written (days - gap_days)
	GapDays    int    `json:"gap_days"`  // days with no row — data gap, not 断更
	FlatDays   int    `json:"flat_days"` // observed days with Δwords = 0 — 断更
	StartWords int64  `json:"start_words"`
	EndWords   int64  `json:"end_words"`
	StartFavs  int64  `json:"start_favs"`
	EndFavs    int64  `json:"end_favs"`
	Status     string `json:"status"`
	Source     string `json:"source"`
}

// simRNG is a small deterministic LCG: the same (nid, days) always
// regenerates the identical metric values (timestamps anchor to the
// run day, by design — the series must end today), so tests can pin
// values and re-runs stay comparable.
type simRNG struct{ s uint64 }

func newSimRNG(nid int64, days int) *simRNG {
	return &simRNG{s: uint64(nid)*0x9E3779B97F4A7C15 + uint64(days) | 1}
}

func (r *simRNG) next() uint64 {
	r.s = r.s*6364136223846793005 + 1442695040888963407
	return r.s >> 11
}

// intN returns a uniform value in [0, n).
func (r *simRNG) intN(n int) int {
	return int(r.next() % uint64(n))
}

// SimulateObservations generates `days` of synthetic observation rows for
// one nid in user.db — a dev aid for the author workbench (docs/07),
// whose real data takes weeks of daily polling to accumulate. The series
// starts from the seed book's current counters (the seed is a 2026-05
// snapshot, so simulated growth ends above it, as live counters would;
// out-of-seed books get a neutral baseline) and covers the six workbench
// metrics: words / favs / praises / short_comments / long_comments /
// clicks (docs/07 §0/§3).
//
// Three day classes exercise every rendering path of the workbench:
//   - update day (~80%): Δwords 2,500–6,499, straddling the 3,000
//     full-attendance threshold (docs/07 §2)
//   - flat day (~12%): observed but Δwords = 0 — 断更 (an update miss)
//   - gap day (~8%): no observation row at all — 数据缺口; counters still
//     grow across it, so the next row's delta reads "含 N 天累计"
//
// A book that is not 连载中 in the seed never gains words (all flat).
// Re-running is idempotent: the nid's existing simulate rows are
// replaced; real observation rows (source 'detail'/'app') are untouched.
// seed.db is never touched.
func (s *Store) SimulateObservations(ctx context.Context, nid int64, days int) (SimulationSummary, error) {
	rng := newSimRNG(nid, days)

	var w, c, f, p sql.NullInt64
	var st sql.NullString
	err := s.DB.QueryRowContext(ctx, `
SELECT words, clicks, favs, praises, status FROM seed.books WHERE nid = ?`, nid).
		Scan(&w, &c, &f, &p, &st)
	if err != nil && err != sql.ErrNoRows {
		return SimulationSummary{}, err
	}
	words, clicks, favs, praises := w.Int64, c.Int64, f.Int64, p.Int64
	status := "连载中"
	if st.Valid {
		status = st.String
	}
	serializing := status == "连载中"
	startWords, startFavs := words, favs

	type simRow struct {
		observedAt int64
		values     [6]int64 // clicks, favs, praises, words, shortC, longC
		updatedAt  string
	}
	rows := make([]simRow, 0, days)
	gapDays, flatDays := 0, 0
	shortC, longC := int64(0), int64(0)
	var lastUpdate *time.Time

	now := time.Now()
	for i := days - 1; i >= 0; i-- {
		day := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0,
			time.Local).AddDate(0, 0, -i)
		roll := rng.intN(100)
		kind := "update"
		switch {
		case roll < 8:
			kind = "gap"
		case roll < 20:
			kind = "flat"
		}
		if !serializing {
			kind = "flat" // 已完结：永不加字
		}
		var dw, df, dc, dsc, dlc int
		switch kind {
		case "gap":
			if serializing {
				dw = 2500 + rng.intN(4000)
			}
			df = 5 + rng.intN(20)
			dc = 400 + rng.intN(800)
			if rng.intN(5) == 0 {
				dsc = 1
			}
			if rng.intN(12) == 0 {
				dlc = 1
			}
		case "flat":
			df = 3 + rng.intN(12)
			dc = 300 + rng.intN(700)
			if rng.intN(4) == 0 {
				dsc = 1
			}
			if rng.intN(10) == 0 {
				dlc = 1
			}
		default:
			dw = 2500 + rng.intN(4000)
			df = 15 + rng.intN(66)
			dc = 800 + rng.intN(2200)
			if rng.intN(5) < 3 {
				dsc = 1 + rng.intN(2)
			}
			if rng.intN(4) == 0 {
				dlc = 1
			}
		}
		dpraise := int(float64(df) * (0.25 + float64(rng.intN(26))/100.0))
		words += int64(dw)
		favs += int64(df)
		praises += int64(dpraise)
		clicks += int64(dc)
		shortC += int64(dsc)
		longC += int64(dlc)

		if kind == "gap" {
			gapDays++
			continue // no observation row this day — 数据缺口
		}
		if kind == "flat" {
			flatDays++
		} else {
			lastUpdate = &day
		}
		ua := lastUpdate
		if ua == nil {
			ua = &day
		}
		rows = append(rows, simRow{
			observedAt: day.Add(12 * time.Hour).Unix(),
			values:     [6]int64{clicks, favs, praises, words, shortC, longC},
			updatedAt:  ua.Format("2006-01-02T15:04:05"),
		})
	}

	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return SimulationSummary{}, err
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx,
		`DELETE FROM observations WHERE nid = ? AND source = ?`,
		nid, simulateSource); err != nil {
		return SimulationSummary{}, err
	}
	stmt, err := tx.PrepareContext(ctx, `
INSERT OR REPLACE INTO observations(nid, observed_at, clicks, favs, praises, words,
 short_comments, long_comments, status, updated_at, source)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
	if err != nil {
		return SimulationSummary{}, err
	}
	defer stmt.Close()
	for _, r := range rows {
		if _, err := stmt.ExecContext(ctx, nid, r.observedAt,
			r.values[0], r.values[1], r.values[2], r.values[3],
			r.values[4], r.values[5], status, r.updatedAt, simulateSource); err != nil {
			return SimulationSummary{}, err
		}
	}
	if err := tx.Commit(); err != nil {
		return SimulationSummary{}, err
	}

	return SimulationSummary{
		NID: nid, Days: days, Rows: len(rows),
		GapDays: gapDays, FlatDays: flatDays,
		StartWords: startWords, EndWords: words,
		StartFavs: startFavs, EndFavs: favs,
		Status: status, Source: simulateSource,
	}, nil
}

// DeleteSimulatedObservations removes one nid's dev-simulation rows
// (source='simulate' only); real observation rows are never touched.
func (s *Store) DeleteSimulatedObservations(ctx context.Context, nid int64) (int64, error) {
	res, err := s.DB.ExecContext(ctx,
		`DELETE FROM observations WHERE nid = ? AND source = ?`, nid, simulateSource)
	if err != nil {
		return 0, err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return 0, err
	}
	return n, nil
}

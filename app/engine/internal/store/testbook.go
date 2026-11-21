package store

import (
	"context"
	"database/sql"
	"time"
)

// TestBookNID is the fixed fictional nid of the workbench test book
// (docs/07 dev aid, settings test switch). It sits far above the real
// platform's nid range so it can never collide with seed or live data;
// its nid-dating extrapolates beyond the anchors (low confidence),
// which is honest for a fictional book.
const TestBookNID = int64(99000001)

// The test book's fixed identity.
const (
	TestBookTitle     = "工作台测试·全勤纪"
	TestBookAuthor    = "工作台测试"
	TestBookGenre     = "魔幻"
	TestBookSummary   = "作者工作台（docs/07）开发用的虚构测试书：内置 60 天模拟" +
		"观测数据，用于验证更新热力图 / 六指标折线 / 同期对照。全部数据本地" +
		"生成，与官方无关；在「设置 → 测试工具」中开关。"
)

// TestBook is the virtual test book's state — the settings switch's
// source of truth.
type TestBook struct {
	NID     int64  `json:"nid"`
	Present bool   `json:"present"`
	Title   string `json:"title,omitempty"`
	Days    int    `json:"days,omitempty"`
	Rows    int    `json:"rows,omitempty"`
}

// InjectTestBook materializes the fictional workbench book into
// user.db (docs/07 dev aid — the settings test switch). It mimics the
// real out-of-seed flow (search discovery → detail fetch), so every
// existing pathway finds the book without special-casing:
//   - a simulated observation series (SimulateObservations,
//     source='simulate', neutral out-of-seed baseline) — the final row
//     becomes the book's "current" counters
//   - a book_meta row (what makes /books/:nid serve the overlay view)
//   - a discovered row (the watchlist's title/genre COALESCE finds it;
//     收录管理 lists it)
//   - a watchlist row, role=self, polling OFF: the fictional book has
//     no official page, so background polling would only fail; the user
//     may activate it to exercise the failure path (docs/07 §4)
//
// Idempotent: re-injecting replaces the prior state. seed.db is never
// touched.
func (s *Store) InjectTestBook(ctx context.Context, days int) (TestBook, error) {
	nid := TestBookNID

	// 1. History first: the series' final row is the book's "current"
	//    counters (the seed is a snapshot; live counters sit above it —
	//    same behaviour for the test book).
	summary, err := s.SimulateObservations(ctx, nid, days)
	if err != nil {
		return TestBook{}, err
	}

	var (
		clicks, favs, praises, words sql.NullInt64
		status, updatedAt            sql.NullString
	)
	err = s.DB.QueryRowContext(ctx, `
SELECT clicks, favs, praises, words, status, updated_at
FROM observations WHERE nid = ? ORDER BY observed_at DESC LIMIT 1`, nid).
		Scan(&clicks, &favs, &praises, &words, &status, &updatedAt)
	if err != nil {
		return TestBook{}, err
	}
	now := time.Now().Unix()
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return TestBook{}, err
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx, `
INSERT OR REPLACE INTO book_meta(nid, source, fetched_at, title, author, genre,
 price_type, status, cover_url, summary, words, favs, praises, clicks, updated_at)
VALUES (?, 'simulate', ?, ?, ?, ?, '免费', ?, NULL, ?, ?, ?, ?, ?, ?)`,
		nid, now, TestBookTitle, TestBookAuthor, TestBookGenre,
		status.String, TestBookSummary, words.Int64, favs.Int64, praises.Int64,
		clicks.Int64, updatedAt.String); err != nil {
		return TestBook{}, err
	}
	if _, err := tx.ExecContext(ctx, `
INSERT OR REPLACE INTO discovered(nid, title, author, genre, words, favs, praises,
 cover_url, summary, source, observed_at)
VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 'simulate', ?)`,
		nid, TestBookTitle, TestBookAuthor, TestBookGenre, words.Int64,
		favs.Int64, praises.Int64, TestBookSummary, now); err != nil {
		return TestBook{}, err
	}
	if _, err := tx.ExecContext(ctx, `
INSERT OR REPLACE INTO watchlist(nid, role, added_at, poll_enabled, poll_interval)
VALUES (?, 'self', ?, 0, 86400)`,
		nid, now); err != nil {
		return TestBook{}, err
	}
	if err := tx.Commit(); err != nil {
		return TestBook{}, err
	}

	return TestBook{NID: nid, Present: true, Title: TestBookTitle,
		Days: summary.Days, Rows: summary.Rows}, nil
}

// RemoveTestBook tears the fictional test book down: overlay metadata,
// discovery row, watchlist entry and observation rows. The nid is
// reserved for the test book, so deleting all of its observations is
// safe (no real book can have that nid).
func (s *Store) RemoveTestBook(ctx context.Context) (TestBook, error) {
	nid := TestBookNID
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return TestBook{}, err
	}
	defer tx.Rollback()
	for _, q := range []string{
		`DELETE FROM book_meta WHERE nid = ?`,
		`DELETE FROM discovered WHERE nid = ?`,
		`DELETE FROM watchlist WHERE nid = ?`,
		`DELETE FROM observations WHERE nid = ?`,
	} {
		if _, err := tx.ExecContext(ctx, q, nid); err != nil {
			return TestBook{}, err
		}
	}
	if err := tx.Commit(); err != nil {
		return TestBook{}, err
	}
	return TestBook{NID: nid, Present: false}, nil
}

// TestBookState reports whether the fictional test book is injected and
// how many observation rows it carries (the settings switch's read
// side).
func (s *Store) TestBookState(ctx context.Context) (TestBook, error) {
	nid := TestBookNID
	var title sql.NullString
	err := s.DB.QueryRowContext(ctx,
		`SELECT title FROM book_meta WHERE nid = ?`, nid).Scan(&title)
	if err != nil {
		if err == sql.ErrNoRows {
			return TestBook{NID: nid, Present: false}, nil
		}
		return TestBook{}, err
	}
	var rows int
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM observations WHERE nid = ?`, nid).Scan(&rows); err != nil {
		return TestBook{}, err
	}
	return TestBook{NID: nid, Present: true, Title: title.String, Rows: rows}, nil
}

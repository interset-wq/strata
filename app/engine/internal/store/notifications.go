package store

import (
	"context"
	"database/sql"
)

// Notification is one follow-tab event row (watch_events, user.db v12):
// a tracked book's observed change (kind = words|favs|status), written by
// the background watcher and surfaced via /strata/notifications. Display
// only — events never feed admission, ordering or scoring (docs/12 red
// line). Joined to seed.books for the display title.
type Notification struct {
	NID      int64    `json:"nid"`
	Title    string   `json:"title"`
	Kind     string   `json:"kind"`
	OldValue *string  `json:"old_value"`
	NewValue *string  `json:"new_value"`
	At       int64    `json:"created_at"`
	Read     bool     `json:"read"`
}

// LastObservation returns the newest observation row of one book (the
// watcher diffs against it to detect changes). sql.ErrNoRows when the
// book has none yet.
func (s *Store) LastObservation(ctx context.Context, nid int64) (
	favs, words sql.NullInt64, status sql.NullString, err error) {
	err = s.DB.QueryRowContext(ctx, `
SELECT favs, words, COALESCE(status, '') FROM observations
 WHERE nid = ? ORDER BY observed_at DESC LIMIT 1`, nid).
		Scan(&favs, &words, &status)
	return
}

// RecordWatchEvent appends one change event. Same (nid, kind, at-second)
// rows are idempotent via the primary key; values are stringified so the
// display layer never needs to know the metric's domain.
func (s *Store) RecordWatchEvent(ctx context.Context, nid int64, kind,
	oldValue, newValue string, at int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO watch_events(nid, kind, old_value, new_value, created_at, read)
VALUES (?, ?, ?, ?, ?, 0)`, nid, kind, oldValue, newValue, at)
	return err
}

// Notifications returns every follow event, newest first, joined with the
// seed title. Unread first is not enforced — the page renders in time
// order and the unread count is returned separately.
func (s *Store) Notifications(ctx context.Context, limit int) (
	[]*Notification, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT e.nid, COALESCE(b.title, ''), e.kind, e.old_value, e.new_value,
       e.created_at, e.read
  FROM watch_events e
  LEFT JOIN seed.books b ON b.nid = e.nid
 ORDER BY e.created_at DESC, e.rowid DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []*Notification{}
	for rows.Next() {
		var (
			n       Notification
			oldV    sql.NullString
			newV    sql.NullString
			readInt int
		)
		if err := rows.Scan(&n.NID, &n.Title, &n.Kind, &oldV, &newV,
			&n.At, &readInt); err != nil {
			return nil, err
		}
		n.OldValue = strPtr(oldV)
		n.NewValue = strPtr(newV)
		n.Read = readInt == 1
		items = append(items, &n)
	}
	return items, rows.Err()
}

// UnreadNotifications counts unread follow events.
func (s *Store) UnreadNotifications(ctx context.Context) (int, error) {
	var n int
	err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM watch_events WHERE read = 0`).Scan(&n)
	return n, err
}

// MarkNotificationsRead flips every event to read (the list is small and
// the tab is a single-purpose surface — no per-row selection).
func (s *Store) MarkNotificationsRead(ctx context.Context, at int64) error {
	_, err := s.DB.ExecContext(ctx,
		`UPDATE watch_events SET read = 1 WHERE read = 0`)
	return err
}

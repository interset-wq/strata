package store

import (
	"context"
	"testing"
	"time"
)

// user.db write paths (docs/02 §3): watchlist (v6: the single
// user-interest list — the former bookshelf merged in as inactive
// entries), observation time series, preferences, browsing footprint,
// covers, and refresh-cooldown stamping. Everything stays in the
// writable user DB; the bundled seed is never touched.

func TestWatchlistAddToggleRemove(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	// v6: one list — active=false is the former bookshelf entry
	// (save-only), active=true is tracked.
	if err := st.WatchAdd(ctx, 1001, 100, false); err != nil {
		t.Fatal(err)
	}
	if err := st.WatchAdd(ctx, 1002, 200, true); err != nil {
		t.Fatal(err)
	}
	// re-adding an existing book must be a no-op, not a duplicate row
	if err := st.WatchAdd(ctx, 1001, 999, true); err != nil {
		t.Fatal(err)
	}
	items, err := st.WatchList(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 {
		t.Fatalf("watchlist size = %d, want 2", len(items))
	}
	wantActive := map[int64]bool{1001: false, 1002: true}
	for _, it := range items {
		if it.Title == "" {
			t.Fatalf("watchlist item %d has empty title (seed join broken)", it.NID)
		}
		if want, ok := wantActive[it.NID]; !ok || it.Active != want {
			t.Fatalf("watchlist item %d active = %v, want %v", it.NID, it.Active, want)
		}
	}
	// toggling activation flips poll_enabled without touching the row
	if err := st.WatchSetActive(ctx, 1001, true); err != nil {
		t.Fatal(err)
	}
	items, err = st.WatchList(ctx)
	if err != nil {
		t.Fatal(err)
	}
	for _, it := range items {
		if it.NID == 1001 && !it.Active {
			t.Fatalf("1001 not active after toggle: %+v", items)
		}
	}
	if err := st.WatchRemove(ctx, 1001); err != nil {
		t.Fatal(err)
	}
	items, err = st.WatchList(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 1002 {
		t.Fatalf("after remove: %+v, want only 1002", items)
	}
}

func TestObservationsInsertDedupeAndPrune(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	now := time.Now().Unix()
	old := now - 200*24*3600 // beyond the 180-day retention window
	if err := st.InsertObservation(ctx, 1002, old, nil, nil, nil, nil, nil, nil); err != nil {
		t.Fatal(err)
	}
	// same-(nid, second) insert is deduped by the primary key
	if err := st.InsertObservation(ctx, 1002, old, nil, nil, nil, nil, nil, nil); err != nil {
		t.Fatal(err)
	}
	favs := int64(42)
	status := "连载中"
	if err := st.InsertObservation(ctx, 1002, now, nil, &favs, nil, nil, &status, nil); err != nil {
		t.Fatal(err)
	}
	got, err := st.Observations(ctx, 1002)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 {
		t.Fatalf("observations = %d, want 2 (same-second deduped)", len(got))
	}
	if got[0].ObservedAt != now || got[0].Favs == nil || *got[0].Favs != 42 ||
		got[0].Status == nil || *got[0].Status != "连载中" {
		t.Fatalf("newest row wrong: %+v", got[0])
	}
	n, err := st.PruneObservations(ctx, time.Unix(now, 0))
	if err != nil {
		t.Fatal(err)
	}
	if n < 1 {
		t.Fatalf("prune removed %d, want >= 1 (the 200-day-old row)", n)
	}
	got, err = st.Observations(ctx, 1002)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].ObservedAt != now {
		t.Fatalf("after prune: %+v, want only the recent row", got)
	}
}

func TestPrefsRoundTrip(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	if v, ok, err := st.Pref(ctx, "nope"); err != nil || ok || v != "" {
		t.Fatalf("absent pref = (%q, %v, %v), want empty", v, ok, err)
	}
	if err := st.SetPref(ctx, "k", "v1"); err != nil {
		t.Fatal(err)
	}
	v, ok, err := st.Pref(ctx, "k")
	if err != nil || !ok || v != "v1" {
		t.Fatalf("pref = (%q, %v, %v), want v1", v, ok, err)
	}
	if err := st.SetPref(ctx, "k", "v2"); err != nil {
		t.Fatal(err)
	}
	v, _, _ = st.Pref(ctx, "k")
	if v != "v2" {
		t.Fatalf("pref after overwrite = %q, want v2", v)
	}
}

func TestRecordBrowsingAndRecentHistory(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	now := time.Now().Unix()
	if err := st.RecordBrowsing(ctx, 1002, now); err != nil {
		t.Fatal(err)
	}
	if err := st.RecordBrowsing(ctx, 1001, now-100); err != nil {
		t.Fatal(err)
	}
	// re-opening an older entry bumps it to the front (upsert)
	if err := st.RecordBrowsing(ctx, 1001, now+100); err != nil {
		t.Fatal(err)
	}
	items, err := st.RecentHistory(ctx, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 1001 || items[1].NID != 1002 {
		t.Fatalf("history = %+v, want [1001 1002] newest first", items)
	}
	if items[0].Title == "" {
		t.Fatal("history item lost its seed title join")
	}
}

func TestUpsertCoverAndCover(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	if err := st.UpsertCover(ctx, 1003, "/covers/a.jpg", 1); err != nil {
		t.Fatal(err)
	}
	if c, err := st.Cover(ctx, 1003); err != nil || c != "/covers/a.jpg" {
		t.Fatalf("cover = (%q, %v), want /covers/a.jpg", c, err)
	}
	if err := st.UpsertCover(ctx, 1003, "/covers/b.jpg", 2); err != nil {
		t.Fatal(err)
	}
	if c, _ := st.Cover(ctx, 1003); c != "/covers/b.jpg" {
		t.Fatalf("cover after upsert = %q, want /covers/b.jpg", c)
	}
	if c, err := st.Cover(ctx, 1009); err != nil || c != "" {
		t.Fatalf("never-set cover = (%q, %v), want empty", c, err)
	}
}

func TestWatchlistCycle(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	now := time.Now().Unix()
	if err := st.WatchAdd(ctx, 1004, now, true); err != nil {
		t.Fatal(err)
	}
	// re-adding must stay one row
	if err := st.WatchAdd(ctx, 1004, now+1, true); err != nil {
		t.Fatal(err)
	}
	items, err := st.WatchList(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].NID != 1004 || items[0].Role != "self" {
		t.Fatalf("watchlist = %+v, want one 1004/self row", items)
	}
	// never polled => due
	due, err := st.WatchDue(ctx, now+10, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 1 || due[0] != 1004 {
		t.Fatalf("due = %v, want [1004]", due)
	}
	if err := st.WatchPollDone(ctx, 1004, now+10); err != nil {
		t.Fatal(err)
	}
	// default poll_interval is 86400s: not due again right after
	due, err = st.WatchDue(ctx, now+20, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 0 {
		t.Fatalf("due after poll = %v, want empty", due)
	}
	if err := st.WatchRemove(ctx, 1004); err != nil {
		t.Fatal(err)
	}
	items, _ = st.WatchList(ctx)
	if len(items) != 0 {
		t.Fatalf("watchlist after remove = %+v, want empty", items)
	}
}

func TestRefreshAttemptRecordFinish(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()
	now := time.Now().Unix()
	if a, err := st.RefreshAttempt(ctx, 1005); err != nil || a != nil {
		t.Fatalf("never-refreshed = (%+v, %v), want nil", a, err)
	}
	if err := st.RecordRefreshAttempt(ctx, 1005, now, "pending"); err != nil {
		t.Fatal(err)
	}
	a, err := st.RefreshAttempt(ctx, 1005)
	if err != nil || a == nil || a.AttemptedAt != now || a.State != "pending" {
		t.Fatalf("attempt = %+v, want pending@%d", a, now)
	}
	if err := st.FinishRefreshAttempt(ctx, 1005, now, "ok"); err != nil {
		t.Fatal(err)
	}
	a, _ = st.RefreshAttempt(ctx, 1005)
	if a == nil || a.State != "ok" {
		t.Fatalf("state after finish = %+v, want ok", a)
	}
	// a newer attempt makes the older finish a no-op
	if err := st.RecordRefreshAttempt(ctx, 1005, now+10, "pending"); err != nil {
		t.Fatal(err)
	}
	if err := st.FinishRefreshAttempt(ctx, 1005, now, "stale"); err != nil {
		t.Fatal(err)
	}
	a, _ = st.RefreshAttempt(ctx, 1005)
	if a == nil || a.AttemptedAt != now+10 || a.State != "pending" {
		t.Fatalf("stale finish clobbered newer attempt: %+v", a)
	}
}

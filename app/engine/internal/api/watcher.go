package api

import (
	"context"
	"log"
	"time"

	"strata/engine/internal/crawl"
)

// watcherTick is the scheduling cadence: once per tick the worker asks the
// store for due watchlist books and polls each through the background lane.
const watcherTick = time.Minute

// watcherPollLimit caps how many books are polled per tick so a large
// watchlist cannot monopolize the global limiter (docs/06 survival rule:
// foreground requests always outrank background ones).
const watcherPollLimit = 5

// startWatcher launches the background poll worker: it periodically picks
// due watchlist books, fetches their mobile detail page through a background
// limiter slot (three-state verdict, docs/05 §4.3), appends an observation
// row for alive pages, and stamps last_poll_at either way. Failures are
// stamped too, so a bad book cannot wedge the queue; nothing here touches
// the recommendation signal whitelist (docs/12 §3.2).
func (s *Server) startWatcher(ctx context.Context) {
	if s.watcherStarted {
		return
	}
	s.watcherStarted = true
	go func() {
		ticker := time.NewTicker(watcherTick)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				s.pollDue(ctx)
			}
		}
	}()
}

// pollDue polls every due book in this tick, serially, through the
// background lane of the global limiter.
func (s *Server) pollDue(ctx context.Context) {
	now := time.Now().Unix()
	nids, err := s.store.WatchDue(ctx, now, watcherPollLimit)
	if err != nil {
		log.Printf("watcher: due query: %v", err)
		return
	}
	for _, nid := range nids {
		select {
		case <-ctx.Done():
			return
		default:
		}
		s.pollOne(ctx, nid)
	}
}

// pollOne fetches one book through a background slot and writes the
// observation when the page is alive. Only alive pages are written;
// dead/zombie pages only update last_poll_at (their data is stale, not
// absent — the data page distinguishes the two).
func (s *Server) pollOne(ctx context.Context, nid int64) {
	pctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// App API enhancement first (same contract as bookRefresh); any failure
	// silently degrades to the mobile HTML baseline.
	if s.appAPI {
		if app, aerr := crawl.FetchAppNovel(pctx, s.client, s.limiter, nid, false); aerr == nil {
			clicks, favs, words := app.ViewTimes, app.MarkCount, app.CharCount
			status := map[bool]string{true: "已完结", false: "连载中"}[app.IsFinish]
			updatedAt := app.LastUpdateTime
			observedAt := time.Now().Unix()
			_ = s.store.InsertObservation(pctx, nid, observedAt,
				&clicks, &favs, nil, &words, &status, &updatedAt)
			if app.NovelCover != "" {
				_ = s.store.UpsertCover(pctx, nid, app.NovelCover, observedAt)
			}
			_ = s.store.WatchPollDone(pctx, nid, observedAt)
			return
		}
	}

	state, d, observedAt, err := crawl.FetchDetail(pctx, s.client, s.limiter, nid, false)
	if err != nil {
		// Stamp even on failure so a persistently bad book does not retry
		// every tick; the next poll happens after its full interval.
		_ = s.store.WatchPollDone(pctx, nid, time.Now().Unix())
		return
	}
	if state == crawl.DetailAlive && d != nil {
		favs, praises, words := d.Favs, d.Praises, d.Words
		status, updatedAt := d.Status, d.UpdatedAt
		_ = s.store.InsertObservation(pctx, nid, observedAt,
			nil, &favs, &praises, &words, &status, &updatedAt)
	}
	_ = s.store.WatchPollDone(pctx, nid, time.Now().Unix())
}

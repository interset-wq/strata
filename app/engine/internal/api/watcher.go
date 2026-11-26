package api

import (
	"context"
	"database/sql"
	"log"
	"strconv"
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
// absent — the data page distinguishes the two). Alive fetches diff the
// fresh observation against the previous one and record watch_events for
// every changed metric (follow-tab notifications, user.db v12).
func (s *Server) pollOne(ctx context.Context, nid int64) {
	pctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	// Pre-fetch baseline for the change diff (notification layer).
	prevFavs, prevWords, prevStatus, _ := s.store.LastObservation(pctx, nid)

	// App API enhancement first (same contract as bookRefresh); any failure
	// silently degrades to the mobile HTML baseline.
	if s.appAPI {
		if app, aerr := crawl.FetchAppNovel(pctx, s.client, s.limiter, nid, false); aerr == nil {
			observedAt := time.Now().Unix()
			_ = s.writeApp(pctx, nid, app, observedAt)
			s.diffEvents(pctx, nid, prevFavs, prevWords, prevStatus, observedAt)
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
		_ = s.writeHTML(pctx, nid, d, observedAt)
		s.diffEvents(pctx, nid, prevFavs, prevWords, prevStatus, observedAt)
	}
	_ = s.store.WatchPollDone(pctx, nid, observedAt)
}

// diffEvents records a watch_events row per metric that changed between
// the previous observation and the fresh one (words grow, favs move,
// status flips). Values are stringified; no change, no row.
func (s *Server) diffEvents(ctx context.Context, nid int64,
	prevFavs, prevWords sql.NullInt64, prevStatus sql.NullString, at int64) {
	favs, words, status, _ := s.store.LastObservation(ctx, nid)
	var changes [][3]string
	if words.Valid && prevWords.Valid && words.Int64 > prevWords.Int64 {
		changes = append(changes, [3]string{"words",
			itoa(prevWords.Int64), itoa(words.Int64)})
	}
	if favs.Valid && prevFavs.Valid && favs.Int64 != prevFavs.Int64 {
		changes = append(changes, [3]string{"favs",
			itoa(prevFavs.Int64), itoa(favs.Int64)})
	}
	if status.String != "" && prevStatus.Valid &&
		prevStatus.String != status.String {
		changes = append(changes, [3]string{"status",
			prevStatus.String, status.String})
	}
	for _, c := range changes {
		if err := s.store.RecordWatchEvent(ctx, nid, c[0], c[1], c[2], at); err != nil {
			log.Printf("watcher: record event nid=%d kind=%s: %v", nid, c[0], err)
		}
	}
}

func itoa(n int64) string {
	return strconv.FormatInt(n, 10)
}

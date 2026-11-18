package api

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"strata/engine/internal/crawl"
	"strata/engine/internal/store"
)

var genres = map[string]bool{
	"魔幻": true, "玄幻": true, "古风": true, "科幻": true, "校园": true,
	"都市": true, "游戏": true, "同人": true, "悬疑": true,
}

// D2 deep-rank metrics. Keep in sync with app/tools/seedbuild/deep_ranks.py.
var deepMetrics = map[string]bool{
	"favs": true, "clicks": true, "praises": true, "pr": true,
}

const (
	defaultLimit = 50
	maxLimit     = 200
)

type Server struct {
	store   *store.Store
	limiter *crawl.Limiter
	client  *http.Client

	// App API is the optional enhancement pathway (docs/05 §3.5): off by
	// default, any failure silently degrades to the mobile HTML baseline.
	appAPI bool

	// Refresh debounce: same nid within the window returns the last
	// verdict without touching the limiter (docs/08).
	refreshMu   sync.Mutex
	refreshLast map[int64]refreshEntry

	// Background watchlist poll worker (Phase 5): started once in New.
	watcherStarted bool
}

const refreshDebounce = time.Minute

type refreshEntry struct {
	verdict gin.H
	at      time.Time
}

func New(s *store.Store) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	// cmd/ffi sets GODEBUG=netdns=cgo so DNS goes through bionic getaddrinfo
	// (Go's pure resolver cannot read /etc/resolv.conf on Android). Device-side
	// DNS can be poisoned, so the dialer prefers verified static IPs and keeps
	// TLS ServerName intact.
	client := &http.Client{
		Timeout: 30 * time.Second,
		Transport: &http.Transport{
			DialContext: crawl.NewHostsDialer(map[string][]string{
				"m.sfacg.com": {"106.54.231.107"},
			}, 10*time.Second).DialContext,
		},
	}
	srv := &Server{
		store:       s,
		limiter:     crawl.NewLimiter(crawl.DefaultInterval),
		client:      client,
		refreshLast: map[int64]refreshEntry{},
		appAPI:      os.Getenv("STRATA_APP_API") == "1",
	}
	group := r.Group("/strata")
	group.GET("/healthz", srv.healthz)
	group.GET("/meta", srv.meta)
	group.GET("/books/:nid", srv.book)
	group.POST("/books/:nid/refresh", srv.bookRefresh)
	group.GET("/books/:nid/observations", srv.observations)
	group.GET("/watchlist", srv.watchList)
	group.POST("/watchlist/:nid", srv.watchAdd)
	group.DELETE("/watchlist/:nid", srv.watchRemove)
	group.GET("/rankings/favs", srv.rankingFavs)
	group.GET("/rankings/board", srv.rankingBoard)
	group.GET("/discover", srv.discover)
	group.GET("/rankings/deep", srv.rankingDeep)
	group.GET("/rankings/short", srv.rankingShort)
	group.GET("/rankings/new", srv.rankingNew)
	group.GET("/search", srv.search)
	group.GET("/random", srv.random)
	group.GET("/featured", srv.featured)
	group.GET("/shelf", srv.shelfList)
	group.PUT("/shelf", srv.shelfAdd)
	group.DELETE("/shelf/:nid", srv.shelfRemove)
	srv.startWatcher(context.Background())
	return r
}

func (s *Server) healthz(c *gin.Context) {
	m := s.store.Manifest
	c.JSON(http.StatusOK, gin.H{
		"status":         "ok",
		"schema_version": m.SchemaVersion,
		"seed_version":   m.SeedVersion,
		"book_count":     m.BookCount,
		"licensed_count": m.LicensedCount,
		"content_end":    m.ContentEnd,
		"gen_min":        m.GenMin,
		"gen_max":        m.GenMax,
	})
}

func (s *Server) meta(c *gin.Context) {
	seedMeta, err := s.store.SeedMeta(c.Request.Context())
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"manifest":  s.store.Manifest,
		"seed_meta": seedMeta,
	})
}

func (s *Server) book(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	detail, err := s.store.Book(c.Request.Context(), nid)
	if errors.Is(err, store.ErrNotFound) {
		fail(c, http.StatusNotFound, "not_found", "book not in seed")
		return
	}
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}

	source := "seed"
	if detail.Local != nil {
		source = "local"
	}
	// Locally fetched cover (App API novelCover) takes priority over the
	// seed column, which is empty for many books (upstream crawler bug).
	cover, _ := s.store.Cover(c.Request.Context(), nid)
	c.JSON(http.StatusOK, gin.H{
		"source":    source,
		"data_end":  s.store.Manifest.ContentEnd,
		"book":      detail.Book,
		"tags":      detail.Tags,
		"local":     detail.Local,
		"effective": effective(detail),
		"cover":     cover,
	})
}

func effective(d *store.BookDetail) gin.H {
	b, o := d.Book, d.Local
	out := gin.H{
		"clicks":     b.Clicks,
		"favs":       b.Favs,
		"praises":    b.Praises,
		"words":      b.Words,
		"status":     b.Status,
		"updated_at": b.UpdatedAt,
	}
	if o == nil {
		return out
	}
	if o.Clicks != nil {
		out["clicks"] = o.Clicks
	}
	if o.Favs != nil {
		out["favs"] = o.Favs
	}
	if o.Praises != nil {
		out["praises"] = o.Praises
	}
	if o.Words != nil {
		out["words"] = o.Words
	}
	if o.Status != nil {
		out["status"] = o.Status
	}
	if o.UpdatedAt != nil {
		out["updated_at"] = o.UpdatedAt
	}
	return out
}

func (s *Server) rankingFavs(c *gin.Context) {
	rawYear := c.Query("year")
	if rawYear == "" {
		fail(c, http.StatusBadRequest, "invalid_argument", "year is required")
		return
	}
	year, err := strconv.Atoi(rawYear)
	if err != nil || year < s.store.Manifest.GenMin || year > s.store.Manifest.GenMax {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"year must be between gen_min and gen_max")
		return
	}
	genre := c.Query("genre")
	if genre != "" && !genres[genre] {
		fail(c, http.StatusBadRequest, "invalid_argument", "unknown genre")
		return
	}
	limit, ok := parseLimit(c)
	if !ok {
		return
	}

	// 二级页过滤维度（宫格入口）：状态精确匹配；比赛=contest 非空。
	status := c.Query("status")
	if status != "" && status != "已完结" && status != "连载中" {
		fail(c, http.StatusBadRequest, "invalid_argument", "unknown status")
		return
	}
	contest := c.Query("contest")

	items, err := s.store.RankingFavs(c.Request.Context(), year, genre, status, contest, limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	var genreOut any
	if genre != "" {
		genreOut = genre
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind":              "favs",
			"pool":              "seed",
			"ordering":          "fav_pctl",
			"content_end":       s.store.Manifest.ContentEnd,
			"year":              year,
			"genre":             genreOut,
			"limit":             limit,
			"licensed_excluded": true,
		},
		"items": items,
	})
}

func (s *Server) rankingShort(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.RankingShort(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind":              "short",
			"pool":              "seed",
			"ordering":          "favs",
			"content_end":       s.store.Manifest.ContentEnd,
			"limit":             limit,
			"short_max_words":   50000,
			"licensed_excluded": true,
		},
		"items": items,
	})
}

func (s *Server) rankingNew(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.RankingNew(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind":              "new",
			"pool":              "seed",
			"ordering":          "fav_pctl",
			"content_end":       s.store.Manifest.ContentEnd,
			"min_est_year":      s.store.Manifest.GenMax - 1,
			"limit":             limit,
			"licensed_excluded": true,
		},
		"items": items,
	})
}

// rankingDeep serves the D2 full-universe generation boards. Unlike
// /rankings/favs (which reads the curated seed pool), the candidate universe
// here is the 241,758-row statistical frame, so early generations really do
// have a Top200 board. See app/docs/10-deep-ranks.md.
// random samples the seed uniformly at random for the home shuffle grid.
func (s *Server) random(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.RandomBooks(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"pool": "seed", "ordering": "random"},
		"items": items,
	})
}

// rankingBoard is the Classic full-catalog board (docs/12 showcase column):
// platform cumulative values, offset-paginated. Display-only pathway.
func (s *Server) rankingBoard(c *gin.Context) {
	kind := c.Query("kind")
	if _, ok := map[string]bool{
		"recommend": true, "popular": true, "favs": true,
		"new": true, "finish": true, "words": true,
	}[kind]; !ok {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"kind must be recommend|popular|favs|new|finish|words")
		return
	}
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	offset := 0
	if raw := c.Query("offset"); raw != "" {
		var err error
		if offset, err = strconv.Atoi(raw); err != nil || offset < 0 {
			fail(c, http.StatusBadRequest, "invalid_argument", "offset must be a non-negative integer")
			return
		}
	}
	items, err := s.store.BoardBooks(c.Request.Context(), kind, limit, offset)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{"kind": kind, "pool": "seed", "ordering": "cumulative",
			"licensed_excluded": true},
		"items": items,
	})
}

// discover is the classic discovery stream (docs/12 §5): cover-bearing
// books by platform clicks, keyset pagination via cursor "clicks:nid",
// 20 per batch, stateless.
func (s *Server) discover(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.Discover(c.Request.Context(), c.Query("cursor"), limit)
	if err != nil {
		fail(c, http.StatusBadRequest, "invalid_argument", err.Error())
		return
	}
	var nextCursor string
	if len(items) == limit {
		last := items[len(items)-1]
		if last.Clicks != nil {
			nextCursor = fmt.Sprintf("%d:%d", *last.Clicks, last.NID)
		}
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":        gin.H{"pool": "seed", "ordering": "clicks", "cover_required": true},
		"items":       items,
		"next_cursor": nextCursor,
	})
}

// watchList returns the author's tracked books joined with seed metadata.
func (s *Server) watchList(c *gin.Context) {
	items, err := s.store.WatchList(c.Request.Context())
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"meta": gin.H{"pool": "user"}, "items": items})
}

// watchAdd tracks a book. Idempotent (INSERT OR IGNORE).
func (s *Server) watchAdd(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	if err := s.store.WatchAdd(c.Request.Context(), nid, time.Now().Unix()); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"meta": gin.H{"nid": nid, "added": true}})
}

// watchRemove drops a book from the watchlist.
func (s *Server) watchRemove(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	if err := s.store.WatchRemove(c.Request.Context(), nid); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"meta": gin.H{"nid": nid, "removed": true}})
}

func (s *Server) rankingDeep(c *gin.Context) {
	rawYear := c.Query("year")
	year, err := strconv.Atoi(rawYear)
	if err != nil || year < s.store.Manifest.GenMin || year > s.store.Manifest.GenMax {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"year must be between gen_min and gen_max")
		return
	}
	metric := c.Query("metric")
	if !deepMetrics[metric] {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"metric must be favs, clicks, praises or pr")
		return
	}
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, depth, err := s.store.RankingDeep(c.Request.Context(), year, metric, limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind":              "deep",
			"pool":              "universe",
			"ordering":          metric,
			"content_end":       s.store.Manifest.ContentEnd,
			"year":              year,
			"metric":            metric,
			"limit":             limit,
			"depth":             depth,
			"licensed_excluded": true,
		},
		"items": items,
	})
}

func (s *Server) search(c *gin.Context) {
	q := c.Query("q")
	if q == "" {
		fail(c, http.StatusBadRequest, "invalid_argument", "q is required")
		return
	}
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.Search(c.Request.Context(), q, limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind":        "search",
			"pool":        "seed",
			"q":           q,
			"limit":       limit,
			"includes":    "licensed",
			"content_end": s.store.Manifest.ContentEnd,
		},
		"items": items,
	})
}

// bookRefresh fetches the mobile detail page and classifies the result
// (docs/05 §4.3 three-state verdict). Alive pages get an observation row
// appended to user.db; dead/zombie pages are reported and never written.
// The call is synchronous: the global limiter already serializes requests,
// and a user-triggered refresh takes exactly one foreground slot.
func (s *Server) bookRefresh(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	// Debounce: an identical nid within the window replays the last verdict
	// without a fetch or a limiter slot.
	s.refreshMu.Lock()
	if e, ok := s.refreshLast[nid]; ok && time.Since(e.at) < refreshDebounce {
		resp := cloneVerdict(e.verdict)
		resp["cached"] = true
		s.refreshMu.Unlock()
		c.JSON(http.StatusOK, resp)
		return
	}
	s.refreshMu.Unlock()

	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()

	// App API enhancement (docs/05 §3.5): opt-in via STRATA_APP_API=1.
	// On success the precise metadata replaces the HTML-parsed values and
	// the cover is cached; ANY failure silently falls through to the
	// mobile HTML baseline — no retry, no user-visible error.
	if s.appAPI {
		if app, aerr := crawl.FetchAppNovel(ctx, s.client, s.limiter, nid, true); aerr == nil {
			clicks, favs, words := app.ViewTimes, app.MarkCount, app.CharCount
			status := map[bool]string{true: "已完结", false: "连载中"}[app.IsFinish]
			updatedAt := app.LastUpdateTime
			observedAt := time.Now().Unix()
			if err := s.store.InsertObservation(ctx, nid, observedAt,
				&clicks, &favs, nil, &words, &status, &updatedAt); err == nil {
				if app.NovelCover != "" {
					_ = s.store.UpsertCover(ctx, nid, app.NovelCover, observedAt)
				}
				resp := gin.H{
					"state":    "alive",
					"written":  true,
					"source":   "app",
					"add_time": app.AddTime,
					"detail": gin.H{
						"clicks": clicks, "favs": favs, "words": words,
						"status": status, "updated_at": updatedAt,
						"cover": app.NovelCover, "point": app.Point,
					},
				}
				s.refreshMu.Lock()
				s.refreshLast[nid] = refreshEntry{verdict: resp, at: time.Now()}
				s.refreshMu.Unlock()
				c.JSON(http.StatusOK, resp)
				return
			}
		}
		// fall through: silent degrade to the HTML baseline
	}

	state, d, observedAt, err := crawl.FetchDetail(ctx, s.client, s.limiter, nid, true)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	resp := gin.H{"state": state.String(), "written": false}
	if d != nil {
		resp["detail"] = d
	}
	if state == crawl.DetailAlive {
		favs, praises, words := d.Favs, d.Praises, d.Words
		status, updatedAt := d.Status, d.UpdatedAt
		if err := s.store.InsertObservation(ctx, nid, observedAt,
			nil, &favs, &praises, &words, &status, &updatedAt); err != nil {
			fail(c, http.StatusInternalServerError, "internal", err.Error())
			return
		}
		resp["written"] = true
	}
	s.refreshMu.Lock()
	s.refreshLast[nid] = refreshEntry{verdict: resp, at: time.Now()}
	s.refreshMu.Unlock()
	c.JSON(http.StatusOK, resp)
}

// cloneVerdict shallow-copies a cached verdict so callers cannot mutate the
// cache entry.
func cloneVerdict(v gin.H) gin.H {
	out := make(gin.H, len(v)+1)
	for k, val := range v {
		out[k] = val
	}
	return out
}

// observations returns a nid's observation history, newest first.
func (s *Server) observations(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	items, err := s.store.Observations(c.Request.Context(), nid)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// featured returns editor-picked books (seed featured=1) for the home
// carousel — a static, build-time curation, never presented as "hot".
func (s *Server) featured(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.FeaturedBooks(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// shelfList returns the local shelf joined with seed titles.
func (s *Server) shelfList(c *gin.Context) {
	items, err := s.store.ShelfList(c.Request.Context())
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

func (s *Server) shelfAdd(c *gin.Context) {
	var body struct {
		NID int64 `json:"nid"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.NID <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid is required")
		return
	}
	if err := s.store.ShelfAdd(c.Request.Context(), body.NID, time.Now().Unix()); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (s *Server) shelfRemove(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	if err := s.store.ShelfRemove(c.Request.Context(), nid); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func parseLimit(c *gin.Context) (int, bool) {
	raw := c.Query("limit")
	if raw == "" {
		return defaultLimit, true
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit < 1 || limit > maxLimit {
		fail(c, http.StatusBadRequest, "invalid_argument", "limit must be 1..200")
		return 0, false
	}
	return limit, true
}

func fail(c *gin.Context, status int, code, message string) {
	c.AbortWithStatusJSON(status, gin.H{
		"error": gin.H{"code": code, "message": message},
	})
}

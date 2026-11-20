package api

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
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

	// Serializes the per-nid cooldown check and attempt stamp so two
	// concurrent taps cannot both consume the same 24h window.
	refreshMu sync.Mutex

	// Background watchlist poll worker (Phase 5): started once in New.
	watcherStarted bool
}

const (
	detailRefreshWindow = 24 * time.Hour
	detailRateLimitPref = "detail_rate_limit_enabled"
)

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
		store:   s,
		limiter: crawl.NewLimiter(crawl.DefaultInterval),
		client:  client,
		appAPI:  os.Getenv("STRATA_APP_API") == "1",
	}
	group := r.Group("/strata")
	group.GET("/healthz", srv.healthz)
	group.GET("/meta", srv.meta)
	group.GET("/settings", srv.settings)
	group.PUT("/settings", srv.updateSettings)
	group.GET("/books/:nid", srv.book)
	group.POST("/books/:nid/refresh", srv.bookRefresh)
	group.GET("/books/:nid/observations", srv.observations)
	group.GET("/watchlist", srv.watchList)
	group.POST("/watchlist/:nid", srv.watchAdd)
	group.PUT("/watchlist/:nid", srv.watchSetActive)
	group.DELETE("/watchlist/:nid", srv.watchRemove)
	group.GET("/rankings/favs", srv.rankingFavs)
	group.GET("/rankings/board", srv.rankingBoard)
	group.GET("/rankings/classic", srv.rankingClassic)
	group.GET("/discover", srv.discover)
	group.GET("/rankings/deep", srv.rankingDeep)
	group.GET("/rankings/short", srv.rankingShort)
	group.GET("/rankings/new", srv.rankingNew)
	group.GET("/search", srv.search)
	group.GET("/random", srv.random)
	group.GET("/licensed", srv.licensed)
	group.GET("/moe-goddess", srv.moeGoddess)
	group.GET("/history", srv.history)
	group.POST("/history/:nid", srv.recordHistory)
	group.GET("/featured", srv.featured)
	group.GET("/featured-all", srv.featuredAll)
	group.GET("/cover-carousel", srv.coverCarousel)
	group.GET("/calendar", srv.calendar)
	group.GET("/ip-groups", srv.ipGroups)
	group.GET("/year-groups", srv.yearGroups)
	group.GET("/genre-groups", srv.genreGroups)
	group.GET("/ip-books", srv.ipBooks)
	group.GET("/banner", srv.banner)
	group.GET("/author-books", srv.authorBooks)
	group.GET("/author-profile", srv.authorProfile)
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

// settings reports the user-adjustable fetch limits. The detail cooldown is
// on by default; users can disable it when they intentionally want several
// manual refreshes in a day.
func (s *Server) settings(c *gin.Context) {
	enabled, err := s.detailRateLimitEnabled(c.Request.Context())
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"detail_rate_limit_enabled":     enabled,
		"detail_refresh_window_seconds": int64(detailRefreshWindow / time.Second),
	})
}

func (s *Server) updateSettings(c *gin.Context) {
	var body struct {
		DetailRateLimitEnabled *bool `json:"detail_rate_limit_enabled"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.DetailRateLimitEnabled == nil {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"detail_rate_limit_enabled is required")
		return
	}
	value := "0"
	if *body.DetailRateLimitEnabled {
		value = "1"
	}
	if err := s.store.SetPref(c.Request.Context(), detailRateLimitPref, value); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	s.settings(c)
}

// detailRateLimitEnabled returns the persisted preference; missing means on.
func (s *Server) detailRateLimitEnabled(ctx context.Context) (bool, error) {
	v, ok, err := s.store.Pref(ctx, detailRateLimitPref)
	if err != nil {
		return false, err
	}
	if !ok {
		return true, nil
	}
	return v != "0" && v != "false", nil
}

// detailRefreshInfo describes the cooldown for one book on GET /books/:nid so
// the UI can disable the button before a useless request is made.
func (s *Server) detailRefreshInfo(ctx context.Context, nid int64, now time.Time) (gin.H, error) {
	enabled, err := s.detailRateLimitEnabled(ctx)
	if err != nil {
		return nil, err
	}
	attempt, err := s.store.RefreshAttempt(ctx, nid)
	if err != nil {
		return nil, err
	}
	out := gin.H{
		"rate_limit_enabled": enabled,
		"window_seconds":     int64(detailRefreshWindow / time.Second),
	}
	if attempt != nil {
		out["last_attempt_at"] = attempt.AttemptedAt
		out["last_state"] = attempt.State
		next := attempt.AttemptedAt + int64(detailRefreshWindow/time.Second)
		if enabled && next > now.Unix() {
			out["next_allowed_at"] = next
		}
	}
	return out, nil
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
	if detail.Local != nil || detail.Meta != nil {
		source = "local"
	}
	// Locally fetched cover takes priority over the seed column, which is
	// empty or relative for many books (upstream crawler bug).
	cover, _ := s.store.Cover(c.Request.Context(), nid)
	if cover == "" && detail.Meta != nil && detail.Meta.CoverURL != nil {
		cover = *detail.Meta.CoverURL
	}
	refresh, err := s.detailRefreshInfo(c.Request.Context(), nid, time.Now())
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"source":    source,
		"data_end":  s.store.Manifest.ContentEnd,
		"book":      detail.Book,
		"tags":      detail.Tags,
		"local":     detail.Local,
		"meta":      detail.Meta,
		"effective": effective(detail),
		"cover":     cover,
		"refresh":   refresh,
	})
}

func effective(d *store.BookDetail) gin.H {
	b, o, m := d.Book, d.Local, d.Meta
	out := gin.H{
		"title":      b.Title,
		"author":     b.Author,
		"genre":      b.Genre,
		"price_type": b.PriceType,
		"clicks":     b.Clicks,
		"favs":       b.Favs,
		"praises":    b.Praises,
		"words":      b.Words,
		"status":     b.Status,
		"cover_url":  b.CoverURL,
		"updated_at": b.UpdatedAt,
	}
	if m != nil {
		overlayStr(out, "title", m.Title)
		overlayStr(out, "author", m.Author)
		overlayInt(out, "author_id", m.AuthorID)
		overlayStr(out, "genre", m.Genre)
		overlayInt(out, "type_id", m.TypeID)
		overlayStr(out, "price_type", m.PriceType)
		overlayStr(out, "status", m.Status)
		overlayStr(out, "cover_url", m.CoverURL)
		overlayStr(out, "summary", m.Summary)
		overlayInt(out, "words", m.Words)
		overlayInt(out, "favs", m.Favs)
		overlayInt(out, "praises", m.Praises)
		overlayInt(out, "clicks", m.Clicks)
		overlayStr(out, "updated_at", m.UpdatedAt)
		overlayStr(out, "add_time", m.AddTime)
		overlayFloat(out, "point", m.Point)
		overlayStr(out, "bg_banner", m.BgBanner)
		overlayInt(out, "category_id", m.CategoryID)
		overlayBool(out, "is_sensitive", m.IsSensitive)
		overlayBool(out, "allow_down", m.AllowDown)
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

func overlayStr(out gin.H, key string, v *string) {
	if v != nil {
		out[key] = *v
	}
}

func overlayInt(out gin.H, key string, v *int64) {
	if v != nil {
		out[key] = *v
	}
}

func overlayFloat(out gin.H, key string, v *float64) {
	if v != nil {
		out[key] = *v
	}
}

func overlayBool(out gin.H, key string, v *bool) {
	if v != nil {
		out[key] = *v
	}
}

func metaStr(v string) *string {
	v = strings.TrimSpace(v)
	if v == "" {
		return nil
	}
	return &v
}

func metaInt(v int64) *int64 {
	return &v
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
	status := c.Query("status")
	if status != "" && status != "serial" && status != "finished" &&
		status != "browse" && status != "short" {
		fail(c, http.StatusBadRequest, "invalid_status",
			"status must be empty, \"serial\", \"finished\", \"browse\" or \"short\"")
		return
	}
	form, ok := parseForm(c)
	if !ok {
		return
	}
	items, err := s.store.RandomBooks(c.Request.Context(), limit, status, form)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"pool": "seed", "ordering": "random"},
		"items": items,
	})
}

// licensed lists the small fixed pool of licensed Japanese light novels
// (is_licensed=1), favs order. Home entry card 授权作品.
func (s *Server) licensed(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.LicensedBooks(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"pool": "licensed", "ordering": "favs"},
		"items": items,
	})
}

// moeGoddess lists books carrying a yearly 萌神 award tag (2018–2024),
// favs order. Home entry card 萌神获奖.
func (s *Server) moeGoddess(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.MoeGoddessBooks(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"pool": "moe-goddess", "ordering": "favs"},
		"items": items,
	})
}

// recordHistory bumps the local browsing footprint for one nid. The detail
// page calls it fire-and-forget on every open.
func (s *Server) recordHistory(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "bad nid")
		return
	}
	if err := s.store.RecordBrowsing(c.Request.Context(), nid, time.Now().Unix()); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"recorded": true})
}

// history returns the most recently opened books for the home reading
// history entry. Pure local data.
func (s *Server) history(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	items, err := s.store.RecentHistory(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
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
	form, ok := parseForm(c)
	if !ok {
		return
	}
	items, err := s.store.BoardBooks(c.Request.Context(), kind, form, limit, offset)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{"kind": kind, "pool": "seed", "ordering": "cumulative",
			"form": form, "licensed_excluded": true},
		"items": items,
	})
}

// discover is the classic discovery stream (docs/12 §5): cover-bearing
// books by platform clicks, keyset pagination via cursor "clicks:nid",
// 20 per batch, stateless.
func (s *Server) rankingClassic(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	offset := 0
	if raw := c.Query("offset"); raw != "" {
		var err error
		if offset, err = strconv.Atoi(raw); err != nil || offset < 0 {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"offset must be a non-negative integer")
			return
		}
	}
	form, ok := parseForm(c)
	if !ok {
		return
	}
	year := 0
	if raw := c.Query("year"); raw != "" {
		var err error
		if year, err = strconv.Atoi(raw); err != nil || year <= 0 {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"year must be a positive integer")
			return
		}
	}
	order := c.Query("order")
	if order != "" && order != "favs" && order != "pct" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"order must be \"favs\" or \"pct\"")
		return
	}
	items, err := s.store.ClassicBooks(c.Request.Context(),
		c.Query("genre"), c.Query("status"), c.Query("contest"), form, year, limit, offset, order)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	ordering := "favs"
	if order == "pct" {
		ordering = "fav_pctl"
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind": "classic", "pool": "seed", "ordering": ordering,
			"genre": c.Query("genre"), "status": c.Query("status"),
			"contest": c.Query("contest"), "form": form, "year": year,
			"order": order, "licensed_excluded": true,
		},
		"items": items,
	})
}

func (s *Server) discover(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	form, ok := parseForm(c)
	if !ok {
		return
	}
	items, err := s.store.Discover(c.Request.Context(), c.Query("cursor"), form, limit)
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
		"meta": gin.H{"pool": "seed", "ordering": "clicks", "cover_required": true,
			"form": form},
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

// watchAdd puts a book on the watchlist (v6: the single user-interest
// list). Body {active?: bool}: active=false (default) = save-only
// entry (former bookshelf); active=true = tracked. Idempotent — an
// existing entry keeps its state.
func (s *Server) watchAdd(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	var body struct {
		Active *bool `json:"active"`
	}
	_ = c.ShouldBindJSON(&body)
	active := body.Active != nil && *body.Active
	if err := s.store.WatchAdd(c.Request.Context(), nid, time.Now().Unix(), active); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"meta": gin.H{"nid": nid, "added": true}})
}

// watchSetActive toggles tracking on a watchlist entry (v6):
// body {active: bool}.
func (s *Server) watchSetActive(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	var body struct {
		Active bool `json:"active"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		fail(c, http.StatusBadRequest, "invalid_argument", "body must be {active: bool}")
		return
	}
	if err := s.store.WatchSetActive(c.Request.Context(), nid, body.Active); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"meta": gin.H{"nid": nid, "active": body.Active}})
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
//
// By default each book is limited to one outbound detail request per 24h.
// The attempt is stamped BEFORE the request, so dead/zombie/network failures
// also consume the window. The Settings switch can disable this limit.
func (s *Server) bookRefresh(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	now := time.Now()
	blocked, allowed, err := s.reserveDetailRefresh(c.Request.Context(), nid, now)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	if !allowed {
		c.JSON(http.StatusOK, blocked)
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 30*time.Second)
	defer cancel()

	// App API enhancement (docs/05 §3.5): opt-in via STRATA_APP_API=1.
	// On success every field the response carries is persisted; ANY failure
	// silently falls through to the mobile HTML baseline — no retry, no
	// user-visible error.
	if s.appAPI {
		if app, aerr := crawl.FetchAppNovel(ctx, s.client, s.limiter, nid, true); aerr == nil {
			observedAt := time.Now().Unix()
			if err := s.writeApp(ctx, nid, app, observedAt); err == nil {
				s.finishDetailRefresh(nid, now.Unix(), "app")
				c.JSON(http.StatusOK, gin.H{
					"state":    "alive",
					"written":  true,
					"source":   "app",
					"add_time": app.AddTime,
					"detail":   app,
				})
				return
			}
		}
		// fall through: silent degrade to the HTML baseline
	}

	state, d, observedAt, err := crawl.FetchDetail(ctx, s.client, s.limiter, nid, true)
	if err != nil {
		s.finishDetailRefresh(nid, now.Unix(), "error")
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	resp := gin.H{"state": state.String(), "written": false}
	if d != nil {
		resp["detail"] = d
	}
	if state == crawl.DetailAlive {
		if err := s.writeHTML(ctx, nid, d, observedAt); err != nil {
			s.finishDetailRefresh(nid, now.Unix(), "error")
			fail(c, http.StatusInternalServerError, "internal", err.Error())
			return
		}
		resp["written"] = true
	}
	s.finishDetailRefresh(nid, now.Unix(), state.String())
	c.JSON(http.StatusOK, resp)
}

// reserveDetailRefresh atomically checks the per-nid cooldown and, when
// allowed, stamps the attempt before any network I/O. It returns a ready-made
// rate_limited response when the window is still closed.
func (s *Server) reserveDetailRefresh(ctx context.Context, nid int64, now time.Time) (gin.H, bool, error) {
	s.refreshMu.Lock()
	defer s.refreshMu.Unlock()

	enabled, err := s.detailRateLimitEnabled(ctx)
	if err != nil {
		return nil, false, err
	}
	attempt, err := s.store.RefreshAttempt(ctx, nid)
	if err != nil {
		return nil, false, err
	}
	window := int64(detailRefreshWindow / time.Second)
	if enabled && attempt != nil && now.Unix() < attempt.AttemptedAt+window {
		next := attempt.AttemptedAt + window
		return gin.H{
			"state":               "rate_limited",
			"written":             false,
			"rate_limit_enabled":  true,
			"last_attempt_at":     attempt.AttemptedAt,
			"next_allowed_at":     next,
			"retry_after_seconds": next - now.Unix(),
		}, false, nil
	}
	if err := s.store.RecordRefreshAttempt(ctx, nid, now.Unix(), "pending"); err != nil {
		return nil, false, err
	}
	return nil, true, nil
}

// finishDetailRefresh updates the stamped attempt's diagnostic state without
// clobbering a newer attempt that may have started after this one.
func (s *Server) finishDetailRefresh(nid, attemptedAt int64, state string) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = s.store.FinishRefreshAttempt(ctx, nid, attemptedAt, state)
}

// writeHTML persists every field parsed from the mobile detail page: the
// observation row keeps the metric time series, book_meta keeps the latest
// book attributes (title/author/genre/cover/summary/...), and covers keeps
// the legacy App cover cache in sync.
func (s *Server) writeHTML(ctx context.Context, nid int64, d *crawl.Detail, observedAt int64) error {
	favs, praises, words := d.Favs, d.Praises, d.Words
	var wordsPtr *int64
	if words > 0 {
		wordsPtr = &words
	}
	if err := s.store.InsertObservation(ctx, nid, observedAt,
		nil, &favs, &praises, wordsPtr, metaStr(d.Status), metaStr(d.UpdatedAt)); err != nil {
		return err
	}
	m := &store.BookMeta{
		NID:       nid,
		Source:    "html",
		FetchedAt: observedAt,
		Title:     metaStr(d.Title),
		Author:    metaStr(d.Author),
		Genre:     metaStr(d.Genre),
		PriceType: metaStr(d.PriceType),
		Status:    metaStr(d.Status),
		CoverURL:  metaStr(d.CoverURL),
		Summary:   metaStr(d.Summary),
		Favs:      &favs,
		Praises:   &praises,
		Words:     wordsPtr,
		UpdatedAt: metaStr(d.UpdatedAt),
	}
	if err := s.store.UpsertBookMeta(ctx, m); err != nil {
		return err
	}
	if d.CoverURL != "" {
		_ = s.store.UpsertCover(ctx, nid, d.CoverURL, observedAt)
	}
	return nil
}

// writeApp persists every field returned by GET /novels/{id}. The App API
// has no praises/summary, so those stay nil and the previous local values
// are preserved.
func (s *Server) writeApp(ctx context.Context, nid int64, app *crawl.AppNovel, observedAt int64) error {
	clicks, favs, words := app.ViewTimes, app.MarkCount, app.CharCount
	status := "已完结"
	if !app.IsFinish {
		status = "连载中"
	}
	if err := s.store.InsertObservation(ctx, nid, observedAt,
		&clicks, &favs, nil, &words, &status, metaStr(app.LastUpdateTime)); err != nil {
		return err
	}
	m := &store.BookMeta{
		NID:         nid,
		Source:      "app",
		FetchedAt:   observedAt,
		Title:       metaStr(app.NovelName),
		Author:      metaStr(app.AuthorName),
		AuthorID:    metaInt(app.AuthorID),
		Genre:       metaStr(crawl.AppGenre(app.TypeID)),
		TypeID:      metaInt(app.TypeID),
		PriceType:   metaStr(app.SignStatus),
		Status:      metaStr(status),
		CoverURL:    metaStr(app.NovelCover),
		Words:       &words,
		Favs:        &favs,
		Clicks:      &clicks,
		UpdatedAt:   metaStr(app.LastUpdateTime),
		AddTime:     metaStr(app.AddTime),
		Point:       &app.Point,
		BgBanner:    metaStr(app.BgBanner),
		CategoryID:  metaInt(app.CategoryID),
		IsSensitive: &app.IsSensitive,
		AllowDown:   &app.AllowDown,
	}
	if err := s.store.UpsertBookMeta(ctx, m); err != nil {
		return err
	}
	if app.NovelCover != "" {
		_ = s.store.UpsertCover(ctx, nid, app.NovelCover, observedAt)
	}
	return nil
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

// calendar serves the release-calendar view (docs/14 P1): seed books
// grouped by est_date at day/week/month granularity. Display-only
// pathway — the recommendation layer never consumes it. Weeks start on
// Monday (Chinese convention). Empty dates are filled with zero-total
// cells so the UI grid is always complete.
func (s *Server) calendar(c *gin.Context) {
	gran := c.Query("granularity")
	anchorRaw := c.Query("anchor")
	t, err := time.Parse("2006-01-02", anchorRaw)
	if err != nil {
		fail(c, http.StatusBadRequest, "invalid_argument", "anchor must be YYYY-MM-DD")
		return
	}
	var from, to time.Time
	var anchorLabel string
	switch gran {
	case "day":
		from, to = t, t
		anchorLabel = t.Format("2006-01-02")
	case "week":
		monday := t.AddDate(0, 0, -((int(t.Weekday()) + 6) % 7))
		from, to = monday, monday.AddDate(0, 0, 6)
		anchorLabel = monday.Format("2006-01-02")
	case "month":
		first := time.Date(t.Year(), t.Month(), 1, 0, 0, 0, 0, time.UTC)
		from, to = first, first.AddDate(0, 1, -1)
		anchorLabel = first.Format("2006-01")
	default:
		fail(c, http.StatusBadRequest, "invalid_argument",
			"granularity must be day|week|month")
		return
	}
	perCell, _ := strconv.Atoi(c.DefaultQuery("per_cell", "3"))
	if perCell < 1 || perCell > 50 {
		perCell = 3
	}
	days, err := s.store.BooksByDateRange(
		c.Request.Context(), from.Format("2006-01-02"), to.Format("2006-01-02"),
		gran != "month", perCell)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	universe, err := s.store.UniverseCountByDay(
		c.Request.Context(), from.Format("2006-01-02"), to.Format("2006-01-02"))
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	cellMap := make(map[string]store.CalendarDay, len(days))
	for _, d := range days {
		cellMap[d.Date] = d
	}
	cells := make([]store.CalendarDay, 0, int(to.Sub(from).Hours()/24)+1)
	for d := from; !d.After(to); d = d.AddDate(0, 0, 1) {
		key := d.Format("2006-01-02")
		if cell, ok := cellMap[key]; ok {
			if gran == "month" {
				cell.Items = nil // month grid shows totals only
			}
			cell.Universe = universe[key]
			cells = append(cells, cell)
		} else {
			cells = append(cells, store.CalendarDay{Date: key, Universe: universe[key]})
		}
	}
	c.JSON(http.StatusOK, gin.H{
		"granularity": gran,
		"anchor":      anchorLabel,
		"cells":       cells,
	})
}

// daySeed resolves the daily random seed shared by the banner and
// cover-carousel endpoints: the server date (YYYYMMDD) by default,
// client-overridable via ?seed= for deterministic caching and tests.
func daySeed(c *gin.Context) int64 {
	seed := time.Now().Format("20060102")
	if raw := c.Query("seed"); raw != "" {
		seed = raw
	}
	var day int64
	for _, ch := range seed {
		day = day*10 + int64(ch-'0')
	}
	return day
}

// banner picks the daily banner set: a uniform deterministic shuffle of the
// whole banner pool (seed featured=1, licensed included) keyed by a date
// seed so every day draws a different, cacheable set. An optional form
// narrows the pool to one form before shuffling.
func (s *Server) banner(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	form, ok := parseForm(c)
	if !ok {
		return
	}
	day := daySeed(c)
	offset := 0
	if raw := c.Query("offset"); raw != "" {
		o, err := strconv.Atoi(raw)
		if err != nil || o < 0 {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"offset must be a non-negative integer")
			return
		}
		offset = o
	}
	items, err := s.store.BannerPick(c.Request.Context(), day, offset, limit,
		form)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// featured returns editor-picked books (seed featured=1) for the home
// carousel — a static, build-time curation, never presented as "hot".
// An optional form narrows the pool; a short pool is returned as-is.
func (s *Server) featured(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	form, ok := parseForm(c)
	if !ok {
		return
	}
	items, err := s.store.FeaturedBooks(c.Request.Context(), limit, form)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// featuredAll pages through the whole featured=1 pool (编辑精选, licensed
// included) for the 大图精选 "更多" gallery: favs DESC by default (most
// curated first), order=asc inverts.
func (s *Server) featuredAll(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	offset := 0
	if raw := c.Query("offset"); raw != "" {
		o, err := strconv.Atoi(raw)
		if err != nil || o < 0 {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"offset must be a non-negative integer")
			return
		}
		offset = o
	}
	order := "desc"
	if raw := c.Query("order"); raw != "" {
		if raw != "asc" && raw != "desc" {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"order must be 'asc' or 'desc'")
			return
		}
		order = raw
	}
	items, err := s.store.FeaturedAll(c.Request.Context(), limit, offset,
		order)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// coverCarousel serves the 对话/短篇 tabs' composed banners: one form's
// cover-bearing favs head pool (top 100), drawn with the daily date seed
// (same hash as /banner) so consecutive days show different books while
// staying within the head. The client draws a paper-and-ink banner from
// each cover; cover-less books never appear, so the pool filter
// guarantees a drawable result.
func (s *Server) coverCarousel(c *gin.Context) {
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	form := c.Query("form")
	if form == "" || !validForms[form] {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return
	}
	items, err := s.store.CoverCarousel(c.Request.Context(), form, limit,
		daySeed(c))
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{"pool": "seed", "ordering": "daily", "form": form,
			"head_pool": 100, "cover_required": true},
		"items": items,
	})
}

// authorBooks lists one author's seed books in timeline order for the
// author page (docs/author-profile-on-demand): local data only, no
// network. Unknown authors return an empty list, not an error.
func (s *Server) authorBooks(c *gin.Context) {
	author := c.Query("author")
	if author == "" {
		fail(c, http.StatusBadRequest, "invalid_argument", "author is required")
		return
	}
	limit, ok := parseLimit(c)
	if !ok {
		return
	}
	offset := 0
	if raw := c.Query("offset"); raw != "" {
		o, err := strconv.Atoi(raw)
		if err != nil || o < 0 {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"offset must be a non-negative integer")
			return
		}
		offset = o
	}
	items, err := s.store.AuthorBooks(c.Request.Context(), author, limit, offset)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"pool": "seed", "ordering": "est_date_desc", "author": author},
		"items": items,
	})
}

// authorProfileOKTTL / authorProfileDeadTTL: cache lifetimes for the
// on-demand author profile (docs/author-profile-on-demand §4). Intro
// and avatar are slow-changing snapshot values, so a week is plenty
// for ok rows; dead rows (source book delisted) re-probe after a day
// in case of restoration.
const (
	authorProfileOKTTL   = 7 * 24 * 3600
	authorProfileDeadTTL = 24 * 3600
)

// authorProfile serves the author page header (docs/author-profile-on-
// demand §1-3): on-demand, never pre-fetched. One mobile detail fetch
// (avatar/name/works, on the book the page already shows) plus one PC
// fetch for the intro only when with_intro=1. A user.db cache
// (author_profiles, v7) short-circuits repeat opens within the TTL;
// fresh=1 bypasses it. The fetched book's author must match the
// requested author (casefold, space-sensitive) or the result is served
// but not cached — a wrong book can't poison the profile.
func (s *Server) authorProfile(c *gin.Context) {
	author := c.Query("author")
	nid, nerr := strconv.ParseInt(c.Query("nid"), 10, 64)
	if author == "" || nerr != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"author and a positive nid are required")
		return
	}
	withIntro := c.Query("with_intro") == "1"
	fresh := c.Query("fresh") == "1"
	key := strings.ToLower(author)
	now := time.Now().Unix()

	if !fresh {
		if p, err := s.store.GetAuthorProfile(c.Request.Context(), key); err == nil && p != nil {
			ttl := int64(authorProfileOKTTL)
			if p.Verdict == "dead" {
				ttl = int64(authorProfileDeadTTL)
			}
			if now-p.ObservedAt < ttl {
				c.JSON(http.StatusOK, gin.H{
					"nid":           p.SourceNID,
					"author_name":   p.AuthorName,
					"author_intro":  p.AuthorIntro,
					"author_avatar": p.AuthorAvatar,
					"works":         []crawl.AuthorWork{},
					"verdict":       p.Verdict,
					"observed_at":   p.ObservedAt,
					"source":        "cache",
				})
				return
			}
		}
	}

	state, d, fetchStart, err := crawl.FetchDetail(c.Request.Context(), s.client, s.limiter, nid, true)
	if err != nil {
		fail(c, http.StatusBadGateway, "fetch_error", err.Error())
		return
	}
	if state == crawl.DetailDead {
		_ = s.store.SaveAuthorProfile(c.Request.Context(), &store.AuthorProfile{
			AuthorKey: key, AuthorName: "", Verdict: "dead",
			SourceNID: nid, ObservedAt: fetchStart,
		})
		c.JSON(http.StatusOK, gin.H{
			"nid": nid, "author_name": "", "author_intro": nil,
			"author_avatar": "", "works": []crawl.AuthorWork{},
			"verdict": "dead", "observed_at": fetchStart, "source": "live",
		})
		return
	}

	name, avatar := "", ""
	works := []crawl.AuthorWork{}
	if state == crawl.DetailAlive && d != nil {
		name = d.AuthorName
		if name == "" {
			name = d.Author
		}
		avatar = d.AuthorAvatar
		works = d.AuthorWorks
		if works == nil {
			works = []crawl.AuthorWork{}
		}
	}
	if strings.Contains(avatar, "common/0.gif") {
		avatar = ""
	}
	var intro *string
	if withIntro && name != "" {
		if box, _, perr := crawl.FetchAuthorBox(c.Request.Context(), s.client, s.limiter, nid, true); perr == nil && box != nil {
			if box.Intro != "" {
				v := box.Intro
				intro = &v
			}
			if box.Avatar != "" && !strings.Contains(box.Avatar, "common/0.gif") {
				avatar = box.Avatar
			}
		}
	}

	// Identity guard: the fetched book must be by the requested author
	// (casefold, space-sensitive), otherwise serve but do not cache.
	match := name == "" || strings.ToLower(name) == key
	verdict := "ok"
	if name == "" && avatar == "" && len(works) == 0 {
		verdict = "error"
	}
	var avatarPtr *string
	if avatar != "" {
		avatarPtr = &avatar
	}
	if match {
		_ = s.store.SaveAuthorProfile(c.Request.Context(), &store.AuthorProfile{
			AuthorKey: key, AuthorName: name, AuthorIntro: intro,
			AuthorAvatar: avatarPtr, Verdict: verdict,
			SourceNID: nid, ObservedAt: fetchStart,
		})
	}
	c.JSON(http.StatusOK, gin.H{
		"nid": nid, "author_name": name, "author_intro": intro,
		"author_avatar": avatar, "works": works,
		"verdict": verdict, "observed_at": fetchStart, "source": "live",
	})
}

// ipGroups serves the IP tab's entry row: one form's books aggregated by
// contest (征文) — named IPs count DESC, total for the client's "other"
// fold. form=ip_collab is the intended caller.
func (s *Server) ipGroups(c *gin.Context) {
	form, ok := parseForm(c)
	if !ok || form == "" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return
	}
	total, groups, err := s.store.IpGroups(c.Request.Context(), form,
		c.Query("status"))
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":   gin.H{"pool": "seed", "form": form, "status": c.Query("status"), "ordering": "count"},
		"total":  total,
		"groups": groups,
	})
}

// yearGroups serves the short tab's year entry: a form's seed books
// aggregated by est_year (DESC) plus the pool total.
func (s *Server) yearGroups(c *gin.Context) {
	form, ok := parseForm(c)
	if !ok || form == "" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return
	}
	total, groups, err := s.store.YearGroups(c.Request.Context(), form)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":   gin.H{"pool": "seed", "form": form, "ordering": "year_desc"},
		"total":  total,
		"groups": groups,
	})
}

// genreGroups serves the short tab's genre browse entry: a form's seed
// books aggregated by genre (count DESC) plus the pool total.
func (s *Server) genreGroups(c *gin.Context) {
	form, ok := parseForm(c)
	if !ok || form == "" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return
	}
	total, groups, err := s.store.GenreGroups(c.Request.Context(), form)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":   gin.H{"pool": "seed", "form": form, "ordering": "count"},
		"total":  total,
		"groups": groups,
	})
}

// ipBooks serves one IP entry list: group names a contest exactly, or
// "other" for the long tail outside the top-2 contests by count.
func (s *Server) ipBooks(c *gin.Context) {
	form, ok := parseForm(c)
	if !ok || form == "" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return
	}
	group := c.Query("group")
	if group == "" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"group must be a contest name or 'other'")
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
			fail(c, http.StatusBadRequest, "invalid_argument",
				"offset must be a non-negative integer")
			return
		}
	}
	items, err := s.store.IpBooks(c.Request.Context(), form, group, limit, offset)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{"pool": "seed", "form": form, "group": group,
			"ordering": "favs"},
		"items": items,
	})
}

var validForms = map[string]bool{
	"invalid": true, "short": true, "medium": true, "long": true, "dialogue": true, "ip_collab": true,
}

// parseForm returns the optional docs/13 form filter. Empty means all forms.
func parseForm(c *gin.Context) (string, bool) {
	form := c.Query("form")
	if form == "" {
		return "", true
	}
	if !validForms[form] {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return "", false
	}
	return form, true
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

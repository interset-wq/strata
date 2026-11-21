package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"

	"strata/engine/internal/crawl"
	"strata/engine/internal/eras"
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

	// TTL cache + in-flight coalescing for the official board endpoints
	// (monthly-granularity data; one fetch per key serves repeated taps).
	ranksCache *officialRanksState
}

const (
	detailRefreshWindow = 24 * time.Hour
	detailRateLimitPref = "detail_rate_limit_enabled"
	appAPIPref          = "app_api_enabled"
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
		ranksCache: &officialRanksState{
			entries: map[string]struct {
				loadedAt time.Time
				body     []byte
			}{},
			inflight: map[string]chan []byte{},
		},
	}
	group := r.Group("/strata")
	group.GET("/healthz", srv.healthz)
	group.GET("/meta", srv.meta)
	group.GET("/settings", srv.settings)
	group.PUT("/settings", srv.updateSettings)
	group.GET("/books/:nid", srv.book)
	group.POST("/books/:nid/refresh", srv.bookRefresh)
	group.POST("/books/:nid/rank-seed", srv.bookRankSeed)
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
	group.GET("/search-history", srv.searchHistory)
	group.POST("/search/remote", srv.searchRemote)
	group.GET("/official-ranks/monthly", srv.officialRanksMonthly)
	group.GET("/official-ranks/pc", srv.officialRanksPc)
	group.GET("/official-ranks/mobile", srv.officialRanksMobile)
	group.GET("/official-ranks/sale-set", srv.officialRanksSaleSet)
	group.GET("/discovered", srv.discoveredList)
	group.DELETE("/discovered/:nid", srv.discoveredDelete)
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
	group.GET("/facets", srv.facets)
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
	appAPI, err := s.appAPIEnabled(c.Request.Context())
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"detail_rate_limit_enabled":     enabled,
		"detail_refresh_window_seconds": int64(detailRefreshWindow / time.Second),
		"app_api_enabled":               appAPI,
	})
}

func (s *Server) updateSettings(c *gin.Context) {
	var body struct {
		DetailRateLimitEnabled *bool `json:"detail_rate_limit_enabled"`
		AppAPIEnabled          *bool `json:"app_api_enabled"`
	}
	if err := c.ShouldBindJSON(&body); err != nil ||
		(body.DetailRateLimitEnabled == nil && body.AppAPIEnabled == nil) {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"detail_rate_limit_enabled or app_api_enabled is required")
		return
	}
	if body.DetailRateLimitEnabled != nil {
		if err := s.store.SetPref(c.Request.Context(), detailRateLimitPref, boolPref(*body.DetailRateLimitEnabled)); err != nil {
			fail(c, http.StatusInternalServerError, "internal", err.Error())
			return
		}
	}
	if body.AppAPIEnabled != nil {
		if err := s.store.SetPref(c.Request.Context(), appAPIPref, boolPref(*body.AppAPIEnabled)); err != nil {
			fail(c, http.StatusInternalServerError, "internal", err.Error())
			return
		}
	}
	s.settings(c)
}

func boolPref(v bool) string {
	if v {
		return "1"
	}
	return "0"
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

// appAPIEnabled returns the persisted App-API preference (设置页开关); when
// never set it falls back to the STRATA_APP_API env snapshot taken at
// startup (native dev runs). Off by default.
func (s *Server) appAPIEnabled(ctx context.Context) (bool, error) {
	v, ok, err := s.store.Pref(ctx, appAPIPref)
	if err != nil {
		return false, err
	}
	if !ok {
		return s.appAPI, nil
	}
	return v == "1" || v == "true", nil
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
		// Out-of-seed books (official-search discovery loop, docs/08
		// §search-remote): once a detail fetch has landed data in
		// user.db, serve the overlay view instead of 404. Seed-only
		// fields (est dating, form, percentiles) do not exist for
		// books outside the seed and stay absent.
		meta, merr := s.store.BookMeta(c.Request.Context(), nid)
		if merr != nil || meta == nil {
			fail(c, http.StatusNotFound, "not_found", "book not in seed")
			return
		}
		cover, _ := s.store.Cover(c.Request.Context(), nid)
		if cover == "" && meta.CoverURL != nil {
			cover = *meta.CoverURL
		}
		refresh, rerr := s.detailRefreshInfo(c.Request.Context(), nid, time.Now())
		if rerr != nil {
			fail(c, http.StatusInternalServerError, "internal", rerr.Error())
			return
		}
		book := gin.H{
			"nid":        nid,
			"title":      meta.Title,
			"author":     meta.Author,
			"genre":      meta.Genre,
			"price_type": meta.PriceType,
			"status":     meta.Status,
			"words":      meta.Words,
			"clicks":     meta.Clicks,
			"favs":       meta.Favs,
			"praises":    meta.Praises,
			"cover_url":  meta.CoverURL,
			"updated_at": meta.UpdatedAt,
			"summary":    meta.Summary,
			"has_comic":  meta.ComicID != nil && *meta.ComicID > 0,
			"has_audio":  meta.AlbumID != nil && *meta.AlbumID > 0,
		}
		eff := gin.H{
			"title":      meta.Title,
			"author":     meta.Author,
			"genre":      meta.Genre,
			"price_type": meta.PriceType,
			"status":     meta.Status,
			"cover_url":  meta.CoverURL,
			"summary":    meta.Summary,
			"words":      meta.Words,
			"clicks":     meta.Clicks,
			"favs":       meta.Favs,
			"praises":    meta.Praises,
			"updated_at": meta.UpdatedAt,
			"add_time":   meta.AddTime,
			"point":      meta.Point,
		}
		// nid dating for discovered books (docs/metrics-definitions §1.1):
		// interpolated from the embedded anchor table — the same
		// algorithm as the analysis pipeline, golden-tested against it.
		// Extrapolated nids (beyond the newest anchor) come out low-tier.
		er := eras.Estimate(nid)
		book["est_year"] = er.EstYear
		book["est_date"] = er.EstDate
		book["est_conf"] = er.Confidence
		eff["est_year"] = er.EstYear
		eff["est_date"] = er.EstDate
		eff["est_conf"] = er.Confidence
		c.JSON(http.StatusOK, gin.H{
			"source":    "local",
			"data_end":  s.store.Manifest.ContentEnd,
			"book":      book,
			"tags":      []string{},
			"local":     nil,
			"meta":      meta,
			"effective": eff,
			"cover":     cover,
			"refresh":   refresh,
		})
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
		out["has_comic"] = m.ComicID != nil && *m.ComicID > 0
		out["has_audio"] = m.AlbumID != nil && *m.AlbumID > 0
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
	contest := store.NormalizeContest(c.Query("contest"))

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
	year := 0
	if raw := c.Query("year"); raw != "" {
		var err error
		if year, err = strconv.Atoi(raw); err != nil ||
			year < s.store.Manifest.GenMin || year > s.store.Manifest.GenMax {
			fail(c, http.StatusBadRequest, "invalid_argument",
				"year must be between gen_min and gen_max")
			return
		}
	}
	items, err := s.store.BoardBooks(c.Request.Context(), kind, form, year, limit, offset)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{"kind": kind, "pool": "seed", "ordering": "cumulative",
			"form": form, "year": year, "licensed_excluded": true},
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
	wordsBand := c.Query("words-band")
	if wordsBand != "" && wordsBand != "short" &&
		wordsBand != "medium" && wordsBand != "long" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"words-band must be \"short\", \"medium\" or \"long\"")
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
	if order != "" && order != "favs" && order != "pct" && order != "clicks" &&
		order != "praises" && order != "words" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"order must be one of \"favs\", \"pct\", \"clicks\", \"praises\", \"words\"")
		return
	}
	dir := c.Query("dir")
	if dir != "" && dir != "asc" && dir != "desc" {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"dir must be \"asc\" or \"desc\"")
		return
	}
	contest := store.NormalizeContest(c.Query("contest"))
	tag := c.Query("tag")
	ptype := c.Query("ptype")
	items, err := s.store.ClassicBooks(c.Request.Context(),
		c.Query("genre"), c.Query("status"), contest, form, wordsBand,
		tag, ptype, year, limit, offset, order, dir)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	ordering := order
	if ordering == "" {
		ordering = "favs"
	}
	if order == "pct" {
		ordering = "fav_pctl"
	}
	dirEcho := "desc"
	if dir == "asc" {
		dirEcho = "asc"
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{
			"kind": "classic", "pool": "seed", "ordering": ordering,
			"genre": c.Query("genre"), "status": c.Query("status"),
			"contest": contest, "form": form, "year": year,
			"tag": tag, "ptype": ptype,
			"order": order, "dir": dirEcho, "licensed_excluded": true,
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

// rankingDeep serves the D2 full-universe generation boards. Unlike
// /rankings/favs (which reads the curated seed pool), the candidate universe
// here is the 241,758-row statistical frame, so early generations really do
// have a Top200 board. See app/docs/10-deep-ranks.md.
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
	// History write is best-effort: a busy user.db must not fail the
	// search itself (docs/08 §search-history).
	_ = s.store.AddSearchHistory(c.Request.Context(), q, len(items))
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

// searchHistory serves the recent local-search keywords for the search
// page empty state (docs/08 §search-history): distinct keywords, most
// recently used first, up to 50 (default 10).
func (s *Server) searchHistory(c *gin.Context) {
	limit := 10
	if raw := c.Query("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 && n <= 50 {
			limit = n
		}
	}
	words, err := s.store.SearchHistory(c.Request.Context(), limit)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": words})
}

// searchRemote runs the official HTML search (docs/08 §search-remote):
// a 30-row hard cap with silent rate limiting, so the UI triggers it
// manually and crawl enforces a 6-second self-cooldown. Seed hits are
// marked in_seed; out-of-seed hits go to user.db discovered (the
// discovery-loop entry). The throttled verdict is served as a flag,
// never faked as empty results.
func (s *Server) searchRemote(c *gin.Context) {
	q := c.Query("q")
	if q == "" {
		fail(c, http.StatusBadRequest, "invalid_argument", "q is required")
		return
	}
	fetchStart := time.Now().Unix()
	res, err := crawl.FetchSearch(c.Request.Context(), s.client, s.limiter, q, true)
	if err != nil {
		if errors.Is(err, crawl.ErrSearchTooSoon) {
			fail(c, http.StatusTooManyRequests, "too_soon", err.Error())
			return
		}
		fail(c, http.StatusBadGateway, "fetch_error", err.Error())
		return
	}
	if res.Throttled {
		c.JSON(http.StatusOK, gin.H{
			"meta":  gin.H{"kind": "search-remote", "q": q, "rate_limited": true},
			"items": []gin.H{},
		})
		return
	}
	nids := make([]int64, len(res.Items))
	for i, h := range res.Items {
		nids[i] = h.NID
	}
	inSeed, err := s.store.SeedNIDsIn(c.Request.Context(), nids)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	out := make([]gin.H, len(res.Items))
	var outside []store.DiscoveredHit
	for i, h := range res.Items {
		seed := inSeed[h.NID]
		out[i] = gin.H{
			"nid": h.NID, "title": h.Title, "author": h.Author,
			"updated_at": h.UpdatedAt, "cover_url": h.CoverURL,
			"summary": h.Summary, "in_seed": seed,
		}
		if !seed {
			outside = append(outside, store.DiscoveredHit{
				NID: h.NID, Title: h.Title, Author: h.Author,
				CoverURL: h.CoverURL, Summary: h.Summary,
			})
		}
	}
	// Discovery write-back is best-effort (docs/08 §search-remote).
	if len(outside) > 0 {
		_ = s.store.UpsertDiscoveredSearch(c.Request.Context(), outside, fetchStart)
	}
	c.JSON(http.StatusOK, gin.H{
		"meta": gin.H{"kind": "search-remote", "q": q,
			"rate_limited": false, "declared": res.Declared,
			"content_end": s.store.Manifest.ContentEnd},
		"items": out,
	})
}

// discoveredList serves the auto-collected out-of-seed books
// (docs/08 §discovered): most recently collected first, paged.
func (s *Server) discoveredList(c *gin.Context) {
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
	items, err := s.store.ListDiscovered(c.Request.Context(), limit, offset)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"kind": "discovered", "pool": "user"},
		"items": items,
	})
}

// discoveredDelete removes one auto-collected book (user tap on the
// discovery list). user.db only — the bundled seed is untouched.
func (s *Server) discoveredDelete(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	if err := s.store.DeleteDiscovered(c.Request.Context(), nid); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"deleted": nid})
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
// bookRankSeed pre-writes a minimal book_meta row from an official-rank
// entry (docs/08 §rank-seed): the rankings UI calls it right before
// navigating to /book/:nid, so an out-of-seed book renders its overlay
// immediately and the full data is completed by a background refresh
// instead of a ~10s blocking collect spinner. Local write only — never
// touches the network.
func (s *Server) bookRankSeed(c *gin.Context) {
	nid, err := strconv.ParseInt(c.Param("nid"), 10, 64)
	if err != nil || nid <= 0 {
		fail(c, http.StatusBadRequest, "invalid_argument", "nid must be a positive integer")
		return
	}
	var req struct {
		Title    string `json:"title"`
		Author   string `json:"author"`
		CoverURL string `json:"cover_url"`
		Genre    string `json:"genre"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		fail(c, http.StatusBadRequest, "invalid_argument", "invalid json body")
		return
	}
	if err := s.store.SeedFromRank(c.Request.Context(), nid, req.Title, req.Author, req.CoverURL, req.Genre); err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{"seeded": true})
}

// enrichAdpworks stores the official adaptation-works ids (App API
// /adpworks, docs/05 §6) after a successful alive write: comic_id and
// album_id (0 = confirmed none), plus the comic folderName archive when a
// comic exists. Pure best-effort: any failure leaves the columns NULL and
// never affects the refresh response. Gated by the app_api_enabled setting
// (STRATA_APP_API env bootstrap), off by default.
func (s *Server) enrichAdpworks(ctx context.Context, nid int64) {
	enabled, err := s.appAPIEnabled(ctx)
	if err != nil || !enabled {
		return
	}
	aw, err := crawl.FetchAdpWorks(ctx, s.client, s.limiter, nid, true)
	if err != nil || aw == nil {
		return
	}
	var folder *string
	if aw.ComicID > 0 {
		if c, cerr := crawl.FetchComic(ctx, s.client, s.limiter, aw.ComicID, true); cerr == nil && c != nil && c.FolderName != "" {
			f := c.FolderName
			folder = &f
		}
	}
	_ = s.store.SetAdaptation(ctx, nid, aw.ComicID, aw.AlbumID, folder)
}

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

	// App API enhancement (docs/05 §3.5): opt-in via the app_api_enabled
	// setting (STRATA_APP_API env bootstrap). On success every field the
	// response carries is persisted; ANY failure silently falls through to
	// the mobile HTML baseline — no retry, no user-visible error.
	if appAPIOn, sErr := s.appAPIEnabled(ctx); sErr == nil && appAPIOn {
		if app, aerr := crawl.FetchAppNovel(ctx, s.client, s.limiter, nid, true); aerr == nil {
			observedAt := time.Now().Unix()
			if err := s.writeApp(ctx, nid, app, observedAt); err == nil {
				s.enrichAdpworks(ctx, nid)
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
		s.enrichAdpworks(ctx, nid)
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
	newestFirst := true
	if o := c.Query("order"); o == "oldest" {
		newestFirst = false
	} else if o != "" && o != "newest" {
		fail(c, http.StatusBadRequest, "invalid_argument", "order must be newest|oldest")
		return
	}
	items, err := s.store.AuthorBooks(c.Request.Context(), author, limit, offset, newestFirst)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	ordering := "est_date_desc"
	if !newestFirst {
		ordering = "est_date_asc"
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":  gin.H{"pool": "seed", "ordering": ordering, "author": author},
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
				// works cache (v8): replay the official list stored at fetch
				// time instead of an always-empty array.
				worksResp := []crawl.AuthorWork{}
				if p.Works != nil && *p.Works != "" {
					if err := json.Unmarshal([]byte(*p.Works), &worksResp); err != nil {
						worksResp = []crawl.AuthorWork{}
					}
				}
				c.JSON(http.StatusOK, gin.H{
					"nid":           p.SourceNID,
					"author_name":   p.AuthorName,
					"author_intro":  p.AuthorIntro,
					"author_avatar": p.AuthorAvatar,
					"works":         worksResp,
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
		// works cache (v8): persist the official works list so cache
		// hits replay it (docs/08 §author-profile).
		var worksJSON *string
		if b, err := json.Marshal(works); err == nil {
			s := string(b)
			worksJSON = &s
		}
		_ = s.store.SaveAuthorProfile(c.Request.Context(), &store.AuthorProfile{
			AuthorKey: key, AuthorName: name, AuthorIntro: intro,
			AuthorAvatar: avatarPtr, Verdict: verdict,
			SourceNID: nid, ObservedAt: fetchStart, Works: worksJSON,
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

// facets serves the classic-list filter sheet's value lists for one form
// pool: genres / price types / top 60 tags / years, each with pool counts
// (user 2026-11-21: the unified multi-dimension filter on every classic
// rankings page). form "" (all forms) is allowed.
func (s *Server) facets(c *gin.Context) {
	form, ok := parseForm(c)
	if !ok {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"form must be invalid|short|medium|long|dialogue|ip_collab")
		return
	}
	genres, ptypes, tags, years, err := s.store.Facets(c.Request.Context(), form)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"meta":   gin.H{"pool": "seed", "form": form, "tag_limit": 60},
		"genres": genres, "ptypes": ptypes, "tags": tags, "years": years,
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
	group := store.NormalizeContest(c.Query("group"))
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

// ---------------------------------------------------------------------------
// Official SFACG boards (demo page; facts: docs/sfacg-live-ranks.md).
// All three fetchers go through the shared limiter, foreground priority.
// Board data is monthly granularity, so responses are cached per key
// (24h TTL) and concurrent taps on the same key are coalesced into one
// upstream request; a user-triggered tap that hits a full limiter queue
// waits (bounded retry) instead of failing — the drop-on-overflow rule
// stays for background jobs only.
// ---------------------------------------------------------------------------

// officialRanksTTL covers current-period boards (monthly granularity, 24h);
// officialRanksHistoricalTTL covers past months — that data never changes,
// so one fetch per session is enough.
const (
	officialRanksTTL           = 24 * time.Hour
	officialRanksHistoricalTTL = 365 * 24 * time.Hour
)

type officialRanksState struct {
	mu      sync.Mutex
	entries map[string]struct {
		loadedAt time.Time
		body     []byte
	}
	inflight map[string]chan []byte
}

var reOfficialMonth = regexp.MustCompile(`^\d{4}-(0[1-9]|1[0-2])$`)

var officialRanksMonthlyMeta = map[int]struct{ kind, note string }{
	0: {"月票榜", "月票票数榜——站内唯一公开的付费强度信号；免费书可入榜；按月清零"},
	2: {"新书榜", "官方月度新书榜（top 10）"},
	3: {"热销榜", "当期点券消耗（订阅额）排序；免费书结构性不可入榜"},
	4: {"对话月票榜", "对话产品线月票票数榜（2017-07 起）"},
}

var officialRanksMobileMeta = map[string]struct{ kind, note string }{
	"original": {"人气榜", "官方移动端人气榜 top 20（无数值，算法未公开）"},
	"bm":       {"收藏榜", "官方移动端收藏榜 top 20（无数值）"},
	"new":      {"新书榜", "官方移动端新书榜 top 20（无数值）"},
	"jp":       {"日轻榜", "日系轻小说池榜单 top 20（无数值）"},
	"sale":     {"热销榜", "官方移动端热销榜 top 20（无数值）"},
}

// officialRanksMonthly serves one board of one month from the historical
// monthly library (MonthlyBoy.ashx, 2013-03 onward, any month).
func (s *Server) officialRanksMonthly(c *gin.Context) {
	month := c.Query("date")
	if !reOfficialMonth.MatchString(month) {
		fail(c, http.StatusBadRequest, "invalid_argument", "date must be YYYY-MM")
		return
	}
	rank := 0
	if raw := c.Query("rank"); raw != "" {
		var err error
		if rank, err = strconv.Atoi(raw); err != nil {
			fail(c, http.StatusBadRequest, "invalid_argument", "rank must be an integer")
			return
		}
	}
	meta, ok := officialRanksMonthlyMeta[rank]
	if !ok {
		fail(c, http.StatusBadRequest, "invalid_argument", "rank must be 0|2|3|4")
		return
	}
	// Past months never change → cache for the session; the current month
	// is still filling in → 24h.
	ttl := officialRanksTTL
	now := time.Now()
	if month < fmt.Sprintf("%04d-%02d", now.Year(), int(now.Month())) {
		ttl = officialRanksHistoricalTTL
	}
	body, err := s.officialRanksServed(c.Request.Context(),
		"monthly:"+month+":"+strconv.Itoa(rank), ttl, func() ([]byte, error) {
			items, ferr := crawl.FetchMonthlyRanks(c.Request.Context(), s.client,
				s.limiter, month, rank, true)
			if ferr != nil {
				return nil, ferr
			}
			return json.Marshal(gin.H{
				"meta": gin.H{
					"source": "MonthlyBoy.ashx", "month": month, "rank": rank,
					"kind": meta.kind, "note": meta.note, "first_month": "2013-03",
				},
				"items": items,
			})
		})
	if err != nil {
		fail(c, http.StatusBadGateway, "upstream", err.Error())
		return
	}
	c.Data(http.StatusOK, "application/json; charset=utf-8", body)
}

// officialRanksServed returns the cached (or coalesced) response body for
// key; on a cache miss it runs fetch — which still goes through the
// limiter — and absorbs transient queue-full drops with a bounded 2s
// retry so a user-triggered tap queues instead of 502-ing.
func (s *Server) officialRanksServed(ctx context.Context, key string,
	ttl time.Duration, fetch func() ([]byte, error)) ([]byte, error) {
	st := s.ranksCache
	st.mu.Lock()
	if e, ok := st.entries[key]; ok && time.Since(e.loadedAt) < ttl {
		st.mu.Unlock()
		return e.body, nil
	}
	st.mu.Unlock()
	// user.db cache (v9): survives process restarts, so a cold start does
	// not re-fetch every official board from upstream.
	if body, ok, gerr := s.store.OfficialRanksGet(ctx, key, ttl); gerr == nil && ok {
		st.mu.Lock()
		st.entries[key] = struct {
			loadedAt time.Time
			body     []byte
		}{loadedAt: time.Now(), body: body}
		st.mu.Unlock()
		return body, nil
	}
	st.mu.Lock()
	if ch, ok := st.inflight[key]; ok {
		st.mu.Unlock()
		select {
		case b := <-ch:
			return b, nil
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	ch := make(chan []byte, 1)
	st.inflight[key] = ch
	st.mu.Unlock()

	var (
		body []byte
		err  error
	)
	for attempt := 0; ; attempt++ {
		body, err = fetch()
		if err == nil || !errors.Is(err, crawl.ErrQueueFull) {
			break
		}
		if attempt >= 8 {
			break
		}
		select {
		case <-ctx.Done():
			err = ctx.Err()
			break
		case <-time.After(2 * time.Second):
		}
	}

	st.mu.Lock()
	delete(st.inflight, key)
	if err == nil {
		st.entries[key] = struct {
			loadedAt time.Time
			body     []byte
		}{loadedAt: time.Now(), body: body}
	}
	st.mu.Unlock()

	if err == nil {
		// Best-effort persistence (v9): a write failure only means the next
		// cold start re-fetches; the in-memory cache still serves this run.
		_ = s.store.OfficialRanksPut(ctx, key, body)
	}

	if err != nil {
		return nil, err
	}
	ch <- body
	return body, nil
}

// officialRanksPc serves the four current-month boards of the PC Rank page
// (月票 with 票数 / 打赏 / 热销 are book boards; 粉丝 is reader-side).
func (s *Server) officialRanksPc(c *gin.Context) {
	// v2 key: the v1 cache body was written before cover enrichment.
	body, err := s.officialRanksServed(c.Request.Context(),
		"pc:current:v2", officialRanksTTL, func() ([]byte, error) {
			boards, ferr := crawl.FetchPcRanks(c.Request.Context(),
				s.client, s.limiter, true)
			if ferr != nil {
				return nil, ferr
			}
			// The PC rank page has no <img> in its rows. Join every nid back
			// to the seed/user cover so the UI does not fall back to the
			// default placeholder for the whole board (2026-11-21).
			nids := make([]int64, 0, len(boards)*20)
			for _, board := range boards {
				for _, entry := range board.Entries {
					if entry.NID > 0 {
						nids = append(nids, entry.NID)
					}
				}
			}
			covers, _ := s.store.CoverURLs(c.Request.Context(), nids)
			for bi := range boards {
				for ei := range boards[bi].Entries {
					entry := &boards[bi].Entries[ei]
					if entry.CoverURL == "" && entry.NID > 0 {
						entry.CoverURL = covers[entry.NID]
					}
				}
			}
			return json.Marshal(gin.H{
				"meta": gin.H{
					"source": "book.sfacg.com/Rank/",
					"note":   "PC 当期四榜：月票（带票数）/ 打赏 / 热销为书榜，粉丝榜为读者侧（消费火券，当期月榜）",
				},
				"boards": boards,
			})
		})
	if err != nil {
		fail(c, http.StatusBadGateway, "upstream", err.Error())
		return
	}
	c.Data(http.StatusOK, "application/json; charset=utf-8", body)
}

// officialRanksMobile serves one mobile board by slug (original/bm/new/jp/sale).
func (s *Server) officialRanksMobile(c *gin.Context) {
	slug := c.Query("board")
	meta, ok := officialRanksMobileMeta[slug]
	if !ok {
		fail(c, http.StatusBadRequest, "invalid_argument",
			"board must be original|bm|new|jp|sale")
		return
	}
	body, err := s.officialRanksServed(c.Request.Context(),
		"mobile:"+slug, officialRanksTTL, func() ([]byte, error) {
			items, ferr := crawl.FetchMobileRank(c.Request.Context(),
				s.client, s.limiter, slug, true)
			if ferr != nil {
				return nil, ferr
			}
			return json.Marshal(gin.H{
				"meta": gin.H{
					"source": "m.sfacg.com/rank/" + slug + ".html",
					"board":  slug, "kind": meta.kind, "note": meta.note,
				},
				"items": items,
			})
		})
	if err != nil {
		fail(c, http.StatusBadGateway, "upstream", err.Error())
		return
	}
	c.Data(http.StatusOK, "application/json; charset=utf-8", body)
}

// officialRanksSaleSet serves the passive "官方热销" signal: the nids
// currently on a cached 热销 board — 月榜库当期 rank=3, PC 月度热销榜.
// (移动热销 removed 2026-11-21: the official mobile-rank API is buggy and
// its data untrustworthy; the app no longer loads mobile boards.) It NEVER
// fetches: an empty or expired cache yields an empty set, so the endpoint
// is offline-safe and costs nothing to poll. Boards only enter the set
// after the user (or the rankings page) has loaded them at least once.
func (s *Server) officialRanksSaleSet(c *gin.Context) {
	now := time.Now()
	month := fmt.Sprintf("%04d-%02d", now.Year(), int(now.Month()))
	ids := map[int64]struct{}{}
	for _, key := range []string{
		"monthly:" + month + ":3", // 月榜库 当期热销榜
		"pc:current:v2",           // PC 月度热销榜（boards 里只取热销）
	} {
		body, ok, err := s.store.OfficialRanksGet(c.Request.Context(), key, officialRanksTTL)
		if err != nil || !ok {
			continue
		}
		var doc struct {
			Items  []crawl.RankEntry `json:"items"`
			Boards []crawl.PcBoard   `json:"boards"`
		}
		if err := json.Unmarshal(body, &doc); err != nil {
			continue
		}
		for _, it := range doc.Items {
			if it.NID > 0 {
				ids[it.NID] = struct{}{}
			}
		}
		for _, b := range doc.Boards {
			if !strings.Contains(b.Name, "热销") {
				continue
			}
			for _, it := range b.Entries {
				if it.NID > 0 {
					ids[it.NID] = struct{}{}
				}
			}
		}
	}
	out := make([]int64, 0, len(ids))
	for id := range ids {
		out = append(out, id)
	}
	sort.Slice(out, func(i, j int) bool { return out[i] < out[j] })
	c.JSON(http.StatusOK, gin.H{"nids": out})
}

package api

import (
	"context"
	"errors"
	"net/http"
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

const (
	defaultLimit = 50
	maxLimit     = 200
)

type Server struct {
	store   *store.Store
	limiter *crawl.Limiter
	client  *http.Client

	// Refresh debounce: same nid within the window returns the last
	// verdict without touching the limiter (docs/08).
	refreshMu   sync.Mutex
	refreshLast map[int64]refreshEntry
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
	}
	group := r.Group("/strata")
	group.GET("/healthz", srv.healthz)
	group.GET("/meta", srv.meta)
	group.GET("/books/:nid", srv.book)
	group.POST("/books/:nid/refresh", srv.bookRefresh)
	group.GET("/books/:nid/observations", srv.observations)
	group.GET("/rankings/favs", srv.rankingFavs)
	group.GET("/rankings/short", srv.rankingShort)
	group.GET("/rankings/new", srv.rankingNew)
	group.GET("/search", srv.search)
	group.GET("/shelf", srv.shelfList)
	group.PUT("/shelf", srv.shelfAdd)
	group.DELETE("/shelf/:nid", srv.shelfRemove)
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
	c.JSON(http.StatusOK, gin.H{
		"source":    source,
		"data_end":  s.store.Manifest.ContentEnd,
		"book":      detail.Book,
		"tags":      detail.Tags,
		"local":     detail.Local,
		"effective": effective(detail),
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

	items, err := s.store.RankingFavs(c.Request.Context(), year, genre, limit)
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
			&favs, &praises, &words, &status, &updatedAt); err != nil {
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

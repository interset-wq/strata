package api

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

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
	store *store.Store
}

func New(s *store.Store) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	srv := &Server{store: s}
	group := r.Group("/strata")
	group.GET("/healthz", srv.healthz)
	group.GET("/meta", srv.meta)
	group.GET("/books/:nid", srv.book)
	group.GET("/rankings/favs", srv.rankingFavs)
	group.GET("/rankings/short", srv.rankingShort)
	group.GET("/rankings/new", srv.rankingNew)
	group.GET("/search", srv.search)
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

// Booklist endpoints (docs/booklist-in-app.md). The official booklist API
// has no enumeration action, so the list endpoint probes a window of ten
// sequential ids — one fetch at a time through the shared limiter
// (queueCap 8: submitting a whole window at once would drop the tail).
// Each id's raw body is cached 24h in the official-ranks cache (booklists
// update — lastUpdateDateTime is the evidence) and parsed on every serve,
// so the local join stays live. A short page = end (the temp/novly-proven
// semantics on the live id space).
package api

import (
	"context"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"strata/engine/internal/crawl"
)

const (
	booklistPageSize = 10
	booklistTTL      = 24 * time.Hour
)

// booklistFetchFn builds the cache fetch closure for one id/kind (the
// default seam goes through the shared limiter, foreground lane).
func (s *Server) booklistFetchFn(ctx context.Context, id int, kind string) func() ([]byte, error) {
	return func() ([]byte, error) {
		b, err := s.booklistFetch(ctx, s.client, s.limiter, id, kind, true)
		if err != nil {
			return nil, err
		}
		return []byte(b), nil
	}
}

// booklists serves one window of the sequential-id booklist browser
// (docs/booklist-in-app.md: 页不满即到底; invalid ids are dropped,
// transport errors fail the request — the UI retries).
func (s *Server) booklists(c *gin.Context) {
	page := 1
	if raw := c.Query("page"); raw != "" {
		v, err := strconv.Atoi(raw)
		if err != nil || v < 1 {
			fail(c, http.StatusBadRequest, "invalid_argument", "page must be >= 1")
			return
		}
		page = v
	}
	ctx := c.Request.Context()
	items := []crawl.BooklistItem{}
	for i := 0; i < booklistPageSize; i++ {
		id := (page-1)*booklistPageSize + i + 1
		body, err := s.officialRanksServed(ctx, "booklist:"+strconv.Itoa(id),
			booklistTTL, s.booklistFetchFn(ctx, id, "item"))
		if err != nil {
			fail(c, http.StatusBadGateway, "upstream_error", err.Error())
			return
		}
		if it := crawl.ParseBooklistItem(string(body)); it != nil {
			items = append(items, *it)
		}
		// it == nil: invalid id (data missing) — deterministic, drop.
	}
	c.JSON(http.StatusOK, gin.H{
		"page":  page,
		"items": items,
		"done":  len(items) < booklistPageSize,
	})
}

// booklistNovelItem is one joined row of the detail endpoint: the official
// booklist fields plus the local join (in_library + form for seed books —
// nothing is fabricated for out-of-library works, docs/12 red line).
type booklistNovelItem struct {
	crawl.BooklistNovel
	InLibrary bool   `json:"in_library"`
	Form      string `json:"form,omitempty"`
}

// booklistNovels serves one booklist's header + work list (official order,
// no sort control) with the local seed join.
func (s *Server) booklistNovels(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil || id < 1 {
		fail(c, http.StatusBadRequest, "invalid_argument", "id must be a positive integer")
		return
	}
	ctx := c.Request.Context()
	key := "booklist:" + strconv.Itoa(id)
	metaBody, err := s.officialRanksServed(ctx, key, booklistTTL,
		s.booklistFetchFn(ctx, id, "item"))
	if err != nil {
		fail(c, http.StatusBadGateway, "upstream_error", err.Error())
		return
	}
	meta := crawl.ParseBooklistItem(string(metaBody))
	if meta == nil {
		fail(c, http.StatusNotFound, "not_found", "booklist not found")
		return
	}
	novelsBody, err := s.officialRanksServed(ctx, key+":novel", booklistTTL,
		s.booklistFetchFn(ctx, id, "novel"))
	if err != nil {
		fail(c, http.StatusBadGateway, "upstream_error", err.Error())
		return
	}
	novels := crawl.ParseBooklistNovels(string(novelsBody))
	nids := make([]int64, len(novels))
	for i, n := range novels {
		nids[i] = n.NID
	}
	local, err := s.store.BooksByNIDs(ctx, nids)
	if err != nil {
		fail(c, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	items := make([]booklistNovelItem, 0, len(novels))
	for _, n := range novels {
		lite, ok := local[n.NID]
		items = append(items, booklistNovelItem{n, ok, lite.Form})
	}
	c.JSON(http.StatusOK, gin.H{
		"booklist": meta,
		"items":    items,
	})
}

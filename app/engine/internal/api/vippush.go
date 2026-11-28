package api

import (
	"encoding/json"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"strata/engine/internal/store"
)

// 24h TTL per issue, same as preorder: the H5 page is server-rendered and
// curated, but future Saturdays may still gain entries. Empty pages are
// cached too (negative result).
const vippushTTL = 24 * time.Hour

type vippushEntry struct {
	loadedAt time.Time
	body     []byte
}

type vippushState struct {
	mu      sync.Mutex
	entries map[string]vippushEntry
}

// vipPush serves GET /strata/vippush?date=YYYYMMDD: the weekly VIP-release
// feature page (docs/sfacg-endpoints.md §7.6) proxied through the shared
// limiter and joined against seed.books so the UI can route in-library nids
// to the detail page. Same Saturday issue key as preorder, but a different
// data line: preorder = editor-picked upgrades, vippush = the whole release.
func (s *Server) vipPush(c *gin.Context) {
	key, err := normalizePreorderSaturday(c.Query("date"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	s.vippushCache.mu.Lock()
	entry, ok := s.vippushCache.entries[key]
	s.vippushCache.mu.Unlock()
	if ok && time.Since(entry.loadedAt) <= vippushTTL {
		c.Data(http.StatusOK, "application/json; charset=utf-8", entry.body)
		return
	}

	items, ferr := s.vippushFetch(c.Request.Context(), s.client, s.limiter, key, true)
	if ferr != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "上游不可达：" + ferr.Error()})
		return
	}

	nids := make([]int64, len(items))
	for i, it := range items {
		nids[i] = it.Nid
	}
	inLib, jerr := s.store.PreorderInLib(c.Request.Context(), nids)
	if jerr != nil {
		inLib = map[int64]store.InLibBook{}
	}

	out := make([]map[string]any, len(items))
	for i, it := range items {
		m := map[string]any{
			"nid":     it.Nid,
			"title":   it.Title,
			"cover":   it.Cover,
			"genre":   it.Genre,
			"tags":    it.Tags,
			"in_seed": false,
			"in_lib":  nil,
		}
		if lib, hit := inLib[it.Nid]; hit {
			m["in_seed"] = true
			m["in_lib"] = map[string]any{
				"author": lib.Author,
				"favs":   lib.Favs,
				"cover":  lib.Cover,
			}
		}
		out[i] = m
	}

	body, err := json.Marshal(gin.H{"date": key, "items": out})
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	s.vippushCache.mu.Lock()
	s.vippushCache.entries[key] = vippushEntry{loadedAt: time.Now(), body: body}
	s.vippushCache.mu.Unlock()
	c.Data(http.StatusOK, "application/json; charset=utf-8", body)
}

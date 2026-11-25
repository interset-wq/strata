package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"strata/engine/internal/store"
)

// 24h TTL per issue: the payload is editorially curated and static, but
// future weeks can still gain entries upstream, so re-check daily. Empty
// issues are cached too (negative result) — most pre-2020 weeks are empty.
const preorderTTL = 24 * time.Hour

type preorderEntry struct {
	loadedAt time.Time
	body     []byte
}

type preorderState struct {
	mu      sync.Mutex
	entries map[string]preorderEntry
}

// normalizePreorderSaturday accepts YYYYMMDD or YYYY-MM-DD and clamps to the
// Saturday of that week — the upstream issue key (§7.5: only Saturdays carry
// data; e.g. 2026-11-25 → 2026-11-28).
func normalizePreorderSaturday(raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	t, err := time.Parse("20060102", raw)
	if err != nil {
		t, err = time.Parse("2006-01-02", raw)
	}
	if err != nil {
		return "", fmt.Errorf("date must be YYYYMMDD")
	}
	// Saturday of the Monday-start week containing the day: back to Monday,
	// then forward 5 (Sunday keeps the Saturday just passed).
	t = t.AddDate(0, 0, -(int(t.Weekday())+6)%7)
	t = t.AddDate(0, 0, 5)
	return t.Format("20060102"), nil
}

// preorder serves GET /strata/preorder?date=YYYYMMDD: the official weekly
// pre-order issue (VIP upgrade preview) proxied through the shared limiter,
// joined against seed.books so the UI can route in-library nids to the
// detail page. Caliber red line (docs/sfacg-endpoints.md §7.5): the date is
// the planned VIP-upgrade week, never the first-publish date.
func (s *Server) preorder(c *gin.Context) {
	key, err := normalizePreorderSaturday(c.Query("date"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	s.preorderCache.mu.Lock()
	entry, ok := s.preorderCache.entries[key]
	s.preorderCache.mu.Unlock()
	if ok && time.Since(entry.loadedAt) <= preorderTTL {
		c.Data(http.StatusOK, "application/json; charset=utf-8", entry.body)
		return
	}

	items, ferr := s.preorderFetch(c.Request.Context(), s.client, s.limiter, key, true)
	if ferr != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "上游不可达：" + ferr.Error()})
		return
	}

	nids := make([]int64, len(items))
	for i, it := range items {
		nids[i] = it.NovelID
	}
	inLib, jerr := s.store.PreorderInLib(c.Request.Context(), nids)
	if jerr != nil {
		inLib = map[int64]store.InLibBook{}
	}

	out := make([]map[string]any, len(items))
	for i, it := range items {
		m := map[string]any{
			"nid":          it.NovelID,
			"title":        it.NovelName,
			"intro":        it.Intro,
			"cover":        it.Cover,
			"is_main_push": it.IsMainPush,
			"tags":         it.Tags,
			"in_seed":      false,
			"in_lib":       nil,
		}
		if lib, hit := inLib[it.NovelID]; hit {
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
	entry = preorderEntry{loadedAt: time.Now(), body: body}
	s.preorderCache.mu.Lock()
	s.preorderCache.entries[key] = entry
	s.preorderCache.mu.Unlock()
	c.Data(http.StatusOK, "application/json; charset=utf-8", body)
}

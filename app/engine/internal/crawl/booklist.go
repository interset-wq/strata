// Booklist fetcher (docs/booklist-in-app.md). The official booklist API
// (pages.sfacg.com/api/HttpProxy, actionName=/bookList/...) has NO
// enumeration action (a bare /bookList probes 404, 2026-11-22), so
// browsing walks sequential ids: an invalid id parses to nil and the
// caller drops it (temp/novly-proven semantics — a short page = end).
//
// All upstream values (charCount/viewTimes/markCount) are display-only
// classic-layer metrics — never recommendation signals (docs/12 red line).
package crawl

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// booklistAPI is the upstream base URL (a var so tests can point it at a
// stub; production is the pages.sfacg.com HttpProxy).
var booklistAPI = "https://pages.sfacg.com/api/HttpProxy"

// booklistTimeout bounds one probe. The shared client's 30s timeout alone
// would let a serial 10-id window spin for minutes on a black-holed mobile
// network (2026-11-23 device report); 15s is already generous for a small
// JSON metadata call.
var booklistTimeout = 15 * time.Second

// expand parameters (the fields the app rows actually display).
const (
	booklistExpandItem  = "avatar,verifyType,vipLevel,nickName,growup"
	booklistExpandNovel = "bigNovelCover,typeName,intropointCount,tags,sysTags"
)

// BooklistItem is one booklist (the list-window item and the detail header
// share the shape — the meta endpoint is the same /bookList/{id} action).
type BooklistItem struct {
	ID         int    `json:"id"`
	Title      string `json:"title"`
	Summary    string `json:"summary,omitempty"`
	Author     string `json:"author,omitempty"`
	Avatar     string `json:"avatar,omitempty"`
	VIP        bool   `json:"vip,omitempty"`
	MarkNum    int    `json:"mark_num"`
	Recommends int    `json:"recommend_num"`
	NovelNum   int    `json:"novel_num"`
	Updated    string `json:"updated,omitempty"`
}

// BooklistNovel is one work inside a booklist (official fields only — the
// API layer's local join adds in_library/form for seed books).
type BooklistNovel struct {
	NID    int64  `json:"nid"`
	Title  string `json:"title"`
	Author string `json:"author,omitempty"`
	Cover  string `json:"cover,omitempty"`
	Type   string `json:"type,omitempty"`
	Words  int64  `json:"words,omitempty"`
	Clicks int64  `json:"clicks,omitempty"`
	Favs   int64  `json:"favs,omitempty"`
	Finish bool   `json:"finish"`
	Note   string `json:"note,omitempty"`
}

// FetchBooklist fetches one booklist's metadata (kind "item") or its work
// list (kind "novel") through the shared limiter and returns the raw body:
// the API layer caches the bytes per id and parses on every serve, so the
// local join stays live — the same pattern as the roster endpoint.
func FetchBooklist(ctx context.Context, client *http.Client, l *Limiter,
	id int, kind string, foreground bool) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, booklistTimeout)
	defer cancel()
	var (
		body string
		ferr error
	)
	err := l.Submit(ctx, foreground, func() {
		action := "/bookList/" + strconv.Itoa(id)
		expand := booklistExpandItem
		if kind == "novel" {
			action += "/novel"
			expand = booklistExpandNovel
		}
		u := booklistAPI + "?actionName=" + url.QueryEscape(action) +
			"&expand=" + url.QueryEscape(expand)
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
		if err != nil {
			ferr = err
			return
		}
		req.Header.Set("User-Agent", ranksDesktopUA)
		req.Header.Set("Referer", "https://pages.sfacg.com/")
		b, err := doFetch(client, req)
		if err != nil {
			ferr = err
			return
		}
		body = string(b)
	})
	if err != nil {
		return "", err
	}
	if ferr != nil {
		return "", ferr
	}
	return body, nil
}

// ParseBooklistItem parses one /bookList/{id} response. Nil when the id is
// invalid or the interface is dead (data missing / errorCode != 200) — the
// caller degrades or drops, never retries.
func ParseBooklistItem(raw string) *BooklistItem {
	var doc struct {
		Status struct {
			ErrorCode int `json:"errorCode"`
		} `json:"status"`
		Data *struct {
			BookListID   int    `json:"bookListID"`
			Title        string `json:"title"`
			Summary      string `json:"summary"`
			MarkNum      int    `json:"markNum"`
			RecommendNum int    `json:"recommendNum"`
			NovelNum     int    `json:"novelNum"`
			LastUpdate   string `json:"lastUpdateDateTime"`
			User         *struct {
				NickName string `json:"nickName"`
				Expand   struct {
					Avatar   string `json:"avatar"`
					VIPLevel int    `json:"vipLevel"`
				} `json:"expand"`
			} `json:"user"`
		} `json:"data"`
	}
	if err := json.Unmarshal([]byte(raw), &doc); err != nil {
		return nil
	}
	if doc.Status.ErrorCode != 200 || doc.Data == nil || doc.Data.BookListID <= 0 {
		return nil
	}
	d := doc.Data
	it := &BooklistItem{
		ID:         d.BookListID,
		Title:      cleanText(d.Title),
		Summary:    cleanText(d.Summary),
		MarkNum:    d.MarkNum,
		Recommends: d.RecommendNum,
		NovelNum:   d.NovelNum,
	}
	if it.Title == "" {
		it.Title = "书单 #" + strconv.Itoa(d.BookListID)
	}
	if len(d.LastUpdate) >= 10 {
		it.Updated = d.LastUpdate[:10]
	}
	if d.User != nil {
		it.Author = d.User.NickName
		it.Avatar = normalizeURL(d.User.Expand.Avatar)
		it.VIP = d.User.Expand.VIPLevel > 0
	}
	return it
}

// ParseBooklistNovels parses a /bookList/{id}/novel response (the official
// order is preserved — v1 has no sort control). Nil for a dead interface
// (the API layer's meta fetch fails first for dead ids, so an empty slice
// here reads as "empty booklist").
func ParseBooklistNovels(raw string) []BooklistNovel {
	var doc struct {
		Status struct {
			ErrorCode int `json:"errorCode"`
		} `json:"status"`
		Data *struct {
			Items []struct {
				Summary string `json:"summary"`
				Novels  struct {
					NovelID    int64  `json:"novelId"`
					NovelName  string `json:"novelName"`
					AuthorName string `json:"authorName"`
					NovelCover string `json:"novelCover"`
					CharCount  int64  `json:"charCount"`
					ViewTimes  int64  `json:"viewTimes"`
					MarkCount  int64  `json:"markCount"`
					IsFinish   bool   `json:"isFinish"`
					Expand     struct {
						BigCover string `json:"bigNovelCover"`
						TypeName string `json:"typeName"`
					} `json:"expand"`
				} `json:"novels"`
			} `json:"items"`
		} `json:"data"`
	}
	if err := json.Unmarshal([]byte(raw), &doc); err != nil {
		return nil
	}
	if doc.Status.ErrorCode != 200 || doc.Data == nil {
		return nil
	}
	out := make([]BooklistNovel, 0, len(doc.Data.Items))
	for _, it := range doc.Data.Items {
		n := it.Novels
		if n.NovelID <= 0 {
			continue
		}
		cover := normalizeURL(n.Expand.BigCover)
		if cover == "" {
			cover = normalizeURL(n.NovelCover)
		}
		out = append(out, BooklistNovel{
			NID:    n.NovelID,
			Title:  cleanText(n.NovelName),
			Author: cleanText(n.AuthorName),
			Cover:  cover,
			Type:   n.Expand.TypeName,
			Words:  n.CharCount,
			Clicks: n.ViewTimes,
			Favs:   n.MarkCount,
			Finish: n.IsFinish,
			Note:   cleanText(it.Summary),
		})
	}
	return out
}

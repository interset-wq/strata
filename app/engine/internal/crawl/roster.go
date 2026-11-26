// Contest roster fetcher (docs/contest-roster-fields.md §1). Two endpoint
// generations keyed by the static tag table (store/roster_tags.go):
//
//	new SPA (2023+):  GET /api/essay/getNovels?tagIds=&page=&size<=500
//	old H5 (2018-22): GET /ajax/ashx/Common.ashx?op=getNovelsByTag&tagId=&ps<=200&pi(0基)
//
// Rows carry exactly six fields (nid/title/author/intro/cover/categoryID) —
// no 成绩/定年/获奖/名次. Those come from the local join at the API layer,
// never from this endpoint (docs/contest-display-in-app.md).
//
// A dead interface (errorCode != 200 / bare status != 200 / structure
// missing / malformed body) parses to nil — the caller degrades to the
// in-library view and must not retry.
package crawl

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
)

// RosterEntry is one row of an official contest roster (six fields only).
type RosterEntry struct {
	NID    int64  `json:"nid"`
	Title  string `json:"title"`
	Author string `json:"author,omitempty"`
	Intro  string `json:"intro,omitempty"`
	Cover  string `json:"cover,omitempty"`
	// CategoryID is a division hint only (0 常规 / 1 对话 / 3 征文短篇赛道 /
	// 4 沉浸式互动) — never a form truth (E.28 只正向用 1/4).
	CategoryID int `json:"category_id,omitempty"`
}

// RosterPage is one fetched page. TotalPage is server-computed for the
// requested size (not a fixed value) — always page relative to it. Size
// records the page length actually served (the handler may downgrade it
// on the size boundary trap), so the API layer can turn TotalPage into a
// rough total estimate.
type RosterPage struct {
	TotalPage int           `json:"total_page"`
	Size      int           `json:"size,omitempty"`
	Entries   []RosterEntry `json:"entries"`
}

// rosterOldCoverBase completes the old H5 cover path fragment
// ("YYYY/MM/uuid.jpg") to the production CDN URL (new-gen covers are full
// URLs; docs/contest-roster-fields.md §3).
const rosterOldCoverBase = "https://rs.sfacg.com/web/novel/images/NovelCover/Big/"

// rosterEntryFrom builds a RosterEntry, dropping placeholder rows without a
// positive nid (the endpoints mix those into early lists).
func rosterEntryFrom(nid int64, categoryID int, name, author, intro, cover string) (RosterEntry, bool) {
	if nid <= 0 {
		return RosterEntry{}, false
	}
	e := RosterEntry{
		NID:        nid,
		Title:      cleanText(name),
		Cover:      normalizeURL(cover),
		CategoryID: categoryID,
	}
	if author != "" {
		e.Author = cleanText(author)
	}
	if intro != "" {
		e.Intro = cleanIntroText(intro)
	}
	return e, true
}

// ParseRosterNew parses the 2023+ SPA response
// {"status":{"errorCode":200},"data":{"totalPage":N,"novels":[...]}} —
// lower-cased field names, full cover URLs. Nil when the interface is dead.
func ParseRosterNew(body string) *RosterPage {
	var doc struct {
		Status struct {
			ErrorCode int `json:"errorCode"`
		} `json:"status"`
		Data *struct {
			TotalPage int `json:"totalPage"`
			Novels    []struct {
				NovelID    int64  `json:"novelID"`
				CategoryID int    `json:"categoryID"`
				NovelName  string `json:"novelName"`
				AuthorName string `json:"authorName"`
				Intro      string `json:"intro"`
				Cover      string `json:"cover"`
			} `json:"novels"`
		} `json:"data"`
	}
	if err := json.Unmarshal([]byte(body), &doc); err != nil {
		return nil
	}
	if doc.Status.ErrorCode != 200 || doc.Data == nil {
		return nil
	}
	p := &RosterPage{TotalPage: doc.Data.TotalPage, Entries: []RosterEntry{}}
	for _, it := range doc.Data.Novels {
		if e, ok := rosterEntryFrom(it.NovelID, it.CategoryID, it.NovelName,
			it.AuthorName, it.Intro, it.Cover); ok {
			p.Entries = append(p.Entries, e)
		}
	}
	return p
}

// ParseRosterOld parses the 2018-2022 H5 response
// {"status":200,"totalPage":N,"novels":[...]} — note the bare integer
// status (no data wrapper), upper-cased field names, and cover path
// fragments that need the CDN prefix. Nil when the interface is dead.
func ParseRosterOld(body string) *RosterPage {
	var doc struct {
		Status    int `json:"status"`
		TotalPage int `json:"totalPage"`
		Novels    []struct {
			NovelID    int64  `json:"NovelID"`
			CategoryID int    `json:"CategoryID"`
			NovelName  string `json:"NovelName"`
			AuthorName string `json:"AuthorName"`
			Intro      string `json:"Intro"`
			Cover      string `json:"Cover"`
		} `json:"novels"`
	}
	if err := json.Unmarshal([]byte(body), &doc); err != nil {
		return nil
	}
	if doc.Status != 200 {
		return nil
	}
	p := &RosterPage{TotalPage: doc.TotalPage, Entries: []RosterEntry{}}
	for _, it := range doc.Novels {
		cover := normalizeURL(it.Cover)
		if !strings.HasPrefix(cover, "http") {
			cover = rosterOldCoverBase + cover
		}
		if e, ok := rosterEntryFrom(it.NovelID, it.CategoryID, it.NovelName,
			it.AuthorName, it.Intro, cover); ok {
			p.Entries = append(p.Entries, e)
		}
	}
	return p
}

// FetchRoster fetches one page of one tag's roster through the shared
// limiter (user-triggered = foreground lane). gen selects the endpoint
// generation — the values mirror store.RosterGenNew ("new") /
// store.RosterGenOld ("old") from the contest ledger; an unknown value is an
// error, not a guess. page is the upstream page index (0-based for both
// generations, 2026-11-26 probe), size is the per-generation page length
// (new <= 500, old ps <= 200).
//
// Result contract: err != nil = transport/queue problem; err == nil and
// page == nil = interface dead (degrade, never retry); otherwise the page
// (possibly empty — the size boundary trap, see the handler's downgrade).
func FetchRoster(ctx context.Context, client *http.Client, l *Limiter,
	gen string, tag, page, size int, foreground bool) (*RosterPage, error) {
	var (
		res  *RosterPage
		perr error
	)
	err := l.Submit(ctx, foreground, func() {
		var u string
		switch gen {
		case "new":
			u = "https://pages.sfacg.com/api/essay/getNovels" +
				"?tagIds=" + strconv.Itoa(tag) +
				"&page=" + strconv.Itoa(page) +
				"&size=" + strconv.Itoa(size)
		case "old":
			u = "https://pages.sfacg.com/ajax/ashx/Common.ashx" +
				"?op=getNovelsByTag&tagId=" + strconv.Itoa(tag) +
				"&ps=" + strconv.Itoa(size) +
				"&pi=" + strconv.Itoa(page)
		default:
			perr = fmt.Errorf("crawl: unknown roster gen %q", gen)
			return
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
		if err != nil {
			perr = err
			return
		}
		req.Header.Set("User-Agent", ranksDesktopUA)
		req.Header.Set("Referer", "https://pages.sfacg.com/")
		body, err := doFetch(client, req)
		if err != nil {
			perr = err
			return
		}
		if gen == "new" {
			res = ParseRosterNew(string(body))
		} else {
			res = ParseRosterOld(string(body))
		}
	})
	if err != nil {
		return nil, err
	}
	if perr != nil {
		return nil, perr
	}
	if res != nil {
		res.Size = size
	}
	return res, nil
}

// Package crawl — official SFACG board fetchers (docs/sfacg-live-ranks.md):
//
//  1. MonthlyBoy.ashx — the historical monthly library (2013-03 onward, any
//     month, month-cleared). rank 0/2/3/4 = 月票/新书/热销/对话月票.
//  2. book.sfacg.com/Rank/ — the PC current-month page: four bd_PHB boards
//     (月票 with 票数, 打赏, 热销, plus the reader-side 粉丝 board).
//  3. m.sfacg.com/rank/{original,bm,new,jp,sale}.html — five mobile boards,
//     top 20 each, no values, nid in /b/{nid}/ links.
package crawl

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
)

// RankEntry is one row of an official board, shared by all three sources.
// NID is 0 for reader-side rows (粉丝 board); Value carries 月票/火券 when
// the source publishes one.
type RankEntry struct {
	NID      int64  `json:"nid"`
	Rank     int    `json:"rank"`
	Title    string `json:"title"`
	Author   string `json:"author,omitempty"`
	Genre    string `json:"genre,omitempty"`
	CoverURL string `json:"cover_url,omitempty"`
	Value    int    `json:"value,omitempty"`
}

// PcBoard is one named board of the PC Rank page.
type PcBoard struct {
	Name    string      `json:"name"`
	Entries []RankEntry `json:"entries"`
}

const (
	ranksDesktopUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
	ranksMobileUA  = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36"
)

// ---------------------------------------------------------------------------
// 1. MonthlyBoy.ashx (historical monthly library, JSON)
// ---------------------------------------------------------------------------

// ParseMonthlyRanks parses the MonthlyBoy.ashx getRanks response:
// {"data":[{"nid":…,"name":…,"ticketNum":…,"authorName":…,"cover":…}]}.
// Rows with a missing/non-positive nid are dropped (the endpoint mixes
// placeholder rows into early months).
func ParseMonthlyRanks(body string) []RankEntry {
	var doc struct {
		Data []struct {
			NID        int64   `json:"nid"`
			Name       string  `json:"name"`
			TicketNum  int     `json:"ticketNum"`
			AuthorName *string `json:"authorName"`
			Cover      string  `json:"cover"`
		} `json:"data"`
	}
	if err := json.Unmarshal([]byte(body), &doc); err != nil {
		return nil
	}
	items := make([]RankEntry, 0, len(doc.Data))
	for _, it := range doc.Data {
		if it.NID <= 0 {
			continue
		}
		e := RankEntry{
			NID:     it.NID,
			Rank:    len(items) + 1,
			Title:   it.Name,
			Value:   it.TicketNum,
			CoverURL: normalizeURL(it.Cover),
		}
		if it.AuthorName != nil {
			e.Author = cleanText(*it.AuthorName)
		}
		items = append(items, e)
	}
	return items
}

// ---------------------------------------------------------------------------
// 2. PC Rank page (four bd_PHB boards)
// ---------------------------------------------------------------------------

var (
	// The 粉丝 board's title li embeds a 月/总 tab sub-<ul>, so only take
	// the first text line of the li.
	rePcBoardTitle = regexp.MustCompile(`(?s)<li class="bd_PHB_li1">\s*([^<\n]+)`)
	rePcRow        = regexp.MustCompile(`(?s)<li class="bd_PHB_list"><span>(\d+)</span><span[^>]*>(.*?)</span>(\d+)?</li>`)
	rePcLink       = regexp.MustCompile(`<a href="([^"]+)"[^>]*>([^<]+)</a>`)
)

// ParsePcRanks parses the four boards of book.sfacg.com/Rank/. Book boards
// carry nid + optional 票数 (月票 board); the 粉丝 board is reader-side
// (username, 消费火券, no nid). The 粉丝 board has 月/总 sub-tabs; only the
// 月 (current month) rows are returned.
func ParsePcRanks(html string) []PcBoard {
	boards := []PcBoard{}
	blocks := strings.Split(html, `<ul class="bd_PHB">`)
	for _, block := range blocks[1:] {
		block = cutToNextBoard(block)
		if strings.Contains(block, `id="tab1_1"`) {
			// 粉丝 board: keep only the 月 sub-tab block.
			if i := strings.Index(block, `id="tab1_1"`); i >= 0 {
				block = block[:i]
			}
		}
		tm := rePcBoardTitle.FindStringSubmatch(block)
		if tm == nil {
			continue
		}
		name := strings.TrimSpace(reStripSfprefix.ReplaceAllString(tm[1], ""))
		board := PcBoard{Name: name, Entries: []RankEntry{}}
		for _, row := range rePcRow.FindAllStringSubmatch(block, -1) {
			inner := row[2]
			entry := RankEntry{}
			if rm, err := strconv.Atoi(row[1]); err == nil {
				entry.Rank = rm
			} else {
				continue
			}
			if lm := rePcLink.FindStringSubmatch(inner); lm != nil {
				entry.Title = cleanText(lm[2])
				if nm := reNovelNID.FindStringSubmatch(lm[1]); nm != nil {
					if n, err := strconv.ParseInt(nm[1], 10, 64); err == nil {
						entry.NID = n
					}
				}
			}
			if entry.Title == "" {
				continue
			}
			if row[3] != "" {
				if v, err := strconv.Atoi(row[3]); err == nil {
					entry.Value = v
				}
			}
			board.Entries = append(board.Entries, entry)
		}
		boards = append(boards, board)
	}
	return boards
}

var (
	reStripSfprefix = regexp.MustCompile(`^SF轻小说`)
	reNovelNID      = regexp.MustCompile(`/Novel/(\d+)/`)
)

// cutToNextBoard trims a bd_PHB block at the page footer or any markup that
// is not part of the board list.
func cutToNextBoard(block string) string {
	if i := strings.Index(block, `<div class="footer"`); i >= 0 {
		block = block[:i]
	}
	if i := strings.LastIndex(block, `</ul>`); i >= 0 {
		block = block[:i]
	}
	return block
}

// ---------------------------------------------------------------------------
// 3. Mobile rank pages (five boards, no values)
// ---------------------------------------------------------------------------

var (
	reMobileBlock   = regexp.MustCompile(`(?s)<ul class="book_bk_qs1 book_list">(.*?)</ul>`)
	reMobileNID     = regexp.MustCompile(`/b/(\d+)/`)
	reMobileCover   = regexp.MustCompile(`<img src="([^"]+)"`)
	reMobileTitle   = regexp.MustCompile(`id="listtitle">([^<]+)<`)
	reMobileAuthorG = regexp.MustCompile(`(?s)<div>([^<]+?/[^<]+?)</div>`)
)

// ParseMobileRank parses one m.sfacg.com/rank/{slug}.html page: top 20
// rows, each a cover + listtitle + 「作者 / 题材」.
func ParseMobileRank(html string) []RankEntry {
	items := []RankEntry{}
	for _, m := range reMobileBlock.FindAllStringSubmatch(html, -1) {
		seg := m[1]
		e := RankEntry{Rank: len(items) + 1}
		if n := reMobileNID.FindStringSubmatch(seg); n != nil {
			if id, err := strconv.ParseInt(n[1], 10, 64); err == nil {
				e.NID = id
			}
		}
		if t := reMobileTitle.FindStringSubmatch(seg); t != nil {
			e.Title = cleanText(t[1])
		}
		if c := reMobileCover.FindStringSubmatch(seg); c != nil {
			e.CoverURL = normalizeURL(c[1])
		}
		if ag := reMobileAuthorG.FindStringSubmatch(seg); ag != nil {
			author, genre, _ := strings.Cut(ag[1], "/")
			e.Author = strings.TrimSpace(author)
			e.Genre = strings.TrimSpace(genre)
		}
		if e.NID > 0 && e.Title != "" {
			items = append(items, e)
		}
	}
	return items
}

// ---------------------------------------------------------------------------
// Fetch wrappers (all foreground, through the shared limiter)
// ---------------------------------------------------------------------------

func doFetch(client *http.Client, req *http.Request) ([]byte, error) {
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("http %d", resp.StatusCode)
	}
	buf := make([]byte, 0, 64*1024)
	tmp := make([]byte, 8192)
	for {
		n, rerr := resp.Body.Read(tmp)
		buf = append(buf, tmp[:n]...)
		if rerr != nil || len(buf) > 512*1024 {
			break
		}
	}
	return buf, nil
}

// FetchMonthlyRanks fetches one board of one month from the historical
// library (2013-03 onward). month is "YYYY-MM"; rank is 0/2/3/4.
func FetchMonthlyRanks(ctx context.Context, client *http.Client, l *Limiter, month string, rank int, foreground bool) ([]RankEntry, error) {
	var (
		res  []RankEntry
		perr error
	)
	err := l.Submit(ctx, foreground, func() {
		u := "https://pages.sfacg.com/ajax/act/MonthlyBoy.ashx" +
			"?op=getRanks&date=" + month + "&rank=" + strconv.Itoa(rank)
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
		res = ParseMonthlyRanks(string(body))
	})
	if err != nil {
		return nil, err
	}
	if perr != nil {
		return nil, perr
	}
	return res, nil
}

// FetchPcRanks fetches the four current-month boards of the PC Rank page.
func FetchPcRanks(ctx context.Context, client *http.Client, l *Limiter, foreground bool) ([]PcBoard, error) {
	var (
		res  []PcBoard
		perr error
	)
	err := l.Submit(ctx, foreground, func() {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			"https://book.sfacg.com/Rank/", nil)
		if err != nil {
			perr = err
			return
		}
		req.Header.Set("User-Agent", ranksDesktopUA)
		body, err := doFetch(client, req)
		if err != nil {
			perr = err
			return
		}
		res = ParsePcRanks(string(body))
	})
	if err != nil {
		return nil, err
	}
	if perr != nil {
		return nil, perr
	}
	return res, nil
}

// MobileBoardSlugs are the five mobile board slugs in display order.
var MobileBoardSlugs = []string{"original", "bm", "new", "jp", "sale"}

// FetchMobileRank fetches one mobile board by slug (see MobileBoardSlugs).
func FetchMobileRank(ctx context.Context, client *http.Client, l *Limiter, slug string, foreground bool) ([]RankEntry, error) {
	var (
		res  []RankEntry
		perr error
	)
	err := l.Submit(ctx, foreground, func() {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			"https://m.sfacg.com/rank/"+slug+".html", nil)
		if err != nil {
			perr = err
			return
		}
		req.Header.Set("User-Agent", ranksMobileUA)
		body, err := doFetch(client, req)
		if err != nil {
			perr = err
			return
		}
		res = ParseMobileRank(string(body))
	})
	if err != nil {
		return nil, err
	}
	if perr != nil {
		return nil, perr
	}
	return res, nil
}

package crawl

import (
	"context"
	"fmt"
	"html"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// DetailState is the three-state verdict per docs/05 §4.3. Status codes are
// ignored (invalid nids return 200); the verdict comes from page content.
type DetailState int

const (
	DetailAlive DetailState = iota
	DetailDead
	DetailZombie
)

func (s DetailState) String() string {
	switch s {
	case DetailAlive:
		return "alive"
	case DetailDead:
		return "dead"
	default:
		return "zombie"
	}
}

// Detail is the parsed mobile page (docs/05 §4.1). Only alive pages get one.
// Every field the page exposes is parsed in the same request; none is wasted.
type Detail struct {
	Title     string `json:"title,omitempty"`
	Author    string `json:"author,omitempty"`
	Genre     string `json:"genre,omitempty"`
	PriceType string `json:"price_type,omitempty"`
	CoverURL  string `json:"cover_url,omitempty"`
	Summary   string `json:"summary,omitempty"`
	Favs      int64  `json:"favs"`
	Praises   int64  `json:"praises"`
	Words     int64  `json:"words"`
	Status    string `json:"status"`
	UpdatedAt string `json:"updated_at"`
}

var (
	reErrorPage = regexp.MustCompile(`出错啦`)
	reCatalog   = regexp.MustCompile(`book_Catalog"\s*>`)
	reCatalogA  = regexp.MustCompile(`<a\s`)
	reInteract  = regexp.MustCompile(`book_interact`)
	reSmall     = regexp.MustCompile(`<small>\s*(-?[\d,]+)\s*</small>`)
	reWords     = regexp.MustCompile(`book_info3">[^<]*?([\d,]+)字`)
	reStatus    = regexp.MustCompile(`(已完结|连载中)`)
	reUpdated   = regexp.MustCompile(`\b(\d{2})-(\d{2})-(\d{2}) (\d{2}):(\d{2})\b`)
	reTitle     = regexp.MustCompile(`(?s)class="book_newtitle"[^>]*>(.*?)</span>`)
	reInfo2     = regexp.MustCompile(`(?s)class="book_info2"[^>]*>(.*?)</div>`)
	reInfo2Span = regexp.MustCompile(`(?s)<span[^>]*>(.*?)</span>`)
	reInfo3     = regexp.MustCompile(`(?s)class="book_info3"[^>]*>(.*?)</span>`)
	reInfo3AW   = regexp.MustCompile(`(?s)^\s*(.*?)\s*/\s*([\d,]+)\s*字`)
	reInfoCover = regexp.MustCompile(`(?s)<ul[^>]*class="book_info"[^>]*>.*?<img[^>]+src=['"]([^'"]+)['"]`)
	reProfile   = regexp.MustCompile(`(?s)<ul class="book_profile">(.*?)</ul>`)
	reSummary   = regexp.MustCompile(`(?s)<li[^>]*class="book_bk_qs1"[^>]*>(.*?)</li>`)
	reTag       = regexp.MustCompile(`(?s)<[^>]+>`)
)

// detailGenres is the nine-way genre vocabulary used by seed.books.
var detailGenres = map[string]bool{
	"魔幻": true, "玄幻": true, "古风": true, "科幻": true, "校园": true,
	"都市": true, "游戏": true, "同人": true, "悬疑": true,
}

// ParseDetail is a pure function: HTML in, verdict out (docs/05 §4.4). It
// must not touch the network, the database, or the clock. Verdict order
// per §4.3: dead → zombie (no catalog link / illegal numbers) → alive.
func ParseDetail(html string) (DetailState, *Detail) {
	// Dead: the mobile negative copy. HTTP status carries zero information.
	if reErrorPage.MatchString(html) {
		return DetailDead, nil
	}

	// Zombie check 1: the catalog container has no links to chapter lists.
	// Structural evidence beats keyword search (docs/05 §4.3).
	if m := reCatalog.FindStringIndex(html); m != nil {
		window := html[m[0]:min(m[1]+400, len(html))]
		if !reCatalogA.MatchString(window) {
			return DetailZombie, nil
		}
	}

	// Parse numbers; collect first two <small> values after book_interact
	// (favs, praises; the reward item has no number, monthly tickets are
	// discarded in v1).
	interact := reInteract.FindStringIndex(html)
	if interact == nil {
		return DetailZombie, nil
	}
	window := html[interact[0]:min(interact[0]+600, len(html))]
	small := reSmall.FindAllStringSubmatch(window, 2)
	if len(small) < 2 {
		return DetailZombie, nil
	}
	favs, err1 := parseNum(small[0][1])
	praises, err2 := parseNum(small[1][1])
	if err1 != nil || err2 != nil {
		return DetailZombie, nil
	}

	// Zombie check 2: negative counts are illegal by definition (docs/05
	// §4.3: negative_favs sample of 58 books with a reading entrance).
	if favs < 0 || praises < 0 {
		return DetailZombie, nil
	}

	d := Detail{Favs: favs, Praises: praises}

	if m := reTitle.FindStringSubmatch(html); m != nil {
		d.Title = cleanText(m[1])
	}
	if m := reInfo2.FindStringSubmatch(html); m != nil {
		for _, sm := range reInfo2Span.FindAllStringSubmatch(m[1], -1) {
			value := cleanText(sm[1])
			switch {
			case detailGenres[value] && d.Genre == "":
				d.Genre = value
			case (value == "已完结" || value == "连载中") && d.Status == "":
				d.Status = value
			case value != "" && d.PriceType == "":
				d.PriceType = value
			}
		}
	}
	if m := reInfo3.FindStringSubmatch(html); m != nil {
		info := cleanText(m[1])
		if aw := reInfo3AW.FindStringSubmatch(info); aw != nil {
			d.Author = cleanText(aw[1])
			if w, err := parseNum(aw[2]); err == nil && w > 0 {
				d.Words = w
			}
		}
		// Two-digit year: always a 20xx date, stored as sortable TEXT (§4.2).
		if u := reUpdated.FindStringSubmatch(info); u != nil {
			d.UpdatedAt = "20" + u[1] + "-" + u[2] + "-" + u[3] + " " + u[4] + ":" + u[5] + ":00"
		}
	}
	if d.Words == 0 {
		if m := reWords.FindStringSubmatch(html); m != nil {
			if w, err := parseNum(m[1]); err == nil && w > 0 {
				d.Words = w
			}
		}
	}
	if d.Status == "" {
		if m := reStatus.FindStringSubmatch(html); m != nil {
			d.Status = m[1]
		}
	}
	if d.UpdatedAt == "" {
		if m := reUpdated.FindStringSubmatch(html); m != nil {
			d.UpdatedAt = "20" + m[1] + "-" + m[2] + "-" + m[3] + " " + m[4] + ":" + m[5] + ":00"
		}
	}
	if m := reInfoCover.FindStringSubmatch(html); m != nil {
		d.CoverURL = normalizeURL(m[1])
	}
	if m := reProfile.FindStringSubmatch(html); m != nil {
		if sm := reSummary.FindStringSubmatch(m[1]); sm != nil {
			d.Summary = cleanText(sm[1])
		}
	}

	// Illegal numbers that survived the sign check: all-zero anomalies.
	if favs == 0 && praises == 0 {
		return DetailZombie, nil
	}
	return DetailAlive, &d
}

// cleanText turns a small HTML fragment into display text: tags become
// spaces, entities are decoded, and runs of whitespace collapse.
func cleanText(s string) string {
	s = reTag.ReplaceAllString(s, " ")
	s = html.UnescapeString(s)
	return strings.Join(strings.Fields(s), " ")
}

// normalizeURL completes protocol-relative and root-relative page URLs.
func normalizeURL(s string) string {
	s = strings.TrimSpace(html.UnescapeString(s))
	switch {
	case strings.HasPrefix(s, "//"):
		return "https:" + s
	case strings.HasPrefix(s, "/"):
		return "https://m.sfacg.com" + s
	default:
		return s
	}
}

func parseNum(s string) (int64, error) {
	return strconv.ParseInt(strings.ReplaceAll(strings.TrimSpace(s), ",", ""), 10, 64)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// FetchDetail fetches the mobile detail page for nid through the limiter and
// parses it. The limiter slot is foreground when user-triggered. It returns
// the fetch-start unix second for the observation write-back (docs/05 §5.1:
// observed_at is injected by the engine, not the parser).
func FetchDetail(ctx context.Context, client *http.Client, l *Limiter, nid int64, foreground bool) (DetailState, *Detail, int64, error) {
	fetchStart := time.Now().Unix()
	var (
		state DetailState
		d     *Detail
		perr  error
	)
	err := l.Submit(ctx, foreground, func() {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			fmt.Sprintf("https://m.sfacg.com/b/%d/", nid), nil)
		if err != nil {
			perr = err
			return
		}
		req.Header.Set("User-Agent",
			"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Mobile Safari/537.36")
		resp, err := client.Do(req)
		if err != nil {
			perr = err
			return
		}
		defer resp.Body.Close()
		buf := make([]byte, 0, 32*1024)
		tmp := make([]byte, 8192)
		for {
			n, rerr := resp.Body.Read(tmp)
			buf = append(buf, tmp[:n]...)
			if rerr != nil || len(buf) > 256*1024 {
				break
			}
		}
		state, d = ParseDetail(string(buf))
	})
	if err != nil {
		return 0, nil, 0, err
	}
	if perr != nil {
		return 0, nil, 0, perr
	}
	return state, d, fetchStart, nil
}

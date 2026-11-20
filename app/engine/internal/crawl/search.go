package crawl

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"
)

// SearchHit is one result row of the official HTML search
// (docs/sfacg-endpoints.md §2.1): a 30-row hard cap, no paging —
// 「共搜索到 N 个结果」 N is the TRUNCATED number, never the true total.
type SearchHit struct {
	NID       int64  `json:"nid"`
	Title     string `json:"title"`
	Author    string `json:"author,omitempty"`
	UpdatedAt string `json:"updated_at,omitempty"`
	CoverURL  string `json:"cover_url,omitempty"`
	Summary   string `json:"summary,omitempty"`
}

// SearchResult is the parsed official search page. Throttled is the
// silent rate-limit verdict: the server answers HTTP 200 with a
// structurally normal page whose search box label flips to 「请输入关键字」
// — status codes carry zero information, the fingerprint string is the
// verdict (probe-verified; a normal page never contains it, §2.1/§8).
type SearchResult struct {
	Items     []SearchHit `json:"items"`
	Declared  int         `json:"declared"`
	Throttled bool        `json:"throttled"`
}

var (
	reSearchBlock    = regexp.MustCompile(`(?s)<ul style="width:100%">(.*?)</ul>`)
	reSearchNID      = regexp.MustCompile(`book\.sfacg\.com/Novel/(\d+)`)
	reSearchTitle    = regexp.MustCompile(`(?s)class="orange_link2">(.*?)</a>`)
	reSearchCover    = regexp.MustCompile(`<img src="([^"]+)"`)
	reSearchInfo     = regexp.MustCompile(`(?s)综合信息：\s*(.*?)<br\s*/?>`)
	reSearchDeclared = regexp.MustCompile(`共搜索到\s*(\d+)\s*个结果`)
	// The bare text node after the 综合信息 line, up to </li>: the intro
	// snippet (20–200 chars on 27/29 probed rows) — the only search
	// interface that carries one.
	reSearchSummary = regexp.MustCompile(`(?s)综合信息：[^<]*<br\s*/?>\s*(.*?)</li>`)
)

const searchThrottleFingerprint = "请输入关键字"

// ErrSearchTooSoon is returned by FetchSearch when the 6-second
// self-cooldown between official searches has not elapsed.
var ErrSearchTooSoon = fmt.Errorf("search too soon: keep %s between official searches", searchMinGap)

// searchMinGap is the probe's hard constraint: requests closer than 6
// seconds raise the throttle probability (docs/sfacg-endpoints.md §2.1,
// probe GAP=6.0). In-process only — one user's taps rarely hit it, but
// a rapid retry loop must not burn the throttle budget.
const searchMinGap = 6 * time.Second

var (
	searchMu     sync.Mutex
	searchLastAt time.Time
)

func checkSearchGap() error {
	searchMu.Lock()
	defer searchMu.Unlock()
	if !searchLastAt.IsZero() && time.Since(searchLastAt) < searchMinGap {
		return ErrSearchTooSoon
	}
	searchLastAt = time.Now()
	return nil
}

// ParseSearch is a pure function: HTML in, verdict out. The throttle
// check runs first — a throttled page is structurally a normal search
// page, so structure alone cannot distinguish it.
func ParseSearch(html string) *SearchResult {
	res := &SearchResult{Items: []SearchHit{}}
	if strings.Contains(html, searchThrottleFingerprint) {
		res.Throttled = true
		return res
	}
	if m := reSearchDeclared.FindStringSubmatch(html); m != nil {
		if n, err := parseNum(m[1]); err == nil {
			res.Declared = int(n)
		}
	}
	for _, block := range reSearchBlock.FindAllStringSubmatch(html, -1) {
		seg := block[1]
		nid := reSearchNID.FindStringSubmatch(seg)
		if nid == nil {
			continue
		}
		hit := SearchHit{}
		if n, err := parseNum(nid[1]); err == nil {
			hit.NID = n
		}
		if t := reSearchTitle.FindStringSubmatch(seg); t != nil {
			hit.Title = cleanText(t[1])
		}
		if c := reSearchCover.FindStringSubmatch(seg); c != nil {
			hit.CoverURL = normalizeURL(c[1])
		}
		if info := reSearchInfo.FindStringSubmatch(seg); info != nil {
			infoTxt := strings.Join(strings.Fields(info[1]), " ")
			author, updated, _ := strings.Cut(infoTxt, "/")
			hit.Author = strings.TrimSpace(author)
			hit.UpdatedAt = strings.TrimSpace(updated)
		}
		if sm := reSearchSummary.FindStringSubmatch(seg); sm != nil {
			hit.Summary = cleanText(sm[1])
		}
		res.Items = append(res.Items, hit)
	}
	return res
}

// FetchSearch fetches one official HTML search page through the limiter
// (plus the 6-second self-cooldown above; foreground when
// user-triggered). The search endpoint is the PC site, so the UA is
// desktop. Returns the parsed verdict; the throttled case is a normal
// result, not an error.
func FetchSearch(ctx context.Context, client *http.Client, l *Limiter, keyword string, foreground bool) (*SearchResult, error) {
	if err := checkSearchGap(); err != nil {
		return nil, err
	}
	var (
		res  *SearchResult
		perr error
	)
	err := l.Submit(ctx, foreground, func() {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			"https://s.sfacg.com/?Key="+url.QueryEscape(keyword)+"&SS=0&S=1", nil)
		if err != nil {
			perr = err
			return
		}
		req.Header.Set("User-Agent",
			"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
		resp, err := client.Do(req)
		if err != nil {
			perr = err
			return
		}
		defer resp.Body.Close()
		buf := make([]byte, 0, 64*1024)
		tmp := make([]byte, 8192)
		for {
			n, rerr := resp.Body.Read(tmp)
			buf = append(buf, tmp[:n]...)
			if rerr != nil || len(buf) > 256*1024 {
				break
			}
		}
		res = ParseSearch(string(buf))
	})
	if err != nil {
		return nil, err
	}
	if perr != nil {
		return nil, perr
	}
	return res, nil
}

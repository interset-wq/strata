package crawl

import (
	"context"
	"fmt"
	"net/http"
	"regexp"
	"time"
)

// AuthorBoxIntro is the PC detail page's author box
// (docs/author-profile-on-demand §2.2) — the only web source of the
// author intro. The mobile page has no intro at all, so this is a
// second, separate request, issued only when the caller wants an intro.
type AuthorBoxIntro struct {
	Intro  string `json:"intro,omitempty"`
	Avatar string `json:"avatar,omitempty"`
	Name   string `json:"name,omitempty"`
}

var (
	rePCErr     = regexp.MustCompile(`小说不存在`)
	rePCDesc    = regexp.MustCompile(`(?s)class="author-desc"[^>]*>(.*?)</div>`)
	rePCMaskImg = regexp.MustCompile(`(?s)class="author-mask"[^>]*>.*?<img[^>]+src=['"]([^'"]+)['"]`)
	rePCName    = regexp.MustCompile(`(?s)class="autor-name"[^>]*>(.*?)<`)
)

// ParseAuthorBox is a pure function: PC HTML in, author box out. A dead
// page (「小说不存在」— HTTP status carries zero information, §2.2)
// yields nil. An alive page without the author-box structure yields an
// empty box: intro "" is a normal value (some authors wrote none),
// never fabricate text.
func ParseAuthorBox(html string) *AuthorBoxIntro {
	if rePCErr.MatchString(html) {
		return nil
	}
	box := AuthorBoxIntro{}
	if d := rePCDesc.FindStringSubmatch(html); d != nil {
		box.Intro = cleanText(d[1])
	}
	if a := rePCMaskImg.FindStringSubmatch(html); a != nil {
		box.Avatar = normalizeURL(a[1])
	}
	if n := rePCName.FindStringSubmatch(html); n != nil {
		box.Name = cleanText(n[1])
	}
	return &box
}

// FetchAuthorBox fetches the PC detail page for nid through the limiter
// and parses the author box. The limiter slot is foreground when
// user-triggered (same convention as FetchDetail). Returns nil on a dead
// page, a non-nil empty box on an alive page without an author box.
func FetchAuthorBox(ctx context.Context, client *http.Client, l *Limiter, nid int64, foreground bool) (*AuthorBoxIntro, int64, error) {
	fetchStart := time.Now().Unix()
	var (
		box  *AuthorBoxIntro
		perr error
	)
	err := l.Submit(ctx, foreground, func() {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet,
			fmt.Sprintf("https://book.sfacg.com/Novel/%d/", nid), nil)
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
		buf := make([]byte, 0, 32*1024)
		tmp := make([]byte, 8192)
		for {
			n, rerr := resp.Body.Read(tmp)
			buf = append(buf, tmp[:n]...)
			if rerr != nil || len(buf) > 256*1024 {
				break
			}
		}
		box = ParseAuthorBox(string(buf))
	})
	if err != nil {
		return nil, 0, err
	}
	if perr != nil {
		return nil, 0, perr
	}
	return box, fetchStart, nil
}

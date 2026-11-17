package crawl

import (
	"context"
	"fmt"
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
type Detail struct {
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
)

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

	if m := reWords.FindStringSubmatch(html); m != nil {
		if w, err := parseNum(m[1]); err == nil && w > 0 {
			d.Words = w
		}
	}
	if m := reStatus.FindStringSubmatch(html); m != nil {
		d.Status = m[1]
	}
	// Two-digit year: always a 20xx date, stored as sortable TEXT (§4.2).
	if m := reUpdated.FindStringSubmatch(html); m != nil {
		d.UpdatedAt = "20" + m[1] + "-" + m[2] + "-" + m[3] + " " + m[4] + ":" + m[5] + ":00"
	}

	// Illegal numbers that survived the sign check: all-zero anomalies.
	if favs == 0 && praises == 0 {
		return DetailZombie, nil
	}
	return DetailAlive, &d
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

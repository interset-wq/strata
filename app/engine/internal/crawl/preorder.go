package crawl

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// PreOrder upstream: the ajax endpoint behind the weekly pre-order H5 page
// (docs/sfacg-endpoints.md §7.5). The date is the issue key and must be a
// Saturday; cid=0 is light novels — cid=1 (dialogue) has been empty in every
// sampled issue, so the engine does not expose the parameter.
const (
	preorderBase    = "https://pages.sfacg.com/ajax/act/PreOrder.ashx"
	preorderTimeout = 10 * time.Second
)

// PreOrderItem is one editorially picked book of an issue. 8 upstream
// fields; hasOrder is the logged-in user's reservation state (always false
// anonymously) and is intentionally not carried.
type PreOrderItem struct {
	NovelID    int64    `json:"novelId"`
	NovelName  string   `json:"novelName"`
	CategoryID int64    `json:"categoryId"`
	Intro      string   `json:"intro"`
	Cover      string   `json:"cover"`
	IsMainPush bool     `json:"isMainPush"`
	Tags       []string `json:"tags"`
}

type preOrderResp struct {
	Status int            `json:"status"`
	Data   []PreOrderItem `json:"data"`
}

// FetchPreOrder requests one issue (YYYYMMDD, Saturday) through the shared
// limiter. Empty data is a valid answer (most pre-2020 weeks are empty),
// not an error.
func FetchPreOrder(ctx context.Context, client *http.Client, l *Limiter,
	date string, foreground bool) ([]PreOrderItem, error) {
	ctx, cancel := context.WithTimeout(ctx, preorderTimeout)
	defer cancel()

	var (
		resp preOrderResp
		ferr error
	)
	err := l.Submit(ctx, foreground, func() {
		ferr = func() error {
			req, err := http.NewRequestWithContext(ctx, http.MethodGet,
				fmt.Sprintf("%s?op=getPreOrderNovels&date=%s&cid=0", preorderBase, date), nil)
			if err != nil {
				return err
			}
			req.Header.Set("User-Agent", ranksDesktopUA)
			req.Header.Set("Referer", "https://pages.sfacg.com/")
			hresp, err := client.Do(req)
			if err != nil {
				return err
			}
			defer hresp.Body.Close()
			if hresp.StatusCode != http.StatusOK {
				return fmt.Errorf("preorder: HTTP %d", hresp.StatusCode)
			}
			return json.NewDecoder(hresp.Body).Decode(&resp)
		}()
	})
	if err != nil {
		return nil, err
	}
	if ferr != nil {
		return nil, ferr
	}
	if resp.Status != 200 {
		return nil, fmt.Errorf("preorder: upstream status %d", resp.Status)
	}
	return resp.Data, nil
}

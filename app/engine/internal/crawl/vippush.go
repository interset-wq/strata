package crawl

import (
	"context"
	"fmt"
	"html"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// VIP 上架专题（vipPush）上游：每周六的 H5 直出页，书籍列表内联在 HTML
// 里（docs/sfacg-endpoints.md §7.6），没有 JSON ajax 端点。与预约列表
// （PreOrder.ashx）是同一期次的两条不同数据线：预约 = 编辑精选（含 intro /
// isMainPush），专题 = 当周上架全书（24 本，仅标题/封面/分类/标签）。
//
// 页面第二个 tab（对话小说）直出为空，故只解析轻小说 tab 下的 .data-list。
const (
	vippushBase    = "https://pages.sfacg.com/h5/general/vipPush%s.html?type=android"
	vippushTimeout = 10 * time.Second
)

// 结构稳定：每个书块以 <div class="item" data-nid="..." data-cid="..."> 开始，
// 到下一个同形态节点（或页面尾）为止；tab 头的 <div class="item">无
// data-nid，不会误命中。块内 img / .novel-name / .tag 各取一次。
var (
	reVipPushHead = regexp.MustCompile(`<div\s+class="item"\s+data-nid="(\d+)"[^>]*>`)
	reVPNCover    = regexp.MustCompile(`(?s)<img[^>]+src=['"]([^'"]+)['"]`)
	reVPName      = regexp.MustCompile(`(?s)class="novel-name"[^>]*>(.*?)</div>`)
	reVPTag       = regexp.MustCompile(`(?s)class="tag"[^>]*>(.*?)</div>`)
	reVPSpan      = regexp.MustCompile(`(?s)<span[^>]*>(.*?)</span>`)
)

// VipPushItem is one book on the weekly VIP-release feature page. Upstream
// carries no author/words/status — those come from seed via the API join.
type VipPushItem struct {
	Nid   int64    `json:"nid"`
	Title string   `json:"title"`
	Cover string   `json:"cover"`
	Genre string   `json:"genre"`
	Tags  []string `json:"tags"`
}

// FetchVipPush requests one Saturday issue (YYYYMMDD) through the shared
// limiter. An empty list is valid (a week with no feature page), not an error;
// the caller caches empty results too.
func FetchVipPush(ctx context.Context, client *http.Client, l *Limiter,
	date string, foreground bool) ([]VipPushItem, error) {
	ctx, cancel := context.WithTimeout(ctx, vippushTimeout)
	defer cancel()

	var (
		items []VipPushItem
		ferr  error
	)
	err := l.Submit(ctx, foreground, func() {
		ferr = func() error {
			req, err := http.NewRequestWithContext(ctx, http.MethodGet,
				fmt.Sprintf(vippushBase, date), nil)
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
				return fmt.Errorf("vippush: HTTP %d", hresp.StatusCode)
			}
			// 页面约 28 KB；2 MB 上限防御异常超大响应。
			body, err := io.ReadAll(io.LimitReader(hresp.Body, 2<<20))
			if err != nil {
				return err
			}
			items = ParseVipPush(string(body))
			return nil
		}()
	})
	if err != nil {
		return nil, err
	}
	if ferr != nil {
		return nil, ferr
	}
	return items, nil
}

// ParseVipPush extracts the light-novel book list from a vipPush H5 page.
// Exported for fixture tests; the input is the raw HTML, not a JSON envelope.
func ParseVipPush(page string) []VipPushItem {
	// Go regexp 无 lookahead：先收集每个书块起点，块内容 = 本起点到下一
	// 起点（或页尾），保证最后一本也被解析。
	heads := reVipPushHead.FindAllStringSubmatchIndex(page, -1)
	out := make([]VipPushItem, 0, len(heads))
	for i, loc := range heads {
		if len(loc) < 4 {
			continue
		}
		nid, err := strconv.ParseInt(page[loc[2]:loc[3]], 10, 64)
		if err != nil || nid <= 0 {
			continue
		}
		start := loc[1]
		end := len(page)
		if i+1 < len(heads) {
			end = heads[i+1][0]
		}
		it := VipPushItem{Nid: nid, Tags: []string{}}
		block := page[start:end]
		if c := reVPNCover.FindStringSubmatch(block); len(c) > 1 {
			it.Cover = normalizeVipPushCover(c[1])
		}
		if n := reVPName.FindStringSubmatch(block); len(n) > 1 {
			it.Title = cleanVipPushText(n[1])
		}
		if t := reVPTag.FindStringSubmatch(block); len(t) > 1 {
			tagBlock := t[1]
			if g := reVPSpan.FindStringSubmatch(tagBlock); len(g) > 1 {
				it.Genre = cleanVipPushText(g[1])
				tagBlock = reVPSpan.ReplaceAllString(tagBlock, "")
			}
			for _, tag := range strings.Split(tagBlock, "/") {
				if tag = cleanVipPushText(tag); tag != "" {
					it.Tags = append(it.Tags, tag)
				}
			}
		}
		out = append(out, it)
	}
	return out
}

// 上游封面是协议相对 URL（//rs.sfacg.com/...）；与 preorder 保持一致补齐
// https，供 Flutter Image.network 直接使用。
func normalizeVipPushCover(raw string) string {
	raw = strings.TrimSpace(raw)
	if strings.HasPrefix(raw, "//") {
		return "https:" + raw
	}
	return raw
}

func cleanVipPushText(raw string) string {
	raw = strings.ReplaceAll(raw, "\n", " ")
	raw = strings.ReplaceAll(raw, "\r", " ")
	raw = strings.ReplaceAll(raw, "\t", " ")
	raw = strings.Join(strings.Fields(html.UnescapeString(raw)), " ")
	return strings.TrimSpace(raw)
}

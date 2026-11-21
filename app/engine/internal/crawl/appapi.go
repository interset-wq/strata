package crawl

import (
	"context"
	"crypto/md5"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// App API（api.sfacg.com）是可选增强通路：契约见 docs/05 §3.5 —— 默认关闭，
// 失败一律静默降级回移动版 HTML 基线；认证为 App 内置公共常量 + 每请求自签。
// 事实档案：analysis/references/sfacg-app-api.md。
const (
	appAPIRoot    = "https://api.sfacg.com"
	appAPIBase    = "https://api.sfacg.com/novels"
	appAPISalt    = "FN_Q29XHVmfV3mYX"
	appAPIBasic   = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="
	appAPIAccept  = "application/vnd.sfacg.api+json;version=1"
	appAPIUA      = "boluobao/5.0.36(android;32)/H5/%s/H5"
	appAPITimeout = 18 * time.Second
)

// appAPIHeaders builds the per-request self-signed header set. nonce and
// device token are client-generated UUIDv4 (uppercase); the server only
// verifies the md5 signature.
func appAPIHeaders() (http.Header, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return nil, err
	}
	// UUIDv4: set version 4 and variant bits.
	raw[6] = (raw[6] & 0x0f) | 0x40
	raw[8] = (raw[8] & 0x3f) | 0x80
	hexed := hex.EncodeToString(raw[:])
	nonce := strings.ToUpper(
		hexed[0:8] + "-" + hexed[8:12] + "-" + hexed[12:16] + "-" +
			hexed[16:20] + "-" + hexed[20:32])
	deviceToken := nonce
	ts := time.Now().UnixMilli()
	sign := strings.ToUpper(fmt.Sprintf("%x", md5.Sum([]byte(nonce+fmt.Sprint(ts)+deviceToken+appAPISalt))))

	h := http.Header{}
	h.Set("accept", appAPIAccept)
	h.Set("authorization", appAPIBasic)
	h.Set("user-agent", fmt.Sprintf(appAPIUA, deviceToken))
	h.Set("sfsecurity", fmt.Sprintf(
		"nonce=%s&timestamp=%d&devicetoken=%s&sign=%s",
		nonce, ts, deviceToken, sign))
	return h, nil
}

// AppNovel is the subset of GET /novels/{id}'s data object the app uses.
// Field semantics: sfacg-app-api.md §3.1.
type AppNovel struct {
	NovelID        int64   `json:"novelId"`
	NovelName      string  `json:"novelName"`
	AuthorID       int64   `json:"authorId"`
	AuthorName     string  `json:"authorName"`
	AddTime        string  `json:"addTime"`
	LastUpdateTime string  `json:"lastUpdateTime"`
	MarkCount      int64   `json:"markCount"`
	ViewTimes      int64   `json:"viewTimes"`
	CharCount      int64   `json:"charCount"`
	Point          float64 `json:"point"`
	IsFinish       bool    `json:"isFinish"`
	SignStatus     string  `json:"signStatus"`
	TypeID         int64   `json:"typeId"`
	CategoryID     int64   `json:"categoryId"`
	IsSensitive    bool    `json:"isSensitive"`
	AllowDown      bool    `json:"allowDown"`
	NovelCover     string  `json:"novelCover"`
	BgBanner       string  `json:"bgBanner"`
	NID            int64   `json:"nid"`
	TID            int64   `json:"tid"`
}

// AppGenre maps the App API typeId to the nine-way genre vocabulary.
func AppGenre(typeID int64) string {
	switch typeID {
	case 21:
		return "魔幻"
	case 22:
		return "玄幻"
	case 23:
		return "古风"
	case 24:
		return "科幻"
	case 25:
		return "校园"
	case 26:
		return "都市"
	case 27:
		return "游戏"
	case 28:
		return "同人"
	case 29:
		return "悬疑"
	default:
		return ""
	}
}

// FetchAppNovel requests GET /novels/{nid} through the shared limiter.
// The App API has its own verdict: HTTP 200 with status.httpCode==200 and a
// positive novelId means usable metadata; anything else (sign error 417,
// unknown nid, structural change, transport failure) is an error the caller
// must treat as "degrade silently to the HTML baseline" — never as dead.
func FetchAppNovel(ctx context.Context, client *http.Client, l *Limiter,
	nid int64, foreground bool) (*AppNovel, error) {
	ctx, cancel := context.WithTimeout(ctx, appAPITimeout)
	defer cancel()

	var (
		meta *AppNovel
		ferr error
	)
	err := l.Submit(ctx, foreground, func() {
		ferr = func() error {
			h, err := appAPIHeaders()
			if err != nil {
				return err
			}
			req, err := http.NewRequestWithContext(ctx, http.MethodGet,
				fmt.Sprintf("%s/%d", appAPIBase, nid), nil)
			if err != nil {
				return err
			}
			req.Header = h
			resp, err := client.Do(req)
			if err != nil {
				return err
			}
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusOK {
				return fmt.Errorf("app api http %d", resp.StatusCode)
			}
			var body struct {
				Status struct {
					HTTPCode int `json:"httpCode"`
				} `json:"status"`
				Data AppNovel `json:"data"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
				return err
			}
			// The App API returns 417 (sign) or other codes inside a 200
			// body — same trap as the HTML endpoints returning 200 for
			// invalid nids. Anything but 200 is unusable.
			if body.Status.HTTPCode != 200 {
				return fmt.Errorf("app api status httpCode %d", body.Status.HTTPCode)
			}
			if body.Data.NovelID <= 0 {
				return fmt.Errorf("app api no novel data")
			}
			meta = &body.Data
			return nil
		}()
	})
	if err != nil {
		return nil, err
	}
	return meta, ferr
}

// AdpWorks is the data object of GET /adpworks/novelId/{id} (sfacg-app-api.md
// §3.4): the official adaptation-works ids for a novel. 0 = confirmed none;
// a fetch failure must leave book_meta NULL (未抓/失败), so the caller only
// persists on success (docs/05 §6).
type AdpWorks struct {
	NovelID int64 `json:"novelId"`
	AlbumID int64 `json:"albumId"`
	ComicID int64 `json:"comicId"`
}

// FetchAdpWorks requests GET /adpworks/novelId/{nid} through the shared
// limiter. The endpoint sits at the API root, not under /novels
// (appAPIBase). 0 ids are a valid answer; anything else is an error the
// caller treats as "leave the columns NULL".
func FetchAdpWorks(ctx context.Context, client *http.Client, l *Limiter,
	nid int64, foreground bool) (*AdpWorks, error) {
	ctx, cancel := context.WithTimeout(ctx, appAPITimeout)
	defer cancel()

	var (
		meta *AdpWorks
		ferr error
	)
	err := l.Submit(ctx, foreground, func() {
		ferr = func() error {
			h, err := appAPIHeaders()
			if err != nil {
				return err
			}
			req, err := http.NewRequestWithContext(ctx, http.MethodGet,
				appAPIRoot+"/adpworks/novelId/"+fmt.Sprint(nid), nil)
			if err != nil {
				return err
			}
			req.Header = h
			resp, err := client.Do(req)
			if err != nil {
				return err
			}
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusOK {
				return fmt.Errorf("app api http %d", resp.StatusCode)
			}
			var body struct {
				Status struct {
					HTTPCode int `json:"httpCode"`
				} `json:"status"`
				Data AdpWorks `json:"data"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
				return err
			}
			// Same 200-with-error-code trap as FetchAppNovel.
			if body.Status.HTTPCode != 200 {
				return fmt.Errorf("app api status httpCode %d", body.Status.HTTPCode)
			}
			meta = &body.Data
			return nil
		}()
	})
	if err != nil {
		return nil, err
	}
	return meta, ferr
}

// Comic is the subset of GET /comics/{id} the app keeps: the folderName is
// the web entry path, archived so the link can be enabled without a re-fetch
// if the official comic site ever recovers (docs/05 §6.1).
type Comic struct {
	ComicName  string `json:"comicName"`
	FolderName string `json:"folderName"`
	ViewTimes  int64  `json:"viewTimes"`
	IsFinished bool   `json:"isFinished"`
}

// FetchComic requests GET /comics/{comicID} for the folderName archive.
func FetchComic(ctx context.Context, client *http.Client, l *Limiter,
	comicID int64, foreground bool) (*Comic, error) {
	ctx, cancel := context.WithTimeout(ctx, appAPITimeout)
	defer cancel()

	var (
		meta *Comic
		ferr error
	)
	err := l.Submit(ctx, foreground, func() {
		ferr = func() error {
			h, err := appAPIHeaders()
			if err != nil {
				return err
			}
			req, err := http.NewRequestWithContext(ctx, http.MethodGet,
				appAPIRoot+"/comics/"+fmt.Sprint(comicID), nil)
			if err != nil {
				return err
			}
			req.Header = h
			resp, err := client.Do(req)
			if err != nil {
				return err
			}
			defer resp.Body.Close()
			if resp.StatusCode != http.StatusOK {
				return fmt.Errorf("app api http %d", resp.StatusCode)
			}
			var body struct {
				Status struct {
					HTTPCode int `json:"httpCode"`
				} `json:"status"`
				Data Comic `json:"data"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
				return err
			}
			if body.Status.HTTPCode != 200 {
				return fmt.Errorf("app api status httpCode %d", body.Status.HTTPCode)
			}
			meta = &body.Data
			return nil
		}()
	})
	if err != nil {
		return nil, err
	}
	return meta, ferr
}

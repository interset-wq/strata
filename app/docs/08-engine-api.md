# 08 · 引擎 HTTP 契约（Go ↔ Dart）

> v1.0 · 2026-11-17
> 本文档是 Go 引擎与 Flutter（dart:ffi 客户端）之间的**绑定契约**。双方都以本文为准；
> 改动任何端点必须先改本文。现状实现见 `app/engine/internal/api/api.go`。

## 总则

- 服务只绑定 `127.0.0.1`，端口由内核动态分配（`:0`）。启动方（CLI 或 FFI）负责把
  实际地址交给 UI。
- 所有响应为 UTF-8 JSON；HTTP 状态码语义常规。
- 错误响应统一为：

  ```json
  { "error": { "code": "invalid_argument", "message": "..." } }
  ``

  | code | HTTP | 含义 |
  | --- | --- | --- |
  | `invalid_argument` | 400 | 参数缺失/非法 |
  | `not_found` | 404 | nid 不在种子里 |
  | `internal` | 500 | 存储层/内部错误 |

- **分页**：统一用 `limit` 查询参数，1..200，缺省 50；越界返回 `invalid_argument`。
  v1 不做游标翻页（榜单一次最多 200 条已够）。
- 契约基线常量：`content_end`（种子数据截止日）、`gen_min`/`gen_max`（出生年份区间，
  当前 2007..2025）、`book_count=30878`、`licensed_count=47`。以 `/strata/healthz`
  实际返回为准，不要在 Dart 侧硬编码。

## 现有端点（已实现）

### GET /strata/healthz

200：

```json
{
  "status": "ok",
  "schema_version": 1,
  "seed_version": "…",
  "book_count": 30878,
  "licensed_count": 47,
  "content_end": "2026-05-03",
  "gen_min": 2007,
  "gen_max": 2025
}
```

UI 启动轮询即打这个端点（200ms 间隔、15s 超时），`status=="ok"` 即认为引擎就绪。

### GET /strata/meta

200：`{ "manifest": <Manifest>, "seed_meta": {key: value, …} }`。
`Manifest` 字段与 `app/assets/manifest.json` 一致（`schema_version`、`seed_version`、
`content_end`、`built_at`、`book_count`、`licensed_count`、`tag_count`、`tag_rows`、
`gen_min`、`gen_max`、`counts`、`files`）。

### GET /strata/books/:nid

- 400 `invalid_argument`：nid 不是正整数。
- 404 `not_found`：nid 不在种子（含 47 本授权书，均可见）。

200：

```json
{
  "source": "seed" | "local",
  "data_end": "2026-05-03",
  "book": { …24 列 Book… },
  "tags": ["…"],
  "local": <Observation|null>,
  "meta": <BookMeta|null>,
  "effective": { "title": …, "author": …, "genre": …, "price_type": …,
                 "clicks": …, "favs": …, "praises": …, "words": …,
                 "status": …, "cover_url": …, "summary": …,
                 "updated_at": …, "add_time": …, "point": …,
                 "author_id": …, "type_id": …, "category_id": …,
                 "is_sensitive": …, "allow_down": … },
  "cover": "https://…cover…" | null
}
```

`effective` = 种子值依次被 `meta`（最近一次抓取的全部书目元数据）和
`local`（最新观测）覆盖后的展示值；`local != null || meta != null` 即
`source == "local"`。`cover` 优先取本地封面直链，种子 `cover_url` 大量为空
或为相对路径，客户端须兼容相对路径并使用官方默认封面兜底。
`POST /strata/books/:nid/refresh` 的 `detail` 同样返回本次请求解析到的全部字段：
HTML 含书名/作者/分类/签约/封面/简介/收藏/赞/字数/状态/更新时间，外加
`tickets`（当月月票，`GetTicketNum.ashx` 追加请求，失败为 null）；App API 含
`markCount/viewTimes/charCount/point/addTime/signStatus/typeId/categoryId/...`。

详情响应另含衍生作品入口（05 §6、§6.1），字段只在已抓到时出现：

```json
{ "comic_id": 2937, "album_id": 97, "comic_folder": "XJYQS",
  "comic_url": "http://manhua.sfacg.com/mh/XJYQS/" }
```

`comic_url` 由本地按模板拼装，零请求；`album_id>0` 时**不给链接**（无官方 Web
模板），UI 只标「有有声改编」。`comic_id`/`album_id` 为 `null`（未抓/失败）与
`0`（确认无改编）都表示不显示入口。

### GET /strata/rankings/favs?year=&genre=&limit=

- `year` 必填，须在 `gen_min..gen_max` 内，否则 400。
- `genre` 可选，枚举：魔幻/玄幻/古风/科幻/校园/都市/游戏/同人/悬疑。

200：

```json
{
  "meta": { "kind": "favs", "pool": "seed", "ordering": "fav_pctl",
            "content_end": "…", "year": 2019, "genre": null|"魔幻",
            "limit": 50, "licensed_excluded": true },
  "items": [ { "nid": 123, "title": "…", "author": "…", "genre": "…",
               "est_year": 2019, "favs": 12345, "fav_pctl": 99.7 } ]
}
```

分位只按种子池（`is_licensed=0`）计算；`licensed_excluded` 恒为 true，榜单永不出现授权书。

**二级页过滤参数（宫格入口，已实现）**：`status=已完结|连载中`（精确匹配，非法值 400）、
`contest=1`（全部参赛作品）或 `contest=具体届次名`（如 `2025春季征文`，精确匹配）。
与 `genre` 可组合，均在分位榜口径内过滤。`contest` 取值在端上从 `contest=1` 结果
聚合（items 的 `contest` 字段），不单独提供枚举端点。

### GET /strata/rankings/board?kind=&limit=&offset=（**已实现**）

Classic 全库榜（docs/12 展示列）：平台累计值排序，不涉及分位。`kind` 枚举：
`recommend`(praises) / `popular`(clicks) / `favs` / `new`(est_date) / `finish`(已完结按 favs) /
`words`。`offset` 分页（默认 0）。items 为 RankItem（含 `status`/`words`/`clicks`/`cover_url`）。

### GET /strata/discover?cursor=&limit=（**已实现**）

Classic 发现流（docs/12 §5）：候选池 = `is_licensed=0` 且**有封面**（封面硬门槛，
12,107 本），按平台 `clicks` 降序，**keyset 游标分页**（cursor = 上一批末条
`clicks:nid`，缺省从顶部开始），每批默认 20，stateless。响应含 `next_cursor`
（批末返回，为空表示到底）。

### GET/POST/DELETE /strata/watchlist（**已实现**）

作者工作台追踪列表（Phase 5，docs/12 §3.4 反馈回路隔离：观测数据只存 user.db）。
GET 返回 `{items:[{nid,title,author,genre,cover_url,added_at,role,note}]}`（JOIN seed.books，
按加入时间倒序）；POST/DELETE `/watchlist/:nid` 幂等增删。观测时序见
`GET /books/:nid/observations`（按 observed_at 倒序，来源 source 标注），
保留期由 PruneObservations 管理。

**订阅式后台抓取（Phase 5，已实现）**：引擎启动时挂后台 worker，每分钟 tick，
每次最多取 5 本到期书（`poll_enabled=1` 且 `now - last_poll_at >= poll_interval`，
默认 86400s），经**后台 lane** 限速槽逐本串行抓取（前台请求永远优先）。
App API 成功→精确元数据写观测 + cover 缓存；否则 HTML 兜底（三态判据，
仅 alive 写观测）。无论成败均盖章 `last_poll_at`，坏书不会卡死队列；
失败不写观测行——数据页据实区分「暂无更新」与「数据缺口」。

### GET /strata/random?limit=（**已实现**）

首页"换一换"网格数据源：`is_licensed=0` 种子库内 `ORDER BY RANDOM()` 均匀抽样
（默认 limit，上限 max_limit），items 为 RankItem（含 status/words/clicks/favs/
cover_url）。诚实随机——官方"次元新书/专题推荐"的换一换同款模式。

### GET /strata/rankings/short?limit=

200：同上结构，`meta.kind="short"`、`ordering="favs"`、`short_max_words=50000`，
`items` 元素为 `{ nid, title, author, genre, est_year, favs, words }`（无分位字段）。

## 草案（Phase 3/4 实现，未落地前 UI 不得依赖）

### GET /strata/search?q=&limit=

L1 本地搜索（**已实现**）：种子库内 `title`/`author` LIKE 匹配（v1 无 FTS5）。
`q` 必填（非空），`limit` 同分页规则。

```json
{
  "meta": { "kind": "search", "pool": "seed", "q": "…", "limit": 50,
            "includes": "licensed", "content_end": "…" },
  "items": [ { "nid": 123, "title": "…", "author": "…", "genre": "…",
               "est_year": 2019, "favs": 12345 } ]
}
```

**授权书可被搜索**（`includes:"licensed"`），只是不参与榜单与统计。
按 `favs DESC` 排序。官方搜索 L2（30 条硬上限 + 静默限流识别）走 Phase 4，
端点预留 `POST /strata/search/remote`，响应附 `rate_limited: bool`。

### GET /strata/rankings/new?limit=

新书/新作榜（**已实现**）：近两代（`est_year >= gen_max-1`）按同代分位
`fav_pctl DESC` 排序（docs/03「按代查询再合并」的等价单查询），
`is_licensed=0`。

```json
{
  "meta": { "kind": "new", "pool": "seed", "ordering": "fav_pctl",
            "content_end": "…", "min_est_year": 2024, "limit": 50,
            "licensed_excluded": true },
  "items": [ <RankItem 同分位榜> ]
}
```

### POST /strata/books/:nid/refresh（**已实现**）

触发一次移动版详情抓取（`m.sfacg.com/b/{nid}/`，共用全局限速器，前台优先）。
v1 为**同步调用**（限速器已串行化，一次前台刷新只占一个槽位；不再用 202+轮询）。

三态判据按 05 号文档 §4.3：死亡（「出错啦」否定文案）/ 僵尸（目录容器无链接、
负数计数）/ 存活。仅存活态写入 `user.db.observations`（追加，`(nid, observed_at)`
去重），`seed.db` 永远只读。

**防抖**：同一 nid 60 秒内重复刷新直接返回上次结果，响应带 `"cached": true`，
不占限速槽位。**保留期**：观测保留 180 天（02 §3.1），引擎每次启动批量清理过期行。

```json
// 200，存活：
{ "state": "alive", "written": true,
  "detail": { "favs": 281988, "praises": 89171, "words": 5446886,
              "status": "已完结", "updated_at": "2024-03-25 20:57:00" } }
// 200，死亡/僵尸（不写观测，UI 按态标注）：
{ "state": "dead" | "zombie", "written": false }
```

**App API 增强通路（实验性，默认关闭）**：环境变量 `STRATA_APP_API=1` 启用。
启用后 refresh 先走 `api.sfacg.com/novels/{id}`（App 内置公共凭据自签，共用全局限速器，
前台优先）；成功时以 App 精确值写入观测（`clicks`= `viewTimes` 精确整数、
`favs`=`markCount`、`words`=`charCount`），响应为：

```json
{ "state": "alive", "written": true, "source": "app", "add_time": "2024-12-27T19:03:11",
  "detail": { "clicks": 33353509, "favs": 281034, "words": 2978118,
              "status": "已完结", "updated_at": "...", "cover": "https://...", "point": 7.2 } }
```

**降级**：App API 任何失败（签名 417/未知 nid/超时/结构变更）**静默回落**移动版
HTML 基线，响应不带 `source` 字段——调用方无需区分。**独立判据**：App API 只判
`status.httpCode==200 && data.novelId>0`（可用/不可用两态），死亡/僵尸三态判定仍
以 HTML 基线为准；`addTime` 不进定年模型，命中书为种子 `est_conf=exact` 档（05 §0）。

### GET /strata/books/:nid/observations（**已实现**）

```json
{ "items": [ { "observed_at": 1700000000, "clicks": null, "favs": 281988,
               "praises": 89171, "words": 5446886, "short_comments": null,
               "long_comments": null, "status": "已完结",
               "updated_at": "2024-03-25 20:57:00" } ] }
```

`observed_at` 倒序；`null` 表示该字段本次未抓（不是 0）。

### 书架 / watchlist（Phase 4/5）

| 端点 | 方法 | 语义 |
| --- | --- | --- |
| `/strata/shelf` | GET（**已实现**） | 书架列表，`items: [{nid, title, author, genre, added_at}]`，与种子 JOIN 取书名 |
| `/strata/shelf` | PUT（**已实现**） | 收藏，body `{ "nid": 123456 }` |
| `/strata/shelf/:nid` | DELETE（**已实现**） | 取消收藏 |
| `/strata/watchlist` | GET | 观测列表（含 `role: self\|peer`，Phase 5） |
| `/strata/watchlist` | POST/DELETE | 增删（`nid` + `role`，Phase 5） |

只写 `user.db`；与种子的关联**只用 `nid`**（rowid 每次种子发布都会重排）。

## FFI 启动契约（Phase 1）

`c-shared` 库导出三个符号：

- `char* strata_start(char* assets_dir, char* data_dir)` → JSON
  `{ok, addr?, seed_version?, book_count?, licensed_count?, content_end?, error?}`，
  `addr` 形如 `http://127.0.0.1:PORT`；
- `char* strata_stop()` → 同构 JSON；引擎未启动也返回 `{ok:true}`；
- `void strata_free(char*)` → 释放以上返回的 C 字符串（Dart 侧用完必调）。

启动失败（如种子缺失/校验不过）通过 `error` 字符串返回诊断信息，UI 据此显示
失败页，不做无限重试。

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
```

| code | HTTP | 含义 |
| --- | --- | --- |
| `invalid_argument` | 400 | 参数缺失/非法 |
| `not_found` | 404 | nid 不在种子里 |
| `internal` | 500 | 存储层/内部错误 |

- **分页**：统一用 `limit` 查询参数，1..200，缺省 50；越界返回 `invalid_argument`。
  v1 不做游标翻页（榜单一次最多 200 条已够）。
- 契约基线常量：`content_end`（种子数据截止日）、`gen_min`/`gen_max`（出生年份区间，
  当前 2007..2025）、`book_count=26339`、`licensed_count=47`。`form` 可选过滤：
  `invalid|short|medium|long|dialogue|ip_collab`，空值表示全部。以 `/strata/healthz`
  实际返回为准，不要在 Dart 侧硬编码。

## 现有端点（已实现）

### GET /strata/healthz

200：

```json
{
  "status": "ok",
  "schema_version": 3,
  "seed_version": "20260503.19",
  "book_count": 18477,
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

详情响应另含衍生作品标注（05 §6、§6.1），字段只在已抓到时出现：

```json
{ "comic_id": 2937, "album_id": 97, "comic_folder": "XJYQS" }
```

**不返回任何外链字段**：漫画站被官方定期关闭（当前详情页全 404），有声无 Web 模板，
拼出的 URL 即死链。UI 只按 `>0` 显示「有改编漫画 / 有有声」的静态标注；
`comic_folder` 仅为官方恢复后复用的留档。`null`（未抓/失败）与 `0`（确认无改编）
都不显示标注。

### GET /strata/banner?seed=&offset=&limit=&form=（**已实现**）

每日轮播：对 featured=1 全池（含 is_licensed，展示层）按日期种子（默认当天
`yyyymmdd`）做等概率确定性洗牌，取 `[offset, offset+limit)` 段——同日稳定、隔天
必变、分段不重叠。`form` 可选，洗牌前先收窄到单一形态。

### GET /strata/featured?limit=&form=（**已实现**）

编辑精选**固定序**：`ORDER BY favs DESC, nid ASC`，不做随机。池子不足 `limit`
时原样返回（池空返回空数组）。

**首页分形态轮播（docs/13 form）**：轮播随首页形态 tab 切换，行为按池大小定——

| form          | featured 池（seed 20260503.19） | 轮播行为                                                                                                           |
| ------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `long`      | 662（含授权 44）               | 日期种子洗牌（`/banner`）                                                                                        |
| `dialogue`  | 0                              | 空轮播（UI 渲染 `SizedBox.shrink`）                                                                              |
| `medium`    | 3（全授权）                    | 池不足 6 张，**固定收藏序**（`/featured`）                                                                 |
| `ip_collab` | 2                              | 同上，**固定**                                                                                               |
| `short`     | 0                              | **复用 IP 的固定轮播**（UI 侧把 `form=short` 映射为 `ip_collab`；IP 形态 featured 按字数指标本也是短篇） |

short→IP 的回退是 UI 的职责（`bannerProvider` 一处集中），API 保持纯过滤语义：
`/featured?form=short` 返回空池，不替客户端做回退。

### GET /strata/featured-all?limit=&offset=&order=（**已实现**）

「大图精选 · 全部」gallery 分页：默认 `order=desc`（收藏降序，编辑精选池热门
在前），`order=asc` 倒序。`nid` 作稳定 tie-breaker（注意 SQL 里必须写
`seed.books.nid`——covers 表同名列，裸 `nid` 会歧义 500）。`limit` 1..200、
`offset` ≥ 0，越界返回空数组而非 400，非法值 400。

### GET /strata/ip-groups?form=&status=（**已实现**）

contest 聚合端点：`form` 必填，池按征文（`contest`，非空）`GROUP BY` 聚合，
`count DESC, contest ASC` 稳定序。返回 `total`（池总量，含无 contest 的
书）+ `groups: [{contest, count}]`。

- IP tab 入口行（`form=ip_collab`）：端上取前 2 组作命名 IP 入口
  （崩坏3征文 → 崩坏3，去“征文”后缀），其余折成“其他”（total − 前 2 之和）。
- 短篇 tab 比赛榜入口（`form=short`）：`status` 可选（精确匹配，缺省
  不过滤；短篇池本身经种子完结条款已干净，UI 不传 status）。用途 =
  `/classic-list` 比赛榜页的**赛道 Drawer**（AppBar 汉堡/左缘右滑打开，
  本地搜索过滤 + 选中态，选中后标题追加赛道标签）。

### GET /strata/ip-books?form=&group=&limit=&offset=（**已实现**）

一个 IP 入口的列表：`group` 必填——征文名（精确匹配）或 `'other'`
（收藏数前 2 名征文之外的长尾，引擎内部算 top-2）。组内 `favs DESC,
nid ASC`，分页同 `/rankings/classic`。未知征文名返回空列表不报错。

### GET /strata/cover-carousel?form=&limit=&seed=（**已实现**）

对话/短篇 tab 合成轮播源：`form` 必填（同 `/banner` 的枚举校验），`seed` 同
`/banner` 语义（默认服务端日期，客户端可覆盖做确定性缓存/测试）。池 = 该
form **且有封面**（covers 观测或 seed `cover_url` 非空）的书按
`favs DESC, nid ASC` 取 Top-100（头部池，质量底），再按 `/banner` 同款
哈希（B=500001 半圈切点）每日抽取——每天换书、但始终在头部内。引擎只
保证 URL 存在，不保证 CDN 可达——封面 404 时 UI 回退纸底占位（docs/15
占位语义）。items 为 RankItem（`cover_url` 必填非空）。

### GET /strata/year-groups?form=（**已实现**）

短篇 tab 年份榜入口：`form` 必填（同 `/banner` 的枚举校验），池按
`est_year` 聚合（`est_year DESC`）。返回 `total`（池总量）+
`groups: [{year, count}]`。用途 = `/classic-list` 年份榜页的**年份
bottom sheet**（页内切换、无中间页，用户 2026-11-19 定）。

### GET /strata/genre-groups?form=（**已实现**）

短篇 tab 题材榜入口：`form` 必填（同上），池按 `genre`（非空）聚合
（`count DESC, genre ASC` 稳定序）。返回 `total`（池总量）+
`groups: [{genre, count}]`。用途 = `/classic-list` 题材榜页的
**FilterChip 行**（「全部题材」+ 各题材标签，单选切换）。

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

### GET /strata/rankings/board?kind=&form=&limit=&offset=（**已实现**）

Classic 全库榜（docs/12 展示列）：平台累计值排序，不涉及分位。`kind` 枚举：
`recommend`(praises) / `popular`(clicks) / `favs` / `new`(est_date) / `finish`(已完结按 favs) /
`words`。`offset` 分页（默认 0）。items 为 RankItem（含 `status`/`words`/`clicks`/`cover_url`）。

### GET /strata/rankings/classic?genre=&status=&contest=&form=&year=&order=&limit=&offset=（**已实现**）

Classic 主线分类/状态/大赛列表：默认按平台累计 `favs` 降序（`favs DESC, nid ASC`）。
`genre`/`status`/`contest` 与 `/rankings/favs` 同义；`contest=1` 表示全部大赛作品。
`year` 可选（正整数，按 `est_year` 精确过滤；非法值 400）。`order` 可选：
`favs`（默认）或 `pct`（同代收藏分位 `fav_pctl DESC`、NULL 末尾——
docs/form-definitions §6 优质短篇口径；非法值 400）。`items` 为 RankItem
（含 `form`），`meta.ordering` 回显实际排序（`favs`/`fav_pctl`）。

短篇 tab（docs/form-definitions §4 收录资格）的年份榜/比赛榜/题材榜/优质榜
以 `form=short[&year=Y|&contest=X|&genre=G|&order=pct]` 调本端点（不带
status——种子层已实施完结条款，池本身已干净）。三个轴入口**不做中间页**：
直达 `/classic-list` 榜单页，页内用三种不重复的控件切轴——年份 =
ModalBottomSheet、比赛 = Drawer、题材 = FilterChip（用户 2026-11-19 定）。

### GET /strata/discover?cursor=&form=&limit=（**已实现**）

Classic 发现流（docs/12 §5）：候选池 = `is_licensed=0` 且**有封面**（封面硬门槛，
全部有封面的种子书），按平台 `clicks` 降序，**keyset 游标分页**（cursor = 上一批末条
`clicks:nid`，缺省从顶部开始），每批默认 20，stateless。响应含 `next_cursor`
（批末返回，为空表示到底）。

### GET/POST/PUT/DELETE /strata/watchlist（**已实现**，v6 起统一书架）

用户兴趣的唯一列表（docs/02 §v6：本 app 无阅读功能，书架并入 watchlist——
未激活 = 只存，激活 = 追踪）。GET 返回 `{items:[{nid,title,author,genre,cover_url,
added_at,role,note,active}]}`（JOIN seed.books，按加入时间倒序，`active` = poll_enabled）；
POST `/watchlist/:nid` body `{active?: bool, role?: string}`（缺省 active=false = 原「收藏」）；
PUT `/watchlist/:nid` body `{active: bool}` 切换追踪；DELETE 幂等移除。旧 `/strata/shelf`
GET/PUT/DELETE 已移除（数据由 user.db v6 迁移）。观测时序见
`GET /books/:nid/observations`（按 observed_at 倒序，来源 source 标注），
保留期由 PruneObservations 管理。

**订阅式后台抓取（Phase 5，已实现）**：引擎启动时挂后台 worker，每分钟 tick，
每次最多取 5 本到期书（`poll_enabled=1` 且 `now - last_poll_at >= poll_interval`，
默认 86400s），经**后台 lane** 限速槽逐本串行抓取（前台请求永远优先）。
App API 成功→精确元数据写观测 + cover 缓存；否则 HTML 兜底（三态判据，
仅 alive 写观测）。无论成败均盖章 `last_poll_at`，坏书不会卡死队列；
失败不写观测行——数据页据实区分「暂无更新」与「数据缺口」。

### GET /strata/random?limit=&status=&form=（**已实现**）

首页"换一换"网格数据源：`is_licensed=0` 种子库内 `ORDER BY RANDOM()` 均匀抽样
（默认 limit，上限 max_limit），items 为 RankItem（含 status/words/clicks/favs/
cover_url）。诚实随机——官方"次元新书/专题推荐"的换一换同款模式。
`status` 池：`serial`（连载中）/ `finished`（已完结）/ `browse`（长篇口径
words≥60万）/ `short`（短篇池：无状态/字数条件，`form` 传 `short`，
form 过滤即池本身）。

### GET /strata/rankings/short?limit=

200：同上结构，`meta.kind="short"`、`ordering="favs"`、`short_max_words=50000`，
`items` 元素为 `{ nid, title, author, genre, est_year, favs, words }`（无分位字段）。

## 草案（Phase 3/4 实现，未落地前 UI 不得依赖）

### GET /strata/search?q=&limit=（**已实现**）

L1 本地搜索：种子库内 `title`/`author` LIKE 匹配（v1 无 FTS5）。
`q` 必填（非空），`limit` 同分页规则。**每次成功搜索自动写入搜索历史**
（best-effort，写失败不影响搜索本身）。

```json
{
  "meta": { "kind": "search", "pool": "seed", "q": "…", "limit": 50,
            "includes": "licensed", "content_end": "…" },
  "items": [ { "nid": 123, "title": "…", "author": "…", "genre": "…",
               "est_year": 2019, "favs": 12345, "cover_url": "…" } ]
}
```

**授权书可被搜索**（`includes:"licensed"`），只是不参与榜单与统计。
按 `favs DESC` 排序。items 带 `cover_url`（观测覆盖层优先，与列表同口径）。

### GET /strata/search-history?limit=（**已实现**）

最近本地搜索关键词（搜索页空态 chips）：按关键词去重、最近使用优先，
`limit` 默认 10 上限 50，响应 `{ "items": ["英雄", …] }`。存储在 user.db
`search_history`（v5 表，无迁移），保留最近 200 行。

### POST /strata/search/remote?q=（**已实现**）

官方 HTML 搜索（docs/sfacg-endpoints §2.1，原 Phase 4 预留契约落地）：
`GET s.sfacg.com/?Key={q}&SS=0&S=1`，**30 条硬上限、无翻页**——`declared`
就是截断后的数字，不是真实总量。含简介（27/29 命中）与封面，是三个官方
搜索接口里信息最全的（JSON 搜索是其子集，故不用）。

- **静默限流**：HTTP 200 + 指纹翻转（搜索框标签变「请输入关键字」，正常
  页面不含该串），连续 ~17 次触发、持续数分钟。响应 `meta.rate_limited=true`、
  `items` 空——UI 明确提示，绝不伪造空结果。
- **6 秒自冷却**：引擎内强制（`ErrSearchTooSoon` → 429 `too_soon`）；
  手动触发 + 冷却让用户操作基本不可能碰到限流。
- 结果标注 `in_seed`（内置库命中）；**库外命中写 user.db `discovered`**
  （source='search'，重命中刷新 observed_at——观测闭环入口）。
- 库外书详情为按需抓取视图（种子无该行）。

```json
{ "meta": { "kind": "search-remote", "q": "…", "rate_limited": false,
            "declared": 29, "content_end": "…" },
  "items": [ { "nid": 123, "title": "…", "author": "…",
               "updated_at": "2024/3/25 20:57:58", "cover_url": "https://…",
               "summary": "…", "in_seed": false } ] }
```

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

### watchlist（原书架 + 追踪列表，v6 起统一）

| 端点                   | 方法                       | 语义                                                                             |
| ---------------------- | -------------------------- | -------------------------------------------------------------------------------- |
| `/strata/watchlist`      | GET（**已实现**）    | 统一列表（激活 + 未激活），`items` 含 `active`（= poll_enabled）                |
| `/strata/watchlist/:nid` | POST（**已实现**）   | 加入，body `{active?, role?}`；active=false = 原「加入书架」                     |
| `/strata/watchlist/:nid` | PUT（**已实现**）    | 切换追踪，body `{active: bool}`                                                  |
| `/strata/watchlist/:nid` | DELETE（**已实现**） | 移除（观测历史保留）                                                             |

只写 `user.db`；与种子的关联**只用 `nid`**（rowid 每次种子发布都会重排）。

### GET /strata/author-books?author=&limit=&offset=&order=（**已实现**）

作者页时间轴的作品列表（`docs/author-profile-on-demand` §1）：**纯本地**，无网络。
`author` 必填（显示名精确匹配——seed 作者名为规范字符串）；`limit` 默认 20；
`offset` 非负整数；`order` = `newest`（默认，`est_date DESC`）| `oldest`
（`est_date ASC`，作者页排序按钮切换）。两个方向定年 0001 回填书都沉底，
nid 同向跟随。未知作者返回空列表，不是错误。items 为标准 RankItem，**额外带
`est_date`（YYYY-MM-DD，时间轴用；旧端点不返回此字段，RankItem 侧为可选
字段）**；meta.ordering 回显实际排序（`est_date_desc` / `est_date_asc`）。

```json
{ "meta": { "pool": "seed", "ordering": "est_date_desc", "author": "无聊看看天" },
  "items": [ { "nid": 48704, "title": "英雄再临(英雄？我早就不当了)",
               "author": "无聊看看天", "est_year": 2010,
               "est_date": "2010-06-12", "favs": 7881, ... } ] }
```

### GET /strata/discovered?limit=&offset= 与 DELETE /strata/discovered/:nid（**已实现**）

自动收录的库外书列表（收录管理页，观测闭环入口）：user.db `discovered` 表，
按 `observed_at DESC` 分页。行含 nid/title/author/cover_url/summary/source
（`'search'`）/observed_at。**库外书在种子表无行，est_year/genre 为空**——
定年由详情页 overlay 响应实时给出（内置 nid 锚点表，见 `/books/:nid`）。
`DELETE /discovered/:nid` 移除一条收录（收录管理页滑动删除），只删 user.db
行、响应 `{ "deleted": nid }`，种子库不可变。

### GET /strata/author-profile?author=&nid=&with_intro=&fresh=（**已实现**）

作者资料按需抓取 + user.db 缓存（作者页头部；`docs/author-profile-on-demand`
§1–§4，**不预采、不随种子内置**）。`author` + `nid`（该作者任意一本书，作
源书）必填；`with_intro=1` 才追加一次 PC 请求取简介（移动版无简介）；
`fresh=1` 绕过缓存。身份守卫：源书作者与 `author` 必须 casefold 相等（空格
敏感），否则返回但不缓存——错误的书不能污染资料。

响应（扁平）：

```json
{ "nid": 48704, "author_name": "无聊看看天", "author_intro": "……" ,
  "author_avatar": "https://rss.sfacg.com/……", "works": [ { "nid": 48704, "title": "……" } ],
  "verdict": "ok", "observed_at": 1763570000, "source": "live" }
```

- `verdict`：`ok` | `dead`（源书下架，移动版三态判定）| `error`（抓取失败无
  数据）。UI 降级：error 时头部回退本地作者名，书目列表照常。
- `author_intro` 为 null/空是**正常值**（作者没写）——UI 不得伪造、不得拿
  书简介顶替。
- 缓存：`user.db author_profiles`（schema v7，键 = casefold 显示名），ok 行
  7 天 / dead 行 1 天 TTL；缓存命中时 `source=cache` 且 `works` 为空（作品
  列表走 `/author-books`）。只写 user.db，不碰 seed.db。
- 抓取走全局限速器（foreground 槽），与详情页刷新共享配额。

## 官方榜单（docs/sfacg-live-ranks.md 三来源；入口 = 榜单页「官方榜单」卡）

四个端点均为 `GET`，响应为完整榜单 JSON；抓取走全局限速器（foreground
槽），TTL 缓存两层：进程内存 + `user.db official_ranks_cache`（schema
v9，重启不丢；当期 24h / 历史月 365d）。失败 → 502 `upstream`。

### GET /strata/official-ranks/monthly?date=YYYY-MM&rank=0|2|3|4（**已实现**）

历史月榜库（MonthlyBoy.ashx，2013-03 起任意月）。rank：0 月票 / 2 新书 /
3 热销 / 4 对话月票（2017-07 起）。响应 `{meta:{month,rank,kind,note,…},
items:[{rank,nid,title,author,cover_url,value?}]}`——月票/对话月票带
`value`（票数），其余无数值。

### GET /strata/official-ranks/pc（**已实现**）

PC 当期四榜（book.sfacg.com/Rank/）一页返回：`{meta, boards:[{name,
entries:[…]}]}`，顺序 月度月票榜（带票数）/ 月度打赏榜 / 月度热销榜 /
粉丝榜（读者侧，消费火券，条目**无 nid**，`nid=0`）。粉丝榜实为用户
充值榜，对产品无意义，App 不展示（端点保真、展示层裁剪，同移动四榜
口径；2026-11-21 用户判定）。

### GET /strata/official-ranks/mobile?board=original|bm|new|jp|sale（**已实现**）

移动当期榜（m.sfacg.com/rank/）。**注意：仅 `sale`（热销榜）有效**——与
手机 App「畅销榜」几乎一致（数据滞后 ≤3 天）；其余四榜数据落后 >3 年
（2026-11-20 实测判定过时），App 内不展示，端点保留仅供数据对照。
**2026-11-21 用户判定**：官方移动榜单 API 多 bug（官方自身问题），数据
不可信，App 已整体移除移动榜单——端点保留仅供数据对照，不参与
sale-set。

### GET /strata/official-ranks/sale-set（**已实现**）

被动「官方热销」信号：当前在已缓存热销榜上（月榜库当期 rank=3 ∪ PC
月度热销）的 nid 升序数组 `{nids:[…]}`（移动热销 2026-11-21 摘除——App
不再加载移动榜单，官方 API 数据不可信）。**从不为它发起
抓取**——缓存未命中/过期/离线一律空集，UI 据此静默降级（详情页「官方
热销」徽标不显示）。

## FFI 启动契约（Phase 1）

`c-shared` 库导出三个符号：

- `char* strata_start(char* assets_dir, char* data_dir)` → JSON
  `{ok, addr?, seed_version?, book_count?, licensed_count?, content_end?, error?}`，
  `addr` 形如 `http://127.0.0.1:PORT`；
- `char* strata_stop()` → 同构 JSON；引擎未启动也返回 `{ok:true}`；
- `void strata_free(char*)` → 释放以上返回的 C 字符串（Dart 侧用完必调）。

启动失败（如种子缺失/校验不过）通过 `error` 字符串返回诊断信息，UI 据此显示
失败页，不做无限重试。

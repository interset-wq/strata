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
                 "is_sensitive": …, "allow_down": …,
                 "has_comic": …, "has_audio": … },
  "cover": "https://…cover…" | null,
  "awards": [ { "nid": …, "edition": "十二征", "award": "金奖",
                "category": "长篇" | null } ]
}
```

`effective` = 种子值依次被 `meta`（最近一次抓取的全部书目元数据）和
`local`（最新观测）覆盖后的展示值；`local != null || meta != null` 即
`source == "local"`。`cover` 优先取本地封面直链，种子 `cover_url` 大量为空
或为相对路径，客户端须兼容相对路径并使用官方默认封面兜底。
`awards` = 种子侧获奖记录（schema v5，`contest_awards` 表）：详情页徽标
`{edition} · {award|征文获奖}`（「待逐档标定」占位由展示层统一映射为
「征文获奖」，edition 原样显示、多届并列）；种子书详情恒有该字段
（空列表 = 无获奖），库外 overlay 详情无此字段。获奖仅作展示素材，
永不参与排序/打分（docs/12 红线）。
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
`effective`（种子书）与 `book`（库外书）另派生布尔 `has_comic`/`has_audio`
（>0 为 true）供 UI 直接消费；数据仅在 App API 通路开启（设置项 `app_api_enabled`
或 `STRATA_APP_API=1`）且存活态刷新成功时写入（docs/05 §6、§6.1）。
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
`count DESC, contest ASC` 稳定序。组名已归一化（`NormalizeContest`，用户
2026-11-21）：仅 N征 系列是多赛项赛事（六征长篇/中篇/短篇 → 六征），其他
征文名原样返回。返回 `total`（池总量，含无 contest 的书）+
`groups: [{contest, count}]`。

- IP tab 入口行（`form=ip_collab`）：端上取前 2 组作命名 IP 入口
  （崩坏3征文 → 崩坏3，去“征文”后缀），其余折成“其他”（total − 前 2 之和）。
- 短篇 tab 比赛榜入口（`form=short`）：`status` 可选（精确匹配，缺省
  不过滤；短篇池本身经种子完结条款已干净，UI 不传 status）。用途 =
  `/classic-list` 比赛榜页的**赛道 Drawer**（AppBar 汉堡/左缘右滑打开，
  本地搜索过滤 + 选中态，选中后标题追加赛道标签）。

### GET /strata/ip-books?form=&group=&limit=&offset=（**已实现**）

一个 IP 入口的列表：`group` 必填——征文名（归一化匹配：母赛事名命中其
全部篇幅赛项，归一化规则见聚合端点）或 `'other'`
（归一化后收藏数前 2 名征文之外的长尾，引擎内部算 top-2）。组内 `favs DESC,
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
`groups: [{year, count}]`。原用途 = `/classic-list` 年份榜页的**年份
bottom sheet**（用户 2026-11-19 定）；2026-11-21 筛选面板化后经典页
年份值改走 `/facets`，本端点保留。

### GET /strata/genre-groups?form=（**已实现**）

短篇 tab 题材榜入口：`form` 必填（同上），池按 `genre`（非空）聚合
（`count DESC, genre ASC` 稳定序）。返回 `total`（池总量）+
`groups: [{genre, count}]`。原用途 = `/classic-list` 题材榜页的
**FilterChip 行**（用户 2026-11-19 定）；2026-11-21 筛选面板化后经典页
题材值改走 `/facets`，本端点保留。

### GET /strata/facets?form=（**已实现**）

筛选 facet（用户 2026-11-21：所有经典榜单页统一多维 filter）：`form`
可选（空 = 全 form），返回经典页筛选面板各维度的值列表 + 池内本数：
`genres` / `ptypes` / `tags`（top 60，`count DESC, name ASC`）+
`years`（`year DESC`）。池口径与 classic 列表一致（`is_licensed=0`）；
状态是固定枚举（已完结/连载中），不在 facet 里。无白名单：
`/rankings/classic` 的 `tag` / `ptype` 传未知值时匹配不到，不报错。

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
`contest=1`（全部参赛作品）或 `contest=具体届次名`（如 `2025春季征文`；
归一化匹配：`六征` 这类母赛事名命中其 长篇/中篇/短篇 三个赛项）。
与 `genre` 可组合，均在分位榜口径内过滤。`contest` 取值在端上从 `contest=1` 结果
聚合（items 的 `contest` 字段，已是归一化赛事名），不单独提供枚举端点。

### GET /strata/rankings/board?kind=&form=&limit=&offset=（**已实现**）

Classic 全库榜（docs/12 展示列）：平台累计值排序，不涉及分位。`kind` 枚举：
`recommend`(praises) / `popular`(clicks) / `favs` / `new`(est_date) / `finish`(已完结按 favs) /
`words`。`offset` 分页（默认 0）。items 为 RankItem（含 `status`/`words`/`clicks`/`cover_url`）。

### GET /strata/rankings/classic?genre=&status=&contest=&form=&year=&tag=&ptype=&order=&dir=&limit=&offset=（**已实现**）

Classic 主线分类/状态/大赛列表：默认按平台累计 `favs` 降序（`favs DESC, nid ASC`）。
`genre`/`status`/`contest` 与 `/rankings/favs` 同义；`contest=1` 表示全部大赛作品。
`year` 可选（正整数，按 `est_year` 精确过滤；非法值 400）。`tag` /
`ptype` 可选（用户 2026-11-21 筛选面板，取值来自 `/facets`）：
`tag` 为逗号分隔多值 = OR（多选命中任一即入，book_tags EXISTS IN）、
`ptype` 单值精确匹配 price_type；未知值匹配不到。facets 返回的
count 不参与面板展示（用户 2026-11-21：筛选不显示计数）。
`order` 可选：
`favs`（默认）、`pct`（同代收藏分位 `fav_pctl DESC`、NULL 末尾——
docs/form-definitions §6 优质短篇口径）与三个经典榜指标 `clicks`/`praises`/`words`
（平台累计值 `DESC, favs DESC, nid ASC`、NULL 末尾——展示层，docs/12）；
非法值 400。`dir` 可选 `asc`（逆序，用户 2026-11-21；累计值四榜升序、
NULL 仍排末尾，`pct` 忽略；缺省 `desc`），`meta.dir` 回显。`items` 为
RankItem（含 `form`），`meta.ordering` 回显实际排序
（`favs`/`fav_pctl`/`clicks`/`praises`/`words`）。

短篇 tab（docs/form-definitions §4 收录资格）的年份榜/比赛榜/题材榜/优质榜
以 `form=short[&year=Y|&contest=X|&genre=G|&order=pct]` 调本端点（不带
status——种子层已实施完结条款，池本身已干净）。入口**不做中间页**：
直达 `/classic-list` 榜单页，页内两类控件——比赛赛道 = Drawer（侧滑
面板，大池要搜索），五维筛选（状态/价格/年份/题材/标签）= 统一筛选
BottomSheet（用户 2026-11-21：所有经典榜单页共用；旧年份 ModalBottomSheet
/ 题材 FilterChip 行并入筛选面板）、
指标 = SegmentedButton（用户 2026-11-21：短篇 tab「经典榜单」入口
`metric-switchable=1`，点击/收藏/点赞/字数四榜页内切换，20 本/页上滑加载）。

### GET /strata/discover?cursor=&form=&limit=（**已实现**）

Classic 发现流（docs/12 §5）：候选池 = `is_licensed=0` 且**有封面**（封面硬门槛，
全部有封面的种子书），按平台 `clicks` 降序，**keyset 游标分页**（cursor = 上一批末条
`clicks:nid`，缺省从顶部开始），每批默认 20，stateless。响应含 `next_cursor`
（批末返回，为空表示到底）。

### GET /strata/recommend?cursor=&form=&limit=（**已实现**，2026-11-21 接入）

量化推荐流（docs/12 §3、docs/lqs-ranking-integration.md）：候选池 =
`is_licensed=0` + **有封面**（硬门槛）+ `fav_pctl IS NOT NULL`（可推荐门槛代理）。
**两级排序键**（不合并成一个分）：`lqs` 非空的长篇组在前、组内 `lqs DESC`；
其余回退 `fav_pctl DESC`（同代收藏分位，位置分）；`nid ASC` 稳定平局键。
**keyset 游标** = `lqs|favpctl|nid`（lqs 段在回退组为空；浮点全精度往返），
stateless，每批默认 20。累计原始值（clicks/favs/praises）只出现在 SELECT 展示列，
**禁入 ORDER BY / WHERE**（docs/12 §3.2 红线）。响应与 `/discover` 同构
（items + next_cursor），`meta.ordering="lqs|fav_pctl"`、`licensed_excluded=true`。
发现流 UI（发现页）已切换至本端点；`/discover` 保持 clicks 展示流口径不变
（端点保真、展示层裁剪的同一政策）。

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

### POST/DELETE /strata/dev/simulate?nid=&days=（**已实现**，工作台开发辅助）

作者工作台（docs/07）开发辅助：真实轮询观测需要数周才能积累，此端点向
user.db 生成一段**确定性**合成观测序列（同 nid+days 重放数值一致，时间戳
锚定运行日），供更新热力图 / 六指标折线 / 同期对照开发验收。`days` 默认
60、范围 1..180。起点 = 种子书当前值（种子是 2026-05 快照，终点高于种子，
与真实计数器行为一致；库外书用中性基线）。覆盖六指标：words / favs /
praises / short_comments / long_comments / clicks。序列含三种日类以覆盖全部
渲染路径：**更新日**（~80%，Δwords 2,500–6,499 横跨全勤 3,000 线）、
**断更日**（~12%，有观测但 Δwords=0）、**缺口日**（~8%，无观测行——
数据缺口 ≠ 断更；缺口期计数器仍在涨，次日差分读作「含 N 天累计」）；
已完结书永不加字。行 `source='simulate'`（观测时序端点现返回 source 标记，
顺带修复此前 SELECT 漏列的缺陷），重跑替换同 nid 的 simulate 行
（幂等），不碰 seed.db 与真实观测行。POST 响应
`{nid,days,rows,gap_days,flat_days,start_words,end_words,start_favs,end_favs,
status,source}`；DELETE 仅删该 nid 的 simulate 行，响应 `{nid,deleted}`。

### GET/POST/DELETE /strata/dev/test-book（**已实现**，设置页测试开关）

作者工作台（docs/07）开发辅助：「设置 → 测试工具 → 工作台测试书」Switch 的
背后即此端点。POST 注入一本**虚构**测试书（固定 nid 99,000,001，远高于平台
真实 nid 段，永不冲突；nid 定年走 extrapolation 低置信档，对虚构书是诚实的），
模仿真实库外书链路，引擎零特判：60 天模拟观测（SimulateObservations，
`source:'simulate'`，非种子书中性基线）+ `book_meta` 行（最新观测值 = 书
「当前值」，详情页因此走 `source:"local"` overlay 链）+ `discovered` 行
（watchlist title COALESCE 与收录管理可找到它）+ watchlist 条目（`role:'self'`，
**不追踪**——虚构书无官方页，后台轮询必失败；用户可手动激活验证失败路径，
docs/07 §4）。DELETE 一次性清四表。GET/POST/DELETE 响应
`{nid,present,title,days,rows}`（缺席时仅前二字段非空）。`days` 默认 60，范围
1..180。不碰 seed.db；幂等重注入（同 nid 替换旧状态）。

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

### GET /strata/contests

赛事档案列表（docs/contest-display-in-app.md 形态一）：seed 内置库（`is_licensed=0`）
按赛事事件聚合——N征 系列并入母赛事（对话类分轨随之并入），非 N征 赛事以
原名为单事件。零网络请求。官方日期来自引擎内嵌静态表（源
`analysis/references/contest-editions.md`，用户核实；缺失只显届次/年份，不编造）。

200：`{ groups: [ContestGroup] }`，示例（`.25` 种子实测）：

```json
{
  "name": "七征", "series": "x", "count": 399,
  "forms": { "long": 280, "dialogue": 107, "short": 8, "medium": 4 },
  "tracks": ["七征长篇", "七征对话类征文长篇", "七征对话类征文短篇", "七征中篇", "七征短篇"],
  "roster": true,
  "roster_tracks": ["长篇", "中篇", "短篇", "对话类征文长篇", "对话类征文短篇"],
  "year_min": 2019, "year_max": 2019,
  "year": 2019, "start": null, "end": null, "note": null
}
```

- `series`：`x`（N征）/ `winter` / `spring` / `autumn` / `other`。分节排序，
  节内按 cohort 最早 `est_year`、再按名。
- `count`/`forms`：仅内置库（种子收录）作品，**非官方全量参赛规模**
  （属 P1 清单 API）。`forms` 按 DOM 核实的 `form` 统计，与 `tracks`
  （平台原始赛项标注）不必互洽。
- `tracks`：赛事原始赛项名（count DESC）。
- `roster`/`roster_tracks`：该赛事是否可拉官方清单（引擎内嵌已验证 tagId
  静态台账，`store/roster_tags.go`）+ 已验证赛道列表（空 = 单轨，
  `roster_tracks` 键省略）。档案页「查看官方清单」入口恒在：`roster=false`
  时引擎回落库内子集并提示「仅库内作品」（见 `/strata/roster` 降级）。
- `year`/`start`/`end`/`note`：官方元数据（静态表），无则 null；
  `year_min`/`year_max` 是库内书 `est_year` 区间（在库口径）。

### GET /strata/contests/books?contest=&per=

一届赛事的代表作：per-form 窗口
（`ROW_NUMBER() OVER (PARTITION BY form ORDER BY (fav_pctl IS NULL) ASC,
fav_pctl DESC, nid)`），`per` 限每形态条数（1..50，默认 10）；
累计原始值不进排序（docs/12 红线）。covers 覆盖层适用。

- 400 `invalid_argument`：`contest` 缺失，或 `per` 越界。
- 匹配语义与榜单筛选一致：N征 事件前缀匹配（含对话类分轨），非 N征 精确匹配。

200：`{ contest, items: [RankItem], awards: [AwardBook] }`（`rank` = 该 form
组内名次 1..per）。`awards` = 该赛事库内获奖作品（schema v5，`contest_awards`
表 join seed.books；edition → 赛事名由引擎内置静态表映射 11 条，表外赛事
返回空列表）；行序 = `fav_pctl DESC NULLs last, nid`——奖项字段不参与排序
（docs/12 红线）。`AwardBook` = award 四字段（nid/edition/award/category）
+ title/author/favs/fav_pctl/cover_url/est_year。140 本库外获奖行无 books
行可 join，v1 不返回。

### GET /strata/roster?contest=&division=&page=（**已实现**，2026-11-21 P1 官方清单）

一届赛事的官方参赛清单一页（docs/contest-display-in-app.md 形态二，
**按需**——全库后台批量抓清单禁止）。`contest` = 赛事事件名（同
`/contests`）；`division` = 赛道（多轨赛事必传，取值 = `/contests` 该组
`roster_tracks`；单轨留空）；`page` 从 1 起（引擎内部换算各世代页基：
新 API 1-based、旧 API 0-based pi）。

- 400 `invalid_argument`：`contest` 缺失；多轨赛事 `division` 缺失/未知；
  `page` < 1。
- tagId 台账是引擎内嵌静态表（29 条，源 docs/contest-roster-harvest.md；
  tagId 只能从每届页面现场取、不能推导——新增届次务必现取后入表）。
- 两代端点（按 tag 世代选择）：新 SPA（2023+，`api/essay/getNovels`，
  size ≤ 500）/ 旧 H5（2018–22，`Common.ashx?op=getNovelsByTag`，ps ≤ 200，
  相对封面路径拼 CDN 前缀）。清单行只有 6 字段
  （nid/标题/作者/简介/封面/categoryID）；`category_id` 是赛道提示
  （0 常规/1 对话/3 征文短篇/4 沉浸式），**不是 form 真值**（E.28 只正向
  用 1/4）。
- **size 边界陷阱**：个别 tag（如 724）size=500 返回空、≤8 正常——首页
  空时引擎按 500→100→10 递减重试后再下结论（旧世代 ps=200 单档）。
- 缓存：复用 `official_ranks_cache`（user.db v9），key = `roster:{tag}:{page}`；
  TTL 按 `contest_meta` end 日期判（未结束 24h / 已结束 365d / end 未知 24h）。
  缓存的是上游原始页；**本地 join 每次响应都做**（覆盖层/种子变化即时反映）。
- **本地 join**：种子内作品 `in_library=true` + form/fav_pctl/favs/status/
  est_year/words（seed 口径；用户观测覆盖层从不进 form/分位）；库外作品
  只带清单 6 字段——不伪造徽标（docs/12 红线）。
- **降级恒 200（无 502 墙）**：赛事无 tagId / 接口失效（新 API
  `errorCode≠200`、旧 API 裸 `status≠200`、结构缺失、响应体畸形）/ 上游
  抓取失败 → 引擎回落库内子集（同代分位序、cap 2000），响应
  `source="degraded"` + `note`；UI 顶部提示条「仅库内作品，清单不完整」。
  失效响应不入缓存，下次打开重试（不重试风暴）。
- 清单顺序保持官方返回序；v1 无排序控件（用户 2026-11-21 定案）。
- 库外条目点击复用搜索页链路：UI 推 `/book/{nid}`，详情页覆盖层按需抓
  详情 + 自动收录（discovered），不写 seed。

200：

```json
{ "contest": "十三征", "division": "长篇", "page": 1, "pages": 3,
  "source": "official",
  "items": [ { "nid": 713638, "title": "Re：如果成为神明",
               "author": "某NoName", "intro": "…",
               "cover": "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2024/08/….jpg",
               "category_id": 3, "in_library": true, "form": "short",
               "fav_pctl": 0.93, "favs": 412, "status": "连载中",
               "est_year": 2024, "words": 38000 } ] }
```

降级响应同形：`source="degraded"`、`note`（如「无官方清单，仅显示库内
作品」）、`page`/`pages` 恒 1，items 为库内子集（无 intro/category_id）。

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

**App API 增强通路（默认关闭）**：设置项 `app_api_enabled`（`PUT /settings`，见下节）启用；
未设置过时环境变量 `STRATA_APP_API=1` 兜底（native 开发用）。启用后 refresh 先走
`api.sfacg.com/novels/{id}`（App 内置公共凭据自签，共用全局限速器，前台优先）；
成功时以 App 精确值写入观测（`clicks`= `viewTimes` 精确整数、
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

### GET / PUT /strata/settings（**已实现**）

GET 200：

```json
{ "detail_rate_limit_enabled": true, "detail_refresh_window_seconds": 86400,
  "app_api_enabled": false }
```

PUT body 传 `detail_rate_limit_enabled` / `app_api_enabled`（至少一个，bool），响应同
GET。两项均持久化在 user.db prefs：详情刷新限流默认开；App API 默认关，未设置过时
环境变量 `STRATA_APP_API=1` 兜底（native 开发用）。App API 通路认证为 App 内置固定
凭据 + 每请求自签（`sfacg-app-api.md` §1，引擎 `crawl/appapi.go` 已实现），无需用户
输入任何凭据；共用全局限速器，前台优先，任何失败静默回落移动版 HTML 基线。

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

## 官方榜单（docs/sfacg-live-ranks.md 三来源；入口 = 首页长篇页内 Tab / 对话直达 m4）

四个端点均为 `GET`，响应为完整榜单 JSON；抓取走全局限速器（foreground
槽），TTL 缓存两层：进程内存 + `user.db official_ranks_cache`（schema
v9，重启不丢；当期 24h / 历史月 365d）。失败 → 502 `upstream`。

### GET /strata/official-ranks/monthly?date=YYYY-MM&rank=0|2|3|4（**已实现**）

历史月榜库（MonthlyBoy.ashx，2013-03 起任意月）。rank：0 月票 / 2 新书 /
3 热销 / 4 对话月票（2017-07 第一份；2018-07 起连续）。UI 可选下界：
`m4` = 2017-07，其余历史月榜 = 2013-03；中间空槽照常可选并显示「无数据」。
响应 `{meta:{month,rank,kind,note,…},
items:[{rank,nid,title,author,cover_url,value?}]}`——月票/对话月票带
`value`（票数），其余无数值。

### GET /strata/official-ranks/pc（**已实现**）

PC 当期四榜（book.sfacg.com/Rank/）一页返回：`{meta, boards:[{name,
entries:[…]}]}`，顺序 月度月票榜（带票数）/ 月度打赏榜 / 月度热销榜 /
粉丝榜（读者侧，消费火券，条目**无 nid**，`nid=0`）。粉丝榜实为用户
充值榜，对产品无意义，App 不展示（端点保真、展示层裁剪，同移动四榜
口径；2026-11-21 用户判定）。App 进一步只展示**月度打赏榜**：PC 月度
月票/热销与历史月榜当月 `rank=0/3` 是同一榜，不重复展示（2026-11-21
用户判定）。PC 榜单页的排行行**本身没有 `<img>`**；服务端按 nid 回查
`seed.books.cover_url` / `covers` 补齐 `cover_url`，仍缺失的才由端上默认
封面兜底。

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

### POST /strata/books/:nid/rank-seed（**已实现**）

即时详情的预写（2026-11-21，收录提速）：官方榜单行被点时，UI 先调用
本端点把该行的 title/author/cover_url/genre 写入 `user.db book_meta`
（source=`rank`；`ON CONFLICT` 只填空字段，**从不覆盖**已有数据——完整
抓取数据仍归标准 refresh 路径），再导航 `/book/:nid`。库外书由此首帧
即渲染最小 overlay（不再 404 → 全屏转圈等 ~10s 收录）；详情页发现
overlay 无 `words` 时自动触发一次后台 refresh 静默补全。纯本地写，
**从不触网**。请求体 `{title, author, cover_url, genre}`（均可省略）；
响应 `{seeded: true}`。

## FFI 启动契约（Phase 1）

`c-shared` 库导出三个符号：

- `char* strata_start(char* assets_dir, char* data_dir)` → JSON
  `{ok, addr?, seed_version?, book_count?, licensed_count?, content_end?, error?}`，
  `addr` 形如 `http://127.0.0.1:PORT`；
- `char* strata_stop()` → 同构 JSON；引擎未启动也返回 `{ok:true}`；
- `void strata_free(char*)` → 释放以上返回的 C 字符串（Dart 侧用完必调）。

启动失败（如种子缺失/校验不过）通过 `error` 字符串返回诊断信息，UI 据此显示
失败页，不做无限重试。

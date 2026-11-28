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
  "cover": "https://…cover…" | null,
  "awards": [ { "nid": …, "edition": "十二征", "award": "金奖",
                "category": "长篇" | null } ]
}
```

`effective` = 种子值依次被 `meta`（最近一次抓取的全部书目元数据）和
`local`（最新观测）覆盖后的展示值；`local != null || meta != null` 即
`source == "local"`。`cover` 优先取本地封面直链，种子 `cover_url` 大量为空
或为相对路径，客户端须兼容相对路径并使用官方默认封面兜底。
`awards` = 种子侧获奖记录（schema v5，`contest_awards` 表）：引擎仍返回该字段，
但**端上已不解析、详情页不显示**（用户裁定 2026-11-26：911 行里 867 行的奖项是
占位值「待逐档标定」，渲染成「征文获奖」零信息，真获奖名全库仅 42 本；详情页
赛事卡只报 `books.contest` 届次，见 `docs/contest-display-in-app.md` §6）；
种子书详情恒有该字段（空列表 = 无获奖），库外 overlay 详情无此字段。获奖仅作
展示素材，永不参与排序/打分（docs/12 红线）。
`POST /strata/books/:nid/refresh` 的 `detail` 同样返回本次请求解析到的全部字段：
HTML 含书名/作者/分类/签约/封面/简介/收藏/赞/字数/状态/更新时间，外加
`tickets`（当月月票，`GetTicketNum.ashx` 追加请求，失败为 null）；App API 含
`markCount/viewTimes/charCount/point/addTime/signStatus/typeId/categoryId/...`。


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
`groups: [{contest, count, top_nid, top_title, top_cover}]`；`top_*`
是该组收藏最高的一本，供 IP tab 卡片文案直接渲染，避免每组再发
`/ip-books` 请求（`top_cover` 保留在契约里，当前 UI 不展示封面）。

- IP tab 分组网格（`form=ip_collab`）：端上展示全部组（seed 当前 6 组），
  不再取前 2 组 + “其他”；每组是纯文字卡片（`top_title` 做副文案），
  点击进 `/ip-books?group=` 二级页。2026-11-24 用户定：IP 封面质量参差，
  不用封面。
- 短篇 tab 比赛榜入口（`form=short`）：`status` 可选（精确匹配，缺省
  不过滤；短篇池本身经种子完结条款已干净，UI 不传 status）。用途 =
  `/classic-list` 比赛榜页的**赛道 Drawer**（AppBar 汉堡/左缘右滑打开，
  本地搜索过滤 + 选中态，选中后标题追加赛道标签）。

### GET /strata/ip-books?form=&group=&limit=&offset=（**已实现**）

一个 IP 入口的列表：`group` 必填——征文名（归一化匹配：母赛事名命中其
全部篇幅赛项，归一化规则见聚合端点）。组内 `favs DESC,
nid ASC`，分页同 `/rankings/classic`。未知征文名返回空列表不报错。
`'other'` 仍保留为兼容旧深链（归一化后收藏数前 2 名征文之外的长尾，
引擎内部算 top-2），但 IP tab 分组网格已不再生成该入口。

### GET /strata/calendar?granularity=day|week|month&anchor=YYYY-MM-DD&per_cell=（**已实现**，2026-11-26 增 bounds）

发书日历（docs/14 P1）：种子书按 `est_date` 日/周/月聚合，周一起算；空日期
补零格。**响应**：`{granularity, anchor, cells:[{date,total,universe,items?}],
bounds:{first,last}}`。`month` 格只有 total/universe（items 省略）；
`total` = 内置库（is_licensed=0）可点击子集，`universe` = 全平台估计
（`calendar_universe` 表，UI 必须标「估计~N」）；`low` 档只入月层。
`bounds` = 日历真正有数据的日子区间（库内 est_date ∪ calendar_universe 两层
并集），UI 的导航边界与默认落点用它——不能用 manifest genMax 推 12-31，
那会让用户翻进空月（2026-11-26 修订）。`universe` 原样返回
`calendar_universe` 的构建值（含不完整末尾月，如 2026-10）；「尾部不完整月
不估算」由 UI 依据 `bounds.last` 是否在月末自行判定（不在月末 → 该月及之后
不显示全平台数字，2026-11-26 裁定；引擎与种子不裁剪）。非法 granularity / 非
YYYY-MM-DD anchor → 400。

### GET /strata/preorder?date=YYYYMMDD（**已实现**，2026-11-24）

每周签约升 VIP 推荐（官方活动名"每周上架推荐"）：代理官方
`pages.sfacg.com/ajax/act/PreOrder.ashx?op=getPreOrderNovels&date=&cid=0`
（端点事实与语义实证 → docs/sfacg-endpoints.md §7.5）。要点：

- `date` 必须是**周六**（期数键）；非周六由引擎归一到所在周的周六。
  2020-08 中旬前基本全空（2018-12 起零星有），空期返回 `items: []`。
- `cid` 固定 0（轻小说）——实测各期 cid=1 对话小说全空，暂不暴露参数。
- 只读、无认证、无分页；走全局限速器前台车道（用户触发），结果按期缓存
  24h（空期缓存负结果），重复打开不再打上游。
- 响应：`{date: "YYYY-MM-DD", items: [{nid, title, intro, cover,
  is_main_push, tags: [], in_seed, in_lib}]}`。`is_main_push=true` 官方渲染
  「主编推荐」。`in_seed` = 该 nid 在内置库；是则 `in_lib` 带库内
  author/favs/cover，端上直接进详情页；否则详情不可用（上游无作者/字数，
  intro 内联展示）。
- 口径红线（§7.5 实证）：`date` 是**预定签约升 VIP 周**（官方语义 =
  签约升级为 VIP），不是首发日——我们此前的「上架」语义实为入库/创建，
  与官方不符已弃用；与日历 est_date（nid 内插）口径不同，UI 严禁混列/互推。
- `hasOrder` 是用户预约态（未登录恒 false），不透传。

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
`groups: [{year, count}]`。用途 = `/classic-list` 顶部**年份轴横向条**
（全部 + 各年，用户 2026-11-25 定；年份高频切换，不放进筛选面板）。
2026-11-21–24 曾临时走 `/facets`，现恢复使用本端点。

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
  "meta": { "kind": "favs", "pool": "seed", "ordering": "favs",
            "content_end": "…", "year": 2019, "genre": null|"魔幻",
            "limit": 50, "licensed_excluded": true },
  "items": [ { "nid": 123, "title": "…", "author": "…", "genre": "…",
               "est_year": 2019, "favs": 12345 } ]
}
```

榜单按同代收藏降序（`favs DESC, nid`；E.30：分位列退役，同代内与分位序单调等价）；`licensed_excluded` 恒为 true，榜单永不出现授权书。

**二级页过滤参数（宫格入口，已实现）**：`status=已完结|连载中`（精确匹配，非法值 400）、
`contest=1`（全部参赛作品）或 `contest=具体届次名`（如 `2025春季征文`；
归一化匹配：`六征` 这类母赛事名命中其 长篇/中篇/短篇 三个赛项）。
与 `genre` 可组合，均在榜口径内过滤。`contest` 取值在端上从 `contest=1` 结果
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
`favs`（默认）与三个经典榜指标 `clicks`/`praises`/`words`（`pct` 原同代收藏分位
排序，E.30 退役——分位列已出种子）。
（平台累计值 `DESC, favs DESC, nid ASC`、NULL 末尾——展示层，docs/12）；
非法值 400。`dir` 可选 `asc`（逆序，用户 2026-11-21；累计值四榜升序、
NULL 仍排末尾，`pct` 忽略；缺省 `desc`），`meta.dir` 回显。`items` 为
RankItem（含 `form`），`meta.ordering` 回显实际排序
（`favs`/`clicks`/`praises`/`words`）。

短篇 tab（docs/form-definitions §4 收录资格）的年份榜/比赛榜/题材榜/优质榜
以 `form=short[&year=Y|&contest=X|&genre=G]` 调本端点（不带
status——种子层已实施完结条款，池本身已干净）。入口**不做中间页**：
直达 `/classic-list` 榜单页，页内控件——年份 = 顶部固定横向条
（`/year-groups`，全部 + 各年，一键切换）、比赛赛道 = Drawer（侧滑
面板，大池要搜索）、四维筛选（状态/价格/题材/标签）= 统一筛选
BottomSheet（用户 2026-11-25：年份移出后所有经典榜单页共用）、
指标 = SegmentedButton（用户 2026-11-21：短篇 tab「经典榜单」入口
`metric-switchable=1`，点击/收藏/点赞/字数四榜页内切换，20 本/页上滑加载）。

### GET /strata/discover?cursor=&form=&limit=（**已实现**）

Classic 发现流（docs/12 §5）：候选池 = `is_licensed=0` 且**有封面**（封面硬门槛，
全部有封面的种子书），按平台 `clicks` 降序，**keyset 游标分页**（cursor = 上一批末条
`clicks:nid`，缺省从顶部开始），每批默认 20，stateless。响应含 `next_cursor`
（批末返回，为空表示到底）。

### GET /strata/recommend?cursor=&form=&k=&limit=（**已实现**，2026-11-21 接入；2026-11-23 改 cqs/clx 口径）

量化推荐流（docs/12 §3、app/docs/18-runtime-metrics.md，报告 24）：候选池 =
`is_licensed=0` + **有封面**（硬门槛）+ form 内 `cqs IS NOT NULL`（且 `cps` 落在
form 内 20–80 分位**中层带**——筛选不发榜）。**排序** = form 内 `cqs DESC`；
`k>0` 时运行时 **clx** 重排 `cqs×(1−K+K×len_norm)`（篇幅偏好，K∈[0,1] 缺省 0，
预设 0/0.25/0.60；不落列、不合成分）。**keyset 游标** = `score|nid`（score 为
排序表达式值，浮点全精度往返），stateless，每批默认 20。items 带 `cqs_state`
（stable/low 证据强度）。**form 回退**：short/ip_collab 无 cqs 证据（报告 24 §3），
回退经典 `pr DESC` 排序（赞藏比，E.30；门 `pr NOT NULL` = 同一 favs≥10
证据代理；`meta.ordering="pr"`；游标保持 3 段 "0|pr|nid" 语法）。累计原始值
（clicks/favs/praises）只在 SELECT 展示列，**禁入 ORDER BY / WHERE**
（docs/12 §3.2 红线）。响应与 `/discover` 同构（items + next_cursor），
`meta.ordering="cqs"|"clx"|"pr"`、`licensed_excluded=true`。lqs 两级排序为
上一版口径（归档不落地，cqs 接任，两者不合并、分数不可比）。**P2（2026-11-23）**：
discovered 中已评分的库外书以同键并流——详情抓取写回后运行时现算
（eras 锚点定年 → 长度带 form → cps/cqs/len_norm，校准表来自种子 v7）；
同人库外书不评分（E.17 污染源），form 未知不进流。发现流 UI（发现页）
已切换至本端点；`/discover` 保持 clicks 展示流口径不变
（端点保真、展示层裁剪的同一政策）。

### GET /strata/quant?form=&board=&limit=&offset=（**已实现**，2026-11-25）

量化榜单页（用户 2026-11-25 裁定：自定义指标独立出榜，**经典榜单禁止修改**；
app/docs/18 红线修订）：`board=cqs` 为**口碑榜**（form 内 `cqs DESC`，NULL 不进榜，
items 带 `cqs_state`（stable/low）证据强度——18 §2 红线 4：不展示精确名次）；
`board=cps` 为**位置榜**（form 内 `cps DESC`，NULL 不进榜；替代旧「不发榜」裁定）。
**form 是硬前置**（18 §2 红线 1）：发布 form=long（缺省）| form=dialogue
（2026-11-25 起对话 tab 独立出页：app 按 form 隔离、无页内切换；
short/medium/IP 无 cqs 证据）。候选池 = 三源并集（种子书 `is_licensed=0`
∪ 已评分 discovered ∪ 收录 book_meta，按 nid 去重——收录均等原则）；
**无** cps 中层带过滤、**无**封面硬门槛（榜单全量排序，非发现流，区别于
`/recommend`）；平台累计值（clicks/favs/praises）不进 ORDER BY（docs/12 红线）。
offset 分页（同 `/rankings/classic`）；`meta.kind="quant"`，回显 `board`/`form`，
`licensed_excluded=true`。clx 篇幅偏好不属于榜单（18 §2 红线 5），本端点不接受 `k`。

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
原名为单事件（异写经台账 alias 归一，同一届不会渲染成两行）。零网络请求。

官方口径（赛程日期、逐赛道清单条数、获奖数、活动页 URL）全部来自引擎内嵌
**赛事台账** `store/contest_ledger.json`：`app/tools/contestledger/build_ledger.py`
从 contest-achieve（https://github.com/light-nook-labs/contest-achieve，
AGPL-3.0）`docs/data/contests.json` 生成，per-track 条数 2026-11-24 抓取。
台账取代此前两份手抄 Go 表（`store/roster_tags.go` + `store/contest_meta.go`，
已删），是官方事实的唯一来源；改台账只改生成脚本，不手改 JSON。
当前 78 个事件 / 102 条 roster tag / 15 条 award tag / 4 条 alias；
53 届有已验证活动页 URL、75 届有 `roster_total`、41 届有 `award_total`。
表外赛事只显届次/年份，不编造。

200：`{ groups: [ContestGroup] }`，示例（当前种子实测）：

```json
{
  "name": "七征", "series": "x", "count": 452,
  "forms": { "long": 217, "dialogue": 144, "short": 81, "medium": 10 },
  "tracks": ["七征长篇", "七征对话类征文长篇", "七征对话类征文短篇",
             "七征-赛道3", "七征短篇", "七征中篇", "七征-赛道2"],
  "year_min": 2019, "year_max": 2019,
  "year": 2019, "start": "2019-05-25", "end": "2019-09-24",
  "result": "2019-12-24",
  "official": "https://pages.sfacg.com/h5/act/zw2019/",
  "roster": true,
  "list_kind": "roster",
  "divisions": [
    { "name": "长篇", "tag": 408, "kind": "roster", "roster": 4272 },
    { "name": "中篇", "tag": 409, "kind": "roster", "roster": 1359 },
    { "name": "短篇", "tag": 410, "kind": "roster", "roster": 764 },
    { "name": "对话类征文长篇", "tag": 411, "kind": "roster", "roster": 583 },
    { "name": "对话类征文短篇", "tag": 412, "kind": "roster", "roster": 372 }
  ],
  "roster_total": 7350, "award_total": 45
}
```

一征（award-only 示例）：

```json
{
  "name": "一征", "series": "x", "count": 2,
  "forms": { "long": 2 }, "tracks": ["一征"],
  "year": 2013, "year_min": 2014, "year_max": 2014,
  "roster": false, "list_kind": "award",
  "divisions": [
    { "name": "金奖", "tag": 635, "kind": "award", "roster": 1, "awards": 1 },
    { "name": "银奖", "tag": 636, "kind": "award", "roster": 1, "awards": 1 },
    { "name": "铜奖", "tag": 637, "kind": "award", "roster": 3, "awards": 3 }
  ],
  "award_total": 5
}
```

- `series`：`x`（N征）/ `winter` / `spring` / `autumn` / `other`。组序 =
  档案 tab 序（`spring` / `x` / `autumn` / `winter` / `other`，用户
  2026-11-22 裁定），节内按开赛年份**降序**（用户 2026-11-26 改裁定：档案
  按「最近一届在前」读；官方 `year` 优先、缺失落 `year_min`）、再按
  「第X届」届序降序、再按 `roster_total` 降序（缺失按 0 排最后；主题/其他
  tab 无届序，靠这一级分大小）、再按名（稳定排序）。
- `count`/`forms`：**本地在库**（种子收录）作品数与形态分布，不是官方参赛
  规模；`forms` 按 DOM 核实的 `form` 统计，与 `tracks`（平台原始赛项标注）
  不必互洽。UI 与 `roster_total` 并排时两个口径必须分开标注（「在库」/
  「官方清单」），不得混成一个数。
- `tracks`：赛事原始赛项名（count DESC，同数按名）。
- `roster`/`divisions`/`list_kind`：`ledger tracks` 现在 roster 与 award 两类都出。
  `roster` = 该赛事是否有参赛清单 tag（`list_kind == "roster"` 的快捷布尔；
  award-only 赛事恒 false）；`list_kind` = `"roster"` | `"award"` | 键省略（无
  tag）——`"award"` 仅一/二/三征（上游获奖作品标签 635–649），UI 只能说
  「获奖名单」。`divisions` = 官方赛道（台账序 = 官方展示序），每行 `{name,
  tag, kind, roster?, awards?}`：roster 赛道 `roster` = 官方清单条数（未核实
  则键省略），award 赛道 `awards` = 获奖名额（`roster` 是该获奖 tag 的列表
  长度，只有几个名额时二者可能不等，**展示名额用 `awards`**）。单轨赛事只有
  一行 `name="全部"`（`tag` 仍是真实 tagId；`/strata/roster` 的 `division`
  传「全部」与留空等价——UI 把 chip 文案原样回传，故两者都认）。
  无 tag 时 `divisions` 键省略。档案页「查看官方清单 / 获奖名单」入口恒在：
  无 tag 时引擎回落库内子集并提示「仅库内作品」（见 `/strata/roster` 降级）。
- `roster_total`：官方参赛清单总条数 = 各 roster 赛道 `roster` 之和（上游
  逐 tag 现场计数；award 赛道永不计入）。任一赛道条数未核实 → null，**不给
  半截的和**；UI 于是回落显示「接口无清单」而不是摆一个偏小的数。award-only
  赛事恒 null（从未有参赛清单）。
- `award_total`：官方获奖名额 = 各赛道 `awards` 之和（台账全有才算，否则
  null），只为统计格/入口撑数。2026-11-26 起一/二/三征的获奖名单本身可经
  `/strata/roster` 拉取（见下），其余届次仍只有数量（docs/contest-display-in-app.md §6），
  UI 不得把名额当参赛规模。
- `year`/`start`/`end`/`result`/`note`/`official`：官方元数据（台账），
  无则键省略（UI 区分「官方未公示」与一个日期）；`result` = 官方公布日，
  晚于今天时档案页说「预计结果公布」——还没到日子的是承诺不是事实。
  `year_min`/`year_max` 是库内书 `est_year` 区间（在库口径）。
  一/二/三征上游无日期，`year` 按用户核定填 **2013/2014/2015**
  （历史页 `zw2013`–`zw2015` 同证，2026-11-26）；三征另有上游公布日
  2015-12-15。
  `official` = 官方活动页 URL（h5/移动版形态，逐届页面实证见
  `docs/contest-roster-harvest.md` §2），未验证时省略、UI 隐藏跳转入口。
- `lane`：other 系列事件的首页 tab 归属（用户 2026-11-22 裁定：对话的
  归档放首页对话区、IP 的归档放 IP 区）：`dialogue` / `ip`；键省略 =
  主题类（档案列表「主题」tab）。引擎侧确定性分类：先届次覆盖（星穹
  小说家征文 = 对话赛事，用户 2026-11-22 核实——IP 标题但归对话区），
  再名称规则（含 对话/点鸭 → dialogue；含 同人/崩坏3/少女前线/龙之谷/
  星穹 → ip）。四季系列永无 lane。UI 侧对应入口 =
  `/contest-archive?lane=dialogue`（首页对话区）/ `?lane=ip`（首页 IP 区）——
  不带 lane 时「主题」tab 只列 lane 为空的主题类。

### GET /strata/contests/books?contest=&per=

一届赛事的代表作：per-form 窗口
（`ROW_NUMBER() OVER (PARTITION BY form ORDER BY (favs IS NULL) ASC,
favs DESC, nid)`），`per` 限每形态条数（1..50，默认 10）；
跨代 favs 近似（E.30：分位列退役）。covers 覆盖层适用。

- 400 `invalid_argument`：`contest` 缺失，或 `per` 越界。
- 匹配语义与榜单筛选一致：N征 事件前缀匹配（含对话类分轨），非 N征 精确匹配。

200：`{ contest, items: [RankItem], awards: [AwardBook] }`（`rank` = 该 form
组内名次 1..per）。`awards` = 该赛事库内获奖作品（schema v5，`contest_awards`
表 join seed.books；edition → 赛事名由引擎内置映射表 `store/awards.go`
`awardEventEditions`（11 条，仍是手抄小表，未并进台账）映射，表外赛事
返回空列表）；行序 = `favs DESC NULLs last, nid`（E.30）——奖项字段不参与排序。
`AwardBook` = award 四字段（nid/edition/award/category）
+ title/author/favs/cover_url/est_year。140 本库外获奖行无 books
行可 join，v1 不返回。

### GET /strata/roster?contest=&division=&page=（**已实现**，2026-11-21 P1 官方清单）

一届赛事的官方参赛清单一页（docs/contest-display-in-app.md 形态二，
**按需**——全库后台批量抓清单禁止）。`contest` = 赛事事件名（同
`/contests`）；`division` = 赛道（取值 = `/contests` 该组
`divisions[].name`；多轨赛事必传，单轨赛事传「全部」或留空，两者等价）；
`page` 从 1 起——**对 App 的接口 1-based，两代上游端点都 0-based**，引擎
内部换算 `page-1`（2026-11-26 探针订正：旧「新 API 1-based / 旧 API 0-based
pi」是错的；tag 704 `page=0` 给 500 条、`page=1` 给末尾 321 条、`page=2`
已空但 `totalPage` 仍说 2）。

- 400 `invalid_argument`：`contest` 缺失；多轨赛事 `division` 缺失/未知；
  `page` < 1。
- tagId 台账 = 引擎内嵌赛事台账 `store/contest_ledger.json`（102 条 roster
  tag，源 docs/contest-roster-harvest.md；tagId 只能从每届页面现场取、不能
  推导——新增届次务必现取后回 `build_ledger.py` 入表）。台账另有 15 条
  `kind="award"` 的 tag（一/二/三征的金银铜榜，635–649，contest-achieve
  2026-11-24 采集）：2026-11-26 起它们**同一抓取路径可拉**——响应带
  `list_kind="award"`、降级 note 说「获奖名单暂不可用」，UI 标题写
  「获奖名单 · X」；它们仍不计入 `roster_total`，也永不被称作参赛清单。
- 两代端点（按 tag 世代选择）：新 SPA（2023+，`api/essay/getNovels`，
  size ≤ 500）/ 旧 H5（2018–22，`Common.ashx?op=getNovelsByTag`，ps ≤ 200，
  相对封面路径拼 CDN 前缀）。清单行只有 6 字段
  （nid/标题/作者/简介/封面/categoryID）；`category_id` 是赛道提示
  （0 常规/1 对话/3 征文短篇/4 沉浸式），**不是 form 真值**（E.28 只正向
  用 1/4）。
- **size 边界陷阱**：个别 tag（如 724）size=500 返回空、≤8 正常——首页
  空时引擎按 500→100→10 递减重试后再下结论（旧世代 ps=200 单档）。
- 缓存：进程内 TTL 缓存（引擎重启即清空；与官方榜单共享并发合并），
  key = `roster:{tag}:{page}`；TTL 按台账 `end` 日期判（未结束 24h /
  已结束 10 年——数据不变，用户 2026-11-22 裁定 / end 未知 24h）。
  缓存的是上游原始页；**本地 join 每次响应都做**（覆盖层/种子变化即时反映）。
- **本地 join**：种子内作品 `in_library=true` + form/favs/status/
  est_year/words（seed 口径；用户观测覆盖层从不进 form）；库外作品
  只带清单 6 字段——不伪造徽标（docs/12 红线）。
- **降级恒 200（无 502 墙）**：赛事无 tagId / 接口失效（新 API
  `errorCode≠200`、旧 API 裸 `status≠200`、结构缺失、响应体畸形）/ 上游
  抓取失败 → 引擎回落库内子集（同代分位序、cap 2000），响应
  `source="degraded"` + `note`（roster 赛事「官方清单暂不可用…」，award
  赛事「获奖名单暂不可用…」）；UI 顶部提示条同步换词。失效响应不入缓存，
  下次打开重试（不重试风暴）。
- 清单顺序保持官方返回序；v1 无排序控件（用户 2026-11-21 定案）。
- 库外条目点击复用搜索页链路：UI 推 `/book/{nid}`，详情页覆盖层按需抓
  详情 + 自动收录（discovered），不写 seed。

200：

```json
{ "contest": "十三征", "division": "长篇", "page": 1, "pages": 3,
  "total_estimate": 1500, "list_kind": "roster",
  "source": "official",
  "items": [ { "nid": 713638, "title": "Re：如果成为神明",
               "author": "某NoName", "intro": "…",
               "cover": "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2024/08/….jpg",
               "category_id": 3, "in_library": true, "form": "short",
               "favs": 412, "status": "连载中",
               "est_year": 2024, "words": 38000 } ] }
```

`list_kind` = `"roster"` | `"award"`（一/二/三征获奖名单）；降级响应不带
（UI 从档案组取）。降级响应同形：`source="degraded"`、`note`（如「无官方
清单，仅显示库内作品」）、`page`/`pages` 恒 1，items 为库内子集（无
intro/category_id），无 `total_estimate`。
- `total_estimate` = pages × 实际页大小（官方清单规模近似；末页不满时
  误差至多一页——用户 2026-11-22 裁定：近似即可，不多发请求取精确值）；
  UI 清单页优先用台账的精确条数显示「官方清单 N 条」，台账缺数才回落
  「官方清单约 N 条」。**文案统一「官方清单」，不写「官方参赛/约 N 篇参赛」**——
  这个数数的是清单接口返回的条目。

### GET /strata/booklists?page=（**已实现**，2026-11-23 官方书单）

官方书单列表一窗（docs/booklist-in-app.md）。官方 API **无枚举动作**
（裸 `/bookList` 探针 404），引擎每窗探 10 个连续书单号、**逐个**走共享
限速器（1s/号，首窗 ≈10 秒）；每号原始响应进程内 24h 缓存
（key = `booklist:{id}`，与官方榜单共享并发合并——书单会更新，24h 是
上限），当日再访秒回。无效号（data 缺失）确定性丢弃；窗口有效数 < 10
= 到底（temp/novly 在真实 id 空间验证的语义）。

- 400 `invalid_argument`：`page` 非 ≥1 整数。
- 502 `upstream_error`：上游抓取失败（UI 重试；失效响应不入缓存）。
  超时边界三层（2026-11-23 真机转圈修复）：逐探测 15s / 窗口 deadline
  30s（详情 25s、推荐 20s）/ UI 45s——详见 docs/booklist-in-app.md §深化 5。
- 书单官方累计值（mark_num/recommend_num）纯展示（docs/12 红线）。

200：

```json
{ "page": 1, "done": false,
  "items": [ { "id": 1, "title": "玄幻无敌养成，女徒弟孝心变质",
               "summary": "…", "author": "菠萝包编辑部",
               "avatar": "https://rss.sfacg.com/….jpg", "vip": false,
               "mark_num": 2170, "recommend_num": 399, "novel_num": 6,
               "updated": "2021-05-11" } ] }
```

`done=true` = 已到底（页不满）；UI 停止加载下一页。

### GET /strata/booklists/recommend?count=（**已实现**，2026-11-23 首页推荐行）

以 **UTC 日期为种子**随机抽 count（默认 3、范围 1..10）个官方书单
（docs/booklist-in-app.md §深化）：seed = `int(yyyymmdd)`，当日稳定——
同一批号全天一致，再访走 24h 缓存秒回；无效号自动补抽（上限 3×count），
整批失效则返回短列表/空 `items`（永不报错——增益区块语义）。每号与
列表/详情共享 `booklist:{id}` 缓存。

```json
{ "items": [ { "id": 42, "title": "…", "author": "…",
               "mark_num": 800, "recommend_num": 120, "novel_num": 18,
               "updated": "2025-06-01" } ] }
```

UI：首页长篇 tab「书单推荐」横排文本卡（#id + 标题 + N 部作品 + 作者），
点击进 `/booklists/:id`；加载失败/空结果整行隐藏。

### GET /strata/booklists/:id/novels（**已实现**，2026-11-23 官方书单）

书单详情：元数据 + 作品列表（两个上游请求，各缓存 24h，key
`booklist:{id}` / `booklist:{id}:novel`）+ 本地 join（`BooksByNIDs`）：
库内作品 `in_library=true` + `form`；库外只带官方字段（不伪造徽标，
docs/12 红线）。作品列表保持官方返回序，无排序控制、无分页。

- 400 `invalid_argument`：`id` 非正整数。
- 404 `not_found`：书单号不存在（data 缺失）。
- 502 `upstream_error`：上游抓取失败。
- 作品官方累计值（words/clicks/favs）纯展示（docs/12 红线）；库外作品
  点击走 rankSeed 收录链路（同 roster 行）。

200：

```json
{ "booklist": { "id": 1, "title": "…", "summary": "…",
                "author": "菠萝包编辑部", "vip": false,
                "novel_num": 6, "updated": "2021-05-11" },
  "items": [ { "nid": 292332, "title": "我的女徒弟们都是未来诸天大佬",
               "author": "一白均", "cover": "https://rss.sfacg.com/….jpg",
               "type": "古风", "words": 2748798, "clicks": 38820520,
               "favs": 166979, "finish": true, "note": "推荐语…",
               "in_library": true, "form": "long" } ] }
```

UI：首页长篇 tab 宫格第一格「分类」→「书单」（2026-11-23 裁定：经典
榜单筛选面板已有题材选择，分类路由冗余）；`/browse?mode=category` 路由
保留、首页不再提供入口。

## 草案（Phase 3/4 实现，未落地前 UI 不得依赖）

### GET /strata/search?q=&limit=（**已实现**）

L1 本地搜索：种子库内 `title`/`author` LIKE 匹配（v1 无 FTS5）。
**nid 精确查找**：`q` 为 **`#` 前缀 + 纯数字**（如 `#123`）时按 `nid = q` 精确匹配（种子 +
已收录并集；1–3 位数字仍走关键词——「7」是词不是 id；int64 溢出同样落回
关键词）。未命中返回空 `items`，UI 渲染「未收录」行 → 点击进详情页收录
链路。`q` 必填（非空），`limit` 同分页规则。**每次成功搜索自动写入搜索历史**
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

新书/新作榜（**已实现**）：近两代（`est_year >= gen_max-1`）按
`favs DESC, est_date DESC, nid` 排序（E.30：分位列退役，跨代近似），
`is_licensed=0`。

```json
{
  "meta": { "kind": "new", "pool": "seed", "ordering": "favs",
            "content_end": "…", "min_est_year": 2024, "limit": 50,
            "licensed_excluded": true },
  "items": [ <RankItem 同 favs 榜> ]
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
| `/strata/watchlist/:nid` | POST（**已实现**）   | 加入，body `{active?, role?}`；active=false = 原「加入书架」，role=peer = 同期对照（缺省 self）；满 100 本上限 → 409 `watchlist_full` |
| `/strata/watchlist/:nid` | PUT（**已实现**）    | 切换追踪 / 切换 role，body `{active?, role?}`（至少一个，docs/07 §1：role 可改、一列 UPDATE、历史曲线连续） |
| `/strata/watchlist/:nid` | DELETE（**已实现**） | 移除（观测历史保留）                                                             |

只写 `user.db`；与种子的关联**只用 `nid`**（rowid 每次种子发布都会重排）。

### GET /strata/author-books?author=&limit=&offset=&order=（**已实现**）

作者页时间轴的作品列表（`docs/author-profile-on-demand` §1）：**纯本地**，无网络。
`author` 必填（显示名精确匹配——seed 作者名为规范字符串）；`limit` 默认 20；
`offset` 非负整数；`order` = `newest`（默认，`est_date DESC`）| `oldest`
（`est_date ASC`，作者页排序按钮切换）。两个方向定年 0001 回填书都沉底，
nid 同向跟随。未知作者返回空列表，不是错误。items 为标准 RankItem，**额外带
`est_date`（YYYY-MM-DD，时间轴用；旧端点不返回此字段，RankItem 侧为可选
字段）**。（E.30：原额外字段 `fav_pctl` 退役——分位列已不在种子，作者页代表作改各
form favs Top-1，docs/17 §3）。meta.ordering 回显实际排序
（`est_date_desc` / `est_date_asc`）。

```json
{ "meta": { "pool": "seed", "ordering": "est_date_desc", "author": "无聊看看天" },
  "items": [ { "nid": 48704, "title": "英雄再临(英雄？我早就不当了)",
               "author": "无聊看看天", "est_year": 2010,
               "est_date": "2010-06-12", "favs": 7881, ... } ] }
```

### GET /strata/related?nid=&limit=（**已实现**，2026-11-26）

详情页「相关推荐」（算法与取舍见 `docs/related-books.md` v4.1）：**纯本地**，只读 seed，
无网络、断网可用。`nid` 必填正整数（锚点=当前书，可以是库外书或授权书）；
`limit` 默认 8、上限 20，越界或非法一律 400 `invalid_argument`。

硬门槛（任一不满足即不进候选）：`is_licensed=0`、有封面（`covers` ∪ `cover_url`）、
`form = 锚点 form`、`nid ≠ 锚点`、`author ≠ 锚点作者`（同作者交给 `/author-books` 轨）、
质量证据（long/dialogue 要 `cqs` 非空且落在 `cps` 20–80 中层带；其余 form 要 `pr` 非空且
`favs ≥ 10`，`favs` 只作准入不作排序键）。召回按 A′（同 genre + |Δyear|≤3 + 强标签重叠）→
B（同 genre + ≤5，按全标签重叠数打散）→ C′（跨 genre + ≤3 + 强标签）→ 同 form 口碑末档
逐级降档；锚点含 df ≤ 100 的极稀疏强标签时世代窗口放宽到 ±8，锚点 `est_year < 2000` 时
A′/C′ 关闭。档内先按最稀有强标签分层、多标签轮流出一本，再按口碑 DESC（`cqs` 或
平滑 `pr_s`）、nid ASC。累计值 `clicks/favs/praises` 只 SELECT 展示、绝不参与排序
（docs/12 §3.2 红线）。

`meta.tier` = 贡献了条目的最后一档（`a`/`b`/`c`/`fallback`，无条目为 `none`）、
`meta.ordering` = 实际排序键（`cqs`/`pr`），两者只供诊断，UI 不展示指标名。
锚点查不到（无 nid 行、无 form）→ `items: []` + `tier: "none"`，不是错误；UI 整行隐藏。

```json
{ "meta": { "pool": "seed", "form": "long", "genre": "魔幻",
            "tier": "a", "ordering": "cqs" },
  "items": [ { "nid": 1001, "title": "Long A", "author": "Author A",
               "genre": "魔幻", "est_year": 2010, "form": "long",
               "cover_url": "2010/1/x.jpg", "favs": 500, ... } ] }
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
  "offlibrary": [ { "nid": 9001, "title": "……" } ],
  "verdict": "ok", "observed_at": 1763570000, "source": "live" }
```

- `verdict`：`ok` | `dead`（源书下架，移动版三态判定）| `error`（抓取失败无
  数据）。UI 降级：error 时头部回退本地作者名，书目列表照常。
- `author_intro` 为 null/空是**正常值**（作者没写）——UI 不得伪造、不得拿
  书简介顶替。
- `works` = 移动版 `.book_Author` 作品集（**不截断，作者全部作品**；PC 版
  作品集截断、不作书目来源——用户 2026-11-22 裁定，
  `docs/author-profile-on-demand` §2.1）。`offlibrary` = `works` −
  `seed.books`（引擎实时差集，保持页面序）：作者页「其他作品」区块数据源，
  点击走 rankSeed 预写 → 详情页收录链路。
- 缓存：`user.db author_profiles`（schema v8，键 = casefold 显示名），ok 行
  7 天 / dead 行 1 天 TTL；缓存命中时 `source=cache`，`works` 回放抓取时存的
  官方全量（v8 起不再为空），`offlibrary` 仍对当前 seed 实时差集。只写
  user.db，不碰 seed.db。
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

# 比赛 API 端内接入：工程可行性分析

> **定位**：征文清单 API 接入 `app/` 的工程可行性分析——端点/字段/限流/降级/工作量，是 display 文档「工程交接」节的落地输入。
> **状态**：工程侧分析（2026-11-21），基于引擎与 UI 现状代码核实；分析侧实证（端点档案、tagId 地图、字段权威、展示定案）以对应文档为准，本文只给指针、不复制数字。真待裁定已全部拍板（2026-11-21，裁定记录见 `contest-display-in-app.md`）；路径 A 已落地，路径 B（P1）实施中。
> **权威范围**：本文唯一维护端内接入点映射、风险清单与工作量估算；不裁定展示口径（display 权威）、tagId 台账（harvest 权威）、字段口径（fields 权威）。
> **口径**：工作量估算随代码演进失效，实施前重估；引用分析侧数字一律以来源文档当前值为准。
> **更新日期**：2026-11-21。

## 结论

1. **可行，风险低，且端内基础设施已全部就位**：全局限速器、fetcher 模式（Fetch + Parse + golden test）、
   缓存包装器、库外书覆盖层、库外书自动收录——接清单 API 不建任何新网络层，
   净增 = 1 个 fetcher 文件 + 1 张缓存表 + 2 个只读/按需端点 + 1 个 UI 页。
2. **两条通路成本差大，建议拆成两个独立可交付阶段**：
   **路径 A 赛事档案页（本地视图，零请求）** 是纯聚合，可行性确定；
   **路径 B 参赛清单浏览页（按需 API）** 是唯一涉及网络的，其最大约束不是接口
   （已实证、无风控迹象）而是 **tagId 地图随新赛事膨胀**——新赛事未摸到 tagId 前只能降级本地，
   这是常态而非异常，且不影响路径 A。
3. **前置依赖一项**：假短/中篇剔除规则（`fake-complete-short-medium.md`，分析侧已裁定、尚未实施）
   须在档案页上线前生效，否则「代表作」仍是污染头部。这是路径 A 唯一的硬依赖。
4. **红线全部可满足**（docs/12 量化红线 + display 文档「不做」清单）：复用全局限速不建新限速器；
   不造新指标不进推荐打分；按需请求 + 按页缓存不做全库批量；库外书只读不写种子；
   库内排序用 `fav_pctl` 同代分位，累计原始值不进 ORDER BY。

## 事实：端内现状（2026-11-21 代码核实）

### 1. seed 层已有 contest 数据（零请求可用）

- `seed.books.contest`：单值 TEXT，赛道信息编码在字符串里（「七征长篇」），
  取值枚举与占比见 display 文档三层数据表（本文不复制）。
- 引擎已有归一化：`NormalizeContest`（仅 N征 系列剥赛道后缀，用户 2026-11-21 裁定口径）。
- 引擎已有 contest 消费端：`RankingFavs`（contest=1 任意征文 / 否则赛事或其任一赛道，
  `contestMatchClause`）、`ClassicBooks`（筛选面板维度）、`ipGroups`/`ipBooks`（ip_collab 按 contest 聚合）；
  `Book.Contest`/`RankItem.Contest` 字段已回传端上。
- UI 已有消费端：`contestGroupsProvider`（按 form 聚合 → 短篇 tab 比赛 chip）、`ipGroupsProvider`、
  `contestChipLabel`/`contestIpLabel`（紧凑标签推导）。
- **推论**：赛事列表、每赛事库内参赛书、form 分布、同代分位排序的代表作品——本地聚合即得，
  与「用已有数据长出视图」的既有路线（`app/docs/14-discovery-views.md`）一致。

### 2. 爬虫基础设施（路径 B 的落点）

| 关注点 | 现有设施（已核实） | 路径 B 净增 |
| --- | --- | --- |
| 限速 | `crawl.Limiter`：全局 1s 间隔、fg/bg 双队列、队列上限 8、溢出即丢；`api.New` 已装配单例 | **0**——清单请求 = 用户触发 = foreground lane；翻页串行（`Submit` 阻塞）天然符合「按页串行、失败即跳过」契约 |
| fetcher 模式 | `FetchXxx(ctx, client, s.limiter, …, foreground)` + 纯函数 `ParseXxx` + golden test（`crawl/testdata/` 每 fetcher 均有 fixture） | `crawl/roster.go` 一个文件：`FetchRoster` + `ParseRosterNew`/`ParseRosterOld`（JSON 解析，比 detail 的 HTML 简单）；fixture 直接取自 fields 文档的两段真实响应样例 |
| 缓存 | `officialRanksServed(ctx, key, ttl, fn)` 包装器（key + TTL 读时判 + in-flight 合并）+ `official_ranks_cache` 表 | 缓存 key `roster:{tag}:{gen}:{page}`；TTL 双档与官方榜单同构——**活跃赛事 24h / 已结束赛事 365d**（历史清单不再变化） |
| 库外书 | `book_meta`（可写覆盖层，含 source）、`discovered`（自动收录）、详情页覆盖层链路 | **0**——清单库外书只读展示（标题/作者/简介/封面），不写种子、不伪造 form/分位、不用 `categoryID` 顶替 |
| 降级先例 | App API 失败静默回退 HTML 基线（不重试、不报错给用户） | 同款形态：errorCode≠200 或结构缺失 → 接口失效判定 → 回落本地子集，不重试风暴、不清空已显示值 |

## 事实：两条通路

### 路径 A：赛事档案页（本地视图，零请求）

- **数据**：seed `contest` 枚举 → 赛事列表；每赛事参赛书 + form 分布 + 代表作品
  （`fav_pctl` 同代分位、按 long/medium/short/dialogue 分组独立排序——混排会被长篇流量淹没，display 文档口径）。
- **引擎**：约 1–2 个只读端点（赛事列表；单赛事参赛书按 form 分组）。聚合模式 `ipGroups` 已有，主要工作是端点封装。
- **UI**：赛事列表页 + 一届一页（赛道列表、参赛规模、代表作品分组、获奖信息读种子获奖表）。
- **日期**：从 `analysis/references/contest-editions.md` 导出内置静态表（单一真源，随发版更新，
  早期届次无精确日就只显示届次/年份，不编造）。
- **硬依赖**：假短/中篇剔除规则上线（见结论 3）。
- **工作量**：引擎 ~1 天 + UI 1–2 天 + 前置规则实施 0.5–1 天（含验证「代表作」头部已净）。
- **无网络面**：无限速、无降级问题，可行性确定。

### 路径 B：参赛清单浏览页（按需 API）

**端点与字段**（分析侧实证，权威见 `contest-roster-fields.md` / `contest-roster-harvest.md`）：

| | 新 SPA（2023 起） | 旧 H5（2018–2022） |
| --- | --- | --- |
| 端点 | `GET /api/essay/getNovels?tagIds={t}&page={n}&size≤500` | `GET /ajax/ashx/Common.ashx?op=getNovelsByTag&tagId={t}&ps≤200&pi{0基}` |
| 结构 | `{status:{errorCode,msg}, data:{totalPage, novels[]}}` | `{status(裸 int), novels[], totalPage}` |
| 条目 | 6 字段小写（`novelID/…`），cover 完整 URL | 6 字段首字母大写（`NovelID/…`），cover 路径片段（需拼 CDN 前缀） |

清单**不含**成绩/定年/获奖/名次/赛道中文名——成绩层只能靠库内 join（覆盖层优先、种子兜底），
库外书只展示清单自带字段。补采覆盖价值数字见 harvest 文档（本文不复制）。

**tagId 地图 = 内置静态配置**（14 tag 台账从 harvest 文档导出，逐 tag 记端点世代 + page 起始口径；
每办一届新增一批号、跨届不复用、sandbox/pages 异号——新赛事 tagId 未入库前该赛事降级本地视图，
这是设计内常态，随种子发版补齐）。

**解析四规则**（fields 文档）：字段名两套大小写双兼容；tagId 按 `location.host` 取生产值
（静态表直接存生产值）；`categoryID` 只作赛道提示不作 form 真值；`intro` 是作品简介非作者 intro。

**风险清单（均有既有降级兜底）**：

| 风险 | 兜底 |
| --- | --- |
| `size` 边界陷阱（个别 tag `size=500` 返回空、小 size 正常） | 判空先 `size=1` 探活，降 size 重试 |
| `page` 起始随版本变 | 静态表逐 tag 记录起始口径，以页面实际传参为准 |
| 活动页改版/下线（历史赛事清单拿不到 = 常态） | 降级本地子集 + 「仅库内作品，清单不完整」标注；不清空已显示值 |
| 接口字段/结构漂移 | 双世代解析器 + 结构缺失 → 失效判定回落本地，不猜字段 |
| tagId 地图滞后（新赛事） | 新赛事仅本地视图，档案页（路径 A）不受影响 |
| 限速风控 | 复用 1s 全局限速 + foreground 优先 + 队列溢出丢弃；分析侧同契约无风控迹象 |

**工作量**：引擎 1–2 天（fetcher + 缓存表 + 端点 + 双解析器 golden test）+ UI 2 天
（赛事 → 赛道 → 分页浏览页，库内/库外条目区分与徽标规则）。

## 边界与红线合规

- 只取清单元数据：不取正文、不登录、不带用户 cookie（display 文档请求契约，端点天然满足）。
- 不做全库后台批量抓清单：按需（用户打开浏览页）+ 按页缓存 + 历史 365d TTL。
- 不造新指标：展示层只消费已有 `form`/`fav_pctl`/`favs`；不进推荐打分白名单（docs/12 §3.2）。
- 库外书不写种子：清单通路对 seed.db 只读；「提级为常规覆盖更新通路（写补采池）」是独立裁定项，不在本分析范围内默认。
- 跨届横比只用 `fav_pctl`（同代分位），不用累计 favs 混书龄横比（display 文档口径）。

## 真待裁定（均已拍板 2026-11-21，裁定记录见 `contest-display-in-app.md`；本文不执行）

1. **P0 → P1 顺序确认**：先落路径 A 赛事档案页（零请求零依赖），再做路径 B 清单浏览页。
2. **赛事元数据维护方式**：`analysis/references/contest-editions.md` 导出内置静态表随发版更新，
   还是另有权威来源。
3. **库外书点击行为**：允许点击触发详情抓取（消耗请求、可补成绩）还是仅展示不可点。
4. **是否提级为常规覆盖更新通路**：只展示 / 也写补采池，与更新频率。
5. **前置规则时点**：假短/中篇剔除规则（`seed_policy.py`）实施与验证排期。

## 交叉引用

- **展示设计 / 三层数据 / 降级表**：`contest-display-in-app.md`（权威）
- **端点参数 / 字段 / 真实样例 / 获奖四代形态**：`contest-roster-fields.md`（权威）
- **tagId 台账 / URL 实证 / 补采覆盖数字 / 试号记录**：`contest-roster-harvest.md`（唯一权威）
- **URL 形态演进 / 四季节奏 / tagId 分配规律**：`contest-url-api-patterns.md`
- **获奖入种口径**：`award-winners-as-seed-source.md`；**赛事日期**：`analysis/references/contest-editions.md`
- **假短/中篇治理（路径 A 硬依赖）**：`fake-complete-short-medium.md`
- **引擎抓取基础设施**：`app/engine/internal/crawl/`（limiter/detail/ranks + testdata golden fixtures）
- **双模式量化红线**：`app/docs/12-dual-mode.md`

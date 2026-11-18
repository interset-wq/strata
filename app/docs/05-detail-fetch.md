# APP 设计文档 05：详情页抓取与写回

> **定案 v1.0**。口径依据：`docs/sfacg-endpoints.md` §4/§4.4/§6/§8/§9/§11.5、
> `docs/sfacg-app-api.md`。触发与限速契约见 01 §3；写回表结构见 02 §3。

## 0. 结论

详情页抓取是 v1 唯一的增量通路，抓"用户打开的这一本的当前值"；端上只写 `user.db`，
`seed.db` 永远只读，按 `nid` 关联、`observed_at` 取较新者。

| 结论 |
| --- |
| 三条通路：**移动版 HTML = 稳定基线（默认）**；PC 版 = 补充（限观测列表点击追踪）；App API = 可选增强（失效即降级） |
| **全字段刷新**：详情页触发的每次成功抓取，响应内所有可解析字段一次落库——成绩进 `observations` 时序、书目属性进 `book_meta` 覆盖层、封面直链进 `covers`；UI 一律覆盖层优先、种子兜底，保证本地数据不落后 |
| 点击变化：PC 版量化 ±500 不可做；App API `viewTimes` 精确整数可做单书曲线；跨书点击变化榜不做（无曝光分母） |
| 本站状态码零信息量（无效 nid 返回 200），判活必须匹配否定文案或结构缺陷 |
| 三态分级写入：只有**存活**写观测；死亡/僵尸回落本地值不写 |
| 标签不抓（无写回目标）；评论与章节仅 `watchlist` 书抓 |
| `addTime` 不进定年**模型**（`log(nid)` 曲线不动）；命中 addTime 的书种子侧为 `est_conf=exact`、est_date 即官方值；端上写入 `book_meta.add_time`，展示「官方上架于 …」 |

## 1. 端点

| 维度 | 移动版 `m.sfacg.com/b/{nid}/` | PC 版 `book.sfacg.com/Novel/{nid}/` | App API `api.sfacg.com` |
| --- | --- | --- | --- |
| 定位 | **基线** | 补充 | 增强（可失效） |
| 体积 | 14.7 KB | 73.5 KB | 0.7 KB |
| favs/praises/words | `.book_interact li` 第 1/2 项、`.book_info3` | 同页有，解析更绕 | `markCount` / —（无点赞）/ `charCount` |
| status / updated_at | `.book_info div` / `.book_info3` | 同页 | `isFinish` / `lastUpdateTime`（ISO 8601） |
| clicks | **无** | `人气：11899.5万`（量化 ±500） | `viewTimes` 精确整数 |
| addTime / 章节 | 无 | 无 | `addTime` 秒级 / `chaps` 逐章（222–489 KB） |
| 稳定性 | web 端长期稳定 | web 端长期稳定 | 无契约，随时可能变 |

抓取口径可校验：nid=48704 种子 favs 281,034 / 详情页实测 281,988——差值即快照后真实增量。

**默认 1 个移动版请求**。PC 版仅在 `watchlist` 开启点击追踪时追加（点击绝对值画趋势）。
App API 规则：

- 默认不启用；失败（401/417/404/超时/结构变更）即静默回落移动版，不重试；
- 移动版必须始终可用，不得出现"只有 App API 能跑"的路径；
- 认证用 App 内置固定常量，不引入用户账号/cookie；
- **正文绝不取**（`/Chaps/{id}?expand=content` 实测 401/507，有权限也不取）；
- `addTime` 不改变定年模型；本书展示用官方值（`book_meta.add_time`），种子侧对应 `est_conf=exact` 档。

## 2. 解析（纯函数 + golden test）

移动版字段映射：

| 字段 | 位置 | 要点 |
| --- | --- | --- |
| `favs`/`praises` | `.book_interact li` 第 1/2 项 `<small>` | 去千分位；负数按僵尸判 |
| `words` | `.book_info3` | 剥「字」；0 视为缺失 |
| `status` | `.book_info div` | 取含「完结/连载」片段；当期态 |
| `updated_at` | `.book_info3` | `YY-MM-DD` 固定补 `20` 前缀 |
| 简介/封面 | `.book_bk_qs1` / `.book_info img[src]` | 协议相对 URL 补 `https:` |
| 打赏（第 3 项） | — | 无数字，不解析；页内月票项不解析——月票走 GetTicketNum 端点（§6，精确值） |

App API 无选择器解析，但三态判据不同：读 `status.httpCode`（200 存活 / 404 死亡 /
**417 或 401 = 通路不可用，不是书死了**）；`markCount`/`charCount` 缺失或非法 = 僵尸。
`point` 为官方废弃字段（App 不展示、值集中占位常量无区分度），**采集层直接丢弃**。

解析器签名 `parse_detail(html, url) -> Result<DetailState, ParseError>`：不碰网络/数据库/时钟。
fixture 每态一份真实 HTML，存 `app/engine/internal/crawl/testdata/`（`alive_48704` /
`dead_73900` / `zombie_4733`，来源与特征见该目录 README），由 `detail_fixture_test.go`
校验三态；`detail_test.go` 的内联最小 HTML 用例保留，验证判据本身。
站方改版：先改 fixture 与期望值 → 测试红 → 改解析器 → 绿，禁止反序。

### 三态判据（先判态，再解析）

```
响应到达（HTTP 状态码一律忽略）
 ├─ 含「小说不存在」(PC) / 「出错啦」(移动) → 死亡：不写观测，标「官方页面不存在」
 ├─ div.book_Catalog 下无 <a>（无阅读入口）→ 僵尸：不写观测，标「当前不可阅读」
 ├─ 数字非法（负收藏、异常全零）→ 僵尸：同上
 └─ 有入口 + 数字合法 → 存活 → 解析并写回
```

红线：不看状态码；不用体积阈值判活（僵尸与存活体积中位只差 35 B）；
不细究下架原因（声明是充分非必要条件，判据只能是缺陷检测）。
僵尸实证集中在 `nid ≤ 83,624`，不外推到高 id 段。

## 3. 写回

仅存活态。**全字段刷新原则：一次请求拿到的所有可用字段都必须落库，不能只取 favs，
也不能挑"看起来有用"的字段**——少写一个字段，本地数据就多旧一分。观测流水与
书目覆盖层分两次写入；同一 `(nid, observed_at)` 已存在时观测行不重复：

```sql
INSERT INTO observations(nid, observed_at, favs, praises, words, status, updated_at, source)
VALUES (?, ?, ?, ?, ?, ?, ?, 'detail');
-- clicks：仅订阅点击追踪抓 PC/App API 时同事务写；
-- short_comments / long_comments：仅作者工作台抓评论时；NULL=未抓，非 0

-- 最新书目元数据覆盖层（user.db），每次成功抓取整体 UPSERT。
-- 本次未返回的字段用 COALESCE 保留旧值（HTML 无 clicks，App API 无 praises/简介）。
INSERT INTO book_meta(nid, source, fetched_at, title, author, author_id,
  genre, type_id, price_type, status, cover_url, summary, words, favs, praises,
  clicks, updated_at, add_time, point, bg_banner, category_id, is_sensitive,
  allow_down)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(nid) DO UPDATE SET ...;
```

- 移动版 HTML：书名、作者、分类、签约状态、封面、简介、收藏、赞、字数、状态、
  更新时间全部解析并写入 `book_meta`；无 clicks，不伪造。
- 月票：存活态追加 `GetTicketNum.ashx`（1 B）写 `book_meta.tickets`；请求失败
  月票置 NULL，不影响其余字段落库。
- App API：`novelName/authorName/authorId/addTime/lastUpdateTime/markCount/
  viewTimes/charCount/point/isFinish/signStatus/typeId/categoryId/isSensitive/
  allowDown/novelCover/bgBanner` 全部写入；无 praises/简介，保留旧值。
- **UI 读取顺序：书目属性（书名/作者/分类/签约/封面/简介/字数/状态/更新时间）
  一律 `book_meta` 优先、`seed.books` 兜底**；成绩数值走 `observations` 最新观测。
  覆盖层有值就用覆盖层，时间标注见 §5——这是"本地数据不落后"的机制保证。
- `covers` 继续同步一份封面直链，兼容旧读路径；UI 优先读 `book_meta.cover_url`。
- `discovered` 仍只用于官方搜索命中、种子未录入的书；不覆盖 `book_meta`。
- **绝不写 `books`**：种子只读；写进去升级即丢、污染分位分母、与发布版本脱钩。
- `user_stats` 增量：`fav_delta_30d`（30 天前观测相减，不足则 NULL）、
  `click_delta_30d` 恒 NULL、`obs_count`+1、`first_seen`/`last_seen`。
  可从 `observations` 全量重算。涨幅榜样本不足时隐藏整榜。
- 主键 `(nid, observed_at)` 天然去重；保留 180 天按月 DELETE，不做 VACUUM。

## 4. 限速与失败

限速器全局单例（`engine/crawler`），与搜索共用：端点间隔 ≥1s 全局共享；详情页请求优先；
队列硬上限、溢出丢弃；同书并发合并。响应缺少任何已知结构（书名、`.book_interact`、
否定文案三者皆无）按"未知失败"处理，不当空数据、不写观测。

| 级别 | 情形 | 处理 |
| --- | --- | --- |
| F1 网络 | 超时/断连 | 回落本地值，不重试阻塞前台 |
| F2 限流 | 结构缺失疑似限流 | 回落本地值，退避由限速器管 |
| F3 死亡 | 否定文案 | 标注，不写观测 |
| F4 僵尸 | 无入口/数字非法 | 标注，不写观测 |
| F5 解析 | 选择器未命中 | 结构化 `ParseError`，本机日志 |

任何一级不清空已显示值、不显示空白；F3/F4 只标注当次、不持久化。

去重：同书 30 秒窗口只发一次，窗口内读本地值。

## 5. 数据时间标注

| 展示元素 | 取值 |
| --- | --- |
| 成绩数值 | 最新观测，无观测取种子 |
| 来源标签 | 「本地刷新于 YYYY-MM-DD HH:MM」/「种子快照 2026-05-03」（读 `seed_meta`，不硬编码） |
| 回落态 | 「官方页面当前不可读，显示上次记录」 |

禁止把种子值标成"当前"、回落值标成"实时"。观测榜成熟度：1 条观测只显当前值；
≥2 条但 <30 天显示"观测中"；≥30 天显示收藏涨幅；全书样本不足整榜隐藏。

## 6. 评论 / 标签 / 章节

| 维度 | 规则 |
| --- | --- |
| 评论 | `op=getcomment` 精确整数（须过滤 `CommentID=0` 置顶公告）；**仅 `watchlist` 书抓**，写 `observations` 两列；全库统计不可做，观测列表内时间序列可行 |
| 月票 | `GetTicketNum.ashx?nid=` 裸整数（`docs/sfacg-endpoints.md` §7.3）：**存活态详情抓取追加 1 次**（1 B），失败置 NULL 不阻塞；写入 `book_meta.tickets`。**当月值每月 1 日清零，跨月不可比**——只存当期、UI 标「本月」，不做月票时序与月票榜 |
| 标签 | 移动版无结构化标签、App API 不返回（仅 PC 版有）；`book_meta` 可挂 `tags` 列，待需求出现再抓，v1 不抓 |
| 章节 | 移动版目录页 168 KB 不抓；**App API `chaps` 仅 `watchlist` 书抓**（一次性快照）：逐章 `addTime`（更新热力图数据源）、`charCount`（正文口径）、VIP/废章/待审标记；落 `novel_chapters` 独立表，失败即回落 |
| 衍生作品 | `GET /adpworks/novelId/{id}`（`docs/sfacg-app-api.md` §3.4）一次 0.2 KB 得 `comicId`/`albumId`（`0`=无）。**存活态详情抓取追加此请求**，写入 `book_meta.comic_id/album_id`；`comic_id>0` 时再取一次 `/comics/{comic_id}` 的 `folderName` 存 `comic_folder`（拼 Web 入口用，1 次 0.5 KB）。**详情页据此显示直达入口**：`comic_id>0` → 「看漫画」，`album_id>0` → 「听有声」；`NULL`（未抓/失败）不显示、`0`（确认无改编）不显示。全站改编漫画 **<50 本**、有声 **≈150 本**，均少于 `featured` 620 本且高度重叠，**不适合作全库维度或推荐信号**。入口 URL 见 §6.1 |

### 6.1 直达入口 URL

| 类型 | URL 模板 | 状态（2026-11-18 实测） |
| --- | --- | --- |
| 漫画 | `http://manhua.sfacg.com/mh/{comic_folder}/` | 官方模板（`sfacg.com/catalog?tid=10` 分类页仍用此格式，`comic_folder` = `/comics/{id}.folderName`）。但该路径当前返回「页面找不到了」、`mh.sfacg.com` 返回 403——漫画 Web 端疑似下线或限区域。**照模板拼、打不开由浏览器兜底，不回退伪造 URL** |
| 有声 | 无 | 仅有 `albumId`，无 folderName；`book.sfacg.com/Album/{id}/`、`m.sfacg.com/a\|album\|audio/{id}/`、`sfacg.com/album\|audio/{id}/` 全部 404 / 「出错啦」。**暂不生成链接**，入口待官方深链确认后补 |

规则：只显示确认可拼的入口；不可拼的类别只标「有改编」不给链接（不给死链）。
URL 全部本地拼装、零额外请求；`comic_id>0` 但 `comic_folder` 为空（未取到）时入口隐藏，
下次刷新重试。

## 7. 不做

全库后台批量（订阅式除外）；一般读者抓 PC 版；跨书点击变化榜；一般读者抓评论；
抓标签；移动版目录页；写 `books`；死亡/僵尸写成 0 值观测；靠状态码判活；
按体积判活；细究下架原因；上传抓取结果/日志；App API 取代移动版基线；取正文；
`addTime` 整体替换定年模型；为抓取引入用户凭据；月票时序/月票榜（当月值
每月清零、时序断序，`book_meta.tickets` 只存当期）。

## 8. 待决

详情页日上限初值（建议 300 本/日）；30 秒去重窗口按实测调；`YY-MM-DD` 补世纪仅适用 2000 年代。

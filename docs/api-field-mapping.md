# App API 返回字段 ↔ 本项目数据字段：实测对应关系

> **性质**：全局契约文档。回答「App API 一次请求返回的字段，哪些是我们已有的、哪些是新的、
> 哪些看着像其实不能用」。与 [`sfacg-app-api.md`](./sfacg-app-api.md)（端点与字段字典）、
> [`metrics-definitions.md`](./metrics-definitions.md)（自定义指标口径）配套。
>
> **数据仅供参考（用户裁定 2026-11-20）**：本文所有计数、比例、样本量与误差都是**某次快照的
> 现算值**，会随抓取批次与数据集版本变化；**量级与字段关系可信，精确数字过期属正常，不必逐次
> 修订**，也禁止硬编码到代码。已知 API 覆盖不到的信息（如 `praises`/`contest`/`tags`/运营位，
> 以及 App 侧的真实展示）**以手机 App 为准**；拿不准的直接问维护者，不要靠现有 API 硬推。
>
> **快照背景**：`analysis/out/app_api_novels.jsonl` 约 11.4 万条（2026-11-16/17 抓取），
> 与 `analysis/out/novels.csv`（内容上界 2026-05-03）按 `nid` 内连接，配对约 11 万本；
> 样本只覆盖 `tid=21` 魔幻、`tid=22` 玄幻两类，九类枚举完整性由端点档案佐证，非全样本验证。

---

## 0. 一句话结论

**18 个业务字段 = 1 个主键 + 11 个同义可刷新（含 `bgBanner` → `featured` 布尔化）+ 1 个旁证
（`addTime`）+ 2 个新维度（`authorId`/`categoryId`）+ 3 个无用（`point` 废弃占位分、
`isSensitive` 敏感内容强制下架故本库不会命中、`allowDown` 全站书籍恒禁止下载）。
App 不返回 `praises`/`contest`/`tags`，因此赞藏比 `pr` 与分位列无法靠这次刷新重建——
这是「用 API 翻新快照」的硬边界。**

---

## 1. 逐字段对照表

`novels.csv` = 分析主表 15 列；`books` = 种子表 28 列（v3 加 `form`/`lqs`/`lqs_pctl`/`vel_pctl`）。

| App 字段 | 本项目对应 | 关系判定 | 实测证据（110,370 对） | 刷新可行性 |
|---|---|---|---|---|
| `novelId` | `id` / `books.nid` | **同义**（主键） | 配对键，100% 相等 | — |
| `novelName` | `title` | **同义** | 直接取用 | ✅ 可 |
| `authorName` | `author` | **同义**（显示名） | 直接取用；显示名可改，身份看 `authorId` | ✅ 可 |
| `authorId` | `dataset/author_ids.jsonl` | **新维度（已入库）** | 账号唯一身份，大小写不敏感、空格敏感 | ✅ 已存，不必再取 |
| `addTime` | `est_date`（旁证） | **不同口径** | 与 `est_date` 绝对误差中位 **1.3 天**、P90 **7.0 天**、有偏中位 **+0.5 天**（281 锚点曲线） | ⚠️ 只作旁证，不替换 nid 定年 |
| `lastUpdateTime` | `updated_at` | **同义** | **98.9% 完全相等**，100% API ≥ CSV（时点晚半年） | ✅ 可（当期值，只进 user.db） |
| `markCount` | `favs` | **同义** | Spearman **0.9987**，80.8% 完全相等，85.1% API ≥ CSV | ✅ 可（关键刷新字段） |
| `viewTimes` | `clicks` | **同义** | Spearman **0.9987**，62.5% 相等，99.96% ≥（45 本反向） | ✅ 可，但见 §4 累计不可比 |
| `charCount` | `words` | **同义** | Spearman **0.9986**，98.7% 相等，99.8% ≥ | ✅ 可 |
| `point` | — | **🗑 废弃占位分** | App 端不展示（刷差评问题，作者要求删除）；2020 年后 **90.9% 为 6.0**（2021+ 为 93.5%）、5.0 仅 2.0%；老书残留 9.x/10.0；与 `pr` 的 Spearman **仅 0.1626** | ❌ 采集层丢弃，不入库、不展示、不计算 |
| `isFinish` | `status` | **同义**（布尔↔文本） | 383 本冲突（0.35%），均为半年间状态翻转 | ✅ 可，按 `True→已完结` 映射 |
| `signStatus` | `price_type` | **同义** | VIP→VIP 3,572、普通→免费 100,090、签约→签约 6,660；漂移 48 本 | ✅ 可，映射表见 §2 |
| `typeId` | `genre` | **同义**（id↔文本） | 21→魔幻 88,528、22→玄幻 25,852；1 条 tid=9 异常 | ✅ 可 |
| `categoryId` | `form`（产品线标记） | **新维度（形态，非题材）** | **0=常规 / 1=对话小说 / 3=短篇 / 4=沉浸式互动小说**；7,227 本 DOM 真值交叉：cat=1 的 533 本**全对话零散文**、cat=0 的 6,649 本**全散文零对话**、cat=4 的 5 本全为互动小说；征文名佐证（cat=1 清一色「N征对话小说」、cat=3 清一色「N征短篇」）。**与 genre/typeId 不同义**：cat=1 跨 9 个 genre 出现、同 genre 内多 cat 并存 | 🆕 形态金标，见 §3.4 |
| `isSensitive` | — | **🗑 无用字段** | 敏感标记内容会被**强制下架**，能进入本库的书不会被命中；对本库无判别力 | ❌ 不采集、不入库、不使用 |
| `allowDown` | — | **🗑 无用字段（历史遗留）** | 所有书籍本身就**禁止下载**，无论该字段取何值结论都不变，无实际意义 | ❌ 不采集、不入库、不使用 |
| `novelCover` | `cover_url` | **同义**（URL↔相对路径） | 去前缀后 **92.68%** 一致（CSV 有封面的 53,628 本），7.32% 为半年间换图；**配对里 CSV 缺封面的 56,742 本 API 全有** | ✅ 可，须剥离 URL 前缀（§2） |
| `bgBanner` | `featured` | **同义**（非空→`=1`） | 横幅图 URL，仅 **0.31%**（351 本）非空；形如 `…/beitouNew/cut/{nid}.jpg?TOKEN`。**URL 主体可由 nid 拼 CDN 前缀得到，故本项目只存布尔** `featured=1`（报告 01：其封面时间戳偏差中位 +338 天） | ✅ 可，非空即置 `featured=1` |

**汇总**：1 主键 + 11 同义 + 1 旁证 + 2 新维度 + 3 无用（`point`/`isSensitive`/`allowDown`）。

---

## 2. 值映射细则（覆盖前必读）

| 映射 | 规则 | 注意 |
|---|---|---|
| `isFinish` → `status` | `True`→`已完结`，`False`→`连载中` | 383 本冲突是快照后完结状态翻转；刷新会改变 `status` 的历史语义（见 §4） |
| `signStatus` → `price_type` | `VIP`→`VIP`；`签约`→`签约`；`普通`→`免费` | 48 本漂移（普通→VIP 26、VIP→签约 9 等），属签约状态变化 |
| `typeId` → `genre` | 21 魔幻 / 22 玄幻 / 23 古风 / 24 科幻 / 25 校园 / 26 都市 / 27 游戏 / 28 同人 / 29 悬疑 | 与 CSV 九类一一对应；样本只含前两类 |
| `novelCover` → `cover_url` | 剥离前缀 `https://rss.sfacg.com/web/novel/images/NovelCover/Big/` | CSV 存相对路径（如 `2025/12/uuid.jpg`），API 返回完整 URL；不剥离会 0% 匹配 |
| `categoryId` → 形态标记 | 0=常规 / 1=对话 / 3=短篇 / 4=互动 | 是**产品线/形态**而非题材，不可再当「同人标记」用；与 `typeId/genre` 正交，九类 genre 都出现 cat=1。映射细目与反证见 §3.4 |
| `bgBanner` → `featured` | 非空 → `=1` | URL 主体 `…/beitouNew/cut/{nid}.jpg` 可由 nid 拼 CDN 前缀得到，故只存布尔、不存 URL（token 会变）；呼应报告 01 的运营时间结论 |

---

## 3. 两组「看着像、不能用」的字段 + 一组「同义但只存布尔」

### 3.1 `point` ≠ `pr`（最易误用）

- 本项目 `pr` = `praises / favs`（**赞藏比**，详见 [`metrics-definitions.md`](./metrics-definitions.md)），
  App 的 `point` 是 0–10 评分，且 App 端早已不展示。
- 110,370 对样本 Spearman 仅 **0.1626**——几乎无关。原档案 §3.1 写 `point → pr` 是错的，已修正。
- 值高度集中在占位常量 `6.0`：2020 年后占 90.9%（2021+ 为 93.5%），`5.0` 仅 2.0%；
  2019 年前老书才残留大量 9.x/10.0（2018 年前 10.0 占 32.2%）。无区分度。
- App **不返回 `praises`**，所以刷新 `favs` 后 `pr` 的分子仍是旧值，`pr` 会失真（见 §4）。

### 3.2 `bgBanner` 就是 `featured`（同义，只存布尔）

- `featured=1` 表示封面曾用于 banner（报告 01）；它与 App 的 `bgBanner` 非空**是同一件事**，
  上一版写「❌ 不同义、不入库」是误判，已按维护者口径改回。
- `bgBanner` 只有 0.31% 非空，形如 `https://rss.sfacg.com/web/novel/images/images/beitouNew/cut/{nid}.jpg?TOKEN`。
  **URL 主体 `…/beitouNew/cut/{nid}.jpg` 可由 nid 拼 CDN 前缀直接得到**，token 部分会变、无保存价值；
  因此本项目只存一个布尔 `featured`（非空→`=1`），而不是整条 URL——这正是用布尔而非字符串表示的原因。

### 3.3 `addTime` 不作定年替换

- 与 `est_date` 绝对误差中位 **1.3 天**、P90 **7.0 天**、有偏中位 **+0.5 天**——精度很高
  （E.15 把定年锚点从 104 扩到 281 后，旧档案的 2.1 天 / P90 11 天已过期）。
- **在 app 内可以更新 user.db 的时间**（当期值写进本地库，供详情页展示）。
- 但项目定案：nid 定年体系是大量分析与 App 设计的基础，**不因 `addTime` 改定年/改 `books`**。
  它只作锚点旁证（核验流程见报告中定年档案）。

### 3.4 `categoryId` 是形态标记，不是题材（2026-11-20 实测定案）

> 校准脚本 `analysis/probe_category_id.py`（`--fetch` 可从每个 genre 分层重抓）。
> 本节是用户要求「多找几本书验证、确定真实语义」的结果；原猜测「cate 和 genre 同义」被数据否证。

**真实语义**（API 全快照 114,381 本 + 9 个 genre 各 8 本分层抽样 + DOM 真值 7,227 本）：

| 值 | 语义 | 决定性证据 |
|---|---|---|
| `0` | 常规（散文长篇为主） | DOM 真值 6,649 本**全部 prose，零 dialogue** |
| `1` | 对话小说 | DOM 真值 533 本**全部 dialogue，零散文**；有征书的征文名清一色「九征/十征对话小说」「征文大赛对话小说组」 |
| `3` | 短篇 | 有征书清一色「N征短篇」「超新星杯短篇大赛」；字数 <2 万占 78% |
| `4` | 沉浸式互动小说 | 5 本 DOM 真值全 dialogue，预读区均为「全新的沉浸式互动小说…只能在APP上观看」；签约 39/40、2024+ 才出现 |

**与 `genre/typeId` 不是同义词**（用户原猜测）：`cat=1` 在九个 genre 里都出现，同一个 genre 内
`cat=0/1/3/4` 并存——`categoryId` 是**产品线/形态**维度，`typeId` 才是题材。抽样交叉表见探针输出。

**用途**：这是 App 侧直接给出的形态金标（比本地 `forms.classify` 的形态估计可靠），
但本项目种子已 100% DOM 真值、且用户裁定 form 侧不再做精度工程，故**不据此改判据/种子**；
仅作为「App → 本地字段」的权威对照记录。取值分布随版本变化（数字仅供参考）。

---

## 4. 写回的硬约束：能刷新的字段，有些不能「就地覆盖」

一次请求能拿回当期值，不等于能直接写回 `books`——三个派生口径会被打破：

1. **分位列**：`fav_pctl/click_pctl/praise_pctl/pr/pctl_pr` 是在**完整 universe
   （241,864 行）构建期按世代算出的**，种子只是其中 **18,656 行**子集（18,609 非授权 + 47 授权）。
   只刷 `books` 的绝对值、不重算分位，分位数就与新值脱节。
2. **`pr`**：App 不返回 `praises`，刷新 `favs` 后 `pr = praises/favs` 分母变了、分子没变，
   赞藏比失真。
3. **`status`/`updated_at` 的历史语义**：快照 `status` 非当期状态，项目靠
   「已完结且 `updated_at < 时点`」重建生命状态（报告 10）；覆盖当期值会抹掉历史重建的基础。

**因此两条路（需拍板，本轮不实施）**：

- **追加快照表**（推荐）：新表 `novel_snapshots(nid, fetched_at, markCount, viewTimes, charCount, isFinish, signStatus, ...)`；
  当期值只进新表，`books` 原列与分位分母不动。历史可比、可增量刷新，代价是多一张表与查询 JOIN。
- **就地覆盖**：仅刷 `cover_url`（不影响任何派生列）与 `lastUpdateTime`；
  `favs/clicks/words/status/price_type` 覆盖须同步重算分位与 `pr`——**缺 `praises`，
  做不到完整重算**，故此路只适合「只要封面」的场景。

> 注意累计值跨时点不可比（报告 02/08）：`clicks` 混杂书龄与曝光分母；`favs` 更接近真实偏好。
> 刷新后这些是 2026-11 的累计值，与 2026-05 快照不能直接做差比较。

---

## 5. App 给不了的字段（反向缺口）

| 字段 | 来源 | 能否从 App 补 |
|---|---|---|
| `contest` 征文 | PC 详情页 / 比赛页 | ❌ 无 |
| `tags` 标签 | PC 详情页 | ⚠️ 需 `expand=tags,sysTags,intro` 另取（非本 18 字段） |
| `praises` 赞数 | PC 详情页 | ❌ 无 → `pr` 无法刷新 |
| `featured` 运营位 | App `bgBanner` 非空（同义） | ✅ 可，`bgBanner` 非空 → `featured=1` |
| `est_year/est_date/est_conf` | `lib/eras.py` 定年 | ❌ 不适用（本地推导，`addTime` 仅旁证） |
| `fav_pctl/click_pctl/praise_pctl/pr/pctl_pr` | 构建期全库分位 | ❌ 需全量重建 |
| `is_licensed` | 授权名单 | ❌ 本地名单判定 |

---

## 6. 对封面脚本的启示

- **封面补全价值最大**：配对的 110,370 本里 CSV 缺封面 56,742 本，API 全都有封面
  （整个 CSV 有 131,828 本缺封面，API 样本只覆盖其中一部分）。这是取回封面的核心收益。
- **一次请求物尽其用（已实施 2026-11-18）**：`cover_queue.py` 的成功记录已在结果 jsonl
  附 `snapshot`（`markCount`/`viewTimes`/`charCount`/`lastUpdateTime`/`isFinish`/`signStatus`/
  `typeId`/`categoryId`/`addTime`/`authorId`/`bgBanner`/`isSensitive`/`allowDown` 共 15 字段），
  **`point` 在分析侧采集层直接丢弃**（废弃占位分）；`isSensitive`/`allowDown` 虽出现在原始
  快照里，但按上表为无用字段（敏感内容强制下架、全站书籍禁止下载），**不入库、不作为维度使用**；
  `export --snapshots PATH` 另导快照。
  快照只落盘、不覆盖 `books`（§4 约束）。引擎侧另把包括 `point` 在内的字段写进 user.db
  的 `book_meta`（展示用），两者不冲突——**分析口径与 app 本地库是两套存储**。
- **格式**：写回 `cover_url` 必须剥离 URL 前缀；`bgBanner` 非空 → `featured=1`（URL 主体可由 nid 拼 CDN 前缀得到，故只存布尔）。
- 样本局限（只两类）不影响字段对应关系，但**九类全量刷新前需确认 `typeId` 映射无遗漏**。

---

> **复现**（在 `analysis/` 下，中文输出请给 Python 传 `encoding="utf-8"`）：
> 读 `out/app_api_novels.jsonl` 与 `out/novels.csv` 按 `novelId==id` 内连接；
> `addTime` 误差另用 `lib.eras.estimate(ids)['est_date']`。本文所有数字均由这两步现算，
> 随数据集版本变化，禁止硬编码到代码。

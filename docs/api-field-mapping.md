# App API 返回字段 ↔ 本项目数据字段：实测对应关系

> **定位**：全局契约文档，回答「App API 返回的字段哪些已有、哪些是新维度、哪些看着像其实不能用」。
> **状态**：现行口径（用户裁定 + 快照实测）；与 [`sfacg-app-api.md`](./sfacg-app-api.md)（端点/字段字典）、[`metrics-definitions.md`](./metrics-definitions.md)（指标口径）配套。
> **权威范围**：本文唯一维护字段对应关系、值映射、写回边界；作者资料选择器唯一权威见 [`author-profile-on-demand.md`](./author-profile-on-demand.md)。
> **口径**：所有计数/比例/样本量与误差均为快照现算值，仅供参考，禁止硬编码进代码；API 覆盖不到的信息（如 `praises`/`contest`/`tags`、App 侧真实展示）以手机 App 为准，拿不准直接问维护者。
> **更新日期**：2026-11-21。

快照背景：`analysis/out/app_api_novels.jsonl` 约 11.4 万条（2026-11-16/17 抓取）与
`analysis/out/novels.csv`（内容上界 2026-05-03）按 `nid` 内连接、配对约 11 万本；样本只覆盖
`tid=21` 魔幻、`tid=22` 玄幻，九类完整性由端点档案佐证，非全样本验证。

## 0. 一句话结论

**18 个业务字段 = 1 主键 + 11 同义可刷新（含 `bgBanner`→`featured` 布尔化）+ 1 旁证（`addTime`）
+ 2 新维度（`authorId`/`categoryId`）+ 3 无用（`point` 废弃占位分、`isSensitive` 敏感内容强制下架
本库不会命中、`allowDown` 全站书籍恒禁下载）。App 不返回 `praises`/`contest`/`tags`，
赞藏比 `pr` 与分位列无法靠这次刷新重建——这是「用 API 翻新快照」的硬边界。**

## 1. 逐字段对照表

`novels.csv` = 分析主表 15 列；`books` = 种子表 26 列（v3 加 `form`，v8 去 `lqs`/`lqs_pctl`/`vel_pctl`，v11 加 `db_update` 逐本快照时间）。
证据列为 110,370 对快照现算。

| App 字段 | 本项目对应 | 关系判定 | 实测证据 | 刷新可行性 |
|---|---|---|---|---|
| `novelId` | `id` / `books.nid` | 同义（主键） | 配对键，100% 相等 | — |
| `novelName` | `title` | 同义 | 直接取用 | 可 |
| `authorName` | `author` | 同义（显示名，可改；身份看 `authorId`） | 直接取用 | 可 |
| `authorId` | `dataset/author_ids.jsonl` | 新维度（已入库） | 账号唯一身份，大小写不敏感、空格敏感 | 已存 |
| `addTime` | `est_date`（旁证） | 不同口径 | 绝对误差中位 **1.3 天**、P90 **7.0 天**、有偏中位 **+0.5 天**（281 锚点曲线），见 §3.3 | 只作旁证 |
| `lastUpdateTime` | `updated_at` | 同义 | 98.9% 相等，100% API ≥ CSV | 可（当期值，只进 user.db） |
| `markCount` | `favs` | 同义 | Spearman 0.9987，80.8% 相等 | 可（关键刷新字段） |
| `viewTimes` | `clicks` | 同义 | Spearman 0.9987，62.5% 相等，99.96% ≥ | 可，见 §4 累计不可比 |
| `charCount` | `words` | 同义 | Spearman 0.9986，98.7% 相等 | 可 |
| `point` | — | 废弃占位分 | App 不展示；2020 年后 90.9% 为 6.0；与 `pr` 的 Spearman 仅 0.1626，见 §3.1 | 采集层丢弃 |
| `isFinish` | `status` | 同义（布尔↔文本） | 383 本冲突（0.35%），半年间状态翻转 | 可 |
| `signStatus` | `price_type` | 同义 | 普通→免费 100,090、VIP→VIP 3,572、签约→签约 6,660；漂移 48 本 | 可，映射见 §2 |
| `typeId` | `genre` | 同义（id↔文本） | 21→魔幻 88,528、22→玄幻 25,852；1 条 tid=9 异常 | 可 |
| `categoryId` | `form`（形态） | 新维度（形态，非题材） | 0 常规/1 对话/3 短篇/4 互动；与 genre 正交，详见 §3.4 | 正向判据 |
| `isSensitive` | — | 无用字段 | 敏感内容强制下架，本库书不会命中 | 不采集 |
| `novelCover` | `cover_url` | 同义（URL↔相对路径） | 去前缀后 92.68% 一致；CSV 缺封面的 56,742 本 API 全有 | 可，须剥离前缀（§2） |
| `bgBanner` | `featured` | 同义（非空→`=1`） | 仅 0.31%（351 本）非空，见 §3.2 | 可，非空即置 1 |
| `allowDown` | — | 无用字段（历史遗留） | 全站书籍恒禁下载，取值不改变结论 | 不采集 |

**汇总**：1 主键 + 11 同义 + 1 旁证 + 2 新维度 + 3 无用。

## 2. 值映射细则（覆盖前必读）

| 映射 | 规则 | 注意 |
|---|---|---|
| `isFinish`→`status` | `True`→已完结，`False`→连载中 | 383 本冲突是快照后状态翻转，覆盖会抹掉历史语义（§4） |
| `signStatus`→`price_type` | `VIP`→VIP；`签约`→签约；`普通`→免费 | 48 本漂移属签约状态变化 |
| `typeId`→`genre` | 21 魔幻/22 玄幻/23 古风/24 科幻/25 校园/26 都市/27 游戏/28 同人/29 悬疑 | 与 CSV 九类一一对应；样本只含前两类 |
| `novelCover`→`cover_url` | 剥离 `https://rss.sfacg.com/web/novel/images/NovelCover/Big/` | CSV 存相对路径，API 返回完整 URL；不剥离 0% 匹配 |
| `categoryId`→形态标记 | 0 常规/1 对话/3 短篇/4 互动 | 产品线/形态而非题材，不可当「同人标记」；与 `typeId/genre` 正交，细目见 §3.4 |
| `bgBanner`→`featured` | 非空→`=1` | URL 主体可由 nid 拼 CDN 前缀，只存布尔、不存会变的 token |

## 3. 三组字段结论

### 3.1 `point` ≠ `pr`

- 本项目 `pr` = `praises/favs`（赞藏比，见 [`metrics-definitions.md`](./metrics-definitions.md)），
  App 的 `point` 是 0–10 评分且早已不展示。两者 Spearman 仅 **0.1626**——几乎无关；`point→pr`
  的旧映射已废，现行结论是采集层直接丢弃 `point`。
- 值高度集中在占位常量 `6.0`（2020 年后 90.9%、2021+ 93.5%），2019 年前老书才残留 9.x/10.0。
- App 不返回 `praises`，刷新 `favs` 后 `pr` 的分子仍是旧值，`pr` 会失真（§4）。

### 3.2 `bgBanner` 就是 `featured`（同义，只存布尔）

- `featured=1`（封面曾用于 banner）与 App `bgBanner` 非空是同一件事；`bgBanner↔featured` 的旧误判
  已改，现行结论只存布尔。形如 `…/beitouNew/cut/{nid}.jpg?TOKEN`，仅 0.31% 非空。
- URL 主体可由 nid 拼 CDN 前缀得到，token 会变无保存价值，故只存一个布尔 `featured`（非空→`=1`）。

### 3.3 `addTime` 不作定年替换

- 与 `est_date` 误差见 §1（中位 1.3 天、P90 7.0 天），精度很高；可在 app 内更新 user.db 的当期时间。
- 项目定案：nid 定年体系是大量分析与 App 设计的基础，**不因 `addTime` 改定年/改 `books`**，它只作锚点旁证。

### 3.4 `categoryId` 是形态标记，不是题材（2026-11-20 实测定案）

校准脚本 `analysis/probe_category_id.py`。用户所说「cate 和 genre 同义」指英文词义（都是「分类」维度），
实测两者**取值空间正交**：`categoryId` 编码产品线/形态，`typeId/genre` 编码题材。
证据：API 全快照 114,381 本 + 9 个 genre 各 8 本分层抽样 + DOM 真值 7,227 本。

| 值 | 语义 | 决定性证据 |
|---|---|---|
| `0` | 常规（散文长篇为主） | DOM 真值 6,649 本全 prose、零 dialogue |
| `1` | 对话小说 | DOM 真值 533 本全 dialogue、零散文；征文名清一色「N征对话小说」 |
| `3` | 短篇 | 征文名清一色「N征短篇」；字数 <2 万占 78% |
| `4` | 沉浸式互动小说 | 5 本 DOM 全 dialogue，预读区「只能在APP上观看」；签约 39/40、2024+ 才出现 |

**与 `genre` 不同义**：`cat=1` 在九个 genre 里都出现，同一 genre 内 `cat=0/1/3/4` 并存。

**用途**：App 侧直接给出的形态金标。2026-11-20 接入 `analysis/lib/forms.py` 级 3.6：`cat=1/4→dialogue`
救回 invalid，低于用户裁定级。**只正向、不反向**——`cat=0` 不撤销 dialogue（早期对话书仍是 cat=0），
`cat=3` 是征文赛道不判形态；覆盖约全库 45%，缺席不作推断。E.28 救回 241 本 cat=1 对话书
（对话档 6,189→6,430）。取值分布随版本变化，数字仅供参考。

## 4. 写回的硬约束：能刷新不等于能就地覆盖

一次请求能拿回当期值，不等于能写回 `books`——三个派生口径会被打破：

1. **分位列**：`fav_pctl/click_pctl/praise_pctl/pr/pctl_pr` 在完整 universe（241,864 行）构建期按世代
   算出，种子只是其中 18,656 行子集；只刷绝对值不重算分位，分位数就与新值脱节。
2. **`pr`**：App 不返回 `praises`，刷新 `favs` 后分母变、分子没变，赞藏比失真。
3. **`status`/`updated_at` 历史语义**：快照 `status` 非当期状态，项目靠「已完结且 `updated_at < 时点`」
   重建生命状态；覆盖当期值会抹掉历史重建基础。

**边界（定案程度不同）**：

- **封面写回已定案**：走追加只读 `covers` 表、不动 `books`（`books.cover_url` 原列保留）。
- **其他字段全量刷新未定案**：追加快照表 `novel_snapshots(nid, fetched_at, markCount, viewTimes, …)`
  是推荐方向（历史可比、不破坏分位分母），但本轮不实施；就地覆盖只适合「只要封面」且须同步重算
  分位与 `pr`（缺 `praises` 做不到完整重算）。工程侧落地事项，本文不执行。

> 累计值跨时点不可比（报告 02/08）：刷新后是 2026-11 累计值，与 2026-05 快照不能直接做差。

## 5. App 给不了的字段（反向缺口）

| 字段 | 来源 | 能否从 App 补 |
|---|---|---|
| `contest` 征文 | PC 详情页/比赛页 | 无 |
| `tags` 标签 | PC 详情页 | 需 `expand=tags,sysTags,intro` 另取（非本 18 字段） |
| `praises` 赞数 | PC 详情页 | 无 → `pr` 无法刷新 |
| `featured` 运营位 | App `bgBanner` 非空 | 可 |
| `est_year/est_date/est_conf` | `lib/eras.py` 定年 | 不适用（`addTime` 仅旁证） |
| 分位列/`pr` | 构建期全库分位 | 需全量重建 |
| `is_licensed` | 授权名单 | 本地判定 |
| 作者 `intro`/头像 | Web 详情页 DOM | App API 无；按需抓、不内置，见 [`author-profile-on-demand.md`](./author-profile-on-demand.md) |

## 6. 对封面脚本的启示

- **封面补全价值最大**：配对 110,370 本里 CSV 缺封面 56,742 本、API 全有；整个 CSV 有 131,828 本缺封面。
- **一次请求物尽其用（已实施 2026-11-18）**：`cover_queue.py` 成功记录在结果 jsonl 附 `snapshot`，
  共 15 字段：`novelName`/`authorName`/`markCount`/`viewTimes`/`charCount`/`lastUpdateTime`/`isFinish`/
  `signStatus`/`typeId`/`categoryId`/`addTime`/`authorId`/`bgBanner`/`isSensitive`/`allowDown`。
  `point` 在分析侧采集层直接丢弃；`isSensitive`/`allowDown` 按 §1 为无用字段，不入库、不作维度。
  快照只落盘、不覆盖 `books`（§4 约束）；引擎侧另写入 user.db 的 `book_meta` 供展示，两套存储不冲突。
- **格式**：写回 `cover_url` 必须剥离前缀；`bgBanner` 非空→`featured=1`。
- 样本局限（只两类）不影响字段对应关系，但九类全量刷新前需确认 `typeId` 映射无遗漏。

> **复现**：在 `analysis/` 下读 `out/app_api_novels.jsonl` 与 `out/novels.csv` 按 `novelId==id` 内连接；
> `addTime` 误差另用 `lib.eras.estimate(ids)['est_date']`。所有数字均由这两步现算，禁止硬编码。

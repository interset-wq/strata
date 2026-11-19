# App API 返回字段 ↔ 本项目数据字段：实测对应关系

> **性质**：全局契约文档。回答「App API 一次请求返回的字段，哪些是我们已有的、哪些是新的、
> 哪些看着像其实不能用」。与 [`sfacg-app-api.md`](./sfacg-app-api.md)（端点与字段字典）、
> [`metrics-definitions.md`](./metrics-definitions.md)（自定义指标口径）配套。
>
> **实证基础**：本地 `analysis/out/app_api_novels.jsonl`（114,381 条，2026-11-16/17 抓取）
> 与 `analysis/out/novels.csv`（245,887 行，内容上界 2026-05-03）按 `nid` 内连接，
> **配对 110,365 本**。所有一致率为这对样本的现算值，非估计。
>
> **样本局限**：`app_api_novels.jsonl` 只抓了 `tid=21` 魔幻（88,528）、`tid=22` 玄幻（25,852）
> 两类，类型映射的完整性由端点档案九类枚举佐证，非全样本验证。

---

## 0. 一句话结论

**18 个业务字段里，9 个与我们的列直接同义、可安全刷新；3 个"看着像"实则不同义、覆盖会出错；
6 个是我们没有的新维度。App 不返回 `praises`/`contest`/`tags`/运营标记，因此赞藏比 `pr`
与分位列无法靠这次刷新重建——这是"用 API 翻新快照"的硬边界。**

---

## 1. 逐字段对照表

`novels.csv` = 分析主表 15 列；`books` = 种子表 28 列（v3 加 `form`/`lqs`/`lqs_pctl`/`vel_pctl`）。

| App 字段 | 本项目对应 | 关系判定 | 实测证据（110,365 对） | 刷新可行性 |
|---|---|---|---|---|
| `novelId` | `id` / `books.nid` | **同义**（主键） | 配对键，100% 相等 | — |
| `novelName` | `title` | **同义** | 直接取用 | ✅ 可 |
| `authorName` | `author` | **同义** | 直接取用 | ✅ 可 |
| `authorId` | — | **新维度** | 作者 id，可做作者生态（CSV 只有名字） | 🆕 建议新增列 |
| `addTime` | `est_date`（旁证） | **不同口径** | 与 `est_date` 绝对误差中位 **2.1 天**、P90 11 天、有偏中位 −0.0 | ⚠️ 只作旁证，不替换 nid 定年 |
| `lastUpdateTime` | `updated_at` | **同义** | **98.9% 完全相等**，100% API ≥ CSV（时点晚半年） | ✅ 可（这是当期值） |
| `markCount` | `favs` | **同义** | Spearman **0.9987**，80.8% 完全相等，85.1% API ≥ CSV | ✅ 可（关键刷新字段） |
| `viewTimes` | `clicks` | **同义** | Spearman **0.9987**，100% ≥，62.5% 相等 | ✅ 可，但见 §4 累计不可比 |
| `charCount` | `words` | **同义** | Spearman **0.9986**，98.7% 相等，99.8% ≥ | ✅ 可 |
| `point` | — | **🗑 无用字段（官方已废弃）** | App 端不展示该评分（读者水军刷差评，作者要求官方删除）；值高度集中于**单一占位常量**无区分度：本地样本 2020 年后 **96.8% 为 6.0**、5.0 仅 1.6%、2019 年前老书残留少量 9.x/10.0 历史评分；与 `pr` 的 Spearman **仅 0.1625** | ❌ **采集层直接丢弃，不入库、不展示、不参与任何计算** |
| `isFinish` | `status` | **同义**（布尔↔文本） | 仅 383 本冲突（0.35%），均为半年间状态翻转 | ✅ 可，按 `True→已完结` 映射 |
| `signStatus` | `price_type` | **同义** | VIP→VIP 3,568、普通→免费 100,090、签约→签约 6,659；漂移 48 本 | ✅ 可，映射表见 §2 |
| `typeId` | `genre` | **同义**（id↔文本） | 21→魔幻 85,537、22→玄幻 24,828，与九类枚举一一对应 | ✅ 可 |
| `categoryId` | — | **新维度** | 0 非同人 / 1 同人（1 占 9.3%），比 `genre=同人` 更宽（含 sysTags） | 🆕 建议新增列 |
| `isSensitive` | — | **新维度** | 敏感标记 | 🆕 |
| `allowDown` | — | **新维度** | 是否允许下载 | 🆕 |
| `novelCover` | `cover_url` | **同义**（URL↔相对路径） | 去前缀后 92.66% 一致；7.34% 为半年间换图。**CSV 缺封面的 56,736 本 API 全有** | ✅ 可，须剥离 URL 前缀（§2） |
| `bgBanner` | ~~`featured`~~ → **无** | **❌ 不同义** | 横幅图 URL，仅 0.3% 非空；`featured` 是运营位标记（报告 01：其封面时间戳偏差中位 +338 天） | ❌ 不可覆盖 `featured` |

**汇总**：9 个可直接刷新 + 1 个旁证（`addTime`）+ 6 个新维度（4 个建议存）+ 2 个禁止覆盖（`point`/`bgBanner`）。

---

## 2. 值映射细则（覆盖前必读）

| 映射 | 规则 | 注意 |
|---|---|---|
| `isFinish` → `status` | `True`→`已完结`，`False`→`连载中` | 383 本冲突是快照后完结状态翻转，API 值更新，但刷新会改变 `status` 的历史语义（见 §4） |
| `signStatus` → `price_type` | `VIP`→`VIP`；`签约`→`签约`；`普通`→`免费` | 48 本漂移（普通→VIP 26、VIP→签约 9 等），属签约状态变化 |
| `typeId` → `genre` | 21 魔幻 / 22 玄幻 / 23 古风 / 24 科幻 / 25 校园 / 26 都市 / 27 游戏 / 28 同人 / 29 悬疑 | 与 CSV 九类一一对应；样本只含前两类 |
| `novelCover` → `cover_url` | 剥离前缀 `https://rss.sfacg.com/web/novel/images/NovelCover/Big/` | CSV 存相对路径（如 `2025/12/uuid.jpg`），API 返回完整 URL；不剥离会 0% 匹配 |
| `categoryId` → 新列 | 1=同人（含系统标签），0=非同人 | 与 `genre=同人` 不等价——后者只覆盖正式分类 |

---

## 3. 三组"看着像、不能用"的字段（本次分析的核心）

### 3.1 `point` ≠ `pr`（最易误用）

- 本项目 `pr` = `praises / favs`（**赞藏比**，详见 [`metrics-definitions.md`](./metrics-definitions.md)），
  App 的 `point` 是 **0–10 评分**。
- 110,365 对样本 Spearman 仅 **0.1625**——几乎无关。原档案 §3.1 写 `point → pr`
  是错的，已修正。
- App **不返回 `praises`**，所以刷新 `favs` 后 `pr` 的分子仍是旧值，`pr` 会失真（见 §4）。

### 3.2 `bgBanner` ≠ `featured`

- `featured` 是运营位标记（`=1` 表示封面曾用于 banner，见报告 01），不是横幅图本身。
- `bgBanner` 只有 0.3% 非空，且是图片 URL。二者语义不同，不能互相覆盖。

### 3.3 `addTime` 不作定年替换

- 与 `est_date` 绝对误差中位仅 2.1 天、P90 11 天——精度其实很高，几乎无偏。
- 但项目定案：nid 定年体系是大量分析与 App 设计的基础，**不因 addTime 改定年**。
  它只作锚点旁证（`source=user_verified` 的核验流程见报告中定年档案）。

---

## 4. 写回的硬约束：能刷新的字段，有些不能"就地覆盖"

一次请求能拿回当期值，不等于能直接写回 `books`——三个派生口径会被打破：

1. **分位列**：`fav_pctl/click_pctl/praise_pctl/pr/pctl_pr` 是在**完整 universe
   （241,864 行）构建期按世代算出的**，种子只是其中 18,077 行子集（不含 47 授权）。只刷 `books`
   的绝对值、不重算分位，分位数就与新值脱节。
2. **`pr`**：App 不返回 `praises`，刷新 `favs` 后 `pr = praises/favs` 分母变了、分子没变，
   赞藏比失真。
3. **`status`/`updated_at` 的历史语义**：快照 `status` 非当期状态，项目靠
   "已完结且 `updated_at < 时点`"重建生命状态（报告 10）；覆盖当期值会抹掉历史重建的基础。

**因此两条路（需拍板，本轮不实施）**：

- **追加快照表**（推荐）：新表 `novel_snapshots(nid, fetched_at, markCount, viewTimes,
  charCount, isFinish, signStatus, ...)`，当期值只进新表，`books` 原列与分位分母不动。
  历史可比、可增量刷新，代价是多一张表与查询 JOIN。
- **就地覆盖**：仅刷 `cover_url`（不影响任何派生列）与 `lastUpdateTime`；
  `favs/clicks/words/status/price_type` 覆盖须同步重算分位与 `pr`——**缺 `praises`，
  做不到完整重算**，故此路只适合"只要封面"的场景。

> 注意累计值跨时点不可比（报告 02/08）：`clicks` 混杂书龄与曝光分母；`favs` 更接近真实
> 偏好。刷新后这些是 2026-11 的累计值，与 2026-05 快照不能直接做差比较。

---

## 5. App 给不了的字段（反向缺口）

| 字段 | 来源 | 能否从 App 补 |
|---|---|---|
| `contest` 征文 | PC 详情页 / 比赛页 | ❌ 无 |
| `tags` 标签 | PC 详情页 | ⚠️ 需 `expand=tags,sysTags,intro` 另取（非本 18 字段） |
| `praises` 赞数 | PC 详情页 | ❌ 无 → `pr` 无法刷新 |
| `featured` 运营位 | 构建期运营标记 | ❌ 无 |
| `est_year/est_date/est_conf` | `lib/eras.py` 定年 | ❌ 不适用（本地推导，addTime 仅旁证） |
| `fav_pctl/click_pctl/praise_pctl/pr/pctl_pr` | 构建期全库分位 | ❌ 需全量重建 |
| `is_licensed` | 授权名单 | ❌ 本地名单判定 |

---

## 6. 对封面脚本的启示

- **封面补全价值最大**：CSV 缺封面 56,736 本，API 全都有封面——这正是取回封面的核心收益。
- **一次请求物尽其用（已实施 2026-11-18）**：`cover_queue.py` 的成功记录已在结果 jsonl
  附 `snapshot`（markCount/viewTimes/charCount/lastUpdateTime/isFinish/signStatus/
  typeId/categoryId/addTime/authorId/bgBanner/isSensitive/allowDown 共 15 字段），
  **`point` 采集层直接丢弃**（官方废弃）；`export --snapshots PATH` 另导快照。
  快照只落盘、不覆盖 `books`（§5 约束），写回策略待拍板。
- **格式**：写回 `cover_url` 必须剥离 URL 前缀；`bgBanner` 不要写进 `featured`。
- 样本局限（只两类）不影响字段对应关系，但**九类全量刷新前需确认 `typeId` 映射无遗漏**。

---

> 复现命令（在 `analysis/` 下）：`uv run python - <<'PY'` 读两个文件按 `nid` 合并后现算；
> 数字随数据集版本变化，禁止硬编码到代码。

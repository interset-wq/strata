# 运行时量化指标（cqs/cps/clx）落地设计

> **定位**：推荐层（量化模式）排序与筛选信号的唯一权威设计——口径、公式、常量、
> 存储形态、引擎/UI 形态以本文为准。
> **口径来源**：`analysis/reports/24_runtime_metrics.md`（2026-11-23，用户裁定：
> 运行时可直接计算的指标替代原有自定义指标）。本文不复述公式推导，只钉死落地形态。
> **红线继承**：docs/12 双模式契约全部有效——平台累计值严禁回流推荐打分；
> `clicks` 禁入 cqs/cps 公式（报告 §2.3）；推荐为口碑驱动、非协同过滤。
> **更新日期**：2026-11-23。

---

## 1. 结论：三个指标、一个替代关系

| 指标 | 回答的问题 | 公式（报告 24） | 落地形态 |
| --- | --- | --- | --- |
| **cqs** | 同 form、同年、同题材、同收藏档里的口碑 | `log(pr_s) − 格内中位`，`pr_s = (praises+500×μ0)/(favs+500)`，μ0=cqs 池 `praises/favs` 中位 | 种子书构建期预计算；推荐层**排序分** |
| **cps** | 同 form、同年、同篇幅档、同题材里的收藏位置 | `log1p(favs) − 格内中位` | 种子书构建期预计算；**只做中层筛选**（20–80 分位带），不发榜 |
| **clx** | 用户的篇幅偏好如何重排 cqs | `cqs × (1−K+K×len_f)`，K∈{0, 0.25, 0.60} 默认 0 | **运行时现算**（引擎按 K 参数重排），不存列、不预排 |

**替代关系（用户 2026-11-23 裁定）**：

- 推荐层排序分职责由 **cqs 接任**：`lqs`（长篇）/`mqs`（中篇）维持「归档不落地」，
  定义文档（16-length-weighted-quality 等）保留作历史，**不与 cqs 合并、分数不可比**（报告 §8.4）。
- `fav_pctl` 等五个构建期分位**保留**：种子已有、详情页分位展示与经典榜仍用；
  但它们是构建期快照，**库外新书永远算不出**——库外书的质量信号走运行时 cqs/cps（二期）。
- 经典榜单继续用原始 `favs/clicks/praises` 排序，不受影响。

## 2. 硬边界（报告 §9 全条继承，重点五条）

1. **form 是硬前置**：所有 cqs/cps/clx 查询先 `WHERE form = ?`；跨 form 总榜不存在。
   cqs 只发布长篇/对话（stable 为主）；中篇为 low_confidence 探索层；短篇/IP 合作无 cqs
   （池太小），只走 cps 筛选 + 经典榜。
2. **年内 P50 以下不发布 cqs**：先过滤后加分，不改格内分母。
3. **cps 不是榜单**：只做每个 form 中层带（20–80 分位）筛选，之后由 cqs 排序。
4. **文案不承诺精确名次**：Bootstrap Top100 Jaccard 0.70，UI 显示「中层/证据强度」，
   不出现「第 N 名」叙事。
5. **clx 文案叫「篇幅偏好」**，不叫「排名」；K 默认 0（纯 cqs）；不与 cqs 合成总分。

## 3. 种子侧（schema v6）

### 3.1 books 新增 4 列（种子书 = 18,656 本，授权书 NULL）

| 列 | 类型 | 语义 |
| --- | --- | --- |
| `cqs` | REAL | 口径见 §1；不满足（favs<1000 / P50− / 格<5 本 / 短篇·IP）为 NULL |
| `cqs_state` | TEXT | `'stable'`（格 ≥20 本）/ `'low'`（5–19 本）；NULL 同上 |
| `cps` | REAL | 口径见 §1；favs<10 或格<20 本为 NULL |
| `len_norm` | REAL | `log(clip(words,LO,HI)/LO)/log(HI/LO)`，锚点按 form 取可发布池 P10/P90；无 cqs 为 NULL |

### 3.2 新校准表（库外书运行时定档的依赖，随种子发布）

```sql
CREATE TABLE calib_fav_bounds(form TEXT, est_year INTEGER, p50 REAL, p75 REAL, p90 REAL,
  PRIMARY KEY(form, est_year));            -- cqs 池内 form×年收藏分位阈值
CREATE TABLE calib_len_anchors(form TEXT PRIMARY KEY, lo REAL, hi REAL);
CREATE TABLE calib_cqs_median(form TEXT, est_year INTEGER, genre TEXT, fband TEXT,
  med REAL, cell_n INTEGER, PRIMARY KEY(form, est_year, genre, fband));
CREATE TABLE calib_cps_median(form TEXT, est_year INTEGER, band TEXT, genre TEXT,
  med REAL, PRIMARY KEY(form, est_year, band, genre));
```

`seed_meta.calibration_version` 记录快照版本（= seed_version）；常量钉死
`κ=500`、篇幅档切点 `[2,000, 50,000, 150,000, ∞]`（报告 24 §7.1：κ 250–2000 可调，默认 500）。
校准全部由 build_seed 在分析 universe（`is_licensed=0`、`est_year 2007..2025`、
form≠invalid、words≥2000）上**自含现算**，不依赖报告生成器的运行时状态。

### 3.3 索引

`idx_form_cqs ON books(form, cqs DESC)`（发现流主查询）；其余查询走既有索引。

## 4. 引擎形态

- 发现流（量化模式）排序键改为：同 form 内 `cqs DESC`（NULL 不进榜）；
  候选先过 cps 中层带（form 内 20–80 分位，SQL 窗口或物化时判定）。
- `clx`：端点接受 `k` 参数（0/0.25/0.60，缺省 0），运行时
  `ORDER BY cqs*(1-K+K*len_norm)`；K=0 走纯 cqs 索引路径。
- 响应带 `cqs_state`（stable/low），UI 据此标注证据强度。
- 经典模式端点（fav_pctl/clicks 排序）零改动。

## 5. UI 形态

- 量化发现流加「篇幅偏好」三档选择（不加权/偏厚/厚书优先——K=0/0.25/0.60，
  K>0 恒加厚书、无「偏短」向），ChoiceChip 关 ✔；档位会话内记忆
  （落盘持久化待设置面板统一做）。
- 书卡证据标注：`low` 档书显示「低置信」小字；stable 不额外标注。
- 文案红线：不显示精确名次；「篇幅偏好」非「排名」。

## 6. 分期

- **P1（本期）**：种子预计算 + 校准表 + 引擎 cqs/cps/clx + UI。覆盖种子书。
- **P2（后续）**：库外书运行时现算（discovered 写回后按 §8.3 顺序：
  定年→定档→cps→cqs→len_norm）。依赖种子内的校准表（本版已带）+ **eras 锚点表入种子**
  （281 行，待 v7）；锚点表进来之前，库外书不进 cqs/cps 榜，只进搜索/详情。

## 7. 验收断言（validate.py）

- cqs 非空 ⇔（form∈{long,dialogue,medium} 且 favs≥1000 且 fband∈P50+ 且格≥5）；
  short/ip_collab 的 cqs 全 NULL。
- cqs_state='stable' ⇔ 格 ≥20 本；种子内 stable 覆盖与报告 24 §3 同量级
  （长篇 ~84%、对话 ~80%，快照现算校验，不写死）。
- len_norm ∈ [0,1] 且只在 cqs 非空时非空。
- 授权书四列全 NULL；`calibration_version` 与 seed_version 一致。

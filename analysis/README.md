# analysis · SFACG 书层数据分析

对菠萝包轻小说（SFACG）二十年书目数据的可复现研究。数据从原始爬虫产物出发，
经规范化建成单张宽表，再按专题产出 19 份报告与 82 张图表。

**定位**：官方榜单回答「现在什么火」，本分析回答「过去十年结构如何变化」。
这是一个观察性书目研究，不含正文内容，也不含营收、付费人数或用户事件数据。

| 项 | 值 |
| --- | --- |
| 唯一原始数据集 | `data/extracted/dataset/data/meta*.jsonl`，22 个文件 / 249,832 行 |
| 规范化书目表 | `out/novels.csv`，245,779 行 × 15 列（构建时已剔除正版日轻 47 行） |
| 数据内容上界 | **2026-05-03**（原始 jsonl 的 `max(last_update)`，即扫描起点，非统一读取时刻） |
| 年份覆盖 | 2007–2026（年度序列止于 2025：上界之后创建的新书不在库内） |
| 定年 | `lib/eras.py`，104 个锚点、log(nid) 分段线性插值，留一法 P99 = 50 天 |
| 在架覆盖率 | 约 69.3%（95% CI 64.6–73.9，分层加权，见报告 10）；**补爬对象约 1 千本**，非 11.1 万 |
| 产出 | 19 份报告（`reports/*.md`）、82 张图（`reports/figures/*.png`） |

---

## 快速开始

工作目录为本目录（`pyproject.toml` 在此），使用 `uv` 管理依赖：

```bash
cd analysis
uv sync

# 首次：校验 dataset.7z 哈希并解压（jsonl 已存在则自动跳过）
uv run --extra archive python pipeline/prepare.py

# 从 jsonl 重建书目表、schema 与清单（内置校验，失败即拒绝发布）
uv run python pipeline/build_csv.py
```

生成报告（各生成器相互独立，可单跑；汇总篇 16 引用前序结论但数字自算）：

```bash
for f in generators/report_*.py; do uv run python "$f"; done   # 全部 19 份
uv run python generators/report_market.py                      # 单跑 01（定年与供给）
uv run python generators/report_timeline.py                    # 单跑 16（收官汇总）
```

依赖：Python ≥ 3.11，pandas、matplotlib、scipy、scikit-learn、jieba、wordcloud、requests。
仅重新解压归档时需要额外依赖 `py7zr`（`--extra archive`）。

---

## 数据管线

```
dataset.7z  ──pipeline/prepare.py──▶  meta*.jsonl（22 文件，唯一原始数据集）
                                  │
                                  ├──pipeline/build_csv.py──▶  out/novels.csv
                                  │                          out/schema.sql
                                  │                          out/manifest.json
                                  │
                    out/monthly_ranks.jsonl ◀──fetchers/fetch_monthly_ranks.py（付费刻度）
                    out/survival_probe.jsonl ◀──fetchers/fetch_survival.py（存活审计）
                    out/title_tokens.pkl   ◀──报告 12/14 的 jieba 切词缓存
                                  │
                    lib/eras.py（nid 定年）+ lib/config.py（清洗规则）
                                  │
                    generators/report_*.py──▶  reports/*.md + figures/*.png
```

`out/` 不入库，均可由上述脚本重建；榜单与存活探测需联网重新抓取。

抓取机制（报告 10 §7）：原始 jsonl 是 Scrapy `scrapy -o` 按天切分、追加写入的产物；
列表页按 `last_update` 降序，每天从上一天的断点续爬。全量是一次约 3 周、
从新到旧的**单向游标扫描**，不是统一时刻的快照——更新中的书与新入库书被重排到
游标身后，因此遗漏偏向「短、新、更新中」而非冷门。

---

## 目录结构

代码按**职责**分四类：共享库、报告生成器、联网抓取、数据管线。
**所有路径都从 `lib/paths.py` 派生**——脚本放在哪个目录都读到同一份数据。

| 路径 | 说明 |
| --- | --- |
| `lib/` | **共享库**：`paths`（路径唯一真源）、`config`（枚举域、清洗与行级剔除规则）、`eras`（nid 定年）、`charts`（统一图表风格） |
| `generators/` | **19 份报告的生成器**（`report_*.py`）；**报告是生成物，勿手改** |
| `fetchers/` | 可选联网抓取器：月度榜、存活状态、存活书详情 |
| `pipeline/` | 数据管线：`prepare`（校验归档并解压）、`build_csv`（jsonl → CSV 的唯一规范化入口）、`validate`（CSV 格式层与取值层校验，构建时自动调用） |
| `anchors/` | 定年锚点：`nid_anchors.jsonl`（104 条插值输入）、`verified_dates.jsonl`（用户核实证据档案）、`approximate_dates.jsonl`（已清空，保留备用） |
| `references/` | 外部查证档案：**端点总表 `sfacg-endpoints.md`**、征文日期、萌神标签、榜单端点、定年取证、百科与史料等 |
| `data/` | 归档与解压后的 jsonl（归档不入库） |
| `out/` | 派生数据资产，可重建，不入库 |
| `reports/` | 报告正文与图表，均由生成器产出 |

### 为什么路径集中在 `lib/paths.py`

早期 `config.py` / `eras.py` / `charts.py` 各自用
`Path(__file__).resolve().parent` 推算根目录，脚本又出现 5 种拼路径的写法，
甚至有两个生成器写死了绝对路径。移动脚本就会静默读错数据。

现在：

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # analysis/ 根
from lib import paths
df = pd.read_csv(paths.CSV_FILE)
```

`paths.ROOT` 恒等于 `analysis/`，与脚本位置无关。
**新增脚本一律用 `paths.*`，不要自己拼路径。**

---

## 报告清单

| # | 报告 | 生成器 | 核心结论 |
| --- | --- | --- | --- |
| 01 | 市场结构 | `generators/report_market.py` | 定年体系、单峰供给、商业化门槛加深 |
| 02 | 注意力集中度 | `generators/report_attention.py` | Gini 0.95 是结构常数，重心随周期迁移 |
| 03 | 作者生态 | `generators/report_author.py` | 新作者 2020 先见顶，收缩是作者基数流失 |
| 04 | 题材与标签 | `generators/report_genre.py` | 三足结构、女性向标签扩张、词表受控 |
| 05 | 生命周期与存量 | `generators/report_lifecycle.py` | 完结二元结构、92.8% 断更书持有 80.7% 收藏 |
| 06 | 征文 | `generators/report_contest.py` | 日历首尾相接、报名≠完赛 |
| 07 | 商业化 | `generators/report_commercial.py` | 月票与热销两条刻度、付费 2020 见顶 |
| 08 | 互动漏斗 | `generators/report_engagement.py` | 曝光分母效应、赞藏比断崖 |
| 09 | 题材语义空间 | `generators/report_tagspace.py` | 99 词受控词表、同人 = IP 命名空间 |
| 10 | 生存与遗漏 | `generators/report_survival.py` | ✅ **已重写**：三态判据 + 分母先扣构建剔除 2,451 本 + 按 nid 段分层加权，覆盖率 69.3%（旧 68.9% 量级未变，但口径已改）；**核心新结论**：在册密度 U 型 / 缺失槽位存活率倒 U 型 = 游标扫描形状（§2.1）。判活三态（死亡 200+否定文案、僵尸无阅读入口或数字非法、存活），下架原因不进判据。补爬对象约 1 千本。见 `references/sfacg-endpoints.md` §5.1/§11.5 |
| 11 | 速更短篇 | `generators/report_shortform.py` | 独立品类、新手高频试水、非弃坑 |
| 12 | 标题形态与命名史 | `generators/report_titles.py` | 标题通胀、跟风证据分级 |
| 13 | 跟风传播 | `generators/report_fad.py` | 头部少造词、爆款潮是赛道共振 |
| 14 | 标题成功配方 | `generators/report_titlewords.py` | 条件分位剥离题材、配方题材特定 |
| 15 | 征文到商业化 | `generators/report_contest_commerce.py` | 优势属于人，不属于比赛 |
| 16 | 十年结构变迁 | `generators/report_timeline.py` | 收官汇总：统一时间轴、六条主线、对照先于因果 |
| 17 | banner 投入 | `generators/report_banner.py` | 作者筛选、下注/奖励二元 |
| 18 | 种子规模决策 | `generators/report_seed_scale.py` | 捆绑 29,396 本（gz 4.18 MB）、膨胀源是索引不是表数 |
| 19 | 短篇生态 | `generators/report_shortnovel.py` | 短篇=≤5万字且完结、收藏天花板、赞藏比在短篇里方向反 |

编号经过顺延，最终为 15 征文商业化、16 汇总、17 banner（banner 应要求提前）、18 种子规模、19 短篇（面向 App 品类设计）。

---

## 口径约束（写结论前必读）

这些规则由前序报告逐条查证得来，违反任一条即需返工。

1. **原始数据集唯一**：`meta*.jsonl` 是唯一原始来源；归档数据库、早期 `quarry/` 文档与
   其他分片均不用于结论。`out/novels.csv` 由其规范化派生。
2. **内容上界 2026-05-03**：由 `eras.snapshot_bounds()` 现算，不是外部快照日期；
   `max(last_update)` 是扫描起点，不是每本书的读取时刻。
3. **年份来自定年，不来自 `updated_at`**：后者是末次更新时间，老书一次编辑可晚于创建十年以上。
   `updated_at` 只能当「时长」用（与内容上界相减 = 断更时长，不依赖定年）。
4. **正版日轻剔除**：作者 ∈ {天闻角川, 天闻角川2号机, 丸山黄金, HJ文库}（`config.LICENSED_LN_AUTHORS`）。
   授权版复用了盗版条目的旧 id，nid 不单调，会污染定年与世代统计。构建时已整行剔除。
5. **快照状态 ≠ 当期状态**：`status` / `price_type` 是 2026 上界态；跨时点统计生命或商业化状态
   必须用「`status=已完结` 且 `updated_at` < 该时点」重建（报告 07 `attach_done_now()`）。
6. **累计指标跨时点不可比**：`clicks` 受上架时长与曝光分母混杂，`favs` 更接近真实偏好；
   转化率排行必须分曝光档，`updated_at` 不是创作时间。
7. **标签不是自由词汇**：受控词表约 2014 上线，跨世代比较仅 2017 年后可靠；
   2022 年有 23 个 IP/亚文化标签被清理；`20XX萌神` 是年度赛事荣誉，须整行剔除并单列。
   `末日` 与 `末世` 是两个独立标签，不合并。
8. **样本有覆盖偏倚**：对在架书覆盖约 68.9%，遗漏偏「短、新、更新中」；
   凡绝对计数是下界，排序与相对比较稳健。
9. **计费口径**：月票由充值返还（1 票 ≈ 0.5 元），可投任意书含免费书；热销榜 ≈ 订阅额。
   `fireMoney` 是按字数计的整本订阅定价，**不是营收**；平台无营收/订阅额/付费人数数据。
10. **榜单是顶部结构**：月度 top20 右截断、每月清零；月票总票是 top20 之和，非全站票量。
11. **批准的新锚点直接追加** `anchors/nid_anchors.jsonl`（`source=user_verified`，字段名 `addTime`），
    并在 `verified_dates.jsonl` 留档；待查清单见 `references/dating-wishlist.md`。
12. **报告数字一律现算**，不在正文写死快照数字；所有发现为结构描述，区分相关与因果。

---

## 参考档案

`references/` 保存可溯源但不属于数据中台结论的外部证据：

| 文件 | 内容 |
| --- | --- |
| `contest-editions.md` | 征文各产品线官方日期与 cohort 窗口校验 |
| `verified-dates.md` | 用户核实创建时间的原始消息、配对依据与并入决策 |
| `dating-wishlist.md` | 按锚点间隔排序的定年取证清单（P0 已完成） |
| `moebattle-tags.md` | 萌神标签来源、氪金机制与剔除依据 |
| `my2020-top10.md` / `.json` | 2020 年度 TOP10 页面口径与 `fireMoney` 诊断 |
| `sfacg-live-ranks.md` | 月度榜端点语义、计费机制与抓取证据 |
| `sfacg-endpoints.md` | **已知端点总表**：三类搜索接口的字段覆盖与容量上限、`novelbytype` 枚举、详情页/目录/评论/榜单字段、静默限流与失败模式、复现命令 |
| `sfacg-baike.md` / `bolobao-baike.md` / `pku-lightnovel-essay-2018.md` / `sfacg-pku-chronicle.md` | 平台沿革与文学史旁证 |

---

## 数据来源

数据来自 SFACG 公开页面与 API，仅用于个人研究与书目分析。上游原始快照与凭据不入库。
根 `README.md` 与 `docs/` 为早期文档，含指向已删除 `quarry/` 的链接与旧口径数字；
**当前数据口径以本目录的生成器与报告为准**。

## 许可

本目录代码与报告以 **AGPL-3.0** 授权（全文见根 [`LICENSE`](../LICENSE)）。
抓取脚本（`fetch_*.py`）属授权范围：若修改后以网络服务形式对外提供，须按 AGPL 第 13 条
公开完整对应源码。分析文字与图表版权归作者所有。

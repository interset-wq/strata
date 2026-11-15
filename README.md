# 书层 Strata

![](https://img.shields.io/badge/status-research-blue) ![](https://img.shields.io/badge/data-246%2C045%20novels-green)

一个 SF 轻小说（菠萝包轻小说）**二十年书目数据**的研究与产品化项目。

这里存放的不是一个 App，而是一个判断：**官方榜单回答「现在什么火」，我们想回答「过去什么好」。**
为了验证这个判断站不站得住，先把 24.6 万本书、20 年时间、667 张 banner 摊开分析——
结论写在 [`docs/`](./docs/)，可复现的代码写在 [`quarry/`](./quarry/)。
| 层 | 名字 | 目录 | 职责 |
| --- | --- | --- | --- |
| 产品 | **书层 Strata** | `app/`（预留） | Flutter 手机端 App，后续开发 |
| 研究 | **quarry**（采石场） | [`quarry/`](./quarry/) | Python 数据分析：定年、年表、基线断言 |
| 设计 | — | [`docs/`](./docs/) | 数据实测报告、架构、17 表 schema |

## 核心结论（先看这个）

三个维度的峰值**不在同一年**，而且先起来的不是规模，是认可：

| 维度 | 峰值年 | 峰值 | 2025 |
| --- | --- | --- | --- |
| 原创作品认可密度（每千本新书获 banner） | **2015** | 22.4‰ | 0.41‰ |
| 认可绝对量（当年创建的书最终获 banner） | **2016** | 95 本 | 6 本 |
| 单本爆发力（当年新书人气 P99） | **2019** | 272 万 | 89 万 |
| 供给规模（当年新增书） | **2022** | 37,095 | 14,574 |

顺序是 **2015 认可先起 → 2019 爆款见顶 → 2022 规模才见顶**。供给涨到 11.7 倍的同时，
每千本获 banner 的能力从 22.4‰ 跌到 1.08‰（−95%）——名额没变，分母变了。

2022 之后供给三年跌 61%（37,095 → 27,215 → 18,877 → 14,574）。**这 22,521 本的缺口里
73% 是「新人没来」，不是老作者停笔**——人均产量几乎没动（1.42 → 1.27），塌的是活跃人数
（24,181 → 10,720）。同期新人首年留存从 17.7% 跌到 10.7%，新生代最终拿到 banner 的比例
从 3.31% 跌到 0.11%。详见 [`quarry/reports/01_supply.md`](./quarry/reports/01_supply.md)。

而「24.6 万本」这个数字本身要打折：**只有 3,766 本（1.53%）是「完结且 ≥30 万字」**。
一半的书不到 1 万字，81% 已断更，断更里又有一半死在 1 万字之前。只想筛「≥30 万字」
的话有 52.7% 是坑，连 ≥100 万字都还有 31.4%。「成品率」（每千本新书产出几个完结长篇）
2016 见顶 28.8‰ 后腰斩到 13.3‰（2022），2025 全年只产出 **225 本**可读完的新书。

> 口径：已剔除版权方账号（天闻角川 / 天闻角川2号机 / HJ文库 / 丸山黄金）的 **47 本引进日轻**（`novels.flg_import`）。这批书由版权方
> 账号整批上架、banner 由版权方提供，不代表 SFACG 对原创作品的认可。剔除后 2006–2009 年
> 原创 banner **归零**——那四年的 banner 全给了引进书。

详见 [`quarry/reports/00_timeline.md`](./quarry/reports/00_timeline.md)（时间轴）
与 [`01_supply.md`](./quarry/reports/01_supply.md)（供给归因）、
[`02_readability.md`](./quarry/reports/02_readability.md)（可读性结构）。

## 快速开始

```bash
cd quarry
uv sync
uv run pytest -q          # 46 项断言：规模 / 归一化 / 清洗 / 定年 / 可复现 / 供给归因 / 可读性 / 状态语义
```

数据集（约 46 MB）随 [GitHub Release](https://github.com/interset-wq/strata/releases) 发布，不进 git。
解压到 `quarry/datasets/v1/` 后即可直接分析。**字段语义、NULL 含义、哪 5,320 本能排序、
哪些数被截断过——先看 [`quarry/DATASET.md`](./quarry/DATASET.md)**：

```python
import duckdb
con = duckdb.connect("quarry/datasets/v1/strata-v1.duckdb", read_only=True)
con.sql("select year, books_new, banners, grant_per_1k from era_stats order by year")
```

从上游原始快照重建（需要自己准备三片 sqlite 到 `quarry/data/raw/chunks/`）：

```bash
uv run python -m quarry.build_dataset       # raw → datasets/v1
uv run python -m quarry.report_timeline     # 出时间轴的图
uv run python -m quarry.report_supply       # 出供给归因的图
uv run python -m quarry.report_readability  # 出可读性结构的图
```

## 方法上守的六条线

1. **右删失**：2026 年的书只被观测了几个月，不能和 2016 年的书比总字数、总人气。
   banner 书创作跨度中位 **2.5 年**，所以「2025 只有 6 个 banner」是下界，不是实况。
2. **存活偏差 68.3%**：nid 是自增主键、号不重用，77.6 万个历史号里只有 24.6 万本还在架，
   其余 52.9 万个号对应的书已被删或被屏蔽；另有 4.5 万本号还在但数值被清零（正文取不到）。
   所以「某年新增 N 本」是下界，分母也不能用 24.6 万。
3. **`click_num` 跨年不可比**：它是累计曝光量 × 当年用户规模。唯一可跨年比较的是**当年全库分位**。
4. **口径写在数字旁边**：标签密度是 top-99 截断口径，banner 是切片口径——不写清楚，半年后自己都会被自己的数字骗。
5. **不把工程实现当数据事实**：上游把库拆成 `cold/warm/hot` 只为分批解压、加快首屏，切分依据就是 `status`（2/4、5/6、3），零信息量。数据集不保留该列，凡需「完结/断更」的区分直接用 `outcome`。2026-05 之后新书只剩约 7% 可见，判据是 **nid 密度**而不是分片。
6. **不继承上游的主观分层**：上游 `status` 把「结局」和「A 标」压成一列，而 A 标（5=断更A、6=完结A）只是按「banner / 人气≥1000万 / 长评≥60 / 收藏≥1万 / 赞≥1万」派生的**成绩**标记——判定式在 243,193 行上零反例，即 5/6 相对 2/4 无任何结局信息。拆成 `outcome`（三值结局）+ `stats_precise`（数值精度），A 组整体丢弃。**后果不小**：把 status 6 当「长篇小说」的代表会得到 108.7 万字的中位数，那是选择偏差；真实的完结长篇里 65% 落在未达标组。

## 数据来源与致谢

数据来自 SF 轻小说（菠萝包轻小说）的公开页面与 API，仅用于个人研究与书目分析，
不含任何正文内容。上游原始快照与凭据均不入库。

## 许可

代码 MIT（见 [`LICENSE`](./LICENSE)）。`docs/` 下的分析文字与图表版权归作者所有。

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
| 原创作品认可密度（每千本新书获 banner） | **2015** | 22.7‰ | 0.41‰ |
| 认可绝对量（当年创建的书最终获 banner） | **2016** | 95 本 | 6 本 |
| 单本爆发力（当年新书人气 P99） | **2019** | 272 万 | 89 万 |
| 供给规模（当年新增书） | **2022** | 37,095 | 14,574 |

顺序是 **2015 认可先起 → 2019 爆款见顶 → 2022 规模才见顶**。供给涨到 11.7 倍的同时，
每千本获 banner 的能力从 22.7‰ 跌到 1.08‰（−95%）——名额没变，分母变了。

2022 之后供给三年跌 61%（37,095 → 27,215 → 18,877 → 14,574），这条曲线没有删失，最硬。

> 口径：已剔除天闻角川 / HJ文库的 **46 本引进日轻**（`novels.flg_import`）。这批书由版权方
> 账号整批上架、banner 由版权方提供，不代表 SFACG 对原创作品的认可。剔除后 2006–2009 年
> 原创 banner **归零**——那四年的 banner 全给了引进书。

详见 [`quarry/reports/00_timeline.md`](./quarry/reports/00_timeline.md)。

## 快速开始

```bash
cd quarry
uv sync
uv run pytest -q          # 24 项断言：规模 / 归一化 / 清洗 / 定年 / 可复现
```

数据集（约 46 MB）随 [GitHub Release](https://github.com/interset-wq/strata/releases) 发布，不进 git。
解压到 `quarry/datasets/v1/` 后即可直接分析：

```python
import duckdb
con = duckdb.connect("quarry/datasets/v1/strata-v1.duckdb", read_only=True)
con.sql("select year, books_new, banners, grant_per_1k from era_stats order by year")
```

从上游原始快照重建（需要自己准备三片 sqlite 到 `quarry/data/raw/chunks/`）：

```bash
uv run python -m quarry.build_dataset     # raw → datasets/v1，约 4 秒
uv run python -m quarry.report_timeline   # 出图
```

## 方法上守的四条线

1. **右删失**：2026 年的书只被观测了几个月，不能和 2016 年的书比总字数、总人气。
   banner 书创作跨度中位 **2.5 年**，所以「2025 只有 7 个 banner」是下界，不是实况。
2. **存活偏差**：库里只有今天仍在架的书，被删除、下架的全部不可见。所有「某年新增 N 本」都是下界。
3. **`click_num` 跨年不可比**：它是累计曝光量 × 当年用户规模。唯一可跨年比较的是**当年全库分位**。
4. **口径写在数字旁边**：标签密度是 top-99 截断口径，banner 是切片口径——不写清楚，半年后自己都会被自己的数字骗。

## 数据来源与致谢

数据来自 SF 轻小说（菠萝包轻小说）的公开页面与 API，仅用于个人研究与书目分析，
不含任何正文内容。上游原始快照与凭据均不入库。

## 许可

代码 MIT（见 [`LICENSE`](./LICENSE)）。`docs/` 下的分析文字与图表版权归作者所有。

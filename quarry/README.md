# quarry

SFACG 二十年书目数据的**勘测**项目。名字取「采石场」——从沉积层里开采样本，出数据与基线，
不做产品判断。App 本体叫「书层 Strata」，在 `../app/`，与本项目分开命名。

## 数据主权：我们只发布自己的数据集

上游 `Novel Hub` 的三片 sqlite 只是**构建原料**，不随本项目发布，也不进 git。
所有分析与后续开发只依赖 `datasets/`——我们自己产出的数据集。

```
data/raw/chunks/*.sqlite       上游三片原始快照   191 MB   不进 git / 不随 Release
        │
        ▼  uv run python -m quarry.build_dataset
datasets/v1/                   我们的数据集        46 MB   不进 git / 随 Release 发布
  ├── strata-v1.duckdb         单文件，开箱即用     24.3 MB
  ├── parquet/*.parquet        工具无关，长期归档   21.5 MB
  └── manifest.json            版本 + 行数 + sha256 + 来源 + 锚点指纹
```

### 数据集内容

| 表 | 行数 | 说明 |
|---|---|---|
| `novels` | 246,045 | 书目主表，含 6 个 `flg_` 质量标记 |
| `novels_era` | 246,045 | **nid 定年**：`est_date` / `est_year` / `confidence` |
| `era_stats` | 21 | **年表**：每年新增书、作者、banner、人气分位、删失标记 |
| `tags` | 106 | 标签，`name` 为唯一键 |
| `novel_tags` | 742,546 | 书↔标签 |
| `authors` | 137,965 | 按 name 去重（原 140,638，跨片重复 2,673） |
| `contests` | 99 | 按 name 去重（原 209，跨片重复 110） |

### 定年：为什么用 nid，为什么可信

`novels.id` 就是站点全局自增主键，严格单调。`data/anchors/nid_anchors.jsonl` 里有
**91 个 API 实测锚点**（`nid → addTime`），0 次真逆序，覆盖 `2,242 ~ 777,879` 全库。

- 插值在 **log(nid)** 空间做：nid 消耗速率从 1.8 nid/天（2006）涨到 328 nid/天（2025），
  差 180 倍，线性插值会系统性高估早期速度。留一法实测：log 最大误差 237 天，线性 356 天。
- **92% 的锚点误差 ≤ 1 天**；误差全部集中在 2006–2010 的锚点稀疏区。
- **2017 年是可信度分水岭**：锚点按 2.5% 分位采样，书多的年份锚点密。2016 及以前
  `confidence` 几乎全是 `low`（两侧锚点隔 1–2 年），2017 起 0% low（精度到天）。
- `last_update` 给出误差的独立测量：12.5% 的书 `est_date` 晚于最后更新，中位差 5 天。

改锚点必须同步跑 `uv run pytest -q`，`test_leave_one_out_accuracy` 与
`test_dating_precision_splits_at_2017` 会拦住精度退化。

补锚点（快照更新后尾部会变长）：

```bash
uv run python -m quarry.tools.refill_anchors --lo 777879 --hi 800000 --n 12
```

### 两条复现路径

**A. 直接用发布的数据集**（推荐，秒级）

```bash
cd quarry
uv sync
# 从 GitHub Release 下载 strata-v1 并解压到 datasets/v1/
uv run pytest -q          # 24 项断言，含 manifest 与定年精度校验
```

**B. 从上游原始快照重建**（需要自己拿到那三片 sqlite）

```bash
# 放置到 data/raw/chunks/{cold,warm,hot}_chunk.sqlite
cd quarry
uv sync
uv run python -m quarry.build_dataset
uv run pytest -q
```

`manifest.json` 记录了三个源文件的 sha256——重建后核对它，就能确认拿到的是同一批原料。
全局 `tag_id` 按字典序分配，`authors`/`contests` 去重取 `top_novel_clicks` 最大者，
因此**同一份原料必定构建出完全相同的数据集**。

## 构建时做的四件事

1. **归一化**：三片 tags 各自编号，同 id 率 0%，id 是废号。按 `name` 重建全局 id，264 次观测 → 106 个唯一名。
2. **清洗**：只修物理不可能的值。`like_num < 0`（58 条）置 NULL 并打 `flg_like_fixed`；
   其余异常一律只标记不删除。
3. **去重**：`authors` / `contests` 跨片重复，按 name 合并，并重映射 `novels.contest_id`。
4. **定年**：91 个锚点 + log 插值给全库算 `est_date`，再聚合成 `era_stats` 年表。

## 清洗原则：修错误，不抹病灶

| 类型 | 处理 | 例子 |
|---|---|---|
| 物理不可能 | 置 NULL + 标记 | `like_num = -11` |
| 口径差异 / 缺失 | 只标记，保留原值 | `praise > click`（2,094）、`comment_num` 为 NULL（98%，**不等于 0**） |
| 结构性事实 | 不动，写进文档 | 无标签书 12,187、标签数上限 7（top-99 截断）、默认封面 34,641 |

`flg_` 列：`placeholder_title` / `word_zero` / `default_cover` / `like_fixed` /
`praise_gt_click` / `comment_missing`。

## 已知数据缺陷（分析时必须记住）

- **tags 是 top-N 截断采样**：cold 片 72 万条关联只挂在 99 个标签上（每标签约 7,290 本），
  `tags.id` 稀疏到 710,395，单本标签数上限 7。所谓「按年标签密度」是 top-99 口径下的数字，
  老书偏用长尾标签会被低估；趋势方向可信，绝对值不可当全量。
- **banner 与 status 强绑定**：banner 只出现在 `status ∈ {3 连载中, 5 断更A, 6 完结A}`，
  cold 片 24 万本（`2 已完结 / 4 断更`）一条 banner 都没有。A 后缀疑似**等级标记**而非更新状态，
  待验证。
- **`LIKE` 大小写**：SQLite 对 ASCII 不敏感、DuckDB 敏感。默认封面 34,641 含 2 条
  `defaultnew.jpg` 小写变体，用 `LIKE` 会漏成 34,639。统一用 `ILIKE`。
- **`comment_num` / `review_num` 仅 4,690 本有值**（1.9%），NULL = 未采集。
- **存活偏差**：上游已排除「下架」状态的书，库中只有今天仍在架的作品，
  所有「某年新增 N 本」都是下界。
- **banner 授予有右删失**：banner 书创作跨度中位 2.5 年（P75 4.6、P90 7.1），
  只有 15% 在 1 年内完成。所以最近 3 年的授予量还没发生完，`era_stats.censored`
  标出这批年份——**2024 年 11 个、2025 年 7 个是下界，不是实况**。
- **`view_num` / `click_num` 跨年不可比**：它是累计值，等于「当年用户规模 × 曝光时间」。
  2015 年创建的书已积累 11 年，2025 年的只有 1.5 年。做跨年比较只能用比例类指标
  （`grant_per_1k`、`vip_pct`）或当年内部分位。
- **nid 区间填充率 31.7% 不能当下架率**：775,638 个 nid 宽度里只有 246,045 本书，
  但无法确认 nid 是否被非小说对象共用（平均 3.15 个 nid 才 1 本）。待查。

## 三条硬规则

1. **分析代码只读 `datasets/`，永不读 `data/raw/`**。raw 随时可以删掉。
2. **总量断言失败就停**。`novels != 246,045` 说明原料换了，此时任何结论都不可信。
3. **异常是病灶，不是脏数据**。提前「修好」会掩盖真问题；要修就同时留下 `flg_` 标记。

## 目录

```
quarry/
├── src/quarry/
│   ├── config.py           路径、基线常量、数据集版本、锚点路径
│   ├── build_dataset.py    raw → datasets/v1（归一化 + 清洗 + 去重 + 定年）
│   ├── era.py              nid → 日期：插值、留一法验证、置信度
│   ├── annual.py           年度年表 era_stats + 删失标记
│   ├── report_timeline.py  出时间轴报告图
│   └── tools/refill_anchors.py   补锚点（快照更新后用）
├── data/anchors/           91 个 nid 锚点（**入库**，随数据集发布）
├── datasets/v1/            自有数据集（gitignored，随 Release 发布）
├── data/raw/chunks/        上游原料（gitignored，不发布）
├── sql/                    分析查询
├── tests/                  24 项断言
├── reports/                产出报告与图表
└── notebooks/              探索（结论必须落回 src/ 或 tests/）
```

## 已出报告

| 报告 | 内容 |
|---|---|
| [`reports/00_timeline.md`](reports/00_timeline.md) | 时间轴：定年模型、年表、三阶段、删失警告、"黄金五年 15–20"检验 |

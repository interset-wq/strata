# RAW.md
> 三片快照：`cold` / `warm` / `hot` SQLite，共 246,045 本书，是 `build_dataset.py` 的输入原料，**不等于 `datasets/v1` 数据集**。本文面向数据集构建者，用于识别原始数据缺陷；分析代码只读 `datasets/v1`。

快照信息：
- 快照日期：2026-06-13
- 解压总大小：137.7 MB；gzip 压缩包 62.1 MB
- 表结构：三片完全一致，5 张表、11 个索引
- 数据边界：`cold` 240,725｜`warm` 2,515｜`hot` 2,805；跨片 `novels.id` 无重复
- gz sha256：cold `920f88bb…` / warm `74b909af…` / hot `1a8514f7…`

| 文件 | 用途 | 阅读时机 |
|---|---|---|
| RAW.md（本文） | 原料来源、分片逻辑、ID 隔离、数据缺陷 | 构建数据集、核对 raw/数据集行数、数值异常排查 |
| DATASET.md | `datasets/v1` 表结构、字段语义、体检SQL | 编写查询、引用指标前 |

## 30 秒上手
文件路径：`quarry/data/raw/chunks/`，纳入 `.gitignore`，不进入 Git、不随 Release 分发。
- 无该原料：无法重建数据集
- 已有 `datasets/v1`：无需该原料

```python
import sqlite3
con = sqlite3.connect("file:data/raw/chunks/cold_chunk.sqlite?mode=ro", uri=True)
con.execute("select count(*) from novels").fetchone()
```

```sql
attach 'cold_chunk.sqlite' as cold;
attach 'warm_chunk.sqlite' as warm;
attach 'hot_chunk.sqlite'  as hot;
select 'cold' src, count(*) from cold.novels
union all select 'warm', count(*) from warm.novels
union all select 'hot',  count(*) from hot.novels;
```
DuckDB 兼容写法：`attach 'cold_chunk.sqlite' as cold (type sqlite)`。

## 文件清单
| chunk | 文件 | novels | 解压字节 | gz字节 | 压缩率 | 上游App定位 |
|---|---|---|---|---|---|---|
| cold | cold_chunk.sqlite | 240725 | 134156288 | 60506244 | 45.1% | 静态存量，按需解压 |
| warm | warm_chunk.sqlite | 2515 | 1593344 | 734620 | 46.1% | 优质存量合并包 |
| hot | hot_chunk.sqlite | 2805 | 1925120 | 889167 | 46.2% | 首屏加载、按月更新 |
| 合计 | 三片 | 246045 | 137674752 | 62130031 | 45.1% | — |

| chunk | 解压sha256 |
|---|---|
| cold | `0e2b90f09489e26137332831fa96cf2a6450efee016e933d41d7d2a9753372e0` |
| warm | `7399d1045bac670cb303936e51c09b7ada9928e5ce42e46023e4f739aef155cd` |
| hot | `89fa62daa0e1c14c727919d91dbf905db2b606b23a9369599da38b473d115411` |

## 分片规则：按 status 划分
| chunk | status取值 | 业务含义 |
|---|---|---|
| cold | 2（已完结）、4（断更） | done + dead |
| warm | 5（断更A）、6（完结A） | A标优质完结/断更 |
| hot | 3（连载中） | ongoing |

三片不是随机切分，成绩层差异极大：`warm` 的 VIP（`ptype=4`）占 **93.0%**（2,337/2,515），`hot` 17.4%、`cold` 仅 1.7%。同理 `has_banner=1` 的 667 本里 638 本在 `warm`、29 本在 `hot`、**cold 为 0**。

### 分层样本特征
> 预留章节，用于补充三类分片样本分布、指标分布、长尾特征说明。

## 表与字段
### novels（16列，一书一行）
```sql
create table novels (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT,
  genre INTEGER DEFAULT 1,
  status INTEGER DEFAULT 1,
  ptype INTEGER DEFAULT 1,
  has_banner BOOLEAN DEFAULT 0,
  word_num INTEGER,
  click_num INTEGER,
  praise_num INTEGER,
  like_num INTEGER,
  comment_num INTEGER,
  review_num INTEGER,
  contest_id INTEGER,
  cover TEXT,
  last_update DATETIME
);
```

- `id`：全局唯一，跨片不重复。跨度 2,242–777,879，号段里只有 **31.7%** 有书（775,638 个号对应 246,045 本，**68.3% 空洞**）。**空洞就是下架/屏蔽**：SFACG 用自增主键、号只增不重用，抓取又覆盖了列表页全量分页（不是按 ID 抽样），被删或被屏蔽的书不再出现在列表里、号就永久空着。所以 **775,638 是「历史上建过的书」，246,045 是「今天还在架的」**——约 52.9 万个号对应的书已不可见，这才是下架率（且是下界，见下条）。
- `author`：字符串类型，非稳定业务主键；平台规定作者名唯一，不支持作者改名。可能混入非法字符，建议后续同理非法字符统一替换为空格。三片 140,638 行，按 name 去重后 **137,965**（重复 2,673 行）。
- `genre` / `ptype`：字段默认值都是 1，快照内**没有取值 1 的记录**——`genre ∈ 2..10`（9 类），`ptype ∈ {2,3,4}`（免费/签约/VIP）。
- `last_update`：UTC 时间串（`+00:00`），**不是上架时间**。三片抓取时点不同：cold 最晚 2026-06-09、warm 2026-06-08、hot 2026-06-13。
- `cover`：默认封面标识存在大小写两种写法（`defaultNew.jpg` / `defaultnew.jpg`）；DuckDB `LIKE` 大小写敏感，直接查询会造成漏检。
- `comment_num` / `review_num`：**98.1% 为 NULL**（241,355/246,045），两列 NULL 完全同步。语义为未采集，不等于数值 0。分片看：cold 98.5% / warm 73.7% / hot 86.6% NULL——所以「A 标 = 走过详情接口」也不成立（warm 里近四分之三同样没有评论数）。
- 数值字段 **≤0 = 下架/屏蔽**：这是 SFACG 的固有 bug，正文取不到时计数被清零而不是报错，行却还留着。所以同一批下架书有两种可观测形态（见下）：
  - `word_num=0`：497 本（cold 496 + hot 1），其中 496 本 `click_num>0`，最高一本 169,726 人气 / 1,385 收藏——**有读者、正文清零**，正是「号还在但看不了正文」的样本；只有 1 本 click 也为 0。它区别于 NULL（NULL 是这一列没抓到）
  - `click_num=0`：4,476 本，其中 4,475 本 `word_num>0`——字数还在、人气被清零
  - `like_num=0`：30,117 本；`praise_num=0`：33,196 本；四项全为 0 的只有 **1 本**
  - 按「任意一项 ≤0」统计，cold 片有 **44,784 本（18.6%）**、全库 **45,165 本（18.4%）** 是下架残骸：行还在、数值被清空
  - `like_num` 是唯一出现负值的列：58 本（全在 cold），-1 到 -11，属计数抖动，不是哨兵值。`build_dataset` 会把它们置为 NULL——`datasets/v1` 里 `like_num` 的 58 个 NULL 就是这 58 行
  - 唯一要留神的是 hot 片：381 本有 ≤0，其中 **267 本有正文、有人气**，只是收藏或赞为 0（最高 10.8 万字 / 357 人气 / 0 收藏，`last_update` 在 5 月）。能进 hot 说明还在架，这里的 0 更像真 0——判 hot 的下架必须结合 `last_update`，不能照搬 cold 的规则
- `like_num` 语义为收藏量；`praise_num` 语义为点赞量（与 `click_num` 三者不同源，不要混用）。

### 下架/屏蔽的两种形态
平台对下架书的页面不返回 404（`book.sfacg.com/Novel/{nid}/` 照样给 200），`status` 里也没有任何代码写入 7——**raw 里不存在「已删除」标记**，只能靠下面两条反推：

| 形态 | 表里长什么样 | 规模 | 能拿到什么 |
|---|---|---|---|
| ① 号失效 | `novels` 里没有这一行 | ~52.9 万个号（68.3%） | 只有一个空洞，无标题无作者 |
| ② 号还在、内容清零 | 行在，但数值 ≤0 | 45,165 本（18.4%） | title/author/genre/last_update 都还在，可做下架分析 |

两者互不重叠，合起来构成完整的不可读集合：**77.6 万个历史号段里，只有约 20.1 万本（246,045 − 45,165）今天还能读到正文，占 25.9%**。这也是为什么上游给不出下架清单：没有状态码可用，也没有删除时间。分析时 **②不能当真实低互动留在样本里**，它会把字数、人气、收藏的分位数整体拉低。

顺带一个用法：nid 单调递增，空洞可以按两侧存活书的 `last_update` 内插到年份上，估「含已删书」的年度建书量。这是插值不是观测，用的时候要标明。

### 三套互不相通的 ID 空间
`novels.id` 是唯一可跨片 join 的键；`authors` / `tags` / `contests` 各自独立自增，而且 **`INSERT OR IGNORE` 跳过时也会消耗序号**，导致 id 全是断号：

| 片 | authors | tags | contests / novel_tags |
|---|---|---|---|
| cold | 136,499 行，id 240,726–377,224 | **99 行**，id 1–710,395 | contests 97 行到 91,516；novel_tags 721,748 |
| warm | 1,652 行，id 2,516–4,167 | 79 行，id 1–8,466 | contests 55 行；novel_tags 8,656 |
| hot | 2,487 行，id 2,806–5,292 | 86 行，id 1–5,577 | contests 57 行；novel_tags 12,142 |

`cold.authors` 从 **240,726** 起，正好是「240,725 本书各插一次 + 136,499 行」的烧号结果（`sqlite_sequence` = 377,224）；`cold.tags` 只有 99 行却撑到 710,395 号，因为每挂一个标签就烧一个号（seq 721,748 = novel_tags 行数）。**结论：这三张表的 id 是片内编号，跨片只能按 name join**，`build_dataset.py` 已把它们重映射成全局 id。

顺便：`tags` 也不是全站字典，而是「本片用到的子集」——cold 99 / warm 79 / hot 86，并集 106，cold 恰好缺 7 个。在单片上算「全站标签热度」会漏。

## status 派生逻辑
平台原生仅两类状态：`连载中`、`已完结`；其余状态为上游派生伪状态。派生判定代码不在公开仓库，判定逻辑不可复现。

| status值 | 标识 | 来源 |
|---|---|---|
| 1 | 其他 | 兜底状态，本快照无数据 |
| 2 | 已完结 | 平台原生 |
| 3 | 连载中 | 平台原生 |
| 4 | 断更 | 上游判定：连载状态 + 连续90天无更新 |
| 5 | 断更A | A标：断更，满足 banner/click≥1000w/review≥60/like≥1w/praise≥1w 任一条件 |
| 6 | 完结A | A标：已完结，满足A标阈值条件 |
| 7 | 下架 | 上游标记，本快照已过滤该类数据 |

**判定时点不是快照日，`status=4` ≠「现在已断更」**：779 本 `status=4` 的书 `last_update` 在 2026-03-15 之后。cold 的断更书按月分布 2026-01 `1,043` / 02 `904` / 03 `1,239` / **04 `97` / 05 `2` / 06 `3`**——判定冻结在 2026 一季度。机制在爬虫的 cutoff：抓到 `last_update` 超出 7 天窗口的书就 `should_stop`，窗口外的书不再被访问，`status` 也不再更新。要按定义筛「已断」，得自己用 `last_update` 算，两个口径差 779 本。

同理 `5`/`6` 是发版前按阈值打的标，上游自己在文档里称其为 **pseudo status**；`A` 只表示「banner 或四项阈值之一达标」，与结局、质量都无关。

## raw → datasets/v1 守恒映射
| 指标 | raw合计 | datasets/v1 | 差异来源 |
|---|---|---|---|
| novels | 246045 | 246045 | 无 |
| done | 43581 | 43581 | status 2+6合并 |
| dead | 199659 | 199659 | status 4+5合并 |
| ongoing | 2805 | 2805 | 无 |
| stats_precise | 5320 | 5320 | status 3/5/6 = warm+hot 全量 |
| has_banner | 667 | 667 | 无 |
| novel_tags | 742546 | 742546 | tag_id全局重映射 |
| authors | 140638行 | 137965 | 跨片同名去重 |
| contests | 209行 | 99 | 跨片同名去重 |
| tags | 264行 | 106 | 跨片同名去重 |
| `like_num < 0` | 58 | 0（转 NULL） | 负值置空，见上 |

> `stats_precise` 命名误导：它等于 **warm 全量 + hot 全量**（详情通道两片），既不是「精度更高」，也不等于 A 标（A 标只有 5/6 那 2,515 本）。行数 5,320 不用动，解释要换。

## 原料体检SQL & 锚点
```sql
-- 分片计数、ID边界
select 'cold' c, count(*) n, min(id) lo, max(id) hi from cold.novels
union all select 'warm', count(*), min(id), max(id) from warm.novels
union all select 'hot',  count(*), min(id), max(id) from hot.novels;

-- 跨片ID重复校验
select
  (select count(*) from cold.novels)
+ (select count(*) from warm.novels)
+ (select count(*) from hot.novels)
- (select count(*) from (
    select id from cold.novels union
    select id from warm.novels union
    select id from hot.novels)) as dup; -- 预期结果 0
```

校验锚点（任意一项不匹配，停止数据集构建流程）：
1. 分片行数：240725 / 2515 / 2805；并集总数 246045，无重复ID
2. status取值约束：cold ∈ {2,4}；warm ∈ {5,6}；hot ∈ {3}
3. cold 分片 `has_banner=1` 样本数量为 0（另两片 638 / 29）
4. cold `like_num` 最大值 9999；warm `like_num` 最大值 354531
5. `click_num >= 1000000` 的样本共 3,745 本，其中末三位非零数量 = 0
6. cold.authors 最小 id = 240726；cold.tags 行数 = 99 而最大 id = 710395
7. authors 去重后 137965；tags 去重后 106（分片 99/79/86）；contests 去重后 99（分片 97/55/57）
8. novel_tags 关联记录总数 742546（721748 + 8656 + 12142）
9. `last_update` 最大值：hot 2026-06-13（cold 2026-06-09 / warm 2026-06-08）；hot 最小值 2026-04-03
10. `like_num < 0` 共 58 本，全部在 cold；warm/hot 均为 0
11. ID 空洞 529,593 个（775,638 − 246,045），即已删号的书；数值 ≤0 本数 cold 44,784 / 全库 45,165
12. 文件sha256与manifest清单一致

全部锚点校验通过后，执行构建命令：
```bash
uv run python -m quarry.build_dataset
```
产出固定哈希的数据集，pytest 断言全部通过。

## 六种会算错的写法
| 写法 | 后果 |
|---|---|
| 只拿 246,045 本谈「历史上建过多少书」 | 68.3% 的号已删、书已不可见；历史总量应按 775,638 个号算 |
| 把 ≤0 的书当真实低互动留在样本 | 45,165 本（18.4%）是下架残骸，字数/人气/收藏的分位被整体拉低 |
| `authors.id` / `tags.id` 跨片 join | 三套独立自增空间且烧号，必错；只能按 name |
| 用单片 `tags` 算标签热度 | 本片是子集（99/79/86），cold 缺 7 个标签 |
| `status=4` 当「现在已断更」 | 779 本与 `last_update` 矛盾；判定冻结在 2026Q1 |
| 直接在 raw 上跑分析 | 分析只读 `datasets/v1`，raw 是构建输入，随时可能被替换 |

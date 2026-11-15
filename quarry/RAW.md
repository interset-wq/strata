# 上游原料字典 · 三片 sqlite

> **一句话**：这是从 novly Release 下载的**未经加工的三片快照**——`cold` / `warm` / `hot`
> 各一个 sqlite，合计 246,045 本书。它们**不是**我们的数据集（那是 `DATASET.md` 描述的
> `datasets/v1/`），只是 `build_dataset.py` 的输入。
>
> 读这个文件的目的只有一个：**知道原料哪里脏、哪里缺、哪些列不能直接用**，
> 免得在 raw 上算出漂亮但错的数字。

```
快照日 2026-06-13 · 三片解压 137.7 MB / gz 62.1 MB · 五张表 · 11 个索引 · 三套互不相通的 id 空间
novels 240,725 + 2,515 + 2,805 = 246,045（跨片 0 重复）· novel_tags 742,546 · 表结构三片完全一致
sha256(gz) cold 920f88bb… / warm 74b909af… / hot 1a8514f7…
```

**这两个文件的分工**：

| 文件 | 讲什么 | 什么时候读 |
|---|---|---|
| `RAW.md`（本文） | 原料：从哪来、怎么切的、id 为什么不能混、哪片被截断过 | 要跑 `build_dataset`、要核对 raw 与数据集的行数、怀疑数字对不上时 |
| [`DATASET.md`](./DATASET.md) | 产物：`datasets/v1` 的 7 张表、字段语义、两套精度、体检 SQL | **要写查询、要引用任何数字之前** |

分析代码**只读 `datasets/`，永不读 raw**（`config.py` 顶部就这么写的）。本文是给
构建者看的，不是给分析者看的。

---

## 0. 30 秒上手

文件在 `quarry/data/raw/chunks/`，**不进 git、不随 Release 发布**（`.gitignore: quarry/data/raw/`）。
没有这三个文件就重建不了数据集；有 `datasets/v1/` 就完全不需要它们。

```python
import sqlite3
con = sqlite3.connect("file:data/raw/chunks/cold_chunk.sqlite?mode=ro", uri=True)
con.execute("select count(*) from novels").fetchone()      # (240725,)
```

三片并集就是全库，`novels.id` 是唯一跨片可 join 的键。先把三片挂成 schema：

```sql
attach 'cold_chunk.sqlite' as cold;
attach 'warm_chunk.sqlite' as warm;
attach 'hot_chunk.sqlite'  as hot;

select 'cold' src, count(*) from cold.novels
union all select 'warm', count(*) from warm.novels
union all select 'hot',  count(*) from hot.novels;
-- cold 240725 / warm 2515 / hot 2805
```

DuckDB 也一样：`attach 'cold_chunk.sqlite' as cold (type sqlite)`。

---

## 1. 血缘：从站内页面到这三个文件

```
sfacg.com 的页面与 API            UGC 本体，唯一的事实来源
        │  novel_hub 爬虫（Light Nook Labs，MIT）
        ▼
release/*.jsonl                   爬虫产物：每行一本书，status/tags 是**字符串**
        │  nookdata 修复（负值、嵌套标签、ptype 降级）
        ▼
jsonl_fixed/*.jsonl               修复版 JSONL
        │  novly `scripts/build_chunks.py`
        ▼
{cold,warm,hot}_chunk.sqlite       ← **本文的对象**
        │  gzip -9 → novly Release `assets/chunks/*.sqlite.gz`
        ▼
（我们下载并解压）
        │  quarry `build_dataset.py`
        ▼
datasets/v1/{duckdb, parquet}     我们的数据集，见 DATASET.md
```

四件事必须记住：

1. **每一级都在丢东西**，且不可逆。下架的书在第一级就不见了，`comment_num` 在上游
   采集阶段就没有，后面任何一级都补不回来。
2. **`status` 是上游的主观判定**，不是平台字段（§6.1）。到我们这里已经拆成 `outcome`。
3. **切分是打包行为，不是数据属性**（§3）。上游做这件事只为首屏加载。
4. 上游代码 MIT，**数据本身没有授权**。所以 raw 只留在本地，发布的是我们重新构建的
   `datasets/v1`；再分发 raw 是另一件事，不要顺手做。

---

## 2. 文件清单

| chunk | 文件 | novels | 解压字节 | gz 字节 | gz 占比 | 在 App 里的角色（上游设计） |
|---|---|---|---|---|---|---|
| cold | `cold_chunk.sqlite` | **240,725** | 134,156,288 | 60,506,244 | 45.1% | 永不更新，首次安装后按需解压 |
| warm | `warm_chunk.sqlite` | **2,515** | 1,593,344 | 734,620 | 46.1% | 冷合并时并入主库 |
| hot | `hot_chunk.sqlite` | **2,805** | 1,925,120 | 889,167 | 46.2% | 首屏先解压它，月更 |

合计 **137.7 MB 解压 / 62.1 MB gz**。`cold` 一片占 97.4% 的体积，`warm + hot` 只有 3.5 MB
——这两个小片才是「现在还在动」的部分，所以上游让它们单独发版。

物理形态（三片一致，已实测）：

- `page_size = 4096`，`journal_mode = delete`，`user_version = 0`，无 WAL 残留
- 每片 **11 个索引**，`novels` 上 7 个（status/genre/ptype/click_num/author/has_banner/last_update），
  `novel_tags` 上 2 个，`authors` 上 2 个。**索引是给 App 的查询路径建的，不是给分析建的**
- 三片 `create table` 语句**逐字节相同**——`novels`/`authors`/`tags`/`novel_tags`/`contests`
  五张表，可以直接 `union all` 表结构

文件指纹（与 `datasets/v1/manifest.json` 里 `source` 段完全一致，可用来确认拿到的是同一批原料）：

| chunk | sha256（解压后 = manifest 记录值） |
|---|---|
| cold | `0e2b90f09489e26137332831fa96cf2a6450efee016e933d41d7d2a9753372e0` |
| warm | `7399d1045bac670cb303936e51c09b7ada9928e5ce42e46023e4f739aef155cd` |
| hot | `89fa62daa0e1c14c727919d91dbf905db2b606b23a9369599da38b473d115411` |

`gzip -dc x.sqlite.gz | sha256sum` 与表里一致，说明 gz 无损、没被重新打包过。

---

## 3. 切分规则：其实是按 `status` 切的

`scripts/build_chunks.py` 的 `get_chunk_category()` 只有一条判据：`status`。
实测对得上，一行为不差：

| chunk | 收纳的 `status` | 实测本数 | 对应结局 |
|---|---|---|---|
| cold | 2 已完结 / 4 断更 | 42,193 + 198,532 = **240,725** | done + dead |
| warm | 5 断更A / 6 完结A | 1,127 + 1,388 = **2,515** | done + dead（成绩好的那批） |
| hot | 3 连载中 | **2,805** | ongoing |

并集 246,045，**跨片 `novels.id` 重复 0 条**。所以「三片」等价于「按 status 分三组」，
不携带任何 status 之外的信息——这也是 `datasets/v1` 里不保留 `chunk` 列的原因
（`DATASET.md` §4.2）。

### 3.1 三片不是随机分组，是三个质量层

| | cold | warm | hot |
|---|---|---|---|
| 字数中位 | **10,088** | **888,500** | 91,682 |
| 字数最小 | 0（496 本空壳） | **22,588** | 0（1 本） |
| 字数最大 | 8,532,591 | 9,563,189 | 21,762,745 |
| VIP 占比（ptype=4） | 1.7% | **92.9%** | 17.4% |
| banner | **0 本** | 638 本 | 29 本 |
| 有标签的书 | 94.9% | 99.7% | 100% |
| 平均标签数 | 3.16 | 3.45 | 4.33 |

`warm` 里连一本 2 万字以下的书都没有——A 标只发给成绩达标的完结书，短篇根本进不来。
这就是「拿 `status=6` 当长篇小说会得到 108.7 万字中位数」的物理来源：warm 是**筛选后的
样本**，不是随机抽样。

### 3.2 上游自己的文档已经过期

`novly/docs/data-pipeline.md` 的表还写着「hot = 连载中 + 完结A + 断更A，~5k 条」、
「cold 按 `md5(author)%3` 分成 cold_1/2/3」。**当前这批文件不是那样**：

- `hot` 只有 2,805 本，且 `status` 100% 是 3
- 有独立的 `warm_chunk.sqlite`（2,515 本），A 组已经从 hot 里拆出来
- `cold` 只有一片，240,725 本 ≈ 原 3 片之和（80k × 3）

`build_chunks.py` 的 `CHUNKS` 字典也还是 cold_1/2/3 的旧结构，说明**文件是更新的，
脚本和文档是旧的**。以实测为准，别以文档为准。

---

## 4. 表与列

### 4.1 `novels` — 16 列，一行一本书

```sql
create table novels (
  id INTEGER PRIMARY KEY,      -- 站内 nid，全局唯一、严格单调
  title TEXT NOT NULL,
  author TEXT,                 -- 字符串，不是外键
  genre INTEGER DEFAULT 1,     -- 2–10，**实际无 1**
  status INTEGER DEFAULT 1,    -- 2/3/4/5/6，见 §6.1
  ptype INTEGER DEFAULT 1,     -- 2 免费 / 3 签约 / 4 VIP，**实际无 1**
  has_banner BOOLEAN DEFAULT 0,-- 0/1
  word_num INTEGER,
  click_num INTEGER,           -- 人气（累计浏览）
  praise_num INTEGER,          -- **赞**（不是打赏）
  like_num INTEGER,            -- **收藏**（不是点赞）← 语义反了
  comment_num INTEGER,         -- 短评，98% NULL
  review_num INTEGER,          -- 长评，98% NULL
  contest_id INTEGER,          -- 指向本片 contests.id
  cover TEXT,                  -- 完整 URL，含协议与域名
  last_update DATETIME         -- TEXT，'YYYY-MM-DD HH:MM:SS+00:00'
);
```

| 列 | 实测 | 坑 |
|---|---|---|
| `id` | 2,242 ~ 777,879，246,045 个值 | 宽度 775,638，**68.3% 是空洞**，不是下架率（`DATASET.md` §5.2） |
| `title` | 无空串、无首尾空格 | 65 本是纯数字占位（全在 cold） |
| `author` | 无 NULL、无空串、无首尾空格，140,638 行 → 137,965 个不同名字 | 字符串不是身份 |
| `genre` | 2–10，**无 1** | 表里定义了「1 其他」，一行都没有 |
| `ptype` | 2/3/4，**无 1** | 同上 |
| `word_num` | 0 ~ 21,762,745 | 497 本为 0，是真实空壳不是 NULL |
| `click_num` | 0 ~ 118,613,000 | cold 片上限只有 3,824,000（§6.2） |
| `like_num` | **−11** ~ 354,531 | 58 个负数，全在 cold，物理不可能 |
| `praise_num` | 0 ~ 138,110 | 2,094 本 `praise > click`（cold 2,076 + hot 18） |
| `comment_num` | NULL 占 98.1% | **未采集**，不是 0 |
| `review_num` | NULL 占 98.1% | 同上；cold 片最大值只有 47 |
| `contest_id` | NULL 占 61.2% | 真的不参加征文；按片指向本片 `contests`（§5.1） |
| `cover` | 34,641 本是默认封面 `defaultNew.jpg` | **2 条是小写 `defaultnew.jpg`**，DuckDB 的 `LIKE` 区分大小写会漏 |
| `last_update` | 全部 25 字符、全部 `+00:00` | 字符串可直接比较，但**不是上架时间** |

### 4.2 其余四张表

| 表 | 行数（cold / warm / hot） | 一行是什么 | 注意 |
|---|---|---|---|
| `authors` | 136,499 / 1,652 / 2,487 | **本片内**每个作者名 + 他 clicks 最大的那本书 | 是物化视图，不是作者表（§5.2） |
| `tags` | 99 / 79 / 86（共 264 行，去重后 **106** 个名字） | **本片用到的**标签 | 不是全站标签字典（§5.3） |
| `novel_tags` | 721,748 / 8,656 / 12,142 | 一次挂载 `(novel_id, tag_id)` | tag_id 是片内 id |
| `contests` | 97 / 55 / 57（共 209 行，去重后 **99** 个名字） | 一个征文 | 同上 |

`authors` 的列：`id`（自增，无意义）、`name`（UNIQUE）、`top_novel_id` / `top_novel_title` /
`top_novel_clicks`（按 `click_num` 取最大）。`top_novel_id` 全部能在本片 `novels` 里找到，
`name` 全部能在本片 `novels.author` 里找到——这两条断言跑过，0 例外。

---

## 5. 三套 id 空间：最容易被忽略的一件事

**只有 `novels.id` 是全球唯一的。其余三张表的 id 都是片内自增，跨片同 id 率 0%。**

| 表 | cold | warm | hot | 跨片重名 | 同 name 同 id |
|---|---|---|---|---|---|
| `authors.id` | 240,726 ~ 377,224 | 2,516 ~ 4,167 | 2,806 ~ 5,292 | 2,673 个名字 | 0 |
| `tags.id` | 1 ~ 710,395 | 1 ~ 8,466 | 1 ~ 5,577 | 72 个名字（cold∩warm） | **0/72** |
| `contests.id` | 1 ~ 91,516 | 1 ~ 1,720 | 1 ~ 1,763 | 110 行 | 0 |

### 5.1 id 为什么这么离谱

`build_chunks.py` 用 `INSERT OR IGNORE` + `AUTOINCREMENT` 写 `authors`/`tags`/`contests`：

```python
cursor.execute('INSERT OR IGNORE INTO authors (name) VALUES (?)', (author_name,))   # 每本书一次
cursor.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag_name,))         # 每条挂载一次
```

**SQLite 的 `AUTOINCREMENT` 在 `OR IGNORE` 跳过时也会消耗序号。** 所以每个自增表都被
多烧了几十万个号，而 `sqlite_sequence` 恰好留下了精确的账：

| 片 | `sqlite_sequence` | 实际行数 | 等式的右边 |
|---|---|---|---|
| cold | `authors` 377,224 | 136,499 | 240,725（每本书一次）+ 136,499 = **377,224** |
| | `tags` 721,748 | **99** | 721,748（每条挂载一次）= `novel_tags` 行数 |
| | `contests` 92,068 | 97 | 92,068（每个有征文的书一次）= 有 `contest_id` 的书数 |
| warm | `authors` 4,167 / `tags` 8,656 / `contests` 1,726 | 1,652 / 79 / 55 | 2,515+1,652 / 8,656 / 1,726 |
| hot | `authors` 5,292 / `tags` 12,142 / `contests` 1,763 | 2,487 / 86 / 57 | 2,805+2,487 / 12,142 / 1,763 |

**六个等式在三片上全部精确成立**——这就是「id 是废号」的硬证据，不是估计：

- `cold.authors` 只有 136,499 行，id 却从 **240,726** 开始：前 240,725 个号被 24 万本书
  逐条 `INSERT OR IGNORE` 烧掉了，正好等于本书数
- `cold.tags` 只有 **99 行**，id 却到 710,395：72 万条挂载每条都烧一个号
- `cold.contests` 97 行撑到 91,516 号：9.2 万本书各尝试插入一次征文

结论：**`authors.id`、`tags.id`、`contests.id` 是纯废号，当它不存在。** 跨片要合并，
必须按 `name` join（`build_dataset.py` 正是这么做的：`on=["chunk", "tag_id"]` 先把
片内 id 映射到全局 `tag_gid`，再按 name 去重）。直接 `union all` 这两张表会得到
「一个 tag_id 指向 3 个不同标签」的灾难。

### 5.2 作者名会被切成两半

`authors` 是**每片各算一份**的物化结果。同一个作者如果既有完结书（cold）又有连载书
（hot），就会在 `authors` 里出现两行，`top_novel_clicks` 各算各的：

| | 名字数 |
|---|---|
| cold | 136,499 |
| warm | 1,652 |
| hot | 2,487 |
| **合计行数** | **140,638** |
| **去重后** | **137,965**（重复 2,673 行） |

实测重叠：cold∩warm 1,398、cold∩hot 1,253、warm∩hot 168。所以**别拿 raw 的
`count(*) from authors` 当作者总数**，那多算了 2.7 千。上游 App 是用
`UPDATE ... WHERE w.top_novel_clicks > authors.top_novel_clicks` 合并的（`merge-chunks.js`）。

### 5.3 `tags` 是「本片用到的标签」，不是全站字典

- cold 99 个、warm 79 个、hot 86 个，**并集 106 个**
- cold 恰好缺 7 个：`2018萌神` ~ `2024萌神` —— 这些标签只挂当年获奖作品，cold 里没有
- warm 缺 27 个（`SCP`、`克苏鲁`、`型月`、`骨王`…），hot 缺 20 个

所以「某标签有多少本」必须三片加起来算；只查 cold 会得出「没有 2018萌神 这个标签」
这种假结论。

单本标签数上限：cold 5、warm 5、hot 7——**是截断，不是事实**（`DATASET.md` §5.3）。

---

## 6. 三个必须知道的语义陷阱

### 6.1 `status` 把两个维度压成了一列

```
结局（平台状态）：2 已完结 / 3 连载中 / 4 断更
成绩标记（上游派生）：5 = 断更A、6 = 完结A
```

`A` 不是平台状态，是 `novel_hub` 按规则给「成绩好的完结/断更书」打的标：

> `断更`/`已完结` + (banner OR 人气≥1000万 OR 长评≥60 OR 收藏≥1万 OR 赞≥1万) → `断更A`/`完结A`

**实测零反例**：warm 的 2,515 本全部 rule=True，cold 的 240,725 本全部 rule=False。

更关键的是 **A 在 cold 片上结构性地不可达**：

| 判据 | 阈值 | cold 片实测上限 | 能触发吗 |
|---|---|---|---|
| `has_banner` | 1 | **0** | 否 |
| `click_num` | 10,000,000 | **3,824,000** | 否 |
| `review_num` | 60 | **47** | 否 |
| `like_num` | 10,000 | **9,999** | 否 |
| `praise_num` | 10,000 | **9,928** | 否 |

五条判据的上限全部卡在阈值下方（收藏差 1、赞差 72、长评差 13、人气差 617 万），
banner 恒为 0。所以**在「完结/断更」这一层里，`status` 5/6 等价于「这本书的数值来自
详情页精确通道」**——这才是 A 的真实含义，与「完结/断更」无关，也与质量无关。
（`status=3` 连载中的 2,805 本也走同一条精确通道，只是没完结、所以没被打 A。）

这就是 `datasets/v1` 删掉 `status`、只保留 `stats_precise`（= 原 3/5/6，5,320 本）的原因。
判定式留在 `config.A_RULE_SQL`，只给测试复现零反例用。详见 `DATASET.md` §4.1。

### 6.2 三片的数值精度不同，cold 的顶端被截断

| 最大值 | cold | warm | hot |
|---|---|---|---|
| `click_num` | **3,824,000** | 118,613,000 | 108,392,000 |
| `like_num` | **9,999**（恰好 9,999 的 1 本） | 354,531 | 280,449 |
| `praise_num` | **9,928** | 138,110 | 110,649 |
| `review_num` | **47** | 520 | 612 |

cold 的数字是列表页显示值还原的（「10903.2万」→ 只精确到千位），且历史归档段此后再没重采。
后果：

- **跨片排序 `order by like_num desc` 是错的**——cold 里那些 9,999 的书可能是 30 万收藏
- 低门槛筛选（`click_num >= 100000`）三片都能用；高门槛（`like_num >= 10000`、`click_num >= 10000000`）
  只对 warm + hot 有效
- `click_num >= 100000` 全库 14,809 本，其中 11,713 本（79%）在 cold 片——所以低门槛
  必须包含 cold，不能只查 warm/hot

### 6.3 `status` 的判定时点早于快照日

定义上「断更 = 3 个月没更新」，但实测 **779 本 `status=4` 的书 `last_update` 在
2026-03-15 之后**（另有 230 本 `status=2`），占 cold 的 0.42%。也就是说这批书的
`status` 是**更早时候**判的，之后作者又更新了。

按月看更清楚（cold，`status in (2,4)` 的书按 `last_update` 落在哪个月）：

| 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 |
|---|---|---|---|---|---|---|
| 1,249 | 1,190 | 1,047 | 1,386 | **240** | 13 | 5 |

3 月还有 1,386 本，4 月起断崖。说明**断更判定基本冻结在 2026 年一季度**，
`cold` 片再没重判过（`hot` 片相反：2,805 本的 `last_update` 全部落在
2026-04-03 ~ 2026-06-13 这个区间内）。

用法：想要「现在还在更的书」用 `status=3`；想要「按定义已经断了」必须自己算
`last_update < date('2026-06-13', '-90 day')`，两个口径会差 779 本。

---

## 7. raw 与 `datasets/v1` 的换算表

每一行都是守恒的，对不上就是哪一步错了：

| 量 | raw（三片之和） | `datasets/v1` | 差从哪来 |
|---|---|---|---|
| `novels` | 246,045 | 246,045 | — |
| `done` | 42,193 + 1,388 = 43,581 | 43,581 | status 2 与 6 合并 |
| `dead` | 198,532 + 1,127 = 199,659 | 199,659 | status 4 与 5 合并 |
| `ongoing` | 2,805 | 2,805 | — |
| `stats_precise` | 2,805 + 2,515 = 5,320 | 5,320 | status 3/5/6 |
| `has_banner` | 638 + 29 + 0 = 667 | 667 | — |
| `novel_tags` | 721,748 + 8,656 + 12,142 = 742,546 | 742,546 | tag_id 重映射 |
| `authors` | 140,638 行 | **137,965** | 2,673 个名字跨片（§5.2） |
| `contests` | 209 行 | **99** | 110 行同名重复 |
| `tags` | 264 行 | **106** | 按 name 去重后重编号 1–106 |
| `flg_import` | 47 本（全在 warm） | 47 | 按版权方账号识别，raw 里没有标记 |

反向核对用 `manifest.json` 的 `source` 段：那里记着三个文件的 `bytes` / `sha256` / `rows`
和读取耗时（cold 2.84 s、warm 0.04 s、hot 0.04 s）。

---

## 8. 陷阱清单（每条都在 raw 上验过）

| # | 症状 | 正确做法 |
|---|---|---|
| 8.1 | `count(*) from authors` 得 140,638，当成作者数 | 按 name 去重得 137,965；或直接用 `datasets/v1` |
| 8.2 | 三片 `union all authors/tags/contests` 后 id 串味 | 这三张表只能按 name 或 `(chunk, id)` join |
| 8.3 | `order by like_num desc` 排出 9,999 的「收藏第一」 | 排序锁 `status in (3,5,6)`；cold 的顶端不存在 |
| 8.4 | 以为 `likes` 高就是热门 | `like_num` 是**收藏**，`praise_num` 是**赞**，名字反了 |
| 8.5 | `avg(comment_num)` 得 25.9，结论「平均每本 26 条短评」 | 只有 4,690 本（1.9%）有值，其余是 NULL（未采集）；有值那批均值 1,359 |
| 8.6 | `sum(like_num)` 出现负数 | cold 有 58 个负值（最小 −11），上游已置 NULL 并打 `flg_like_fixed` |
| 8.7 | 用 `last_update` 当年份做趋势 | 那是最后编辑时间；上架日要用 `novels_era.est_date` |
| 8.8 | 用 `status in (5,6)` 筛「长篇小说」 | 得到 88.8 万字中位数，是选择偏差；用 `outcome='done' and word_num>=300000` |
| 8.9 | 只查 cold 说「没有 2018萌神 这个标签」 | 三片并集才有 106 个标签（§5.3） |
| 8.10 | 用 `like '%defaultnew%'` 数默认封面 | DuckDB 区分大小写，会漏 2 条；用 `ILIKE` |
| 8.11 | `genre=1` / `ptype=1` 筛「其他」 | 两列都没有 1，结果恒为空 |
| 8.12 | `word_num = 0` 当缺失丢掉 | 497 本是真空壳，会拉低字数中位；要不要排先决定 |
| 8.13 | 拿 `novels.id` 的洞估下架量 | 68.3% 空洞，含非小说对象占号，只能当下界 |
| 8.14 | 认为「cold 永不更新」所以数据很旧 | cold 的 `last_update` 最晚到 2026-06-09，快照是滚动的 |
| 8.15 | 在 raw 上跑分析脚本 | 分析只读 `datasets/v1`；raw 是构建输入，随时可能被替换 |

---

## 9. 体检：换原料后先跑这段

```sql
-- 三片各自的本数与 id 边界（先 attach 三片，见 §0）
select 'cold' c, count(*) n, min(id) lo, max(id) hi from cold.novels
union all select 'warm', count(*), min(id), max(id) from warm.novels
union all select 'hot',  count(*), min(id), max(id) from hot.novels;

-- 跨片 id 不重复：三片之和 - 并集 = 0
select
  (select count(*) from cold.novels)
+ (select count(*) from warm.novels)
+ (select count(*) from hot.novels)
- (select count(*) from (
     select id from cold.novels union
     select id from warm.novels union
     select id from hot.novels)) as dup;   -- 0
```

锚点（任一项不等就停下确认，**不要**直接改代码）：

| 检查 | 期望值 |
|---|---|
| `cold.novels` / `warm.novels` / `hot.novels` | 240,725 / 2,515 / 2,805 |
| 三片 `novels.id` 并集 | 246,045，重复 0 |
| `cold.status` 取值 | 只有 2 和 4 |
| `warm.status` 取值 | 只有 5 和 6 |
| `hot.status` 取值 | 只有 3 |
| `cold.has_banner = 1` | 0 |
| `cold.like_num` 上限 / `warm.like_num` 上限 | 9,999 / 354,531 |
| `cold.authors` 最小 id | 240,726（= 本书数 + 1） |
| `authors` 三片行数之和 / 去重名字数 | 140,638 / 137,965 |
| `novel_tags` 三片之和 | 742,546 |
| 三片 `tags` 名字并集 | 106 |
| 三片 `contests` 名字并集 | 99 |
| `max(last_update)` | 2026-06-13 |
| sha256（解压后） | 与 §2 表一致，也与 `manifest.json` 一致 |

全绿之后 `uv run python -m quarry.build_dataset` 必定产出同一份 parquet
（`content_hash cd773d14…`），`uv run pytest -q` 46 项断言应全过。

---

## 10. 一句话总结

1. **三片 = 按 `status` 切的三个包**，不是三个数据集；并集才是全库，跨片只有 `novels.id` 能 join。
2. **`authors` / `tags` / `contests` 的 id 在每个文件里都从头编号**，且被 `INSERT OR IGNORE`
   烧出几十万的废号——按 name 对齐，别按 id。
3. **cold 片的四个数值上限全部低于 A 阈值**，所以完结层里的 `status` 5/6 真正表达的是
   「数值走过详情页精确通道」，不是「完结」也不是「好书」。

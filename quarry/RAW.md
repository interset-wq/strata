# 上游原料字典 · 三片 sqlite

> 这是从 novly Release 下载的**未经加工的三片快照**——`cold` / `warm` / `hot`
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

| 文件                          | 讲什么                                                        | 什么时候读                                                          |
| ----------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------- |
| `RAW.md`（本文）            | 原料：从哪来、怎么切的、id 为什么不能混、哪片被截断过         | 要跑 `build_dataset`、要核对 raw 与数据集的行数、怀疑数字对不上时 |
| [`DATASET.md`](./DATASET.md) | 产物：`datasets/v1` 的 7 张表、字段语义、两套精度、体检 SQL | **要写查询、要引用任何数字之前**                              |

分析代码**只读 `datasets/`，永不读 raw**（`config.py` 顶部就这么写的）。本文是给
构建者看的，不是给分析者看的。

---

## 30 秒上手

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
   采集阶段就没有（未采集comment_num和review_num），后面任何一级都补不回来。
2. **`status` 是上游的主观判定**，不是平台字段（§6.1）。到我们这里已经拆成 `outcome`。平台只有已完结和连载中
3. **切分是打包行为，不是数据属性**（§3）。上游做这件事只为首屏加载。
4. 上游代码 MIT，**数据本身没有授权**。所以 raw 只留在本地，发布的是我们重新构建的
   `datasets/v1`；再分发 raw 是另一件事，不要顺手做。

---

## 2. 文件清单

| chunk | 文件                  | novels            | 解压字节    | gz 字节    | gz 占比 | 在 App 里的角色（上游设计）  |
| ----- | --------------------- | ----------------- | ----------- | ---------- | ------- | ---------------------------- |
| cold  | `cold_chunk.sqlite` | **240,725** | 134,156,288 | 60,506,244 | 45.1%   | 永不更新，首次安装后按需解压 |
| warm  | `warm_chunk.sqlite` | **2,515**   | 1,593,344   | 734,620    | 46.1%   | 冷合并时并入主库             |
| hot   | `hot_chunk.sqlite`  | **2,805**   | 1,925,120   | 889,167    | 46.2%   | 首屏先解压它，月更           |

合计 **137.7 MB 解压 / 62.1 MB gz**。`cold` 一片占 97.4% 的体积，`warm + hot` 只有 3.5 MB
——这两个小片才是「现在还在动」的部分，所以上游让它们单独发版。

物理形态（三片一致，已实测）：

- `page_size = 4096`，`journal_mode = delete`，`user_version = 0`，无 WAL 残留
- 每片 **11 个索引**，`novels` 上 7 个（status/genre/ptype/click_num/author/has_banner/last_update），
  `novel_tags` 上 2 个，`authors` 上 2 个。**索引是给 App 的查询路径建的，不是给分析建的**
- 三片 `create table` 语句**逐字节相同**——`novels`/`authors`/`tags`/`novel_tags`/`contests`
  五张表，可以直接 `union all` 表结构

文件指纹（与 `datasets/v1/manifest.json` 里 `source` 段完全一致，可用来确认拿到的是同一批原料）：

| chunk | sha256（解压后 = manifest 记录值）                                   |
| ----- | -------------------------------------------------------------------- |
| cold  | `0e2b90f09489e26137332831fa96cf2a6450efee016e933d41d7d2a9753372e0` |
| warm  | `7399d1045bac670cb303936e51c09b7ada9928e5ce42e46023e4f739aef155cd` |
| hot   | `89fa62daa0e1c14c727919d91dbf905db2b606b23a9369599da38b473d115411` |

`gzip -dc x.sqlite.gz | sha256sum` 与表里一致，说明 gz 无损、没被重新打包过。

---

## 3. 切分规则：其实是按 `status` 切的

`scripts/build_chunks.py` 的 `get_chunk_category()` 只有一条判据：`status`。
实测对得上，一行为不差：

| chunk | 收纳的 `status` | 实测本数                             | 对应结局                    |
| ----- | ----------------- | ------------------------------------ | --------------------------- |
| cold  | 2 已完结 / 4 断更 | 42,193 + 198,532 = **240,725** | done + dead                 |
| warm  | 5 断更A / 6 完结A | 1,127 + 1,388 = **2,515**      | done + dead（成绩好的那批） |
| hot   | 3 连载中          | **2,805**                      | ongoing                     |

并集 246,045，**跨片 `novels.id` 重复 0 条**。所以「三片」等价于「按 status 分三组」，
不携带任何 status 之外的信息——这也是 `datasets/v1` 里不保留 `chunk` 列的原因
（`DATASET.md` §4.2）。

### 3.1 三片不是随机分组，是三个质量层

|                     | cold             | warm              | hot        |
| ------------------- | ---------------- | ----------------- | ---------- |
| 字数中位            | **10,088** | **888,500** | 91,682     |
| 字数最小            | 0（496 本空壳）  | **22,588**  | 0（1 本）  |
| 字数最大            | 8,532,591        | 9,563,189         | 21,762,745 |
| VIP 占比（ptype=4） | 1.7%             | **92.9%**   | 17.4%      |
| banner              | **0 本**   | 638 本            | 29 本      |
| 有标签的书          | 94.9%            | 99.7%             | 100%       |
| 平均标签数          | 3.16             | 3.45              | 4.33       |

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
  status INTEGER DEFAULT 1,    -- 2/3/4/5/6，见 §6
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

| 列              | 实测                                                          | 坑                                                                         |
| --------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `id`          | 2,242 ~ 777,879，246,045 个值                                 | 宽度 775,638，**68.3% 是空洞**，不是下架率（`DATASET.md` §5.2）   |
| `title`       | 无空串、无首尾空格                                            | 65 本是纯数字占位（全在 cold）                                             |
| `author`      | 无 NULL、无空串、无首尾空格，140,638 行 → 137,965 个不同名字 | 字符串不是身份                                                             |
| `genre`       | 2–10，**无 1**                                         | 表里定义了「1 其他」，一行都没有                                           |
| `ptype`       | 2/3/4，**无 1**                                         | 同上                                                                       |
| `word_num`    | 0 ~ 21,762,745                                                | 497 本为 0，是真实空壳不是 NULL                                            |
| `click_num`   | 0 ~ 118,613,000                                               | cold 片上限只有 3,824,000（§6.2）                                         |
| `like_num`    | **−11** ~ 354,531                                      | 58 个负数，全在 cold，物理不可能                                           |
| `praise_num`  | 0 ~ 138,110                                                   | 2,094 本 `praise > click`（cold 2,076 + hot 18）                         |
| `comment_num` | NULL 占 98.1%                                                 | **未采集**，不是 0                                                   |
| `review_num`  | NULL 占 98.1%                                                 | 同上；cold 片最大值只有 47                                                 |
| `contest_id`  | NULL 占 61.2%                                                 | 真的不参加征文；按片指向本片 `contests`（§5.1）                         |
| `cover`       | 34,641 本是默认封面 `defaultNew.jpg`                        | **2 条是小写 `defaultnew.jpg`**，DuckDB 的 `LIKE` 区分大小写会漏 |
| `last_update` | 全部 25 字符、全部 `+00:00`                                 | 字符串可直接比较，但**不是上架时间**                                 |

### 4.2 其余四张表

| 表             | 行数（cold / warm / hot）                              | 一行是什么                                          | 注意                            |
| -------------- | ------------------------------------------------------ | --------------------------------------------------- | ------------------------------- |
| `authors`    | 136,499 / 1,652 / 2,487                                | **本片内**每个作者名 + 他 clicks 最大的那本书 | 是物化视图，不是作者表（§5.2） |
| `tags`       | 99 / 79 / 86（共 264 行，去重后 **106** 个名字） | **本片用到的**标签                            | 不是全站标签字典（§5.3）       |
| `novel_tags` | 721,748 / 8,656 / 12,142                               | 一次挂载 `(novel_id, tag_id)`                     | tag_id 是片内 id                |
| `contests`   | 97 / 55 / 57（共 209 行，去重后 **99** 个名字）  | 一个征文                                            | 同上                            |

`authors` 的列：`id`（自增，无意义）、`name`（UNIQUE）、`top_novel_id` / `top_novel_title` /
`top_novel_clicks`（按 `click_num` 取最大）。`top_novel_id` 全部能在本片 `novels` 里找到，
`name` 全部能在本片 `novels.author` 里找到——这两条断言跑过，0 例外。

---

## 5. 三套 id 空间：最容易被忽略的一件事

**只有 `novels.id` 是全球唯一的。其余三张表的 id 都是片内自增，跨片同 id 率 0%。**

| 表              | cold              | warm          | hot           | 跨片重名                | 同 name 同 id  |
| --------------- | ----------------- | ------------- | ------------- | ----------------------- | -------------- |
| `authors.id`  | 240,726 ~ 377,224 | 2,516 ~ 4,167 | 2,806 ~ 5,292 | 2,673 个名字            | 0              |
| `tags.id`     | 1 ~ 710,395       | 1 ~ 8,466     | 1 ~ 5,577     | 72 个名字（cold∩warm） | **0/72** |
| `contests.id` | 1 ~ 91,516        | 1 ~ 1,720     | 1 ~ 1,763     | 110 行                  | 0              |

### 5.1 id 为什么这么离谱

`build_chunks.py` 用 `INSERT OR IGNORE` + `AUTOINCREMENT` 写 `authors`/`tags`/`contests`：

```python
cursor.execute('INSERT OR IGNORE INTO authors (name) VALUES (?)', (author_name,))   # 每本书一次
cursor.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag_name,))         # 每条挂载一次
```

**SQLite 的 `AUTOINCREMENT` 在 `OR IGNORE` 跳过时也会消耗序号。** 所以每个自增表都被
多烧了几十万个号，而 `sqlite_sequence` 恰好留下了精确的账：

| 片   | `sqlite_sequence`                                      | 实际行数        | 等式的右边                                             |
| ---- | -------------------------------------------------------- | --------------- | ------------------------------------------------------ |
| cold | `authors` 377,224                                      | 136,499         | 240,725（每本书一次）+ 136,499 = **377,224**     |
|      | `tags` 721,748                                         | **99**    | 721,748（每条挂载一次）= `novel_tags` 行数           |
|      | `contests` 92,068                                      | 97              | 92,068（每个有征文的书一次）= 有 `contest_id` 的书数 |
| warm | `authors` 4,167 / `tags` 8,656 / `contests` 1,726  | 1,652 / 79 / 55 | 2,515+1,652 / 8,656 / 1,726                            |
| hot  | `authors` 5,292 / `tags` 12,142 / `contests` 1,763 | 2,487 / 86 / 57 | 2,805+2,487 / 12,142 / 1,763                           |

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

|                    | 名字数                             |
| ------------------ | ---------------------------------- |
| cold               | 136,499                            |
| warm               | 1,652                              |
| hot                | 2,487                              |
| **合计行数** | **140,638**                  |
| **去重后**   | **137,965**（重复 2,673 行） |

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

## 6. `status` 是怎么被造出来的：四步加工，后两步都不在仓库里

这一节是本文件最重要的部分。`status` 看着像「平台状态」，其实是四步加工的产物：
**平台只给两个值，后面两个值（`断更`、`A`）都是别人加的判断，而且加判断的代码不在我们拿到的仓库里。**

```
站点页面文案       字数：3240533字[连载中]      ← 平台只给「连载中 / 已完结」，且是「字数」格的后缀
    │ 列表页解析（utils/html.py:_parse_row，爬虫 meta_batch.py:_row 同源）
爬虫产出 JSONL     status: "连载中" / "已完结"
    │ ① 断更判定——代码不在仓库里，只留下配置 died_days = 90
上游 DB / release   status: 2 / 3 / 4
    │ ② A 标——代码不在仓库里，只留下四个阈值 active_*
本快照              status: 2 / 3 / 4 / 5 / 6（5 = 断更A、6 = 完结A）
    │ build_chunks.py 按 status 分组
三片 sqlite         cold = 2/4、warm = 5/6、hot = 3
```

### 6.1 第一步：状态是「字数」那一格的后缀，不是独立字段

列表页每个条目只有 4 格：

```
['类型：魔幻', '字数：3240533字[连载中]', '人气：4757.4万', '更新：2026/5/25 20:26:36']
```

解析只有三行（`utils/html.py:105-107`）：

```python
genre, wordnum_status, click_num, last_update = values
word_num, status = wordnum_status.split("字[")
status = status.replace("]", "")
```

三个后果，每条都能解释一批「数据消失」：

1. **状态和字数共用一格**。`split("字[")` 匹配不到就抛异常，整行被 `except: continue` 丢掉
   （`build_chunks.py:process_jsonl_files`）。所以「这本书不在库里」可能只是格式变了。
2. **`status` 是中文原文，没有枚举校验**。`STATUS_MAP.get(status, 1)` 遇到没见过的字面值
   静默落到「其他」= 1，而 1 在 `should_skip_novel` 里会被跳过 —— **静默丢书，不报错**。
3. **`word_num` 与 `status` 永远同源**，不存在「状态新、字数旧」的组合。

### 6.2 第二步：`status` 的语义写在文档里，但只有两个值来自平台

`status` 的语义不是猜的，上游把它写成了文档，而且三处一致：

| 出处 | 内容 |
|---|---|
| `docs/website.md:207-212` | **Data Rules**：Died、A-status 两条规则（中文） |
| `AGENTS.md:128-136` | 同样两条的英文版，并明确标注 **`A status (pseudo)`** |
| `docs/commands.md:207` | A 判据的阈值展开，用于爬取任务分级 |
| `site_config.toml [thresholds]` | `died_days = 90`、`active_click/praise/like/review` 四个数 |

`docs/website.md` 原文只有两行：

```
- **Died**: `连载中` + 3 months no update → `断更`
- **A-status**: `断更`/`已完结` + (banner OR click≥1000w OR review≥60 OR like≥1w OR praise≥1w) → `断更A`/`完结A`
```

注意上游自己把 A 称为 **pseudo**（伪状态）——它承认这不是平台状态。七个值的来源于是很清楚：

| 枚举 | 值 | 字面 | 谁加的 | 依据 |
|---|---|---|---|---|
| `OTHER` | 1 | 其他 | 兜底默认值 | `STATUS_MAP.get(status, 1)` |
| `FINISHED` | 2 | 已完结 | **平台** | `docs/meta_spider.md:66` 的解析示例 `字数：3240533字[连载中]` |
| `ON_GOING` | 3 | 连载中 | **平台** | 同上 |
| `DIED` | 4 | 断更 | 上游按文档判定 | `website.md` 的 Died 规则 |
| `ACTIVE_D` | 5 | 断更A | 上游按文档判定 | `website.md` 的 A-status 规则 |
| `ACTIVE_F` | 6 | 完结A | 上游按文档判定 | 同上 |
| `REMOVED` | 7 | 下架 | 处理下架页时打标 | 三片里已被丢弃 |

所以「一本书是断更」不是平台事实，是**有人按一条 90 天的规则替你判的**。
`datasets/v1` 里 `outcome='dead'` 的那 199,659 本，全部来自这个判断。

### 6.3 第三步：`断更` 的规则有文档、阈值有配置，**但代码里没有实现**

三样东西齐全地摆在眼前，唯独缺执行：

| | 在哪 |
|---|---|
| 规则（3 个月无更新） | `docs/website.md:209`、`AGENTS.md:130` |
| 阈值（90 天） | `site_config.toml [thresholds] died_days = 90` |
| 实现 | **不存在**。全仓 grep 不到任何把 `ON_GOING` 改写成 `DIED` 的代码，`died_days` 也没有被任何 Python 读过 |

唯一沾边的是 `meta_batch.py:100-106` 的 **cutoff**：抓到 `last_update` 早于 `days`（默认 7 天）的书就
`should_stop = True` 停抓。这是**爬取窗口**，不是状态判定——但它有一个副作用：**老书再也不会被重新访问**，
于是它们的 `status` 永远停在最后一次判定（§6.9 的 779 个反例就是它的指纹）。

实现缺失的两种解释，都无法证伪：

- 派生逻辑在重构时被删（仓库只有一个 squash 后的提交，没有历史可查）
- 派生发生在 `nookdata`——上游那层「修复」仓库里，我们没有它

结论：**规则可读、阈值可读、执行不可复现。** 用 `断更` 就是在用一个我们无法重跑、也不知道
判定时点的判断（不是平台的，也不是我们的）。

### 6.4 第四步：A 标的规则同样只有文档，连「写」的代码都没有

四个阈值在 `site_config.toml`：`active_click = 10,000,000`、`active_review = 60`、
`active_like = 10,000`、`active_praise = 10,000`。和 `died_days` 一样，**没有任何代码写入 5/6**，
全仓只有三处在「读」它：

- `fill_tasks.py:95` — `if novel.status in (ACTIVE_D, ACTIVE_F): is_urgent = True`（定爬取优先级）
- `generate_static.py` / `views/other.py` — 按阈值画榜单分组，同样只读

结论：**A 是发版前用一次性脚本或手工 SQL 打上去的，脚本没进仓库。** 这对我们是三件事：

1. A 标**不可复现**，只有判定式可复现（`config.A_RULE_SQL` 就是为此留的）
2. A 标**可能被人工改过**。「零反例」只说明这批数据里没有例外，不说明规则被严格程序化执行
3. 阈值一旦被上游改（比如 `active_like` 从 1 万调到 2 万），同一份原始数据会切出不同的 warm ——
   **三片的边界是「上游那天的阈值」的函数**，不是数据本身的属性

判定式在本快照上零反例：warm 2,515 本全部 True，cold 240,725 本全部 False。
但这条「零反例」正是下一节的循环。

### 6.5 循环：不能用 cold 的「上限」证明 A 与精度有关

`DATASET.md` §3 的旧论证是：cold 的上限 382.4 万 / 9,999 / 9,928 / 47 全部卡在 A 阈值下方，
所以 `status` 5/6 的真实含义是「这行的数字走过详情页精确通道」。

**这个论证是循环的。** cold 的定义就是「五条判据都不达标」——任何达标的完结/断更书都会
被标成 A 进 warm。于是：

- 「cold 的 `like_num` 上限 = 9,999」不是测量截断线，而是 `like≥10000 → A → 去 warm` 的**定义效应**
- 反证：cold 里 `like_num` 在 9,900–9,999 是平滑分布（9,981 / 9,985 / 9,986 / 9,989 / 9,991 /
  9,993 / 9,995 / 9,999 各 1 本），**等于 9,999 的只有 1 本**。若真有 9,999 的显示钳位，
  这里会堆出一座尖峰
- 同理 `review_num` 上限 47、`praise_num` 上限 9,928、`click_num` 上限 3,824,000
  （≥300 万只有 22 本，无堆积）都是**组内最大值，不是钳位**

一句话：**「A 组 = 精确通道」不是实测结论，是从判定式反推出来的同义反复。**
下面两节才是能独立验证的东西。

### 6.6 独立事实一：`click_num` 只有一档千位粒度，且三片一致

`click_num` 的解析是 `int(float(x.replace("万", "")) * 10_000)`。只要页面用「X.Y万」显示，
末三位就恒为 0。实测分离得干干净净：

| `click_num` 区间 | cold | warm | hot | 千整占比 |
|---|---|---|---|---|
| < 10 万 | 229,012（4,461 千整） | 10（0） | 2,214（113） | 2% 左右 = 巧合 |
| 10 万 ~ 100 万 | 10,559（14） | 103（0） | 402（2） | 0.1% = 巧合 |
| **≥ 100 万** | **1,154（1,154）** | **2,150（2,150）** | **168（168）** | **100%** |
| ≥ 1000 万 | 0 | 252（252） | 21（21） | 100% |

**分界线是 100 万，不是 1000 万**：≥100 万的 3,745 本里，末三位非零的是 **0 本**；
<100 万的 24 万本里「千整」只占 2% 左右（自然巧合率，末位数字本来就略偏 0/5）。

三个推论：

- 100 万以上的人气只有 **1,000** 的分辨率，同一个「X.Y万」会落在几十本书上 → 并列极多
- 这条规则**三片完全一致**，所以它不能用来解释「A 组更精确」——两组的 click 精度一样
- `like_num` / `praise_num` / `word_num` / `review_num` 都是**精确整数**：
  warm 的 `like_num` 末位 0–9 分布均匀（233–267 本/位），没有截断痕迹

### 6.7 独立事实二：唯一真实的通道差异是「评论数有没有值」

`comment_num` / `review_num` 不在列表页那一行，而来自**另一次 API 调用**
（`Common.ashx?op=getcomment&nid=…` → `LongCommentNum`，见 `meta_batch.py`）。
所以「有没有评论数」才是「这本书走没走过那个接口」的独立证据：

| | cold | warm | hot | 合计 |
|---|---|---|---|---|
| 有 `comment_num` | 3,652（1.5%） | 662（26.3%） | 376（13.4%） | **4,690（1.9%）** |
| NULL | 237,073（98.5%） | 1,853（73.7%） | 2,429（86.6%） | 241,355 |

关键点：**warm 里也有 74% 没有评论数**。所以 A 标并不等价于「走过详情接口」。

### 6.8 那到底该怎么用 `status`

| 想知道 | 正确做法 |
|---|---|
| 结局（完结 / 断更 / 连载） | 用 `status` 分片，但记住后两个值是**别人的判断**，且是判定时刻的（§6.9） |
| 「这个数可不可信」 | **不要**看 A / `stats_precise`；只有一个事实：`click_num` 全库统一千位粒度 |
| 「这本书走过详情接口吗」 | `comment_num is not null`（全库 4,690 本） |
| 能推荐给别人的成品 | 我们自己的 `outcome='done' and word_num>=300000`（3,766 本） |

### 6.9 `status` 的判定时点早于快照日

定义上「断更 = 3 个月没更新」，但实测 **779 本 `status=4` 的书 `last_update` 在
2026-03-15 之后**（另有 230 本 `status=2`），占 cold 的 0.42%。这批书的 `status` 是
**更早时候**判的，之后作者又更新了。

按月看更清楚（cold，`status in (2,4)` 的书按 `last_update` 落在哪个月）：

| 2025-12 | 2026-01 | 2026-02 | 2026-03 | 2026-04 | 2026-05 | 2026-06 |
|---|---|---|---|---|---|---|
| 1,249 | 1,190 | 1,047 | 1,386 | **240** | 13 | 5 |

3 月还有 1,386 本，4 月起断崖。说明**断更判定基本冻结在 2026 年一季度**，`cold` 片再没重判过。
机制在 §6.3 那条 cutoff 里：爬虫只走到 `last_update` 落在 7 天窗口内的书，断更的书永远在窗口外，
**不会再被访问，也就不会再有新判定**。
对照 `hot` 片：2,805 本 `status=3` 的 `last_update` 全部落在 2026-04-03 ~ 2026-06-13，
**零例外**。两个标签用两个时钟：`连载中` 是随采集维护的，`断更` 是冻住的。

用法：想要「现在还在更的书」用 `status=3`；想要「按定义已经断了」必须自己算
`last_update < date('2026-06-13', '-90 day')`，两个口径差 779 本。

---

## 7. raw 与 `datasets/v1` 的换算表

每一行都是守恒的，对不上就是哪一步错了：

| 量                | raw（三片之和）                    | `datasets/v1`   | 差从哪来                         |
| ----------------- | ---------------------------------- | ----------------- | -------------------------------- |
| `novels`        | 246,045                            | 246,045           | —                               |
| `done`          | 42,193 + 1,388 = 43,581            | 43,581            | status 2 与 6 合并               |
| `dead`          | 198,532 + 1,127 = 199,659          | 199,659           | status 4 与 5 合并               |
| `ongoing`       | 2,805                              | 2,805             | —                               |
| `stats_precise` | 2,805 + 2,515 = 5,320              | 5,320             | status 3/5/6 = **A 组**，不是精度标记（§6.5） |
| `has_banner`    | 638 + 29 + 0 = 667                 | 667               | —                               |
| `novel_tags`    | 721,748 + 8,656 + 12,142 = 742,546 | 742,546           | tag_id 重映射                    |
| `authors`       | 140,638 行                         | **137,965** | 2,673 个名字跨片（§5.2）        |
| `contests`      | 209 行                             | **99**      | 110 行同名重复                   |
| `tags`          | 264 行                             | **106**     | 按 name 去重后重编号 1–106      |
| `flg_import`    | 47 本（全在 warm）                 | 47                | 按版权方账号识别，raw 里没有标记 |

反向核对用 `manifest.json` 的 `source` 段：那里记着三个文件的 `bytes` / `sha256` / `rows`
和读取耗时（cold 2.84 s、warm 0.04 s、hot 0.04 s）。

---

## 8. 陷阱清单（每条都在 raw 上验过）

| #    | 症状                                                     | 正确做法                                                                     |
| ---- | -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 8.1  | `count(*) from authors` 得 140,638，当成作者数         | 按 name 去重得 137,965；或直接用 `datasets/v1`                             |
| 8.2  | 三片 `union all authors/tags/contests` 后 id 串味      | 这三张表只能按 name 或 `(chunk, id)` join                                  |
| 8.3  | 以为 cold 的数值被截断过，所以不能跨组排序              | `like`/`praise`/`word` 都是精确整数；只有 `click_num` 有千位粒度且三片一致（§6.6）。跨组排序可以做，但要接受千位并列 |
| 8.4  | 以为 `likes` 高就是热门                                | `like_num` 是**收藏**，`praise_num` 是**赞**，名字反了       |
| 8.5  | `avg(comment_num)` 得 25.9，结论「平均每本 26 条短评」 | 只有 4,690 本（1.9%）有值，其余是 NULL（未采集）；有值那批均值 1,359         |
| 8.6  | `sum(like_num)` 出现负数                               | cold 有 58 个负值（最小 −11），上游已置 NULL 并打 `flg_like_fixed`        |
| 8.7  | 用 `last_update` 当年份做趋势                          | 那是最后编辑时间；上架日要用 `novels_era.est_date`                         |
| 8.8  | 用 `status in (5,6)` 筛「长篇小说」                    | 得到 88.8 万字中位数，是选择偏差；用 `outcome='done' and word_num>=300000` |
| 8.9  | 只查 cold 说「没有 2018萌神 这个标签」                   | 三片并集才有 106 个标签（§5.3）                                             |
| 8.10 | 用 `like '%defaultnew%'` 数默认封面                    | DuckDB 区分大小写，会漏 2 条；用 `ILIKE`                                   |
| 8.11 | `genre=1` / `ptype=1` 筛「其他」                     | 两列都没有 1，结果恒为空                                                     |
| 8.12 | `word_num = 0` 当缺失丢掉                              | 497 本是真空壳，会拉低字数中位；要不要排先决定                               |
| 8.13 | 拿 `novels.id` 的洞估下架量                            | 68.3% 空洞，含非小说对象占号，只能当下界                                     |
| 8.14 | 认为「cold 永不更新」所以数据很旧                        | cold 的 `last_update` 最晚到 2026-06-09，快照是滚动的                      |
| 8.15 | 在 raw 上跑分析脚本                                      | 分析只读 `datasets/v1`；raw 是构建输入，随时可能被替换                     |
| 8.16 | 把 `status=4` 当「现在已断更」                          | 779 本断更书的 `last_update` 在 2026-03-15 之后；要「按定义已断」得自己算（§6.9） |
| 8.17 | 以为 A 标（`stats_precise`）=「走过详情页、数更准」      | A 只是四个阈值 + banner 的 OR，派生代码不在仓库；warm 里 74% 也没有评论数（§6.4、§6.7） |
| 8.18 | 换一批上游数据后沿用本文件的假设                          | 阈值（`active_*`）与派生规则都可能变；先跑 §9 的锚点，特别看三片的 status 取值 |

---

## 9. 体检：换原料后先跑这段

```sql
-- 三片各自的本数与 id 边界（先 attach 三片，见文首「30 秒上手」）
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

| 检查                                               | 期望值                                     |
| -------------------------------------------------- | ------------------------------------------ |
| `cold.novels` / `warm.novels` / `hot.novels` | 240,725 / 2,515 / 2,805                    |
| 三片 `novels.id` 并集                            | 246,045，重复 0                            |
| `cold.status` 取值                               | 只有 2 和 4                                |
| `warm.status` 取值                               | 只有 5 和 6                                |
| `hot.status` 取值                                | 只有 3                                     |
| `cold.has_banner = 1`                            | 0                                          |
| `cold.like_num` / `warm.like_num` 组内最大值   | 9,999 / 354,531（是 A 判据的产物，不是钳位）|
| `click_num ≥ 100 万` 里末三位非零的本数         | 0（共 3,745 本，千位粒度，§6.6）           |
| `cold.authors` 最小 id                           | 240,726（= 本书数 + 1）                    |
| `authors` 三片行数之和 / 去重名字数              | 140,638 / 137,965                          |
| `novel_tags` 三片之和                            | 742,546                                    |
| 三片 `tags` 名字并集                             | 106                                        |
| 三片 `contests` 名字并集                         | 99                                         |
| `max(last_update)`                               | 2026-06-13                                 |
| sha256（解压后）                                   | 与 §2 表一致，也与 `manifest.json` 一致 |

全绿之后 `uv run python -m quarry.build_dataset` 必定产出同一份 parquet
（`content_hash cd773d14…`），`uv run pytest -q` 46 项断言应全过。

---

## 10. 一句话总结

1. **三片 = 按 `status` 切的三个包**，不是三个数据集；并集才是全库，跨片只有 `novels.id` 能 join。
2. **`authors` / `tags` / `contests` 的 id 在每个文件里都从头编号**，且被 `INSERT OR IGNORE`
   烧出几十万的废号——按 name 对齐，别按 id。
3. **`status` 里只有 2 和 3 是平台事实**（已完结 / 连载中）。`断更` 与 `A` 都是上游判定，
   **派生代码都不在仓库里**——所以 A 既不是「精确通道」也不是「好书」，只是四阈值 OR。

---

## 11. 与旧结论的冲突（待处理）

上面 §6.5–6.7 直接推翻了 `DATASET.md` §3 的三处说法。列在这里，避免下次又照着旧文写 SQL：

| 旧表述（`DATASET.md` §3） | 实测 |
|---|---|
| 非精确组「`click_num` 上限 3,824,000」「`like_num` 上限 9,999」 | 是**组内最大值**，由 A 判据定义产生，不是钳位（§6.5） |
| 「精确组 `comment_num`/`review_num` **全部有值**」 | 5,320 本里只有 **1,038 本**有值（19.5%）：warm 662 + hot 376（§6.7） |
| 「被截断的只有顶端，`click < 300 万` 占非精确组 99.99%」 | 显示粒度的分界线是 **100 万**，且三片一致；100 万以上末三位恒为 0（§6.6） |

**还没有改 `DATASET.md`**，因为这几句话被下游引用、改口径要同步：

- `docs/README.md` 的「关键数字」表：「上游精确池（warm + hot）5,320 本」
- `config.py` 里 `stats_precise` / `PRECISE_STATUS` 的注释（「这行的数字来自详情页精确通道」）
- `tests/` 里与 precise 相关的断言名
- App 设计文档里「5,320 本能排序」的说法

**改与不改有个共同结论**：`stats_precise` 这个名字是误导的，它实际等于「A 组」=「四阈值之一或 banner」。
行数（5,320）不用动，只是解释要换。要不要改，等确认。

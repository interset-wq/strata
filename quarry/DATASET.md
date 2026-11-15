# 数据集字典 · strata v1

> 246,045 本书、2006-08 至 2026-06 的书目快照。上游 `Novly` 的三片 sqlite
> 只是原料，本文件描述的是**我们自己构建的** `datasets/v1/`。原料本身的字段、
> id 空间与脏数据见 [`RAW.md`](./RAW.md)。
>
> 本文件的每个数字都可以用文中给的 SQL 现算出来。**凡是写死的数字，都是断言锚点**
> （`config.BASELINE`），改了就要人工确认。

```
schema_version 5 · content_hash cd773d14… · 快照日 2026-06-13
novels 246,045 · novel_tags 742,546 · authors 137,965 · contests 99 · tags 106
```

---

## 30 秒上手

```python
import duckdb
con = duckdb.connect("datasets/v1/strata-v1.duckdb", read_only=True)

# 唯一权威的结局字段是 outcome，不是 status（status 已删除，见 §4）
con.sql("select outcome, count(*) from novels group by 1 order by 2 desc")

# 上架时间在 novels_era，不在 novels.last_update
con.sql("""
  select e.est_year, count(*) books
  from novels n join novels_era e using (id)
  where not n.flg_import and e.est_year between 2015 and 2025
  group by 1 order by 1
""")
```

不想装 DuckDB 就读 parquet（`datasets/v1/parquet/*.parquet`，zstd）。
**校验只能对 parquet 做**：`strata-v1.duckdb` 每次构建字节都不同（DuckDB 内部元数据非确定），
`manifest.json` 里已标 `deterministic: false`。

---

## 1. 表：一行是什么

| 表             | 行数    | 粒度                 | 一行是什么                                                |
| -------------- | ------- | -------------------- | --------------------------------------------------------- |
| `novels`     | 246,045 | 一本书               | 书目 + 全部成绩指标 + 7 个 `flg_` 标记                  |
| `novels_era` | 246,045 | 一本书               | `nid → 日期` 定年结果（1:1 于 novels，`id` 可 join） |
| `era_stats`  | 21      | 一年                 | 年表，**已排除引进日轻**，被排除量另列两列          |
| `tags`       | 106     | 一个标签             | `tag_id` 1–106 连续，`name` 唯一                     |
| `novel_tags` | 742,546 | 一次挂载             | `(novel_id, tag_gid)`，覆盖 233,858 本（95.1%）         |
| `authors`    | 137,965 | 一个**作者名** | 按 name 去重后的代表书（不是「一个人」）                  |
| `contests`   | 99      | 一个征文             | 按 name 去重（原 209 行 → 99 名）                        |

**没有 `status` 列，也没有 `chunk` 列。** 两个都是上游的加工产物，已被剥掉：
`status` 拆成 `outcome` + `stats_precise`，`chunk`（cold/warm/hot）只是打包切分。
见 §4.1、§4.2。

---

## 2. 字段字典

### 2.1 `novels`

| 字段              | 类型        | NULL    | 实测范围                      | 含义与注意                                                                                           |
| ----------------- | ----------- | ------- | ----------------------------- | ---------------------------------------------------------------------------------------------------- |
| `id`            | BIGINT      | 0       | 2,242 ~ 777,879               | **就是站点 nid**，全局自增、严格单调。它是全库唯一的时间轴依据                                 |
| `title`         | TEXT        | 0       | —                            | 65 本是纯数字占位（`flg_placeholder_title`）                                                       |
| `author`        | TEXT        | 0       | 137,965 个不同串              | **是字符串，不是身份**。改名=新人，同名=可能两人（§5.6）                                      |
| `genre`         | BIGINT      | 0       | 2–10（无 1）                 | 2魔幻 3玄幻 4古风 5科幻 6校园 7都市 8游戏 9同人 10悬疑。**数据集不带名称，要自己映射**         |
| `outcome`       | TEXT        | 0       | `done`/`dead`/`ongoing` | **唯一权威的结局**。43,581 / 199,659 / 2,805                                                   |
| `ptype`         | BIGINT      | 0       | 2/3/4                         | 2 免费(91.9%)、3 签约(5.3%)、4 VIP(2.8%)。**是编辑漏斗层级，不是价格**                         |
| `has_banner`    | BIGINT      | 0       | 0/1                           | 667 本（0.27%）。站方运营位，不是质量分（§5.4）                                                     |
| `word_num`      | BIGINT      | 0       | 0 ~ 21,762,745                | 字数，**快照日的现值**，连载中还在长。497 本为 0（不是 NULL）。字数 <= 0表示书籍已下架或被屏蔽 |
| `click_num`     | BIGINT      | 0       | 0 ~ 118,613,000               | **人气**（累计浏览）。不是「点击次数」也不是「收藏」                                           |
| `praise_num`    | BIGINT      | 0       | 0 ~ 138,110                   | **赞**（API `fav`）。名字和语义反了，见 §3                                                  |
| `like_num`      | DOUBLE      | 58      | 0 ~ 354,531                   | **收藏**（API `markCount`）。58 个 NULL 来自负值修正                                         |
| `comment_num`   | DOUBLE      | 241,355 | 0 ~ 162,798                   | 短评数。**98.1% 是 NULL = 未采集，不是 0**                                                     |
| `review_num`    | DOUBLE      | 241,355 | 0 ~ 612                       | 长评数，同样 98.1% NULL。同上                                                                        |
| `contest_id`    | DOUBLE      | 150,488 | 1–99                         | 61.2% 的书不参加征文                                                                                 |
| `cover`         | TEXT        | 0       | —                            | 34,641 本是默认封面（`flg_default_cover`）                                                         |
| `last_update`   | TIMESTAMPTZ | 0       | —                            | **最后更新，不是上架时间**。UTC 带时区（§5.1）                                                |
| `stats_precise` | BOOLEAN     | 0       | 5,320 True                    | **这行的 click/like/praise 是否来自详情页精确通道**。决定能不能排序（§3）                     |

7 个 `flg_`：`placeholder_title`(65) / `word_zero`(497) / `default_cover`(34,641) /
`like_fixed`(58) / `praise_gt_click`(2,094) / `comment_missing`(241,355) / `import`(47)。

### 2.2 `novels_era`

| 字段                  | 类型        | 说明                                                                                           |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------- |
| `id`                | BIGINT      | join `novels.id`                                                                             |
| `est_date`          | TIMESTAMP_S | **估计的上架日**，无时区（naive）。全库 2006-08-26 ~ 2026-06-13                          |
| `est_year`          | SMALLINT    | 由 `est_date` 取年，年表都用它                                                               |
| `nid_gap`           | BIGINT      | 两侧锚点的 nid 间距。**不要用它判断精度**（能从 1 跳到 53,021）                          |
| `gap_days`          | INT         | 两侧锚点的**日期**间距，P25/50/75/90/99 = 61/84/121/211/870                              |
| `mode`              | TEXT        | `interp` / `extrap_low` / `extrap_high`。v1 全库 100% `interp`（首尾锚点恰好是首尾书） |
| `confidence`        | TEXT        | `gap_days ≤ 90` → high(141,495)；`≤365` → mid(81,438)；else low(23,112)                |
| `err_lower_bound`   | INT         | 误差**下界**：`est_date - last_update` 的正值。40,338 本 > 0，中位 3 天                |
| `after_last_update` | BOOLEAN     | `err_lower_bound > 1`，30,662 本（12.5%）                                                    |

`confidence` 的分水岭在 **2017**：2016 及以前几乎全 `low`（锚点按 2.5% 分位采样，
早期书少→锚点稀，两侧隔 1–2 年）；2017 起 0% `low`。

### 2.3 `era_stats`

| 字段                                  | 说明                            | 陷阱                                                 |
| ------------------------------------- | ------------------------------- | ---------------------------------------------------- |
| `books_new`                         | 当年新增                        | **不含引进日轻**，加 `import_books` 才是全量 |
| `authors_new`                       | 当年首次出现的作者名            | 名字口径，不是人                                     |
| `banners`                           | 当年 banner 授予量              | 最近 3 年右删失，见 `censored`                     |
| `grant_per_1k`                      | `banners / books_new × 1000` | 2006 年分母 0 → NULL，不是 0                        |
| `p50/p90/p99_view`                  | 当年新书人气分位                | 同一年内可比，**跨年不可比**                   |
| `median_word`                       | 当年新书字数中位                | 删失：老书有十年时间长，新书没有                     |
| `vip_pct`                           | `ptype=4` 占比（%）           | —                                                   |
| `import_books` / `import_banners` | 被排除的引进日轻                | 守恒式：`books_new + import_books == 当年全量`     |
| `censored`                          | 仍在删失窗口内                  | 2024–2026 为 True                                   |

### 2.4 `tags` / `novel_tags`

`tags` 是**重编号后**的：上游三片各自 `AUTOINCREMENT`，同 id 率 0%，cold 片 99 行却
撑到 710,395 号（纯废号）。这里按 `name` 字典序重编成 1–106，保证重建结果完全一致。

`novel_tags` 挂载数：1 个 24,630 本 / 2 个 35,032 / 3 个 66,411 / 4 个 90,313 /
5 个 17,467 / 6 个 3 / 7 个 2。**上限 7 是截断，不是事实**（§5.3）。

### 2.5 `authors` / `contests`

`authors` 不是人：按名字去重，取 `top_novel_clicks` 最大的那本当代表。24.6 万本书
对应 137,965 个名字，**68% 的名字只有一本书**——这不是「68% 的作者只写一本」，
是「改名 + 一次性投递 + 同人搬运」混在一起的结果。

`contests` 99 个：`2022春季征文` ~ `龙之谷征文`，跨片重复 110 行已合并，
`novels.contest_id` 已重映射。

---

## 3. 最危险的一件事：三个指标有两套精度

`stats_precise` 不是「质量标记」，只回答一句：**这行的数字是详情页给的，还是列表页显示值？**

|                                  | `stats_precise = false`（240,725 本）       | `stats_precise = true`（5,320 本） |
| -------------------------------- | --------------------------------------------- | ------------------------------------ |
| `click_num` 上限               | **3,824,000**                           | 118,613,000                          |
| `like_num` 上限                | **9,999**（恰好等于 9,999 的只有 1 本） | 354,531                              |
| `praise_num` 上限              | **9,928**                               | 138,110                              |
| `comment_num` / `review_num` | 98.1% NULL                                    | 全部有值                             |

成因不是采集器有两套逻辑，而是**同一份数据被冻结在不同年代**：历史归档段早年用列表页
采集，显示值「10903.2万」被还原成整数后只精确到千位，此后再没重采过，截断值就永久留在库里。

**规则**：

```sql
-- ❌ 错：跨精度排序，前 5,320 名之外全是截断值
select id, title from novels order by like_num desc limit 20;

-- ✅ 对：要排序/比大小，就锁在精确通道
select id, title, like_num from novels
where stats_precise order by like_num desc limit 20;

-- ✅ 对：要全库覆盖，就只用分位/比例，且承认 300 万以上是地板
select id from novels where click_num >= 100000;   -- 低端不受 cap 影响，可信
```

被截断的只有**顶端**：`click < 300 万` 的占非精确组的 99.99%，这些数是真的。
所以「人气 ≥ 10 万」这类**低门槛**筛选全库可用；「人气 ≥ 1000 万」「收藏 ≥ 1 万」
这类**高门槛**只能用在精确通道上。

---

## 4. 上游的四个加工层，全部剥掉了

上游 `Novel Hub` 不是原始数据，它自己做了四层加工。我们只取事实字段，判断一律重做。

### 4.1 `status` 5 值 → `outcome` 3 值 + `stats_precise`

上游 `status`：2 完结 / 3 连载中 / 4 断更 / 5 断更A / 6 完结A。
`A` 不是平台状态，是上游按规则派生的成绩标记：

> `断更`/`已完结` + (banner OR 人气≥1000万 OR 长评≥60 OR 收藏≥1万 OR 赞≥1万) → `断更A`/`完结A`

判定式在原 2/4/5/6 的 243,193 行上**零反例**（5/6 全部 True，2/4 全部 False），
即 `5/6` 相对 `2/4` **不携带任何额外信息**。而且它的实质是「收藏 ≥ 1 万」——
2,468 本里 2,353 本靠这一条进来，而上方截断线正好是 9,999，两件事纠缠不清。

后果最严重的一条：拿 `status=6` 当「长篇小说」会得到 108.7 万字的中位数，那是
**选择偏差**。完结且 ≥30 万字的 3,766 本里，只有 1,326 本（35%）在 A 组。

所以：`outcome` 由我们定（`done`/`dead`/`ongoing`），`stats_precise` 只表达精度，
判定式作为常量 `config.A_RULE_SQL` 留给测试复现零反例。

### 4.2 `cold/warm/hot` 三片 → 不留列

三片与 `status` 严格一一对应（cold=2/4、warm=5/6、hot=3），并集恰好 246,045。
它只是上游**为了首屏加载分批解压**做的打包切分，零信息量。留在表里只会诱使分析
把它当维度——这类错误在本项目里真实发生过一次。

### 4.3 `tags.id` → 按 name 重编号

见 §2.4。

### 4.4 `authors` / `contests` → 按 name 去重

见 §2.5。

---

## 5. 陷阱清单（每条都踩过）

### 5.1 `last_update` 不是上架时间

老书 `last_update` 是十年后的一次编辑。2015 年创建的书和 2025 年创建的书可能
`last_update` 都在 2026。**所有「某年新增多少本」必须用 `novels_era.est_date`。**

```sql
-- ❌ 这算的是「最后更新时间分布」，不是创作年代
select strftime(last_update, '%Y') y, count(*) from novels group by 1;

-- ✅
select est_year y, count(*) from novels_era group by 1 order by 1;
```

### 5.2 `id` 有 68.3% 的空洞，不能当下架率

nid 宽度 775,638（2,242 → 777,879），只有 246,045 本书，**平均 3.15 个 nid 才 1 本**。
无法从本地判断空洞是「下架」还是「nid 被评论/章节等非小说对象共用」。
**别用它估下架量**，只能当下界参考。

### 5.3 `tags` 是 top-N 截断采样，不是全量

cold 段 72 万条关联只挂在 99 个标签上，**每个标签约 7,290 本**——均匀得可疑，
是采样不是自然分布。单本标签上限 7（只有 2 本达到），说明每本只保留了前几个标签。

后果：按年算「标签密度」得到的是 **top-99 口径**下的数字，2010 年 0.53 个/本、
2026 年 4.24 个/本。方向可信（老书确实标签少），**绝对值不能当全量引用**，
也**不能**用「某标签只有 N 本」证明它冷门。

### 5.4 `has_banner` 是运营位，不是质量分

667 本（0.27%），663/667 是 VIP，**209 本其实已经断更**（成绩达标但没写完）。
它可以用作「官方精选」入口的收录条件，**不能进质量分加权**。

另外：47 本引进日轻 **100% 带 banner**，且 2006–2009 年的 banner 全是它们。
所有认可类统计必须 `where not flg_import`，否则「早期原创 banner」会凭空多出 12 个。

### 5.5 2026-05 之后的书是「看不见」，不是「没有」

`est_date` 最大值 2026-06-13，但 5 月起每千个 nid 的成书数从 ~490 掉到 36，而 nid 流速
仍是 ~72/天、一个月没变。**判据是 nid 密度，不是行数**。

- 年度序列**截止 2025**
- 2026 只能用 **1–4 月同窗口**（2022 12,262 → 2026 3,997，同比 −19.8%）
- `supply.nid_density()` 已封装，低于 `density_floor=200` 的月份一律不进序列

### 5.6 `author` 是字符串，不是人

改名 = 新人（高估新人流入、低估留存）；同名可能是两个人（低估新人）。
cohort / 留存分析必须写明这是**名字口径**。

### 5.7 NULL 与 0 是两件事，别用 `coalesce` 抹平

| 字段                                      | NULL 含义                                                   |
| ----------------------------------------- | ----------------------------------------------------------- |
| `comment_num` / `review_num`（98.1%） | **未采集**。抹成 0 会得出「99% 的书没长评」这个假结论 |
| `like_num`（58）                        | 上游值是负数，物理不可能，已置 NULL 并打 `flg_like_fixed` |
| `contest_id`（61.2%）                   | 真的不参加征文                                              |
| `era_stats.grant_per_1k`（2006）        | 分母 0。是 NULL，不是 0                                     |

### 5.8 NULL 列在 DuckDB 里是 `DOUBLE`

`like_num` / `comment_num` / `review_num` / `contest_id` 因为含 NULL，被推断成 DOUBLE。
直接 `sum()` 得浮点，`group by` 也可能出现 `10000.0`。需要整数就 `cast(... as bigint)`。

### 5.9 `LIKE` 大小写：SQLite 不敏感，DuckDB 敏感

默认封面 34,641 本含 2 条 `defaultnew.jpg` 小写变体，用 `LIKE '%defaultnew%'` 会漏成 34,639。
**统一用 `ILIKE`。**

### 5.10 人气不能跨年比较，并列还极多

`click_num` 是累计值 = 当年用户规模 × 曝光时长。2015 年的书攒了 11 年，2025 年的只有 1.5 年。
唯一可跨年比较的是**当年内部分位**。

而且全库只有 **42,840 个不同取值**（24.6 万本），中位点击 412——**大量并列，名次不唯一**。
`order by click_num` 得到的「第 N 名」在并列区没有意义。

### 5.11 三个指标的名字是错的

上游把「收藏」翻成 `like_num`（Facebook 语境），把「赞」写成 `praise_num`。
**语义正好反了。** 而本项目的 App 设计文档（`docs/schema.sql`）用的是 API 原名：

| `quarry` 数据集（上游名） | 真实语义         | 站方 API key  | `docs/schema.sql` 里的名字 |
| --------------------------- | ---------------- | ------------- | ---------------------------- |
| `click_num`               | 人气（累计浏览） | `viewTimes` | `view_num`                 |
| `like_num`                | **收藏**   | `markCount` | `mark_num`                 |
| `praise_num`              | **赞**     | `fav`       | `fav_num`                  |

两套命名并存是刻意的（数据集保留上游名便于对账），但**写 SQL 时必须看这张表**。
`order by like_num` 排的是收藏榜，不是点赞榜。

### 5.12 结局的「完结」不等于「写完」

43,581 本 `done` 里 92% 在 30 万字以下，中位 9,502 字、跨度 12 天。
真正「能推荐给别人读完」的（完结且 ≥30 万字）只有 **3,766 本（1.53%）**。
筛选必须 `outcome = 'done' and word_num >= 300000`，两个条件都要。

### 5.13 `genre` / `ptype` 是数字，数据集不带名称

不想每次重抄映射，就直接把映射写进查询（一条语句，复制即可跑）：

```sql
with genre_map(id, name) as (values
  (2,'魔幻'),(3,'玄幻'),(4,'古风'),(5,'科幻'),
  (6,'校园'),(7,'都市'),(8,'游戏'),(9,'同人'),(10,'悬疑'))
select g.name, count(*) n
from novels n join genre_map g on g.id = n.genre
group by 1 order by n desc;
```

实测**无 `genre=1`**（表里定义过「1 其他」，但一本都没有）。
`ptype`：2 免费 / 3 签约 / 4 VIP。

### 5.14 `word_num = 0` 是真实存在的，别当缺失

497 本（104 本标 done、392 本 dead、1 本 ongoing）。是空壳书，不是 NULL。
用 `flg_word_zero` 区分，`median(word_num)` 会被它们拉低——做字数分析时先决定要不要排除。

### 5.15 三个峰值错开 6 年，别混成一个「黄金期」

| 量                              | 峰值年         | 值        |
| ------------------------------- | -------------- | --------- |
| 认可密度（每千本新书获 banner） | **2015** | 22.36‰   |
| banner 绝对量                   | **2016** | 95 个     |
| 单本爆发力 P99 人气             | **2019** | 272 万    |
| 供给                            | **2022** | 37,095 本 |
| 成品（完结且≥30万）            | **2021** | 522 本    |

「2015 认可先起 → 2019 爆款见顶 → 2022 规模见顶」是三个不同的机制，
合并成一句「黄金五年」会丢掉全部信息。

---

## 6. 校验：重建后先跑这段

```bash
uv run pytest -q                       # 46 项断言，全绿才可信
```

手工快速体检：

```sql
select
  (select count(*) from novels)                          as novels,      -- 246045
  (select count(*) from novels where outcome='done')      as done,        -- 43581
  (select count(*) from novels where stats_precise)       as precise,     -- 5320
  (select count(*) from novels where has_banner)          as banners,     -- 667
  (select count(*) from novels where flg_import)          as imports,     -- 47
  (select count(*) from novel_tags)                       as tag_links,   -- 742546
  (select count(*) from authors)                          as authors,     -- 137965
  (select max(est_date)::date from novels_era)            as last_day;    -- 2026-06-13
```

任何一项不等，说明原料换了或口径改了——先停下确认，**不要**直接改基线。

重建：

```bash
uv run python -m quarry.build_dataset   # raw → datasets/v1，约 20 秒
```

同一份原料必定构建出相同的 parquet（5 个文件 sha256 逐字节一致），
`manifest.json` 的 `content_hash` 只由 parquet 决定。

---

## 7. schema 演进

改列结构必须 +1，并在 `config.SCHEMA_VERSION` 留一行说明。

| 版本 | 变化                                                               |
| ---- | ------------------------------------------------------------------ |
| v2   | 新增 `novels_era`（定年）与 `era_stats`（年表）                |
| v3   | `novels` 增 `flg_import`；`era_stats` 排除引进日轻并新增两列 |
| v4   | 删 `chunk` / `src_file`（上游打包切分，非数据属性）            |
| v5   | 删 `status`，拆成 `outcome` + `stats_precise`；A 标整体丢弃  |

---

## 8. 三句话总结

1. **只有 `novels.id`（nid）能当时间轴**，`last_update` 和 `est_date` 都是别的东西。
2. **只有 `stats_precise` 的 5,320 本能排序**，其余 24 万本的顶端被截断过，只能比门槛不能比大小。
3. **只有 `outcome='done' AND word_num>=300000` 的 3,766 本算「可读」**，`outcome='done'` 单独用会被空壳书骗。

前两条决定**怎么算**，第三条决定**算什么**。

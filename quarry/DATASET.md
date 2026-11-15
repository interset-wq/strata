# 数据集字典 · strata v1

> `schema_version 5` · `content_hash cd773d14…` · 快照日 2026-06-13
>
> 本文件描述我们构建的 `datasets/v1/`。上游三片 sqlite 的字段、id 空间与脏数据见
> [`RAW.md`](./RAW.md)。本文只记录结构、语义与使用约束，不记录统计量：所有计数以
> `manifest.json` 与 `config.BASELINE` 为准，需要时现算。

## 0. 读取

```python
import duckdb
con = duckdb.connect("datasets/v1/strata-v1.duckdb", read_only=True)

# 结局用 outcome，不存在 status 列
con.sql("select outcome, count(*) from novels group by 1 order by 2 desc")

# 上架时间在 novels_era，不在 novels.last_update
con.sql("""
  select e.est_year, count(*) books
  from novels n join novels_era e using (id)
  where not n.flg_import and e.est_year between 2015 and 2025
  group by 1 order by 1
""")
```

也可直接读 `datasets/v1/parquet/*.parquet`（zstd）。**校验只能对 parquet 做**：
`strata-v1.duckdb` 每次构建字节不同（DuckDB 内部元数据非确定），`manifest.json` 已标
`deterministic: false`。

## 1. 表与粒度

| 表 | 粒度 | 一行是什么 |
|---|---|---|
| `novels` | 一书一行 | 书目、成绩指标与 7 个 `flg_` 标记 |
| `novels_era` | 一书一行 | `nid → 日期` 定年结果，1:1 于 `novels` |
| `era_stats` | 一年一行 | 年表，已排除引进日轻，被排除量另列 |
| `tags` | 一标签一行 | `tag_id` 连续，`name` 唯一 |
| `novel_tags` | 一次挂载 | `(novel_id, tag_gid)` |
| `authors` | 一作者名一行 | 按 name 去重的代表书，**不是一个人** |
| `contests` | 一征文一行 | 按 name 去重 |

无 `status` 列，无 `chunk` 列。两者都是上游加工产物，已剥离（§4）。

## 2. 字段字典

### 2.1 `novels`

| 字段 | 类型 | NULL | 含义与约束 |
|---|---|---|---|
| `id` | BIGINT | 否 | 站点 nid，全局自增、严格单调；全库唯一的时间轴依据 |
| `title` | TEXT | 否 | 书名；含纯数字占位记录（`flg_placeholder_title`） |
| `author` | TEXT | 否 | 作者名；平台内唯一且不可修改，可作稳定身份键（§5.6） |
| `genre` | BIGINT | 否 | 2 魔幻 / 3 玄幻 / 4 古风 / 5 科幻 / 6 校园 / 7 都市 / 8 游戏 / 9 同人 / 10 悬疑；无 1 |
| `outcome` | TEXT | 否 | `done` / `dead` / `ongoing`，唯一权威的结局字段 |
| `ptype` | BIGINT | 否 | 2 免费 / 3 签约 / 4 VIP；编辑漏斗层级，不是价格 |
| `has_banner` | BIGINT | 否 | 0/1；站方运营位，非质量分（§5.4） |
| `word_num` | BIGINT | 否 | 字数，快照日现值；连载中仍在增长 |
| `click_num` | BIGINT | 否 | 人气（累计浏览）；不是点击数，也不是收藏 |
| `praise_num` | BIGINT | 否 | 赞（API `fav`）；命名与语义错位（§3 第 4 条） |
| `like_num` | DOUBLE | 是 | 收藏（API `markCount`）；NULL 来自上游负值修正 |
| `comment_num` | DOUBLE | 是 | 短评数；NULL 表示未采集，不是 0（§5.7） |
| `review_num` | DOUBLE | 是 | 长评数；与 `comment_num` 同步缺失 |
| `contest_id` | DOUBLE | 是 | 征文 id；NULL 表示未参加 |
| `cover` | TEXT | 否 | 封面 URL；默认封面存在大小写两种写法（§5.9） |
| `last_update` | TIMESTAMPTZ | 否 | 最后更新，UTC 带时区；不是上架时间（§5.1） |
| `stats_precise` | BOOLEAN | 否 | 上游 `status ∈ {3,5,6}` 的标记，即 `warm` + `hot` 两片全量；**既不表示精度，也不等于 A 标**（§3） |

7 个 `flg_`：`placeholder_title`、`word_zero`、`default_cover`、`like_fixed`、
`praise_gt_click`、`comment_missing`、`import`。均为派生布尔标记，不参与指标计算。

### 2.2 `novels_era`

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | BIGINT | join `novels.id` |
| `est_date` | TIMESTAMP_S | 估计上架日，无时区；按 nid 单调性在两侧锚点间插值 |
| `est_year` | SMALLINT | 由 `est_date` 取年，年表使用该列 |
| `nid_gap` | BIGINT | 两侧锚点的 nid 间距；不能用于判断精度 |
| `gap_days` | INT | 两侧锚点的日期间距，是 `confidence` 的依据 |
| `mode` | TEXT | `interp` / `extrap_low` / `extrap_high` |
| `confidence` | TEXT | `gap_days ≤ 90` → `high`；`≤ 365` → `mid`；否则 `low` |
| `err_lower_bound` | INT | `est_date - last_update` 的正值，误差下界 |
| `after_last_update` | BOOLEAN | `err_lower_bound > 1`，估计日晚于最后更新 |

定年精度随时间变化：锚点按 nid 分位采样，早期作品稀疏，`confidence` 以 2017 年为分界，
之前多为 `low`。使用分年序列时应同时读取该列。

### 2.3 `era_stats`

| 字段 | 含义 | 约束 |
|---|---|---|
| `books_new` | 当年新增 | 不含引进日轻，加 `import_books` 才是全量 |
| `authors_new` | 当年首次出现的作者名 | 名字即作者身份（§5.6），与人数一致 |
| `banners` | 当年 banner 授予量 | 最近年份存在右删失，见 `censored` |
| `grant_per_1k` | `banners / books_new × 1000` | 分母为 0 时为 NULL，不是 0 |
| `p50/p90/p99_view` | 当年新书人气分位 | 同年内可比，跨年不可比 |
| `median_word` | 当年新书字数中位 | 受删失影响，老书积累时间长 |
| `vip_pct` | `ptype = 4` 占比 | — |
| `import_books` / `import_banners` | 被排除的引进日轻 | 守恒式：`books_new + import_books` = 当年全量 |
| `censored` | 仍在删失窗口内 | 2024–2026 为 True |

### 2.4 `tags` / `novel_tags`

`tags` 由上游片内 id 按 `name` 字典序重编为连续编号，保证重建结果一致；
上游 id 是片内编号且大量断号，不可跨片使用。

`novel_tags` 单本最多 7 个标签，**上限来自上游截断，不是作品实际标签数**。
标签集合本身也是采样子集，不是全站字典（§5.3）。

### 2.5 `authors` / `contests`

`authors` 是名称索引：按 name 去重（name 即作者身份，见 §5.6），取 `top_novel_clicks`
最大的作品作为代表。多数名字只对应一本书，反映一次性投稿与同人搬运，
不能读作「多数作者只写一本」。

`contests` 按 name 去重，`novels.contest_id` 已重映射到去重后的编号。

## 3. 成绩指标的可比性

三件事决定这些数字能不能比。

**1）`click_num` 是累计值。** 等于当年用户规模 × 曝光时长，2015 年的作品积累十余年，
2025 年的只有一年多。跨年比较只能用当年内部分位或比例类指标。

**2）`click_num` 高位为千位粒度。** 上游对百万以上的显示值按「万」为单位保留一位小数，
还原后 `click_num ≥ 100 万` 时末三位恒为 0，并列极多。排序得到的「第 N 名」在并列区不唯一。
该粒度全库一致，不区分分片或分组。

**3）`like_num` / `praise_num` 是精确整数，但完结层受 A 规则截断。** A 规则只作用于
已完结与断更的作品，因此 `cold` 片（非 A 的完结层）这两项必然低于阈值 1 万；
连载层（`hot`）不受该规则约束，可以有高分作品。这是「达标即被标为 A」的筛选结果，
不是测量误差，不能读作上游截断：

- 跨全库比较收藏或赞是有效的，但结果按分片分层；
- 在完结层上筛「收藏 ≥ 1 万」，等价于筛 A 规则命中，不能推出「没有更多高收藏作品」。

**4）`stats_precise` 既不表示精度，也不等于 A 标。** 它等于上游 `status ∈ {3,5,6}`，
即 `warm` 与 `hot` 两片全量，包含全部连载中作品；A 标只对应 `status ∈ {5,6}`。
命名的由来是上游假设这两片走过详情页采集，实测不成立：`warm` 中多数作品的评论数同样缺失，
`click_num` 的千位粒度在两组中都存在。该列仅用于复现上游分层与兼容旧查询，
不应作为「可信 / 不可信」开关，也不宜作为分析维度。

**由此得到的写法：**

```sql
-- 按人气排序：说明粒度，接受 100 万以上的千位并列
select id, title, click_num from novels order by click_num desc limit 20;

-- 按收藏排序：有效，但结果天然按 A 组分层
select id, title, like_num from novels order by like_num desc limit 20;

-- 门槛筛选：低门槛无副作用；高门槛（≥ 1000 万 / ≥ 1 万）的结果等价于 A 规则命中
select id from novels where click_num >= 100000;
```

**4）三个指标的名字是错的。** 上游把「收藏」译作 `like_num`，把「赞」写作 `praise_num`，
两者语义与字面相反。数据集保留上游名以便对账，`docs/schema.sql` 使用 API 原名：

| `quarry`（上游名） | 真实语义 | 站方 API key | `docs/schema.sql` |
|---|---|---|---|
| `click_num` | 人气（累计浏览） | `viewTimes` | `view_num` |
| `like_num` | 收藏 | `markCount` | `mark_num` |
| `praise_num` | 赞 | `fav` | `fav_num` |

`order by like_num` 排的是收藏榜。

## 4. 已剥离的上游加工

上游 `Novel Hub` 不是原始数据，自带四层加工。本项目只取事实字段，判断一律重做。

### 4.1 `status` → `outcome` + `stats_precise`

上游 `status` 为 2 完结 / 3 连载中 / 4 断更 / 5 断更A / 6 完结A，其中 4、5、6 为派生值
（派生链见 `RAW.md` §5）。A 标是「成绩达标」标记，不携带结局信息：

- 2 与 6 都是已完结，4 与 5 都是断更，差别只在成绩；
- A 标与「长篇」「优质」无对应关系，用 `status = 6` 取长篇会产生选择偏差。

因此 `outcome` 由本项目定义；`stats_precise` 保留上游 `status ∈ {3,5,6}` 的分层信息，
仅用于兼容与复现，不承担语义。A 判定式作为常量 `config.A_RULE_SQL` 留作测试基线。

### 4.2 `chunk` → 不留列

`cold/warm/hot` 与 `status` 一一对应，是上游为分批解压做的打包切分，不含数据属性。
留列会诱使分析把它当维度，故删除。

### 4.3 `tags.id` → 按 name 重编号

见 §2.4。

### 4.4 `authors` / `contests` → 按 name 去重

见 §2.5。

## 5. 使用约束

### 5.1 `last_update` 不是上架时间

老书的 `last_update` 常是多年后的一次编辑。所有「某年新增」必须用 `novels_era.est_date`。

```sql
-- 错：这是最后更新时间分布
select strftime(last_update, '%Y') y, count(*) from novels group by 1;

-- 对
select est_year y, count(*) from novels_era group by 1 order by 1;
```

### 5.2 `id` 空洞不可归因

`id` 为自增主键、号不重用，空洞说明该行已被删除；平台不返回 404，raw 无删除标记。
空号混有版权清理、测试数据、违规下架、作者主动撤下四类来源，死号无元数据，无法区分。
不计算下架率与存活率，不把号段宽度当历史总量，不对空洞做年度内插（`RAW.md` §8）。

### 5.3 `tags` 是截断采样

上游按作品保留前几个标签，单本上限 7，标签集合为采样子集。按年统计的「标签密度」
只有方向意义，绝对值不能当全量引用；也不能用「某标签作品少」证明该标签冷门。

### 5.4 `has_banner` 是运营位

banner 授予与成绩、完结状态都可能不一致，存在「成绩达标但未完结」的样本。
可作为「官方精选」的收录条件，不能进入质量分加权。

引进日轻全部带 banner，认可类统计必须 `where not flg_import`，否则早期年份的
banner 会全部由引进作品构成。

### 5.5 2026-05 之后是采集断层

`est_date` 的最大值接近快照日，但 5 月起单位 nid 的成书数显著下降，而 nid 流速未变。
判据是 nid 密度，不是行数。

- 年度序列截止 2025；
- 2026 只能使用 1–4 月同窗口对比；
- `supply.nid_density()` 已封装，低于 `density_floor` 的月份不进入序列。

### 5.6 `author` 是稳定的作者身份

平台禁止改名、禁止重名，因此 `author` 字符串即作者身份键，不是可能漂移的昵称。
按名字做的 cohort、留存、新人流入与按作者做的统计同义，不需要再声明「名字口径」。

唯一的技术风险在字符串本身：

- 比较大小写敏感。存在仅大小写不同、其余相同的名字对，无法判定是同一人的
  不同时期写法还是两个作者，需要时应显式声明。
- 同一作者跨片出现时名字完全一致，`authors` 表的重复行是分片各自建表所致，
  不是同名两人（见 `RAW.md` §6）。

`author` 与账号无关：账号注销、封禁不体现在本字段。

### 5.7 NULL 与 0 是两件事

| 字段 | NULL 含义 | 处理 |
|---|---|---|
| `comment_num` / `review_num` | 未采集 | 不可 `coalesce` 成 0，否则会把缺失读成「没有评论」 |
| `like_num` | 上游负值，物理不可能 | 已置 NULL 并标记 `flg_like_fixed` |
| `contest_id` | 未参加征文 | 可当 0 处理 |
| `era_stats.grant_per_1k` | 分母为 0 | 保持 NULL |

0 是有效观测值，表示计数未积累；不作为删除、下架或清零的证据（`RAW.md` §7）。

### 5.8 含 NULL 的列被推断为 `DOUBLE`

`like_num`、`comment_num`、`review_num`、`contest_id` 在 DuckDB 中为 DOUBLE，
`sum()` 返回浮点，`group by` 可能出现 `10000.0`。需要整数时显式 `cast(... as bigint)`。

### 5.9 `LIKE` 大小写

默认封面存在大小写两种写法，DuckDB 的 `LIKE` 区分大小写，会漏检。统一用 `ILIKE`。

### 5.10 排名在并列区不唯一

`click_num` 取值高度集中，低区间大量并列（成因见 §3 第 2 条）。任何「第 N 名」「前 N%」
都需要声明并列处理规则，否则结果不可复现。

### 5.11 结局的「完结」不等于「写完」

`outcome = 'done'` 包含大量极短作品与提前归档的作品。可推荐样本必须同时满足字数条件：

```sql
where outcome = 'done' and word_num >= 300000
```

单独使用 `outcome = 'done'` 会被空壳作品污染。

### 5.12 非正值行在分析前剔除

正文不可得（`word_num <= 0`）或计数非正的行不代表可读作品，字数、人气、收藏的分布
统计应排除。v1 保留这些行以便追溯，未在构建阶段删除。

剔除是取样处理，不是下架统计：0 值来自默认值与未积累，不能用于推断作品是否下架。

```sql
where word_num > 0 and click_num > 0
```

### 5.13 `genre` / `ptype` 不带名称

映射直接写进查询：

```sql
with genre_map(id, name) as (values
  (2,'魔幻'),(3,'玄幻'),(4,'古风'),(5,'科幻'),
  (6,'校园'),(7,'都市'),(8,'游戏'),(9,'同人'),(10,'悬疑'))
select g.name, count(*) n
from novels n join genre_map g on g.id = n.genre
group by 1 order by n desc;
```

`ptype`：2 免费 / 3 签约 / 4 VIP。

## 6. 校验与重建

```bash
uv run pytest -q          # 断言全绿才可信
uv run python -m quarry.build_dataset
```

手工体检（期望值与 `manifest.json`、`config.BASELINE` 对照，不在此写死）：

```sql
select
  (select count(*) from novels)                     as novels,
  (select count(*) from novels where outcome='done') as done,
  (select count(*) from novels where stats_precise)  as a_group,
  (select count(*) from novels where has_banner)     as banners,
  (select count(*) from novels where flg_import)     as imports,
  (select count(*) from novel_tags)                  as tag_links,
  (select count(*) from authors)                     as authors,
  (select max(est_date)::date from novels_era)       as last_day;
```

任一项不符，先确认原料版本或口径是否变更，不要直接改基线。

同一份原料构建出的 parquet 逐字节一致，`content_hash` 只由 parquet 决定。

## 7. schema 演进

改列结构必须递增版本，并在 `config.SCHEMA_VERSION` 留说明。

| 版本 | 变化 |
|---|---|
| v2 | 新增 `novels_era`（定年）与 `era_stats`（年表） |
| v3 | `novels` 增 `flg_import`；`era_stats` 排除引进日轻并新增两列 |
| v4 | 删 `chunk` / `src_file`（上游打包切分，非数据属性） |
| v5 | 删 `status`，拆为 `outcome` + `stats_precise`；A 标整体丢弃 |

### 7.1 与规范化产物线的关系

`analysis/` 另建一条产出线，直接读 novel_hub 爬虫的原始 jsonl，产出一张
`analysis/out/novels.csv`：按 `nid` 去重、列重命名、枚举落中文真值、标签以 `|`
连在同一行内不展开；字符串已归一（非法字符换空格、非 ASCII 空白归一、压连续空格、
去首尾空白）。约束写在 `analysis/out/schema.sql`，DuckDB 导入时生效。

剔除三类不可用的行（判据与阈值见 `analysis/config.py`）：收藏为负、字数与人气
同时为 0、书名不含文字字符且字数与人气都低于阈值。第三条只删无内容者——书名
由纯数字或纯符号构成的行里，有相当一部分是真实作品（如「0.5」45.9 万字、
6.8 万点击），删掉会损失真实信号。被删的 id 逐条记入 `manifest.json`。

| 产物 | 服务对象 | 组织方式 | 约束 |
|---|---|---|---|
| `datasets/v1/` | Flutter 应用 | 反规范化，含 `flg_` 标记与定年结果 | 无 DDL，靠构建断言 |
| `analysis/out/` | 分析脚本 | 单表宽表，枚举即真值，列表不展开 | `schema.sql` 的 PK / CHECK |

两者不是版本关系，是同一上游的两种组织方式：前者用冗余换查询延迟，后者用一张
平表换分析时的直接可读。`novels_era` 与 `era_stats` 只存在于本表，`analysis/out`
不含定年结果。

## 8. 三条使用规则

1. **时间轴只用 `novels.id`**，`last_update` 与 `est_date` 都不是上架时间。
2. **结局只用 `outcome`**，`stats_precise` 是上游分片遗留标记，不是精度、也不是 A 标。
3. **可读样本要两个字条件**：`outcome = 'done'` 加字数门槛；单独使用会被空壳作品污染。

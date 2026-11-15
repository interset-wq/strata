# 上游原料说明 · Novly Release 三片 SQLite

> 本文件描述 `build_dataset.py` 的输入：`data/raw/chunks/{cold,warm,hot}_chunk.sqlite`，
> 来自上游 Novly Release 的 `assets/chunks/*.sqlite.gz`。原料仅用于重建数据集，
> 分析代码只读 `datasets/v1`；产物字段语义见 [`DATASET.md`](./DATASET.md)。
>
> 本文只记录**结构、语义与约束**，不记录统计量。所有行数与分布随快照变化，
> 需要时以 `datasets/v1/manifest.json` 与 `config.BASELINE` 为准。

## 1. 来源与文件

| 项 | 内容 |
|---|---|
| 快照日 | 2026-06-13（三片同一时点导出） |
| 格式 | SQLite 3，三片表结构完全一致（5 张表、11 个索引），可 `attach` 后跨片查询 |
| 体积 | 解压约 138 MB，gz 约 62 MB；`cold` 占绝大部分 |
| 完整性 | 解压后 sha256 与 `datasets/v1/manifest.json` 的 `source` 段逐条一致 |
| 版本管理 | 位于 `.gitignore`，不进 Git、不随 Release 分发 |

| 文件 | 上游用途 | 内容 |
|---|---|---|
| `cold_chunk.sqlite` | 静态存量，按需解压 | 主体，不含 banner 记录 |
| `warm_chunk.sqlite` | 优质存量合并包 | 与 `cold` 不重叠 |
| `hot_chunk.sqlite` | 首屏加载，按月更新 | 仅连载中作品 |

原料不可替代：缺失则无法重建数据集。已有 `datasets/v1` 时无需读取原料。

```python
import sqlite3
con = sqlite3.connect("file:data/raw/chunks/cold_chunk.sqlite?mode=ro", uri=True)
```

```sql
attach 'cold_chunk.sqlite' as cold;
attach 'warm_chunk.sqlite' as warm;
attach 'hot_chunk.sqlite'  as hot;
```

DuckDB 写法：`attach 'cold_chunk.sqlite' as cold (type sqlite)`。

## 2. 分片规则

三片按 `novels.status` 分组，不是随机切分：

| 片 | `status` |
|---|---|
| `cold` | 2 已完结 / 4 断更 |
| `warm` | 5 断更A / 6 完结A |
| `hot` | 3 连载中 |

由此产生三个必须遵守的前提：

1. **每片都是条件样本**。`warm` 的 VIP 与 banner 占比显著高于其余两片，`cold` 无 banner；
   在单片上算任何「全站比例」都会偏。
2. **并集才是完整快照**。跨片 `novels.id` 无重复，可直接 `union all`。
3. **分片不携带数据属性**。它是上游为分批解压做的打包切分，构建时丢弃（见 `DATASET.md` §4.2）。

## 3. 表结构

| 表 | 粒度 | 说明 |
|---|---|---|
| `novels` | 一书一行 | 书目与成绩字段，主键 `id` |
| `authors` | 一片一行 | 作者名 → 代表书；名称索引，不是作者实体表，也不是全站字典 |
| `tags` | 一片一行 | 本片引用到的标签，**不是全站字典** |
| `novel_tags` | 一次挂载 | `(novel_id, tag_id)` |
| `contests` | 一片一行 | 本片引用到的征文 |

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

## 4. 字段语义

| 字段 | 语义 | 约束 |
|---|---|---|
| `id` | 站点 nid，自增、严格单调、跨片唯一 | 号段不连续，见 §8 |
| `title` | 书名 | 含纯数字占位记录 |
| `author` | 作者名 | 平台内唯一且不可修改，可作稳定身份键（见 `DATASET.md` §5.6） |
| `genre` | 分类 | 取值 2–10，无 1；数据集不附名称 |
| `status` | 上游状态 | 见 §5，不可直接用于「当前是否连载」 |
| `ptype` | 编辑漏斗层级 | 2 免费 / 3 签约 / 4 VIP，不是价格 |
| `has_banner` | 站方运营位 | 非质量分，见 `DATASET.md` §5.4 |
| `word_num` | 字数，快照日现值 | 连载中仍在增长；0 表示正文不可得，见 §7 |
| `click_num` | 人气（累计浏览） | 跨年不可比；高位为千位粒度，见 `DATASET.md` §3 |
| `like_num` | 收藏（API `markCount`） | 与 `praise_num` 语义错位，见 `DATASET.md` §3 |
| `praise_num` | 赞（API `fav`） | 同上 |
| `comment_num` | 短评数 | 大量 NULL，语义为未采集，不等于 0 |
| `review_num` | 长评数 | 与 `comment_num` 同步缺失 |
| `contest_id` | 征文 id | 未参加为 NULL |
| `cover` | 封面 URL | 默认封面存在大小写两种写法 |
| `last_update` | 最后更新时间，UTC（`+00:00`） | **不是上架时间**，见 `DATASET.md` §5.1 |

## 5. `status` 的派生链

平台原生只提供两个状态，其余为上游派生：

| 值 | 标识 | 来源 |
|---|---|---|
| 1 | 其他 | 解析兜底，快照内无记录 |
| 2 | 已完结 | 平台原生 |
| 3 | 连载中 | 平台原生 |
| 4 | 断更 | 上游按「连载中 + 90 天无更新」判定 |
| 5 | 断更A | 在 4 的基础上满足 A 规则 |
| 6 | 完结A | 在 2 的基础上满足 A 规则 |
| 7 | 下架 | 上游标记，本快照已过滤 |

A 规则的阈值写在 `site_config.toml [thresholds]`，规则原文见上游 `docs/website.md` 与
`AGENTS.md`（`A status (pseudo)`）：

```
A = banner OR click ≥ 1000 万 OR review ≥ 60 OR like ≥ 1 万 OR praise ≥ 1 万
```

三点使用约束：

1. **派生代码不在公开仓库**。规则与阈值可读，执行过程不可复现，A 与结局、质量均无关。
2. **判定时点早于快照日**。`status = 4` 不等于「当前已断更」：部分行在判定时点之后仍有更新。
3. **判定不会自我更新**。抓取按 `last_update` 设 7 天 cutoff，窗口外的作品不再被访问，
   `status` 停留在最后一次判定。

需要结局时，用 `last_update` 按定义自行计算，不要直接引用 `status`。

## 6. 三套互不相通的 ID 空间

`novels.id` 是唯一可跨片 join 的键。`authors`、`tags`、`contests` 各自独立 `AUTOINCREMENT`，
且 `INSERT OR IGNORE` 跳过时同样消耗序号，导致：

- id 大量断号，起始值与本片作品数相关，而非从 1 开始；
- 同一 name 在不同片可能对应不同 id，同一 id 在不同片一定不对应同一对象。

因此这三张表只能按 `name` 跨片对齐（`build_dataset.py` 已完成重映射），
不得用其 id 做 join、排序或编号。

## 7. 数值字段的可用性

三类取值必须分开处理：

| 取值 | 含义 | 处理 |
|---|---|---|
| NULL | 未采集（`comment_num` / `review_num`） | 不可当 0 参与均值 |
| 0 | 字段默认值，新建作品计数从 0 起算 | 不能作为删除、下架或清零的证据 |
| 负值 | 计数抖动（仅 `like_num`） | 构建时置 NULL |

取样约束：正文不可得（`word_num <= 0`）或计数非正的行不构成可读作品，
在字数、人气、收藏等分布统计中应剔除；剔除数量随快照变化，不写死。
**剔除是取样问题，不是下架统计**——0 值不能用于推断作品是否下架。

## 8. ID 空洞

`id` 为自增主键、号不重用，抓取覆盖列表页全量分页而非按 id 抽样。
因此号段中的空洞说明该行已被删除：平台对已删作品不返回 404，raw 中也没有任何删除标记
（`status` 无 7 值），删除时间与原因均不可得。

空号来源至少四类：早期盗版日轻的版权清理、管理员与测试员创建的功能测试数据、
违规内容强制下架、作者联系编辑主动撤下。死号没有元数据，四类无法区分。

据此确定三条禁令：

- 不以号段宽度计算下架率或存活率；
- 不把号段宽度当作历史建书总量；
- 不对空洞做年度内插以估算供给。

可用的陈述只有一条：当前快照是「仍在架」的样本，不是历史全集的抽样。

## 9. 到 `datasets/v1` 的映射

| 原料 | 产物 | 变换 |
|---|---|---|
| `novels` | `novels` | 丢弃 `status`、`chunk`；负值置 NULL；派生 `flg_` 标记 |
| `novels.id` | `novels_era` | 按 nid 密度定年，输出估计上架日与置信度 |
| `status` | `outcome` + `stats_precise` | 2/6→`done`，4/5→`dead`，3→`ongoing` |
| `authors` / `contests` / `tags` | 同名表 | 按 `name` 跨片去重并重编号 |
| `novel_tags` | `novel_tags` | `tag_id` 重映射为全局 id |
| `last_update` | 原样保留 | 不作为上架时间使用 |

## 10. 构建前校验

```sql
-- 分片行数与 id 边界
select 'cold' src, count(*) n, min(id) lo, max(id) hi from cold.novels
union all select 'warm', count(*), min(id), max(id) from warm.novels
union all select 'hot',  count(*), min(id), max(id) from hot.novels;

-- 跨片 id 重复数，预期为 0
select
  (select count(*) from cold.novels)
+ (select count(*) from warm.novels)
+ (select count(*) from hot.novels)
- (select count(*) from (
    select id from cold.novels union
    select id from warm.novels union
    select id from hot.novels)) as dup;

-- status 取值必须落在本片允许集合内
select 'cold', status, count(*) from cold.novels group by 2
union all select 'warm', status, count(*) from warm.novels group by 2
union all select 'hot',  status, count(*) from hot.novels  group by 2;
```

校验项与期望值由 `config.BASELINE` 与 `manifest.json` 提供，不在本文写死。
任一不符即停止构建，确认原料版本或口径是否变更。

```bash
uv run python -m quarry.build_dataset
```

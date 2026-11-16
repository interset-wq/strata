# APP 设计文档 02：数据模型与种子构建

> **文档状态**：正式设计稿 v1.0（表结构定案），待评审。
> **上游依赖**：01 技术栈 §2 的十条数据硬约束、§3.1 的双库结构、§4.5 的复合搜索与「命中即收录」。
> **下游**：03 榜单设计（本文提供全部排序键与候选池口径）。
> **口径依据**：数据来自 `analysis/out/novels.csv`（245,779 行，已剔除正版日轻），
> 内容上界 **2026-05-03**；上架年由 nid 定年（104 锚点，LOO P99 = 50 天）。
> **本文的每个体积与耗时数字都是现算实测**，测量脚本见 §附录，**不引用任何历史文档里的旧数字**。

---

## 0. 结论

| 项 | 定案 |
| --- | --- |
| **物理库** | 两份：`seed.db`（只读随包）、`user.db`（可写，持久） |
| **seed.db 表** | `books`（单表扁平 23 列）+ `book_tags`（反范式 2 列），**共 2 张表** |
| **seed.db 索引** | 9 个，含 1 个**部分索引**（短篇专用）与 2 个**复合索引**（世代×分位） |
| **seed.db 体积** | SQLite **15.22 MB** / gzip **6.27 MB**（30,831 本，518 B/本） |
| **user.db 表** | 7 张：`observations` / `discovered` / `shelf` + `shelf_lists` / `annotations` / `search_history` / `prefs` / `user_stats` |
| **user.db 增长** | 观测行 **≈59 B/行**；10 万行观测 ≈ 5.8 MB（单表） |
| **跨库关联** | 只用 `nid`；**禁止用 rowid**（种子重发后 rowid 重排） |
| **预计算列** | 5 列分位/比率随种子携带，代价 **+25 B/本**；其中 `pr`（赞藏比）单列换 **800× 查询加速** |
| **不建** | `tags`/`authors`/`contests` 维度表；分片；FTS5；`genres` 枚举表 |

**两条反直觉结论（都由实测得出，且都推翻了直觉写法）：**

1. **比值型指标必须预计算**。赞藏比榜现算 `praises*1.0/favs` 要 **44.9 ms**；
   预计算成 `pr` 列后 **0.056 ms**——**800 倍**。代价仅 +23 B/本。
   这不是可选优化，是「比率榜」能存在的前提。
2. **部分索引（partial index）是短篇榜的唯一可行解**。
   短篇只占种子池的 33%，走 `idx_favs` 要扫 3 倍才凑够 50 条 → **15.1 ms**；
   建 `WHERE words<=50000 AND status='已完结'` 的部分索引 → **0.045 ms**，且只增 **1.3 B/本**。

---

## 1. 为什么是两份物理库

01 §3.1 已定：种子随安装包分发、覆盖安装整包替换，用户数据不可重建。
因此**不是一份库两张表，而是两份库文件**：

| 文件 | 位置 | 权限 | 覆盖安装 | 生命周期 |
| --- | --- | --- | --- | --- |
| `seed.db.gz` | App bundle / assets | 只读 | 随包替换 | 随版本发布 |
| `seed.db` | `seed/seed-<version>.db` | 只读打开 | **按版本比对替换** | 与包版本同寿命 |
| `user.db` | 应用数据目录 | 读写 | **保留** | 直到卸载 |

- **`seed.db` 是解压副本**，不是 assets 内的原文件——SQLite 无法打开 Android assets 内的文件。
  首次启动或版本变更时解压到数据目录，用包内 `manifest.json` 的版本与库内 `seed_meta.version`
  比对决定是否替换。**替换是整文件换名，不做增量 UPDATE**。
- **`user.db` 永不随安装替换**。覆盖安装不丢数据，卸载才丢。
- Go 侧同时持有两个连接，`ATTACH DATABASE ... AS seed` 做跨库查询；
  同一本书取「`observed_at` 较新者」。

**跨库关联只能用 `nid`**（SFACG 的稳定 id）。种子重发后 `rowid` 会重排，
而观测必须跨种子版本继续挂在同一本书上——这是 `observations` 用
`PRIMARY KEY(nid, observed_at)` 而非自增 id 的根本原因。

---

## 2. `seed.db` 表结构

### 2.1 `books`——单表扁平 23 列

| # | 列 | 类型 | 空 | 口径说明 |
| --- | --- | --- | --- | --- |
| 1 | `nid` | INTEGER PK | 否 | SFACG 稳定 id。**跨库唯一键，不可变** |
| 2 | `title` | TEXT | 否 | 书名。最大 41 字符，p99 = 15 |
| 3 | `author` | TEXT | 否 | 作者名。最大 23 字符。**同名即同人**，平台无 author id |
| 4 | `genre` | TEXT | 是 | 题材。**9 种取值**：魔幻 34.9% / 同人 12.9% / 校园 12.9% / 玄幻 12.1% / 都市 9.5% / 科幻 7.1% / 游戏 5.2% / 古风 3.4% / 悬疑 2.1% |
| 5 | `price_type` | TEXT | 是 | 免费 91.9% / 签约 5.2% / VIP 2.8% |
| 6 | `status` | TEXT | 是 | 连载中 82.3% / 已完结 17.7%。**是 2026-05-03 的快照态**，非当期状态 |
| 7 | `contest` | TEXT | 是 | 征文届次，**99 种非空取值**（如「十征长篇」「第九届冬季征文」），38.8% 的书有值。**单值**，无多值 |
| 8 | `words` | INTEGER | 是 | 总字数。p50 = 10,418 / p95 = 228,975 / max 21,556,720。**495 本为 0**（缺失） |
| 9 | `clicks` | INTEGER | 是 | 点击。1.8% 为 0。**累计量，跨时点不可比**（报告 02/08） |
| 10 | `favs` | INTEGER | 是 | 收藏。**12.2% 为 0**（零膨胀严重）。上游字段名是 `like_num`，语义为收藏 |
| 11 | `praises` | INTEGER | 是 | 点赞。13.5% 为 0。上游字段名 `praise_num` |
| 12 | `featured` | INTEGER | 是 | banner 位。**620 本**。图上无书名，UI 须叠字 |
| 13 | `cover_url` | TEXT | 是 | 封面 URL。**仅 46.4% 非空**——banner 书大面积缺失是清洗所致（见 §2.5） |
| 14 | `updated_at` | TEXT | 是 | 最后更新时刻 `YYYY-MM-DD HH:MM:SS`。**只可作「时长」用，不可作时间轴** |
| 15 | `est_year` | INTEGER | 否 | 定年（log-nid 分段线性插值，104 锚点）。**分位与世代榜的分组键** |
| 16 | `est_date` | TEXT | 否 | 定年日期 `YYYY-MM-DD` |
| 17 | `est_conf` | TEXT | 否 | 定年置信度 `high`/`mid`/`low`（锚点间隔 ≤90/≤365/更远） |
| 18 | `tags` | TEXT | 是 | 标签管道串。**仅作展示与兜底**，查询走 `book_tags` |
| 19 | `fav_pctl` | REAL | 是 | 世代内收藏分位（全库参照，1.0 = 该世代最强） |
| 20 | `click_pctl` | REAL | 是 | 世代内点击分位 |
| 21 | `praise_pctl` | REAL | 是 | 世代内赞分位 |
| 22 | `pr` | REAL | 是 | 赞藏比 `praises/favs`，**`favs<10` 置 NULL** |
| 23 | `pctl_pr` | REAL | 是 | 赞藏比在世代内的分位 |

**类型选择的三个决定：**

- **枚举存 TEXT 不存 INTEGER**。`genre` 9 值、`price_type` 3 值、`status` 2 值。
  改成 INTEGER 码实测省 **2.42 MB（20.4%）**——但 gzip 后只省 **0.49 MB**，
  因为枚举值高度重复、gzip 压缩率极高。代价是端上必须维护码表 + JOIN，
  且 `status` 只有 2 值却要做 `status=1` 这类不可读的比较。**不划算，不改。**
- **时间存 TEXT 不存 INTEGER**。`updated_at` 存 `YYYY-MM-DD HH:MM:SS` 而非 unix 秒：
  端上要直接展示与按日期范围比较（断更时长榜），TEXT 可直接字典序比较，
  且 `updated_at < '2025-01-01'` 可读。实测代价约 12 B/本。
- **分位存 REAL 不存档位**。报告 18 实测三列 REAL 分位 **+25 B/本**（gzip +0.49 MB）。
  **不预存 p10/p25/p50/p75/p90/p99 六档**——档位由端上从连续值派生，
  预存六档要多写 6 列 × 30,831 行，收益仅为省几次浮点比较。

### 2.2 `book_tags`——反范式 2 列

```sql
CREATE TABLE book_tags(nid INTEGER NOT NULL, tag TEXT NOT NULL);
```

| 项 | 值 |
| --- | --- |
| 行数 | **111,708** 行（3.6 行/本） |
| 不同标签 | **105 种** |
| 每本标签数 | 中位 10，上限 27；**5.0% 的书无标签**（无 contest 的书占 7.8%，有 contest 的仅 0.5%） |

**为什么要有这张表**（实测对照）：

| 查法 | 耗时 | 查询计划 |
| --- | --- | --- |
| `WHERE tags LIKE '%战斗%'`（管道串） | 0.082 ms | SCAN books |
| `JOIN book_tags WHERE tag='战斗'` | **0.053 ms** | SEARCH t USING COVERING INDEX idx_bt |

管道串 LIKE 在**种子池内**看似够快（0.082 ms），但它是**子串匹配**——
`LIKE '%战斗%'` 会同时命中「战斗」「战斗种族」等不同标签，无法区分；
要精确匹配某标签必须写 `LIKE '%|战斗|%'`，那就退化成全表扫描。
`book_tags` 的 JOIN 走 `idx_bt` 索引，是真正的等值匹配。

> 全库规模下差距是 22 倍（报告 18 实测 9.10 ms vs 0.42 ms）；
> 种子池规模下差距缩小到 1.5 倍，但**语义正确性**的差距不变。

**`tags` 列仍保留**，因为：① 列表页要一次取回全部标签，避免 N+1；
② 兜底路径（官方搜索结果回填）；③ 体积只增约 55 B/本且 gzip 高度可压。

### 2.3 索引：9 个，含部分索引与复合索引

| 索引 | 体积 | 服务查询 | 实测加速 |
| --- | --- | --- | --- |
| `idx_bt(tag, nid)` | 2.11 MB | 标签筛选 | 22×（全库口径） |
| `idx_updated(updated_at)` | 0.83 MB | 断更时长榜 | **118×** |
| `idx_author(author)` | 0.64 MB | 作者精确查询 | **104×** |
| `idx_year_favpctl(est_year, fav_pctl DESC)` | 0.59 MB | 同世代收藏分位榜 | **98.6×** |
| `idx_year_clickpctl(est_year, click_pctl DESC)` | 0.59 MB | 同世代点击分位榜 | 11.3×（单列）/ **≈100×**（复合） |
| `idx_genre_favs(genre, favs DESC)` | 0.52 MB | 题材×收藏榜 | **88.6×** |
| `idx_favs(favs DESC)` | 0.32 MB | 收藏榜 Top50 | **89.7×** |
| `idx_pr(pr DESC)` | 0.46 MB | 赞藏比榜 | **800×** |
| `idx_shortfav(favs DESC) WHERE words<=50000 AND status='已完结'` | **0.04 MB** | 短篇收藏榜 | **336×**（15.1ms→0.045ms） |
| **合计** | **6.11 MB（占库 40.2%）** | | |

**四条索引决策，全部由实测得出：**

1. **复合索引优于单列**。`idx_year`（单列）+ `idx_favpctl`（单列）两个索引共 0.96 MB，
   换 `idx_year_favpctl` 一个复合索引 0.59 MB，**体积更小且快一个数量级**。
   实测单列 `idx_favpctl` 甚至让查询**变慢**（4.77 ms → 16.23 ms）——
   因为它只能定位到分位区间再回表排序，而复合索引直接按序输出。
2. **部分索引是短篇榜的正解**。通用 `idx_favs` 对短篇榜有害：
   短篇只占 33%，SQLite 走 `idx_favs` 从高收藏往下扫，要扫 3 倍才凑够 50 条
   （**15.1 ms，比无索引的 4.9 ms 还慢**）。部分索引把候选集直接缩到短篇子集，
   只需 **1.3 B/本** 就换来 **336×** 加速。
3. **比值指标必须预计算**。`pr` 列 + `idx_pr` 共 0.46 MB，
   把赞藏比榜从 44.9 ms 降到 0.056 ms。
   **预算是必须付的**——不做预计算就没有比率榜。
4. **标题索引不建**。`idx_title` 体积 42.6 B/本（1.20 MB），
   但 `title LIKE '%斗破%'` 的前缀通配符用不上 B-tree，**只快 2.6×**。
   标题搜索走内存索引（§4.3），不占持久化体积。

**「新书榜」必须逐代查询**。`WHERE est_year>=2024 ORDER BY fav_pctl DESC`
这个写法会选错索引（实测 0.578 ms）；改成**按代分别查询再合并**
（`WHERE est_year=? ORDER BY fav_pctl DESC`）是 **0.047 ms**。

### 2.4 `seed_meta`——版本与上界

随包一个小表（3 列 × 1 行），记录：

| 键 | 值 | 用途 |
| --- | --- | --- |
| `schema_version` | 整数 | 表结构版本，升级时校验 |
| `seed_version` | 语义版本 | 与包内 `manifest.json` 比对，决定是否替换 |
| `content_end` | `2026-05-03` | 数据内容上界，UI 必须显示 |
| `built_at` | ISO8601 | 构建时刻 |
| `book_count` | 30,831 | 行数自校验 |
| `tag_count` | 105 | 同上 |
| `gen_min` / `gen_max` | 2007 / 2025 | 定年覆盖范围 |
| `source_coverage` | `0.689` | **对在架书的覆盖率**，UI 用于说明「未收录 ≠ 不存在」 |

> `source_coverage` 是产品诚实性的关键。数据集对在架书覆盖约 68.9%（报告 10），
> 剩余部分不是「不存在」而是「我们没抓到」。这个数字必须随包下发，
> 让 UI 在任何「未收录」场景都能给出准确说明。

### 2.5 数据清洗遗留（必须写进 UI 口径）

| 问题 | 事实 | UI 要求 |
| --- | --- | --- |
| **封面大面积缺失** | banner 书 620 本中仅 71 本有封面（清洗时置空：原始数据的选择器把多本书挂到同一封面，共用组内非属主的封面被判错） | 无封面用占位图；**不得显示「无封面」暗示书没有图** |
| **封面时间戳 ≠ 授予时点** | 封面年月是「最后一次换图时间」，与定年偏差中位 **+338 天** | 不做时序推断；不用封面反推上架时间 |
| **tags 有空值** | 5.0% 的书无标签 | 标签栏隐藏，不显示「无标签」 |
| **words 有 0 值** | 495 本 | 字数显示「—」而非「0 字」 |
| **favs/praises 零膨胀** | 12.2% / 13.5% 为 0 | 收藏数显示「0」是真实的，不要隐藏 |
| **`status` 是快照态** | 2026-05-03 的状态 | 详情页标注「状态为 2026-05-03 快照」 |

---

## 3. `user.db` 表结构

`user.db` 在应用数据目录，可写，**永不随安装替换**。

```sql
-- 3.1 观测流水：每次进入详情页追加一行，只追加不更新
CREATE TABLE observations(
  nid         INTEGER NOT NULL,
  observed_at INTEGER NOT NULL,   -- unix 秒
  clicks      INTEGER,
  favs        INTEGER,
  praises     INTEGER,
  words       INTEGER,
  status      TEXT,
  updated_at  TEXT,
  source      TEXT NOT NULL DEFAULT 'detail',  -- detail | search | rank
  PRIMARY KEY(nid, observed_at)
);
CREATE INDEX idx_obs_time ON observations(observed_at DESC);
```

| 项 | 实测 |
| --- | --- |
| 单表体积 | **≈59 B/行**（WITHOUT ROWID 复合主键） |
| 1,000 行 | 84 KB |
| 5,000 行 | 368 KB |
| 20,000 行 | 1.4 MB |
| 100,000 行 | 5.8 MB |
| gzip 后 | 100,000 行 → 2.6 MB |

**保留策略**：全保留 10 万行是 5.8 MB，单用户可接受。
但**端上必须做保留期裁剪**——90 天前的观测对「近 30 天涨幅」榜单已无用。
建议保留 180 天，裁剪后约 2 MB。裁剪用 `DELETE FROM observations WHERE observed_at < ?`，
按月批量执行，**不做 VACUUM**（碎片由 SQLite 自动复用）。

> `WITHOUT ROWID` 与普通行存实测几乎同体积（59.2 vs 58.2 B/行），
> 但复合主键 `(nid, observed_at)` 省掉了自增 id 列，且天然去重——
> 同一本书同一秒的重复抓取会因主键冲突被忽略。**选它主要是为了语义正确，不是省空间。**

```sql
-- 3.2 官方搜索命中、种子未收录的书
CREATE TABLE discovered(
  nid         INTEGER PRIMARY KEY,
  title       TEXT NOT NULL,
  author      TEXT,
  genre       TEXT,
  words       INTEGER,
  favs        INTEGER,
  praises     INTEGER,
  cover_url   TEXT,
  summary     TEXT,
  source      TEXT NOT NULL,   -- html | json | reffer
  observed_at INTEGER NOT NULL
);
```

**收录 ≠ 进入统计**。`discovered` 的条目没有定年、没有历史指标、没有分位，
**不参与任何榜单排序与世代统计**，UI 单独标注「官方目录，无统计数据」。
理由与分析口径一致：累计指标必须同世代/同期比较（报告 02/08），
把搜索结果并进 `books` 会让分位被无基线样本污染。

```sql
-- 3.3 书架 / 分组
CREATE TABLE shelf(
  nid      INTEGER PRIMARY KEY,
  added_at INTEGER NOT NULL,
  list_id  INTEGER,          -- 0 = 默认书架
  note     TEXT
);
CREATE TABLE shelf_lists(
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

-- 3.4 标注与摘抄
CREATE TABLE annotations(
  id         INTEGER PRIMARY KEY,
  nid        INTEGER NOT NULL,
  chapter    TEXT,
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER
);
CREATE INDEX idx_anno_nid ON annotations(nid, created_at DESC);

-- 3.5 搜索历史（联想去重与「最近搜过」）
CREATE TABLE search_history(
  id      INTEGER PRIMARY KEY,
  keyword TEXT NOT NULL,
  at      INTEGER NOT NULL,
  hits    INTEGER
);
CREATE INDEX idx_sh_at ON search_history(at DESC);

-- 3.6 用户偏好（题材/标签/字数范围/排序偏好）
CREATE TABLE prefs(key TEXT PRIMARY KEY, value TEXT);

-- 3.7 本机统计缓存（自算，不进种子）
CREATE TABLE user_stats(
  nid            INTEGER PRIMARY KEY,
  fav_delta_30d  INTEGER,
  click_delta_30d INTEGER,
  obs_count      INTEGER,
  first_seen     INTEGER,
  last_seen      INTEGER
);
```

### 3.1 「用得越多越准」的落地

`observations` 是这个产品承诺的唯一实现。三层价值：

| 层级 | 能力 | 数据要求 |
| --- | --- | --- |
| L1 详情页新鲜度 | 打开的书显示最新收藏/点击/字数/状态 | 1 条观测 |
| L2 本机涨幅榜 | 「这本书近 30 天收藏涨了多少」 | 同一本书 ≥2 条观测且间隔 ≥30 天 |
| L3 热度迁移榜 | 哪些短篇正在升温 | ≥N 本书各 ≥2 条观测 |

**L2/L3 样本不足时隐藏整个榜单，不做降级展示**（03 §4.7 已定）。

`user_stats` 是**缓存而非真相**——每次观测写入后增量更新，
但可从 `observations` 全量重算（这正是「观测不可重建」的另一面：
观测丢了就丢了，但统计可以重算）。

### 3.2 跨库查询模式

```sql
-- 同一本书取较新值：种子基线 vs 本机观测
SELECT b.nid, b.title,
       COALESCE(o.favs, b.favs)  AS favs,
       COALESCE(o.observed_at, 0) AS observed_at,
       CASE WHEN o.observed_at IS NULL THEN 'seed' ELSE 'local' END AS src
FROM seed.books b
LEFT JOIN main.observations o
       ON o.nid = b.nid
      AND o.observed_at = (SELECT MAX(observed_at) FROM main.observations
                            WHERE nid = b.nid)
WHERE b.nid = ?;
```

**UI 必须区分 `src`**：种子基线显示「数据截至 2026-05-03」，
本机观测显示「本地更新于 X」。混在一起就是撒谎。

---

## 4. 搜索与内存索引

### 4.1 三层复合搜索（01 §4.5 已定）

| 层 | 来源 | 延迟 | 作用 |
| --- | --- | --- | --- |
| L0 联想 | 本地前缀索引 → 官方 `op=searchreffer` | 即时 | 输入过程中补全书名 |
| L1 本地 | `seed.db` + `user.db` + 内存索引 | <1 ms | 有统计与分位的书 |
| L2 官方 | HTML 全量 + JSON 评分 | 200–500 ms | 本地没有的书 |

### 4.2 为什么标题不走 SQL

实测 `WHERE title LIKE '%斗破%'` 在种子上要 **8.99 ms**，
`WHERE title=?` 要 **7.78 ms**（`idx_title` 只快 2.6×，不值得 1.20 MB 索引）。

### 4.3 内存索引实测

端上启动时从 `seed.db` 读 30,831 条标题+作者，建内存结构：

| 操作 | 实测 |
| --- | --- |
| 建索引（57,416 键） | **17.7 ms** |
| 精确查（哈希） | **0.07 µs** |
| 前缀扫描（全键遍历） | 3.89 ms |

**精确查 0.07 µs，是 SQL 的 11 万倍**——这是端上必须有内存索引的直接理由。
但前缀扫描 3.89 ms 对输入法逐字符联想偏慢，**这是 v1 的已知性能债**：

- v1 方案：前缀扫描 3.89 ms（可接受，但每个按键都扫）
- v2 方案：预构建**有序数组 + 二分查找**（前缀区间切片），预计 <0.1 ms；
  或构建 trie。内存开销需在 30,831 本规模上实测后再定。

**不做 FTS5**：种子规模小，内存索引足够；且 FTS5 对中文两字词的 trigram MATCH
有已知失效（早期实测）。

---

## 5. 种子构建流水线

```
analysis/out/novels.csv (245,779 行)
    ↓ ① 剔除正版日轻（4 类授权作者，47 行）
    ↓ ② 定年（eras.estimate，104 锚点）→ est_date / est_year / est_conf
    ↓ ③ 过滤 est_year ∈ [2007, 2025]（2026 年是右删失样本）
    ↓ ④ 种子选取：收藏 Top20k ∪ 近1年上架 ∪ 近90天更新 ∪ 月榜归档 ∪ banner 全集
    ↓ ⑤ 补短篇：双组分位 Top2000（报告 19）
    ↓ ⑥ 分位计算：全库 × est_year（不在种子池内算！）
    ↓ ⑦ pr / pctl_pr 计算
    ↓ ⑧ 建表 + 建索引
    ↓ ⑨ VACUUM + ANALYZE
seed.db (15.22 MB) → gzip (6.27 MB) → 随包分发
```

### 5.1 三条不可违背的构建规则

1. **分位在全库算，不在种子池内算**。种子池是「精选」，在池内重算分位会改分母，
   导致榜单分数不可跨版本比较。构建期一次算好，端上只读。
2. **定年在构建期完成**。端上不做插值（104 锚点 + 分段线性插值不是能在手机上跑的负载）。
3. **种子只增不减**。种子源头本身已缺失大量数据（对在架书覆盖 68.9%），
   再按「用户高概率需要」筛选，实际演化只会增补与刷新数值，几乎不会移除。
   **v1 不为「种子删书」写迁移逻辑**——观测保留只是结构自然产生的结果。

### 5.2 构建期校验（构建必须自证）

| 校验项 | 判据 |
| --- | --- |
| 行数 | `books` 行数 == `seed_meta.book_count` |
| nid 唯一 | `COUNT(DISTINCT nid) == COUNT(*)` |
| 分位范围 | 三列分位全部 ∈ [0, 1] |
| 分位参照系 | 抽样 20 本重算分位，与库中值误差 < 1e-6 |
| 标签反范式一致 | `book_tags` 行数 == 各书标签数之和 |
| 索引一致 | `PRAGMA index_list` 与预期清单逐条比对 |
| 完整性 | `PRAGMA integrity_check` == `ok` |
| 体积 | 超阈值（当前 6.27 MB gzip）告警 |

---

## 6. 迁移与版本策略

### 6.1 三种版本，互相独立

| 版本 | 变更频率 | 影响 |
| --- | --- | --- |
| `schema_version` | 极少 | 表结构变化时 +1。**用户库需要迁移，种子库整体替换** |
| `seed_version` | 随发版 | 种子内容更新。**只换文件，不迁移** |
| 内容上界 | 随发版 | `content_end`。UI 显示的数据时点 |

### 6.2 升级路径

```
启动 → 读包内 manifest.json.seed_version
     → 比对数据目录 seed/seed-<version>.db
        ├─ 不存在 → 解压 seed.db.gz → 落盘 → 删旧文件
        └─ 存在且版本一致 → 直接用
                └─ 存在但版本不同 → 删旧 → 解压新的
     → 打开 user.db → 比对 schema_version
        ├─ 一致 → 直接用
        └─ 不一致 → 执行迁移脚本（事务内）
```

**种子替换是整文件换名，不是增量 UPDATE**——这是「种子只读」的落地形态。

### 6.3 用户库迁移原则

- 迁移脚本**必须在事务里**，失败则回滚并保留原库；
- 迁移只动 `user.db`，**永不触碰 `seed.db`**；
- 迁移前自动备份一份 `user.db.bak`，成功后删除；
- 迁移必须**向前兼容一个版本**（v1 的库能被 v2 打开，反之不必）。

---

## 7. 待决问题

| # | 问题 | 当前建议 | 依据 |
| --- | --- | --- | --- |
| 1 | 标题前缀联想的端上结构 | v1 全键扫描 3.89 ms；v2 换有序数组二分 | §4.3 实测 |
| 2 | 观测保留期 | 180 天，按月裁剪 | §3 实测 59 B/行 |
| 3 | `contest` 是否需要独立维度表 | **不建**。99 种取值、字符串极短、`GROUP BY` 实测 1.53 ms | §2.1 |
| 4 | `genre` 是否需要枚举码表 | **不建**。TEXT 直读，gzip 后体积差仅 0.49 MB | §2.1 实测 |
| 5 | `discovered` 条目是否也要预计算分位 | **不要**。无定年、无基线，纳入会污染分位分母 | §3 口径 |
| 6 | 是否随种子携带历史月榜 | **建议携带**。165 个月 × 4 类榜，原始 1.9 MB，压缩后更小 | 03 §4.5 |
| 7 | 短篇的部分索引阈值（5 万字）是否随定义变更 | 阈值变更时重建索引；构建期一次性完成 | 报告 19 |
| 8 | `user_stats` 是否需要独立表 | v1 需要（L2/L3 榜单要全表聚合） | §3.1 |

---

## 附录：测量方法

本文所有数字来自**真实建库 + 真实 gzip + 真实查询计时**，
种子规模 30,831 本（29,396 ∪ 1,398 短篇补入，报告 18/19 定案）。
测量脚本：`analysis/` 下的一次性探针（建库、gzip、索引逐项归因、
30 次查询取中位数、EXPLAIN QUERY PLAN 校验）。
**报告与本文的数字不互相引用，一律现算。**

| 口径 | 值 |
| --- | --- |
| 数据源 | `analysis/out/novels.csv` 245,779 行（已剔除正版日轻） |
| 内容上界 | 2026-05-03 |
| 种子规模 | 30,831 本 |
| SQLite | 15.22 MB（518 B/本） |
| gzip | 6.27 MB |
| 裸表（无索引） | 9.11 MB |
| 索引合计 | 6.11 MB（40.2%） |
| `book_tags` | 111,708 行 / 105 种标签 |
| 查询计时 | 30 次取中位数 |

---

## 下一篇

**03 榜单设计**（已存在 v0.2）需回填本文定案的内容：
分位字段从三列扩到五列（新增 `pr` / `pctl_pr`）、
候选池口径落定为「30,831 本复合种子」、短篇榜的排序键与部分索引、
以及新书榜「按代查询再合并」的查询约定。

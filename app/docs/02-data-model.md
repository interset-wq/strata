# APP 设计文档 02：数据模型与种子构建
> **2026-11-19 V3 更新**：`schema_version=3`、`books` 28 列（新增 `form`/`lqs`/`lqs_pctl`/`vel_pctl`），
> 种子 18,124 本（47 授权）、`seed_version=20260503.12`（已取消新书发现渠道，见 09 附录 E.8；征文保底见 E.9；封面补全见 E.10；弃书规则+invalid 见 E.11/E.12；弃书质量豁免+对话判据 v2 见 E.13）；下方表格中的 24 列/30,878 为 v2 历史快照。

> **表结构定案 v1.0**。所有体积/耗时为真实建库实测（`app/tools/seedbuild/build_seed.py`），
> 不引用历史文档旧数字。上游约束见 01 §2；搜索口径见 04。

## 0. 结论

| 项           | 定案                                                                                                                                                                                         |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 物理库       | `seed.db`（只读随包）+ `user.db`（可写持久），跨库只认 `nid`，禁 rowid                                                                                                                 |
| seed.db      | `books` 24 列 + `book_tags` 2 列 + `seed_meta`，共 3 表 9 索引；唯一约束：`UNIQUE(cover_url)`、`book_tags` 主键 `(nid,tag)`、`deep_ranks` `UNIQUE(est_year,metric,nid)`（随下次种子重建生效）                                                                                                                         |
| seed.db 体积 | SQLite 16.02 MB（519 B/本）/ gzip 6.67 MB；索引占 6.12 MB（38.2%）                                                                                                                           |
| user.db      | 12 表：`observations` / `book_meta` / `covers` / `discovered` / `watchlist` / `novel_chapters` / `shelf`+`shelf_lists` / `annotations` / `search_history` / `prefs` / `user_stats` / `refresh_attempts`；观测 ≈59 B/行 |
| 预计算       | 五列分位/比率随种子携带（+25 B/本）；`pr` 预计算使赞藏比榜 44.9ms→0.056ms（800×）                                                                                                        |
| 不建         | `tags`/`authors`/`contests` 维度表；枚举码表；FTS5；分片；STRICT 表                                                                                                                    |
| 字符串       | 全 `TEXT`，不用 `VARCHAR(n)`（`n` 被 SQLite 忽略，零约束零信息）；不加长度/CHECK 约束——CHECK 逐行求值使 10 万行写入 58→201ms，超长标题会整批回滚；合法性由 Go 侧常量 + 逐条降级保证 |

## 1. 双库

`seed.db.gz` 在 assets（SQLite 无法直接打开），首启/版本变更解压到
`seed/seed-<version>.db`，按 `manifest.json` 与 `seed_meta.seed_version` 比对，**整文件换名替换、不做增量 UPDATE**。`user.db` 覆盖安装保留、卸载才丢。Go 侧双连接，`ATTACH ... AS seed` 跨库查询，同一字段取 `observed_at` 较新者。

`observations` 主键用 `(nid, observed_at)` 而非自增 id：种子重发后 rowid 重排，
观测必须跨种子版本续挂同一本书。

## 2. seed.db

### 2.1 `books`（24 列）

| #      | 列                                                                     | 类型       | 说明                                                                                                |
| ------ | ---------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------- |
| 1      | `nid`                                                                | INTEGER PK | SFACG 稳定 id，跨库唯一键                                                                           |
| 2      | `title`                                                              | TEXT       | 最长 41 字符（p99=15）；站内强制唯一，快照重名=改名窗口伪影，构建期校验阻断（§5）                   |
| 3      | `author`                                                             | TEXT       | 同名即同人                                                                                          |
| 4      | `genre`                                                              | TEXT       | 9 值：魔幻 34.9%/同人 12.9%/校园 12.9%/玄幻 12.1%/都市 9.5%/科幻 7.1%/游戏 5.2%/古风 3.4%/悬疑 2.1% |
| 5      | `price_type`                                                         | TEXT       | 免费 91.9%/签约 5.2%/VIP 2.8%                                                                       |
| 6      | `status`                                                             | TEXT       | 连载中 82.3%/已完结 17.7%；快照态非当期                                                             |
| 7      | `contest`                                                            | TEXT       | 征文届次，99 种非空取值，38.8% 有值，单值                                                           |
| 8      | `words`                                                              | INTEGER    | p50=10,418 / p95=228,975 / max 21,556,720；5 本为 0                                                 |
| 9      | `clicks`                                                             | INTEGER    | 累计量，跨时点不可比                                                                                |
| 10     | `favs`                                                               | INTEGER    | 上游字段名 `like_num`，语义为收藏；5.0% 为 0                                                      |
| 11     | `praises`                                                            | INTEGER    | 上游 `praise_num`；6.7% 为 0                                                                      |
| 12     | `featured`                                                           | INTEGER    | banner 位 667 本（含正版 47）；图上无书名，UI 叠字                                                  |
| 13     | `cover_url`                                                          | TEXT       | v3 当前 17,265/18,124 非空（95.5%）；UNIQUE——平台每书唯一路径，`rs`/`rss` 视为同一图床；默认封面为 NULL   |
| 14     | `updated_at`                                                         | TEXT       | 只可作时长用，不可作时间轴                                                                          |
| 15     | `est_year`                                                           | INTEGER    | 定年（log-nid，104 锚点）；分位与世代榜分组键                                                       |
| 16     | `est_date`                                                           | TEXT       | 定年日期                                                                                            |
| 17     | `est_conf`                                                           | TEXT       | exact/high/mid/low（exact=App API `addTime` 直接核实的锚点书；high/mid/low=锚点间隔 ≤90/≤365/更远）|
| 18     | `tags`                                                               | TEXT       | 管道串，仅展示与兜底；查询走 `book_tags`                                                          |
| 19–23 | `fav_pctl` / `click_pctl` / `praise_pctl` / `pr` / `pctl_pr` | REAL       | 世代内分位 + 赞藏比（`favs<10` 时 `pr`/`pctl_pr` NULL）                                       |
| 24     | `is_licensed`                                                        | INTEGER    | 正版日轻 47 本；为 1 时五列分位全 NULL，不进 A 类榜与统计                                           |

类型决定：枚举存 TEXT（INTEGER 码 gzip 后只省 0.49 MB，不值码表+JOIN）；
时间存 TEXT（字典序可直接比较，代价 12 B/本）；分位存连续 REAL（不预存六档，
档位端上派生）。

### 2.2 `book_tags` 与索引

```sql
CREATE TABLE book_tags(
  nid INTEGER NOT NULL,
  tag TEXT    NOT NULL,
  PRIMARY KEY(nid, tag)
);
-- 111,828 行 / 105 种标签 / 中位 4 个每本，184 本无标签
```

管道串 `LIKE '%战斗%'` 是子串匹配、无法等值命中；JOIN 走 `idx_bt` 精确匹配。
`tags` 列保留：列表页免 N+1、兜底回填，体积仅 +55 B/本。

| 索引                                                                                 | 体积    | 服务       | 加速         |
| ------------------------------------------------------------------------------------ | ------- | ---------- | ------------ |
| `idx_bt(tag, nid)`                                                                 | 2.12 MB | 标签筛选   | 22×（全库） |
| `idx_updated(updated_at)`                                                          | 0.84 MB | 断更榜     | 118×        |
| `idx_author(author)`                                                               | 0.64 MB | 作者查询   | 104×        |
| `idx_year_favpctl(est_year, fav_pctl DESC)`                                        | 0.59 MB | 世代收藏榜 | 98.6×       |
| `idx_year_clickpctl(est_year, click_pctl DESC)`                                    | 0.59 MB | 世代点击榜 | ≈100×      |
| `idx_genre_favs(genre, favs DESC)`                                                 | 0.52 MB | 题材榜     | 88.6×       |
| `idx_favs(favs DESC)`                                                              | 0.32 MB | 收藏榜     | 89.7×       |
| `idx_pr(pr DESC)`                                                                  | 0.46 MB | 赞藏比榜   | 800×        |
| `idx_shortfav(favs DESC) WHERE words<=50000 AND status='已完结' AND is_licensed=0` | 0.04 MB | 短篇榜     | 336×        |

索引决策：世代榜用复合索引（两个单列 0.96 MB 换一个复合 0.59 MB，且单列版反而慢）；
短篇榜必须部分索引（通用 `idx_favs` 扫 3 倍才凑够 50 条，15.1ms 比无索引还慢）；
标题不建索引（前缀通配符用不上 B-tree，只快 2.6×），走内存索引（§4）。
跨代查询（`est_year>=2024 ORDER BY ...`）会选错索引，**必须按代分别查询再合并**
（0.578ms → 0.047ms）。

### 2.3 `seed_meta`（key/value）

`schema_version` / `seed_version` / `content_end=2026-05-03` / `built_at` /
`book_count=30878` / `licensed_count=47` / `tag_count=105` / `tag_rows=111828` /
`base_count=29433` / `short_added=1398` / `stats_universe=241758` /
`gen_min=2007` / `gen_max=2025`。

不下发 `source_coverage` 单值：覆盖率 69.3% 是可访问上界（空洞混死亡/僵尸/存活，
且约 10% 库内书查不到分类目录）。UI 基于「本地已有 / 站上可发现 / 已下架」三态说明，
不用单一 coverage 数字（依据：`docs/sfacg-endpoints.md` §5.1、报告 10）。

### 2.4 清洗遗留（UI 口径）

| 问题                                        | 要求                               |
| ------------------------------------------- | ---------------------------------- |
| banner 书仅 71/667 有封面（错配清洗置空）   | 无封面用占位图，不暗示「书没有图」 |
| 封面年月 = 换图时间，与定年偏差中位 +338 天 | 不做时序推断                       |
| 5.0% 无标签 / 495 本 words=0                | 标签栏隐藏；字数显示「—」         |
| favs/praises 12.2%/13.5% 为 0               | 显示「0」，是真实值                |
| `status` 是 2026-05-03 快照               | 详情页标注快照时点                 |

## 3. user.db

```sql
-- 观测流水（只追加）：59 B/行（WITHOUT ROWID），10 万行 ≈5.8 MB
CREATE TABLE observations(
  nid INTEGER NOT NULL, observed_at INTEGER NOT NULL,   -- unix 秒
  clicks INTEGER, favs INTEGER, praises INTEGER, words INTEGER,
  short_comments INTEGER, long_comments INTEGER,        -- 仅 watchlist 书抓评论时写；一般读者 NULL
  status TEXT, updated_at TEXT,
  source TEXT NOT NULL DEFAULT 'detail',                -- detail | search | rank
  PRIMARY KEY(nid, observed_at)
);
CREATE INDEX idx_obs_time ON observations(observed_at DESC);
-- 保留 180 天，按月 DELETE 裁剪，不做 VACUUM

-- 最新书目元数据覆盖层：一次成功抓取返回的所有字段都写这里。
-- seed.books 只读；读取时用本表覆盖显示值，不回写种子。
CREATE TABLE book_meta(
  nid INTEGER PRIMARY KEY, source TEXT NOT NULL, fetched_at INTEGER NOT NULL,
  title TEXT, author TEXT, author_id INTEGER, genre TEXT, type_id INTEGER,
  price_type TEXT, status TEXT, cover_url TEXT, summary TEXT,
  words INTEGER, favs INTEGER, praises INTEGER, clicks INTEGER,
  updated_at TEXT, add_time TEXT, point REAL, bg_banner TEXT,
  category_id INTEGER, is_sensitive INTEGER, allow_down INTEGER,
  tickets INTEGER,  -- 当月月票（GetTicketNum.ashx，每月 1 日清零；NULL=未抓/失败）
  comic_id INTEGER, album_id INTEGER, comic_folder TEXT
  -- 衍生作品（/adpworks/novelId/{nid}，0=无；comic_folder 取自 /comics/{comic_id}.folderName）。
  -- 只作详情页「有改编」标注，不外链（官方漫画站定期关闭、有声无 Web 模板）；
  -- comic_folder 留档供官方恢复后复用。NULL=未抓/失败，与 0（确认无改编）严格区分
);
-- HTML 有简介/赞、无 clicks；App API 有 clicks/addTime/point、无简介/赞。
-- UPSERT 时本次缺失字段保留旧值，两通路可互补。UI 书目属性一律覆盖层优先、
-- seed.books 兜底——这是「本地数据不落后」的机制保证。

-- 封面直链缓存（兼容旧读路径，book_meta.cover_url 优先）
CREATE TABLE covers(nid INTEGER PRIMARY KEY, cover TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'app', fetched_at INTEGER NOT NULL);

-- 官方搜索命中、种子未收录
CREATE TABLE discovered(
  nid INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, genre TEXT,
  words INTEGER, favs INTEGER, praises INTEGER, cover_url TEXT, summary TEXT,
  source TEXT NOT NULL, observed_at INTEGER NOT NULL
);  -- 收录 ≠ 进入统计：无定年无分位，不参与榜单，UI 标「官方目录，无统计数据」

-- 书架与分组
CREATE TABLE shelf(nid INTEGER PRIMARY KEY, added_at INTEGER NOT NULL,
                   list_id INTEGER, note TEXT);   -- list_id=0 默认书架
CREATE TABLE shelf_lists(id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at INTEGER NOT NULL);

-- 标注摘抄 / 搜索历史 / 偏好 / 本机统计缓存
CREATE TABLE annotations(id INTEGER PRIMARY KEY, nid INTEGER NOT NULL, chapter TEXT,
                         body TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER);
CREATE INDEX idx_anno_nid ON annotations(nid, created_at DESC);
CREATE TABLE search_history(id INTEGER PRIMARY KEY, keyword TEXT NOT NULL,
                            at INTEGER NOT NULL, hits INTEGER);
CREATE TABLE prefs(key TEXT PRIMARY KEY, value TEXT);  -- 含作者端全勤阈值（key 'quanqin.*'，用户可改）
CREATE TABLE user_stats(nid INTEGER PRIMARY KEY, fav_delta_30d INTEGER,
                        click_delta_30d INTEGER,   -- 恒 NULL：跨书点击变化不做
                        obs_count INTEGER, first_seen INTEGER, last_seen INTEGER);

-- 观测列表（07 作者工作台）：shelf 是"想读"，watchlist 是"追踪数据"，语义不同
CREATE TABLE watchlist(
  nid INTEGER PRIMARY KEY,
  role TEXT NOT NULL DEFAULT 'self',      -- self 本人 | peer 同期对照（定年差>2年软警告）
  added_at INTEGER NOT NULL,
  poll_enabled INTEGER NOT NULL DEFAULT 1, poll_interval INTEGER NOT NULL DEFAULT 86400,  -- 最小 6h
  last_poll_at INTEGER, note TEXT
);
CREATE INDEX idx_watch_poll ON watchlist(poll_enabled, last_poll_at);

-- 章节快照（07 更新热力图主方案）：来自 App API /novels/{id}/chaps，可选增强，
-- 失效回退 observations.words 差分；仅 watchlist 书填充
CREATE TABLE novel_chapters(
  nid INTEGER NOT NULL, chap_id INTEGER NOT NULL,
  added_at TEXT, updated_at TEXT, char_count INTEGER,
  is_vip INTEGER, is_rubbish INTEGER, audit_status INTEGER, fetched_at INTEGER NOT NULL,
  PRIMARY KEY(nid, chap_id)
);
CREATE INDEX idx_chap_added ON novel_chapters(nid, added_at);

-- 每 nid 记一次出站详情尝试：请求前打点（失败也计入冷却窗口），
-- 事后回填三态供诊断；不参与 UI 展示
CREATE TABLE refresh_attempts(
  nid INTEGER PRIMARY KEY, attempted_at INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending'
);
```

跨库取较新值：

```sql
SELECT b.nid, b.title,
       COALESCE(o.favs, b.favs) AS favs,
       CASE WHEN o.observed_at IS NULL THEN 'seed' ELSE 'local' END AS src
FROM seed.books b
LEFT JOIN main.observations o ON o.nid = b.nid
     AND o.observed_at = (SELECT MAX(observed_at) FROM main.observations WHERE nid = b.nid)
WHERE b.nid = ?;
```

UI 必须区分 `src`（种子基线 vs 本地刷新时间）。`user_stats` 是缓存非真相，可从
`observations` 全量重算。涨幅/热度榜样本不足时**隐藏整个榜单，不做降级展示**（03 §4.7）。

## 4. 搜索内存索引

启动时读 30,878 条标题+作者（50,486 键）建内存索引：建索引 17.7ms、精确查 0.07µs
（SQL 的 11 万倍）、前缀扫描 3.89ms（v1 可接受；v2 有序数组+二分，待实测定）。
标题不走 SQL（`LIKE '%..%'` 8.99ms，`idx_title` 只快 2.6× 不值 1.20 MB）。不做 FTS5。

## 5. 种子构建流水线

```
novels.csv (245,887 行，已剔正版日轻；含 108 本 E.14 月榜遗漏补充)
  ① 定年（eras.estimate）→ ② 过滤 est_year∈[2007,2025] → 241,864 行
  ③ 分位：全库 × est_year（不在种子池内算）→ ④ pr / pctl_pr
  ⑤ 选种：favs Top20k ∪ 近1年上架 ∪ 近90天更新 ∪ 月榜归档 ∪ banner 全集
  ⑥ 补短篇双组分位 Top2000 → ⑦ 补回正版 47 本（is_licensed=1，分位 NULL）
  ⑧ 建表建索引 → ⑨ VACUUM + ANALYZE → seed.db.gz 随包
```

边界：近 1 年 = `est_date >= 2025-05-03`，近 90 天 = `updated_at >= 2026-02-02`
（差一天会少 37 本，构建器只认本文这套）。

构建规则（不可违背）：

1. **分位在全库算**（241,864 行参照系），种子池内重算会改分母、不可跨版本比较；
2. **定年构建期完成**，端上不插值；
3. **种子只增不减**，不为删书写迁移逻辑；
4. **正版日轻只进检索不进统计**（nid 复用旧条目、定年不可信；A 类榜必须带 `is_licensed=0`）。

构建期自校验：行数==book_count、nid 唯一、title 重名阻断并列出 nid 对（站内唯一，
重名必为改名/删书快照伪影，人工裁定保留行）、分位∈(0,1]、正版分位全 NULL、
抽样 20 本分位重算误差 <1e-6、`book_tags` 行数一致、索引清单比对、`integrity_check`、
体积阈值告警。

## 6. 版本策略

| 版本               | 影响                                                                    |
| ------------------ | ----------------------------------------------------------------------- |
| `schema_version` | user.db 迁移（事务内，失败回滚；迁移前备份 `.bak`；向前兼容一个版本） |
| `seed_version`   | seed.db 整文件替换，不迁移                                              |
| `content_end`    | UI 显示的数据时点                                                       |

已定结论：`contest`/`genre` 不建维度表；`discovered` 不预计算分位；历史月榜随种子携带
（165 月×4 榜，原始 1.9 MB）；短篇不建独立分类体系（IP 随时间迁移会过期，用现有 tags 表达）；
部分索引阈值（5 万字）变更时构建期重建索引。

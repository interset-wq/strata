-- ============================================================
-- Novly · SQLite Schema（基于 2026-06 全量快照实测）
--
-- 实测数据（246,045 本，cold 240,725 + warm 2,515 + hot 2,805）：
--   · 点击 < 1 万：约 20.2 万本（82%），中位点击 292~410
--   · 上游只有 5,320 本全指标精确（我们自己采后，19,791 本可全部精确）
--   · 种子包 = 榜位闭包 ∪ 标签闭包 ∪ banner 全集 = 19,856 本（见文件末尾）
--   · banner 仅 667 本（0.27%），cold 里为 0         ← 站方人工认证
--
-- ★ 核心原则一：数据可以继承，判定不继承。
--   上游 novel_hub 的**二次加工结论**（A 后缀、warm/cold 分组）一律不采用；
--   只取它的**原始事实字段**（括号里是它起错的名字，成因见 data-findings §14）：
--     nid / title / author / genre / cover
--     人气（它叫 click_num）/ 收藏（它叫 like_num）/ 赞（它叫 praise_num）
--     字数 / status / ptype / banner 位
--   banner 是站方的行为事实，不是第三方的判断，所以可以用。
--   字段能不能用，由**我们自己的采集能力**定义：逐本抓详情页 → 全指标真实。
--   status 只保留三值；成绩的来源与时间用 stats_src + stats_at 表达。
--
-- ★ 核心原则二：字段名跟随 API key，不自创英文名。
--   站方 API（api.sfacg.com）的 key 是它对同一份数据的命名：
--     viewTimes → view_num    markCount → mark_num    fav → fav_num
--   上游错在直译：看到页面写「收藏」，选了 like（Facebook 语境里 like = 点赞），
--   于是 like_num 实际是收藏、praise_num 才是赞——**语义正好反了**。
--   危害：ORDER BY like_num 的人以为在排「点赞最多的书」，实际排的是收藏榜。
--
-- ★ 核心原则三：字段语义必须被验证，不能靠字段名推断。
--   ① 每个字段入库前做三方对账（上游库 / API / 页面文本），至少两方数值吻合；
--   ② 采集器禁止位置解包——上游写 btns[-2:]，站方加了「分享/举报」两个按钮后
--      它取到的是空字符串，int('') 直接崩，而崩溃前数据已静默错位；
--   ③ 精度必须显式：从「万」还原的整数只精确到千位（108392000 实际是 10839.2万），
--      必须标 stats_src='upstream'。**INTEGER 类型不等于精确值。**
--
-- 字段取舍全部依据实测覆盖率，见每张表的注释。
-- ============================================================

-- ============================================================
-- ★★★ 双库划分（2026-11-15 新增）：种子可替换，用户数据不可替换
--
--   问题：种子要能整包更新，而用户改的数据不能跟着丢。
--   做法：两个文件，替换时物理隔离，零合并逻辑。
--
--   ┌ seed.db  （可整包替换；APK 内置 gzip → 首启解压到应用私有目录）
--   │   catalog / banners / tags / book_tags / tag_stats / tag_combos
--   │   rank_lists / rank_snapshots / meta
--   │   nid_epoch（85 行锚点）/ era_stats（16 行年份统计）  ← 都是「时间」的基础设施
--   └ user.db  （**永不替换**；只有用户清数据才会消失）
--       details / shelf / search_log / search_miss / user_patch / local_meta
--
--   ★ 关键：seed.db 虽然叫"种子"，但它是**可写**的。
--     用户打开详情页、搜到未收录的书，都要写进 catalog——否则体验断裂
--     （看完一本刷新了，下次打开又变回旧数字；搜到的书第二次搜还是"没收录"）。
--
--   ★ 但直接写 catalog 的内容扛不住种子替换。所以配一张 user_patch：
--     **日志是 source of truth，catalog 是可重建的物化结果。**
--     写入必须按这个顺序（先日志后物化）：
--       ① 事务写 user.db 的 user_patch（payload + src + observed_at + base_seed）
--       ② 再 UPDATE seed.db 的 catalog（失败无所谓，下次启动从日志重放）
--
--   ★ 种子替换后的重放（唯一需要跨库的地方，启动时一次）：
--       applied=0 的行逐条处理：
--         observed_at <= 新种子 snapshot_at → 观测已过时，applied=1 跳过
--         否则                               → 应用到 catalog，applied=1
--
--   ★ 查询侧零成本：不需要视图、不需要 ATTACH 跨库 JOIN。
--     catalog 已经是合并后的物化结果，索引全部有效，
--     代价只是"重放"（行数 = 用户真正碰过的书，通常几百行，< 20ms）。
--
--   ★ 用户写入**不影响榜单**：rank_snapshots 是构建期快照，本地不重算。
--     否则用户看一次详情页就能把榜位顶动，榜就不可解释了。
--
--   ★★★ 分期（2026-11-15 定）：**这个结构 v1 就完整落地，与有没有后端无关。**
--     P0 bootstrap / P1 自产（v1）：纯静态，没有任何服务端。种子从 GitHub Release 拉，
--         user_patch.synced_at 恒为 NULL（语义是"有日志、未上报"），上报模块不存在。
--     P2 回流：才加 FastAPI 收观测。**表结构一行不改**，只多一个上报模块。
--     → 结论：「用户可写」是第一版的能力，不是后端的能力。
--       后端只决定"观测会不会离开这台设备"，不决定"数据能不能更新"。
--
--   下面的单文件版本可直接 executescript（开发/测试/总览用）；
--   生产按上面的划分拆成 seed.sql / user.sql 两个库，表定义完全一致。
--   两张 meta 不冲突（在不同库里）：meta 属 seed.db，local_meta 属 user.db。
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 元信息（seed.db）
-- ------------------------------------------------------------
CREATE TABLE meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
-- schema_version / seed_version / seed_built_at / seed_book_count / seed_built_from
-- seed_snapshot_at（★ 重放判定的基准：用户观测比它旧就算过时）
-- seed_format_version（★ 载荷格式版本，与 App 版本解耦：种子走 Release 独立更新，
--   旧 App 读到高于自己认知的 format 必须**安全忽略**而不是崩在 no such column）
-- crawl_enabled / crawl_min_interval_ms / detail_ttl_days
--   （★ 零后端的配置下发：种子是唯一能不经发版到达客户端的外来数据，
--     所以应急降级参数放在这里。生效延迟 = 种子更新周期，急事走 Release 里的 flags.json）
-- last_sync_at / sync_cursor（采集进度，非分片游标——我们是单库，没有分片）

-- ------------------------------------------------------------
-- nid → 上架日 的锚点表（★ 85 行，把「时间」变成免费字段）
--
-- 上游库没有 add_time，只有 last_update。但 **SFACG 的 nid 单调递增**：
-- 建站至今没有复用、没有分片、没有回填过号段。实测 85 个跨全库锚点
-- （nid 2,242 → 761,712，覆盖 2006-08 到 2025-10），**0 次逆序**。
--
-- 中间段精度：分段线性插值，nid=121065 估 2018-01-29 / 真 2018-02-02（差 4 天）。
-- 端点和稀疏段要小心：2006–2011 只有 7 个锚点，插值误差可达数月，
-- 所以构建器**必须**覆盖首尾（nid 最小的几本用 API 真值作锚，不能外推）。
--
-- ★ 为什么值得单列一张表（85 行、~3 KB）：
--   24.6 万本全部拿到 add_time，**零 API 请求**。这解锁了「年代轴」——
--   我们的定位是「过去什么好」，而之前整个设计里没有任何一条时间维度。
--   （banner 的时代论、年代榜、书龄筛选，全部依赖这一个字段。）
--
-- ★ 维护：采集时遇到新书就顺手 append 一条锚点（新 nid 的 addTime），
--   表随采集自然加密，不需要专门的维护任务。锚点永远只增不改。
-- ------------------------------------------------------------
CREATE TABLE nid_epoch (
  nid INTEGER PRIMARY KEY,      -- 锚点书的官方 nid
  day INTEGER NOT NULL          -- 该 nid 的 addTime（unix 天）
);
-- 查询用：取 <= :nid 的最近锚点 + 下一个锚点，线性插值。
-- SELECT nid, day FROM nid_epoch WHERE nid <= :nid ORDER BY nid DESC LIMIT 1;
-- SELECT nid, day FROM nid_epoch WHERE nid >  :nid ORDER BY nid ASC  LIMIT 1;

-- ============================================================
-- 目录（端上种子 19,791 行 / 云端全量 246k 行，schema 相同）—— 【seed.db 但可写】
--
-- 实测结论：24.6 万本里只有约 1.5 万本"活着"，其余 96% 是墓碑。
--
-- ★ 本版修正：端上**不再存全量**。降序榜没人会滑到第 2000 名
--   （见 data-findings.md §11：2000 名后 45% 并列，15 万名后 99.4% 并列），
--   所以内置的是「榜位闭包 ∪ 标签闭包 ∪ banner 全集」19,856 本，不是 24 万行。
--   搜索改用 Dart 内存索引（前缀 + 子串 + 拼音首字母），**不用 FTS5**：
--   2 万条太小，trigram 索引比数据本身还大，且中文两字词 MATCH 会失效。
--
-- ★★★ 这张表是**可写的**（用户侧两条写入路径）：
--   ① 详情页回填：用户点开一本，API 一次带回全指标 → 更新这行（stats_src='own'）
--   ② 搜索自动收录：搜到种子之外的书 → 补一行（stats_src='own'，见 §user_patch）
--   两条都必须**先写 user_patch 日志、再写这张表**，否则种子替换后会丢。
--   写入只改展示值，**不改 rank_snapshots**（榜位是构建期快照，本地不重算）。
-- ★ 自动收录的书没有榜位、可能没有 tag_stats 行：
--   UI 必须能显示「有书、无排名」，不能因为查不到名次就整条丢掉。
-- ============================================================
CREATE TABLE catalog (
  -- ★ 沿用官方 nid（全局唯一）。上游合并 novels 用 INSERT OR REPLACE ... SELECT *，
  --   不做任何 id 重映射，所以 books.id 可以跨片信任 —— 与 tags.id 正好相反。
  --   （tags.id 跨片同 id 率实测 0%，见 schema 里 tags 表上方注释）
  id           INTEGER PRIMARY KEY,
  title        TEXT    NOT NULL,
  author       TEXT    NOT NULL,   -- 平台禁止改名与重名：同名即同人，可直接作身份键。
                                   -- 多数作者只有一本书，不单独建 authors 表
  genre        INTEGER NOT NULL,   -- 1其他 2魔幻 3玄幻 4古风 5科幻 6校园 7都市 8游戏 9同人 10悬疑

  -- ★ 真实状态，三值。原库的 5/6 已被拆解，不再作为状态层存在。
  status       TEXT    NOT NULL CHECK (status IN ('连载中','完结','断更')),

  -- ★ 成绩的来源与时间。不问「上游怎么分类」，只问「这数字谁给的、什么时候给的」。
  --
  --   stats_src 是**审计字段，不是查询谓词**：
  --     判断一个数能不能用，看该字段自己是不是 NULL，别看来源。
  --     （mark_num IS NULL → 不可用；mark_num 有值 → 可用。）
  --     来源只用于统计「还剩多少本依赖第三方」。
  --
  --   'own'      = 我们自己的爬虫采的：走 App API，view/mark/fav/ticket/point 全部精确
  --   'upstream' = bootstrap 阶段继承的第三方批量数据：只有 view_num 勉强可用
  --                （且是「4757.4万」这种 5 位有效数字的近似值），
  --                mark/fav/ticket 一律置 NULL（cold 段卡在 9,999、
  --                549 条 mark>view 全是 view≤100 的僵尸书、1,401 条 view=0 但 mark>0）。
  --   终局是全部 'own'：
  --     SELECT stats_src, COUNT(*) FROM catalog GROUP BY 1
  --   就是「摆脱第三方」的进度条。
  stats_src    TEXT    NOT NULL DEFAULT 'own' CHECK (stats_src IN ('own','upstream')),

  -- ★ ptype 不是「价格档位」，而是编辑筛选漏斗的层级 —— 它本身就是一个质量信号。
  --   2 免费  = 没被编辑看中（91.92%，226,158 本）
  --   3 签约  = 过了第一道筛，转化率仅 5.72%（12,933 本）
  --   4 VIP   = 过了第二道筛，转化率 53.8%（6,954 本）
  --   第一道筛极窄、第二道很宽 → 「能不能签约」是生死线。
  --   榜单排序时必须按 ptype 分层：三者中位点击差 100 倍（292 / 2.4 万 / 44 万）。
  ptype        INTEGER NOT NULL CHECK (ptype IN (2,3,4)),

  -- ★ 站方行为事实（不是第三方的二次判断，所以可以采用）：全站仅 667 本（0.27%）有 banner。
  --   其中 10 本点击 < 10 万，全是正版引进日轻（文豪野犬点击仅 475 却挂 banner）。
  --   663/667 是 VIP（ptype=4）→ 它本质是站方对「可售商品」的运营位，不是质量评价。
  --   但它同时是「人的编辑判断」的化石，独立成一等维度。
  --   ★ 边界：只用于「官方精选」入口的收录条件，**不参与质量分加权**。
  --   ★ 与 banners 表的关系（data-findings §17.8）：
  --     本列 = 「站方是否授予过」——历史事实，bootstrap 就有，一次 true 永久 true；
  --     banners.active = 「那张图现在还能不能下」。
  --     两者回答不同问题，不是冗余，但会漂 → 构建器必须断言
  --     COUNT(is_banner=1) == COUNT(banners)，不等直接失败。
  is_banner    INTEGER NOT NULL DEFAULT 0,

  word_num     INTEGER,            -- 字数（API: charCount）。实测 496 本为 0，落库置 NULL

  -- ★★ 三个计数的**官方名字**和我们的旧叫法不同，命名一律对齐 API，避免实现时误解：
  --   网页/接口上的「人气」＝ viewTimes ＝ view_num（不是「点击」）
  --   网页上的「收藏」＝ markCount＝ mark_num
  --   网页上的「赞」  ＝ fav      ＝ fav_num
  --   ※ 2026-11-15 实测 book.sfacg.com/Novel/42229/ 页面原文：
  --     「人气：10903.2万 | 点击阅读 | 赞 111265 | 收藏 196096」
  view_num     INTEGER,            -- 人气。★ 网页只显示「10903.2万」（5 位有效数字），
                                   --   但 API 返回 viewTimes 精确到个位 —— 我们存 API 值，
                                   --   所以「并列名次」不再来自精度，而是真实同分。
                                   --   ※ 上游值（108392000）是「万」还原的，只精确到千位。
  mark_num     INTEGER,            -- 收藏。★ 这是「加书架」的人数，门槛最低、最好刷。
                                   --   上游 cold 段在 9,999 被压平（见下方按行判断规则）
  fav_num      INTEGER,            -- 赞。★ 这是唯一直接喂榜单的计数（见下），刷它有明确收益
  ticket_num   INTEGER,            -- 月票（API: expand.ticket，另有 ticketForWeek/Month）
                                   --   ★ 稀缺且付费：全站 top20 是 3148→226 票，
                                   --     而人气是同量级千万 —— 稀缺才值得刷，才需要防。
  point        REAL,               -- 官方评分 0~10（API: point）。★ 要「看过+登录」才能评，
                                   --   门槛比赞高一个数量级，是唯一相对抗刷的质量信号。
  chapter_num  INTEGER,            -- 章节数（API: expand.chapterCount）
  -- ★★ 上架日（unix 天）。「考古」入口要按书龄筛；也是 banner 时代论的唯一锚点。
  --    与 last_update 的区别：这个是「出生」，那个是「活动」。
  --
  --    ★ 关键：上游库**没有这个字段**（只有 last_update），API 有 addTime。
  --      但我们不需要为 24.6 万本逐个请求 —— **nid 本身就是一条时间轴**：
  --      实测 85 个跨全库锚点，nid 与 addTime 严格单调（0 次逆序），
  --      分段线性插值在中间段误差约 4 天（nid=121065 估 2018-01-29 / 真 2018-02-02）。
  --      → bootstrap 阶段用 nid_epoch 表插值填充，自采后由 API 真值覆盖。
  --
  --    ★ add_time_src 标记这个值的来源，不要把估算值当真值用：
  --      'api'  = API 直接返回（精确到日）
  --      'nid'  = 由 nid 插值估算（±1 周，够做「年代」分桶，不够做「同日」判断）
  add_time     INTEGER,
  add_time_src TEXT CHECK (add_time_src IN ('api','nid')),

  -- ★ 下面所有计数为 NULL 都表示「不知道」，不是「0」——排序必须排除，不能当 0。
  --   bootstrap 阶段继承的第三方数据，**按行判断，不搞一刀切**（实测 2026-11-15）：
  --
  --     · 来自 warm/hot 的行 —— 榜位闭包里 4,073 本（35.6%）：
  --       mark/fav 是精确快照（42229 与 API 差 0.5%），**可以进收藏/点赞榜**，
  --       只是整份数据已过期约 5 个月（快照日 2026-06-13）。
  --     · 来自 cold 的行 —— 7,369 本（64.4%）：
  --       mark 在 9,999 **被压平**（cold 里 >9999 的记录数 = 0）。这不是假值，
  --       是「超过 9999 一律记 9999」，后果是收藏榜前 N 名会全是并列——
  --       而收藏过万的书恰恰是我们要推荐的。这类行的 mark/fav 必须 NULL。
  --       （cold 的 mark 中位只有 1,083，所以不是全坏，是「好书全被抹平」。）
  --     · view_num 无论哪个分片都只有 5 位有效数字（108392000 实为 10839.2万，
  --       精度只到千位）。**INTEGER 类型不等于精确值**，见 data-findings §14.3。
  --   549 条 mark>view 全是 view≤100 的僵尸书、1,401 条 view=0 但 mark>0，
  --   都不在榜位闭包内，不构成影响。
  contest      TEXT,               -- 征文活动名（实测 38% 有值、97 个赛事）
                                   -- 赛事作品=被编辑筛过，对发现老书有正价值，保留
  cover        TEXT,               -- 完整 URL（形如 <前缀>2024/11/7bd0f5b3-...jpg，无法由 id 推导）
                                   -- ★ 不要只存后缀：实测只省 20 KB，因为 gzip 早已把
                                   --   54 字符公共前缀压掉了。不值得为它加一层拼接逻辑。
  last_update  INTEGER,            -- unix 天（原为 DATETIME 字符串，含时区）

  -- ★ 不做「综合质量分」。理由：
  --   任何加权都等于替用户决定「点击和收藏哪个更重要」，而这个答案因人而异；
  --   一旦存在一个神奇数字，就一定会有人拿它排序，然后没人能解释第 7 名为什么是第 7 名。
  --   我们的做法：每个榜只有一个排序键（单维度），判断权交回用户。
  --   组合场景用**明确规则**表达（「完结 + 字数≥100万 + 点击≥10万」），不用加权分。

  -- 成绩采集时间（unix 天）。兼作增量采集游标：
  --   ORDER BY stats_at ASC 取最旧的先重采，就是「谁该更新」的队列。
  stats_at     INTEGER
);

-- 实测：comment_num / review_num 有 86% 为 NULL → 直接删除
-- 实测：authors 表 136,499 行几乎一书一作者 → 删除整张表

CREATE INDEX idx_catalog_view   ON catalog(view_num DESC);
CREATE INDEX idx_catalog_ptype  ON catalog(ptype, view_num DESC);
CREATE INDEX idx_catalog_genre  ON catalog(genre, status, ptype);
CREATE INDEX idx_catalog_banner ON catalog(is_banner, view_num DESC) WHERE is_banner = 1;
CREATE INDEX idx_catalog_own    ON catalog(stats_src, view_num DESC);
CREATE INDEX idx_catalog_ticket ON catalog(ticket_num DESC) WHERE ticket_num > 0;
CREATE INDEX idx_catalog_point  ON catalog(point DESC) WHERE point IS NOT NULL;
CREATE INDEX idx_catalog_stale  ON catalog(stats_at ASC);   -- 增量采集：谁最该重采
CREATE INDEX idx_catalog_author ON catalog(author);
-- 年代轴（2016 年的 top 100）。add_time 是 nid 插值估算的，按年分桶够用；
-- 这是「过去什么好」这个定位唯一的显式时间入口，值得一条索引。
CREATE INDEX idx_catalog_addtime ON catalog(add_time) WHERE add_time IS NOT NULL;

-- ------------------------------------------------------------
-- 首页横幅（banners）—— 【seed.db】★ 图资产，不是书的属性
--
-- 为什么单独一张表（data-findings §17）：catalog 装不下三样东西——
--   ① 独立的图片资产：750×430 横版宣传图，与竖版封面（NovelCover/Big）是两张完全不同的图
--   ② 会被原地替换：站方换图时**覆盖同一路径**，只有 ETag / Last-Modified 变
--   ③ 有自己的可用性：667 张里已有 1 张 404，未来只会更多
--
-- 实测（667 张全量探测，2026-11-15）：
--   URL   https://rss.sfacg.com/web/novel/images/images/beitouNew/cut/{nid}.jpg
--         ★ 可按 nid 构造 → bootstrap 不需要为 banner 抓 667 次 API
--         ★ 签名参数非时效（两次请求完全相同），去掉也能下 → 端上可直连，不需要中转
--   尺寸 750 × 430（1.744:1），抽样 6 张全部一致
--   格式 656 JPEG + 5 PNG + 1 404 —— ★ 5 张 PNG 的文件名也叫 .jpg，**扩展名撒谎**
--   体积 JPEG 93~192 KB（均 140）/ PNG 286~504 KB（均 414，是 JPEG 的 3 倍）
--   可用 666/667（99.85%），含 2013 年的书 → 图几乎永久可用
--
-- ★ 不做的事（都因为拿不到，不假装拿到）：
--   slot（首页/分类/专题）—— 只有一个 bgBanner 字段，没有位置信息
--   start_at / end_at     —— Last-Modified 是批量上传时间（16/23 集中在 2022-01-21
--                            03:33~03:34 一分钟内传完，那是站方批量重建，不是上架）
--   多次上架历史          —— 同路径覆盖，旧图已被销毁，观测不到
--   → 所以一行 = 一本书（book_id 主键），这是唯一诚实的粒度。
--
-- ★ 与 catalog.is_banner 的关系：本表存在性 == is_banner=1（实测 667 双向一致），
--   但语义不同（见 catalog 该列注释）；构建器必须断言两数相等，不等则失败。
-- ------------------------------------------------------------
CREATE TABLE banners (
  book_id       INTEGER PRIMARY KEY,        -- → catalog.id（一本书一张图）
  -- 完整 URL。规则稳定但**必须存下来**：旧路径 beitou/ 已经 404（站方改过一次命名
  -- → beitouNew/），构造式不能当契约。
  image_url     TEXT    NOT NULL,
  width         INTEGER NOT NULL DEFAULT 750,
  height        INTEGER NOT NULL DEFAULT 430,
  -- ★ 格式必须存，不能靠扩展名判断：5/667 实际是 PNG 却叫 .jpg
  format        TEXT    CHECK (format IN ('jpeg','png')),
  -- 实际字节数。★ 按扩展名估算会低估 3 倍（PNG 平均 414 KB vs JPEG 140 KB）
  bytes         INTEGER,
  -- ★★ 缓存 key：URL 永不变、内容会变（站方原地覆盖同一文件）。
  --    端上若用 URL 做图片缓存 key，会**永远显示旧图，且没有任何报错**。
  etag          TEXT,
  -- Last-Modified。★ 禁止用于排序——它记录的是批量上传时刻，不是 banner 上架时刻
  image_mtime   INTEGER,
  first_seen_at INTEGER NOT NULL,           -- 第一次采集到（unix 天）
  -- 上次校验可用性。校验必须 Range GET 前 512 字节 + 查 magic bytes：
  --   该 CDN 对不存在的路径会返回 200 HEAD（假的 Content-Length），HEAD 不可信
  checked_at    INTEGER NOT NULL,
  active        INTEGER NOT NULL DEFAULT 1
                  CHECK (active IN (0,1)),  -- 0 = 图已 404（书还在，只是图没了）

  -- ★★ 时代坐标（两张：绝对定位 + 相对定位）
  --
  -- add_year：上架年（由 catalog.add_time 派生，构建期算）。banner 是**当期认可**，
  --   不是后来追认 —— 实测 667 本里 432 本（64.8%）集中在上架于 2015–2019 的书，
  --   而那五年只占全库 25.1% → banner 密度是其他年份的 2.6 倍。
  --   （唯一例外是正版引进的日轻，见下）
  add_year  INTEGER,
  --
  -- era_pct：**当年**全库人气分位（0–100，构建期算）。
  --   ★ 这是唯一可跨年比较的成绩指标，因为 view_num 的绝对值混了两件事：
  --     ① 当年用户规模（2016 年 banner 书人气中位 206 万，2022 年是 1,132 万）
  --     ② 累计时间（2016 年上架的书已经攒了 10 年，2024 年的只攒了 2 年）
  --   实测 banner 书的 era_pct 中位在各年都稳定在 98.5–99.97%，
  --   说明「banner ≈ 当年 top 1–2%」这条规则长期没变；变的是授予**数量**。
  --
  --   ★ 副作用（刻意接受）：正版引进的日轻会沉到底部 ——
  --     文豪野犬 475 人气、天魔黑兔 3,532、电波女与青春男 5,170，
  --     实测 30 本点击 < 50 万，全是角川系引进（2023-08-03 一天上了 4 本）。
  --     它们的 banner 是**版号/版权方要求**，不是成绩认可。
  --     我们**不设 origin 字段去人工分类**，只让 era_pct 说话：
  --     轮播要求 era_pct >= 20，这 30 本自然被挡在外面；「官方精选」全量展示并按 era_pct 排序。
  era_pct   REAL    CHECK (era_pct IS NULL OR (era_pct >= 0 AND era_pct <= 100))
);
-- → 「官方精选」入口 = FROM banners（667 行）；「首页轮播」= WHERE active = 1
-- → 轮播排序见下方查询 13：**按年分层**，不是全库按人气加权。
--   原因：view_num 的绝对值混了「当年用户规模」和「累计时间」两件事，
--   直接加权会让轮播永远被 2015–2019 的老书占满（data-findings §18.5）。
--   ★ 不要按 image_mtime 排「最新」——那会排出 2022-01-21 那批批量重建的残影。

-- ------------------------------------------------------------
-- 年份统计（★ 16 行，把「时代背景」变成可展示的数据）—— 【seed.db】
--
-- 这张表回答的是「那一年的 SFACG 是什么光景」，而不是「那一年哪本好」。
-- 它是 banner 时代论的量化底座，也是年代榜的语境来源。
--
-- ★ books 是**全库**统计（24.6 万），不是种子闭包 2 万
--   —— 所以必须在构建期算好存进来，端上算不出来（端上只有闭包）。
--
-- 实测（2026-11-15，nid 插值 + 上游快照）：
--   year  books  banners  p99_view   banner中位人气
--   2015   3257     80    2,783,000     1,720,000   ← banner 功能 2015-09 上线
--   2016   4830     89    2,160,000     2,062,000
--   2017  12734     92    1,448,000     4,478,500
--   2018  16500     80    1,907,000     9,008,000
--   2019  24347     91    2,725,000    11,383,000   ← banner 绝对数高峰
--   2020  30356     53    2,336,000    12,299,000   ← banner 中位人气峰值
--   2021  35161     52    1,742,000     9,374,000   ← 新书数峰值
--   2022  37093     40    1,617,000    11,326,500
--   2023  27187     32    1,352,000     8,066,500
--   2024  18856     11    1,196,000     7,639,000   ← 授予量崩塌
--   2025  18676      7      754,066     3,379,000
--
-- 读法：p99_view 是「当年 top 1% 的门槛」，也就是**竞争强度**。
--   它从 2019 的 273 万降到 2025 的 75 万（3.6 倍），这是「用户盘子缩小」
--   唯一能量化的证据；而 banner 授予数从 91 → 7（13 倍），是「站方投入萎缩」的证据。
--   两件事叠加，才能说清「不同年份的 banner 不可直接比较」。
-- ------------------------------------------------------------
CREATE TABLE era_stats (
  year        INTEGER PRIMARY KEY,  -- 上架年（由 nid_epoch 插值分桶）
  books       INTEGER NOT NULL,     -- 当年上架本数（全库）
  banners     INTEGER NOT NULL,     -- 当年获得 banner 的本数
  -- 当年新书人气 P99：竞争强度。★ 这是「含金量」的可比分母
  p99_view    INTEGER,
  median_view INTEGER,              -- 当年新书中位人气（含大量 0，只作参考）
  median_word INTEGER,              -- 当年新书中位字数
  banner_median_view INTEGER,       -- 当年 banner 书中位人气
  banner_median_word INTEGER,       -- 当年 banner 书中位字数
  -- 授予率 = banners/books，构建期算，端上直接读（避免每次除法 + 浮点差异）
  grant_rate  REAL
);

-- ------------------------------------------------------------
-- 详情（按需抓取，只有用户点开过的书才有行）—— 【user.db】
-- 原 DB 完全没有简介字段，这是找书最关键的信息，只能靠 localhost 现抓
-- ★ 搜索接口能一次性补 29 本的 intro / point / type_name
--   所以这张表不只服务详情页，也服务「搜索即采集」（见 search.md §4）
-- ★ 放 user.db 而不是 seed.db：它是**纯缓存**，丢了可以重抓，
--   没有任何"种子"语义。种子替换时不该动它（也就不用重放）。
-- ★ 抓到指标时同时写 user_patch（见下）——details 存"文本与结构"，
--   user_patch 存"成绩观测"，两者职责不同：前者可丢可重抓，后者丢了就是数据损失。
-- ------------------------------------------------------------
CREATE TABLE details (
  book_id        INTEGER PRIMARY KEY,
  intro          TEXT,
  -- ★ 原先这里有 banner_url，2026-11-15 删除：banner 已独立成 seed.db 的 banners 表
  --   （它有 etag/体积/可用性，详情缓存表装不下）。两份 URL 必然漂，只留一份。
  --   若自动收录的书真的有 banner，就同时往 seed.db 的 banners 插一行（该库可写）。
  chapter_count  INTEGER,
  latest_chapter TEXT,
  type_name      TEXT,        -- 官方中文分类（科幻/魔幻/都市/玄幻…）
  point          REAL,        -- 官方评分 0–10，原库没有这个字段
  last_update    INTEGER,     -- unix 天，用于判断完结/断更
  source         TEXT,        -- 'search' / 'detail_page'，标记数据来路
  fetched_at     INTEGER NOT NULL,
  etag           TEXT,
  fetch_status   INTEGER NOT NULL DEFAULT 0   -- 0待抓 1成功 2失败 3已下架
);

-- ------------------------------------------------------------
-- 搜索日志与「待收录队列」—— 【user.db】
-- ★ 2026-11-15 语义变更：搜到未收录的书**当场自动收录**（写 catalog + user_patch），
--   不再只是"记下来等下次种子包"。所以 search_miss 的角色变成**失败重试队列**：
--   自动收录失败（网络断 / 解析异常 / 已下架）才落这里，下次启动重试。
-- 它依然是「唯一由真实用户需求驱动的收录信号」——只是从"候选清单"变成"待办清单"。
-- ------------------------------------------------------------
CREATE TABLE search_log (
  keyword     TEXT    NOT NULL,
  hits_local  INTEGER NOT NULL,
  hits_remote INTEGER NOT NULL,
  searched_at INTEGER NOT NULL
);

CREATE INDEX idx_search_log_time ON search_log(searched_at DESC);
-- ★ search_log **绝不上传**（隐私）。它只留在设备上，用于本地热词与排序权重。

CREATE TABLE search_miss (
  book_id    INTEGER PRIMARY KEY,
  title      TEXT,
  author     TEXT,
  type_name  TEXT,
  point      REAL,
  keyword    TEXT,
  first_seen INTEGER NOT NULL,
  retry_cnt  INTEGER NOT NULL DEFAULT 0,   -- 重试次数；>=3 视为长期失败，不再自动重试
  last_try   INTEGER
);

-- ------------------------------------------------------------
-- 用户观测日志（user_patch）—— 【user.db】★ 这张表是整个写入链的 source of truth
--
-- 为什么需要它：seed.db 会被整包替换，任何直接写进 catalog 的东西都会丢。
-- 所以每次用户侧写入都**先落一条日志**，catalog 只是它的物化结果。
--
-- 写入顺序（不可颠倒）：
--   ① BEGIN → INSERT/UPDATE user_patch → COMMIT
--   ② UPDATE seed.catalog（失败无所谓，下次启动重放）
--
-- 种子替换后的重放（启动时一次）：
--   SELECT ... WHERE applied=0
--     observed_at <= meta.seed_snapshot_at → 观测比新种子旧，作废，applied=1
--     否则                                  → 写 catalog，applied=1
--
-- 一行 = 一本书的**最新一次观测**（不是变更流水）。理由：
-- 详情 API 一次返回全指标，多行没有意义；旧观测只会让重放更慢。
-- 需要"这本书被看过几次"这种统计，另记 in local_meta 的计数器即可。
-- ------------------------------------------------------------
CREATE TABLE user_patch (
  book_id     INTEGER PRIMARY KEY,          -- 官方 nid（可能不在 seed 闭包里）
  payload     TEXT    NOT NULL,             -- JSON，只含本轮有值的字段，见下方示例
  src         TEXT    NOT NULL
                CHECK (src IN ('detail',   -- 详情页回填
                               'search')), -- 搜索自动收录
  observed_at INTEGER NOT NULL,             -- 观测时间（unix 秒），重放判定的依据
  base_seed   INTEGER NOT NULL,             -- 写入时所在的种子版本（便于排查）
  applied     INTEGER NOT NULL DEFAULT 0,   -- 0=待重放 1=已物化到 catalog
  -- ★ v1（无后端）这一列**恒为 NULL**，这是正确的语义（"有日志、未上报"），不是缺陷。
  --   P2 加一个上报模块即可直接接手，无需任何数据迁移。
  --   补报时不必全报：observed_at 早于 30 天的只证明"这书存在"，不上报数值
  --   （半年前的人气写进聚合表就是污染）。见 architecture.md §6.5。
  synced_at   INTEGER,                      -- 上报后端的时间；NULL=待上报（v1 恒 NULL）
  sync_batch  TEXT                          -- 批次 id，重试去重
);

-- payload 示例（一套完整的成绩观测；缺的字段不写，不写 null 占位）
-- {"view_num":1053211,"mark_num":196097,"fav_num":111265,"ticket_num":3148,
--  "point":9.6,"word_num":1408126,"chapter_num":412,"last_update":20613,
--  "stats_at":1763200000}

-- 重放只扫未物化的（部分索引，通常 0 行）
CREATE INDEX idx_patch_replay ON user_patch(observed_at)
  WHERE applied = 0;
-- 上报只扫未同步的（部分索引）
CREATE INDEX idx_patch_sync ON user_patch(observed_at)
  WHERE synced_at IS NULL;

-- ★ 上报边界（详见 docs/cloud.md）：
--   只报 payload（公开可爬的书籍元数据）+ observed_at + 匿名 client_id。
--   **不报** shelf / search_log / 任何设备标识。用户的阅读偏好不是数据资产。
-- ★ 后端聚合策略：同一本书多用户上报 → 每字段取「最新 observed_at」的值，
--   若同一时间窗内差异 > 20% 则取中位数（抗单点脏数据）。

-- ------------------------------------------------------------
-- 标签（2026-06 快照时 106 个 / 742,546 条关系）
-- ★ 这个数会变：官方每年新增（2025萌神 sysTagId=779，上游库里就没有）。
--
-- ★★★ 对齐键只有一个：`name`。上游自己的建表就是这样（data-findings §16.1）：
--     CREATE TABLE tags (id INTEGER PRIMARY KEY AUTOINCREMENT,
--                        name TEXT NOT NULL UNIQUE);
--     冲突判定走 name，id 是代理键。
--
-- ★ 上游 tags.id 不是「片内序号」，是**废号**（data-findings §16.2）：
--     cold 只有 99 行，id 最大 710,395（91 处跳号）；三片 81 个共有 name，
--     同 id 率 = 0%（「橘味」cold=32064 / warm=419 / hot=106）。
--     成因是历史反复重建，AUTOINCREMENT 水位残留。
--   → 处置不是「重映射」，是**当它不存在**。任何按上游 id 对齐的代码都是错的。
--
-- ★ name 唯一 ≠ 语义唯一（data-findings §16.4）：
--     「末世」8,813 本 与 「末日」465 本 **交集为 0**，而「末日」2026-04 还在用。
--     站方不做语义去重，两批作者各打各的词。
--   → 绝不能因为语义相近就合并两个 name；那会把不相关的书虚增进去。
--   → 也不需要任何映射表：同名近义就是两个标签，各自独立、各自参与排序。
--
-- ★ 站方「改名」不是改名，是**新建词条 + 旧词下线**（data-findings §16.3）：
--     「橘味」sysTagId=680，落在 2022(616)~2023(694) 号段 → 是新开的，不是继承。
--     而老书的关系**不回写**：标题含「百合」的 303 本里，只有 1 本带「橘味」。
--   → 所以不存在「同义词迁移」，只存在「两个割裂的快照」。
--     我们也不去桥接它们：搜「百合」就是书名含百合的那 303 本，
--     想找橘味那批就点「橘味」——两个词各自成立，都是真话。
--
-- 标签与 genre 正交：任一标签都横跨全部 9 个 genre，
-- 所以它是独立的发现维度，不是分类的子属性。
--
-- ★ 但它是**偏向新书**的维度（data-findings §16.6）：平均标签数
--     2010–2014 = 0.53 → 2026 = 4.24（八年 8 倍）。
--   2010–2014 那 1.2 万本里一半根本没有标签。
--   → 标签适合「发现新书」，不适合「找被埋没的老书」；UI 上不能当召回主力。
-- ------------------------------------------------------------
CREATE TABLE tags (
  -- ★★ 这是一张**同步表，不是静态字典**。
  --    官方标签集合会持续变化。实测 2026-11-15：`2025萌神` 的 sysTagId = 779，
  --    而上游数据里只有 2018~2024 —— 每年颁奖就多一个标签。
  --    所以它不能「一次性导入」，必须每次采集都 upsert（ON CONFLICT(name)），
  --    让 first_seen_at / last_seen_at 自然生长，用 status 表达下线。
  id      INTEGER PRIMARY KEY,              -- 本地稠密 1..N（我们自己的编号）

  -- ★★ 唯一键 = 业务主键。bootstrap 从上游继承时**只有 name**（没有官方 id），
  --    所以这是唯一可行的对齐方式，也是上游自己的做法。
  --    注意：唯一的是字符串，不是语义（§16.4）。
  name    TEXT    NOT NULL UNIQUE,

  -- 官方 id（API: expand.sysTags[].sysTagId）。**不是身份，是批次指纹。**
  --   实测「严格递增、只追加」——萌神系列：
  --     2018=407  2019=416  2020=455  2021=470  2022=616  2023=694
  --     2024=730  2025=779  橘味=680（落在 2022~2023 之间）
  --   → 号段 ≈ 年份，可用来判断「这个词是哪年开出来的」。
  --   → 但站方换词时**分配新号**（橘味 680 而非继承百合的旧号），
  --     所以它不能当实体身份，也不能用来跨期追踪同一个概念。
  --   → bootstrap 从上游继承的行此列为 NULL，自采后回填。
  sys_tag_id INTEGER UNIQUE,

  -- ★ rename 只发生在同一个 name 行上（站方原地改字，极罕见）；
  --   跨 name 的「改名」一律视为两个独立标签，不做合并（§16.3）。
  --   校验：name 在 + sys_tag_id 变 → 记日志，不要合并、不要报警中断。

  kind    TEXT    NOT NULL                  -- 语义分组，UI 分栏用（人工配置）
            CHECK (kind IN ('subject',   -- 题材：异世界/仙侠/末世/无限流
                            'role',      -- 角色关系：女性主角/单女主/嫁人/倒追/纯爱
                            'mood',      -- 情绪：治愈/致郁/轻松/硬核/救赎
                            'ip',        -- 同人 IP：型月/约战/火影/舰娘/SCP
                            'award',     -- 年度评选：2018萌神..2025萌神（每年新增一个）
                            'other')),   -- ★ 兜底：新标签先落这里，等人工归类
  -- ★ 必须有 'other'，否则官方新增标签会让 INSERT 直接违反 CHECK 约束。
  --   采集器的自动归类规则（可扩展）：`^\d{4}萌神$` → award，其余 → other。
  --   落 other 的标签照常参与筛选，只是 UI 少一个分组标题——先能显示，再谈归类。
  sort    INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,        -- 本数 <100 的长尾标签默认 0

  -- ★ 生命周期。官方下线的标签**不删除**：book_tags 里的关系还在，
  --   用户书架上的旧书还挂着它，删了会造成孤儿引用。
  --   只标记 retired，不进导航、不进种子闭包。
  --
  --   ⚠️ 但「name 消失」不等于「标签下线」（§16.3）：站方换词时旧 name 会消失，
  --      而它承载的书还在。所以 180 天未见只降权（不进导航），**不隐藏、不删关系**；
  --      同名再次出现时**复用同一行**（ON CONFLICT(name) 天然如此），绝不新建，
  --      否则 id 漂移、book_tags 断链。
  first_seen_at INTEGER,                    -- 第一次采集到（unix 天）
  last_seen_at  INTEGER,                    -- 最近一次采集到；>180 天未见 → 不进导航
  status  TEXT    NOT NULL DEFAULT 'active'
            CHECK (status IN ('active','retired'))
);

-- ★★★ 没有同义词表、没有别名表、没有映射。同义标签就是**两个不同标签**。
--   「末世」8,813 本 / 「末日」465 本，交集为 0 —— 它们本来就不该被合并，
--   合并只会得到两个不相交集合的并集 + 虚高的 book_count（§16.4）。
--   产品上也成立：多一个同名近义的入口不是噪音，是**多一条找书的路径**；
--   用户看到「末世」和「末日」并列，能自己判断哪个更贴他要的东西，
--   这比我们替他决定「这两个是同一个」更诚实，也更少出错。
--   → 同义标签的排位由 density 自然决定（末日本数少、密度低，自己沉下去），
--     不需要额外规则。唯一约束只有 tags.name 的 UNIQUE（字符串不重复）。

-- ★ 注意还有第三套「标签」：API 的 expand.tags（"双重开挂"/"十分有趣"/"另类性转"）。
--   那是**读者自由打的词**，无 id、无上限、极度长尾，和 sysTags 不是一个东西。
--   我们不入库、不成维度，只在详情页展示原文（它是氛围，不是筛选器）。

-- 标签统计（全库预计算，N 行；端上算不了——要扫 24 万本 × N 标签）
-- N = 当前 status='active' 的标签数，不是常量。
-- ★ 排序依据是 density，不是 book_count。
--   「战斗」6.5 万本但密度 0.9%，「倒追」1.5 万本密度 7.4% —— 差 8 倍。
--   按数量排，用户看到的全是宽泛无信息的词。
CREATE TABLE tag_stats (
  tag_id       INTEGER PRIMARY KEY REFERENCES tags(id),
  book_count   INTEGER NOT NULL,   -- 全库该标签书数（云端算，端上只有 19,791 本算不出）
  in_seed      INTEGER NOT NULL,   -- 种子内可展示条数 → 决定 UI 是否可点
  median_view  INTEGER NOT NULL,   -- 中位人气：衡量这个坑位的「水位」
  n_10w        INTEGER NOT NULL,   -- 人气 ≥ 10 万
  n_100w       INTEGER NOT NULL,   -- 人气 ≥ 100 万（cold 上限 382 万，安全）
  banner_cnt   INTEGER NOT NULL,
  density      REAL    NOT NULL,   -- n_100w / book_count
  computed_at  INTEGER NOT NULL
);
-- ★ retired 标签的统计照样保留（历史可查），但所有导航查询必须
--   JOIN tags 并过滤 `t.enabled = 1 AND t.status = 'active'`。
-- ★ 新标签（如刚颁的 2025萌神）首次出现时 tag_stats 可能还没有行，
--   UI 要能处理「标签存在但统计缺失」——显示标签、不显示密度，不要整条丢掉。

CREATE TABLE book_tags (
  book_id INTEGER NOT NULL,
  tag_id  INTEGER NOT NULL,
  PRIMARY KEY (book_id, tag_id)    -- 覆盖「这本书有哪些标签」
) WITHOUT ROWID;

CREATE INDEX idx_book_tags_tag ON book_tags(tag_id, book_id);  -- 覆盖「这个标签下有哪些书」

-- 标签组合配方（预计算，仅保留样本足够的）
-- ★ 实测组合不一定更准：「异世界」单独密度 1.1%，+无敌升到 2.1%，+战斗反而跌到 0.7%。
--   但三标签的真配方极强：「倒追+橘味+纯爱」全库 37 本，9 本破百万 = 24.3%（基线 1.5%，16 倍）。
--   端上无全库数据，算不出，只能构建时预计算。
CREATE TABLE tag_combos (
  combo   TEXT PRIMARY KEY,        -- '倒追|橘味|纯爱'（按 name 排序拼接，稳定可复现）
  tag_ids TEXT NOT NULL,           -- '10,27,42'
  n_total INTEGER NOT NULL,
  n_hi    INTEGER NOT NULL,
  density REAL    NOT NULL
);

-- ------------------------------------------------------------
-- 榜单定义
-- 关键：ptype 不是过滤器，是分层维度。
-- 免费/签约/VIP 的成绩量级差 100 倍，混排没有意义。
-- ------------------------------------------------------------
CREATE TABLE rank_lists (
  key        TEXT PRIMARY KEY,
  name       TEXT    NOT NULL,

  -- ★★ 榜分两类，绝不可混在一张列表里渲染：
  --   'own'   = 我们自己算的：指标透明、可解释、用累计值
  --   'sfacg' = 官方榜的快照：只有名次，官方不公布依据
  --             （种草指数实测无法由收藏/赞/月票/人气线性解释，见 data-findings §13.5）
  --
  --   为什么要存官方榜：它是「当期热度」，我们是「累计成绩」。
  --   两者一对比就能说出一句官方说不出来的话：
  --     「官方第 3 名，历史第 47 名」→ 现在很火，但历史上不算什么。
  source     TEXT    NOT NULL DEFAULT 'own' CHECK (source IN ('own','sfacg')),

  -- own 榜必填，sfacg 榜为 NULL（官方不公布口径）
  -- ★ 单维度即可：view / mark / fav / ticket / word / point
  metric     TEXT,
  -- cum = 累计（主力） / 7d / 30d / official（官方当期榜）
  window     TEXT    NOT NULL DEFAULT 'cum' CHECK (window IN ('cum','7d','30d','official')),
  kind       TEXT    NOT NULL,   -- cumulative / efficiency / growth / curated / official
  ptype      INTEGER,            -- NULL = 不分层；否则限定单一 ptype
  status     TEXT,               -- '完结' / '断更' / '连载中' / NULL
  genre      INTEGER,
  -- ★ 榜单只允许在同一把尺子上排序，此字段强制声明数据源要求
  --   metrics = 必须有 mark/fav 真值（我们自己采到的，可精细混排）
  --   view    = 只需 view（覆盖面最大，19,800 本全可用）
  stats_req  TEXT    NOT NULL DEFAULT 'view' CHECK (stats_req IN ('metrics','view')),
  enabled    INTEGER NOT NULL DEFAULT 1,
  sort       INTEGER NOT NULL DEFAULT 0
);

-- ★ 官方 11 个榜（App 实测 2026-11-15）预置为 source='sfacg', window='official'：
--   推荐/人气/畅销/新书/收藏/月票/打赏/种草/粉丝/角色/完结
--   其中 种草榜 另有 9 个分类子榜（全部/魔幻/玄幻/古风/科幻/校园/都市/游戏/悬疑），
--   故 key 形如 'sfacg:seed:all' / 'sfacg:seed:2'（genre 编号）。
--   注意 粉丝榜/角色榜 的主体不是书，不进 rank_snapshots(book_id)，单独处理。

-- ------------------------------------------------------------
-- 榜位历史（服务「变化」，不服务排序）
-- ------------------------------------------------------------
CREATE TABLE rank_snapshots (
  list_key TEXT    NOT NULL,
  bucket   TEXT    NOT NULL,   -- '2026-11-15' / '2026-W46'
  pos      INTEGER NOT NULL,
  book_id  INTEGER NOT NULL,
  -- ★ 我们自己的榜填真实数值；官方榜留 NULL（它只给名次，
  --   种草指数是黑箱，存进来会造成「看起来可比」的假象）
  score    INTEGER,
  PRIMARY KEY (list_key, bucket, pos)
) WITHOUT ROWID;

CREATE INDEX idx_snap_book ON rank_snapshots(book_id, list_key, bucket DESC);

-- ------------------------------------------------------------
-- 书架（用户私有）—— 【user.db】
-- ------------------------------------------------------------
CREATE TABLE shelf (
  book_id     INTEGER PRIMARY KEY,
  added_at    INTEGER NOT NULL,
  note        TEXT,
  last_opened INTEGER
);

-- 本地状态（—— 【user.db】；与 seed.db 的 meta 分开，避免替换时被覆盖）
-- ★ 这里存"这台设备自己的状态"，种子替换后必须保留。
CREATE TABLE local_meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);
-- schema_version      本地库结构版本（迁移用）
-- seed_version        当前挂着的种子版本（与 seed.db 的 meta.seed_version 对账，
--                     不一致 → 触发重放）
-- seed_snapshot_at    冗余一份 seed 快照日，用于重放判定（省一次跨库查询）
-- last_replay_at      上次重放时间
-- last_report_at      上次上报时间（v1 恒不存在——没有上报模块）
-- client_id           匿名随机 id（首次启动生成，无设备指纹），上报去重/限流用
--                     ★ v1 不上报也要生成它。否则 P2 上线时所有存量设备都是"新设备"，
--                       clients>=3 这条防脏阈值永远达不到。生成成本是一次 UUID。
-- detail_ttl_days     详情缓存 TTL（默认 14）。★ v1 就生效：端上抓详情=分布式爬虫，
--                     这是生存约束，不是性能优化
-- total_opens         累计打开详情页次数（本地统计，不上报）

-- ------------------------------------------------------------
-- 搜索索引：★ 不建 FTS5
--
-- 种子里只有 19,791 本，trigram 索引本身 1–2MB，比数据还大；
-- 且中文两字词不足 3 字符时 MATCH 直接失效，实际只能 LIKE '%kw%' 全表扫。
-- 结论：在 Dart 内存里做前缀 + 子串 + 拼音首字母匹配，2 万条遍历 <20ms。
-- 详见 docs/search.md §6。
--
-- 保留这段仅作为「若将来种子扩到 5 万本以上」的备选，默认不执行。
-- CREATE VIRTUAL TABLE catalog_fts USING fts5(
--   title, author, content='catalog', content_rowid='id', tokenize='trigram'
-- );
-- ------------------------------------------------------------

-- ============================================================
-- 种子包定义：内置 **19,856 本**（gzip 实测 ≈ 2.4 MB）
--
-- 三个闭包取并集：
--   A. 榜位闭包 11,442 本 = 9 genre × 3 status × 3 ptype 共 80 组各 top 200
--   B. 标签闭包 12,478 本 = 当前全部 active 标签各 top 200（快照时 106 个）
--   C. **banner 全集 667 本**（★ 2026-11-15 新增，data-findings §17.10）
--   → A∪B = 19,791；再并 C 得 **19,856**（C 里有 65 本不落在 A∪B 里）
--
-- ★★ 为什么 C 不能省（这条差点漏掉）：
--   banner 的授予逻辑与人气反着来（文豪野犬点击 475 挂十年）。667 本里
--   组内名次中位 346，榜位闭包只覆盖 544 本，∪ 标签闭包也只到 602 本，
--   剩下 **65 本（9.7%）永远进不来** —— 而少的正好是「人气低但站方力推」这批，
--   也就是 banner 全部价值所在。能被 top 200 兜住的 banner 书，本来就不需要 banner。
--   代价 +65 行 ≈ +15 KB gzip，收益是「官方精选」667 行完整。
--
-- ★ 体积是实测值，不是估算。早期按「每本 60 字节」推出 223 KB，错了 10 倍：
--   中文标题 UTF-8 三字节/字、封面 URL 约 70 字节、SQLite 每行还有记录头开销。
--   实测（含封面、含标签关系 72,922 行）：原始 5,576 KB → gzip 2,407 KB。
--   参考：去掉封面省 400 KB；封面只存后缀只省 20 KB（gzip 已经吃掉了公共前缀）。
--   2.4 MB 内置在 APK 里完全可以接受，不必为省几百 KB 牺牲封面。
--
-- 覆盖 100% 的可消费榜位（用户不会滑到第 2000 名，见 data-findings.md §11）
-- 自采完成后 19,856 本全部 stats_src='own'（全指标真实）；
-- bootstrap 阶段才会有 upstream 行，且它们不能进收藏/点赞榜。
-- 标签必须一起内置：小众标签（克苏鲁 119 本、型月 522 本）若不进标签闭包，
-- 端上会只剩 2 本和 14 本，这两个入口等于废掉。
--
-- ★ 另外两张「基础设施表」也内置，体积可忽略但不可省：
--   nid_epoch 85 行（≈1 KB gzip）→ 24.6 万本的上架日，全部时代分析的根
--   era_stats 16 行（< 1 KB）    → 年代榜的语境，「那一年 24,347 本新书里 91 张横幅」
-- ============================================================

-- ============================================================
-- 核心查询（基于实测数据校准）
--
-- ★ 总纲：官方榜的排序键是「商业现值」（还在产生收入吗），不是成绩。
--   铁证：同是 VIP，完结书中位点击 327 万，连载中 63 万（5.1 倍），
--   官方把前者撤榜、后者留在榜上。Novly 的排序键只有一个：累计成绩。
-- ============================================================

-- 0) ★ 殿堂 —— banner 与 5000 万点击双认证，全站仅 14 本
--    这是全库置信度最高的集合：站方盖章 + 读者用点击投票
-- SELECT id, title, author, view_num, word_num, status
-- FROM catalog WHERE is_banner = 1 AND view_num >= 50000000
-- ORDER BY view_num DESC;
-- → 14 本。Top1《英雄再临》1.19 亿点击，2024-03 完结，官方已撤榜

-- 0b) ★ 一口气读完 —— 完结 + 超长篇 + 读者验证
--    官方把「完结」当减分项（不能变现了），读者把它当加分项（能读完）
-- SELECT id, title, view_num, word_num, status, ptype
-- FROM catalog
-- WHERE status = '完结' AND word_num >= 1000000 AND view_num >= 100000
-- ORDER BY view_num DESC LIMIT 50;
-- → 1,422 本

-- 0c) 考古 —— 5 年无更新但成绩仍然能打
--    成绩不随时间衰减（5 年以上完结组平均点击 536 万），只是停止增长
-- SELECT id, title, view_num, word_num, last_update
-- FROM catalog
-- WHERE status = '完结' AND last_update < :five_years_ago AND view_num >= 500000
-- ORDER BY view_num DESC LIMIT 50;
-- → 956 本

-- 1) 产品主榜：「完结神作」
--    mark_num IS NOT NULL 保证 like/praise 是真值，可以放心混排
-- SELECT id, title, author, view_num, mark_num, word_num, status, ptype
-- FROM catalog
-- WHERE mark_num IS NOT NULL AND status IN ('完结','断更')
-- ORDER BY view_num DESC
-- LIMIT 50;
-- → 2,515 本，Top1「英雄再临」1.19 亿点击

-- 2) 「官方精选」——banner 是站方人工认证，独立于成绩
--    这是唯一无法被爬虫复现的信号，也是最该给新用户看的入口
-- SELECT id, title, author, view_num, status, ptype
-- FROM catalog WHERE is_banner = 1
-- ORDER BY view_num DESC LIMIT 50;
-- → 667 本

-- 3) 分层榜（避免免费/签约/VIP 混排）
-- SELECT id, title, ptype, view_num
-- FROM catalog
-- WHERE mark_num IS NOT NULL AND status = :status AND ptype = :ptype
-- ORDER BY view_num DESC LIMIT 50;

-- 4) ★「被埋没的好书」——产品的灵魂入口
--    定义：读者用点击找出来了，编辑却连签约都没给（ptype=2 免费）。
--    这批书在官方体系里不存在：不在新书榜（已完结/断更），也没有任何推荐位。
--    只用 click 排序。这条**不需要** like/praise，所以最早被采进来的书也能进。
-- SELECT id, title, author, view_num, word_num, status
-- FROM catalog
-- WHERE ptype = 2 AND is_banner = 0
--   AND status IN ('完结','断更') AND view_num >= 100000
-- ORDER BY view_num DESC LIMIT 50;
-- → 4,930 本，last_update 跨 2008-02 至 2026-05
--   样本：《穿越者将会死于凯文卡斯兰那》377 万点击、10 万字、完结、从未签约

-- 4b) 「商业验证的完本」——过了两轮编辑筛，但没拿到 banner
-- SELECT id, title, view_num, word_num, status FROM catalog
-- WHERE ptype = 4 AND is_banner = 0
--   AND status IN ('完结','断更') AND view_num >= 100000
-- ORDER BY view_num DESC LIMIT 50;
-- → 4,009 本

-- 4c) 宽口径长尾（含签约/VIP，用于「再挖一层」）
-- SELECT id, title, ptype, view_num FROM catalog
-- WHERE is_banner = 0
--   AND status IN ('完结','断更') AND view_num >= 100000
-- ORDER BY view_num DESC LIMIT 50;
-- → 约 11,700 本

-- 5) 长篇巨制（字数维度，老书的天然优势）
-- SELECT id, title, word_num, view_num FROM catalog
-- WHERE mark_num IS NOT NULL AND word_num >= 1000000
-- ORDER BY word_num DESC LIMIT 50;

-- 6) 全量搜索（长尾命中后按 click 排序，不用任何综合分）
-- SELECT c.id, c.title, c.author, c.view_num, c.stats_at
-- FROM catalog c
-- WHERE c.title LIKE '%' || :q || '%' OR c.author LIKE '%' || :q || '%'
-- ORDER BY c.view_num DESC LIMIT 30;

-- 7) 分面计数（筛选器展示「玄幻 12,345」）
-- SELECT genre, COUNT(*) FROM catalog
-- WHERE view_num >= 10000 AND ptype = :ptype
-- GROUP BY genre;

-- ★ 反例，永远不要写：
-- SELECT * FROM catalog ORDER BY mark_num DESC LIMIT 50;
-- → 未自采的书 like 全是 NULL，已自采的会永久霸榜，
--   这不是「收藏最多」，这是「哪一批先采过」。

-- 8) ★ 标签导航：按「神作密度」排，不按本数排
--    按本数排出来是 战斗/日常/异世界 —— 全是宽泛词，没有信息量。
--    按密度排才看到「神作扎堆的地方」。
-- SELECT t.id, t.name, t.kind, s.book_count, s.density
-- FROM tag_stats s JOIN tags t ON t.id = s.tag_id
-- WHERE t.enabled = 1 AND t.status = 'active' AND s.in_seed >= 20
-- ORDER BY s.density DESC LIMIT 30;
-- → 倒追 7.4% / 嫁人 5.8% / 变身 5.1% / 橘味 4.2%，对照 战斗 0.9%、日常 1.4%
-- ★ 必须带 status='active'：官方下线的标签（retired）不该出现在导航里，
--   但它的 tag_stats 和历史关系仍保留，用于已收藏它的用户的旧数据。

-- 9) 标签榜（同一个榜位机制，list_key = 'tag:<name>'）
-- SELECT c.id, c.title, c.view_num, c.word_num
-- FROM book_tags bt JOIN catalog c ON c.id = bt.book_id
-- WHERE bt.tag_id = :tag_id
-- ORDER BY c.view_num DESC LIMIT 200;

-- 10) 标签组合筛选（端上直接按交集查，最多 3 个）
-- SELECT c.id, c.title, c.view_num
-- FROM catalog c
-- WHERE EXISTS (SELECT 1 FROM book_tags WHERE book_id=c.id AND tag_id=:a)
--   AND EXISTS (SELECT 1 FROM book_tags WHERE book_id=c.id AND tag_id=:b)
-- ORDER BY c.view_num DESC LIMIT 200;

-- 11) 神作配方（预计算表直读）
-- SELECT combo, n_total, n_hi, density FROM tag_combos
-- WHERE n_total >= 30 ORDER BY density DESC LIMIT 12;

-- 12) ★★ 官方名次 vs 历史名次（产品里最有信息量的一句话）
--     官方 11 个榜全是「当期热度」，我们是「累计成绩」，同一本书在两边的名次差
--     就是全部产品价值。「官方第 3 / 历史第 47」= 现在很火，历史上不算什么；
--     「官方没有 / 历史第 12」= 当年神作，今天没人推。
-- WITH official AS (
--   SELECT book_id, pos FROM rank_snapshots
--   WHERE list_key = 'sfacg:popular' AND bucket = (SELECT MAX(bucket) FROM rank_snapshots)
-- ), ours AS (
--   SELECT book_id, pos FROM rank_snapshots
--   WHERE list_key = 'own:cum:all' AND bucket = (SELECT MAX(bucket) FROM rank_snapshots)
-- )
-- SELECT c.id, c.title,
--        o.pos AS 官方名次, u.pos AS 历史名次,
--        COALESCE(u.pos, 999999) - COALESCE(o.pos, 999999) AS 名次差
-- FROM catalog c
-- LEFT JOIN official o ON o.book_id = c.id
-- LEFT JOIN ours     u ON u.book_id = c.id
-- WHERE u.pos IS NOT NULL OR o.pos IS NOT NULL
-- ORDER BY 名次差 ASC LIMIT 50;
-- → 名次差为正 = 官方比我们靠前 = 正在火；为负 = 历史地位高于当前热度 = 被埋没的经典

-- ★ 反例 2：永远不要按 tag 的 book_count 排导航
-- SELECT t.name FROM tags t JOIN tag_stats s ON s.tag_id=t.id ORDER BY s.book_count DESC;
-- → 前三名是 战斗/日常/异世界，占了全库 27%，用户点进去和「全部」没区别。

-- ★ 反例 3：永远不要做「全站点赞榜」
-- SELECT * FROM catalog ORDER BY fav_num DESC LIMIT 50;
-- → 三个独立原因，任何一个都足以否掉：
--   (a) 赞是唯一直接被榜单消费的计数，因此唯一有明确刷票收益（作者买水军点它）。
--   (b) 各 genre 的「赞/收藏」基准差 50 倍：同人区 84.2% 的书赞≥收藏
--       （人气≥100万样本 64/76），而玄幻/古风/悬疑是 0%。跨 genre 混排等于
--       把「同人读者习惯点赞」误判成「这本书特别好」。
--   (c) 赞与曝光强绑定：书只要上过一次首页，赞就永久高，和现在还好不好看无关。
--   如果一定要有「大家喜欢」这个入口，用 point（评分）而不是 fav_num：
--   评分要「登录 + 看过」才能打，门槛高一个数量级，且天然是均值不是累计量。

-- 13) 首页轮播：日轮换（同一天稳定，长期铺满 667 张）
--     ★★ 权重必须用 era_pct，**绝对不能用 view_num**。
--     原因：view_num 混了两件不可比的东西 ——
--       ① 当年用户规模（banner 书人气中位：2016 年 206 万 / 2022 年 1,132 万）
--       ② 累计时间（2016 年上架的书已攒 10 年，2024 年的只攒 2 年）
--     用 view_num 加权 = 让轮播永远被黄金五年的老书占满，而且是最早那批。
--     用 era_pct（当年分位）= 每本在「自己的年代」里都是 top 1%，平等竞争；
--     出现频率自然由**各年 banner 数量**决定（2015–2019 占 65%），这正是我们要的。
--
--     :day = 当天序数（如 strftime('%j')），:cid = local_meta.client_id 低 32 位
-- SELECT b.book_id, b.image_url, b.etag, c.title, c.author, b.add_year
-- FROM banners b JOIN catalog c ON c.id = b.book_id
-- WHERE b.active = 1
--   AND b.era_pct >= 20          -- 挡掉正版引进的日轻（30 本，点击可低至 475）
-- ORDER BY -ln((((b.book_id * 2654435761) ^ :day ^ :cid) % 1000000 + 1) / 1000001.0)
--          / (b.era_pct * b.era_pct / 100.0 + 1)
-- LIMIT 5;
-- （exp 加权随机：key = -ln(U)/w。SQLite 有 ln()，但端上在 Dart 里算更简单）
--
-- ★ 为什么不做「按年分层配额」：5 个位要覆盖 11 个年份，比例配额会让
--   2020–2025 永远轮不到（2025 全年只有 7 本，配额 5×7/667 = 0.05 → 0 个位）。
--   均匀随机已经自然给了 65% 给黄金五年，再加分层就是过度设计。

-- 14) 「官方精选」入口（banners 表就是它的数据源，比扫 catalog.is_banner 更有信息）
-- ★ 按 era_pct 排，不按 view_num 排 —— 否则 2023-08-03 批量引进的 4 本日轻
--   会和原创神作混在一起，用户点进去发现 3,532 人气，信任就没了。
-- SELECT b.book_id, c.title, c.author, b.add_year, b.era_pct, b.image_url,
--        e.books AS era_books, e.banners AS era_banners
-- FROM banners b
-- JOIN catalog c ON c.id = b.book_id
-- LEFT JOIN era_stats e ON e.year = b.add_year
-- WHERE b.active = 1
-- ORDER BY b.era_pct DESC, c.view_num DESC;
-- → UI 可显示「2019 年 · 当年 24,347 本新书里 91 本获官方横幅」，
--   这句话本身就是产品价值：它把「banner 有多难得」量化给用户看。

-- 15) ★ 年代榜（新增入口）：某一年上架的书按人气排
--     这是我们定位「过去什么好」的第一个时间维度 —— 之前整个设计里没有时间轴。
--     add_time 来自 nid_epoch 插值（±1 周），按年分桶完全够用。
-- SELECT id, title, author, view_num, word_num, is_banner
-- FROM catalog
-- WHERE add_time >= :y_start AND add_time < :y_end
-- ORDER BY view_num DESC, mark_num DESC, id
-- LIMIT 100;
-- → 配合 era_stats：标题写「2019 年 · 新书 24,347 本 · top1% 门槛 273 万」，
--   让用户知道自己看的这一屏有多难进。

-- 16) 年代总览（时间轴的导航页）
-- SELECT year, books, banners, p99_view, grant_rate
-- FROM era_stats WHERE books >= 1000 ORDER BY year DESC;

-- ★ 反例 5：永远不要用 image_mtime 排「最近上架」
-- SELECT book_id FROM banners ORDER BY image_mtime DESC LIMIT 10;
-- → Last-Modified 是**批量上传时刻**：抽样 23 张里 16 张集中在 2022-01-21
--   03:33:44~03:34:04（一分钟内传完），那是站方的一次批量重建，不是同时上架。
--   按它排会得到一份「代理上传批次榜」，看起来很像「最新推荐」，实际毫无时间意义。
--   banner 的时间信息在数据层不存在，任何「最新 banner」都是编的。

-- ★ 反例 6：永远不要用 URL 或扩展名判断图片能不能用
-- WHERE image_url LIKE '%.jpg' AND active = 1   -- ✗
-- → 5/667 张实际是 PNG 却叫 .jpg（magic bytes 89 50 4E 47）。
--   校验必须：Range GET bytes=0-511 → 看 FF D8（jpeg）/ 89 50 4E 47（png）。
--   且该 CDN 对不存在的路径返回 **200 HEAD + 假 Content-Length**，HEAD 完全不可信。

-- ============================================================
-- 写入路径（user_patch → catalog 的重放）
-- 这一组不是"查询"，是端上唯一允许改数据的四条语句。
-- ============================================================

-- W1) 详情页回填 / 搜索自动收录：**第一步**，写日志（事务提交后才动 catalog）
-- INSERT INTO user_patch(book_id, payload, src, observed_at, base_seed)
-- VALUES (:nid, :json, :src, strftime('%s','now'), :seed_version)
-- ON CONFLICT(book_id) DO UPDATE SET
--   payload     = excluded.payload,
--   src         = excluded.src,
--   observed_at = excluded.observed_at,
--   base_seed   = excluded.base_seed,
--   applied     = 0,          -- 重新待物化
--   synced_at   = NULL,       -- 重新待上报
--   sync_batch  = NULL;

-- W2) **第二步**，物化到 catalog（也用于种子替换后的重放）
--     注意：只写 payload 里出现的字段，不动 stats_src 以外的判定字段。
-- UPDATE catalog SET
--   view_num   = COALESCE(json_extract(:json,'$.view_num'),   view_num),
--   mark_num   = COALESCE(json_extract(:json,'$.mark_num'),   mark_num),
--   fav_num    = COALESCE(json_extract(:json,'$.fav_num'),    fav_num),
--   ticket_num = COALESCE(json_extract(:json,'$.ticket_num'), ticket_num),
--   point      = COALESCE(json_extract(:json,'$.point'),      point),
--   word_num   = COALESCE(json_extract(:json,'$.word_num'),   word_num),
--   chapter_num= COALESCE(json_extract(:json,'$.chapter_num'),chapter_num),
--   last_update= COALESCE(json_extract(:json,'$.last_update'),last_update),
--   stats_at   = COALESCE(json_extract(:json,'$.stats_at'),   stats_at),
--   stats_src  = 'own'
-- WHERE id = :nid;
-- → 若 rowcount = 0（自动收录的新书），改走 INSERT（字段取自 API 全量响应）。

-- W3) 启动重放：扫未物化的日志，逐条比对种子快照日
-- SELECT p.book_id, p.payload, p.observed_at,
--        CAST((SELECT v FROM meta WHERE k='seed_snapshot_at') AS INTEGER) AS snap
-- FROM user_patch p
-- WHERE p.applied = 0;
-- 对每一行：
--   observed_at <= snap → UPDATE user_patch SET applied=1 WHERE book_id=?  （观测过时，作废）
--   否则                → 执行 W2，然后 applied=1

-- W4) 上报：只取 payload，绝不带 shelf / search_log
-- SELECT book_id, payload, observed_at FROM user_patch
-- WHERE synced_at IS NULL ORDER BY observed_at LIMIT 200;
-- 成功后：UPDATE user_patch SET synced_at=strftime('%s','now'), sync_batch=:bid
--         WHERE book_id IN (...);
-- 失败：什么都不改，下次重试（同一 book_id 被新观测覆盖时会重置 synced_at）。

-- ★ 反例 4：永远不要「先改 catalog、后补日志」
-- UPDATE catalog SET view_num=... ; INSERT INTO user_patch ...
-- → 中间崩溃 = 改了一个下次种子更新就消失的值，而且没有任何痕迹。
--   日志必须先行：它是唯一能在种子替换后存活的东西。

# 比赛 URL 与 API 规律：高质量书籍的高效入口

> **定位**：比赛数据通路的规律总览与导航——把端点、字段、补采、获奖定案里的规律抽象成体系，服务于「快速获取高质量书籍 → 提高种子质量」，逐届实证与 tagId 地图用指针指向权威文档。
> **状态**：分析侧研究定案；`app/` 冻结，未改数据集/种子。是否解禁 `app/` 仅作工程交接事项，本文不执行。
> **权威范围**：本文唯一维护三类规律（URL 形态演进、四季节奏、API 与 tagId 分配规律）与文档导航。
> **口径**：文中计数/比例/日期均为快照现算值，仅供参考、随数据版本变化，禁止硬编码进代码；数字不新增、不外推。
> **更新日期**：2026-11-21。

## 结论

时代越新，进入官方榜单的参赛书比例越高（报告 15：库内征文占比 2016 约 20% → 2024 约 59.7%；
月票榜上榜书 2024 达 97.8%，**头部口径，不可外推成「所有新书」**）；获奖 = 平台 + 读者双重认可，
比单看收藏更干净的优质信号。两者合起来：**比赛是种子质量的高效入口**——用远少于全库扫描的请求换高密度优质书目。

三条通路按对种子质量的贡献排序（此表为三条通路的唯一一处汇总）：

| 通路 | 依赖规律 | 产出 | 状态 |
| --- | --- | --- | --- |
| 补优质 | 获奖名单存放规律 | 优质子集 + `contest_awards` 表 | 已验证（获奖定案） |
| 补书目 | 参赛清单 + tagId 规律 | 9,012 本（29%）不在 db 的漏采书，短/中篇最重 | 已验证（补采记录） |
| 提定年 | 官方赛程日期 | 高精度锚点（部分并入锚点表） | 已验证 |

**不造新指标**：排行榜仍用 `fav_pctl`；获奖只作筛选/徽标、不作打分项（避免「获奖 + 高收藏」双重计权），
与 app 主线（novly/classic 不引入新指标）一致。

## 事实：三类规律

### URL 形态演进（四代，按年代）

| 世代 | URL 形态 | 数据存放 | 清单 API |
| --- | --- | --- | --- |
| 早期静态页（四/五征） | `book.sfacg.com/zwYYYY/` | 页面图片/少量链接 | 无（只有规则页文本） |
| H5 活动页（2018–2022） | `pages.sfacg.com/{h5,pc}/act/zwYYYY/`、`/act/djzwYYYY/`（冬征） | 页面 `index.js` 顶部 `tagIds=[...]` | 旧 `Common.ashx?op=getNovelsByTag` |
| 日期式 SPA（2023 起） | `pages.sfacg.com/h5/act/zwYYYYMMDD/pc` | 打包 JS 里 `longTagId/middleTagId/shortTagId`（X 征三轨）或单 `tagId` | 新 `/api/essay/getNovels` |
| UUID 页（2024 秋起） | `pages.sfacg.com/h5/act/zw/essayActivity_{UUID}.html` | HTML `data-tagid`；获奖写进 HTML `img[data-nid]` | 新 `/api/essay/getNovels` |

**年份段演进**：`zwYYYY`（启动年）→ `zwYYYYMMDD`（精确启动日，如 `zw20240504` = 十二征 5-04）。
SPA 的日期 id 本身即启动日，可作赛事定年的页面自证（见 `analysis/references/contest-editions.md`）。

**UUID 页起点是 2024 秋征，务必强调**：2024 春征（`zw20240301`，tag 699）仍是日期式 Vue SPA，
即 2024 年内春征（3 月）→ 秋征（9 月）之间换了模板，勿笼统写「2024 起都用 UUID 页」。
UUID 无法从届次推导，只能靠用户 App 提供入口；每届一套 UUID（4 个 tab：规则/作品/评论/获奖）。
已实证六届（2024 秋 / 2025 春 / 2025 秋 / 2026 春 / 八征冬 / 九征冬）同模板，仅 UUID 与 `template.js?v=` 版本号不同
（2024 秋 `27868` / 2025 春 `42327` / 2025 秋 `83885` / 八征冬 `42945` / 2026 春 `62767` / 九征冬 `94362`），
版本大致随时间递增但非严格；技术栈是 **jQuery + template.js、非 Vue**（与第三代 X 征 SPA 不同）。

**冬征演进**：`djzwYYYY`（一~五征）→ `zwYYYYMMDD` 日期式 SPA（六征 `zw20221205`/485、七征 `zw20231204`/692，
均单轨）→ UUID 页（八征 726、九征 774 起）。**至此冬征一~九届 URL 全部实证**。
六/七征是同套模板早/晚期变体：六征 tagId 写死组件 data、获奖 `showBookDetail(数字)` + CSS 定位分组；
七征 tagId 分三环境、获奖 `openNovel("字符串")` + 标题图分组（获奖形态详见 `contest-roster-fields.md`）。

### 四季节奏（全年首尾相接）

| 产品线 | URL 形态 | 启动节奏 | 清单 API 掌握到 |
| --- | --- | --- | --- |
| X 征（≈夏） | `zwYYYY` → `zwYYYYMMDD` | 早年 7 月、近年固定 5-04 | 十三征（2025） |
| 冬季征文 | 一~五征 `djzwYYYY` → 六/七征 SPA → 八征起 UUID 页 | 12 月上旬（12-04/05/06），1 月高峰 | 一~九届全有且 URL 全实证 |
| 春季征文 | 2024 日期式 SPA → 2025/2026 UUID 页 | 3 月初（03-01） | 2024 / 2025 / 2026 |
| 秋季征文 | UUID 页（2024/2025 实证） | 9-30 | 2024 / 2025 |

**规律**：上一届截止与下一届启动仅差 0–1 天，四季构成持续的新书供给泵；
cohort bulk 下界定年一致晚于官方启动 9–20 天，**故 cohort 下界不可作启动日点锚，窗口约束才是正确用法**（`analysis/references/contest-editions.md`）。

### 获奖页 URL 随机串（实操价值高）

获奖页末尾随机路径（如 `zw20240504/Q3PrLponYiEwN`）是活动页 JS 写死的 Vue Router path，
非 token/加密/动态生成。特性：字符池固定、来自同一混淆池重排（十二征 `...QperQerQnWin` vs 十三征
`...QpersdQerQnWin` 只差 `sd`）；语义会漂移（几乎同串跨届可从「长篇终审」变「中短篇终审」）。
**结论：不能硬编码 path→赛道**，每届从页面 `document.title`（组件 mounted 赋值）或 DevTools 确认。
两届完整路由表与陷阱实证见 `contest-roster-fields.md`。

### API 与 tagId 分配规律

两套清单端点（按活动页世代）：新 SPA/UUID 页 `/api/essay/getNovels?tagIds={t}&page={n}&size={n}`，
旧 H5 `Common.ashx?op=getNovelsByTag&tagId={t}&ps=200&pi={0基}`。
每条 6 字段（nid/标题/作者/简介/封面/categoryID），不含成绩/定年/获奖/名次/赛道中文名。
**字段名大小写两套**（`novelID` vs `NovelID`），**page 起始随版本变、以页面实际传参为准**（仅旧 H5 的 `pi` 稳定 0 基）；
tagId 位置也随版本变（旧 SPA 在打包 JS 变量、UUID 页在 HTML `data-tagid`）。
端点参数与字段真实例见 `contest-roster-fields.md`。

tagId 四条规律：① **全局递增编号池**，同届赛项严格连号（653/654/655、702/703/704、752/753/754），
年度间隔稳定（655→702 = +47、702→752 = +48，每年新增约 47 个号，仅 3 个属 X 征）；
② **每届新增、跨届不复用**，不存在「掌握 4 个端点一劳永逸」；
③ **不区分赛事类型**，号池混着题材/活动标签，`categoryID` 无法区分；
④ **环境异号**，sandbox/test/pages 三套不同（十二征短篇 sandbox 533 vs pages 704），按 `location.host` 取 pages 值。
tagId 地图与逐届实证见 `contest-roster-harvest.md`（唯一权威）。

## 操作：规律怎么落地

**补全路径（已完整跑通）**：`size=1` 探活 → 定年聚集筛候选 → 用户 App 观测确认；
补齐优先靠用户 App DevTools 现场取链接，比猜 URL 快（判定法见 `contest-roster-fields.md`）。
**陷阱**：`size` 对部分 tag 有边界（724 用 `size=500` 返回空、`size=1/3/8` 正常），判空须降 size 重试。

**获奖数据形态是规律落地的最大变量**：获奖名单不在任何接口，存放形态分四代
（早期静态页无 → 十二/十三征 JS 静态 JSON → UUID 页 HTML `img[data-nid]` 六届 → 日期式 Vue render 硬编码三变体
`openNovel("nid")` / `showBookDetail(nid)` / `goNovel(nid)`），提取器须都兼容；
`data-nid`/函数参数始终是可靠 nid，奖项名只能尽力解析、不臆造。
四代形态与提取正则见 `contest-roster-fields.md`（权威），逐届获奖明细与入种口径见 `award-winners-as-seed-source.md`。

**定年锚点**：活动页/官方通稿的精确日期是高置信来源，但用法有限——四征「窗口内最小 nid + 官方启动日」成立并已并入锚点表；
2024-09 后各届 cohort bulk 下界定年一致晚 9–20 天，点锚不成立，只作窗口约束与验证档案（`analysis/references/contest-editions.md`）。

## 边界与降级

- 比赛只覆盖**参赛书**：未参赛的一次性完本短篇、早期静态页时代作品仍会漏；给的是**书目与认可信号**，
  成绩与实时状态仍靠详情抓取。本文研究的是「发现 + 优质增补」，不是「成绩实时」或「全量覆盖」的替代。
- 四代形态均已实证、获奖 = 优质已验证；获奖提取器正式化（脚本固化、探针兼容四代）为工程侧交接事项，`app/` 不执行。
- **真缺口**：2023 及更早的春/秋征 URL、早期静态页（四/五征）无清单 API——覆盖的残余空白。
- 上述真缺口的补全与工程解禁时点，作为工程侧交接事项另行裁定。

## 交叉引用

- **端点与参数**：`sfacg-endpoints.md`、`contest-roster-fields.md`
- **tagId 地图 / URL 实证 / 补采覆盖**：`contest-roster-harvest.md`（唯一权威）
- **清单字段 / 获奖四代形态 / 提取正则**：`contest-roster-fields.md`（权威）
- **获奖逐届明细 / 入种口径（净 911、剔除 602、140 补采）**：`award-winners-as-seed-source.md`（权威）
- **展示设计 / 三层数据落后 / 降级**：`contest-display-in-app.md`
- **url 与届次逐届对照 / 定年窗**：`analysis/references/contest-editions.md`

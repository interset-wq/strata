# 征文页参赛清单：短/中篇补采通路与 tagId 地图（唯一权威，2026-11-21）

> **定位**：征文清单 REST 补采通路实证记录，也是本组文档唯一的 tagId 地图 / URL 实证权威——逐届 URL、tagId、接口世代以本文为准，其他文档只给文件指针。
> **状态**：分析侧实证定案；`app/` 冻结，未改数据集/种子。是否解禁 `app/` 仅作工程交接事项，本文不执行。
> **权威范围**：本文唯一维护 tagId 地图、活动页 URL 台账、补采覆盖数字与试号实证。
> **口径**：文中计数/比例/日期均为快照现算值，仅供参考、随数据版本变化，禁止硬编码进代码；数字不新增。
> **更新日期**：2026-11-22（722/755 UUID 页实证转正、747/748 官方赛事名订正）。

## 结论

1. **通路成立**：征文清单由 REST 接口分页返回，含 `nid/标题/作者/intro/封面/categoryID`，可直接批量取，不必逐本抓详情页。
2. **两套接口并存**（按活动页年代）：旧 H5 `GET /ajax/ashx/Common.ashx?op=getNovelsByTag&tagId={t}&ps=200&pi={0基}` →
   `{status,novels,totalPage}`；新 SPA `GET /api/essay/getNovels?tagIds={t}&page={n}&size={n}` → `{status,data:{totalPage,novels}}`。
   `page` 起始随版本变、以页面实际传参为准；仅旧 H5 的 `pi` 稳定 0 基。字段名两套大小写（`NovelID` vs `novelID`），字段明细见 `contest-roster-fields.md`。
3. **tagId 是「某届比赛的某个赛项」编号，每次新增、跨届不复用**（用户裁定）：十三征 3 个赛项 = 全新号 752/753/754，
   与十二征 702/703/704 无复用；sandbox / test / pages 三套环境各一批（十二征短篇 sandbox 533 vs 生产 704）。
   **只能从每届页面现场取，不能从届次/赛项名推导、不能猜**——这就是 tagId 地图随新比赛不断膨胀的根因。
4. **补采价值（覆盖数字只在此处一处）**：14 个 tag 拉取去重 **31,092** 本，与 `novels.csv`（245,887 行）比对
   **9,012 本（29%）不在 db**；短/中篇漏采最重（七征中篇 481/1,359=35%、十二征短篇 171/321=53%、
   十二征中篇 360/686=52%）。用户举的 5 本精确短篇中 `709232 血与梦` 命中十二征短篇 tag 704，路径实证有效。

## 事实：URL 形态与 tagId 地图（权威台账）

### 1. URL 三类形态（按年代）

| 世代 | URL 形态 | 清单数据来源 | 届次对应 |
| --- | --- | --- | --- |
| 早期静态页 | `book.sfacg.com/zwYYYY/`（四/五征） | 页面内嵌少量链接，**无清单 API** | `analysis/references/contest-editions.md` |
| H5 活动页（2018–2022） | `pages.sfacg.com/{h5,pc}/act/zwYYYY/`、`/act/djzwYYYY/`（冬季） | 页面 JS 顶部 `tagIds=[...]`，走 `Common.ashx?op=getNovelsByTag` | 本轮实证 11 个 tag |
| SPA 活动页（2023 起） | `pages.sfacg.com/h5/act/zwYYYYMMDD/pc`（`zw20240504`=十二征、`zw20250504`=十三征） | 打包 JS 里 `baseUrl/longTagId/middleTagId/shotTagId`，走 `/api/essay/getNovels` | 本轮实证 3 届 |

**春/秋征：2024 起已全页面实证，仅 2023 及更早缺**。
UUID 页起点是 **2024 秋征**，2024 春征（`zw20240301`，tag 699）仍是日期式 Vue SPA。
冬征演进：`djzwYYYY`（一~五征）→ `zwYYYYMMDD` SPA（六征 485 / 七征 692）→ UUID 页（八征 726 / 九征 774 起），一~九届全实证。
规律总览见 `contest-url-api-patterns.md`。

### 2. tagId 对照台账（页面实证，数字仅供参考）

| 赛事 | 活动页 URL | tagId（长/中/短或单轨） | 接口 | 备注 |
| --- | --- | --- | --- | --- |
| 四征 | `https://book.sfacg.com/zw2016/rule.html` | — | 无 | 规则页有精确日期 |
| 五征 | `https://book.sfacg.com/zw2017/` | — | 无 | |
| 六征 | `https://pages.sfacg.com/h5/act/zw2018/` | — | 无 | |
| 一征冬征 | `https://pages.sfacg.com/h5/act/djzw2018/` | 381 | 旧 | 单轨 |
| 二征冬征 | `https://pages.sfacg.com/h5/act/djzw2019/` | 406 | 旧 | 单轨 |
| 七征 | `https://pages.sfacg.com/h5/act/zw2019/` | 408/409/410/411/412 | 旧 | 5 赛道 |
| 三征冬征 | `https://pages.sfacg.com/h5/act/djzw2020/` | 415 | 旧 | 单轨 |
| 八征 | `https://pages.sfacg.com/h5/act/zw2020/` | 418 | 旧 | 单轨 |
| 九征 | `https://pages.sfacg.com/h5/act/zw2021/` | 457/458/459/462 | 旧 | 老 H5 `tagIds=[457,458,459,462]` 写死；响应 `NovelID` 大写；457 定年全 2021 |
| 十征 | `https://pages.sfacg.com/h5/act/zw2022/` | 475/476/477 | 新 | Vue SPA chunk-common `tagId=1→475/2→476/3→477`；`/api/essay/getNovels` size=12 |
| 四征冬征 | `https://pages.sfacg.com/pc/act/djzw2021/` | 454 | 旧 | 单轨 |
| 五征冬征 | `https://pages.sfacg.com/h5/act/djzw2022/` | 466 | 旧 | 单轨 |
| 六征冬征 | `https://pages.sfacg.com/h5/act/zw20221205/`（日期式 SPA） | **485** | 新 | 组件 data 写死、无三环境配置；获奖 `showBookDetail(数字)` |
| 七征冬征 | `https://pages.sfacg.com/h5/act/zw20231204/`（日期式 SPA） | **692** | 新 | JS `f121` 模块单轨；获奖 `openNovel("nid")` |
| 十一征 | `https://pages.sfacg.com/h5/act/zw20230504/pc` | 653/654/655 | 新 | sandbox 507/508/509 |
| 十二征 | `https://pages.sfacg.com/h5/act/zw20240504/pc` | 702/703/704 | 新 | sandbox 533/534/533（短篇 533，生产 704） |
| 十三征 | `https://pages.sfacg.com/h5/act/zw20250504/pc` | 752/753/754 | 新 | sandbox 599/598/597 |
| 2022 春征 | `https://pages.sfacg.com/h5/act/zw20220301/`（日期式 SPA） | **473** | 新 | `index.b4875a62.js` 硬编码 `tagIds:"473"` 单号、无三环境；首批 200 本 nid 336578~548375、定年全 2022 |
| 2023 春征 | `https://pages.sfacg.com/h5/act/zw20230301/`（日期式 SPA） | **632** | 新 | `f121` 三环境：sandbox 503 / test·pages 632；`getNovels(page,632,"24,29")` |
| 2024 春征 | `https://pages.sfacg.com/h5/act/zw20240301/`（日期式 SPA） | **699** | 新 | `f121` 三环境：sandbox 530 / test·pages 699；获奖 `goNovel(数字)` |
| 八征冬征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_c49534b9-73b2-46c9-a33f-b8144b448662.html` | **726** | 新 | HTML `data-tagid`；获奖 10 本、alt 纯数字 |
| 2021 东方世界秋征 | ⬜（活动页已下线，`zw20210930` 404） | **464** | 新 | 页面无 URL，tagId 靠本地交集反查：全量 815 本 ∩ 库内标注 602 = 602/602 |
| 2021 异世大陆秋征 | ⬜（活动页已下线） | **465** | 新 | 全量 1287 本 ∩ 库内标注 930 = 929/930；与 464 连号、同届两赛道 |
| 2022 主题秋征 | `https://pages.sfacg.com/h5/act/zw20220930/`（日期式） | **481** | 新 | 标题「少年的无限幻想」；`index.1858c64f.js` 硬编码 `tagId:481`（单号、无三环境），`/api/essay/getNovels?tagIds=481` size=9；全量 1945 本 ∩ 库内标注 1461 = **1461/1461** |
| 2023 主题秋征 | `https://pages.sfacg.com/h5/act/zw20230930/`（日期式） | **669** | 新 | 标题「少年的奇迹历险」；`index.0c352714.js` 三环境 sandbox 521 / test·pages **669**（521 仅 1 页反证），另有子榜 `getNovels2(tagId,"23,27")`；全量 1575 本 ∩ 库内标注 1246 = **1246/1246** |
| 少年主题·奇幻冒险 | ⬜（活动页 URL 未取） | **480** | 新 | 无页面实证，tagId 靠本地交集反查：全量 935 ∩ 库内标注「少年的奇幻冒险」704 = **704/704**；tag 480 紧邻 481（无限幻想），2022 同批 |
| 少年主题·无限幻想 | `https://pages.sfacg.com/h5/act/zw20220930/`（日期式） | **481** | 新 | 见上方 2022 主题秋征行，同一赛事 |
| 少年主题·幻想之旅 | ⬜（活动页 URL 未取） | **660** | 新 | 无页面实证，tagId 靠本地交集反查：全量 999 ∩ 库内标注「少年的幻想之旅」775 = **775/775**；nid 落在 2023 上半年，与上两届逐年推进 |
| 少年主题·奇迹历险 | `https://pages.sfacg.com/h5/act/zw20230930/`（日期式） | **669** | 新 | 见上方 2023 主题秋征行，同一赛事 |
| 少年主题·幻想校园 | `https://pages.sfacg.com/h5/act/zw/essayActivity_7465fc4b-8c7e-4e23-a30c-721ec33ced8b.html`（UUID 页） | **722** | 新 | HTML `data-tagid="722"` 页面实证（2026-11-22 转正），当地聚合站活动页佐证征稿 6-21~8-31、公示 10-25；此前本地交集 404/404 命中。获奖 12 本 `data-nid`，`alt` 无中文奖项 |
| 少年二次元创想·长篇 | ⬜（活动页 URL 未取） | **747** | 新 | 官方赛事名「少年二次元创想」轻小说创作大赛（首届，2025-03-01~05-03、公示 07-07，微信原文）；长/短两赛区。tagId 靠本地交集 438/438；nid 中位 741k |
| 少年二次元创想·短篇 | ⬜（活动页 URL 未取） | **748** | 新 | 同上赛事短篇赛区；本地交集 82/82；与 747 连号、同届两赛道 |
| 2024 秋征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_0a10b388-bf92-410c-801a-59c91b853c3f.html` | **725** | 新 | HTML `data-tagid`，页面实证转正；获奖 11 本、alt 完整 |
| 2025 春征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_d892261b-8719-4e3b-b01a-b84278b2996b.html` | **746** | 新 | HTML `data-tagid`；获奖 10 本 |
| 2025 秋征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_d568a583-bde8-4f16-809a-8ab7097261be.html` | **772** | 新 | HTML `data-tagid`，页面实证转正；获奖 7 本 |
| 2026 春征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_52f25c52-1de0-4608-90fc-293aac35a588.html` | **789** | 新 | HTML `data-tagid`；获奖 6 本 |
| 九征冬征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_373481c3-8fb0-4113-83fb-5058a816f828.html` | **774** | 新 | HTML `data-tagid`，页面实证转正；获奖 10 本、alt 完整 |
| 奇幻世界主题征文 | `https://pages.sfacg.com/h5/act/zw/essayActivity_e5950dc7-7f12-4fca-8049-8fd2afd9c0eb.html`（UUID 页） | **755** | 新 | HTML `data-tagid="755"` 页面实证（2026-11-22 转正），聚合站佐证征稿 2025-06-06~08-31、公示 11-28；男性向长篇奇幻主题。此前 755 定年聚集 2025-06/194、07/186 的「奇幻主题征待观测」即此赛事 |
| 点鸭秋色回忆（对话线） | URL 未取到 | **724** | 新 | 微信原文确认（2024-09-21 开幕，对话/互动两体裁、点鸭+菠萝包双端），非页面实证；tag 试号 + 用户书名确认 |

**取生产 tagId**：SPA 的 JS 里 sandbox / test / pages 三套号并存（`i[a] ? i[a] : i.sandboxpages`，
`a = location.host.slice(0, indexOf("."))`），按 `location.host` 前缀选 `pages` 环境；旧 H5 的 `tagIds` 直接写在 `index.js` 顶部。部分早期 SPA 硬编码单号、无三环境（2022 春征 473）。

### 2b. 四季 URL 命名规律（2026-11-22 补，页面实证）

| 系列 | URL 规律 | 实证页面 | 备注 |
| --- | --- | --- | --- |
| 春征 | `h5/act/zwYYYY0301/` | 2022(473)、2023(632)、2024(699) | 启动日固定 3-01；2025 起改 UUID 页 |
| 秋征（主题制） | `h5/act/zwYYYY0930/` | 2022「少年的无限幻想」、2023「少年的奇迹历险」 | 2021 的 `zw20210930` 已下线；2024 起改 UUID 页 |
| X 征早期 | `h5/act/zwYYYY/` | 九征 `zw2021`、十征 `zw2022` | 年份式老 H5；十一征起改 `zwYYYY0504` |
| X 征中期 | `h5/act/zwYYYY0504/pc` | 十一(653–655)、十二(702–704)、十三(752–754) | 启动日固定 5-04 |
| 冬征 | `djzwYYYY` → `zwYYYYMMDD` → UUID 页 | 见上表 | 一~九届全实证 |

**页面下线时的 tagId 反查法**（本轮对 2021 主题秋征实用）：活动页 404 但清单接口仍存活时，先按 tagId 连号区间逐号拉全量 nid（`size=200` 分页、串行 0.25s），再与本地 `novels.csv` 的 `contest` 标注 nid 集合求交集。本轮 `tag464 ∩ 东方世界 = 602/602`、`tag465 ∩ 异世大陆 = 929/930`，交集压倒性即锁定归属。未确认的 tag 一律不写入正式台账。

### 3. 按四季清点：每条线掌握到哪一届

| 系列（启动节奏） | 有清单 API 的届次 | 缺 API 的届次 | 覆盖到最新？ |
| --- | --- | --- | --- |
| X 征（5 月初，≈夏） | 七征(408–412)、八征(418)、九征(457/458/459/462)、十征(475/476/477)、十一征(653–655)、十二征(702–704)、十三征(752–754) | 四/五/六征（早期静态页，无 API） | 是（十三征 2025） |
| 冬季征文（12 月上旬） | 一~五征(381/406/415/454/466)、六征(485)、七征(692)、八征(726)、九征(774) | —（一~九届全有，URL 全实证） | 是（九征） |
| 春季征文（3 月初） | 2022(473)、2023(632)、2024(699)、2025(746)、2026(789) | —（2022 起全有） | 是（2026） |
| 秋季征文（9-30） | 2021 两赛道(464/465)、2022(481)、2023(669)、2024(725)、2025(772) | 早期 2016–2020 主题届 | 是（2025） |
| 少年主题系列（「少年 XX」/「少年二次元创想」） | 480/481（2022）、660/669（2023）、722（2024）、747/748（2025）——7 标注全 100% 交集锁定 | — | 独立年度系列，与秋征交叠；722 已 UUID 页实证 |
| 对话线·点鸭秋色回忆 | 724（试号确认） | — | 独立赛事，非四季主线 |

四季是 4 条持续产出的系列、不是 4 个固定端点——每办一届新增一批 tagId，不存在「掌握 4 个 API 一劳永逸」。「少年 XX」是另一个年度主题系列，7 个标注全部由本地 nid 集合交集 100% 锁定：2022 奇幻冒险 480 / 无限幻想 481，2023 幻想之旅 660 / 奇迹历险 669，2024 幻想校园 722，2025 创想长 747 / 创想短 748（长/短连号同届两赛道）。tagId 按年推进且与秋征交叠；活动页 URL 除两届主题秋征外未逐一实证，清单接口均存活。

### 4. 连续分配与试号实证（部分成立）

**支持「连续分配」**：同届赛项严格连号（653/654/655、702/703/704、752/753/754）；
年度间隔稳定（655→702 = +47、702→752 = +48，每年新增约 47–48 个号，仅 3 个属 X 征）；
跨系列相邻号印证「全年首尾相接」（2024 秋 725 与八征冬 726 紧邻 +1，对应秋征 9-30 与冬征 12 月启动）；
tagId 确是**全局递增编号池**。

**但「不区分什么比赛」不成立**：空档 706–729 几乎连续全有数据，但书目 `categoryID` 混杂（0/1/3/4）、题材各异、定年跨 2024–2026，
号池混着题材/活动标签，靠 `categoryID` 无法区分。鉴别靠**定年聚集度**：征文赛项创建时间集中在赛事窗口（启动后 1–3 周）。

**补全路径（已完整跑通）**：`size=1` 探活 → 定年聚集筛候选 → 用户 App 观测确认。
此前 7 个候选中，699（2024 春征，页面实证）、724（点鸭秋色回忆，用户书名确认）、
725（2024 秋征，用户确认 + UUID 页实证）、772（2025 秋征，页面实证转正）、
774（九征冬征，用户确认 + UUID 页实证）**均已确认**；**最后两个 722、755 也已于 2026-11-22 联网页面实证转正，待观测项清零**：

| tag | 全量本数 | 定年月聚集 | 最终判定（UUID 页 `data-tagid` 实证） |
| --- | --- | --- | --- |
| 722 | 120 | 2024-06:105 / 2024-07:15 | **少年的幻想校园**主题征文（6-21 起），非十二征尾部——定年推断方向对、赛事归属此前不明 |
| 755 | 380 | 2025-06:194 / 2025-07:186 | **奇幻世界**主题征文（6-06 起），非十三征——定年推断命中 |

**找活动页 URL 的新通路（本轮实证）**：本地聚合站 `act.esggi.com` / `nav.esggi.com` 按活动收录页
（如 `/html/page-1846.html`、`page-1966.html`、`page-2046.html`），正文「活动网址」给出**完整 UUID URL**，
搜索引擎按赛事名 + 站域搜到后即可取。722、755、八征冬（726）的 URL 都由这条路补全并用 `data-tagid` 复核。
赛事名/起止日期可从这里取（聚合站元数据），但官方性弱于活动页自身，只作佐证、不作 tagId 真值。

**接口陷阱**：`size` 对部分 tag 有边界（724 用 `size=1/3/8` 正常、`size=500` 返回空 `totalPage=1`），
判空须降 size 重试；早先「706–729 全 active」只说明小 size 下有数据，个别可能是分页边界假象。

## 操作：接口调用与探针

```python
# 新 SPA（推荐，size 大、一页拿全）
GET https://pages.sfacg.com/api/essay/getNovels?tagIds=704&page=1&size=500
# → {"status":{"errorCode":200},"data":{"totalPage":2,"novels":[
#     {"novelID":713638,"categoryID":3,"novelName":"Re：如果成为神明",...}]}}
# 旧 H5（pi 稳定 0 基；ps 可 200）
GET https://pages.sfacg.com/ajax/ashx/Common.ashx?op=getNovelsByTag&tagId=415&ps=200&pi=0
# → {"status":200,"novels":[{"NovelID":277050,...}],"totalPage":...}
```

**限速**：沿用引擎既有抓取限速（分析侧 0.25–0.6s 串行 / 4 并发，无风控迹象）；只取清单元数据、不取正文、不登录。
已固化探针 `analysis/fetchers/probe_contest_roster.py`（端点档案 §7.4 / §11 索引）：

```bash
uv run --project analysis python analysis/fetchers/probe_contest_roster.py \
    --tags 704,703,702 --size 500 --out analysis/out/contest_roster.csv
```

默认 tag 表 = 上文台账 14 个；串行 0.25s、失败即跳过。完整清单存 `analysis/out/contest_roster.csv`（不入库），含 nid/title/author/categoryID/tag。

## 边界与降级

- 清单只覆盖**参加征文**的书；未参赛的一次性完本短篇仍会漏，这条路不是全集。
- `categoryID` 与 `forms` 的 categoryId 判据同源但**不能当 form 真值**（E.28 只正向用 1/4）。
- 早期静态页（四/五征）无清单 API；tagId / 页数是快照，赛事结束后页面可能改版或下线，采集器需支持断点续跑与失效降级。
- 已探 active tag 的具体赛事归属，未确认的一律待用户裁定，不写入正式 tag 台账。

## 交叉引用

- **字段定义与真实例**：`contest-roster-fields.md`（字段权威）、`sfacg-endpoints.md`
- **获奖四代形态与提取正则**：`contest-roster-fields.md`（权威）
- **获奖逐届明细 / 入种口径（净 911、剔除 602、140 补采）**：`award-winners-as-seed-source.md`（权威）
- **规律总览与导航**：`contest-url-api-patterns.md`；**展示设计 / 降级**：`contest-display-in-app.md`
- **赛事日期 / 届次对照**：`analysis/references/contest-editions.md`

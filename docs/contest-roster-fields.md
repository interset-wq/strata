# 征文参赛清单 API：返回字段与获奖存储形态（权威档案，2026-11-21）

> **定位**：征文清单字段与获奖存储形态的权威档案——在 App / DevTools 里核对「接口返回什么字段、获奖名单藏在哪」的依据。
> **状态**：分析侧实测定案；`app/` 冻结，未改数据集/种子。是否解禁 `app/` 仅作工程交接事项，本文不执行。
> **权威范围**：本文唯一维护清单返回字段（名/大小写/取值）与获奖四代形态及提取正则；URL/tagId 见 harvest、逐届获奖见 award，均不复制。
> **口径**：文中计数/比例/日期均为快照现算值，仅供参考、随页面版本变化，禁止硬编码进代码；数字不新增、不外推。
> **更新日期**：2026-11-22（补获奖端点直接探活证据，确认无 REST 获奖接口）。

## 结论

每条参赛作品**只有 6 个字段**：nid、标题、作者、简介、封面、categoryID。
**没有**：字数、收藏、点击、状态、更新时间、上架时间、获奖、名次、赛道中文名、投稿时间。
获奖名单**不在任何接口**，存放形态分四代，提取器须都兼容；`data-nid`/函数参数始终是可靠 nid，奖项名只能尽力解析、不臆造。

## 一、清单字段（权威）

### 1. 新 SPA 接口（2023 起，推荐）

```text
GET https://pages.sfacg.com/api/essay/getNovels?tagIds=704&page=1&size=2
```

**顶层结构**：`{status:{errorCode, msg}, data:{totalPage, novels[]}}`

- `status.errorCode=200`：成功码；`status.msg` 为 `null`。
- `data.totalPage`：总页数（此例 411）。注意本例 `size=2` 时 `totalPage` 仍按 size=2 口径给 411，
  说明它是**服务端按当前 size 算的页数**，别当固定值。
- `data.novels[]`：参赛作品数组，每条 6 字段。

**真实条目**（nid 713638，可在 App 里搜「Re：如果成为神明」核对）：

```json
{
  "novelID": 713638,
  "categoryID": 3,
  "novelName": "Re：如果成为神明",
  "authorName": "某NoName",
  "intro": "14岁的小天才云凪自主动从研究所离职……",
  "cover": "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2024/08/daea837b-bce6-4ca1-98c0-9a945c730a9f.jpg"
}
```

### 2. 旧 H5 接口（2018–2022）

```text
GET https://pages.sfacg.com/ajax/ashx/Common.ashx?op=getNovelsByTag&tagId=415&ps=200&pi=0
```

**顶层结构**：`{status, novels[], totalPage}` —— 注意 `status` 是**裸整数** `200`，没有 `data` 包裹。

**真实条目**（nid 277050，可在 App 里搜「身为反派的我居然有位英雄男友」核对）：

```json
{
  "NovelID": 277050,
  "CategoryID": 0,
  "NovelName": "身为反派的我居然有位英雄男友",
  "AuthorName": "鱼鱼鱼干",
  "Intro": "       成为反派boss之后的和美才发现……",
  "Cover": "2020/09/df267749-ceed-42f9-8fd3-964cc62c149e.jpg"
}
```

### 3. 两套字段对照（大小写不同，语义一一对应）

| 语义 | 新 SPA 字段 | 旧 H5 字段 | 示例值（新/旧） | App 页面上能否看到 |
| --- | --- | --- | --- | --- |
| 作品 id | `novelID` | `NovelID` | 713638 / 277050 | 不显示，但点进详情页 URL 里有 |
| 标题 | `novelName` | `NovelName` | Re：如果成为神明 / 身为反派的我居然有位英雄男友 | 卡片标题 |
| 作者 | `authorName` | `AuthorName` | 某NoName / 鱼鱼鱼干 | 卡片作者名 |
| 作品简介 | `intro` | `Intro` | 一长段正文简介 | 作品详情页简介（**不是作者自述**） |
| 封面 | `cover`（**完整 URL**） | `Cover`（**仅路径片段**） | `https://rs.sfacg.com/...jpg` / `2020/09/....jpg` | 卡片封面图 |
| 分类标记 | `categoryID` | `CategoryID` | 3 / 0 | 不显示（见下文第 3 点） |

**请求参数对照**：新 `tagIds`（复数）+ `page`（**起始随版本变，以页面实际传参为准**）+ `size`（≤500）；
旧 `tagId`（单数）+ `pi`（**稳定 0 基**）+ `ps`（≤200）。
端到端字段定义也与 `sfacg-endpoints.md` 一致。

### 4. 核对时最该注意的三点

1. **`Cover` 两套格式不同**：新接口给**完整 https URL**，旧接口只给**相对路径**（`年月/uuid.jpg`），
   要自己拼 CDN 前缀（如 `https://rs.sfacg.com/web/novel/images/NovelCover/Big/`）。App 里看到的图一样，但字段值不一样。
2. **`intro` 是作品简介**，不是作者 intro——跟作者详情页那段自述是两码事（作者资料走另一条 Web 通路）。
3. **`categoryID` 页面上看不到**，且**不能当 form 真值**：`0` 常规 / `1` 对话 / `3` 征文短篇赛道 / `4` 沉浸式互动。
   E.28 定案只正向用 `1/4` 判 dialogue，`3` 只是赛道标记。清单里新接口多为 `3`（按短篇赛道 tag 拉），旧接口多为 `0`。

### 5. 拿不到、别在 App 里找的字段

清单接口**只返回上面 6 个**。以下在 App 详情页能看到、但接口这里都没有，需另走详情页抓取（`app/docs/05-detail-fetch.md`）：

- 字数、收藏、点击、点赞数
- 连载/完结状态、更新时间、上架时间
- 月票、标签、章节
- 获奖情况、名次：清单接口不给，但**JS 静态 JSON**（webpack 模块，仅 nid+书名）有，见下文第二部分
- 投稿时间、赛道中文名：连活动页 API 也不给，赛道只能靠 tagId 反推

### 6. 一句话使用示例

```python
# 新接口：字段小写；旧接口：首字母大写、status 是裸数字、cover 是路径
GET .../api/essay/getNovels?tagIds=704&page=1&size=500
  → data.novels[0].novelID / novelName / authorName / intro / cover / categoryID
GET .../Common.ashx?op=getNovelsByTag&tagId=415&ps=200&pi=0
  → novels[0].NovelID / NovelName / AuthorName / Intro / Cover / CategoryID
```

## 二、获奖存储四代形态与提取正则（权威）

获奖名单不在任何接口，但存放形态分四代，每代含早期变体，提取器必须都兼容。
逐届 URL / tagId / template 版本台账见 `contest-roster-harvest.md`；逐届获奖 nid、奖项名、收藏与入种口径见 `award-winners-as-seed-source.md`。

### 7. 获奖页 URL 随机串（陷阱）

活动页 JS 写死的 Vue Router path（如 `zw20250504/YiEoewNrQpersdQerQnWin`），**不是动态 token、不是加密、不是每次生成**。

**十二征 `zw20240504` 路由表**（实证，`document.title` 交叉核对）：

| 路径段 | 页面标题 |
| --- | --- |
| `/` | 活动首页 |
| `/mshort`、`/promotion` | 火热进行中 |
| `/ZnrgRrT4c1`、`/ZnrgRrT4c2` | 第十二届初审公布 |
| `/MgioE9QLDwkGE` | 长篇晋级公布 |
| `/PrLpQ3nYiEowN` | 中短篇复审公布 |
| `/Q3PrLponYiEwN` | 中短篇终审公布 |
| `/YiEoewNrQperQerQnWin` | 长篇终审公布 |

**十三征 `zw20250504` 路由表**（实证）：

| 路径段 | 页面标题 |
| --- | --- |
| `/` | 活动首页 |
| `/ZnrgRrT4c1` | 第十三届初审公布（与十二征同一串） |
| `/MgioE9QLDwkGE` | 复审晋级公布（与十二征同一串、标题不同） |
| `/YiEoewNrQpersdQerQnWin` | 中短篇终审公布 |

**字符池固定、语义会漂移**：`PrLpQ3nYiEowN`、`Q3PrLponYiEwN`、`pnerQW3nwNinYiEo` 是同一批字符重排；
`YiEoewNrQperQerQnWin`（十二征长篇终审）与 `YiEoewNrQpersdQerQnWin`（十三征中短篇终审）只差 `sd`——
同一族串含义相反。故**不能硬编码 path→赛道**，每届从 `document.title`（组件 mounted 赋值）或 DevTools 确认。
另注：Vue Router 路由数组里 `meta:{title:...}` 写在**下一条** `path` 前面、实际属于上一条路由，按文本顺序读容易对错页面。

### 8. 第 2 代：JS 静态 JSON（十二/十三征）

获奖名单是 webpack 模块里的静态 JSON：
`"6870":function(e){e.exports=JSON.parse('[{"novelId":"...","novelName":"..."}]')}`。
一条 GET 拿整份 JS 即拿全量名单，无分页、无鉴权，字段仅 `novelId` + `novelName`。
全文件 `url:` 字段只有 `/comments/*`、`/getRank`、`/getTrend`、`/getTaskInfo`、`/getOrnaments`、`/user/access`，
**无任何获奖 HTTP 请求**；`getAwardDataList` 只是 Vue `data` 字段名，不是方法名。
**直接端点探活（2026-11-22）**：对 `/api/essay/{getAward,getAwardList,award,getAwardDataList,getPrize,getWinners}` 及
`Common.ashx?op=getAwardByTag` 逐个请求，全部返回 `No HTTP resource was found` / `parameters fatal error`——
获奖确无 REST 接口，只能从活动页静态数据提取。

**两类陷阱**：① 初审/复审/入围模块（`favs` 中位 4–16）与获奖模块（1112–8372）混在一起，
须按「奖项图标邻域 + favs 跃升」现场判定；② module id 是 webpack hash、跨届会变（十二征 6870 vs 十三征 6666），不能硬编码。
端点路径 `/api/zwYYYYMMDD/` 确实在 JS 里，但那是用户/排行/评论等通用接口前缀，跟获奖无关。
不能把所有静态数组当获奖，否则会把入围书混进优质池。

### 9. 第 3 代：UUID 页 HTML `img[data-nid]`（2024 秋起，六届）

获奖名单写进 HTML `<img data-nid data-categoryid alt>` 标签，连 JS 静态 JSON 都不用了。
获奖区 `<div class="award" data-firstpublictime="...">`，六版同款 4-tab 模板（规则/作品/评论/获奖）、jQuery + template.js：

```html
<!-- 2026 春征 -->
<img data-nid="774528" data-categoryid="0" alt="02金奖.jpg" ...>
<img data-nid="770804" data-categoryid="0" alt="03银奖.jpg" ...>
<!-- 八征冬征：alt 退化为纯数字，奖项名丢失，靠标题图分组 -->
<p><img src="...f576f96a....png" alt="02-min.png" data-href=""></p>  ← 奖项标题图(无 data-nid)
<img data-nid="730611" data-categoryid="0" src="..." alt="03-min.png" ...>  ← 该奖项作品
<p><img src="...c363c80f....png" alt="04-min.png" data-href=""></p>  ← 下一奖项标题图
```

**`data-nid` 始终稳定给 nid（唯一可靠字段）；`alt` 命名法跨届变，不能作为奖项名唯一来源**：
`02金奖.jpg` / `03金奖作品.png` / `02金奖-min.png`（奖项名可读）/
**八征冬退化为纯数字 `03-min.png`（奖项名完全丢失）**。
HTML 结构恢复法：偶数号（02/04/06/10）是被 `<p>` 包裹、无 `data-nid` 的「奖项标题图」，
奇数号（03/05/07…）是紧随其后的获奖作品图；按此恢复档位分组，但**中文奖项名写在标题图图片里、文本拿不到**，
不可凭数量硬套「金银铜推荐」、不可臆造奖项名入种子。
提取器对 `alt` 宽松匹配「奖」字，纯数字则用标题图分组数 + 请用户确认。

### 10. 第 4 代：日期式 Vue SPA render 硬编码 nid（三变体）

获奖 nid 写死在 Vue 组件 render 函数里，三种调用写法提取正则都要兼容：
`openNovel("nid")`（七征冬征，字符串参数）、`showBookDetail(nid)`（六征冬征，数字直接传参）、
`goNovel(nid)`（2024 春征，数字直接传参）。对应正则：
`openNovel\("(\d+)"\)`、`showBookDetail\((\d+)\)`、`goNovel\((\d+)\)`。

分组靠结构恢复：七征冬有 5 张无调用参数的 `announce/N.png` 标题图 + 16 张带 nid 作品图，按规则区名额 1/2/3/6/4 对齐；
六征冬无标题图节点，靠 CSS 绝对定位 `top` 跳变（相邻 ≈3.5rem 同奖项、**>8rem 分界**）恢复 1/2/3/6/4；
2024 春征 16 本按 `reward-box1/2/3/4` 分 3/3/5/5，另 6 张无 nid 标题图。
三者奖项中文名均在图片里、文本拿不到，**只取 nid 为硬数据、不臆造奖项名**。
公示切换点写死在 JS（六征 `2023/04/21`、七征 `2024-04-19 12:00`、春征 `2024/7/7 12:00`），
`isEnd` 由公示时刻决定，未到公示时 tab 显示占位图。

### 11. 四代形态小结与提取器口径

| 代 | 存放形态 | 可靠字段 | 奖项名来源 |
| --- | --- | --- | --- |
| 1 | 早期静态页 | 无 | 无（无获奖名单） |
| 2 | 十二/十三征 JS 静态 JSON | `novelId`/`novelName` | 邻域奖项图标 + favs 跃升，模块 id 跨届变 |
| 3 | UUID 页 HTML `img[data-nid]`（六届，2024 秋起） | `data-nid` | `alt` 尽力解析，纯数字靠标题图分组 |
| 4 | 日期式 Vue render 硬编码（三变体） | 函数参数 nid | 标题图分组 + 规则名额，仅数量模式唯一匹配才用 |

`data-nid`/函数参数始终是可靠 nid；奖项名跨代存放与命名全不同，只能尽力解析、不臆造。
逐届获奖名单与档位明细见 `award-winners-as-seed-source.md`。

## 三、操作：DevTools 判定法（重点）

先按年代认清活动页形态，才知道该搜哪个请求、tagId 藏在哪（URL 实证与已知页面表见 `contest-roster-harvest.md`）：

| 形态 | URL 样式 | 清单接口 | 参赛作品区 |
| --- | --- | --- | --- |
| 早期静态页 | `book.sfacg.com/zwYYYY/` | 无 | 页面内嵌少量链接 |
| H5 活动页（2018–2022） | `pages.sfacg.com/{h5,pc}/act/zwYYYY/`、`/act/djzwYYYY/`（冬季） | 旧 `getNovelsByTag` | JS 顶部 `tagIds` 写死 |
| 日期式 SPA（2023 起） | `pages.sfacg.com/h5/act/zwYYYYMMDD`（可带 `/pc`） | 新 `essay/getNovels`（page 起始随版本变，以页面实际传参为准） | 打包 JS 里 `longTagId/middleTagId/shortTagId`（X 征三轨）或单 `tagId` |
| UUID 页（2024 秋起，春/秋征） | `pages.sfacg.com/h5/act/zw/essayActivity_{UUID}.html` | 新 `essay/getNovels`（page 起始随版本变，以页面实际传参为准） | HTML `data-tagid` 属性；获奖在 HTML `img[data-nid]`（见第 9 节） |

`h5` / `pc` 两条路径多数活动页都有、内容一样；打不开就换另一条试。

### 12. tagId 语义（用户裁定）

**tagId 标识「一届比赛的一个赛项」，不是跨届复用的固定赛道号**：每办一届就新分配一批（十三征长/中/短 = 752/753/754，
与十二征 702/703/704 无复用；单赛项活动如六/七征冬征只有 1 个号）。
**推论**：tagId 无法从「届次 + 赛项名」推导，只能每届从活动页现场取（DevTools 真实请求或页面 JS）；
赛道归属也只能靠 tagId 反推。仍要记住 sandbox / test / pages 三套环境各一批号（十二征短篇 sandbox 533 vs pages 704），取生产值。
完整 tagId 地图与逐届实证见 `contest-roster-harvest.md`（唯一权威）。

### 13. DevTools 判定步骤

1. 打开活动页 → F12 → **Network** → 刷新；若是 SPA 懒加载，**滚动到「参赛作品」区**才触发请求。
2. 过滤请求名：新页搜 `getNovels`（`/api/essay/getNovels`），旧页搜 `getNovelsByTag`（`/ajax/ashx/Common.ashx`）。
3. 看 **Query String 参数**——这是页面**实际用的生产 tagId**，比翻 JS 可靠：
   - 新页：`tagIds=704&page=1&size=500`（复数 `tagIds`、page **起始随版本变，以页面实际传参为准**）；
   - 旧页：`op=getNovelsByTag&tagId=415&ps=200&pi=0`（单数 `tagId`、`pi` 稳定 0 基）。
   - 一个赛事若有长/中/短三条轨，会看到三个不同 tagId 的请求交替出现，按返回作品的 `categoryID` 和赛道标题区分。
4. 看 **Response / Preview** 面板：就是本文第一部分的字段结构（`status` + `novels[]`，新页多一层 `data`）。
5. **不要从打包 JS 里照抄 tagId**：SPA 的 JS 里 sandbox / test / pages 三套环境号并存
   （`i[a] ? i[a] : i.sandboxpages`，`a = location.host.slice(0, indexOf("."))`），只有 `pages` 环境是生产值。
   例：十二征短篇 sandbox 533、生产 704。

## 四、边界与降级

- 清单只覆盖**参加征文**的书；未参赛的一次性完本短篇仍会漏，`categoryID` 不能当 form 真值。
- 早期静态页（四/五征）无清单 API；tagId / 页数为某一时刻快照，赛事结束后页面可能改版或下线，采集器需支持断点续跑与失效降级。
- 获奖四代形态中，奖项名跨代跨届全不同且部分丢失，**只有 nid 是硬数据**；宽松匹配「奖」字在八征冬纯数字 `alt` 上失效，须走 HTML 结构恢复。
- 获奖数据形态与字段口径已定案；是否解禁 `app/` 落地（探针固化、schema v5、专页）仅为工程交接事项，本文不执行。

## 交叉引用

- **端点与参数**：`sfacg-endpoints.md`
- **tagId 地图 / URL 实证 / 已知页面表**：`contest-roster-harvest.md`（唯一权威）
- **获奖逐届明细 / 入种口径（净 911、剔除 602、140 补采、44 可靠/867 待标定）**：`award-winners-as-seed-source.md`（权威）
- **规律总览与导航**：`contest-url-api-patterns.md`
- **展示设计 / 降级**：`contest-display-in-app.md`

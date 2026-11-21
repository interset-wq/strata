# 征文参赛清单 API：返回字段与真实例子（供 App 核对，2026-11-21）

> **用途**：你在 App 里打开征文活动页，对照本文确认「接口返回的每个字段对应页面上什么」。
> **来源**：2026-11-21 各请求 **1 页** 的真实响应（新 SPA `tagIds=704&page=1&size=2`、旧 H5 `tagId=415&ps=200&pi=0`），
> 无登录、无正文。字段定义与陷阱的权威档案是 `docs/sfacg-endpoints.md` §7.4 / `docs/contest-roster-harvest.md`。
> 数字（totalPage 等）为当时快照，仅供参考。

## 0. 一句话结论

**每条参赛作品只有 6 个字段**：nid、标题、作者、简介、封面、categoryID。
**没有**：字数、收藏、点击、状态、更新时间、上架时间、获奖、名次、赛道名、投稿时间——这些清单里都没有。

## 1. 新 SPA 接口（2023 起，推荐）

```text
GET https://pages.sfacg.com/api/essay/getNovels?tagIds=704&page=1&size=2
```

**顶层结构**：`{status:{errorCode, msg}, data:{totalPage, novels[]}}`

- `status.errorCode=200`：成功码；`status.msg` 为 `null`。
- `data.totalPage`：总页数（此例 411，即 `size=500` 下约 20 万条——这是 `tagIds=704` 的返回，
  注意本例 `size=2` 时 `totalPage` 仍按 size=2 口径给 411，说明它是**服务端按当前 size 算的页数**，别当固定值）。
- `data.novels[]`：参赛作品数组，每条 6 字段。

**真实条目（nid 713638，可在 App 里搜「Re：如果成为神明」核对）**：

```json
{
  "novelID": 713638,
  "categoryID": 3,
  "novelName": "Re：如果成为神明",
  "authorName": "某NoName",
  "intro": "14岁的小天才云凪自主动从研究所离职，成了一名光荣的家里蹲之后，已经接近一年时间。\n她原以为在接触过前沿科学之后，世界上便没有任何事物能引起她的兴趣。\n直到那一天，少女敲响了她家的门：\n“让我们来搞一项能改变世界的发明吧！”",
  "cover": "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2024/08/daea837b-bce6-4ca1-98c0-9a945c730a9f.jpg"
}
```

## 2. 旧 H5 接口（2018–2022）

```text
GET https://pages.sfacg.com/ajax/ashx/Common.ashx?op=getNovelsByTag&tagId=415&ps=200&pi=0
```

**顶层结构**：`{status, novels[], totalPage}` —— 注意 `status` 是**裸整数** `200`，没有 `data` 包裹。

**真实条目（nid 277050，可在 App 里搜「身为反派的我居然有位英雄男友」核对）**：

```json
{
  "NovelID": 277050,
  "CategoryID": 0,
  "NovelName": "身为反派的我居然有位英雄男友",
  "AuthorName": "鱼鱼鱼干",
  "Intro": "       成为反派boss之后的和美才发现，那个一直被视为“和平的象征”的NO.1英雄，好像，和自己的男友，有点像？？！\n   （ps：一个少女努力种田变强的故事。）",
  "Cover": "2020/09/df267749-ceed-42f9-8fd3-964cc62c149e.jpg"
}
```

## 3. 两套字段对照（大小写法不同，语义一一对应）

| 语义 | 新 SPA 字段 | 旧 H5 字段 | 示例值（新/旧） | App 页面上能否看到 |
| --- | --- | --- | --- | --- |
| 作品 id | `novelID` | `NovelID` | 713638 / 277050 | ❌ 不显示，但点进详情页 URL 里有 |
| 标题 | `novelName` | `NovelName` | Re：如果成为神明 / 身为反派的我居然有位英雄男友 | ✅ 卡片标题 |
| 作者 | `authorName` | `AuthorName` | 某NoName / 鱼鱼鱼干 | ✅ 卡片作者名 |
| 作品简介 | `intro` | `Intro` | 一长段正文简介 | ✅ 作品详情页简介（**不是作者自述**） |
| 封面 | `cover`（**完整 URL**） | `Cover`（**仅路径片段**） | `https://rs.sfacg.com/...jpg` / `2020/09/....jpg` | ✅ 卡片封面图 |
| 分类标记 | `categoryID` | `CategoryID` | 3 / 0 | ❌ 不显示（见 §5） |

**请求参数对照**：新 `tagIds`（复数）+ `page` **从 1 起** + `size`（≤500）；旧 `tagId`（单数）+ `pi` **从 0 起** + `ps`（≤200）。

## 4. 你核对时最该注意的三点

1. **`Cover` 两套格式不同**：新接口给**完整 https URL**，旧接口只给**相对路径**（`年月/uuid.jpg`），
   要自己拼 CDN 前缀（如 `https://rs.sfacg.com/web/novel/images/NovelCover/Big/`）。App 里看到的图一样，但字段值不一样。
2. **`intro` 是作品简介**，不是作者 intro——跟作者详情页那段自述是两码事（作者资料走另一条 Web 通路）。
3. **`categoryID` 页面上看不到**，且**不能当 form 真值**：`0` 常规 / `1` 对话 / `3` 征文短篇赛道 / `4` 沉浸式互动。
   E.28 定案只正向用 `1/4` 判 dialogue，`3` 只是赛道标记。清单里新接口多为 `3`（因为按短篇赛道 tag 拉），
   旧接口多为 `0`。

## 5. 拿不到、别在 App 里找的字段

清单接口**只返回上面 6 个**。以下你在 App 详情页能看到的，接口这里都没有，需要另走详情页抓取（`app/docs/05-detail-fetch.md`）：

- 字数、收藏、点击、点赞数
- 连载/完结状态、更新时间、上架时间
- 月票、标签、章节
- 获奖情况、名次：清单接口不给，但**活动页 JS 静态 JSON** 有（`/js/index.<hash>.js` 内 webpack 模块，仅 nid+书名，见 §8.4 与 `award-winners-as-seed-source.md`）
- 投稿时间、赛道中文名：连活动页 API 也不给，赛道只能靠 tagId 反推

## 6. 一句话使用示例

```python
# 新接口：一页一条，字段小写；旧接口：首字母大写、status 是裸数字、cover 是路径
GET .../api/essay/getNovels?tagIds=704&page=1&size=500
  → data.novels[0].novelID / novelName / authorName / intro / cover / categoryID

GET .../Common.ashx?op=getNovelsByTag&tagId=415&ps=200&pi=0
  → novels[0].NovelID / NovelName / AuthorName / Intro / Cover / CategoryID
```

> 已用一次性脚本 `temp/probe_roster_sample.py` 抓取（临时文件、不入库）；复核端点定义看权威档案 §7.4。

## 7. 征文活动页 URL（DevTools 核对用）

> 下表 URL 来自 `docs/contest-roster-harvest.md` §1/§2 与 `analysis/references/contest-editions.md` 的实测档案，
> **不是本轮重新验证的**；活动页可能改版/下线。你要做的就是在 DevTools 里确认它们现在还能不能打开、
> 实际请求用的是哪个 tagId。

### 7.0 tagId 的语义（用户裁定 2026-11-21）

**tagId 标识的是「一届比赛的一个赛项」，不是跨届复用的固定赛道号。**

- **每办一届比赛，就新分配一批 tagId**：赛项有几个，就新增几个。十三征文有长/中/短篇 3 个赛项，
  就对应 3 个全新 tagId（752/753/754）；十二征的 702/703/704 与它**毫无复用关系**，是上一届的另一批号。
- 同理，一征冬征、二征冬征这种单赛项活动只有 1 个 tagId（381、406）；七征 5 个赛项就是 5 个号（408–412）。
- **推论（关键）**：tagId 无法从「届次 + 赛项名」推导，**只能每届从活动页现场取**（DevTools 真实请求或页面 JS）。
  这就是 tagId 地图永远追不齐、会随新比赛不断膨胀的根因——不是我们没采全，而是**它本来就是每次新增的一次性编号**。
- 赛道归属也只能靠 tagId 反推（这个 tagId 是哪个活动页的、对应长/中/短哪个赛项），不能只看号本身。
- 仍要记住 sandbox / test / pages 三套环境各一批号（十二征短篇 sandbox 533 vs 生产 704），取生产值。

### 7.1 三类 URL 形态（按年代）

| 形态 | URL 样式 | 清单接口 | 参赛作品区 |
| --- | --- | --- | --- |
| 早期静态页 | `book.sfacg.com/zwYYYY/` | **无** | 页面内嵌少量链接 |
| H5 活动页（2018–2022） | `pages.sfacg.com/{h5,pc}/act/zwYYYY/`、`/act/djzwYYYY/`（冬季） | 旧 `getNovelsByTag` | JS 里 `tagIds` 写死在顶部 |
| SPA 活动页（2023–2025） | `pages.sfacg.com/h5/act/zwYYYYMMDD`（可带 `/pc`） | 新 `essay/getNovels`（page **0 基**） | 打包 JS 里 `longTagId/middleTagId/shotTagId`（X 征三轨）或单 `tagId`（七征冬征，§7.2） |
| UUID 页（2025 起，春/秋征） | `pages.sfacg.com/h5/act/zw/essayActivity_{UUID}.html` | 新 `essay/getNovels`（page **0 基**） | HTML `data-tagid` 属性；获奖名单也在 HTML `img[data-nid]`（`§8.5`）。技术栈是 **jQuery + `template.js?v=`**，非 Vue |

### 7.2 已知具体页面（可直接打开试）

| 赛事 | 活动页 URL | tagId（长/中/短或单轨） | 接口 |
| --- | --- | --- | --- |
| 四征 | `https://book.sfacg.com/zw2016/rule.html`（规则页有精确日期） | — | 无 |
| 五征 | `https://book.sfacg.com/zw2017/` | — | 无 |
| 六征 | `https://pages.sfacg.com/h5/act/zw2018/` | — | 无 |
| 一征冬征 | `https://pages.sfacg.com/h5/act/djzw2018/` | 381 | 旧 |
| 二征冬征 | `https://pages.sfacg.com/h5/act/djzw2019/` | 406 | 旧 |
| 七征 | `https://pages.sfacg.com/h5/act/zw2019/` | 408/409/410/411/412 | 旧 |
| 三征冬征 | `https://pages.sfacg.com/h5/act/djzw2020/` | 415 | 旧 |
| 八征 | `https://pages.sfacg.com/h5/act/zw2020/` | 418 | 旧 |
| 四征冬征 | `https://pages.sfacg.com/pc/act/djzw2021/` | 454 | 旧 |
| 五征冬征 | `https://pages.sfacg.com/h5/act/djzw2022/` | 466 | 旧 |
| **六征冬征** | `https://pages.sfacg.com/h5/act/zw20221205/`（**日期式 SPA**） | **485**（单轨，写死在组件 data） | 新，page **0 基**；获奖 16 本写死在 Vue render（`showBookDetail(数字)`，§8.7）；公示 2023-04-21 |
| **七征冬征** | `https://pages.sfacg.com/h5/act/zw20231204/`（**日期式 SPA，非 UUID、非 `djzwYYYY`**） | **692**（单轨） | 新，page **0 基**；获奖 16 本写死在 Vue render 函数（§8.6）；公示 2024-04-19 |
| 十一征 | `https://pages.sfacg.com/h5/act/zw20230504/pc` | 653/654/655 | 新 |
| 十二征 | `https://pages.sfacg.com/h5/act/zw20240504/pc` | 702/703/704 | 新 |
| 十三征 | `https://pages.sfacg.com/h5/act/zw20250504/pc` | 752/753/754 | 新 |
| **2024 春征** | `https://pages.sfacg.com/h5/act/zw20240301/`（**日期式 SPA，非 UUID**） | **699**（`f121` 三环境：sandbox 530 / test·pages 699） | 新，page 0 基；获奖 16 本写死在 Vue render（`goNovel(数字)`，§8.8）；公示 2024-07-07 |
| 2026 春征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_52f25c52-1de0-4608-90fc-293aac35a588.html` | **789**（HTML `data-tagid`） | 新，page 0 基；获奖公示 2026-07-10 |
| **2025 春征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_d892261b-8719-4e3b-b01a-b84278b2996b.html` | **746**（HTML `data-tagid`） | 新，page 0 基；获奖公示 2025-07-11；template.js `v=42327` |
| **2024 秋征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_0a10b388-bf92-410c-801a-59c91b853c3f.html` | **725**（HTML `data-tagid`，试号转正） | 新，page 0 基；获奖 11 本 `img[data-nid]`、`alt` 中文奖项名完整；公示 2025-02-14 |
| **2025 秋征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_d568a583-bde8-4f16-809a-8ab7097261be.html` | **772**（HTML `data-tagid`，试号转正） | 新，page 0 基；获奖公示 2026-02-13；template.js `v=83885` |
| **八征冬征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_c49534b9-73b2-46c9-a33f-b8144b448662.html` | **726**（HTML `data-tagid`） | 新，page 0 基；获奖公示 2025-04-25；template.js `v=42945` |
| **九征冬征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_373481c3-8fb0-4113-83fb-5058a816f828.html` | **774**（HTML `data-tagid`，试号转正） | 新，page 0 基；获奖 10 本 `img[data-nid]`、`alt` 中文奖项名完整（金1/银1/铜3/推荐5）；公示 2026-05-15；template.js `v=94362` |
| 点鸭秋色回忆 | URL 未取到（对话线）；tag 由试号确认 | **724** | 新 |

`h5` / `pc` 两条路径多数活动页都有，内容一样（H5 页用 `h5`，档案里四征冬征是 `pc`）；打不开就换另一条试。
**UUID 页从 2024 秋征才启用**（`essayActivity_{UUID}.html`，已实证 2024 秋 / 2025 春 / 2025 秋 / 2026 春 / 八征冬 / 九征冬共六版）——UUID 无法从届次推导，
只能从 App 入口拿。六版是**同一套模板**（都 4 个 tab：规则/作品/评论/获奖，都是 jQuery + `template.js`），
只是 `template.js?v=` 版本号不同（2024 秋 `27868` / 八征冬 `42945` / 2025 春 `42327` / 2025 秋 `83885` / 2026 春 `62767` / 九征冬 `94362`）。
**2024 春征（3-01）仍是日期式 Vue SPA**（`zw20240301`，tag 699），是「春征旧届空白」里补到的第一届——
即「UUID 页起点 = 2024 秋征」，春征旧届（2024-03）比秋征早半年、仍是日期式 Vue SPA，勿写「2024 起都用 UUID」。
**冬征 URL 演进补上全部缺口**：一~五征用 `djzwYYYY`；
**六征(2022-12) `zw20221205`、七征(2023-12) `zw20231204` 是两代日期式 SPA**；八征起换 UUID 页。
即「冬征从第八届起换 UUID 页」成立，但 `djzwYYYY` 与 UUID 页之间夹了两代日期式 SPA（六、七征均已实证）。
两代都是**单轨** tagId（485 / 692，无长/中/短拆分），与 X 征三轨不同；又是同套模板的早/晚期变体：
六征 tagId 写死组件 data、获奖 `showBookDetail(数字)`；七征 tagId 分三环境、获奖 `openNovel("字符串")`（§8.6/§8.7）。

**技术栈澄清**：`zwYYYYMMDD/pc` 的 X 征 SPA 用 Vue Router（获奖页随机串即写死路由，§8.3）；
而 UUID 页用 **jQuery + template.js**（本轮下载 `template.js?v=42327` 全文无任何 Vue 痕迹）。
「网站近年大量用 Vue」只对 X 征 SPA 那套成立，不要据此推 UUID 页的 DOM/路由行为。

### 7.3 DevTools 怎么判定（重点）

1. 打开活动页 → F12 → **Network** → 刷新；若是 SPA 懒加载，**滚动到「参赛作品」区**才触发请求。
2. 过滤请求名：新页搜 `getNovels`（`/api/essay/getNovels`），旧页搜 `getNovelsByTag`（`/ajax/ashx/Common.ashx`）。
3. 看 **Query String 参数**——这是页面**实际用的生产 tagId**，比翻 JS 可靠：
   - 新页：`tagIds=704&page=1&size=500`（复数 `tagIds`、page 从 1 起）；
   - 旧页：`op=getNovelsByTag&tagId=415&ps=200&pi=0`（单数 `tagId`、pi 从 0 起）。
   - 一个赛事若有长/中/短三条轨，会看到三个不同 tagId 的请求交替出现，按返回作品的 `categoryID` 和赛道标题区分。
4. 看 **Response / Preview** 面板：就是本文 §1–§3 的字段结构（`status` + `novels[]`，新页多一层 `data`）。
5. **不要从打包 JS 里照抄 tagId**：SPA 的 JS 里 sandbox / test / pages 三套环境号并存（`i[a] ? i[a] : i.sandboxpages`，
   `a = location.host.slice(0, indexOf("."))`），只有 `pages` 环境是生产值。DevTools 里看真实请求最稳。
   例：十二征短篇 sandbox 是 533、生产是 704。

你在 App 里核对字段（§1–§5）和这里 DevTools 判 tagId 是两件配套的事：前者定「返回什么」，后者定「用哪个 tagId 拉哪个赛道」。

## 8. 获奖页 URL 里的随机串（实证 2026-11-21）

> 起因：用户给出 `https://pages.sfacg.com/h5/act/zw20250504/YiEoewNrQpersdQerQnWin`，
> 问路径末尾那串是什么、怎么生成的。抓活动页 JS（`zw20250504/js/index.d34358c7.js`、
> `zw20240504/js/index.820980da.js`）后确认：**它是活动页 JS 里写死的 Vue Router path，
> 不是动态 token、不是加密、不是每次生成**。

### 8.1 十二征 `zw20240504` 路由表（实证）

| 路径段 | 页面标题（`document.title`） | 说明 |
| --- | --- | --- |
| `/` | — | 活动首页 |
| `/mshort`、`/promotion` | 火热进行中 | 宣传/短篇入口 |
| `/ZnrgRrT4c1`、`/ZnrgRrT4c2` | 第十二届初审公布 | 两个入口指向同一类初审页 |
| `/MgioE9QLDwkGE` | 长篇晋级公布 | |
| `/PrLpQ3nYiEowN` | 中短篇复审公布 | |
| **`/Q3PrLponYiEwN`** | **中短篇终审公布** | ← 你给的 URL 1 |
| **`/YiEoewNrQperQerQnWin`** | **长篇终审公布** | ← 你给的 URL 2 |

### 8.2 十三征 `zw20250504` 路由表（实证）

| 路径段 | 页面标题 | 说明 |
| --- | --- | --- |
| `/` | — | 活动首页 |
| `/ZnrgRrT4c1` | 第十三届初审公布 | 与十二征**同一串** |
| `/MgioE9QLDwkGE` | 复审晋级公布 | 与十二征**同一串**，但标题不同 |
| **`/YiEoewNrQpersdQerQnWin`** | **中短篇终审公布** | ← 你最早给的那个 URL |

### 8.3 「固定」这个判断——字符池固定，语义会漂移（关键陷阱）

你说「序列似乎是固定的」，从字符来源看确实有复用规律：

- **同一套混淆字符池反复重排/微调**：`PrLpQ3nYiEowN`、`Q3PrLponYiEwN`、`pnerQW3nwNinYiEo`
  是同一批字符 `P r L p Q 3 n Y i E o w N` 的排列；`YiEoewNrQperQerQnWin`（十二征）
  与 `YiEoewNrQpersdQerQnWin`（十三征）只差中间插入的 `sd`。
- 部分路径**跨届完全复用**：`/ZnrgRrT4c1`（初审）、`/MgioE9QLDwkGE`（晋级/复审）。

但**不能据此把 path 当成稳定的语义标识**——它是每届前端自己排的，语义会漂移：

> 最强反例：`YiEoewNrQperQerQnWin` 在十二征是**长篇终审**，
> 而几乎一样的 `YiEoewNrQpersdQerQnWin` 在十三征是**中短篇终审**——同一族串，含义相反。
> `/MgioE9QLDwkGE` 十二征是「长篇晋级」、十三征是「复审晋级」，也不完全一致。

这正是你说的「有些比赛分别公布中短篇和长篇」的实现方式：十二征把**长篇终审**和**中短篇终审**
拆成两条独立路由（你给的正是这两条），十三征则只有一条中短篇终审路由。

**产品结论**：不要硬编码 path→赛道 的映射；每届只能从**页面 `document.title`**（终审组件在 `mounted`
里赋值）或 DevTools 现场确认。这是 tagId 之外第二类「每届现场取」的动态标识。

> 提醒：Vue Router 路由数组里 `meta:{title:...}` 写在**下一条** `path` 前面，实际属于**上一条**路由，
> 直接照着文本顺序读容易对错页面。上表已按组件 `mounted` 里的 `document.title` 交叉核对。

### 8.4 顺带修正：获奖名单并非「无来源」，且不是 API 而是**JS 静态 JSON**

此前档案记「获奖名单无数据源」，后又猜是「活动页私有 API `/api/zwYYYYMMDD/getAwardDataList`」——
**本轮实证两者都不准**。抓两届活动页 JS（`zw20240504/js/index.820980da.js`、`zw20250504/js/index.d34358c7.js`）
逐行核对：

- 全文件 `url:` 字段只有 `/comments/*`、`/getRank`、`/getTrend`、`/getTaskInfo`、`/getOrnaments`、`/user/access`，
  **没有任何获奖相关 HTTP 请求**。`getAwardDataList` 只是 Vue `data` 里的字段名，不是方法名——之前误读了。
- 获奖名单是 **webpack 模块里的静态 JSON**：形如 `"6870":function(e){e.exports=JSON.parse('[{"novelId":"...","novelName":"..."}]')}`。
  一条 GET 拿到整份 JS 就拿到全部名单，无分页、无鉴权、字段仅 `novelId` + `novelName`。
- 名单按**阶段和奖项**拆成多个模块，**不是每组都是获奖**：模块 `2110/7926/7783` 绑在
  「初审/复审公布」页（favs 中位 4–16，与全站持平，是入围展示）；模块 `6870/6666/f3e3`（金/银/铜奖图标）
  才是终审获奖名单（favs 中位 1112–8372，见 `docs/award-winners-as-seed-source.md`）。
  **不能把所有静态数组当获奖**，否则会把入围书混进优质池。
- 端点路径 `/api/zwYYYYMMDD/` 确实在 JS 里，但那是用户/排行/评论等通用接口的前缀，跟获奖无关。

影响：`contest-display-in-app.md` 里「来源为活动页私有 API、待 DevTools 核对」应改为
「来源为活动页 JS 静态 JSON（已实证），但每届模块 id 与奖项映射需现场取」。

### 8.5 第三代形态：UUID 页把获奖名单写进 HTML `<img data-nid>`（实证 2026-11-21）

用户先后给出六届活动页（**2024 秋征** / 2025 春 / 2025 秋 / 2026 春 / 八征冬 / **九征冬**），**同款 4-tab 模板**（规则/作品/评论/获奖）：

| 赛事 | URL | tagId | 获奖公示 | template.js 版本 | 获奖数 | alt 格式 |
| --- | --- | --- | --- | --- | --- | --- |
| **2024 秋征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_0a10b388-bf92-410c-801a-59c91b853c3f.html` | **725**（试号转正） | 2025-02-14 | `v=27868` | 11 | `02金奖-min.png`（奖项名完整） |
| 八征冬征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_c49534b9-73b2-46c9-a33f-b8144b448662.html` | 726 | 2025-04-25 | `v=42945` | 10 | **纯数字 `03-min.png`（奖项名丢失）** |
| 2025 春征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_d892261b-8719-4e3b-b01a-b84278b2996b.html` | 746 | 2025-07-11 | `v=42327` | 10 | `02金奖.jpg` |
| 2025 秋征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_d568a583-bde8-4f16-809a-8ab7097261be.html` | 772 | 2026-02-13 | `v=83885` | 7 | `03金奖作品.png` |
| 2026 春征 | `https://pages.sfacg.com/h5/act/zw/essayActivity_52f25c52-1de0-4608-90fc-293aac35a588.html` | 789 | 2026-07-10 | `v=62767` | 6 | `02金奖.jpg` |
| **九征冬征** | `https://pages.sfacg.com/h5/act/zw/essayActivity_373481c3-8fb0-4113-83fb-5058a816f828.html` | **774**（试号转正） | 2026-05-15 | `v=94362` | 10 | `02金奖.png`（奖项名完整） |

六版**只有 UUID、template.js 版本号、档位数、alt 命名法不同**，结构主体一致。有几个结构性变化：

1. **URL 形态换了**：不再是 `zwYYYYMMDD`，而是 `zw/essayActivity_{UUID}.html`。
   这正是春征/秋征一直找不到 URL 的原因——它们用的不是旧的日期式路径。
   UUID 页无法从届次推导，只能靠用户 App 提供入口。**2025 就已是 UUID 页**（不是 2026 才开始）。

2. **获奖名单存放换到第 3 种形态：HTML 里的 `<img data-nid data-categoryid alt>` 标签**，
   连 JS 静态 JSON 都不用了。获奖区 `<div class="award" data-firstpublictime="...">`：

   ```html
   <!-- 2026 春征 -->
   <img data-nid="774528" data-categoryid="0" alt="02金奖.jpg" ...>
   <img data-nid="770804" data-categoryid="0" alt="03银奖.jpg" ...>
   <img data-nid="772261" data-categoryid="0" alt="04铜奖.jpg" ...>
   <img data-nid="771720" data-categoryid="0" alt="05新人奖1(1).jpg" ...>
   ...
   <!-- 2025 春征（档位更全：金/银/铜×3/推荐奖×5，共 10 本）-->
   <img data-nid="738162" data-categoryid="0" alt="02金奖.jpg" ...>
   <img data-nid="740593" data-categoryid="0" alt="03银奖.jpg" ...>
   <img data-nid="737435" data-categoryid="0" alt="04铜奖1.jpg" ...>
   <img data-nid="739670" data-categoryid="0" alt="05推荐奖1.jpg" ...>
   ...
   <!-- 2025 秋征（金/银/铜×2/新人×3，共 7 本；alt 带"作品"后缀 + .png）-->
   <img data-nid="759314" data-categoryid="0" alt="03金奖作品.png" ...>
   <img data-nid="760079" data-categoryid="0" alt="05银奖作品.png" ...>
   <img data-nid="762215" data-categoryid="0" alt="07铜奖作品1.png" ...>
   ...
   <!-- 八征冬征（10 本；alt 退化为纯数字，奖项名丢失，靠标题图分组推断）-->
   <p><img src="...f576f96a....png" alt="02-min.png" data-href=""></p>  ← 奖项标题图(无 data-nid)
   <img data-nid="730611" data-categoryid="0" src="..." alt="03-min.png" ...>  ← 该奖项作品
   <p><img src="...c363c80f....png" alt="04-min.png" data-href=""></p>  ← 下一奖项标题图
   <img data-nid="731325" data-categoryid="0" src="..." alt="05-min.png" ...>
   ...
   ```

   **`data-nid` 始终稳定给 nid**（这是唯一可靠的字段）；但 **`alt` 命名法跨届变，不能作为奖项名的唯一来源**：
   - 2025 春 `02金奖.jpg`、2025 秋 `03金奖作品.png`、2026 春 `02金奖.jpg`——`alt` 含中文奖项名；
   - **八征冬征 `alt` 退化为纯数字 `03-min.png`，奖项名完全丢失**，宽松匹配「奖」字的策略在这届会失效。
     它的奖项分组靠 HTML 结构恢复：**偶数号（02/04/06/10）是被 `<p>` 包裹、无 `data-nid` 的「奖项标题图」，
     奇数号（03/05/07…）是紧随其后的获奖作品图（有 `data-nid`）**。按此结构，八征冬征 10 本分 4 档：
     02→[03]（1 本）、04→[05]（1 本）、06→[07/08/09]（3 本）、10→[11/12/13/14/15]（5 本）——
     数量模式与 2025 春征（金1/银1/铜3/推荐5）一致，但**奖项中文名写在标题图图片里、HTML 文本拿不到**，
     只能靠用户看图片或 DevTools，不要凭数量硬套「金银铜推荐」。
   - **结论**：提取器只把 `data-nid` 当硬数据（获奖书 nid 集合可靠）；奖项名/档位作「尽力解析」——
     alt 有中文就用，纯数字则用标题图分组数 + 请用户确认，**绝不臆造奖项名入种子**。
   - 2025 春征 10 本（金 738162 / 银 740593 / 铜×3 / 推荐奖×5），全在库，定年 2025-02~04，收藏 8,702–27,131。
   - **2024 秋征 11 本**，全在库（contest=2024秋季征文，收藏 8,559–33,198），`alt` 中文奖项名完整、直接可读：
     金 720699 / 银 721779 / 铜 727388·724273·720532 / 推荐 722484·723128·722600 / 星火 726385·724040·724589
     （金1/银1/铜3/推荐3/星火3；**「星火奖」是此前四版未见的新奖项名**）。星火 726385 出现在 tag 725 清单第 1 页，可交叉核对。
   - 2025 秋征 7 本（金 759314 / 银 760079 / 铜 762215·759671 / 新人×3），全在库，定年 2025-10~11，收藏 5,986–20,189。
   - 2026 春征 6 本（金/银/铜/新人奖×3），全在库，定年 2026-02~04，金奖收藏仅 40。
   - **九征冬征 10 本**，全在库（contest=第九届冬季征文，收藏 6,190–18,562），`alt` 中文奖项名完整：
     金 765752 / 银 765742 / 铜 765405·764263·767807 / 推荐 764973·769788·767294·768408·766171
     （金1/银1/铜3/推荐5，与 2025 春征同档位结构）。推荐 767294「当妈的我才不要养成病娇女」出现在 tag 774 清单第 1 页，可交叉核对。
   - 八征冬征 10 本，9 本在库（定年 2024-12~2025-01 冬征窗口，收藏 8,710–80,830，信号极强），
     **1 本（nid 731965）不在 universe——可作补种候选**。
   六届共同说明「获奖≠高收藏不可一概而论」，按届看数据。

3. **参赛清单仍是新接口**：`/api/essay/getNovels`，但 **tagId 写在 HTML `data-tagid` 属性**（不是 JS 变量），
   `page` 是 **0 基**（与旧记录「新接口 1 基」不同，接口行为随版本变，按页面实际传参为准）。
   - 2026 春征 tag **789**，size=9 时 totalPage=187（约 1,683 本）；
   - **2024 秋征 tag 725**（试号转正），size=9 时 totalPage=198（约 1,782 本），已实测 errorCode=200。
   - 八征冬征 tag **726**，size=9 时 totalPage=307（约 2,763 本），已实测 errorCode=200。
   - 2025 春征 tag **746**，size=9 时 totalPage=190（约 1,710 本），已实测 errorCode=200。
   - 2025 秋征 tag **772**，size=9 时 totalPage=205（约 1,845 本），已实测 errorCode=200。
   - **九征冬征 tag 774**（试号转正），size=9 时 totalPage=260（约 2,340 本），已实测 errorCode=200。
   六者符合「全局递增、每届新增」，按时间自洽：**2024 秋 725（9 月）< 八征冬 726（12 月）** < 2025 春 746（3 月）
   < 十三征 752（5 月）< 2025 秋 772（9 月）< **九征冬 774（12 月）** < 2026 春 789。
   **772 / 725 / 774 均由试号推断转正为页面实证**（九征冬征明细见本节台账表与清单）。

4. **技术栈澄清**：这六版 UUID 页用的是 **jQuery + `template.js?v=`**（本轮下载 `template.js?v=42327`
   全文无任何 Vue 痕迹），与 `zwYYYYMMDD/pc` 的 X 征 Vue SPA 是两套。模板版本跨届递增但非严格：
   2024 秋 `27868` < 八征冬 `42945` ≈ 2025 春 `42327` < 2026 春 `62767` < 2025 秋 `83885` < 九征冬 `94362`。
   用户观察「网站近年大量用 Vue」只对 X 征 SPA 那套成立，不要据此推 UUID 页的 DOM/路由行为。

### 8.6 第四代形态：日期式 Vue SPA 把获奖 nid 写死在 render 函数（七征冬征实证 2026-11-21）

用户给出 `https://pages.sfacg.com/h5/act/zw20231204/`，标题 **菠萝包轻小说第七届冬季征文**
（页面 JS 内 `baseUrl:"/api/zw20231204"`、`cmtId:3526`；规则区写明征稿 12-04 12:00 起、公示 2024-04-19 12:00，
`updateTabByTime` 里也硬编码 `new Date("2024/04/19 12:00:00")` 作切换获奖 tab 的时间点）。
这是**冬征序列里首次拿到的第七届页面**，填补了 `contest-roster-harvest.md` §2.1 里「冬征缺六/七届」的七征。

**token 位置（与 UUID 页相反）**：tagId 写在**打包 JS** 里（`js/index.31270778.js` 的 webpack 模块 `f121`），
不在 HTML `data-tagid`；这是日期式 SPA 的做法。生产 `pages` 环境 `tagId:692`（单轨），
`testpages:692`，`sandboxpages:523`——取生产值 692。清单接口仍是新 `essay/getNovels`，
页面代码 `getNovels` 传 `t.page`（初值 **0**）+ `t.$config.tagId` + `size:9`，**page 0 基**。
实测 `tagIds=692&page=0&size=9` → `errorCode=200`、`totalPage=336`（约 3,024 本）、9 条全 `categoryID=0`。
页面用 Vue（`chunk-vendors` + `index.js`、Vue Router），与 UUID 页的 jQuery + template.js 是两套。

**获奖名单是第四种存放形态——Vue 组件 render 函数里硬编码 `openNovel("nid")`**：

- 既不是「JS 静态 JSON 模块」（§8.4 十二/十三征），也不是「HTML `img[data-nid]`」（§8.5 UUID 页），
  而是 `Announce` 组件的 render 函数 `V=function(){...}` 里一串
  `o("div",{staticClass:"item",on:{click:function(e){return t.openNovel("677177")}}},[o("img",{...announce/2.png})])`。
  **nid 就在 `openNovel("...")` 的字符串参数里**；配套的 `announce/N.png`（N=1..21）是图片素材文件名，
  只有 `1/3/6/10/17.png` 这 5 张**无 `openNovel`（奖项标题图）**，其余 16 张带 nid。
- 时间开关：`isEnd` 由公示时刻决定，未到公示时该 tab 显示「公布时间」占位图，到了才渲染 `<Announce>`。

**分组靠结构恢复，且这届能定奖项名**（不像八征冬征纯数字 alt 丢失）：规则区文本写死名额
「金奖 1 / 银奖 2 / 铜奖 3 / 编辑推荐奖 6 / 优秀题材奖 4」，与图片的 5 段分组数量 **1/2/3/6/4 完全吻合**，
按标题图顺序对号入座即可。16 本（全部 nid，定年窗口与七征冬征主体簇 678,346–686,575 一致）：

| 奖项（按名额对齐） | nid | 数量 |
| --- | --- | --- |
| 金奖 | 677177 | 1 |
| 银奖 | 681052、689388 | 2 |
| 铜奖 | 679145、681376、682171 | 3 |
| 编辑推荐奖 | 684584、681010、684035、678022、677327、680606 | 6 |
| 优秀题材奖 | 683850、683372、684254、679603 | 4 |

（例：678022「主角的道侣都归我咯」就在 tag 692 清单第 1 页，可交叉核对。）

**提取器影响**：第四代需在 Vue 打包 JS 里匹配 `openNovel\("(\d+)"\)` 拿 nid，
奖项名这届靠规则区名额对齐（数量模式唯一匹配才用，否则只取 nid 不臆造）。
已核对这 16 本全在 universe、收藏 1.2 万–6.9 万（真获奖），明细见 `analysis/out/contest_award_winners.csv`。

### 8.7 第四代的早期变体：六征冬征 `zw20221205`（2026-11-21 实证）

用户给出 `https://pages.sfacg.com/h5/act/zw20221205/`，标题 **菠萝包轻小说第六届冬季征文**。
这是冬征序列**最后一个缺口**（补齐后冬征一~九届 URL/tag 全有），主体簇定年 2023-01（2022-12 启动）。
同为日期式 Vue SPA + 获奖写死在 render 函数（故属第四代），但有三处与七征不同：

1. **tagId 写死在组件 `data`**：`index.dfce9b2d.js` 里 `tagId:485`（单轨），
   **没有** sandbox/test/pages 三套环境配置（七征有）——早期模板更简单。实测 `tagIds=485&page=0&size=9`
   → `errorCode=200`、`totalPage=411`（约 3,699 本）、cat=0。清单端点同为 `/api/essay/getNovels`（页面里 baseURL `/api/essay` + `/getNovels`，page 0 基）。
   该 tag 无 size 边界陷阱：`size=500` 时 `totalPage=8`（约数一致），可整批拉全清单。
2. **获奖调用名不同**：不是 `openNovel("nid")`，而是 **`showBookDetail(619932)`（数字直接传参，无引号）**；
   提取正则要兼容 `showBookDetail\((\d+)\)`。16 本都在一个 `staticClass:"awards"` 块里，
   是 16 个可点击 `<div class="itemN item">`（N=1..16），**没有内嵌的标题图节点**——
   奖项名写在 3 张背景图（`img1/img2/img3`）里，JS 文本拿不到。
3. **分组靠 CSS 定位恢复**：`index.4942aa90.css` 里每个 item 有绝对定位 `top`（rem），
   相邻间距 ≈3.5rem 表示同奖项，**>8rem 的跳变表示奖项分界**。据此分为
   `item1 / item2-3 / item4-6 / item7-12 / item13-16` = **1/2/3/6/4**，
   与七征、规则惯例的金1/银2/铜3/编推6/优题4 一致；但**这是布局推断，奖项名不可臆造入种子**
   （无文本证据），只取 nid 为硬数据。公示切换点写死 `Date.parse("2023/04/21")`（`isEnd` 判断）。
4. 数据：16 本中 **15 本在 universe**（金 619932 收藏 7.6 万、编推 614827 收藏 7.7 万但 `contest` 字段空，
   疑旧书参赛）；**1 本 625069「转生魔王，但其实是个卧底？」不在 universe，可作补种候选**
   （书名从 tag 485 清单第 1 页取到）。明细见 `contest_award_winners.csv`。

### 8.8 第四代的另一变体：2024 春征 `zw20240301`（2026-11-21 实证）

用户给出 `https://pages.sfacg.com/h5/act/zw20240301/`，标题 **菠萝包轻小说2024春季征文**。
这是「春征旧届空白」补到的第一届，也是**证明 UUID 页不是 2024 全场通用**的关键样本：
2024 春征（3-01）仍是**日期式 Vue SPA**（`zwYYYYMMDD`），UUID 页要到 2024 秋征才启用。

1. **tagId = 699**，`f121` 模块三环境配置：sandbox 530 / test 699 / **pages 699**（生产值）；
   `baseUrl=/api/zw20240301`、`cmtId=3571`。实测 `tagIds=699&page=0&size=9` → `errorCode=200`、
   `totalPage=247`（约 2,223 本）、cat=0，清单端点同为 `/api/essay/getNovels`。
   **注意 699 早年曾在三环境配置里以 test 值出现、未挂赛事**，本页实证它同时是 2024 春征的生产 tag。
2. **获奖又是第三种调用写法**：`goNovel(692762)`（数字直接传参，但函数名既非 `openNovel` 也非 `showBookDetail`），
   提取正则要再兼容 `goNovel\((\d+)\)`。16 本写死在 Vue render 的 `reward-list` 区块，
   按 `reward-box1/2/3/4` 分四组 = **3/3/5/5**；另有 6 张**无 nid 的奖项标题图**（`img468e/1ddf/05a4/a097/b08b/9acb`），
   奖项中文名写在图片里、JS 文本拿不到——与八征冬征、六征冬征同类，**只取 nid 为硬数据、不臆造奖项名**。
   公示切换点写死 `Date.parse("2024/7/7 12:00:00")`。
3. **数据：16 本全在 universe**，contest 全是「2024春季征文」，收藏 9,691–53,269
   （金奖组含 692762「青蛇也非池中物」5.3 万、696732「血后」3 万，信号强）。明细见 `contest_award_winners.csv`。

**获奖数据形态演进（四代，每代含早期变体）**：早期静态页（无）→ 十二/十三征 JS 静态 JSON（模块 + 图标邻域判奖）
→ 2025/2026 UUID 页 HTML `img[data-nid]`（六届）→ 日期式 Vue SPA render 硬编码
（七征 `openNovel("nid")` / 六征 `showBookDetail(数字)` / 2024 春征 `goNovel(数字)`，三种写法）。
提取器需兼容四代及各变体；`data-nid`/函数参数始终是可靠 nid，奖项名跨代存放与命名全不同，只能尽力解析、不臆造。

# SFACG 端点参考（实测档案）

> **定位**：SFACG PC 端（`s.sfacg.com` / `m.sfacg.com` / `book.sfacg.com`）外部接口的事实档案，
> 记录「端点是什么、返回什么、边界在哪、实测数字是多少」。
> **状态**：接口事实 + 用户裁定，补测与裁定更新至 2026-11-21；上游实现参照
> [sfacg_tools](https://github.com/light-nook-labs/sfacg_tools) `sfacglib/`（本档只做核对与补测）。
> **权威范围**：本文唯一维护 PC 端端点 URL/参数、限流与状态码陷阱、判活三态；移动端 App API 见 [`sfacg-app-api.md`](./sfacg-app-api.md)（18 字段字典），当期榜展示裁定见 [`sfacg-live-ranks.md`](./sfacg-live-ranks.md)。
> **口径**：计数/比例/误差均为快照现算值，仅供参考，禁止硬编码进代码；接口无契约、随时可能变，引用须带实测时点。
> **更新日期**：2026-11-21。

> **本档只覆盖 PC 端**。移动端 App API 另有档案（2026-11-17 新增，认证机制 + 18 字段字典 +
> 77 个推送位 + 逐章时间戳）。关键差异：上架时间（PC 无 / App 精确到秒 `addTime`）、
> 点击数（PC「万」量化 ±500 / App 精确整数 `viewTimes`）、单本体积（15 KB 移动 / 73 KB PC /
> App 0.7 KB）、章节清单（PC 解析目录 HTML / App 结构化 JSON 含逐章 `addTime`）。
> 定年、精确点击、更新热力图必须先读 `sfacg-app-api.md`。

## 0. 阅读索引

- 端点全景与 `tid` 映射 → §1；搜索三接口能力对照 → §2.4
- 全库枚举、目录容量、最近更新增量 → §3；详情页字段与状态码陷阱 → §4
- 榜单端点与展示裁定 → §7；判活三态、剔除集、覆盖率口径 → §8
- 限流与失败模式 → §9；字段映射 → §10；复现 → §12；开放问题 → §13

---

## 1. 端点总览

| # | 用途 | 方法与地址 | 认证 | 单次条数 | 分页 | 实测体积 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | HTML 搜索 | `GET s.sfacg.com/?Key={kw}` | 无 | **≤30（截断）** | **无** | 58–69 KB |
| 2 | JSON 搜索 | `GET m.sfacg.com/API/HTML5.ashx?op=search` | 无 | 6–15 | **无** | 2.4 KB |
| 3 | 联想词 | `POST m.sfacg.com/API/Book.ashx?op=searchreffer` | 无 | 15 | 无 | 0.6 KB |
| 4 | **分类枚举** | `POST m.sfacg.com/API/HTML5.ashx?op=novelbytype` | 无 | **6** | **深翻页可用** | 1.5 KB |
| 5 | 详情页（移动） | `GET m.sfacg.com/b/{nid}/` | 无 | 1 本 | — | 15 KB |
| 6 | 详情页（PC） | `GET book.sfacg.com/Novel/{nid}/` | 无 | 1 本 | — | 73 KB |
| 7 | 目录页 | `GET m.sfacg.com/i/{nid}/` | 无 | 全部章节 | — | 168 KB |
| 8 | 评论计数 | `GET book.sfacg.com/ajax/ashx/Common.ashx?op=getcomment` | 无 | 1 本 | — | 1 KB |
| 9 | 长评列表 | `GET m.sfacg.com/API/HTML5.ashx?op=getcmtlist` | 无 | 60/页 | `pi` 有效 | — |
| 10 | 评论回复 | `GET m.sfacg.com/API/HTML5.ashx?op=getcmtreply` | 无 | 逐页 | `pi` 有效 | — |
| 11 | 推荐流 | `POST m.sfacg.com/API/HTML5.ashx?op=getpushnovel` | 无 | 9 | **`pi` 无效** | — |
| 12 | 历史月榜 | `GET pages.sfacg.com/ajax/act/MonthlyBoy.ashx?op=getRanks` | 无 | 10–20 | 按月 | 4.4 KB |
| 13 | 当期五榜 | `GET m.sfacg.com/rank/{original,bm,new,jp,sale}.html` | 无 | 20 | 无 | 12.5 KB |
| 14 | PC 榜单页 | `GET book.sfacg.com/Rank/` | 无 | 4 榜同页 | 无 | — |
| 15 | 分类列表（PC） | `GET book.sfacg.com/List/?tid={n}` | 无 | 分页 | `PageIndex` | 34 KB |
| 16 | 更新窗口列表 | `GET book.sfacg.com/List/?ud={days}&PageIndex={n}` | 无 | 20 | `PageIndex`（站方截断 ≈82 页） | 29 KB |
| 17 | 单书月票 | `GET book.sfacg.com/ajax/ashx/GetTicketNum.ashx?nid={id}` | 无 | 1 本 | — | 1 B |
| 18 | 征文参赛清单（旧） | `GET pages.sfacg.com/ajax/ashx/Common.ashx?op=getNovelsByTag` | 无 | `ps` 可 200 | `pi`（0 起） | ~40 KB |
| 19 | 征文参赛清单（新） | `GET pages.sfacg.com/api/essay/getNovels` | 无 | 逐页 ≤500 | `page`（1 起） | — |

**分类 `tid` 映射**（PC 分类页现抓，九个值，无遗漏）：

| tid | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 分类 | 魔幻 | 玄幻 | 古风 | 科幻 | 校园 | 都市 | 游戏 | 同人 | 悬疑 |

与数据集 `genre` 九类一一对应，无需映射表。JSON 接口的 `TypeName` 为同名中文分类，实测一致。

---

## 2. 搜索类：三个接口，三种能力

### 2.1 HTML 搜索（`s.sfacg.com`）

```
GET https://s.sfacg.com/?Key={关键词}&SS=0&S=1
```

| 参数 | 取值 | 语义 |
| --- | --- | --- |
| `Key` | 任意字符串 | **必须 URL 编码**，否则中文可能被丢弃 |
| `S` | `1` | 查小说。`S=0` 返回漫画（实测小说 0 条） |
| `SS` | `0`/`1`/`2` | **实测无效**，三值返回条数相同（29/29/29），可省略 |

返回 ASP.NET WebForms 页面，结果在 `<ul>` 列表，上游 `_parse_html_results` 逐 `<ul>` 取 `<li>`。

| 字段 | 覆盖 | 说明 |
| --- | --- | --- |
| `NovelID` | 29/29 | 从 `book.sfacg.com/Novel/{nid}` 提取 |
| 书名 / 作者 | 29/29 | `<a class="orange_link2">` 文本 / 「综合信息：作者/日期」斜杠前 |
| `last_update` | 29/29 | 同上斜杠后，`YYYY/M/D H:MM:SS` |
| 封面 | 29/29 | `<img src>`，`//rs.sfacg.com/...` 协议相对 |
| **简介** | **27/29** | `li` 内裸文本节点，20–200 字，**三个接口里唯一提供简介** |
| 评分 | 无 | 没有 `Point` |

**条数上限 30**，且「共搜索到 N 个结果」与返回条数恒等——N 是截断值、不是真实总量。实测关键词
声明条数=返回条数：英雄 29、重生 30、少女 29、之 30、的 28、魔法 28、转生 30；对应库内标题命中
分别 1,289 / 4,424 / 11,168 / 28,100 / 98,793 / 4,405 / 4,710。不存在「翻到后面」这条路。**分页参数全部无效**（关键词「重生」，基准首条 `506050`）：`Page=2`、
`page=2`、`pi=2`、`PageIndex=2`、`PageSize=50` 均返回同样的 30 条同一结果集。

### 2.2 JSON 搜索（`HTML5.ashx?op=search`）

```
GET https://m.sfacg.com/API/HTML5.ashx?op=search&keyword={kw}&_={毫秒时间戳}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Status` | int | 200 正常 |
| `Novels[].NovelID` | int | nid |
| `Novels[].NovelName` / `AuthorName` | string | 书名 / 作者 |
| `Novels[].TypeName` | string | 中文分类：科幻/魔幻/都市/玄幻 |
| `Novels[].Point` | float | **评分 0–10**，HTML 接口没有 |
| `Novels[].NovelCover` | string | 相对路径，需拼 `{COVER_BASE}/` |
| `Novels[].Tags` | null | **实测 240 条全为 `null`**，形同不存在 |

**条数**：20 个关键词实测 6–15 条、**中位 12**（不是「固定 12 条」）；`pi=1/2/3` 返回相同结果，
分页无效。与 HTML 搜索（关键词「英雄」）的关系：JSON 12 条是 HTML 29 条的子集（JSON 独有 0 条，
HTML 独有 17 条），但位置 `0,1,…,10,13` **不是严格前缀**——少掉索引 13 的 `124218`，说明两者
排序规则不完全一致，不能当成「HTML 的前 12 条」。

### 2.3 联想词（`Book.ashx?op=searchreffer`）

`POST https://m.sfacg.com/API/Book.ashx?op=searchreffer`，表单 `keyword={关键词}`，需带 `Origin: https://m.sfacg.com`、`Referer: https://m.sfacg.com/search.html`、`X-Requested-With: XMLHttpRequest`。

返回 `{"status": 200, "keywords": ["书名1", ...]}`，**只有完整书名、无 nid**。实测「英雄」15 条
含重复（全角/半角括号、完全重复），规范化括号后按书名去重，15→13 条。只用于「补全书名」，
**不能当搜索结果**（无 nid，无法 join）。注意 `m.sfacg.com/search.html` 内联 JS 对 `keyword`
做了 `encodeURIComponent` 且 jQuery 再编码一次（服务端实际收到双重编码）；上游 `predictive_novel`
不编码同样返回 15 条，两种都能用。

### 2.4 三接口能力对照

| 能力 | HTML | JSON | 联想词 |
| --- | --- | --- | --- |
| 条数 | ≤30 | 6–15 | 15 |
| 分页 | 无 | 无 | 无 |
| nid | 有 | 有 | **无** |
| 简介 | **有（27/29）** | 无 | 无 |
| 评分 `Point` | 无 | **有** | 无 |
| 分类 `TypeName` | 无 | 有 | 无 |
| 封面 / `last_update` | 有 | 有 / 无 | 无 |
| 受静默限流 | **是** | 否 | 否 |

三者不可互相替代：**评分只在 JSON，简介只在 HTML**，联想词给「用户可能想搜什么」。

---

## 3. 分类枚举（`op=novelbytype`）——全库可枚举

`POST https://m.sfacg.com/API/HTML5.ashx?op=novelbytype`，表单 `tid={tid}&pi={页码}`，需带
`Content-Type: application/x-www-form-urlencoded; charset=UTF-8` 与 `Referer: https://m.sfacg.com/search.html?type={tid}`。

| 项 | 实测 |
| --- | --- |
| 每页条数 | **6**（末页可少于 6） |
| 页码 | `pi` 从 **1** 开始；`pi=0` 返回空 |
| 返回字段 | 与 JSON 搜索完全相同（含 `Tags` 恒 null） |
| 排序 | **不按 nid**，首页混有 78 万新书与 2022 年老书 |
| 稳定性 | **同页重复请求完全一致，相邻页无重叠**（5000∩5001=∅） |
| 体积 | 1.5 KB/页 |

**九个分类的目录容量**（`pi` 二分到最后一页，精度 ±1 页）：

| tid | 分类 | 末页 `pi` | 末页填充 | 目录槽位（×6） | 库内同分类 | 库内/槽位 |
| --- | --- | --- | --- | --- | --- | --- |
| 21 | 魔幻 | 14,908 | 5/6 | 89,448 | 85,696 | 95.8% |
| 22 | 玄幻 | 5,131 | 1/6 | 30,786 | 29,798 | 96.8% |
| 23 | 古风 | 1,430 | 4/6 | 8,580 | 8,258 | 96.2% |
| 24 | 科幻 | 2,994 | 1/6 | 17,964 | 17,366 | 96.7% |
| 25 | 校园 | 5,539 | 2/6 | 33,234 | 31,595 | 95.1% |
| 26 | 都市 | 4,154 | 4/6 | 24,924 | 23,450 | 94.1% |
| 27 | 游戏 | 2,180 | 1/6 | 13,080 | 12,782 | 97.7% |
| 28 | 同人 | 5,306 | 1/6 | 31,836 | 31,664 | 99.5% |
| 29 | 悬疑 | 926 | 2/6 | 5,556 | 5,170 | 93.1% |
| | **合计** | **42,568** | | **255,408** | **245,779** | **96.2%** |

- **槽位 ≠ 返回条数**：「页 × 6」是目录容量，实测平均填充 **5.20 条/页**（180 页随机抽样，
  SD 0.90，SE 0.067；分布 6→81、5→65、4→25、3→7、2→2），故实际返回 ≈ 42,568 × 5.20 =
  **221,354 ± 5,578（95% CI）**。缺的 13% 是槽位被跳过，不是书不存在（见 §8.3）。
- **分类内有空洞页**：悬疑第 915 页为空、916–926 仍有内容，二分末页应读作「最后一个非空页」。
- **「库内/枚举」不是覆盖率**：分母是上界、分子是库内 245,779 行，九类比值 93.1–99.5% 是「×6
  上界」口径，换成 ×5.20 会全部超过 100%。
- **排序不按 nid，无「最新」参数**：枚举不是「按时间增量同步」工具，发现新书须整类重扫或靠首页
  （前三条 `786381/783690/778683` 均 ≥77 万）。

**限流表现（与 HTML 搜索相反）**：连打 30 次 @0.5 s，30/30 成功、零空响应；0.3 s 间隔连扫
929 页零失败。全目录约 62 MB 流量，按 0.5 s/页约 5.9 小时（实测约 1.4 s/页，九类全扫需 16 小时以上）。

### 3.5 更新窗口列表（`List/?ud={days}`）

`GET book.sfacg.com/List/?ud={days}&PageIndex={n}`，PC HTML，20 本/页，按最近更新降序。
页头「现在有 `<span>N</span>` 部小说」报窗口总数（ud=7 实测 1,943），但**站方在 ≈82 页（≈1,640 本）
截断**——与月榜右截断同性质。列表行自带标题/作者（含 authorId）/评分/分类 tid/更新日期/字数，
详情抓取失败仍有可用行。与 `novelbytype` 分工：后者枚举全库但无增量能力，ud 列表是唯一
「最近被更新」的高效增量发现源，ud=15/30 可扩窗（上界未测）。端点发现自第三方
`jiuweiyaya/sfacg-rank`，本项目复核：ud=7 PageIndex=1 → 28.7 KB / 20 条 / 总数 1,943。

---

## 4. 详情页

### 4.1 移动版 `m.sfacg.com/b/{nid}/`（15 KB）

| 字段 | 选择器 / 位置 | 示例（nid=48704） |
| --- | --- | --- |
| 书名 | `.book_info span` | 英雄再临(英雄？我早就不当了) |
| 封面 | `.book_info img[src]` | `//rs.sfacg.com/.../2019/11/3d2f9821-….jpg` |
| 分类/状态/定价 | `.book_info div` | `科幻 已完结 VIP` |
| 作者/字数/更新 | `.book_info3` | `无聊看看天 / 5446886字 24-03-25 20:57` |
| 简介 | `.book_bk_qs1` | 完整简介（非截断） |
| **收藏 / 赞 / 月票** | `.book_interact li` 第 1/2/4 项 `<small>` | 281988 / 89171 / 0 |
| 打赏 | 同上第 3 项 | **无数字**（只显示「打赏」） |

**移动版没有点击数**（人气只在 PC）。与数据集对照（nid=48704，内容上界 2026-05-03）：
数据集 `favs` 281,034 / `praises` 89,008，详情页 281,988 / 89,171，差值即 2026-05 后增量。

### 4.2 PC 版 `book.sfacg.com/Novel/{nid}/`（73 KB）

| 字段 | 选择器 | 示例 |
| --- | --- | --- |
| 类型 / 字数+状态 | `.count-detail .text-row .text` 第 1/2 行 | `类型：科幻` / `字数：5446886字[已完结]` |
| **人气（clicks）** | 第 3 行 | `人气：11899.5万`（**单位「万」需换算**） |
| 更新时刻 | 第 4 行 | `更新：2024/3/25 20:57:58` |
| 赞 / 收藏 | `#BasicOperation .btn` | `赞 89171` / `收藏 281988` |
| 标签 | `.tag-list .tag .highlight .text` | `战斗 / 热血 / 无敌 / 超级英雄` |
| 定价 / 征文 / banner | `.title .tag` / `.d-banner` | `VIP` / 存在 |

「人气」带「万」且被截断（`11899.5万`=118,995,000，数据集 118,520,000 为时点差）。解析需处理
「万」后缀：`float(x.replace("万","")) * 10000`，但 PC 只显示到 0.1 万，即 **±500 量化误差**、
丢掉千位精度。

### 4.3 两版取舍

| 需求 | 用哪个 |
| --- | --- |
| 收藏/赞/简介/体积小 | **移动版**（15 KB） |
| 点击数（人气） | **只能 PC 版**（73 KB） |
| 标签 | 只有 PC 版有结构化 `.tag-list`；移动版标签在 JS 里 |
| banner 位 | PC 版 `.d-banner` |

移动版快 5 倍；端上只要收藏与赞用移动版，需要点击数再补 PC 版，**不要两版都抓**。

### 4.4 状态码不可信：判存在必须查文案

本站对不存在的 nid 返回 **HTTP 200**，与正常页同状态码、同 content-type：

| 请求 | 状态码 | 体积 | 标题 / 文案 |
| --- | --- | --- | --- |
| PC `/Novel/{无效 nid}/` | **200** | **1,643 B** | 出错了 / `小说不存在` |
| 移动 `/b/{无效 nid}/` | **200** | **3,738 B** | 出错啦（无书名/字数） |
| 有效页 | 200 | 73,527 B（PC）/ 14.7 KB（移动） | 含书名 |

判据按可靠性排序：① **匹配否定文案**（PC 查 `小说不存在`、移动查 `出错啦`）——唯一与实现无关；
② **无条件检查书名**（正常移动页有 `.book_info span`）。体积阈值 >5 KB 换版式即失效、HTTP 状态码
完全无效，二者都不可作判据。报告 10 的「>5 KB 且含书名」未排除非小说页、无文案判据，是其 21.1%
至今无法复核的原因之一（§8）。

**同类陷阱：PC 列表页越界不报错、粘住末页**。`tid=21&pi=14920`（越界）与 `pi=20000` 返回完全
相同的 34,181 B 页面、首批 id 一致；**不能用「返回为空」判末页，只能比对是否与前一页相同**。
移动端 `novelbytype` 相反，越界返回空数组，可正常判末页。

---

## 5. 目录与章节

| 端点 | 实测 |
| --- | --- |
| `GET m.sfacg.com/i/{nid}/` | 168 KB，`.mulu` 38 个卷标题，`ul a` **1,741 个章节链接** |
| `GET book.sfacg.com/Novel/{nid}/` | 同页含 PC 目录（`.catalog-hd` / `.catalog-list`） |

**VIP 章节标记**：`.icn_vip`（文字章）、`.icn`（图片章）。实测 nid=48704 目录 `.icn_vip` 数量为 0
但 `price_type=VIP`——目录 VIP 标记是**逐章**标记、不是整书标记，不能据此判断书是否 VIP。

---

## 6. 评论

| 端点 | 参数 | 返回 |
| --- | --- | --- |
| `op=getcomment` | `nid`、`_` | `{status, ShortCommentNum, LongCommentNum, ShortComments[]}` |
| `op=getcmtlist` | `nid`、`so=addtime`、`pi`、`ctype=long`、`len=60` | `{Status, Cmts[]}` |
| `op=getcmtreply` | `cid`、`pi`、`withcmt=false` | `{Replys[]}` |

实测 nid=48704：`ShortCommentNum=82291`、`LongCommentNum=452`。上游 jsonl 没有
`review_num`/`comment_num`，报告 03 据此判「长评/短评维度不可做」；本接口补上该维度，但
**只能逐本查**（1 本=1 请求），只对用户实际打开的书有意义，不能全库统计。`getcomment` 第一条
是站方置顶公告，**解析须过滤 `CommentID=0`**。

---

## 7. 榜单

### 7.1 历史月榜（`MonthlyBoy.ashx`）——可回溯任意月份

```
GET https://pages.sfacg.com/ajax/act/MonthlyBoy.ashx?op=getRanks&date={YYYY-MM}&rank={N}
```

| `rank` | 榜单 | 条目 | 值字段 |
| --- | --- | --- | --- |
| 0 | 月票榜 | 20 | `ticketNum` = 月票数 |
| 2 | 新书榜 | 10 | 稀疏（归档中位 0 条/月） |
| 3 | 热销榜 | 20 | `ticketNum` 恒为 0（只排名次） |
| 4 | 对话月票榜 | 20 | `ticketNum` = 月票数 |

返回 `{status:200, data:[{nid, name, ticketNum, authorName, cover}]}`，4.4 KB；**2013-03 起连续
有数据**，每月一期、月度清零。实测 `date=2026-11, rank=0` 首条 750700《黑道公主的我还能怎么
堕落？》**3175 票**（来源：MonthlyBoy 端点，2026-11 当期）。

### 7.2 当期五榜（移动端静态页）

| 端点 | 榜 | 条目 | 数值 |
| --- | --- | --- | --- |
| `m.sfacg.com/rank/original.html` | 人气 | 20 | 无数值，仅 nid 序列 |
| `m.sfacg.com/rank/bm.html` | 收藏 | 20 | 无数值 |
| `m.sfacg.com/rank/new.html` | 新书 | 20 | 无数值 |
| `m.sfacg.com/rank/jp.html` | 日轻 | 18–20 | 无数值 |
| `m.sfacg.com/rank/sale.html` | 热销 | 20 | 无数值 |

全部 12.5 KB，nid 在相对链接 `/b/{nid}/` 里；要数值只能走 PC 榜单页或月榜接口。
**展示裁定（用户 2026-11-20/21）**：移动五榜仅热销榜接近 App「畅销榜」（滞后 ≤3 天），
人气/收藏/新书/日轻四榜多年未变（落后 >3 年）；App 已整体移除移动榜展示——官方移动榜 API
多 bug、数据不可信。**端点事实保留**，详见 [`sfacg-live-ranks.md`](./sfacg-live-ranks.md)。

### 7.3 单书月票（`GetTicketNum.ashx`）

`GET book.sfacg.com/ajax/ashx/GetTicketNum.ashx?nid={id}` → 响应体是裸整数（如 `3189`），
无认证、无 JSON 包装。语义是**当月**票数（每月 1 日清零），与 `MonthlyBoy.ashx` 的 `ticketNum`
同口径。注意：

- **无效 nid 与真零月票同为 `'0'`**——不能判活，只对已判活的书取值；
- 老书可能真实为 0（nid=48704 实测 0）；活跃书正常（nid=750700 → **3189**，来源：GetTicketNum
  端点，2026-11-18 实测，同页 PC 详情「本月排名 999 名」「收藏 15877」交叉吻合）；
- 单请求 1 B；App 详情页可追加此请求获得精确月票（v1 设计丢弃月票，接入属产品决策）。

> **同一本书 750700 的票数在三个来源分别是 3175（MonthlyBoy，2026-11）、3189（GetTicketNum，
> 2026-11-18）、3168（当期榜快照，2026-11-16，见 `sfacg-live-ranks.md`）——端点与时点不同，
> 不要硬统一。** 来源：第三方 `jiuweiyaya/sfacg-rank`，本项目实测复核。

### 7.4 征文参赛清单（`getNovelsByTag` / `essay/getNovels`）

征文「参赛作品区」是分页 REST 接口，无登录/认证，返回 `nid/标题/作者/简介/封面/categoryID`，
用于补采单向游标扫描漏掉的短/中篇（另见专题 `docs/contest-roster-harvest.md`）：

| | 旧 H5 页（2018–2022） | 新 SPA 页（2023 起） |
| --- | --- | --- |
| 地址 | `pages.sfacg.com/ajax/ashx/Common.ashx` | `pages.sfacg.com/api/essay/getNovels` |
| 参数 | `op=getNovelsByTag&tagId={t}&ps=200&pi={0起}` | `tagIds={t}&page={1起}&size={n}` |
| 返回 | `{status,novels[],totalPage}` | `{status:{errorCode},data:{totalPage,novels[]}}` |
| 字段大小写 | `NovelID/NovelName/AuthorName/Intro/...` | `novelID/novelName/authorName/intro/...` |
| 单页上限 | `ps=200` | `size=500`（更大被截断） |

**关键陷阱**：① 字段名大小写两套不同，解析要兼容；② 翻页起点随版本变（旧 `pi` 0 起，新多数
`page` 1 起，但 2025/2026 春征 UUID 页传 `currentPage-1`），按页面 JS 实际传参为准；
③ `tagId` 是「某届比赛某赛项」编号，每新增、跨届不复用，sandbox 与生产 id 也不同，位置随版本变
（旧 SPA 在打包 JS、UUID 页在 HTML `data-tagid`），必须按每届页面实际取生产值，不能从届次推导；
④ 活动页 URL 形态演进 `zwYYYY`→`zwYYYYMMDD`→`zw/essayActivity_{UUID}.html`，冬征六/七例外用日期式
SPA（详见 `contest-roster-fields.md` §8.5–8.7）；⑤ `categoryID` 取值旧 0/1、新 0/1/3，不能当 form 真值；
⑥ 清单 `intro` 是作品简介、非作者 intro（作者资料见 `author-profile-on-demand.md`）；⑦ 只覆盖参赛作品，
未参赛一次性完本短篇仍漏，非全库金标。实测 14 个 tag 去重 31,092 本、9,012 本（29%）不在 db，
短/中篇赛道漏采最重；0.25–0.6 s 串行 / 4 并发无风控迹象，只取清单元数据、不取正文、不登录。

---

## 8. 判活、三态与覆盖率

### 8.1 三态判据（唯一权威，用户 2026-11-17 定案）

只分三态、**不细分下架原因**（版权/违规/抄袭/搬运/AI 生成/作者主动/举报下架均不进判据）：

| 态 | 判据（满足其一即可） | 实测形态 |
| --- | --- | --- |
| **死亡** | 页面是「小说不存在」/「出错啦」——**匹配否定文案**，不看状态码 | PC 1,643 B、移动 3,738 B，HTTP 均 200 |
| **僵尸** | ① 有详情页（含书名/字数/收藏）但**无阅读入口**；或 ② **数字字段非法**（负数收藏、全零、字数与章节不符） | 13–15 KB，与存活页体积中位只差 **35 B（0.25%）**，读入口 0/50 |
| **存活** | 有详情页 + 有 `点击阅读`/`目录列表` + 数字合法 | 14.2 KB，读入口 20/20 |

- **最优判据**：检查 `div.book_Catalog` 下是否有 `<a>`（僵尸是空 `<div class="book_Catalog"></div>`，
  存活有 `/c/{nid}`、`/i/{nid}`），比全文关键词更稳定、不依赖文案；fallback 才是关键词。
  `.book_info2` 僵尸无 VIP、存活有 VIP；页面 `<a>` 数僵尸 12、存活 18。
- **方向性**：「应版权方要求,该小说已经下架」是**充分非必要**条件——出现必是僵尸，没出现不能判存活；
  主判据是「详情页 + 无阅读入口」与「数字字段非法」，都是缺陷检测、与下架原因无关。
- **数字字段非法要单列**：`negative_favs`（58 本）有阅读入口但 `like_num<0`，按判据归僵尸，
  不因「能点开阅读」当正常供给。
- **目录页二次确认**：僵尸目录页 4–6 KB / 章节字 <10，存活 167 KB / 1,078 字，差 30 倍但成本
  高 10 倍，不适合大规模判活；`/c/{nid}/` 对两者都返 3,738 B「出错啦」，不能区分。

### 8.2 剔除集与低 nid 集中

构建期 `out/manifest.json` → `dropped` 共 **2,451 行**：

| 剔除规则 | 行数 | 说明 |
| --- | ---: | --- |
| `status_missing` | **2,287** | status 空 = 已下架但详情页保留 → **主要就是僵尸书** |
| `negative_favs` | 58 | 收藏下溢（数字非法） |
| `title_without_text` | 56 | 无文字书名且无内容 |
| `licensed_light_novel` | **47** | 正版日轻（版权方账号） |
| `genre_unresolved` | 2 | 2010 改版前旧分类 |
| `all_zero` | 1 | 全零 |

剔除集 nid 中位 9,272，2,342/2,451 < 10 万。`status_missing`（僵尸）**严格集中在 nid ≤ 83,624**，
高 nid 区间不存在僵尸：报告 10 探针旧判存活按 nid 分 4 段各抽 10 本 40/40 有阅读入口，高 nid
30 本旧判存活 30/30 有入口、20 本旧判死亡 20/20 死亡页，库内 nid>60 万 30 本 30/30 存活。
⇒ **僵尸是低 id 段结构性遗留，不是均匀现象**；补爬估算须分层，不能对全区间套同一僵尸率。

### 8.3 目录 vs 库：悬疑整类普查（929 页全扫）

分清三个量（数值见 §3）：目录槽位容量、实际返回唯一 nid、缺口（槽位被跳过）。**目录容量不是
全站活书上界**——大量书「页面可访问、但不在任何分类目录里」，不占目录槽位。

悬疑（tid=29）普查实证：

| 指标 | 数值 |
| --- | --- |
| 目录槽位 / 返回条目（含重复）/ 唯一 nid | 5,556 / 4,836 / **4,834**（2 条重复） |
| 槽位缺口 / 空页 | **720**（13.0%，与全站一致）/ 915（类内空洞）、927–929（越界） |
| 与库内交集 / 库外合计 | **4,647**（96.1%）/ **187** |
| ├ 快照后新建（nid>774,850） | **165**（3.4%）——不是漏抓，是时间差 |
| └ 同范围真遗漏 | **22**（占同范围 4,669 本的 **0.47%**） |
| 库内悬疑总数未进目录 | 5,170 → **523 本（10.1%）** |

**结论**：① 库外主体是**新书不是漏抓**（165/187），同范围真遗漏仅 22 本（0.47%），按此外推全站
约 1 千本；② **「不在目录」是平台常态**（约 10% 库内书查不到分类目录，13% 槽位被跳过），
任何以目录为全集的口径都会系统性少算；③ 必须分开命名 `目录内（可发现）` 与 `可访问（页面存在）`。

### 8.4 对报告 10 与覆盖率的后果

报告 10 旧链「缺失槽位 × 21.1% 存活率 → 遗漏活书 → 覆盖率」错在**分母**：把构建期已剔除的
2,451 本（原始 jsonl 全已抓到）、真死亡页与真遗漏活书混在一起统一外推，于是 11.1 万本遗漏被高估。
误判**不在**那 63 本个体（63/63 有阅读入口、19/25 能被 JSON 搜索命中自身，确是真活书）。
按三态判据重写后 **覆盖率 69.3%**（旧 68.9% 量级未变、口径已改）：分母先扣 manifest 剔的
2,451 本，按 nid 段分层加权；在册密度呈 U 型、缺失槽位存活率倒 U 型（游标形状）。
**补爬对象**是「nid ≤ 774,850、三态为存活、且不在 CSV 的 nid」，按悬疑同范围遗漏率 0.47%
估算约 1 千本；2,287 本低 id 僵尸是构建规则的正确剔除，不是补爬对象。

> 工程侧落地事项（如 `report_survival.py` 三态重写、分层出数），本文不执行。

### 8.5 复现

```bash
uv run --project analysis python analysis/fetchers/probe_novelbytype.py --tid 29 --census
# → analysis/out/novelbytype_census_29.json（唯一 nid、重复、空页、与库双向差额）
# 剔除集原因重建：pipeline.build_csv.load_jsonl + clean_row + drop_mask（见 §8.2），
# 再对每组抽样请求 m.sfacg.com/b/{nid}/ 检查阅读入口与否定文案。
```

---

## 9. 限流与失败模式

### 9.1 HTML 搜索的静默限流（最危险）

| 项 | 实测 |
| --- | --- |
| 触发 | 连续约 **17–18** 次请求（@0.5 s）后 |
| 表现 | **HTTP 200**、页面正常（5.8 KB），但标题变「请输入关键字」、声明「共搜索到 0 个结果」 |
| 持续 | **>3 分钟未恢复**（20/45/90/180 s 均仍被限） |
| 范围 | **仅 `s.sfacg.com`**；同期 JSON 搜索、联想词、详情页、`novelbytype` 全正常 |

状态码 200、无异常、结构合法，只一个中文短语说明被限——「用条数是否为空判断成功」的逻辑会
静默给出错误结论。**唯一可靠检测**：响应含「请输入关键字」。上游 `_parse_html_results` 不做此
检查，被限返回空列表，必须自行补。

### 9.2 其他端点与建议

`op=novelbytype` 连打 30 次 @0.5 s 全成功；JSON 搜索未触发（网页实际调用就是它）。建议单端点
≥1 s 间隔，HTML 搜索是唯一需严格计数者，客户端硬上限（如 10 次/分钟）、被限降级到 JSON 搜索。

### 9.3 参数陷阱（实测纠正的四个误解）

| 误解 | 实测事实 |
| --- | --- |
| 「`SS=0` 会让搜索返回空」 | 假，`SS` 三值无差异；空结果是限流，不是参数 |
| 「HTML 搜索返回全量」 | 假，硬上限 30，声明 N 也是截断值 |
| 「JSON 搜索固定 12 条」 | 不准确，6–15 条、中位 12 |
| 「`novelbytype` 需特殊 tid」 | 假，就是 PC 分类页 21–29 九类齐全 |

---

## 10. 字段映射到本项目 schema

| 本项目字段（`books`） | 来源端点 | 表达式 / 备注 |
| --- | --- | --- |
| `nid` / `title` | 全部 | — |
| `author` | 详情页/搜索 | 同名即同人，平台无 author id |
| `genre` | 详情页/`novelbytype` | `TypeName` 或 `tid` 映射，九类一致 |
| `price_type` / `contest` | PC 详情页 `.title .tag` | 无标记=免费；contest 需排除 `签约`/`VIP` |
| `status` / `words` | 详情页 | 状态在 `字数：…字[已完结]` 括号内；字数移动版 `…字`、PC 版 `字数：…字[…]` |
| `clicks` | **仅 PC 详情页** | `人气：11899.5万`→×10000，**±500 量化误差** |
| `favs` / `praises` | 详情页 `.book_interact` | 移动版 `<small>` 第 1/2 项 |
| `featured` | PC 详情页 | `.d-banner` 是否存在 |
| `cover_url` | 详情页/搜索 | `NovelCover` 拼 `{COVER_BASE}/`，协议相对补 `https:` |
| `updated_at` | 详情页 | 移动版 `YY-MM-DD HH:MM`，**需补世纪** |
| `tags` | PC 详情页 | `.tag-list`，移动版无结构化标签 |
| `est_year` 等 | **不由端点提供** | 走 nid 定年（`analysis/lib/eras.py`） |
| 长评/短评数 | `op=getcomment` | **只能逐本查**，不可全库 |

字段与 App API 返回值的完整对应关系见 [`api-field-mapping.md`](./api-field-mapping.md)。

---

## 11. 上游实现的问题清单

[sfacg_tools](https://github.com/light-nook-labs/sfacg_tools) 可直接复用，但四处须自行处理：

| # | 位置 | 问题 | 后果 |
| --- | --- | --- | --- |
| 1 | `_parse_html_results` | 不检测静默限流 | 被限返回空列表，与「真的没搜到」无法区分（§9.1） |
| 2 | `_parse_html_results` 的 `snippet` | 取 `li` 内首个长度>20 的裸文本节点 | 把「综合信息」后换行残留拼进 `updated`（带 `\r\n\t`），需二次清洗 |
| 3 | `search()` 的 `SS='0'` | 参数实测无效却硬写 | 无害，但误导为有效（§9.3） |
| 4 | `predictive_novel` | 未去重 | 返回 15 条含全角/半角重复（§2.3） |

**未实现**：`op=novelbytype`（§3）——上游定位是「下载单本」，不做枚举；端上若要全库同步须自行实现。

---

## 12. 探针与复现

```bash
uv run --project analysis python analysis/fetchers/probe_sfacg_api.py
# → out/sfacg_api_probe.json：搜索/三接口对照/字段覆盖/状态码陷阱
uv run --project analysis python analysis/fetchers/probe_novelbytype.py [--tid 29] [--verify]
# → out/novelbytype_bounds.json：九类二分边界；--verify 追加页间重叠校验
uv run --project analysis python analysis/fetchers/probe_novelbytype.py --tid 29 --census
# → out/novelbytype_census_29.json：整类普查，§8.3 定案源
uv run --project analysis python analysis/fetchers/probe_contest_roster.py [--tags 704,703,702] [--size 500]
# → out/contest_roster.csv：征文清单两套接口 + tag 表 + 与 db 补采差额
```

HTML 搜索探针之间必须 sleep ≥5 s（脚本内置 `GAP=6`）否则被静默限流污染结果；`novelbytype`
相反，0.3–0.7 s 间隔连数百次无异常。`--stress` 会主动触发限流，非必要不要跑。两探针只依赖 `requests`。

---

## 13. 待查（开放问题）

| # | 问题 | 影响 |
| --- | --- | --- |
| 1 | `pi` 深翻页在「新书插入」时是否漂移（只测了单时刻稳定性） | 决定全库枚举能否增量续扫 |
| 2 | 枚举首页是否等价「最近更新」——若是，1 页/类即可增量 | 可把整类全扫降为秒级 |
| 3 | 移动版详情页标签在哪个 JS 变量里 | 若可解析，详情页只抓移动版即可 |
| 4 | HTML 搜索限流准确恢复时间（>3 分钟，未测上界） | 决定重试退避策略 |
| 5 | 类内空洞页（悬疑 915 空、916–926 有内容）是删除空槽还是分页抖动 | 决定全扫能否用「遇空即停」 |
| 6 | 悬疑 523 本「库内有、目录无」的性质：已移除？改分类？还是分页漏读 | 决定「库 vs 目录」差额能否作下架判据 |

# SFACG 官方移动端 App API 事实档案（api.sfacg.com）

> **定位**：`api.sfacg.com`（SFACG 官方 iOS/Android App 后端）的唯一事实档案，与 PC 端 [`sfacg-endpoints.md`](./sfacg-endpoints.md) 互补。
> **状态**：接口事实（实测 2026-11-17～11-18，后续补测见各节）；动手前先读本文，不要猜参数、不要试探性请求。
> **权威范围**：本文唯一维护 App API 的认证、端点、字段字典、推送位与能力边界；字段↔本项目数据列的对应见 [`api-field-mapping.md`](./api-field-mapping.md)。
> **口径**：计数/比例/误差均为快照现算值，仅供参考，禁止硬编码进代码；API 无契约、随时可能变。
> **更新日期**：2026-11-21。

## 0. 阅读索引

- 认证与请求骨架 → §1；端点总表与分类参数 → §2；18 字段字典 → §3
- 77 个推送位 → §4；定年/精确点击/章节时间戳/自建时序 → §5
- 合规边界 → §6；与 PC 端取舍 → §7；开放问题 → §8

> **正文不取**：`GET /Chaps/{id}?expand=content` 实测 401 / errorCode 507「没有访问接口的权限」，
> 无需也无法绕过。本档案只覆盖书目元数据。

---

## 1. 认证机制（实测）

App 用**固定的内置凭据 + 每次请求自签**，不需要用户账号即可访问公开数据端点。

| 项 | 值 / 规则 |
| --- | --- |
| `authorization` | `Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE=`（解码 = `androiduser:1a1$51-yt697;*AJ7Bpxq4`） |
| `accept` | `application/vnd.sfacg.api+json;version=1` |
| `user-agent` | `boluobao/5.0.36(android;32)/H5/{device_token}/H5` |
| `sfsecurity` | `nonce={uuid4大写}&timestamp={unix毫秒}&devicetoken={uuid4大写}&sign={md5大写}` |
| `sign` | `md5(nonce + timestamp + devicetoken + SALT)`，`SALT = "FN_Q29XHVmfV3mYX"` |
| `nonce` / `device_token` | **客户端自造的 UUID**，每次请求重新生成，服务器只校验签名 |

- **签名错误返回 `status.httpCode = 417`，而 HTTP 状态码仍是 200**——与 PC 端「无效 nid 返 200」
  同类陷阱，必须读 JSON 里的 `status.httpCode`。
- `authorization` 的 Basic 凭据是 App 客户端内置的固定常量（所有用户共用），**不是任何用户的私密凭据**；
  由多个公开第三方实现交叉印证、彼此一致（见 §9 上游端点清单）。
- 另有两代签名算法：上述 md5 简单式；`duongden/sfacg_downloader` 用 nonce 重排 + 异或的复杂式。
  简单式实测可用，优先用它。

### 1.1 请求骨架

```python
import hashlib, time, uuid, requests

SALT = "FN_Q29XHVmfV3mYX"
BASIC = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="

def make_headers() -> dict[str, str]:
    nonce = str(uuid.uuid4()).upper()
    timestamp = int(time.time() * 1000)
    device_token = str(uuid.uuid4()).upper()
    sign = hashlib.md5(
        f"{nonce}{timestamp}{device_token}{SALT}".encode("ascii")
    ).hexdigest().upper()
    return {
        "accept": "application/vnd.sfacg.api+json;version=1",
        "authorization": BASIC,
        "user-agent": f"boluobao/5.0.36(android;32)/H5/{device_token}/H5",
        "sfsecurity": (
            f"nonce={nonce}&timestamp={timestamp}"
            f"&devicetoken={device_token}&sign={sign}"
        ),
        "accept-encoding": "gzip",
    }

resp = requests.get("https://api.sfacg.com/novels/730611",
                    headers=make_headers(), timeout=18)
```

---

## 2. 端点总表

复现：`uv run python analysis/fetchers/probe_sfacg_app_api.py --endpoints`

| 端点 | HTTP | 备注 |
| --- | --- | --- |
| `GET /novels/{id}` | 200 | **18 字段，含 `addTime`/`viewTimes`** |
| `GET /novels?tid={类型}&size=50&page=0` | 200 | 分类枚举，`size` 上限 50 |
| `GET /novels?size=50&page=0` | 200 | 全库列表（`tid` 默认 −1） |
| `GET /novels?filter=recom&size=50` | 200 | 首页推荐，实测返回 20 条 |
| `GET /search/novels/result?q=&size=&page=` | 200 | 搜索小说，返回 `{novels, comics, albums}` |
| `GET /search/any/result?q=&size=&page=` | 200 | 搜索任意作品（同上结构） |
| `GET /novels/specialpushs?pushNames=&size=` | 200 | 特别推送列表；`pushNames` 可逗号分隔 |
| `GET /specialpush` | 200 | **全部 77 个推送位** |
| `GET /novels/{id}/dirs` | 200 | 目录 → `{novelId, lastUpdateTime, volumeList}` |
| `GET /novels/{id}/volumes` | 200 | 分卷列表 `{sno, title, volumeId}` |
| `GET /novels/{id}/chaps` | 200 | **逐章列表，含 `addTime`/`charCount`** |
| `GET /novels/{id}/cmts?page=&size=` | 200 | 简评，含 `createTime`/`favCount`/`replyNum`/`isStick` |
| `GET /novels/{id}/fans` | 200 | 粉丝榜，含 `fansPoint`/`nickName`/`vipLevel` |
| `GET /novels/{id}/ticket/rank?numMax=&dateRange=` | 200 | 月票排名，`dateRange`：0 周 / 1 月 / 2 总 |
| `GET /novels/{id}/bonus/rank?numMax=&dateRange=` | 200 | 打赏排名，`dateRange=1` 月度 |
| `GET /novels/{id}/actpushes?filter=android&pageType=` | 200 | 书内活动推送，实测 `pageType=0` 为空 |
| `GET /adpworks/novelId/{id}` | 200 | **衍生作品**：`{novelId, albumId, comicId, *LastUpdateDate}`，`0`=无 |
| `GET /adpworks/comicId/{comic-id}` | 200 | 漫画 → 原著小说（同上结构，反向） |
| `GET /comics/{id}` | 200 | 漫画详情：`comicName`/`folderName`（Web 路径）/`typeId`/`viewTimes`/`isFinished`/`latestChapterTitle`/`signStatus` |
| `GET /albums/{id}` | 200 | 有声详情：`novelId`/`name`/`visitTimes`/`latestChapterId`/`coverBig\|Small\|Medium`；**无 URL 或 folderName 字段** |
| `GET /novels/{id}/reviews` | **404** | 第三方 `ubook-rs` API 文档（GitHub 仓库 `zymelaii/ubook-rs`，非本地文件）记的路径无效 |
| `GET /Chaps/{id}?expand=content` | **401** | errorCode 507「没有访问接口的权限」——**正文不可取** |
| `GET /user` | **401** | 「需要登录才能访问该资源」 |

### 2.1 分类枚举参数

`GET /novels` 的 `tid`（与 PC 端 `novelbytype` 九类一致）：
`−1` 全部、`9` 爱情、`21` 魔幻、`22` 玄幻、`23` 古风、`24` 科幻、`25` 校园、`26` 都市、`27` 游戏、`29` 悬疑。

`categoryId`（查询参数）：`−1` 全部、`0` 常规、`1` 对话小说、`3` 短篇、`4` 沉浸式互动小说。
这是**产品线/形态**过滤、不是题材（与 `tid` 正交），语义经实测定案，见 `api-field-mapping.md`。

> 对比 PC 端：`op=novelbytype` 需 POST + Referer，枚举出 255,408 个目录槽位。App 端 `/novels`
> 结构化得多，但**两者枚举边界是否一致尚未验证**，不要混用结论。

---

## 3. 字段字典

### 3.1 小说详情 / 列表条目的 18 字段

字段与本项目数据列的实测对应关系见 [`api-field-mapping.md`](./api-field-mapping.md)
（配对快照现算，数字仅供参考）。下表「本项目对应」列已按该分析修正：`point`（废弃占位分）
不作 `pr`；`bgBanner` 非空即 `featured=1`（URL 主体可由 nid 拼 CDN 前缀得到，故只存布尔）；
`categoryId` 语义经实测定为形态标记（0/1/3/4），见 `api-field-mapping.md`。

| App 字段 | 类型 | 本项目对应 | 说明 |
| --- | --- | --- | --- |
| `novelId` | int | `id` | 主键 |
| `novelName` | str | `title` | 标题 |
| `authorId` | int | — | **账号唯一身份**（改名/大小写不变，可做作者生态） |
| `authorName` | str | `author` | 作者**显示名**（可改，不能当身份） |
| `addTime` | str | — | **建档时间，精确到秒**（`2024-12-27T19:03:11`） |
| `lastUpdateTime` | str | `updated_at` | 最后更新时间，精确到秒 |
| `markCount` | int | `favs` | 收藏数（精确整数） |
| `viewTimes` | int | `clicks` | 浏览/点击数（**精确整数**，非「万」量化） |
| `charCount` | int | `words` | 字数（含全部内容，口径见 §5.5） |
| `isFinish` | bool | `status` | 是否完结 |
| `signStatus` | str | `price_type` | `VIP` 等签约状态 |
| `typeId` | int | `genre` | 类型 id（见 §2.1） |
| `categoryId` | int | 形态标记 | **0 常规 / 1 对话小说 / 3 短篇 / 4 沉浸式互动小说**——产品线/形态，不是题材 |
| `isSensitive` | bool | — | 敏感标记（无用：敏感内容强制下架，本库书不会命中） |
| `novelCover` | str | `cover_url` | 封面 URL（含 `YYYY/MM/` 目录 → 仍是运营时间） |
| `bgBanner` | str | `featured` | 横幅图 URL，仅 0.31% 非空，非空即 `featured=1` |
| `allowDown` | bool | — | 历史遗留字段（无用：全站书籍恒禁下载） |
| `point` | float | — | 历史遗留字段（废弃占位分） |

**作者身份（2026-11-18 实测）**：

- `authorId` 是账号唯一身份；`authorName` 是**显示名，可改**（改名后同一 `authorId` 在不同书上返回不同名，
  实证 11 组、28 本）。
- 用户名**大小写不敏感**（`kola`/`KOLA` 同为 `authorId=382`）、**空格敏感**
  （`First Order`(7505)/`firstorder`(12459)、`dark digger`(16612)/`darkdigger`(39896) 是不同账号）。
- 按名字做同作者判定必须 `casefold()` 且**不得去空格**；有 `authorId` 时以 id 为准。

### 3.2 章节列表的字段

`GET /novels/{id}/chaps` 每章：`chapId`、`title`/`ntitle`、`sno`/`chapOrder`/`rowNum`、`volumeId`、
**`addTime`**（章节创建时间，精确到秒）、**`updateTime`**（章节更新时间）、**`charCount`**（本章字数，
接近官方全勤计法）、`isVip`、`isRubbish`、`auditStatus`、`expand`。

### 3.3 评论 / 粉丝字段

`GET /novels/{id}/cmts`：`commentId`、`content`、`createTime`、`favCount`、`replyNum`、`ticketNum`、
`isStick`、`accountId`、`displayName`、`roleName`、`vipLevel`、`diyaMember`。
`GET /novels/{id}/fans`：`accountId`、`nickName`、`userName`、`fansPoint`、`levelName`、`vipLevel`。

### 3.4 衍生作品字段（`/adpworks`）

字段（2026-11-18 实测）：`novelId`（原样回显、不校验存在）、`comicId`/`albumId`（`0`=无）、
`comicLastUpdateDate`/`albumLastUpdateDate`（无对应作品时 null）。样本：155640→comic 2937 + album 97，
48704→comic 1920，730611→album 149（无漫画）。

规模 **<200 本**（改编漫画 <50、有声 ≈150），与 `featured` 交集很大、漫画改编大概率是其子集。
Web 入口模板虽在，但漫画站官方定期关闭、详情页**常态 404**，有声无任何 URL 字段。
陷阱：无效/已死/无衍生作品三者 `status` 都是 200 且 id 全 0，**不能判活**，只对已判活取值。

`search/any`（或 `search/novels/result`）返回 `{novels, comics, albums}`：`albums` 带 `novelId` 可反查，
`comics` 只有 `comicId`——漫画侧关联只能走 `/adpworks`；`GET /comics?novelId=` **不支持按小说过滤**
（忽略参数、返回热榜 6 条）。

---

## 4. 推送位（77 个）

`GET /specialpush` 返回 77 个位代码、42 个当前非空：

> `novelSpecialSubject`（当期封面推荐）、`homePush`(10)、`vipPush`(4)、`homeSecondPush`、
> `pocketLoopPush`、`pocketCoverPush`(3)、`chatNovelPush`(4)、`welfarePush`(10)、`announcementPush`、
> `popupPush`、`versionPush`、`minipChatNovelPush`(4)、`fanNovelHomePush`、`homeFloatPush`(1)、
> `firstChargePush`、`chatnovelbannerPush`(10)、`comicCustomizePush`、`compositionbannerPush`(12)、
> `roleBanner`、`novelChatNovelSecondBanner`、`bottomButton`、`homeBroadcastPush`、`homeBottomPush`、
> `bookMarkPush`、`homeTopRreshenPush`(1)、`homeBottomTabPush`、`myBanner`(1)、`interactNovel`(4)、
> `recomposeIp`、`mutualnovel`、`mutualnovelMore`(100)、`chatNovelHotbanners`(5)、`chatNovelHotEditor`(6)、
> `chatNovelHotDaily`(6)、`chatNovelHotType`、`chatNovelHotLooking`(10)、`chatNovelNewHot`(6)、
> `chatNovelNewPotential`(6)、`chatNovelNewWin`(5)、`chatNovelFinishHighPoint`(6)、`chatNovelFinishGood`(6)、
> `merchPush`、`entityDetailPush`、`newbiepackagePush`、`entityLastPagePush`、`bigBrainPush`、
> `signPush`、`newSignInPush`、`contest2Push`、`boluoBannerPush`（括号内为实测非空条数）。

`chatNovel*` 系列是对话小说的榜位（日榜 `chatNovelHotDaily`、编辑推荐、分类榜、新书热门/潜力/获奖等），
PC 端 HTML5 侧无对应端点。`GET /novels/specialpushs` 传 `pushNames=hotpush` 返回键是 `hotPush`（驼峰），
`bigBrainPush` 同名，其余位代码须走 `/specialpush`。全局日/周/月榜（`dayRank`/`weekRank`/`monthRank`）
在 App API 里**没有对应端点**（既不在 pushNames 中，`filter=dayRank` 也返回 0 条）；PC 端来源见
[`sfacg-live-ranks.md`](./sfacg-live-ranks.md)。

---

## 5. 三个能力突破

### 5.1 定年：`addTime` 精确到秒

定年体系（`lib/eras.py`）此前靠 `log(nid) ↔ day` 分段线性反推（现 281 个锚点、留一法 p90 3 天）；
App 的 `addTime` 是**官方建档时刻**，可直接取用。第三方观测站 `book.l66526652.top` 的 `published_at`
自述同源（`sfacg_app.addTime`），与本项目锚点**同源同义**，可作独立旁证。

| 样本 | 区间 | 误差中位 | P90 | P99 | max | ≤30 天 | 有符号均值 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **31,229 条（全量）** | nid 697,226–774,759（锚点区内插段） | **2 天** | 7 天 | **9 天** | **10 天** | 100% | **+0.5 天** |
| └ high 置信度段 | 6,483 条 | 1 天 | 2 天 | — | 3 天 | 100% | — |
| └ mid 置信度段 | 24,746 条 | 3 天 | 7 天 | — | 10 天 | 100% | — |
| 601 条 | nid 785,945–789,242（锚点区外推段） | 132 天 | 147 天 | 153 天 | 153 天 | 0% | −132 天 |

- 全量 P99 = 9 天，比留一法的 P99 = 50 天好一个量级——50 天是稀疏锚点区的悲观估计。几乎无系统偏差
  （+0.5 天），但子区间会局部反向偏移（2024-04~07 段 −4.5 天），**不能把偏差当全局常数校正**。
- 外推段误差 132–153 天、**不可用**，`addTime` 的价值正是补上这一段。锚点区误差上界 10 天是硬事实。

**双源一致性**（2026-11-17，重叠 10,726 本）：完全相同 10,726/10,726 = 100.00%，差值只有 `+0 天`、
最大绝对差 0 天——两个独立通路逐秒完全一致，不存在转述失真。
复现：`probe_external_dates.py --collect --from 2024-04-12 --to 2026-05-01` 与 `--compare`（该站观测史
始于 2024-04-12，`page_size` 上限 50、`page` 有效、`offset` 无效）；一致性校验 `probe_addtime_consistency.py`。

### 5.2 点击数：精确整数

PC 版人气显示到 `0.1 万`（步长 1,000、±500），本项目据此取消了点击变化观测与点击涨幅榜
（05 §3.4、03 §4.7、07 §4.3）。App 的 `viewTimes` 是**精确整数**（示例 33,353,509），该限制不成立。
但 **App API 只给当期快照、无历史回溯，点击涨幅必须自建时序**（§5.4）；此前基于 PC 量化误差取消
点击观测的结论需据此重新评估。

### 5.3 章节级时间戳 → 更新热力图的精确数据源

07 §4.5.1 的归因规则是为对付**观测间隔**设计的近似方案；章节级 `addTime` 直接给出每章日期。
实测 nid 730611（《恶役少爷怎么可能会是圣女？》）：744 章、覆盖 682 自然日、2024-12-27→2026-11-17、
区间内无章节 9/691、连续断更 2026-04-16~04-23（7 天）、近 8 日每日 1 章 4,016–4,034 字。
即**日更字数与断更都可精确到天**，「数据缺口」概念在有章节数据时不存在。

章节列表三个约束（2026-11-17）：**数量无上限**（744/1,568/1,740 章均一次返回，`page`/`size` 无效）、
`addTime` 零缺失且 `isRubbish` 全 0、`auditStatus` 仅见 `1`/`−1`（语义待查，推测 `−1` 正常、
`1` 待审或标记态；待审章节是否计入官方全勤未知，推算时须单独标出）、744 章 222 KB / 1,740 章 489 KB。

### 5.4 时序仍须自建，但成本降 22 倍

**App API 不提供历史时序**——`/history`、`/trend`、`/statistics`、`/rank/history`、`/chaps/statistics`
全返回空，所有指标都是**当期快照**。这不改变 07「订阅式后台抓取以积累时序」的结论，但把每次抓取
代价压到极低：单本 0.7 KB（PC 移动版 15.7 KB，降 22 倍）；逐章时间戳结构化（首次 222–489 KB 快照、
之后 0.7 KB 增量）。端上「定期重抓 + 章节快照」可行。

### 5.5 全勤计数的口径差距可收窄

官方全勤按**正常章节正文**计字数（07 §2.5）。此前只有详情页总字数（含人设/背景/百科），判「可能高估」；
章节 `charCount` 是正文口径、接近官方计法，但仍非官方结算数据，判定须标注「估算、非官方判定」。

---

## 6. 合规边界

- **只取书目元数据**：nid、标题、作者、收藏、点击、字数、状态、时间戳、章节清单。
- **不取正文**：`/Chaps/{id}?expand=content` 无权限（401/507），不尝试绕过。
- **不登录、不使用任何用户 cookie**；不使用任何他人账号；`authorization` 是 App 内置固定常量。
- 串行 + 间隔 ≥0.5 s，不做高频抓取或压力测试。数据版权归菠萝包，**不得转售**。

---

## 7. 与 PC 端通路的取舍

| 维度 | PC HTML（`m.sfacg.com`） | App API（`api.sfacg.com`） |
| --- | --- | --- |
| 单本体积 | 15 KB（移动版）/ 73 KB（PC 版） | **0.7 KB** |
| 建档时间 | 无 | **有（精确到秒）** |
| 点击数 | `11899.5万` 量化（±500） | **精确整数** |
| 章节清单 | 需解析目录 HTML | **结构化 JSON** |
| 榜单 | `MonthlyBoy.ashx`（可回溯任意月） | `/specialpush` 位表 + `ticket/rank`（当期） |
| 认证 | 无（公开页面） | 内置固定凭据 + 自签 |
| 失败模式 | 软 404（HTTP 200 + 文案） | `status.httpCode` 417/401/507，HTTP 仍 200 |

**结论**：书目元数据优先走 App API；需历史回溯的月度榜仍走 PC 端 `MonthlyBoy.ashx`。两者互补、非替代。

---

## 8. 待查（开放问题）

1. `/novels` 深翻页的**排序语义**与可达最大页号——决定它能否替代 PC 的 `novelbytype` 枚举。
2. `filter` 的完整取值表：已知 `recom` 有效，`dayRank`/`hot`/`new`/`ticket` 返回 0 条。
3. 搜索端点的 `size` 上限与总命中数（实测 `size=20` 返回 18 条，原因待查）。
4. `signStatus` 的完整取值集（已见 `VIP`）。
5. `auditStatus` 的 `1`/`−1` 语义，及待审章节是否计入官方全勤判定（§5.3）。
6. 章节 `addTime` 与 `updateTime` 的差异——已发布书是否恒等、修改过的章节如何表现。

---

## 9. 相关文件

- 探针：`analysis/fetchers/probe_sfacg_app_api.py`（自包含，仅依赖 `requests`）
- 外部日期交叉校验：`analysis/fetchers/probe_external_dates.py`
- PC 端档案：[`sfacg-endpoints.md`](./sfacg-endpoints.md)；月度榜档案：[`sfacg-live-ranks.md`](./sfacg-live-ranks.md)
- 上游端点清单（第三方，含 `adpworks` 与各 `expand` 枚举）：
  https://github.com/zymelaii/ubook-rs/blob/master/doc/api.md

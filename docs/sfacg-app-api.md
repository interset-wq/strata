# SFACG 官方移动端 App API 事实档案（api.sfacg.com）

> **权威性**：本文是 `api.sfacg.com`（SFACG 官方 iOS/Android App 后端）的**唯一事实档案**，
> 与 [`sfacg-endpoints.md`](./sfacg-endpoints.md)（PC 端 HTML + `HTML5.ashx`）互为补充。
> 动手前先读本文，**不要猜参数、不要试探性请求**。
>
> **实测日期**：2026-11-17　**实测网络**：Windows 本机直连 `api.sfacg.com` 可达
> **可复现脚本**：`analysis/fetchers/probe_sfacg_app_api.py`

---

## 0. 结论摘要

| # | 结论                                                                                           | 影响                                                             |
| - | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 1 | **App API 无需用户账号即可访问公开数据**，认证用 App 内置的固定凭据 + 每次请求自签       | 端上抓取的可行性前提，比 PC HTML 干净得多                        |
| 2 | **`GET /novels/{id}` 单请求 700 B 返回 19 个字段**，含**精确到秒的 `addTime`** | 定年不再依赖 `log(nid)` 反推，可直接取官方上架时刻             |
| 3 | **`viewTimes` 是精确整数**（不是 PC 版的「万」量化）                                   | 推翻了「点击变化不可观测」的结论（05 §3.4）                     |
| 4 | **`GET /novels/{id}/chaps` 返回逐章 `addTime` + `charCount`**                      | 更新热力图与全勤看板有了**精确数据源**，不必靠观测差值推断 |
| 5 | `GET /specialpush` 返回 **77 个推送位**（42 个非空）                                   | App 首页/榜位的完整位代码表                                      |
| 6 | **App API 不提供历史时序**（`history`/`trend`/`statistics` 全空）                  | 时序仍须自建，但每次抓取只要 0.7 KB（PC 版 15.7 KB，降 22 倍）   |

> **正文不取**：`GET /Chaps/{id}?expand=content` 实测 **401 / errorCode 507「没有访问接口的权限」**，
> 无需也无法绕过。本档案只覆盖书目元数据。

---

## 1. 认证机制（实测）

App 用**固定的内置凭据 + 每次请求自签**，不需要用户账号即可访问公开数据端点。

| 项                | 值 / 规则                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------- |
| `authorization` | `Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE=`（解码 = `androiduser:1a1$51-yt697;*AJ7Bpxq4`） |
| `accept`        | `application/vnd.sfacg.api+json;version=1`                                                            |
| `user-agent`    | `boluobao/5.0.36(android;32)/H5/{device_token}/H5`                                                    |
| `sfsecurity`    | `nonce={uuid4大写}&timestamp={unix毫秒}&devicetoken={uuid4大写}&sign={md5大写}`                       |
| `sign`          | `md5(nonce + timestamp + devicetoken + SALT)`，`SALT = "FN_Q29XHVmfV3mYX"`                          |
| `nonce`         | **客户端自造的 UUID**，不是服务器领取的                                                           |
| `device_token`  | **客户端自造的 UUID**                                                                             |

**要点**：

- `nonce` 与 `device_token` 每次请求重新生成即可，服务器只校验签名。
- **签名错误返回 `status.httpCode = 417`**，而 HTTP 状态码仍是 200 —— 与 PC 端「无效 nid 返 200」
  是同类陷阱，必须读 JSON 里的 `status.httpCode`。
- `authorization` 的 Basic 凭据是 **App 客户端内置的固定常量**（所有 App 用户共用同一套），
  **不是任何用户的私密凭据**。
- 凭据来源：公开第三方实现（GitHub `fengyinxia/sfacg`、`duongden/sfacg_downloader`、
  `Illustar0/SF_AutoCheckIn`、`zymelaii/ubook-rs`、`qingscroll/QingJuan` 等），彼此一致。
- 另有**两代签名算法**：上述 md5 简单式；`duongden/sfacg_downloader` 用的是 nonce 重排 + 异或的复杂式。
  简单式实测可用，优先用它。
- 参考实现：`zymelaii/ubook-rs` 的 `doc/api.md` 是目前最完整的端点清单（57 个端点）。

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

## 2. 端点总表（2026-11-17 实测）

复现：`uv run python analysis/fetchers/probe_sfacg_app_api.py --endpoints`

| 端点                                                    | HTTP          | 备注                                                              |
| ------------------------------------------------------- | ------------- | ----------------------------------------------------------------- |
| `GET /novels/{id}`                                    | 200           | **19 字段，含 `addTime`/`viewTimes`**                   |
| `GET /novels?tid={类型}&size=50&page=0`               | 200           | 分类枚举，`size` 上限 50                                        |
| `GET /novels?size=50&page=0`                          | 200           | 全库列表（`tid` 默认 −1）                                      |
| `GET /novels?filter=recom&size=50`                    | 200           | 首页推荐，实测返回 20 条                                          |
| `GET /search/novels/result?q=&size=&page=`            | 200           | 搜索小说，返回 `{novels, comics, albums}`                       |
| `GET /search/any/result?q=&size=&page=`               | 200           | 搜索任意作品（同上结构）                                          |
| `GET /novels/specialpushs?pushNames=&size=`           | 200           | 特别推送列表；`pushNames` 可逗号分隔                            |
| `GET /specialpush`                                    | 200           | **全部 77 个推送位**                                        |
| `GET /novels/{id}/dirs`                               | 200           | 目录 → `{novelId, lastUpdateTime, volumeList}`                 |
| `GET /novels/{id}/volumes`                            | 200           | 分卷列表，字段 `{sno, title, volumeId}`                         |
| `GET /novels/{id}/chaps`                              | 200           | **逐章列表，含 `addTime`/`charCount`**                  |
| `GET /novels/{id}/cmts?page=&size=`                   | 200           | 简评，含 `createTime`/`favCount`/`replyNum`/`isStick`     |
| `GET /novels/{id}/fans`                               | 200           | 粉丝榜，字段含 `fansPoint`/`nickName`/`vipLevel`            |
| `GET /novels/{id}/ticket/rank?numMax=&dateRange=`     | 200           | 月票排名，`dateRange`：0 周 / 1 月 / 2 总                       |
| `GET /novels/{id}/bonus/rank?numMax=&dateRange=`      | 200           | 打赏排名，`dateRange=1` 月度                                    |
| `GET /novels/{id}/actpushes?filter=android&pageType=` | 200           | 书内活动推送，实测 `pageType=0` 为空                            |
| `GET /novels/{id}/reviews`                            | **404** | `zymelaii/ubook-rs/doc/api.md` 记的路径无效（书评端点另在别处） |
| `GET /Chaps/{id}?expand=content`                      | **401** | errorCode 507「没有访问接口的权限」——**正文不可取**       |
| `GET /user`                                           | **401** | 「需要登录才能访问该资源」                                        |

### 2.1 分类枚举参数

`GET /novels` 的 `tid` 取值（与 PC 端 `novelbytype` 的九类一致）：

`−1` 全部、`9` 爱情、`21` 魔幻、`22` 玄幻、`23` 古风、`24` 科幻、`25` 校园、`26` 都市、
`27` 游戏、`29` 悬疑

`categoryId`：`−1` 全部、`0` 非同人文、`1` 同人文（含类型为同人文或系统标签含「同人」）。

> **对比 PC 端**：`op=novelbytype` 需 POST + Referer，42,568 页枚举出 255,408 个目录槽位。
> App 端 `/novels` 结构化得多，但**两者的枚举边界是否一致尚未验证**——不要混用结论。

---

## 3. 字段字典

### 3.1 小说详情 / 列表条目的 19 字段

> **字段与本项目数据列的实测对应关系见 [`api-field-mapping.md`](./api-field-mapping.md)**
> （110,365 本配对现算，含一致率、值映射、写回约束）。下表「本项目对应」列已按该分析修正
> `point`/`bgBanner` 两处误映射。

| App 字段           | 类型  | 本项目对应             | 说明                                                                               |
| ------------------ | ----- | ---------------------- | ---------------------------------------------------------------------------------- |
| `novelId`        | int   | `id`                 | 主键                                                                               |
| `novelName`      | str   | `title`              | 标题                                                                               |
| `authorId`       | int   | —                     | 作者 id（**新增维度**，可做作者生态）                                        |
| `authorName`     | str   | `author`             | 作者名                                                                             |
| `addTime`        | str   | —                     | **上架时间，精确到秒**（`2024-12-27T19:03:11`）                            |
| `lastUpdateTime` | str   | `updated_at`         | 最后更新时间，精确到秒                                                             |
| `markCount`      | int   | `favs`               | 收藏数（精确整数）                                                                 |
| `viewTimes`      | int   | `clicks`             | 浏览/点击数（**精确整数**，非「万」量化）                                    |
| `charCount`      | int   | `words`              | 字数（**含全部内容**，见 §5.4 口径提醒）                                    |
| `isFinish`       | bool  | `status`             | 是否完结                                                                           |
| `signStatus`     | str   | `price_type`         | `VIP` 等签约状态                                                                 |
| `typeId`         | int   | `genre`              | 类型 id（见 §2.1）                                                                |
| `categoryId`     | int   | —                     | 0 非同人 / 1 同人                                                                  |
| `isSensitive`    | bool  | —                     | 敏感标记                                                                           |
| `novelCover`     | str   | `cover_url`          | 封面 URL（**含 `YYYY/MM/` 目录 → 仍是运营时间，见报告 01 §封面时间戳**） |
| `bgBanner`       | str   | **`featured`** | 横幅图 URL，仅 0.3% 非空，可以通过id拼接得到                                       |
| `allowDown`      | bool  | —                     | 历史遗留字段                                                                       |
| `point`          | float | —                     | 历史遗留字段                                                                       |

### 3.2 章节列表的 15 字段

`GET /novels/{id}/chaps` 每章：

| 字段                                 | 说明                                             |
| ------------------------------------ | ------------------------------------------------ |
| `chapId`                           | 章节 id                                          |
| `title` / `ntitle`               | 章节标题                                         |
| `sno` / `chapOrder` / `rowNum` | 排序号                                           |
| `volumeId`                         | 所属分卷                                         |
| **`addTime`**                | **章节创建时间**（精确到秒）               |
| **`updateTime`**             | 章节更新时间                                     |
| **`charCount`**              | **本章字数**（正文口径，接近官方全勤计法） |
| `isVip`                            | 是否 VIP 章节                                    |
| `isRubbish`                        | 是否废章                                         |
| `auditStatus`                      | 审核状态                                         |
| `expand`                           | 展开标记                                         |

### 3.3 评论 / 粉丝字段

`GET /novels/{id}/cmts`：`commentId`、`content`、`createTime`、`favCount`、`replyNum`、
`ticketNum`、`isStick`、`accountId`、`displayName`、`roleName`、`vipLevel`、`diyaMember`。

`GET /novels/{id}/fans`：`accountId`、`nickName`、`userName`、`fansPoint`、`levelName`、`vipLevel`。

---

## 4. 推送位（77 个）

`GET /specialpush` 返回 77 个位代码，**42 个当前非空**。位代码表（本项目此前只知「11 个 App 榜」
的名字、不知代码）：

> `novelSpecialSubject`（当期封面推荐，如 `2026.11.14封面推荐`）、`homePush`(10)、`vipPush`(4)、
> `homeSecondPush`、`pocketLoopPush`、`pocketCoverPush`(3)、`chatNovelPush`(4)、`welfarePush`(10)、
> `announcementPush`、`popupPush`、`versionPush`、`minipChatNovelPush`(4)、`fanNovelHomePush`、
> `homeFloatPush`(1)、`firstChargePush`、`chatnovelbannerPush`(10)、`comicCustomizePush`、
> `compositionbannerPush`(12)、`roleBanner`、`novelChatNovelSecondBanner`、`bottomButton`、
> `homeBroadcastPush`、`homeBottomPush`、`bookMarkPush`、`homeTopRreshenPush`(1)、
> `homeBottomTabPush`、`myBanner`(1)、`interactNovel`(4)、`recomposeIp`、`mutualnovel`、
> `mutualnovelMore`(100)、`chatNovelHotbanners`(5)、`chatNovelHotEditor`(6)、`chatNovelHotDaily`(6)、
> `chatNovelHotType`、`chatNovelHotLooking`(10)、`chatNovelNewHot`(6)、`chatNovelNewPotential`(6)、
> `chatNovelNewWin`(5)、`chatNovelFinishHighPoint`(6)、`chatNovelFinishGood`(6)、`merchPush`、
> `entityDetailPush`、`newbiepackagePush`、`entityLastPagePush`、`bigBrainPush`、`signPush`、
> `newSignInPush`、`contest2Push`、`boluoBannerPush`（括号内为实测非空条数）。

**`chatNovel*` 系列是对话小说的榜位**（日榜 `chatNovelHotDaily`、编辑推荐、分类榜、
新书热门/潜力/获奖等）——PC 端 HTML5 侧无对应端点。

### 4.1 `GET /novels/specialpushs` 的 pushNames 映射

传 `pushNames=hotpush` 返回的键是 **`hotPush`**（驼峰），`bigBrainPush` 同名。
其余位代码经该端点取不到，须走 `/specialpush`。

> **未找到**：全局日榜/周榜/月榜（`dayRank`/`weekRank`/`monthRank`）在 App API 里**没有对应端点**
> —— 既不在 `specialpushs` 的 pushNames 中，`/novels?filter=` 也不认（`filter=dayRank` 返回 0 条）。
> 这三类榜在 PC 端另有来源（`MonthlyBoy.ashx`，见
> [`sfacg-live-ranks.md`](./sfacg-live-ranks.md)）。

---

## 5. 三个能力突破

### 5.1 定年：`addTime` 精确到秒

定年体系（`lib/eras.py`）此前靠 `log(nid) ↔ day` 分段线性反推，104 个锚点、LOO P99 = 50 天。
App API 的 `addTime` 是**官方建档时刻**，可直接取用。

**外部交叉校验结果**（第三方观测站 `book.l66526652.top` 的 `published_at`，
自述 basis = `sfacg_app.addTime`，与本项目锚点字段**同源同义**）：

| 样本                        | 区间                                           | 误差中位       | P90    | P99            | max             | ≤1 天          | ≤30 天        | 有符号均值        |
| --------------------------- | ---------------------------------------------- | -------------- | ------ | -------------- | --------------- | --------------- | -------------- | ----------------- |
| **31,229 条（全量）** | nid 697,226–774,759（**锚点区内插段**） | **2 天** | 7 天   | **9 天** | **10 天** | **39.2%** | **100%** | **+0.5 天** |
| └ 其中 high 置信度段       | 6,483 条                                       | **1 天** | 2 天   | —             | 3 天            | —              | 100%           | —                |
| └ 其中 mid 置信度段        | 24,746 条                                      | 3 天           | 7 天   | —             | 10 天           | —              | 100%           | —                |
| 601 条                      | nid 785,945–789,242（**锚点区外推段**） | 132 天         | 147 天 | 153 天         | 153 天          | 0%              | 0%             | −132 天          |

- **实测误差比 LOO 的 P99 = 50 天好一个量级**（全量 P99 = 9 天），
  说明 50 天是留一法在稀疏锚点区的悲观估计，模型本身在锚点覆盖区是准的。
- **几乎无系统偏差**（有符号均值 +0.5 天）。注意子区间会呈相反方向的局部偏移
  （2024-04~07 段为 −4.5 天），因此**不能把偏差当成全局常数去校正**。
- 外推段（nid 超过锚点上限 774,850）误差 132–153 天，**不可用**——`addTime` 的价值正是补上这一段。
- **锚点区的误差上界 10 天是硬事实**：这是当前 `log(nid)` 反推定年的真实精度，
  比档案原先记的 P99 = 50 天乐观得多地好。

> 复现：`analysis/fetchers/probe_external_dates.py --collect --from 2024-04-12 --to 2026-05-01`
> 与 `--compare`。采集走该站 `/api/publication-calendar`，该站观测史始于 **2024-04-12**
> （更早日期 `total=0`），`page_size` 硬上限 50、`page` 有效、`offset` 无效。

#### 5.1.1 双源一致性验证

第三方站的 `published_at` 是**转述**（它自述来自 App API），必须验证它是否忠实。
实测（2026-11-17，重叠 10,726 本 nid）：

| 项         | 值                                  |
| ---------- | ----------------------------------- |
| 完全相同   | **10,726 / 10,726 = 100.00%** |
| 差值分布   | 只有 `+0 天` 一种                 |
| 最大绝对差 | **0 天**                      |

**两个独立通路逐秒完全一致** → 第三方站数据可作为 App API 的独立旁证，
两个来源互相印证，不存在"转述失真"。

> 复现：`analysis/fetchers/probe_addtime_consistency.py`

### 5.2 点击数：精确整数

PC 版人气显示到 `0.1 万`（步长 1,000、±500），本项目据此**取消了点击变化观测与点击涨幅榜**
（05 §3.4、03 §4.7、07 §4.3）。App 的 `viewTimes` 是**精确整数**（示例 33,353,509），
该限制不成立。**相关结论需要重新评估**——但要等 App API 的历史值可回溯后才能真正落地
（见 §8 待查 3）。

### 5.3 章节级时间戳 → 更新热力图的精确数据源

07 文档 §4.5.1 的归因规则（按自然日聚合、区分「无更新」与「数据缺口」）是为了对付
**观测间隔**而设计的近似方案。章节级 `addTime` 直接给出每章日期：

实测（nid 730611，《恶役少爷怎么可能会是圣女？》）：

| 项                   | 值                                   |
| -------------------- | ------------------------------------ |
| 章节数               | 744                                  |
| 覆盖自然日           | 682 天                               |
| 日期范围             | 2024-12-27 → 2026-11-17             |
| 区间内无章节的自然日 | 9 / 691                              |
| 连续断更段           | 2026-04-16 ~ 2026-04-23（连续 7 天） |
| 近 8 日逐日          | 每日 1 章、4,016–4,034 字           |

即：**日更字数可以精确到天、断更可以精确到天**，不再需要靠「相邻观测差值」推断，
「数据缺口」这个概念在有章节数据时不存在。

**章节列表的三个实测约束**（2026-11-17）：

| 项       | 实测                                                                                                                                                                 |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 数量上限 | **无**。744 / 1,568 / 1,740 章均一次返回；`page` / `size` 参数无效（传了也返回全量）                                                                       |
| 缺失     | 三个样本的 `addTime` **零缺失**、`isRubbish` 全 0                                                                                                          |
| 审核态   | `auditStatus` 取值仅见 `1` 与 `−1`（730611: 79 / 665；247674: 12 / 1,556；48704: 5 / 1,735）——**语义待查**，推测 `−1` 为正常、`1` 为待审或标记态 |
| 体积     | 744 章 **222 KB**、1,740 章 **489 KB**（响应未压缩）                                                                                                     |

> **审核态的重要性**：`auditStatus` 若表示「未通过审核」，则待审章节**是否计入官方全勤判定未知**，
> 用章节字数推算全勤时必须把这类章节单独标出，不要静默计入。

### 5.4 时序仍须自建，但成本降 22 倍

**App API 不提供历史时序**——`/novels/{id}/history`、`/trend`、`/statistics`、
`/rank/history`、`/chaps/statistics` 全部返回空。所有指标都是**当期快照**。

这不改变 07 文档「订阅式后台抓取以积累时序」的结论，但把每次抓取的代价压到极低：

|                    | PC 移动版详情页                 | App API 详情                               |
| ------------------ | ------------------------------- | ------------------------------------------ |
| 单本体积           | 15.7 KB                         | **0.7 KB（22 倍小）**                |
| 能否拿到逐章时间戳 | 否（要另解析目录 HTML，167 KB） | **是（结构化，222–489 KB 一次性）** |

因此端上「定期重抓 + 章节快照」是可行的：一个观察对象每次约 0.7 KB 增量
\+ 首次 222 KB 章节快照。

### 5.5 全勤计数的口径差距可收窄

官方全勤按**正常章节正文**计字数（见 07 §2.5）。此前本项目只有详情页总字数
（含人设/背景/百科），因此判定「可能高估」（07 §4.5.2）。章节的 `charCount` 是**正文口径**，
与官方计法接近得多——但仍非官方结算数据，判定必须继续标注「估算、非官方判定」。

---

## 6. 合规边界（本档案与配套脚本严格遵守）

- **只取书目元数据**：nid、标题、作者、收藏、点击、字数、状态、时间戳、章节清单。
- **不取正文**：`/Chaps/{id}?expand=content` 实测无权限（401/507），不尝试绕过。
- **不登录、不使用任何用户 cookie**：`/user`、`/sessions` 等需身份端点只探测不调用。
- **不使用任何他人账号**；`authorization` 是 App 内置固定常量，非用户凭据。
- 串行 + 间隔 ≥0.5 s，不做高频抓取，不做压力测试。
- 该站数据版权归菠萝包，**不得转售**。

---

## 7. 与 PC 端通路的取舍

| 维度     | PC HTML（`m.sfacg.com`）          | App API（`api.sfacg.com`）                    |
| -------- | ----------------------------------- | ----------------------------------------------- |
| 单本体积 | 15 KB（移动版）/ 73 KB（PC 版）     | **0.7 KB**                                |
| 上架时间 | 无                                  | **有（精确到秒）**                        |
| 点击数   | `11899.5万` 量���（±500）     | **精确整数**                              |
| 章节清单 | 需解析目录 HTML                     | **结构化 JSON**                           |
| 榜单     | `MonthlyBoy.ashx`（可回溯任意月） | `/specialpush` 位表 + `ticket/rank`（当期） |
| 认证     | 无（公开页面）                      | 内置固定凭据 + 自签                             |
| 失败模式 | 软 404（HTTP 200 + 文案）           | `status.httpCode` 417/401/507，HTTP 仍 200    |

**结论**：书目元数据应优先走 App API；需要历史回溯的月度榜仍走 PC 端 `MonthlyBoy.ashx`。
两者不是替代关系，是互补关系。

---

## 8. 待查

1. `/novels` 深翻页的**排序语义**与可达最大页号——决定它能否替代 PC 的 `novelbytype` 枚举，
   以及枚举边界是否与 PC 端一致。
2. `filter` 的完整取值表：已知 `recom` 有效，`dayRank`/`hot`/`new`/`ticket` 返回 0 条，
   但可能存在别的拼写。
3. ~~`viewTimes` 等累计值是否有历史回溯~~ → **已答（2026-11-17）：没有**。
   `history` / `trend` / `statistics` / `rank/history` / `chaps/statistics` 全部返回空，
   App API 只给当期快照，**时序必须自建**（§5.4）。
4. 全局日/周/月榜（`dayRank`/`weekRank`/`monthRank`）在 App 侧的端点——
   第三方观测站转发的正是这类榜，其 `section_type` 命名说明 App 内部存在这些位，
   但公开端点未暴露。
5. 搜索端点的 `size` 上限与总命中数（实测 `size=20` 返回 18 条，原因待查）。
6. ~~`GET /novels/{id}/chaps` 是否分页/是否有数量上限~~ → **已答（2026-11-17）：无分页、无上限**，
   1,740 章一次返回，`page`/`size` 参数无效（§5.3）。
7. ~~`point`（0–10 评分）能否替代本项目的 `books.pr` 口径~~ → **已答（2026-11-18）：不能**。
   `pr` 是 `praises/favs` 赞藏比，与评分 Spearman 仅 0.1625；App 也不返回 `praises`，
   `pr` 无法靠 API 刷新。详见 [`api-field-mapping.md`](./api-field-mapping.md) §3.1。
8. `signStatus` 的完整取值集（已见 `VIP`）。
9. **`auditStatus` 的 `1` / `−1` 语义**，以及待审章节是否计入官方全勤判定（§5.3）。
10. 章节 `addTime` 与 `updateTime` 的差异——已发布书的两者是否恒等，修改过的章节如何表现。

---

## 9. 相关文件

- 探针：`analysis/fetchers/probe_sfacg_app_api.py`（自包含，仅依赖 `requests`）
- 外部日期交叉校验：`analysis/fetchers/probe_external_dates.py`
- PC 端档案：[`sfacg-endpoints.md`](./sfacg-endpoints.md)
- 月度榜档案：[`sfacg-live-ranks.md`](./sfacg-live-ranks.md)

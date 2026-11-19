# 书籍数据集（`dataset/`）

> **定位**：全量书籍目录的**唯一真源**，供 app 种子构建与后续产品使用。
> **不是分析口径**——不做授权剔除、不做存活判定、不按收藏/字数过滤，一本书都不丢。
> 报告与统计仍走 `analysis/pipeline/build_csv.py` 的 15 列宽表口径，两者不要混用。
> **来源**：`novel_hub`（`light-nook-labs/novel_hub`）的原始 jsonl 快照，内容上界 **2026-05-03**。

## 1. 目录

```
dataset/
├── build.py          唯一构建入口（零网络，纯本地转换）
├── author_ids.jsonl  nid → authorId 证据（App API 探测，用于同账号判定，见 §5）
├── README.md         本文件：口径、字段、规则、已知偏差
└── out/              构建产物（gitignore，可随时重建）
    ├── books.jsonl   每行一本书，15 字段，tags 为数组 —— 唯一真源
    ├── books.csv     同字段扁平表，tags 用 `|` 连接、banner 为 0/1（UTF-8 BOM，方便 Excel）
    ├── cleanup.jsonl 清洗审计：非法字符、授权/App API 封面覆盖、共享封面归还（153,614 行）
    └── manifest.json 输入 sha256、行数、去重数、字段表、输出 sha256
```

重建：

```bash
cd dataset && uv run python build.py
# 换批次：--src "path/meta*.jsonl" --covers cover-check/covers_raw.jsonl --version 20261101.1
```

产物体积：`books.jsonl` 96 MB / `books.csv` 45 MB，**不入库**，由源 jsonl 重建。

## 2. 当前批次（`version: 20260503.6`）

| 指标 | 值 |
|---|---:|
| 输入 | 22 个 jsonl / **249,832 行** + App API 全字段样本 114,381 行 + 逐本采集 11,367 行 + authorId 证据 55 行（sha256 见 `manifest.json`） |
| 书籍 | **248,230 本**（`nid` 2237 – 774850） |
| 合并的重复行 | 1,602 行（1,525 个 `nid` 被抓过多次） |
| 有标签的书 | 234,883 |
| **有封面** | **167,971 本（67.67%）** |
| 封面为空 | 80,259 本 = 快照默认图 36,212 本（部分已被 App API 真图覆盖）+ 共享伪影置空 47,635 本（两类有交集） |
| 授权封面覆盖 | 47 本 |

## 3. 字段（15 个，字段名沿用源 jsonl，不改名）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `nid` | int | 站内书号，主键 |
| `novel_title` | str | 书名（已清洗） |
| `author` | str | 作者署名 |
| `price_type` | str | 免费 / 签约 / VIP（快照态） |
| `contest` | str | 征文标记，空串表示非征文 |
| `genre` | str | 官方分类（主题轴，非形式轴） |
| `click_num` | int | 累计点击（跨书不可比，见 `docs/metrics-definitions.md`） |
| `word_num` | int | 字数 |
| `status` | str | 快照态（2,287 本为空，多为僵尸页） |
| `last_update` | str | 最近更新时间 `YYYY-MM-DD HH:MM:SS` |
| `praise_num` | int | 赞 |
| `like_num` | int | 收藏 |
| `cover` | str | 封面**完整 URL**，空串 = 源站默认图或无图 |
| `banner` | bool | 是否上过 banner 位 |
| `tags` | array[str] | 标签，保持源顺序，不去重 |

## 4. 规则（只有这些，不做别的）

**字符串清洗**（所有 str 字段与每个标签）：

1. Unicode **NFC** 规范化；
2. 控制符（`U+0000–U+001F`、`U+007F–U+009F`）、零宽字符（`U+200B–U+200F`）、
   行/段分隔符（`U+2028`/`U+2029`）、BOM（`U+FEFF`）**替换为空格**；
3. 连续空白折叠为单空格，去首尾空白。

本批实际命中 **5 条**（3 条 `author`、2 条 `novel_title`），明细在 `out/cleanup.jsonl`。

**重复行归并**（不是删书）：同一 `nid` 多行时，取 `last_update` **最新**的一条；
时间相同取文件中靠后的一条。等价于"这本书的最后一次抓取"。

**封面**（`cover` 保留完整 URL，不做任何前缀改写）：

- 文件名以 `default` 开头（`defaultNew.jpg`、`default[1].jpg`）→ **置为空串**，
  因为源站本就没有真封面，留着 URL 只会让下游误以为有图。本批 36,212 本。
- 授权 47 本：用 `cover-check/covers_raw.jsonl`（2026-11-17 重取）覆盖，
  这批书的封面在 jsonl 快照里可能已换图。47/47 命中，覆盖明细在 `cleanup.jsonl`。
- **App API 封面覆盖**：两份来源按「旧样本 → 新逐本采集」顺序覆盖 `cover`：
  ① `analysis/out/app_api_novels.jsonl`（2026-11-16/17 全字段样本，取 `novelCover`）；
  ② `analysis/out/cover_urls.jsonl`（2026-11-18/19 逐本采集，11,367 本）。
  合计 125,748 个 nid 提供 URL，真实封面应用 **105,927 本**（替换旧图同数）；
  采集到默认图的不覆盖，也不抹掉 5 月快照里的真实 URL。
- **共享封面 = jsonl 抓取的推荐位伪影 → 归还「同作者 nid 最大者」**（2026-11-18 定案）：
  同一 `cover` URL 被 ≥2 本书引用时，该 URL 通常是 jsonl 误取的**页面推荐位里该账号另一本书的封面**。
  真主人 = 同账号作品里 `nid` 最大者（推荐位指向最新作），其余置空。
  证据（nid 594446 / 594543 / 239797 抽样）：官网 HTML 中本书真实封面出现 2 次
  （主图位 + 缩略位）、共享图只出现 1 次（推荐位），App API `novelCover` 均返回前者。
  App API 全字段样本里的真实 URL 仅 1 组重复（同 authorId 的两本书，按规则归还 nid 较大者）。
  本批 **23,923 个共享组 → 归还 23,923 本、置空 47,635 本**（`rs` / `rss` 视为同一图床，
  按 `/NovelCover/Big/` 后的路径判重；否则种子剥掉主机后会撞路径）。
  同账号判定见 §5；`authorId` 冲突的组（真混作者）整组置空，本批 **0 组**。
- 其余封面**原样保留**，包括 `rs.sfacg.com` 与 `rss.sfacg.com` 两种主机名——
  本数据集不统一主机，下游按需自行切换。

## 5. 作者身份口径（同账号判定）

站方**不在任何列表页暴露账号 id**，名字是唯一线索，而名字的语义有两条硬规则
（2026-11-18 用户确认 + App API `authorId` 实证）：

1. **大小写不敏感**：`kola` / `KOLA` 是同一账号——nid 4131 与 5971 的 App API
   `authorId` 同为 **382**（`dataset/author_ids.jsonl`）。故作者键做 `casefold`。
2. **空格敏感**：`镜音 レン`(authorId 5780) / `镜音 レ ン`(25615)、
   `First Order`(7505) / `firstorder`(12459)、`dark digger`(16612) / `darkdigger`(39896)
   都是**不同账号**。故作者键**不去空格**（早期版本去过，已撤回；对封面归属无影响，
   但对任何作者级聚合都是错的）。
3. 不做全角折叠（NFKC）：全角/半角是否同一账号未证实，现数据无此案例。

`authorId` 是唯一权威身份，名字可改：11 个「名字不同但共用封面」的组（28 本）
逐本探测后每组单一 `authorId`，确认是**账号改名**（如 `永夜殇辰`→`十二重渊` 同为 337552、
`鱼小沫`/`酸汤咸鱼` 同为 340770），故按同账号归还封面；旧版把这类组整组置空是错的。

`authorId` 覆盖度（本批 **125,775 本**，占 50.7%）= App API 全字段样本
（`authorId`）+ 逐本采集快照（`snapshot.authorId`）+ 探测证据 55
（`dataset/author_ids.jsonl`，`nids` 见 `analysis/fetchers/probe_author_ids.py`）。
判定优先级：**已知识别冲突 > 全员已知且同 id > 名字同键 > 未知（保守置空）**。
未覆盖的书仍走名字键，故新增探测只需把结果并入 `dataset/author_ids.jsonl` 再重建。

## 6. 构建即断言

`build.py` 每次运行都校验，不满足直接失败、不产出可疑数据：

1. `nid` 无重复；
2. 所有文本字段与标签无残留控制符/零宽字符、标签无空项；
3. `cover` 要么是空串，要么是绝对 URL，且**不再有 `default*` 文件名**；
4. 授权 47 本的 `cover` 与 `cover-check` 逐条一致。

额外对拍（本次已跑，非每次）：1,525 个重复 `nid` 的 `last_update` 全部取到最大值；
CSV 前 2,000 行与 JSONL 逐字段一致。

## 7. 已知偏差

- **时点**：内容上界 2026-05-03（单向游标扫描的起点），晚于此时的上架/更新不在库内；
  授权 47 本的封面例外（2026-11-17 取）。
- **不做存活判定**：已下架/僵尸书仍在库内（`status` 为空 2,287 本），需要判活的下游
  自己按 `docs/sfacg-endpoints.md` §11.5 的三态判据处理。
- **累计值不可比**：`click_num`/`like_num` 是平台累计，混杂书龄与曝光分母，
  排序/推荐须用分位口径（`docs/metrics-definitions.md`）。
- **`cover` 空 ≠ 无书**：80,259 本为空，包含快照默认图已置空（36,212 本，部分后来又被
  App API 真图覆盖）与共享伪影置空（47,635 本），两类有交集。UI 需要默认占位。
- **唯一可信的封面来源是 App API**（114,381 条全字段样本 + 11,367 本逐本采集，
  本批应用 105,927 张真实封面）；种子 v3 的 `covers` 表只应从采集结果与本数据集的
  **唯一**封面取数，不要再从原始 jsonl 取 `cover` 字段。
- 本数据集**不含**形式（`form`）、定年（`est_date`）、分位等派生列——那些由下游构建
  （`app/tools/seedbuild/`）在种子阶段计算。

## 8. 谁在用

| 使用方 | 用途 |
| --- | --- |
| `app/tools/seedbuild/build_seed.py` | 种子 `books` 表的数据来源（下一版接这个目录） |
| `app/engine` | 详情页/搜索的兜底字段 |
| 人工核对 | `books.csv` 直接用 Excel 看 |

分析报告**不要**引用本目录：报告口径含授权剔除、universe 过滤与分位计算，
以 `analysis/out/novels.csv` 为准。

# 书籍数据集（`dataset/`）

> **定位**：全量书籍目录的**唯一真源**，供 app 种子构建与后续产品使用。
> **不是分析口径**——不做授权剔除、不做存活判定、不按收藏/字数过滤，一本书都不丢。
> 报告与统计仍走 `analysis/pipeline/build_csv.py` 的 15 列宽表口径，两者不要混用。
> **来源**：`novel_hub`（`light-nook-labs/novel_hub`）的原始 jsonl 快照，内容上界 **2026-05-03**。

## 1. 目录

```
dataset/
├── build.py          唯一构建入口（零网络，纯本地转换）
├── README.md         本文件：口径、字段、规则、已知偏差
└── out/              构建产物（gitignore，可随时重建）
    ├── books.jsonl   每行一本书，15 字段，tags 为数组 —— 唯一真源
    ├── books.csv     同字段扁平表，tags 用 `|` 连接、banner 为 0/1（UTF-8 BOM，方便 Excel）
    ├── cleanup.jsonl 清洗审计：被替换的字符、被覆盖的授权封面（52 行）
    └── manifest.json 输入 sha256、行数、去重数、字段表、输出 sha256
```

重建：

```bash
cd dataset && uv run python build.py
# 换批次：--src "path/meta*.jsonl" --covers cover-check/covers_raw.jsonl --version 20261101.1
```

产物体积：`books.jsonl` 104 MB / `books.csv` 54 MB，**不入库**，由源 jsonl 重建。

## 2. 当前批次（`version: 20260503.1`）

| 指标 | 值 |
|---|---:|
| 输入 | 22 个 jsonl / **249,832 行**（sha256 见 `manifest.json`） |
| 书籍 | **248,230 本**（`nid` 2237 – 774850） |
| 合并的重复行 | 1,602 行（1,525 个 `nid` 被抓过多次） |
| 有标签的书 | 见 `manifest.counts.with_tags` |
| 封面为空的 | 36,212 本（= 源站默认图，见 §4） |
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
- 其余封面**原样保留**，包括 `rs.sfacg.com` 与 `rss.sfacg.com` 两种主机名——
  本数据集不统一主机，下游按需自行切换。

## 5. 构建即断言

`build.py` 每次运行都校验，不满足直接失败、不产出可疑数据：

1. `nid` 无重复；
2. 所有文本字段与标签无残留控制符/零宽字符、标签无空项；
3. `cover` 要么是空串，要么是绝对 URL，且**不再有 `default*` 文件名**；
4. 授权 47 本的 `cover` 与 `cover-check` 逐条一致。

额外对拍（本次已跑，非每次）：1,525 个重复 `nid` 的 `last_update` 全部取到最大值；
CSV 前 2,000 行与 JSONL 逐字段一致。

## 6. 已知偏差

- **时点**：内容上界 2026-05-03（单向游标扫描的起点），晚于此时的上架/更新不在库内；
  授权 47 本的封面例外（2026-11-17 取）。
- **不做存活判定**：已下架/僵尸书仍在库内（`status` 为空 2,287 本），需要判活的下游
  自己按 `docs/sfacg-endpoints.md` §11.5 的三态判据处理。
- **累计值不可比**：`click_num`/`like_num` 是平台累计，混杂书龄与曝光分母，
  排序/推荐须用分位口径（`docs/metrics-definitions.md`）。
- **`cover` 空 ≠ 无书**：36,212 本是官方默认图，UI 需要默认占位；`cover-check` 那 47 本
  也说明"快照里没图"和"现在没图"是两件事。
- 本数据集**不含**形式（`form`）、定年（`est_date`）、分位等派生列——那些由下游构建
  （`app/tools/seedbuild/`）在种子阶段计算。

## 7. 谁在用

| 使用方 | 用途 |
| --- | --- |
| `app/tools/seedbuild/build_seed.py` | 种子 `books` 表的数据来源（下一版接这个目录） |
| `app/engine` | 详情页/搜索的兜底字段 |
| 人工核对 | `books.csv` 直接用 Excel 看 |

分析报告**不要**引用本目录：报告口径含授权剔除、universe 过滤与分位计算，
以 `analysis/out/novels.csv` 为准。

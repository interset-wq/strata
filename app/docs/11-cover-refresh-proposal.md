# 封面补全（11）

> **状态**：方案已定案（存 URL）、采集器已上线并真实采集中（2026-11-18：API 采集累计
> 2,107 / 10,519，今日 1/5 完成）。写回 `covers` 表待种子重建统一做。
> **红线**：不改 `books` 24 列与分位分母、不改报告 10 / 定年。
> 数字全部本地离线核算，禁止硬编码。

## 1. 缺口分层（离线实测）

| 层 | 总数 | 有封面 |
|---|---:|---:|
| 全库宽表 `novels.csv` | 245,779 | 113,965 (46.4%) |
| 种子 `books`（非授权） | 30,831 | 12,107 (39.3%) |
| 深榜表 `deep_ranks` | 14,626 | 4,103 (28.1%) |

种子缺封面 18,724 本的成因：

| 成因 | 本数 | 处置 |
|---|---:|---|
| 爬虫错配被构建期 dedup 置空（原始 jsonl 本有 URL，但属主吻合率仅 19.5%，不能直接用） | 16,976 | 按 nid 从官方源重取 |
| 源头即默认封面（文件名 `default` 开头） | 1,748 | 默认图兜底，不请求 |

## 2. 数据源

App API `GET /novels/{id}` 默认 18 字段含 `novelCover`（完整 https URL），本地 114,381 条
样本 100% 有值。原始 jsonl URL 错配不可用；第三方站已否决（无封面数据）。

合规：只取书目元数据、不取正文、不登录不用 cookie、串行 ≥0.5s；App API 为可选增强通路。

## 3. 方案（已定案：口径 A1 + 默认兜底）

1. 目标池 = 16,976 本错配置空书；其中 **6,457 本在本地 App 样本内（零请求直取）**，
   **10,519 本需请求**（逐本 `GET /novels/{nid}`，@0.5s ≈ 88 分钟全量）。
2. 存 URL 不下图片本体（下载 ≈829 MB–1.4 GB 不可行）；UI 侧 `Image.network + errorBuilder→默认图`。
3. 写回：追加只读 `covers` 表（`nid, cover_url, source, fetched_at`），不动 `books`；
   1,748 本默认封面 `cover_url` 留 NULL。
4. 47 本授权书试跑已验证（`cover-check/`，用户目验通过）。

## 4. 采集器：`analysis/fetchers/cover_queue.py`

队列模式「批量入队 → 出队 → 回填」，为 CI 分片预留接口。**一次请求全字段落盘**（2026-11-18 改造）：
成功记录附 `snapshot`（markCount/viewTimes/charCount/lastUpdateTime/isFinish/signStatus/
typeId/categoryId/addTime/authorId/bgBanner/isSensitive/allowDown 等 15 字段当期值，
对照 `docs/api-field-mapping.md`；`point` 为废弃字段直接丢弃）；App 软失败
（HTTP 200 但 `status.httpCode≠200`）按失败重试。快照只进结果 jsonl，不覆盖 `books`。

- 状态机：`skip_default`(1,748) / `done`(6,457 直取 + 已采集) / `pending` → `running` →
  `done` / `failed`（重试 3 次沉底）。
- **`out/cover_urls.jsonl` 是唯一持久进度**：队列 db（gitignore）可随时由 `enqueue` 重建，
  已采集条目不回退。
- 命令：

```bash
cd analysis
uv run python fetchers/cover_queue.py enqueue --dry-run   # 离线核算
uv run python fetchers/cover_queue.py enqueue             # 入队
uv run python fetchers/cover_queue.py status
uv run python fetchers/cover_queue.py fetch --max-requests N --delay 0.6 [--shard i/n]
uv run python fetchers/cover_queue.py fetch --nids-file LIST --results R.jsonl  # 清单模式：不读写 db
uv run python fetchers/cover_queue.py dequeue --batch 100 --out batch.json  # CI 原子出队
uv run python fetchers/cover_queue.py ack --result result.jsonl
uv run python fetchers/cover_queue.py requeue-expired --lease 600
uv run python fetchers/cover_queue.py export --snapshots PATH  # URL→out/cover_export.jsonl，快照另导
```

## 5. CI 接入（已建 `.github/workflows/cover-fetch.yml`）

结果 jsonl 是唯一持久状态，CI 不接触队列 db：`workflow_dispatch` 传入 gzip+base64 的
**nid 清单**（约 2,100 个约 7 KB，2,081 个实测 7,228 字符）→ `fetch --nids-file` 串行采 →
上传 `cover-results` artifact → 本地 `ack --result` 合并回队列。

- **并行不撞车**：本地与 CI 各取互为补集的分片（本地 `--shard 0/2`、CI 清单只放
  `nid % 2 = 1`），nid 级互斥，无需共享状态或加锁。
- **失败语义**：CI 结果只含成功记录，未采到的书在本地仍是 `pending`，下批自然重试；
  CI 侧不累加 `attempts`，永久 404 只能由本地三轮重试判定。
- **合规**：runner 与本地同样串行 `--delay 0.6`（脚本强制 ≥0.5），不并发请求同一端点。
- 落地顺序仍是 `export --snapshots` → `build_seed.py` 追加 `covers` 表。

## 6. 采集进度与已知现象（2026-11-18）

- **采集结束：10,509 / 10,519（99.90%）**，全部含 15 字段快照、无 `point` 泄漏；
  队列 `pending` 已清零，10 本永久失败（soft-fail 404，App 端已删 / 无详情）。
- 失败 10 本（`73900` `344728` `372652` `715794` `746895` `748459` `755851` `762119`
  `763135` `766089`）：本地数据集（2026-05 上界）里都有行，但 App 现在返回 404——
  属快照之后被删，**不是采集缺陷**。其中 `746895` 有 9,933 收藏，是这批里唯一的头部书。
- 74 本封面已被官方换为默认图 `defaultNew.jpg`（URL 合法，UI 兜底处理）。

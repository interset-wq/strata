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
uv run python fetchers/cover_queue.py dequeue --batch 100 --out batch.json  # CI 原子出队
uv run python fetchers/cover_queue.py ack --result result.jsonl
uv run python fetchers/cover_queue.py requeue-expired --lease 600
uv run python fetchers/cover_queue.py export --snapshots PATH  # URL→out/cover_export.jsonl，快照另导
```

## 5. CI 接入（未建 workflow）

结果 jsonl 是唯一持久状态，job 间无需传队列 db：checkout → `enqueue`（自动续采）→
`fetch --shard i/n`（按 `nid % n` 分片，无共享状态）→ 上传 artifact → 合并 `export` →
`build_seed.py` 追加 `covers` 表。

## 6. 采集进度与已知现象（2026-11-18）

- 累计 API 采集 2,107 条，全部含快照；唯一失败 nid 73900 为 App 端已删书（soft-fail 404）。
- 74 本封面已被官方换为默认图 `defaultNew.jpg`（URL 合法，UI 兜底处理）。
- 全量完成后剩余约 8,411 条待采（按 1/5/天节奏约 5 天）。

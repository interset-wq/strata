"""队列模式的种子封面补全采集器（存 URL + 一次请求的全部有用字段当期快照）。

设计目标：把一个大任务（10,519 次 `GET /novels/{nid}`）拆成可持久化的队列，
支持「批量入队 → 批量出队 → 回填」，并为后续 CI 分片执行预留接口。

## 队列模型（SQLite，sqlite3 标准库，无新依赖）

状态机：`pending → running → done | failed`（`failed` 达重试上限即沉底；
`skip_default` 表示源头就是默认封面，不请求、走端上兜底）。

- `enqueue`：离线读本地数据算出缺口，幂等入队；已回填的结果自动识别为断点续采。
  - 1,748 本默认封面 → `skip_default`（不请求）
  - 6,457 本本地样本已有官方 URL → 直接 `done`（零请求）
  - 10,519 本样本外 → `pending`（需请求）
- `dequeue --batch N [--shard i/n]`：事务内原子领取一批，置 `running`。
  `--shard` 按 `nid % n == i` 取子集，供 CI matrix 并行（无共享可变状态）。
- `ack --result FILE`：回填结果；失败按 `attempts` 重试，超限沉底。
- `requeue-expired`：把超时未 ack 的 `running` 重置为 `pending`（worker 崩溃恢复）。
- `export`：导出 `done` 的 URL 为 jsonl，供 `build_seed.py` 追加 `covers` 表；
  `--snapshots PATH` 另导出完整当期快照（见下）。
- `fetch`：单进程 convenience worker（内部循环 dequeue→请求→ack）。CI 用 dequeue/ack 分离。

## 持久化与 CI

- 队列 db = `analysis/out/cover_queue.db`（运行态，被 .gitignore 忽略，不入库）。
- **结果 jsonl 是唯一持久状态**；队列 db 每次可由 `enqueue` 从本地源 + 结果文件重建。
  CI 每次运行：checkout → `enqueue`（自动读已有结果续采）→ `fetch/dequeue` →
  上传/提交结果 jsonl。进度不依赖队列 db，故无需在 job 间传递 db。
- CI 分片：每个 job 跑 `--shard i/n`，结果各自上传，最终 job 合并后 `export`。

## 合规（继承 references/sfacg-app-api.md）

只取书目元数据，不取正文、不登录、不用用户 cookie；
认证复用 `fetch_app_api_novels.make_headers()`（App 内置固定凭据 + 自签）；
串行 + 间隔 ≥0.5s（脚本强制下限）。App API 是可选增强通路，失效即降级。

## 一次请求、全字段落盘（2026-11-18 用户定案）

每次 `GET /novels/{nid}` 返回 19 个字段，封面只是其一。成功记录在结果 jsonl
附带 `snapshot`，落盘其余有用字段的**当期值**（对照 `docs/api-field-mapping.md`）：
`markCount`(=favs) / `viewTimes`(=clicks) / `charCount`(=words) /
`lastUpdateTime`(=updated_at) / `isFinish` / `signStatus` / `typeId` /
`categoryId` / `addTime` / `authorId` / `bgBanner` / `isSensitive` / `allowDown` 等。
**`point` 采集层直接丢弃**（官方废弃：App 不展示、值集中于占位常量无区分度）。
快照只进结果 jsonl，**不就地覆盖 `books`**（分位分母/pr/定年红线见
`docs/api-field-mapping.md` §5），写回策略待拍板。

## 用法

    cd analysis
    # 0) 离线入队（不联网）；可 --dry-run 只看统计
    uv run python fetchers/cover_queue.py enqueue --dry-run
    uv run python fetchers/cover_queue.py enqueue

    # 1) 看状态
    uv run python fetchers/cover_queue.py status

    # 2a) 本地单进程采集（默认串行 0.6s；先小批量验证）
    uv run python fetchers/cover_queue.py fetch --max-requests 30 --delay 0.6

    # 2b) CI 分片：出队/请求/回填分离（出队本身不联网）
    uv run python fetchers/cover_queue.py dequeue --batch 100 --shard 0/4 --out batch.json
    #   …外部按 batch.json 请求，产出 result.jsonl…
    uv run python fetchers/cover_queue.py ack --result result.jsonl

    # 3) 导出给种子构建器（URL 表）；--snapshots 另出当期快照 jsonl
    uv run python fetchers/cover_queue.py export
    uv run python fetchers/cover_queue.py export --snapshots cover_snapshots.jsonl
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from lib import paths  # noqa: E402
import fetch_app_api_novels as F  # noqa: E402

QUEUE_DB = paths.OUT_DIR / "cover_queue.db"
RESULTS = paths.OUT_DIR / "cover_urls.jsonl"
MIN_DELAY = 0.5  # 合规下限（秒），fetch 强制 clamp

# 一次请求里除 novelCover 外要落盘的当期快照字段（docs/api-field-mapping.md §2）。
# point 官方废弃（App 不展示、96.8% 恒 6.0 无区分度）——直接丢弃。
SNAPSHOT_FIELDS = (
    "novelName", "authorId", "authorName",
    "markCount", "viewTimes", "charCount",
    "lastUpdateTime", "addTime",
    "isFinish", "signStatus", "typeId", "categoryId",
    "bgBanner", "isSensitive", "allowDown",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  nid        INTEGER PRIMARY KEY,
  title      TEXT NOT NULL,
  author     TEXT NOT NULL,
  source     TEXT NOT NULL,           -- sample | api
  status     TEXT NOT NULL,           -- pending | running | done | failed | skip_default
  cover_url  TEXT,
  http       INTEGER NOT NULL DEFAULT 0,
  error      TEXT,
  attempts   INTEGER NOT NULL DEFAULT 0,
  claimed_by TEXT,
  claimed_at REAL,
  updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_status ON jobs(status, nid);
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
"""


# ---------------------------------------------------------------- 本地核算
def _empty_cover_nids(seed_db: Path) -> set[int]:
    """种子 books 中缺封面的非授权 nid。seed.db.gz 解压到临时文件读取。"""
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "seed.db"
        with gzip.open(seed_db, "rb") as src, raw.open("wb") as dst:
            dst.write(src.read())
        con = sqlite3.connect(raw)
        try:
            rows = con.execute(
                "SELECT nid FROM books "
                "WHERE (cover_url IS NULL OR cover_url='') AND is_licensed=0"
            ).fetchall()
        finally:
            con.close()
    return {int(r[0]) for r in rows}


def _default_cover_nids(nids: set[int]) -> set[int]:
    """原始 jsonl 里封面文件名以 default 开头 → 源头无封面。"""
    out: set[int] = set()
    for fp in sorted(glob.glob(str(paths.JSONL_DIR / "meta*.jsonl"))):
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                nid = rec.get("nid")
                if nid in nids:
                    cov = (rec.get("cover") or "").rsplit("/", 1)[-1].lower()
                    if cov.startswith("default"):
                        out.add(int(nid))
    return out


def _local_sample_covers(nids: set[int]) -> dict[int, str]:
    """本地 App API 样本中已有的 novelCover（零请求可用）。"""
    out: dict[int, str] = {}
    for line in paths.APP_API_NOVELS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        nid = rec.get("nid")
        cover = rec.get("novelCover")
        if nid in nids and cover:
            out[int(nid)] = cover
    return out


def load_results(path: Path) -> dict[int, dict]:
    """已回填的完整结果记录（断点续采的持久状态）。

    返回 nid → 原始 record，重建队列时保留 source 与 fetched_at 语义。
    """
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("cover_url"):
            out[int(rec["nid"])] = rec
    return out


def _epoch(rec: dict) -> float:
    """从结果的 fetched_at 还原 epoch，失败则用当前时间。"""
    try:
        return time.mktime(time.strptime(rec["fetched_at"], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return time.time()


def append_results(path: Path, records: list[dict]) -> int:
    """把新回填的 URL 追加到结果 jsonl（进程内按 nid 去重）。

    results 是跨 CI job 的唯一持久进度；队列 db 可随时由 enqueue 重建。
    """
    fresh = [r for r in records if r.get("cover_url")]
    if not fresh:
        return 0
    known: set[int] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    known.add(int(json.loads(line)["nid"]))
                except Exception:
                    continue
    fresh = [r for r in fresh if int(r["nid"]) not in known]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in fresh:
            out = {
                "nid": int(r["nid"]),
                "cover_url": r["cover_url"],
                "source": "app_api",
                "http": int(r.get("http") or 0),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            snap = r.get("snapshot") or {}
            if snap:
                out["snapshot"] = snap
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return len(fresh)


def load_titles(seed_db: Path) -> dict[int, tuple[str, str]]:
    """从种子取 nid→(title, author)，供队列展示；不联网。"""
    with tempfile.TemporaryDirectory() as td:
        raw = Path(Path(td) / "seed.db")
        with gzip.open(seed_db, "rb") as src, raw.open("wb") as dst:
            dst.write(src.read())
        con = sqlite3.connect(raw)
        try:
            rows = con.execute("SELECT nid, title, author FROM books").fetchall()
        finally:
            con.close()
    return {int(n): (t, a or "") for n, t, a in rows}


# ---------------------------------------------------------------- 队列操作
def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    con.executescript(SCHEMA)
    return con


def cmd_enqueue(args: argparse.Namespace) -> None:
    seed = Path(args.seed)
    candidates = _empty_cover_nids(seed)
    defaults = _default_cover_nids(candidates)
    real = candidates - defaults
    local = _local_sample_covers(real)
    done_before = load_results(Path(args.results))

    con = connect(Path(args.db))
    now = time.time()
    before = {r["nid"]: r["status"] for r in con.execute("SELECT nid,status FROM jobs")}
    titles = load_titles(seed)

    def meta(nid: int) -> tuple[str, str]:
        return titles.get(nid, (f"nid={nid}", ""))

    if not args.dry_run:
        con.execute("BEGIN IMMEDIATE")
    try:
        for nid in sorted(candidates):
            title, author = meta(nid)
            updated = now
            if nid in defaults:
                status, source, cover = "skip_default", "default", None
            elif nid in done_before:
                # 已采集：保留 results 里的 URL、来源与时间，不回退
                rec = done_before[nid]
                status, cover = "done", rec["cover_url"]
                source = rec.get("source") or "app_api"
                updated = _epoch(rec)
            elif nid in local:
                status, source, cover = "done", "sample", local[nid]
            else:
                status, source, cover = "pending", "api", None
            # 队列里已 done 但 results 未落盘：从队列保留，避免进度回退
            if nid in before and before[nid] == "done" and status == "pending":
                row = con.execute(
                    "SELECT source, cover_url, updated_at FROM jobs WHERE nid=?", (nid,)
                ).fetchone()
                if row and row["cover_url"]:
                    status, source, cover, updated = (
                        "done", row["source"], row["cover_url"], row["updated_at"])
            con.execute(
                "INSERT INTO jobs(nid,title,author,source,status,cover_url,updated_at) "
                "VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(nid) DO UPDATE SET status=excluded.status, "
                "source=excluded.source, cover_url=excluded.cover_url, updated_at=excluded.updated_at "
                "WHERE jobs.status!='done' OR excluded.status='done'",
                (nid, title, author, source, status, cover, updated),
            )
        if not args.dry_run:
            con.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES('enqueued_at',?)", (str(now),)
            )
            con.commit()
    except Exception:
        if not args.dry_run:
            con.rollback()
        raise
    finally:
        con.close()

    counts = {
        "候选(种子缺封面非授权)": len(candidates),
        "默认封面兜底(skip_default)": len(defaults),
        "需补(真实URL被置空)": len(real),
        "  本地样本直取(done,零请求)": len(local),
        "  需发起请求(pending)": len(real - set(local)),
    }
    print("=== 入队核算（离线，与提案 11 一致）===")
    for k, v in counts.items():
        print(f"  {k:34s} {v:>7,d}")
    print(f"\n{'DRY-RUN：未写库' if args.dry_run else '已写入 ' + str(args.db)}")


def cmd_status(args: argparse.Namespace) -> None:
    con = connect(Path(args.db))
    rows = con.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
    total = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    enq = con.execute("SELECT value FROM meta WHERE key='enqueued_at'").fetchone()
    con.close()
    print(f"队列总数：{total:,d}")
    for r in rows:
        print(f"  {r['status']:<14s} {r['n']:>7,d}")
    if enq:
        print(f"上次入队：{time.strftime('%Y-%m-%d %H:%M', time.localtime(float(enq[0])))}")


def cmd_dequeue(args: argparse.Namespace) -> None:
    shard = None
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        if not (0 <= i < n):
            raise SystemExit(f"非法分片 {args.shard}：需 0<=i<n")
        shard = (i, n)
    con = connect(Path(args.db))
    now = time.time()
    cutoff = now - args.lease
    con.execute("BEGIN IMMEDIATE")
    try:
        sql = (
            "SELECT nid,title,author FROM jobs "
            "WHERE (status='pending' OR (status='running' AND claimed_at<?)) "
            "AND attempts<?"
        )
        params: list = [cutoff, args.max_attempts]
        if shard:
            sql += " AND nid % ? = ?"
            params += [shard[1], shard[0]]
        sql += " ORDER BY nid LIMIT ?"
        params.append(args.batch)
        rows = con.execute(sql, params).fetchall()
        items = [dict(r) for r in rows]
        if items:
            con.executemany(
                "UPDATE jobs SET status='running', claimed_by=?, claimed_at=?, updated_at=? "
                "WHERE nid=?",
                [(args.worker, now, now, it["nid"]) for it in items],
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    text = json.dumps(items, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"出队 {len(items)} 条 → {args.out}", file=sys.stderr)
    print(text)


def cmd_ack(args: argparse.Namespace) -> None:
    path = Path(args.result)
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    con = connect(Path(args.db))
    now = time.time()
    ok = fail = 0
    successes: list[dict] = []
    con.execute("BEGIN IMMEDIATE")
    try:
        for rec in records:
            nid = int(rec["nid"])
            cover = (rec.get("cover_url") or "").strip()
            http = int(rec.get("http") or 0)
            err = (rec.get("error") or "")[:300]
            if cover:
                con.execute(
                    "UPDATE jobs SET status='done', cover_url=?, http=?, error='', "
                    "claimed_by=NULL, claimed_at=NULL, updated_at=? WHERE nid=?",
                    (cover, http, now, nid),
                )
                successes.append({"nid": nid, "cover_url": cover, "http": http,
                                  "snapshot": rec.get("snapshot") or {}})
                ok += 1
            else:
                row = con.execute("SELECT attempts FROM jobs WHERE nid=?", (nid,)).fetchone()
                if row is None:
                    continue
                attempts = row["attempts"] + 1
                status = "failed" if attempts >= args.max_attempts else "pending"
                con.execute(
                    "UPDATE jobs SET status=?, attempts=?, http=?, error=?, "
                    "claimed_by=NULL, claimed_at=NULL, updated_at=? WHERE nid=?",
                    (status, attempts, http, err, now, nid),
                )
                fail += 1
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    appended = append_results(Path(args.results), successes)
    print(f"ack 完成：done={ok}, failed/retry={fail}；写入 results +{appended}")


def cmd_requeue_expired(args: argparse.Namespace) -> None:
    con = connect(Path(args.db))
    cutoff = time.time() - args.lease
    con.execute("BEGIN IMMEDIATE")
    cur = con.execute(
        "UPDATE jobs SET status='pending', claimed_by=NULL, claimed_at=NULL "
        "WHERE status='running' AND claimed_at<?",
        (cutoff,),
    )
    con.commit()
    n = cur.rowcount
    con.close()
    print(f"重置超时 running → pending：{n} 条")


def cmd_export(args: argparse.Namespace) -> None:
    # 快照来源=结果 jsonl（唯一持久状态），先读后写，避免 out 覆盖 results
    snap_records = []
    if getattr(args, "snapshots", None):
        for rec in load_results(Path(args.results)).values():
            snap = rec.get("snapshot") or {}
            if snap:
                snap_records.append({"nid": rec["nid"], "fetched_at": rec.get("fetched_at"),
                                     "snapshot": snap})
    con = connect(Path(args.db))
    rows = con.execute(
        "SELECT nid, cover_url, source, updated_at FROM jobs "
        "WHERE status='done' AND cover_url IS NOT NULL ORDER BY nid"
    ).fetchall()
    con.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({
                "nid": r["nid"],
                "cover_url": r["cover_url"],
                "source": r["source"],
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(r["updated_at"])),
            }, ensure_ascii=False) + "\n")
    print(f"导出 {len(rows):,d} 条 URL → {out}")
    # 可选：另导出成功记录的完整当期快照（来源=结果 jsonl，db 不存快照列）
    if snap_records:
        sp = Path(args.snapshots)
        sp.parent.mkdir(parents=True, exist_ok=True)
        with sp.open("w", encoding="utf-8") as fh:
            for s in sorted(snap_records, key=lambda x: x["nid"]):
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"导出 {len(snap_records):,d} 条当期快照 → {sp}")


def _fetch_one(session: requests.Session, nid: int, timeout: float) -> dict:
    """请求单本详情：封面 + 当期快照（一次请求全字段落盘）。

    App 软失败（HTTP 200 但 status.httpCode≠200）按失败处理，交队列重试。
    """
    rec: dict = {"nid": nid, "cover_url": "", "http": 0, "error": "", "snapshot": {}}
    try:
        r = session.get(f"{F.API.rstrip('/')}/{nid}", timeout=timeout)
        rec["http"] = r.status_code
        body = r.json() or {}
        biz = int(((body.get("status") or {}).get("httpCode")) or 0)
        if biz and biz != 200:
            msg = (body.get("status") or {}).get("msg") or ""
            rec["error"] = f"soft-fail httpCode={biz} {msg}".strip()[:300]
            return rec
        data = body.get("data") or {}
        rec["cover_url"] = data.get("novelCover") or ""
        rec["snapshot"] = {k: data[k] for k in SNAPSHOT_FIELDS if k in data}
        if not rec["cover_url"]:
            rec["error"] = "no novelCover"
    except Exception as exc:  # noqa: BLE001 - 单本失败不中断整轮
        rec["error"] = str(exc)[:300]
    return rec


def _fetch_chunk(session: requests.Session, nids: list[int],
                delay: float, timeout: float, dry_run: bool) -> list[dict]:
    results = []
    for nid in nids:
        if dry_run:
            results.append({"nid": nid, "cover_url": "", "http": 0, "error": "dry-run"})
            continue
        results.append(_fetch_one(session, nid, timeout))
        time.sleep(delay)
    return results


def _load_nids_file(path: Path, shard: tuple[int, int] | None, limit: int) -> list[int]:
    """读取待抓 nid 清单（每行或空白分隔），去重、按分片过滤、截断。"""
    seen: set[int] = set()
    nids: list[int] = []
    for token in Path(path).read_text(encoding="utf-8").split():
        try:
            nid = int(token)
        except ValueError:
            continue
        if nid in seen:
            continue
        seen.add(nid)
        nids.append(nid)
    if shard:
        nids = [n for n in nids if n % shard[1] == shard[0]]
    return nids[:limit]


def cmd_fetch(args: argparse.Namespace) -> None:
    delay = max(args.delay, MIN_DELAY)
    if args.delay < MIN_DELAY:
        print(f"间隔 {args.delay}s 低于合规下限，已按 {MIN_DELAY}s 执行")
    shard = None
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        if not (0 <= i < n):
            raise SystemExit(f"非法分片 {args.shard}：需 0<=i<n")
        shard = (i, n)
    session = requests.Session()
    session.headers.update(F.make_headers())
    # 清单模式：不发 db、不认领，结果只追加 results（跨 CI job 合并回本地队列）
    list_nids = None
    if args.nids_file:
        list_nids = _load_nids_file(Path(args.nids_file), shard, args.max_requests)
        print(f"清单模式：{len(list_nids):,d} 条待请求，不读写队列 db", flush=True)
    total = 0
    while total < args.max_requests:
        batch = min(args.batch, args.max_requests - total)
        if list_nids is not None:
            nids = list_nids[total:total + batch]
            if not nids:
                print("清单已跑完，结束")
                break
            results = _fetch_chunk(session, nids, delay, args.timeout, args.dry_run)
            if not args.dry_run:
                successes = [{"nid": r["nid"], "cover_url": r["cover_url"],
                              "http": int(r.get("http") or 0),
                              "snapshot": r.get("snapshot") or {}}
                             for r in results if (r.get("cover_url") or "").strip()]
                append_results(Path(args.results), successes)
                for r in results:
                    if not (r.get("cover_url") or "").strip():
                        print(f"  失败 nid={r['nid']} http={r.get('http')} "
                              f"{r.get('error')}", flush=True)
        else:
            con = connect(Path(args.db))
            now = time.time()
            cutoff = now - args.lease
            con.execute("BEGIN IMMEDIATE")
            try:
                sql = (
                    "SELECT nid FROM jobs WHERE (status='pending' OR (status='running' AND claimed_at<?)) "
                    "AND attempts<?"
                )
                params: list = [cutoff, args.max_attempts]
                if shard:
                    sql += " AND nid % ? = ?"
                    params += [shard[1], shard[0]]
                sql += " ORDER BY nid LIMIT ?"
                params.append(batch)
                nids = [r[0] for r in con.execute(sql, params).fetchall()]
                con.executemany(
                    "UPDATE jobs SET status='running', claimed_by=?, claimed_at=?, updated_at=? WHERE nid=?",
                    [(args.worker, now, now, nid) for nid in nids],
                )
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()
            if not nids:
                print("队列已空（无 pending），结束")
                break
            results = _fetch_chunk(session, nids, delay, args.timeout, args.dry_run)
            con = connect(Path(args.db))
            now = time.time()
            successes: list[dict] = []
            con.execute("BEGIN IMMEDIATE")
            try:
                for rec in results:
                    nid = int(rec["nid"])
                    cover = (rec.get("cover_url") or "").strip()
                    if cover:
                        con.execute(
                            "UPDATE jobs SET status='done', cover_url=?, http=?, error='', "
                            "claimed_by=NULL, claimed_at=NULL, updated_at=? WHERE nid=?",
                            (cover, int(rec.get("http") or 0), now, nid),
                        )
                        successes.append({"nid": nid, "cover_url": cover,
                                          "http": int(rec.get("http") or 0),
                                          "snapshot": rec.get("snapshot") or {}})
                    else:
                        row = con.execute("SELECT attempts FROM jobs WHERE nid=?", (nid,)).fetchone()
                        attempts = (row["attempts"] + 1) if row else 1
                        status = "pending" if args.dry_run else (
                            "failed" if attempts >= args.max_attempts else "pending")
                        con.execute(
                            "UPDATE jobs SET status=?, attempts=?, http=?, error=?, "
                            "claimed_by=NULL, claimed_at=NULL, updated_at=? WHERE nid=?",
                            (status, attempts, int(rec.get("http") or 0), (rec.get("error") or "")[:300], now, nid),
                        )
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.close()
            if successes and not args.dry_run:
                append_results(Path(args.results), successes)
        total += len(nids)
        ok = sum(1 for r in results if r.get("cover_url"))
        print(f"[{total}/{args.max_requests}] 本批 {len(nids)} 条，成功 {ok}，失败 {len(nids)-ok}",
              flush=True)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--db", default=str(QUEUE_DB))
        p.add_argument("--results", default=str(RESULTS))

    p = sub.add_parser("enqueue", help="离线核算缺口并批量入队")
    common(p)
    p.add_argument("--seed", default=str(paths.ROOT.parent / "app" / "assets" / "seed.db.gz"))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_enqueue)

    p = sub.add_parser("status", help="查看队列状态")
    common(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("dequeue", help="批量原子出队（不联网）")
    common(p)
    p.add_argument("--batch", type=int, default=100)
    p.add_argument("--shard", help="CI 分片 i/n，如 0/4")
    p.add_argument("--worker", default="cli")
    p.add_argument("--lease", type=float, default=600, help="租约秒数，超时可被重新出队")
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--out", help="同时把出队 JSON 写入文件")
    p.set_defaults(func=cmd_dequeue)

    p = sub.add_parser("ack", help="批量回填结果")
    common(p)
    p.add_argument("--result", required=True,
                   help="结果 jsonl：nid/cover_url/http/error[/snapshot]")
    p.add_argument("--max-attempts", type=int, default=3)
    p.set_defaults(func=cmd_ack)

    p = sub.add_parser("requeue-expired", help="重置超时 running")
    common(p)
    p.add_argument("--lease", type=float, default=600)
    p.set_defaults(func=cmd_requeue_expired)

    p = sub.add_parser("export", help="导出已完成的 URL（--snapshots 另导当期快照）")
    common(p)
    p.add_argument("--out", default=str(paths.OUT_DIR / "cover_export.jsonl"),
                   help="URL 导出路径（默认独立文件，避免覆盖 results 持久状态）")
    p.add_argument("--snapshots", help="快照导出路径（含 markCount/viewTimes 等当期字段）")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("fetch", help="单进程 worker：出队→请求→回填")
    common(p)
    p.add_argument("--batch", type=int, default=50)
    p.add_argument("--max-requests", type=int, default=10_000)
    p.add_argument("--delay", type=float, default=0.6)
    p.add_argument("--timeout", type=float, default=25)
    p.add_argument("--shard", help="CI 分片 i/n")
    p.add_argument("--worker", default="cli")
    p.add_argument("--lease", type=float, default=600)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--nids-file", help="清单模式：只抓文件里的 nid，不读写队列 db（CI 用）")
    p.add_argument("--dry-run", action="store_true", help="出队但不发请求、不计失败")
    p.set_defaults(func=cmd_fetch)
    return ap


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

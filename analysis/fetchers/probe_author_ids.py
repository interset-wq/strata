"""探针：按 nid 取 App API 的 `authorId` / `authorName`，用于核对「同作者」判定。

背景：SFACG 用户名**不区分大小写**（用户 2026-11-18 确认），因此 `KEY` / `Key` / `key`
是同一账号；但站点从不在列表页暴露账号 id，只能靠名字推断同作者。
本探针取 `GET /novels/{nid}` 的 `authorId`（`docs/sfacg-app-api.md` §3），
给出**名字之外的权威身份**，用来验证按名字归一的判定是否会误合并 / 漏合并。

用法（串行 ≥0.5s，只取书目元数据，不取正文）：
    cd analysis
    uv run python fetchers/probe_author_ids.py --nids-file out/probe_nids.txt \
        --out out/author_id_probe.jsonl

产物每行：`nid, authorId, authorName, signStatus, isFinish, http, error`
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from lib import paths  # noqa: E402
import fetch_app_api_novels as F  # noqa: E402

MIN_DELAY = 0.5


def load_nids(args: argparse.Namespace) -> list[int]:
    tokens: list[str] = []
    if args.nids_file:
        tokens += Path(args.nids_file).read_text(encoding="utf-8").split()
    if args.nids:
        tokens += args.nids.replace(",", " ").split()
    seen: set[int] = set()
    nids: list[int] = []
    for t in tokens:
        try:
            nid = int(t)
        except ValueError:
            continue
        if nid not in seen:
            seen.add(nid)
            nids.append(nid)
    if not nids:
        raise SystemExit("没有待探测的 nid")
    return nids


def probe(session: requests.Session, nid: int, timeout: float) -> dict:
    rec = {"nid": nid, "authorId": None, "authorName": "", "signStatus": "",
           "isFinish": None, "http": 0, "error": ""}
    try:
        r = session.get(f"{F.API.rstrip('/')}/{nid}", timeout=timeout)
        rec["http"] = r.status_code
        body = r.json() or {}
        biz = int(((body.get("status") or {}).get("httpCode")) or 0)
        if biz and biz != 200:
            rec["error"] = f"soft-fail httpCode={biz} {(body.get('status') or {}).get('msg') or ''}".strip()
            return rec
        data = body.get("data") or {}
        rec["authorId"] = data.get("authorId")
        rec["authorName"] = data.get("authorName") or ""
        rec["signStatus"] = data.get("signStatus") or ""
        rec["isFinish"] = data.get("isFinish")
    except Exception as exc:  # noqa: BLE001 - 单本失败不中断
        rec["error"] = str(exc)[:200]
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nids", help="nid 列表（逗号/空格分隔）")
    ap.add_argument("--nids-file", help="每行或空白分隔的 nid 清单")
    ap.add_argument("--out", default=str(paths.OUT_DIR / "author_id_probe.jsonl"))
    ap.add_argument("--delay", type=float, default=0.6, help="请求间隔（秒，≥0.5）")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--dry-run", action="store_true", help="只列清单不请求")
    args = ap.parse_args()

    nids = load_nids(args)
    delay = max(args.delay, MIN_DELAY)
    out = Path(args.out)
    if args.dry_run:
        print(f"待探测 {len(nids)} 本 → {out}（dry-run 未请求）")
        return
    session = requests.Session()
    session.headers.update(F.make_headers())
    out.parent.mkdir(parents=True, exist_ok=True)
    ok = 0
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for i, nid in enumerate(nids, 1):
            rec = probe(session, nid, args.timeout)
            if rec["authorId"]:
                ok += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(nids)}] nid={nid} authorId={rec['authorId']} "
                  f"{rec['authorName']} {rec['error']}", flush=True)
            time.sleep(delay)
    print(f"成功 {ok}/{len(nids)} → {out}")


if __name__ == "__main__":
    main()

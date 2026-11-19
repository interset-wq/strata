"""补抓月榜遗漏书（报告 10 A 组）：上榜但不在库的 nid，逐本取 App API 详情。

## 背景

月榜 `MonthlyBoy.ashx`（2013-03 起）抓回的上榜书里，有一部分 nid 不在
`out/novels.csv`（jsonl 游标扫描遗漏，报告 10 §A：上榜时必然存活）。
这些是各世代头部书（如 5976 S.M.S-舍子花），对定年锚点、种子质量锚都有价值。

## 用法

    uv run python analysis/fetchers/fetch_rank_missing.py           # 断点续采
    uv run python analysis/fetchers/fetch_rank_missing.py --delay 0.8

## 输出

- `out/rank_missing_meta.jsonl`：App API 详情，字段同 fetch_app_api_novels.KEEP，
  另加 `rank_months`（上榜月列表）、`best_rank`、`max_tickets`。
- `out/rank_missing_summary.json`：全集核对（含已在 app_api_novels.jsonl 里的书）。

## 约束

只取书目元数据；不登录、不取正文；串行 + 间隔 ≥0.5 s（合规规则不变）。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402

from fetchers.fetch_app_api_novels import KEEP, make_headers  # noqa: E402

API = "https://api.sfacg.com/novels"
META_PATH = paths.OUT_DIR / "rank_missing_meta.jsonl"
SUMMARY_PATH = paths.OUT_DIR / "rank_missing_summary.json"


def load_rank_entries() -> dict[int, dict]:
    """nid → {name, author, months, best_rank, max_tickets}"""
    entries: dict[int, dict] = {}
    with (paths.OUT_DIR / "monthly_ranks.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            month = r["month"]
            for rank, it in enumerate(r["items"]):
                nid = int(it["nid"])
                e = entries.setdefault(
                    nid,
                    {"name": it["name"], "author": it["author"],
                     "months": [], "best_rank": rank, "max_tickets": it.get("ticketNum", 0)},
                )
                if month not in e["months"]:
                    e["months"].append(month)
                e["best_rank"] = min(e["best_rank"], rank)
                e["max_tickets"] = max(e["max_tickets"], it.get("ticketNum", 0))
    return entries


def load_lib_nids() -> set[int]:
    with (paths.OUT_DIR / "novels.csv").open(encoding="utf-8", newline="") as f:
        return {int(row["id"]) for row in csv.DictReader(f)}


def load_existing_meta() -> dict[int, dict]:
    """已抓过的（rank_missing_meta.jsonl + app_api_novels.jsonl 里的对应书）"""
    got: dict[int, dict] = {}
    if META_PATH.exists():
        for line in META_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                got[int(d["nid"])] = d
    enum_path = paths.OUT_DIR / "app_api_novels.jsonl"
    if enum_path.exists():
        for line in enum_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                nid = d.get("nid")
                if nid is not None and int(nid) not in got:
                    rec = {k: d[k] for k in KEEP if k in d}
                    rec["nid"] = int(nid)
                    rec["source"] = "app_api_novels"
                    got[int(nid)] = rec
    return got


def fetch_detail(session: requests.Session, nid: int) -> dict | None:
    """GET /Novels/{nid}，返回 KEEP 字段子集；无效/删除书返回 None。"""
    try:
        resp = session.get(f"{API}/{nid}", headers=make_headers(), timeout=25)
    except Exception as exc:  # noqa: BLE001
        print(f"  nid={nid} 请求失败：{exc}")
        return None
    if resp.status_code != 200:
        print(f"  nid={nid} HTTP {resp.status_code}")
        return None
    try:
        payload = resp.json()
    except Exception:
        return None
    status = payload.get("status", {}) or {}
    data = payload.get("data") or {}
    if status.get("httpCode") not in (200, None) or not data.get("novelId"):
        # 无效 nid 返回 200 + 文案页/空 data（状态码不可信，判活须匹配内容）
        return None
    return {k: data[k] for k in KEEP if k in data}


def main() -> None:
    ap = argparse.ArgumentParser(description="补抓月榜遗漏书元数据")
    ap.add_argument("--delay", type=float, default=0.6)
    args = ap.parse_args()

    rank = load_rank_entries()
    lib = load_lib_nids()
    missing = {n: e for n, e in rank.items() if n not in lib}
    print(f"月榜 {len(rank)} 本去重，不在库 {len(missing)} 本")

    got = load_existing_meta()
    todo = [n for n in sorted(missing) if n not in got]
    print(f"已有元数据 {len(got & missing.keys())} 本，待抓 {len(todo)} 本")

    ok = fail = 0
    if todo:
        session = requests.Session()
        with META_PATH.open("a", encoding="utf-8") as fh:
            for i, nid in enumerate(todo, 1):
                d = fetch_detail(session, nid)
                if d is None:
                    fail += 1
                else:
                    e = missing[nid]
                    d["nid"] = nid
                    d["source"] = "rank_missing"
                    d["rank_months"] = e["months"]
                    d["best_rank"] = e["best_rank"]
                    d["max_tickets"] = e["max_tickets"]
                    fh.write(json.dumps(d, ensure_ascii=False) + "\n")
                    fh.flush()
                    ok += 1
                if i % 20 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} 成功 {ok} 失败 {fail}")
                time.sleep(args.delay)

    # 汇总核对
    got = load_existing_meta()
    summary = {
        "rank_unique": len(rank),
        "missing_from_lib": len(missing),
        "meta_available": len(got & missing.keys()),
        "failed": sorted(set(missing) - set(got)),
        "note": "failed=App API 也查不到（大概率快照后被删除或下架）",
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"汇总：可用 {summary['meta_available']}，App API 查不到 "
          f"{len(summary['failed'])} → out/rank_missing_summary.json")


if __name__ == "__main__":
    main()

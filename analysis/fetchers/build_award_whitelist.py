"""生成获奖白名单锚点（种子强制入种唯一真源，2026-11-26 用户裁定）。

用户裁定：所有获奖作品「无论如何筛选，一定能进入种子」——在比赛中脱颖而出
即证明是当年优质作品。白名单 = contest-achieve `docs/data/awards.json` 的全部
verified 记录（613 行 / 609 唯一 nid），覆盖四季主线 + 独立赛事 + 对话线，
不区分 roster/award tag、不区分 form、不因 E.31/E.32/E.34/P10 等规则剔除。

    uv run --project analysis python analysis/fetchers/build_award_whitelist.py
    uv run --project analysis python analysis/fetchers/build_award_whitelist.py --check

产出 `analysis/anchors/seed_award_whitelist.jsonl`：
{nid, title, award, edition, series, contest_track_id, contest_name,
 source, verified, verified_on}。同一 nid 多次获奖（如双赛道）合并为一行，
award 字段用「/」连接。种子侧只读 nid，其余字段供审计与 manifest 留档。
数据来自 contest-achieve（AGPL-3.0），只借名单、不复制代码。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("E:/contest-achieve/docs/data/awards.json")
OUT = ROOT / "analysis" / "anchors" / "seed_award_whitelist.jsonl"

HEADER = (
    "// 获奖白名单（种子强制入种，2026-11-26 用户裁定）：所有 verified 获奖作"
    "品绕过 E.31/E.32/E.34/P10 与 form 配额，无条件入种。\n"
    "// 真源 contest-achieve/docs/data/awards.json（AGPL-3.0）；由 "
    "analysis/fetchers/build_award_whitelist.py 生成，勿手改。\n"
)


def build() -> str:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    merged: dict[int, dict] = {}
    for r in rows:
        if not r.get("verified"):
            continue
        nid = int(r["nid"])
        if nid in merged:
            prev = merged[nid]
            prev["awards"].append(str(r.get("award") or ""))
            prev["editions"].append(str(r.get("contest_name") or ""))
            continue
        merged[nid] = {
            "nid": nid,
            "title": str(r.get("title") or ""),
            "awards": [str(r.get("award") or "")],
            "editions": [str(r.get("contest_name") or "")],
            "series": str(r.get("series") or ""),
            "contest_track_id": int(r.get("contest_track_id") or 0),
            "source": str(r.get("source") or ""),
            "verified_on": str(r.get("verified_at") or ""),
        }
    lines = [HEADER.rstrip("\n")]
    for nid in sorted(merged):
        r = merged[nid]
        rec = {
            "nid": nid,
            "title": r["title"],
            "award": "/".join(a for a in r["awards"] if a),
            "edition": "/".join(e for e in r["editions"] if e),
            "series": r["series"],
            "contest_track_id": r["contest_track_id"],
            "contest_name": r["editions"][0] if r["editions"] else "",
            "source": r["source"],
            "verified": True,
            "verified_on": r["verified_on"],
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="比对现有锚点，不写文件")
    a = ap.parse_args()
    payload = build()
    if a.check:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != payload:
            print(f"FAIL: {OUT} stale; re-run without --check")
            return 1
        print(f"award whitelist up to date ({payload.count(chr(10))} lines)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload, encoding="utf-8")
    n = sum(1 for line in payload.splitlines() if line and not line.startswith("//"))
    print(f"wrote {OUT}: {n} verified award books")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

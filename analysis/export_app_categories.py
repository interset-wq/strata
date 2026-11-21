"""从 App API 快照导出 nid → categoryId 锚点，供 forms.classify 判形态。

来源：`analysis/out/app_api_novels.jsonl`（已有快照，不新增爬虫）。
产出：`analysis/anchors/app_categories.jsonl`（入库，避免依赖 out/ 产物）。

用法：cd analysis && uv run python export_app_categories.py
"""
from __future__ import annotations

import json
from pathlib import Path

from lib import paths

SRC = paths.OUT_DIR / "app_api_novels.jsonl"
DST = paths.ANCHORS_DIR / "app_categories.jsonl"


def main() -> int:
    rows = [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]
    # 同一 nid 可能多次出现在快照（分批抓取），取最后一条（最新观测）
    by_nid: dict[int, int] = {}
    for r in rows:
        cat = r.get("categoryId")
        if cat is not None:
            by_nid[int(r["novelId"])] = int(cat)
    with DST.open("w", encoding="utf-8") as f:
        for nid in sorted(by_nid):
            f.write(json.dumps({"nid": nid, "categoryId": by_nid[nid]}, ensure_ascii=False) + "\n")
    print(f"wrote {len(by_nid):,} rows -> {DST}")
    from collections import Counter
    print("distribution:", dict(sorted(Counter(by_nid.values()).items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

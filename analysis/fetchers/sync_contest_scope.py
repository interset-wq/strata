"""从 contest-achieve 同步 E.34 中短篇赛事 roster 快照（离线、无网络）。

用法：
    uv run --project analysis python analysis/fetchers/sync_contest_scope.py
    uv run --project analysis python analysis/fetchers/sync_contest_scope.py --archive E:/contest-achieve

输入 = 独立仓 `E:/contest-achieve` 的 contests.json + data/<tag>/roster.jsonl。
输出 = `analysis/anchors/contest_short_medium.json`（入库快照，seed build / 作者榜只读它）。
tag 集合变化或任一 roster 未采全即中止，避免把残缺清单当准入规则。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import contest_scope as CS  # noqa: E402
from lib import paths  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, default=CS.ARCHIVE_DEFAULT)
    ap.add_argument("--out", type=Path, default=paths.CONTEST_SHORT_MEDIUM)
    args = ap.parse_args()

    tags = CS.derive_tags(args.archive)
    rosters = CS.rosters(args.archive, tags)
    union = set().union(*rosters.values())
    obj = {
        "schema": 1,
        "source": "light-nook-labs/contest-achieve: contests.json + data/<tag>/roster.jsonl",
        "synced_on": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "tags": {k: list(v) for k, v in tags.items()},
        "tag_nids": {k: len(v) for k, v in sorted(rosters.items(), key=lambda kv: int(kv[0]))},
        "nids": sorted(union),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"synced {len(tags['short']) + len(tags['medium'])} tags, "
          f"{len(union):,} unique nids -> {args.out}")
    print(f"  short tags {tags['short']}")
    print(f"  medium tags {tags['medium']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

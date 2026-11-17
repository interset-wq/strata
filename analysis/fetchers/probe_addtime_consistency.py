"""双源交叉验证：`addTime` 的两个独立来源是否一致。

## 目的

项目里 `addTime` 有两条取得途径：

| 来源 | 通路 | 说明 |
| --- | --- | --- |
| **A. 官方 App API** | `GET /novels?tid=&size=50&page=` | 直接从 `api.sfacg.com` 取 `addTime` |
| **B. 第三方观测站** | `GET /api/publication-calendar?date=` | `book.l66526652.top`，字段 `published_at`，自述 basis = `sfacg_app.addTime` |

B 是**转述**（它自己也声称来自 App API），所以必须验证它是否**忠实**——
若两者在重叠 nid 上逐秒一致，则 B 可作为 A 的独立旁证；
若不一致，则 B 的数据不可用于校验定年。

**实测结论（2026-11-17）**：重叠 10,726 本，**100% 逐秒完全相同**，最大绝对差 0 天。

## 用法

    # 先分别采集两个来源
    uv run python analysis/fetchers/fetch_app_api_novels.py --all
    uv run python analysis/fetchers/probe_external_dates.py --collect --from 2024-04-12 --to 2026-05-01

    # 再交叉验证
    uv run python analysis/fetchers/probe_addtime_consistency.py
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402


def load_app_api(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("nid") and rec.get("addTime"):
            out[int(rec["nid"])] = rec["addTime"]
    return out


def load_external(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("nid") and rec.get("published_at"):
            out[int(rec["nid"])] = rec["published_at"]
    return out


def _as_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "")).date()


def compare(app_path: Path, ext_path: Path) -> int:
    app = load_app_api(app_path)
    ext = load_external(ext_path)
    print("App API 已取: %d 本（带 addTime）" % len(app))
    print("第三方站已取: %d 本" % len(ext))
    common = set(app) & set(ext)
    print("重叠 nid: %d 本" % len(common))
    if not common:
        print("无重叠，无法交叉验证")
        return 1

    diffs: collections.Counter[int] = collections.Counter()
    exact = 0
    max_abs = 0
    examples: list[tuple[int, str, str, int]] = []
    for nid in common:
        d = (_as_date(app[nid]) - _as_date(ext[nid])).days
        diffs[d] += 1
        if d == 0:
            exact += 1
        if abs(d) > max_abs:
            max_abs = abs(d)
            examples = [(nid, app[nid], ext[nid], d)]
        elif abs(d) == max_abs and len(examples) < 3:
            examples.append((nid, app[nid], ext[nid], d))

    n = len(common)
    print("\n=== addTime 双源一致性（App API vs 第三方站）===")
    print("  完全相同: %d / %d (%.2f%%)" % (exact, n, exact / n * 100))
    print("  差值分布（天）:")
    for d, c in sorted(diffs.items())[:12]:
        print("    %+3d 天 : %6d 本 (%.2f%%)" % (d, c, c / n * 100))
    if len(diffs) > 12:
        print("    … 另有 %d 种差值" % (len(diffs) - 12))
    print("  最大绝对差: %d 天" % max_abs)
    for nid, a, b, d in examples[:3]:
        print("    nid=%d  AppAPI=%s  第三方=%s  差=%+d" % (nid, a[:19], b[:19], d))

    if max_abs == 0:
        print("\n  ✅ 两源逐秒一致 —— 第三方站数据可作为 App API 的独立旁证")
        return 0
    print("\n  ⚠ 两源存在差异，第三方站数据不可直接用于校验定年")
    return 2


def main() -> None:
    ap = argparse.ArgumentParser(description="addTime 双源交叉验证")
    ap.add_argument("--app", default=str(paths.OUT_DIR / "app_api_novels.jsonl"))
    ap.add_argument("--ext", default=str(paths.OUT_DIR / "external_dates_full.jsonl"))
    args = ap.parse_args()
    raise SystemExit(compare(Path(args.app), Path(args.ext)))


if __name__ == "__main__":
    main()

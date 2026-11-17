"""App API 枚举结果与本地数据集的覆盖对比。

## 目的

报告 10 判定「在架覆盖率 69.3%」，但**没有给出具体该补哪些书**。
官方 App API 的 `GET /novels` 枚举能给出**官方目录当前的全量清单**，
与本地数据集（`out/novels.csv`，2026-05-03 快照）做差集，就得到：

1. **数据集漏抓的书**（App API 有、数据集无）——补爬清单；
2. **数据集有、App API 已无的书**（数据集有、App API 无）——可能已下架/移出目录，
   是判活/僵尸判据的候选证据；
3. 交集部分的一致性核对（分类、字数、收藏等字段是否漂移）。

## 用法

    uv run python analysis/fetchers/probe_app_api_coverage.py

输出：
- 终端：覆盖统计与分类分布
- `out/app_api_coverage.json`：分类级计数
- `out/app_api_missing.jsonl`：数据集漏抓的书（App API 有、数据集无），逐条带完整元数据
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

TID_NAMES = {9: "爱情", 21: "魔幻", 22: "玄幻", 23: "古风", 24: "科幻",
             25: "校园", 26: "都市", 27: "游戏", 29: "悬疑"}


def load_app(path: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("nid"):
            out[int(rec["nid"])] = rec
    return out


def load_local(path: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for rec in csv.DictReader(fh):
            out[int(rec["id"])] = rec
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="App API 枚举与数据集覆盖对比")
    ap.add_argument("--app", default=str(paths.OUT_DIR / "app_api_novels.jsonl"))
    ap.add_argument("--local", default=str(paths.OUT_DIR / "novels.csv"))
    ap.add_argument("--out", default=str(paths.OUT_DIR / "app_api_coverage.json"))
    ap.add_argument("--missing", default=str(paths.OUT_DIR / "app_api_missing.jsonl"))
    args = ap.parse_args()

    app = load_app(Path(args.app))
    local = load_local(Path(args.local))
    if not app:
        print("App API 枚举为空，先跑 fetch_app_api_novels.py")
        return
    if not local:
        print("本地数据集为空")
        return

    app_ids = set(app)
    local_ids = set(local)
    inter = app_ids & local_ids
    only_app = app_ids - local_ids
    only_local = local_ids - app_ids

    print("=== 覆盖对比 ===")
    print("  App API 枚举 : %7d 本" % len(app_ids))
    print("  本地数据集   : %7d 本（2026-05-03 快照）" % len(local_ids))
    print("  交集         : %7d 本（占枚举 %.1f%%、占数据集 %.1f%%）"
          % (len(inter), len(inter) / len(app_ids) * 100, len(inter) / len(local_ids) * 100))
    print("  **漏抓**（App 有、库无）: %5d 本" % len(only_app))
    print("  库有、App 已无           : %5d 本" % len(only_local))

    # 「漏抓」必须拆开：快照之后新建的书不算漏抓（报告 10 的同一处理）
    bound = "2026-05-03"  # 数据内容上界，analysis/lib/eras.py 的 snapshot_bounds()
    after, before = [], []
    for nid in only_app:
        at = app[nid].get("addTime") or ""
        (after if at[:10] > bound else before).append(nid)
    print("\n  漏抓拆分（按上架时间 vs 数据上界 %s）:" % bound)
    print("    快照后新建（**不算漏抓**）: %5d 本" % len(after))
    print("    快照时已存在却没抓到（真漏抓）: %5d 本" % len(before))
    if before:
        yrs = collections.Counter(app[n].get("addTime", "")[:4] for n in before)
        print("    真漏抓的年份分布:", dict(sorted(yrs.items())))

    # 分类分布
    by_tid: dict[int, dict[str, int]] = {}
    for nid in app_ids:
        tid = app[nid].get("tid") or app[nid].get("typeId")
        slot = by_tid.setdefault(str(tid), {"total": 0, "missing": 0})
        slot["total"] += 1
        if nid in only_app:
            slot["missing"] += 1

    print("\n=== 按分类（枚举总量 / 其中漏抓）===")
    for tid, slot in sorted(by_tid.items(), key=lambda kv: -kv[1]["total"]):
        name = TID_NAMES.get(int(tid), "?")
        rate = slot["missing"] / slot["total"] * 100 if slot["total"] else 0
        print("  tid=%-4s %-4s 总 %6d  漏抓 %5d (%.1f%%)"
              % (tid, name, slot["total"], slot["missing"], rate))

    # 漏抓书的 addTime 分布
    print("\n=== 漏抓书的 addTime 年份分布 ===")
    years = collections.Counter()
    for nid in only_app:
        at = app[nid].get("addTime")
        if at and len(at) >= 4:
            years[at[:4]] += 1
    for y, c in sorted(years.items()):
        print("  %s : %5d 本" % (y, c))

    # 写漏抓清单
    missing_path = Path(args.missing)
    missing_path.parent.mkdir(parents=True, exist_ok=True)
    with missing_path.open("w", encoding="utf-8") as fh:
        for nid in sorted(only_app):
            fh.write(json.dumps(app[nid], ensure_ascii=False) + "\n")
    print("\n漏抓清单 → %s（%d 条）" % (missing_path, len(only_app)))

    summary = {
        "app_api_total": len(app_ids),
        "local_total": len(local_ids),
        "intersection": len(inter),
        "missing_from_dataset": len(only_app),
        "missing_after_snapshot_bound": len(after),
        "missing_true_before_bound": len(before),
        "only_in_dataset": len(only_local),
        "by_tid": by_tid,
        "missing_by_year": dict(sorted(years.items())),
    }
    Path(args.out).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("汇总 → %s" % args.out)


if __name__ == "__main__":
    main()

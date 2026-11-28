"""Author the engine's contest-name translation table (new naming <-> legacy ledger).

Since 2026-11-27 the contest column in dataset/seed uses OUR naming
(analysis/anchors/contest_names.jsonl: 2025春征 / 崩坏3同人 / 第x届冬征 /
点鸭星穹 / 四征长篇 ...), while the embedded official ledger keeps the legacy
event names as its internal join key (2025春季征文 / 崩坏3征文 / 冬季征文 ...)
and its numbers are never recomputed. This script bridges the two: it emits
app/engine/internal/store/contest_names.json, an embed table with

  raw:    every contest spelling (new name, legacy ledger event, legacy alias)
          -> {event, series, lane}
  events: new event name -> {series, lane, legacy: [legacy ledger event, ...]}
          (legacy[0] is the primary row that supplies year/dates/official
           totals; the rest are merged only as extra tracks/tagIds)

No official number is authored or changed here: the table translates names and
points the engine at the rows that already exist in contest_ledger.json.

  python app/tools/contestledger/build_contest_names.py
  python app/tools/contestledger/build_contest_names.py --check
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAMES = ROOT / "analysis/anchors/contest_names.jsonl"
LEDGER = ROOT / "app/engine/internal/store/contest_ledger.json"
OUT = ROOT / "app/engine/internal/store/contest_names.json"

# The engine's five archive tabs (contestSeries buckets). The anchor's `series`
# is our own classification; these are the UI buckets it maps onto.
BUCKET = {
    "X征": "x",
    "春征": "spring",
    "秋征": "autumn",
    "冬征": "winter",
    "点鸭对话": "other",
    "IP同人": "other",
    "主题征文": "other",
    # 2026-11-27 用户定：秋季 tab 更名「秋季/少年」，少年系列归入 autumn。
    "少年": "autumn",
}
# Home-tab lanes, only meaningful for the "other" bucket: dialogue archives
# live in the home dialogue area, IP archives in the IP area; theme events
# stay in the archive list's 主题 tab (少年 now lives under 秋季/少年).
LANE = {"点鸭对话": "dialogue", "IP同人": "ip"}
# Edition-level lane overrides: only two theme contests are pure short-story
# competitions (user decision 2026-11-27). They leave the archive's 主题 tab
# for the home 短篇 tab, same as dialogue/IP lines. Keyed by OUR event name;
# the other six 主题征文 events keep lane="" (stay in the 主题 tab).
LANE_EVENT = {"2024主题短篇": "short", "超新星杯短篇": "short"}


def lane_for(event: str, series: str) -> str:
    return LANE_EVENT.get(event, LANE.get(series, ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed table instead of writing")
    args = ap.parse_args()

    names = [json.loads(line) for line in NAMES.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    series_of = {r["event"]: r["series"] for r in names}
    bucket_of = {ev: BUCKET[series] for ev, series in series_of.items()}
    lane_of = {ev: lane_for(ev, series) for ev, series in series_of.items()}

    # tag -> new event (authoritative: our own naming anchor)
    tag2event = {int(r["tag"]): r["event"] for r in names}
    # legacy event name -> the tags it carries in the official ledger
    legacy_tags: dict[str, list[int]] = {
        e["name"]: [int(t["tag"]) for t in e["tracks"]] for e in ledger["events"]
    }
    # legacy event -> new event (majority vote over shared tagIds)
    legacy2event: dict[str, str] = {}
    for legacy, tags in legacy_tags.items():
        votes = collections.Counter(tag2event[t] for t in tags if t in tag2event)
        if votes:
            legacy2event[legacy] = votes.most_common(1)[0][0]

    # new event -> legacy ledger events; primary row first (same name wins,
    # then lexical) so year/dates/totals come from the event's own row.
    by_event: dict[str, list[str]] = collections.defaultdict(list)
    for legacy, new in legacy2event.items():
        by_event[new].append(legacy)
    for new, legacies in by_event.items():
        legacies.sort(key=lambda name: (name != new, name))

    raw: dict[str, dict] = {}
    for r in names:
        raw[r["name"]] = {"event": r["event"],
                          "series": BUCKET[r["series"]],
                          "lane": lane_for(r["event"], r["series"])}
    # Legacy ledger event names and the four hard-coded aliases stay resolvable
    # (test fixtures and pre-rewrite clients still send those spellings).
    for legacy, new in legacy2event.items():
        raw.setdefault(legacy, {"event": new, "series": bucket_of[new],
                                "lane": lane_of[new]})
    for alias, legacy in ledger.get("aliases", {}).items():
        new = legacy2event.get(legacy, legacy)
        if new in bucket_of:
            raw.setdefault(alias, {"event": new, "series": bucket_of[new],
                                   "lane": lane_of[new]})

    events = {
        ev: {"series": bucket_of[ev], "lane": lane_of[ev], "legacy": by_event.get(ev, [])}
        for ev in sorted(series_of)
    }
    payload = json.dumps({
        "source": {
            "names": str(NAMES.relative_to(ROOT)).replace("\\", "/"),
            "ledger": str(LEDGER.relative_to(ROOT)).replace("\\", "/"),
            "note": "tagId from contest-achieve; all names authored by us. "
                    "Digits live only in contest_ledger.json and are never recomputed here.",
        },
        "raw": dict(sorted(raw.items())),
        "events": events,
    }, ensure_ascii=False, indent=1) + "\n"

    missing = [ev for ev, info in events.items() if not info["legacy"]]
    print(f"raw={len(raw)} events={len(events)} "
          f"with_legacy={sum(1 for i in events.values() if i['legacy'])}")
    if missing:
        print("WARN events with no ledger row:", ", ".join(missing), file=sys.stderr)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != payload:
            print(f"FAIL: {OUT} is stale, re-run without --check", file=sys.stderr)
            return 1
        print("contest names up to date")
        return 0
    OUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT} ({len(payload.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

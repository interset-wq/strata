"""Author the engine's embedded contest-awards table from contest-achieve.

The engine's archive page shows each edition's verified winners (docs/
contest-display-in-app.md §6). This is a *display-only* table — awards never
feed admission, ordering or scoring — and it is deliberately kept separate
from the seed-side contest_awards rows (the old 911-row normalized CSV, 867
of which are placeholders). Source of truth is contest-achieve's awards.json:
613 rows / 609 unique verified nids, every award name real.

  python app/tools/contestledger/build_awards.py \
      --awards E:/contest-achieve/docs/data/awards.json \
      --names analysis/anchors/contest_names.jsonl

Join key: an award row's contest_track_id is a tag in our names file; the
file's event field is the archive-page key and name is the contest string.
Upstream naming never reaches the UI — only the real award string does
(金奖/银奖/铜奖/…). A nid may win more than one award in the same event; those
are merged into one entry with an awards[] array so the book is listed once.

2026-11-27: upstream's naming is never used. The join key is the tagId
contest-achieve already resolved; the NAMES file (analysis/anchors/
contest_names.jsonl) is our single source of truth for both the event key and
per-entry contest string, shared with dataset/build.py. Book rows are cleared
and rewritten from the same mapping, so the winner list matches book/IP views.
Early 一/二/三征 medal tags (635-649) collapse to the bare edition name; the
medal stays in awards[].

Only verified=true rows are accepted. Unverifiable winners are omitted rather
than shown with a placeholder — the archive page explains the count it does
have and never pretends a partial list is complete.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AWARDS = Path("E:/contest-achieve/docs/data/awards.json")
DEFAULT_NAMES = ROOT / "analysis/anchors/contest_names.jsonl"
OUT = ROOT / "app/engine/internal/store/contest_awards.json"

# Display order, coarsest tier first. Awards outside this table keep their
# literal name and sort after the known tiers (alphabetical by name), so a new
# upstream award never disappears or needs a code change.
TIER_ORDER = [
    "金奖", "一等奖", "第1名",
    "银奖", "二等奖", "第2名",
    "铜奖", "三等奖", "第3名",
    "星火奖", "编辑推荐奖", "推荐奖", "优秀题材奖", "创意奖",
    "新人奖", "新星奖", "题材鼓励奖", "鼓励奖", "人气参与奖",
]


def tier_key(award: str) -> tuple[int, str]:
    try:
        return (TIER_ORDER.index(award), "")
    except ValueError:
        return (len(TIER_ORDER), award)


def _load_names(path: Path) -> dict[int, tuple[str, str]]:
    """tag -> (event key, our contest name) from our single-source names file."""
    out: dict[int, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        tag = int(r["tag"])
        if tag in out:
            raise ValueError(f"contest_names.jsonl duplicate tag {tag}")
        out[tag] = (str(r["event"]), str(r["name"]))
    return out


def build(awards: list[dict], names: dict[int, tuple[str, str]]) -> dict:
    tag2event = {tag: pair[0] for tag, pair in names.items()}
    tag2contest = {tag: pair[1] for tag, pair in names.items()}

    # event -> nid -> entry (awards[] accumulates multi-award nids)
    by_event: dict[str, dict[int, dict]] = {}
    skipped: list[str] = []
    for row in awards:
        if not row.get("verified"):
            skipped.append(f"nid {row.get('nid')}: unverified")
            continue
        tag = int(row.get("contest_track_id") or 0)
        event = tag2event.get(tag)
        if event is None:
            skipped.append(f"nid {row.get('nid')}: track {tag} not in names file")
            continue
        nid = int(row["nid"])
        entry = by_event.setdefault(event, {}).setdefault(nid, {
            "nid": nid,
            "title": row.get("title", ""),
            "awards": [],
            "contest": tag2contest[tag],  # our spelling, never upstream's
            "series": row.get("series", ""),
        })
        award = row.get("award", "")
        if award and award not in entry["awards"]:
            entry["awards"].append(award)

    events: dict[str, list[dict]] = {}
    for event, entries in by_event.items():
        rows = list(entries.values())
        rows.sort(key=lambda r: (min((tier_key(a) for a in r["awards"]),
                                     default=(len(TIER_ORDER), r["awards"][0])),
                                 r["nid"]))
        for r in rows:
            r["awards"].sort(key=tier_key)
        events[event] = rows

    payload = {
        "source": {
            "project": "contest-achieve",
            "repository": "https://github.com/light-nook-labs/contest-achieve",
            "file": "docs/data/awards.json",
            "license": "AGPL-3.0",
            "join": "contest_track_id == tag in analysis/anchors/contest_names.jsonl -> event (key) + name (entry.contest); our names, same mapping as dataset/build.py",
        },
        "tier_order": TIER_ORDER,
        "events": events,
    }
    return payload, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--awards", type=Path, default=DEFAULT_AWARDS)
    ap.add_argument("--names", type=Path, default=DEFAULT_NAMES)
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed table instead of writing")
    args = ap.parse_args()

    awards = json.loads(args.awards.read_text(encoding="utf-8"))
    names = _load_names(args.names)
    payload, skipped = build(awards, names)
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"

    total = sum(len(v) for v in payload["events"].values())
    print(f"awards rows={len(awards)} events={len(payload['events'])} "
          f"entries={total} skipped={len(skipped)}")
    for s in skipped:
        print("SKIP:", s, file=sys.stderr)

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"FAIL: {OUT} is stale, re-run without --check", file=sys.stderr)
            return 1
        print("contest_awards.json up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(text.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

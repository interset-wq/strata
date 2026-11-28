"""Refresh / author the engine's contest ledger (official scale + schedule + tagIds).

The ledger (app/engine/internal/store/contest_ledger.json) is the single table the
engine embeds: one row per (event, track), our event/division labels as the key,
upstream's official numbers as the payload.

  python app/tools/contestledger/build_ledger.py --upstream E:/contest-achieve/docs/data/contests.json
        Refresh the committed ledger: per-track counts always come from upstream;
        dates/URL/year fill only where the ledger is still empty (an authored,
        user-verified value is never overwritten).

  python app/tools/contestledger/build_ledger.py --upstream ... --migrate
        One-time (2026-11-26, done): author the ledger from the two Go tables this
        file used to duplicate — store/roster_tags.go (verified tagIds) and
        store/contest_meta.go (verified edition dates/URLs).

Upstream = contest-achieve (https://github.com/light-nook-labs/contest-achieve),
AGPL-3.0. Join key: contest_track_id == our verified tagId, so no upstream event
naming enters our ledger. Provenance of every tagId stays in
docs/contest-roster-harvest.md; this script never invents one.

Page index: upstream uses page_start=0 for all 447 tags, and a live probe on
2026-11-26 proved the new SPA `page` is 0-based too (tag 704: page=0 -> 500 rows,
page=1 -> 321, page=2 -> empty, totalPage=2). Both generations therefore fetch
from 0, so the table carries no page_start column.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TAGS_GO = ROOT / "app/engine/internal/store/roster_tags.go"
META_GO = ROOT / "app/engine/internal/store/contest_meta.go"
OUT = ROOT / "app/engine/internal/store/contest_ledger.json"

# Seed label spellings that name an event we already ledger. Without these the
# same edition renders as two archive rows, one of which finds no tagId.
ALIASES = {
    "2026春征": "2026春季征文",
    "超新星杯短篇": "“超新星杯”短篇大赛",
    "2024主题短篇": "2024主题短篇征文",
    "少年-二次元创想·短篇": "少年创想短篇",
}

TAG_RE = re.compile(
    r"\{Event: \"(?P<event>.*?)\", Division: \"(?P<div>.*?)\", Tag: (?P<tag>\d+), "
    r"Gen: RosterGen(?P<gen>\w+)")
META_RE = re.compile(
    r"\"(?P<event>[^\"]+)\": \{(?P<body>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\},")
# `Year` is a bare int in the Go table, the other fields are quoted.
FIELD_RE = re.compile(r"(?P<key>Year|Start|End|Note|Official):\s*(?:\"(?P<q>[^\"]*)\"|(?P<i>\d+))")
# 一/二征 publish one list per medal, 三征 per (division, medal): the whole
# 635-649 block, which is all those earliest editions ever released.
AWARD_RE = re.compile(r"^(?P<event>[一二三]征)-(?P<div>长篇|中篇|短篇)?(?P<award>金奖|银奖|铜奖)$")

CN = "一二三四五六七八九十"


def clean_url(url: str) -> str:
    return url.split("?")[0].rstrip() if url else ""


def engine_tab(name: str) -> str:
    """Port of the engine's contestSeries(): the app's tab rules, kept here so a
    re-run reports where upstream's family classification differs from them."""
    for ch in name:
        if ch in CN:
            continue
        if ch == "征":
            return "x"
        break
    if "冬季征文" in name:
        return "winter"
    if "春季征文" in name:
        return "spring"
    if "秋季征文" in name:
        return "autumn"
    return "other"


def authored_from_go(upstream: list[dict]) -> list[dict]:
    """The one-time migration source: the two Go tables this ledger replaces,
    plus the award-tier tags only upstream names (635-649)."""
    meta: dict[str, dict] = {}
    text = META_GO.read_text(encoding="utf-8")
    for m in META_RE.finditer(text[text.index("var contestMeta"):]):
        meta[m["event"]] = {k.lower(): (q or i)
                            for k, q, i in FIELD_RE.findall(m["body"])}

    events: dict[str, dict] = {}
    order: list[str] = []

    def event(name: str) -> dict:
        ev = events.setdefault(name, {"name": name, "tracks": []})
        if name not in order:
            order.append(name)
        return ev

    for m in TAG_RE.finditer(TAGS_GO.read_text(encoding="utf-8")):
        event(m["event"])["tracks"].append({
            "kind": "roster",
            "division": m["div"],
            "tag": int(m["tag"]),
            "gen": m["gen"].lower(),
        })

    # Award-tier tags: the earliest X征 editions publish winners as tagIds
    # (635-649), which is how those editions exist at all. They are NOT entry
    # lists, so kind=award keeps them out of the roster fetch path.
    known = {t["tag"] for ev in events.values() for t in ev["tracks"]}
    for r in sorted(upstream, key=lambda r: int(r["contest_track_id"])):
        tid = int(r["contest_track_id"])
        if tid in known:
            continue
        m = AWARD_RE.match(r["contest_name"])
        if not m:
            continue
        event(m["event"])["tracks"].append({
            "kind": "award",
            "division": (m["div"] or "") + m["award"],
            "tag": tid,
            "gen": "old" if r["api_generation"] == "legacy" else "new",
        })

    for name in order:
        ev = events[name]
        ours = meta.get(name, {})
        ev["year"] = int(ours["year"]) if ours.get("year") else None
        ev["start"] = ours.get("start", "")
        ev["end"] = ours.get("end", "")
        ev["result"] = ""
        ev["note"] = ours.get("note", "")
        ev["url"] = clean_url(ours.get("official", ""))
    return [events[n] for n in order]


def refresh(events: list[dict], upstream: list[dict]) -> list[str]:
    """Apply upstream's per-track numbers, filling our remaining gaps."""
    by_tag = {int(r["contest_track_id"]): r for r in upstream}
    warnings: list[str] = []
    used: set[int] = set()

    for ev in events:
        for tr in ev["tracks"]:
            up = by_tag.get(tr["tag"])
            if up is None:
                warnings.append(f"tagId {tr['tag']} ({ev['name']}/{tr['division']}) "
                                "missing upstream: counts stay null, the archive "
                                "degrades to the in-library view")
                continue
            used.add(tr["tag"])
            tr["roster"] = int(up["roster_count"])
            tr["awards"] = int(up["award_count"])
            if not tr["gen"]:
                tr["gen"] = "old" if up["api_generation"] == "legacy" else "new"

        joined = [by_tag[t["tag"]] for t in ev["tracks"] if t["tag"] in by_tag]
        up_first = joined[0] if joined else {}
        ev["series_upstream"] = up_first.get("series", "")
        # Authored (user-verified) values win; upstream only fills what is blank.
        for field, key in (("start", "start_date"), ("end", "end_date"),
                           ("result", "result_date")):
            if not ev.get(field) and up_first.get(key):
                ev[field] = up_first[key]
            elif ev.get(field) and up_first.get(key) and ev[field] != up_first[key]:
                warnings.append(f"event {ev['name']} {field}: ours {ev[field]!r} "
                                f"vs upstream {up_first[key]!r} (ours kept)")
        if not ev.get("url") and up_first.get("activity_url"):
            ev["url"] = clean_url(up_first["activity_url"])
        elif ev.get("url") and up_first.get("activity_url") and \
                ev["url"].rstrip("/") != clean_url(up_first["activity_url"]).rstrip("/"):
            warnings.append(f"event {ev['name']} url: ours {ev['url']!r} vs upstream "
                            f"{clean_url(up_first['activity_url'])!r} (ours kept)")
        if not ev.get("year"):
            ev["year"] = int(ev["start"][:4]) if ev.get("start") else None
        roster = [t for t in ev["tracks"] if t["kind"] == "roster"]
        # A null anywhere means the official scale is unknown, not small:
        # never emit a partial sum as if it were the event's total.
        ev["roster_total"] = (sum(t["roster"] for t in roster)
                              if roster and all(t.get("roster") is not None for t in roster)
                              else None)
        ev["award_total"] = (sum(t["awards"] for t in ev["tracks"])
                             if all(t.get("awards") is not None for t in ev["tracks"])
                             else None)
        if not joined:
            warnings.append(f"event {ev['name']}: no upstream row joined — display "
                            "keeps the in-library view")
        fam = {"X征": "x", "春征": "spring", "秋征": "autumn", "冬征": "winter"}.get(
            ev["series_upstream"])
        if fam and fam != engine_tab(ev["name"]):
            warnings.append(f"event {ev['name']}: upstream family {fam!r} vs our tab "
                            f"{engine_tab(ev['name'])!r} — our tab rules stay in charge "
                            "(series_upstream kept for audit only)")

    orphans = [f"{r['contest_track_id']} {r['contest_name']}" for r in upstream
               if r["contest_name"] != "未知" and r["contest_track_id"] not in used]
    if orphans:
        warnings.append(f"{len(orphans)} upstream tracks not in our ledger: "
                        + "; ".join(orphans[:12]) + ("…" if len(orphans) > 12 else ""))
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream", required=True, type=Path,
                    help="path to contest-achieve docs/data/contests.json")
    ap.add_argument("--migrate", action="store_true",
                    help="author the event/track table from the two Go tables")
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed ledger instead of writing")
    args = ap.parse_args()

    upstream = json.loads(args.upstream.read_text(encoding="utf-8"))
    if args.migrate:
        events = authored_from_go(upstream)
    elif OUT.exists():
        events = json.loads(OUT.read_text(encoding="utf-8"))["events"]
    else:
        print(f"FAIL: {OUT} missing — run with --migrate first", file=sys.stderr)
        return 1

    warnings = refresh(events, upstream)
    ledger = {
        "source": {
            "project": "contest-achieve",
            "repository": "https://github.com/light-nook-labs/contest-achieve",
            "file": "docs/data/contests.json",
            "captured_at": next((r.get("captured_at") for r in upstream
                                 if r.get("captured_at")), ""),
            "join": "contest_track_id == ledger track tag",
            "license": "AGPL-3.0",
        },
        "aliases": ALIASES,
        "events": events,
    }
    payload = json.dumps(ledger, ensure_ascii=False, indent=1) + "\n"

    roster = [e for e in events if e["roster_total"]]
    print(f"events={len(events)} tabs={sorted({engine_tab(e['name']) for e in events})}")
    print(f"tracks={sum(len(e['tracks']) for e in events)} "
          f"with_official={len(roster)} "
          f"with_dates={sum(1 for e in events if e['start'])} "
          f"with_url={sum(1 for e in events if e['url'])} "
          f"official_total={sum(e['roster_total'] or 0 for e in events):,}")
    for w in warnings:
        print("WARN:", w, file=sys.stderr)

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != payload:
            print(f"FAIL: {OUT} is stale, re-run without --check", file=sys.stderr)
            return 1
        print("ledger up to date")
        return 0
    OUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUT} ({len(payload.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

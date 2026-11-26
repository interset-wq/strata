"""中短篇赛事正向准入锚点（E.34，2026-11-26 用户裁定）。

权威数据源是独立归档仓 `light-nook-labs/contest-achieve` 的
``contests.json`` + ``data/<tag>/roster.jsonl``。种子构建与作者榜必须**离线可复现**，
所以不直接读该仓：由 ``analysis/fetchers/sync_contest_scope.py`` 把 26 个中短篇赛项
的 roster nid 并集导出到 ``paths.CONTEST_SHORT_MEDIUM``，本模块只读这个快照。

规则边界（用户裁定 2026-11-26）：
- roster union 只决定「有没有资格进 short/medium 池」，**不决定 short 还是 medium**。
  《少女与龙》(86279) 挂五征短篇、实为 13.9 万字 medium，按 tag 分形态会误伤。
- 唯一豁免通道是人工白名单 ``seed_manual_exempt.jsonl`` 中 ``waive="contest"``
  的逐本书；黑名单（E.32）优先于它。
- 高收藏、无征文或挂非中短篇征文、却被字数规则判成 medium 的书，用户确认为
  **假中篇**，不因收藏高而放行。
"""
from __future__ import annotations

import json
from pathlib import Path

from lib import paths

ANCHOR = paths.CONTEST_SHORT_MEDIUM
WAIVER_ANCHOR = paths.ANCHORS_DIR / "seed_manual_exempt.jsonl"
BLACKLIST_ANCHOR = paths.ANCHORS_DIR / "seed_manual_blacklist.jsonl"
BLACKLIST_KINDS = ("fake_short", "fake_medium", "fake_complete")
ARCHIVE_DEFAULT = Path("E:/contest-achieve")

# 三征 644–649 是获奖分类（无参赛清单），不入池；七征 409/410 在归档里只叫
# 「赛道2/赛道3」，经本地 contest 标注反查确认 409=七征中篇、410=七征短篇。
AWARD_ONLY_TAGS = frozenset({644, 645, 646, 647, 648, 649})
EXPECTED_TAGS = {
    "medium": (276, 378, 384, 409, 419, 458, 476, 654, 703, 753),
    "short": (277, 379, 385, 410, 420, 459, 477, 623, 634, 655,
              676, 693, 704, 748, 754, 794),
}


def _load() -> dict:
    if not ANCHOR.exists():
        raise FileNotFoundError(
            f"missing {ANCHOR}; run: uv run python analysis/fetchers/sync_contest_scope.py")
    obj = json.loads(ANCHOR.read_text(encoding="utf-8"))
    if obj.get("schema") != 1:
        raise ValueError(f"{ANCHOR.name}: unsupported schema {obj.get('schema')!r}")
    tags = obj.get("tags", {})
    if {k: tuple(tags.get(k, ())) for k in EXPECTED_TAGS} != EXPECTED_TAGS:
        raise ValueError(f"{ANCHOR.name}: tag set changed; review the archive sync")
    nids = obj.get("nids")
    if not isinstance(nids, list) or not nids:
        raise ValueError(f"{ANCHOR.name}: empty nid union")
    return obj


def short_medium_nids() -> set[int]:
    """中短篇赛事 roster nid 并集（快照现算，随归档同步变化）。"""
    return {int(n) for n in _load()["nids"]}


def short_medium_tags() -> frozenset[int]:
    """26 个中短篇赛事 tag（与 roster union 同一锚点，供补采接入分析口径放行）。"""
    obj = _load()
    tags = set(obj.get("tags", {}).get("short", ())) | set(
        obj.get("tags", {}).get("medium", ()))
    return frozenset(int(t) for t in tags)


def contest_waived_nids() -> set[int]:
    """人工白名单中 ``waive=contest`` 的 nid（E.34 唯一豁免通道）。"""
    out: set[int] = set()
    for lineno, line in enumerate(WAIVER_ANCHOR.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("//"):
            continue
        row = json.loads(text)
        if row.get("waive") == "contest":
            if not row.get("reason") or not row.get("verified_on"):
                raise ValueError(f"{WAIVER_ANCHOR.name}:{lineno}: reason/verified_on required")
            out.add(int(row["nid"]))
    return out


def manual_blacklist_nids() -> set[int]:
    """E.32 人工黑名单（作者榜与种子共用同一份锚点，当前为空）。"""
    out: set[int] = set()
    for lineno, line in enumerate(BLACKLIST_ANCHOR.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("//"):
            continue
        row = json.loads(text)
        if row.get("kind") not in BLACKLIST_KINDS:
            raise ValueError(f"{BLACKLIST_ANCHOR.name}:{lineno}: unsupported kind={row.get('kind')!r}")
        if not row.get("reason") or not row.get("verified_on"):
            raise ValueError(f"{BLACKLIST_ANCHOR.name}:{lineno}: reason/verified_on required")
        out.add(int(row["nid"]))
    return out


def derive_tags(archive_root: Path) -> dict[str, tuple[int, ...]]:
    """从归档仓注册表推导中短篇赛项；tag 集合变化即报错，等待人工复核。"""
    rows = json.loads((archive_root / "contests.json").read_text(encoding="utf-8"))
    short, medium = [], []
    for row in rows:
        tag = int(row["contest_track_id"])
        if tag in AWARD_ONLY_TAGS:
            continue
        name = str(row.get("contest_name", ""))
        if "短篇" in name:
            short.append(tag)
        elif "中篇" in name:
            medium.append(tag)
    short += [410]  # 七征短篇（归档名「赛道3」）
    medium += [409]  # 七征中篇（归档名「赛道2」）
    got = {"short": tuple(sorted(short)), "medium": tuple(sorted(medium))}
    if got != EXPECTED_TAGS:
        raise ValueError(
            f"archive tag set changed; review before sync:\n"
            f"  short  expected={EXPECTED_TAGS['short']} got={got['short']}\n"
            f"  medium expected={EXPECTED_TAGS['medium']} got={got['medium']}")
    return got


def rosters(archive_root: Path, tags: dict[str, tuple[int, ...]]) -> dict[str, set[int]]:
    """读每个赛项的 roster.jsonl，返回 tag -> nid 集合。"""
    out: dict[str, set[int]] = {}
    for group in ("short", "medium"):
        for tag in tags[group]:
            path = archive_root / "data" / str(tag) / "roster.jsonl"
            meta = archive_root / "data" / str(tag) / "meta.json"
            if not path.exists() or not meta.exists():
                raise FileNotFoundError(f"missing roster/meta for tag {tag}")
            m = json.loads(meta.read_text(encoding="utf-8"))
            complete = any(
                s.get("total_pages") and set(s.get("fetched_pages", ())) == set(range(s["total_pages"]))
                and s.get("novel_count", 0) > 0
                for s in reversed(m.get("snapshots", []))
            )
            if not complete:
                raise ValueError(f"tag {tag} roster is not fully harvested")
            out[str(tag)] = {
                int(json.loads(line)["nid"])
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }
    return out

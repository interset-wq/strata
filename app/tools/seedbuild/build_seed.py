"""Build app/assets/seed.db.gz for the Strata app.

The analysis pipeline (analysis/pipeline/build_csv.py) deliberately drops the
47 licensed Japanese light novels because their reused nids corrupt dating.
The product seed must keep them: they are searchable and detail-visible, but
carry is_licensed=1, NULL percentiles, and never enter A-class rankings.

Usage (from anywhere):
    cd analysis
    uv run python ../app/tools/seedbuild/build_seed.py

The build is pinned to the 2026-05-03 content boundary; count assertions below
fail loudly if the upstream dataset moves without the calibre being re-decided.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
ANALYSIS = REPO / "analysis"
sys.path.insert(0, str(ANALYSIS))

from lib import config as C  # noqa: E402
from lib import eras, paths  # noqa: E402
from pipeline import build_csv as B  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate as V  # noqa: E402

ASSETS = REPO / "app" / "assets"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

SCHEMA_VERSION = 1
SEED_VERSION = "20260503.1"
CONTENT_END = pd.Timestamp("2026-05-03")
GEN_MIN, GEN_MAX = 2007, 2025

# Pinned calibre (see AGENTS.md and app/docs/02-data-model.md).
EXPECT_UNIVERSE = 241_758
EXPECT_ANALYSIS_ROWS = 245_779
EXPECT_LICENSED = 47
EXPECT_BASE = 29_433
EXPECT_SHORT_ADDED = 1_398
EXPECT_SEED = 30_878

REC_N = 20_000
SHORT_MAX_WORDS = 50_000
SHORT_TOP_N = 2_000
SHORT_BINS = [-1, 3_000, 6_000, 10_000, 20_000, 50_001]
SHORT_LABELS = ["<=3k", "3-6k", "6-10k", "10-20k", "20-50k"]

FINAL_COLUMNS = [
    "nid", "title", "author", "genre", "price_type", "status", "contest",
    "words", "clicks", "favs", "praises", "featured", "cover_url", "updated_at",
    "est_year", "est_date", "est_conf", "tags",
    "fav_pctl", "click_pctl", "praise_pctl", "pr", "pctl_pr", "is_licensed",
]


def log(message: str) -> None:
    print(message, flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def blank_tally() -> dict:
    return {
        "text": {},
        "status_missing": 0,
        "status_dead_to_ongoing": 0,
        "genre_relabelled": 0,
        "genre_unresolved": 0,
        "cover_placeholder_nulled": 0,
        "cover_shared_bugged": 0,
        "licensed_ln_total": 0,
        "licensed_ln_with_banner": 0,
        "tags_deduplicated": 0,
        "tags_dropped": 0,
        "word_num_zero": 0,
        "click_num_zero": 0,
        "praise_num_zero": 0,
        "like_num_zero": 0,
    }


def pctl_within(frame: pd.DataFrame, group: str, value: str) -> pd.Series:
    g = frame.groupby(group, observed=True)[value]
    return g.rank(ascending=True, method="average") / g.transform("size")


def seed_set(df: pd.DataFrame) -> tuple[set[int], dict[str, int]]:
    """Replicate report 18's base pool, using content_end-relative cutoffs."""
    base = set(df.nlargest(REC_N, "favs")["id"])
    recent = set(df[df["est_date"] >= CONTENT_END - pd.Timedelta(days=365)]["id"])
    active = set(df[df["upd"] >= CONTENT_END - pd.Timedelta(days=90)]["id"])
    monthly: set[int] = set()
    with paths.MONTHLY_RANKS.open(encoding="utf-8") as fh:
        for line in fh:
            for item in json.loads(line)["items"]:
                if item.get("nid"):
                    monthly.add(int(item["nid"]))
    monthly &= set(df["id"])
    featured = set(df.loc[df["featured"] == 1, "id"])
    ids = base | recent | active | monthly | featured
    return ids, {
        "top_favs": len(base),
        "recent_1y": len(recent),
        "active_90d": len(active),
        "monthly": len(monthly),
        "featured": len(featured),
        "union": len(ids),
    }


def short_supplement(df: pd.DataFrame, existing: set[int]) -> tuple[set[int], int]:
    """Report 19: short dual-percentile Top 2000 (word bin x generation)."""
    short = df[(df["words"] <= SHORT_MAX_WORDS) & (df["status"] == "已完结")].copy()
    short["wb"] = pd.cut(short["words"], SHORT_BINS, labels=SHORT_LABELS, right=True)
    short["grp"] = short["wb"].astype(str) + "|" + short["est_year"].astype(str)
    short["p_grp"] = pctl_within(short, "grp", "favs")
    top = short.sort_values("p_grp", ascending=False).head(SHORT_TOP_N)
    add = set(top.loc[~top["id"].isin(existing), "id"])
    return add, len(short)


def bind(value):
    """Convert pandas/numpy scalars to sqlite3-friendly Python values."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    return value


def licensed_rows(records: dict[int, dict], ids: list[int]) -> pd.DataFrame:
    tally, fixes = blank_tally(), []
    rows = [B.clean_row(records[nid], tally, fixes) for nid in ids]
    df = pd.DataFrame(rows, columns=C.COLUMN_NAMES)
    for name, dtype, _n, _src, _desc in C.COLUMNS:
        if dtype == "Int64":
            df[name] = pd.array(df[name], dtype="Int64")
        else:
            df[name] = df[name].astype(dtype)
    bad = df[df["status"].isna() | df["genre"].isna()]
    if not bad.empty:
        raise SystemExit(f"licensed rows failed cleaning: {bad['id'].tolist()}")
    # All 47 share one known-bad crawler cover; never let licensing own it.
    df["cover_url"] = pd.NA
    df["is_licensed"] = 1
    return df


def build_frames() -> tuple[pd.DataFrame, dict]:
    records, load_stats = B.load_jsonl(paths.JSONL_DIR)
    B.check_fields(records)
    log(f"jsonl: {load_stats['files']} files / {load_stats['lines']} lines"
        f" -> {len(records)} unique nids")

    analysis_df, tally, fixes, dropped = B.build(records)
    if len(analysis_df) != EXPECT_ANALYSIS_ROWS:
        raise SystemExit(f"analysis rows {len(analysis_df)} != {EXPECT_ANALYSIS_ROWS}")

    ln_ids = sorted(nid for nid, row in records.items()
                    if row["author"] in C.LICENSED_LN_AUTHORS)
    if len(ln_ids) != EXPECT_LICENSED:
        raise SystemExit(f"licensed rows {len(ln_ids)} != {EXPECT_LICENSED}")
    ln_df = licensed_rows(records, ln_ids)
    if len(ln_df) != EXPECT_LICENSED:
        raise SystemExit(f"licensed cleaned rows {len(ln_df)} != {EXPECT_LICENSED}")

    df = pd.concat([analysis_df, ln_df], ignore_index=True)
    df["is_licensed"] = df["is_licensed"].fillna(0).astype("int8")
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(
        est[["id", "est_date", "est_year", "est_conf"]], on="id", how="left"
    )
    if df[["est_date", "est_year", "est_conf"]].isna().any().any():
        bad = df[df[["est_date", "est_year", "est_conf"]].isna().any(axis=1)]
        raise SystemExit(f"missing dating for {bad['id'].tolist()[:10]}")

    universe = df[(df["is_licensed"] == 0)
                  & df["est_year"].between(GEN_MIN, GEN_MAX)].copy()
    if len(universe) != EXPECT_UNIVERSE:
        raise SystemExit(f"stats universe {len(universe)} != {EXPECT_UNIVERSE}")

    # Build-time percentiles: full analysis universe, grouped by generation.
    for src, dst in [("favs", "fav_pctl"), ("clicks", "click_pctl"),
                     ("praises", "praise_pctl")]:
        universe[dst] = pctl_within(universe, "est_year", src)
    universe["pr"] = np.where(
        universe["favs"] >= 10,
        universe["praises"] / universe["favs"].replace(0, np.nan),
        np.nan,
    )
    denom = universe.groupby("est_year")["pr"].transform("count")
    universe["pctl_pr"] = (
        universe.groupby("est_year")["pr"].rank(ascending=True, method="average")
        / denom
    )

    universe["upd"] = pd.to_datetime(universe["updated_at"], errors="coerce")
    base, base_detail = seed_set(universe)
    short_add, short_total = short_supplement(universe, base)
    if len(base) != EXPECT_BASE:
        raise SystemExit(f"base seed {len(base)} != {EXPECT_BASE}")
    if len(short_add) != EXPECT_SHORT_ADDED:
        raise SystemExit(f"short supplement {len(short_add)} != {EXPECT_SHORT_ADDED}")

    seed_ids = base | short_add | set(ln_ids)
    if len(seed_ids) != EXPECT_SEED:
        raise SystemExit(f"seed {len(seed_ids)} != {EXPECT_SEED}")

    pctl = universe[["id", "fav_pctl", "click_pctl", "praise_pctl", "pr", "pctl_pr"]]
    seed = df[df["id"].isin(seed_ids)].merge(pctl, on="id", how="left")
    seed = seed.rename(columns={"id": "nid"})
    seed = seed[FINAL_COLUMNS].sort_values("nid").reset_index(drop=True)
    seed["est_date"] = pd.to_datetime(seed["est_date"]).dt.strftime("%Y-%m-%d")

    meta = {
        "load": load_stats,
        "analysis_rows": len(analysis_df),
        "licensed_rows": len(ln_df),
        "dropped_rows": dropped["rows"],
        "dropped_rules": dropped["rules"],
        "universe_rows": len(universe),
        "base": len(base),
        "base_detail": base_detail,
        "short_total": short_total,
        "short_added": len(short_add),
        "seed_rows": len(seed),
        "licensed_ids": ln_ids,
        "licensed_banner": int((ln_df["featured"] == 1).sum()),
        "tally": tally,
        "genre_fixes": fixes,
    }
    return seed, meta


def write_db(seed: pd.DataFrame, meta: dict, db_path: Path) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tag_pairs: list[tuple[int, str]] = []
    for nid, tags in seed[["nid", "tags"]].itertuples(index=False, name=None):
        tags = bind(tags)
        if not tags:
            continue
        for tag in str(tags).split(C.TAG_SEP):
            tag = tag.strip()
            if tag:
                tag_pairs.append((int(nid), tag))
    tag_count = len({tag for _nid, tag in tag_pairs})

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        with conn:
            conn.executemany(
                f"INSERT INTO books({','.join(FINAL_COLUMNS)})"
                f" VALUES({','.join('?' * len(FINAL_COLUMNS))})",
                [tuple(bind(v) for v in row)
                 for row in seed.itertuples(index=False, name=None)],
            )
            conn.executemany(
                "INSERT INTO book_tags(nid, tag) VALUES(?, ?)", tag_pairs
            )
            conn.executemany(
                "INSERT INTO seed_meta(key, value) VALUES(?, ?)",
                [
                    ("schema_version", str(SCHEMA_VERSION)),
                    ("seed_version", SEED_VERSION),
                    ("content_end", CONTENT_END.strftime("%Y-%m-%d")),
                    ("built_at", built_at),
                    ("book_count", str(len(seed))),
                    ("tag_count", str(tag_count)),
                    ("tag_rows", str(len(tag_pairs))),
                    ("gen_min", str(GEN_MIN)),
                    ("gen_max", str(GEN_MAX)),
                    ("licensed_count", str(meta["licensed_rows"])),
                    ("base_count", str(meta["base"])),
                    ("short_added", str(meta["short_added"])),
                    ("stats_universe", str(meta["universe_rows"])),
                ],
            )
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
    finally:
        conn.close()

    return {
        "built_at": built_at,
        "tag_count": tag_count,
        "tag_rows": len(tag_pairs),
    }


def gzip_db(db_path: Path, gz_path: Path) -> None:
    gz_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = gz_path.with_suffix(gz_path.suffix + ".tmp")
    with db_path.open("rb") as src, tmp.open("wb") as dst:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=dst, compresslevel=9, mtime=0
        ) as gz:
            for chunk in iter(lambda: src.read(1 << 20), b""):
                gz.write(chunk)
    tmp.replace(gz_path)


def main() -> int:
    if not paths.JSONL_DIR.exists():
        raise SystemExit(
            f"missing jsonl dir {paths.JSONL_DIR}\n"
            "run: cd analysis && uv run --extra archive python pipeline/prepare.py"
        )
    if not paths.MONTHLY_RANKS.exists():
        raise SystemExit(
            f"missing {paths.MONTHLY_RANKS}; archived monthly ranks are a seed source"
        )

    seed, meta = build_frames()
    log(f"seed rows: {len(seed)} (base {meta['base']} + short "
        f"{meta['short_added']} + licensed {meta['licensed_rows']})")

    work = REPO / "temp" / "seedbuild"
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / "seed.db"
    info = write_db(seed, meta, db_path)

    V.check_db(db_path, seed, meta)

    gz_path = ASSETS / "seed.db.gz"
    gzip_db(db_path, gz_path)
    db_path.unlink()

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "seed_version": SEED_VERSION,
        "content_end": CONTENT_END.strftime("%Y-%m-%d"),
        "built_at": info["built_at"],
        "book_count": len(seed),
        "licensed_count": meta["licensed_rows"],
        "tag_count": info["tag_count"],
        "tag_rows": info["tag_rows"],
        "gen_min": GEN_MIN,
        "gen_max": GEN_MAX,
        "counts": {
            "stats_universe": meta["universe_rows"],
            "base": meta["base"],
            "short_added": meta["short_added"],
            "licensed_added": meta["licensed_rows"],
            "seed": len(seed),
        },
        "source": {
            "dataset": C.SOURCE["repo"],
            "asset": C.SOURCE["asset"],
            "files": meta["load"]["files"],
            "lines": meta["load"]["lines"],
            "unique_nids": meta["load"]["lines"] - meta["load"]["duplicate_rows"],
            "analysis_rows": meta["analysis_rows"],
            "dropped_rows": meta["dropped_rows"],
        },
        "files": {
            "db": {
                "name": "seed.db",
                "bytes": 0,
                "sha256": None,
            },
            "gz": {
                "name": "seed.db.gz",
                "bytes": gz_path.stat().st_size,
                "sha256": sha256(gz_path),
            },
        },
    }
    with gzip.open(gz_path, "rb") as fh:
        db_bytes = fh.read()
    manifest["files"]["db"]["bytes"] = len(db_bytes)
    manifest["files"]["db"]["sha256"] = hashlib.sha256(db_bytes).hexdigest()

    (ASSETS / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log(f"db: {manifest['files']['db']['bytes'] / 1e6:.2f} MB"
        f" -> gzip {manifest['files']['gz']['bytes'] / 1e6:.2f} MB"
        f" ({manifest['files']['gz']['bytes'] / len(seed):.0f} B/book)")
    log(f"wrote {gz_path}")
    log(f"wrote {ASSETS / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

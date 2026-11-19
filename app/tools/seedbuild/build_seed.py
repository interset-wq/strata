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

V3 (2026-11-19): the book source is `dataset/out/books.jsonl` (our own 15-column
catalogue, App-verified covers), admission is `seed_policy.admit()` (quality
anchors + every deep-rank book, **no new-book discovery channel**), and `form` /
`lqs` are build-time columns. The 2026-11-19 follow-up removed the time channels
entirely: new books are structurally disadvantaged by cumulative favourites, so
a dedicated channel for them is unfair to the older library. E.9 adds a
per-contest floor (every named contest keeps >= 3 qualifying books).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
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
import seed_policy as SP  # noqa: E402
import validate as V  # noqa: E402
from lib import forms as FM  # noqa: E402
from lib import lqs as LQ  # noqa: E402
from deep_ranks import DEEP_COLUMNS, METRICS as DEEP_METRICS  # noqa: E402
from deep_ranks import TOP_N as DEEP_TOP_N  # noqa: E402
from deep_ranks import build_deep_ranks, seed_coverage  # noqa: E402

ASSETS = REPO / "app" / "assets"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DATASET = REPO / "dataset" / "out" / "books.jsonl"

SCHEMA_VERSION = 3
SEED_VERSION = "20260503.20"
CONTENT_END = pd.Timestamp("2026-05-03")
GEN_MIN, GEN_MAX = 2007, 2025

# Pinned calibre (see AGENTS.md and app/docs/02-data-model.md).
EXPECT_UNIVERSE = 241_864       # 241,758 + 108（E.14 补充书，est_year 全部落 2007–2025）
EXPECT_ANALYSIS_ROWS = 245_887  # 245,779 + 108 月榜遗漏书（E.14）
EXPECT_DATASET_ROWS = 248_338   # v20260503.7: 248,230 + 108 月榜遗漏书（E.14）
EXPECT_LICENSED = 47
EXPECT_ADMITTED = 18_703       # E.21 正文征文归字数档（8 本连载长篇组书转为中篇→出局）
EXPECT_SEED = 18_750           # 18,703 + 47 licensed
EXPECT_COVERAGE_MIN = 0.9650   # eligible 口径（弃书+invalid 剔除后；详见 P3）。
# E.17 同人短字数条款把 6,012 本同人从 short 移入 dialogue：这些书不再受 E.11
# 弃书约束，eligible 分母因此多出 0.87% 的收藏，而种子只吸收其中 700 本有质量锚
# 的书。门槛随分母下调，P3 的同分母对比（vs V0 +0.00pp）才是回归判据。

# Baseline V0 counts, kept only for the audit trail (app/docs/09 appendix E).
V0_BASE = 29_433
V0_SHORT_ADDED = 1_398
V0_SEED = 30_878

REC_N = 20_000
SHORT_MAX_WORDS = 50_000
SHORT_TOP_N = 2_000
SHORT_BINS = [-1, 3_000, 6_000, 10_000, 20_000, 50_001]
SHORT_LABELS = ["<=3k", "3-6k", "6-10k", "10-20k", "20-50k"]

# dataset/ keeps absolute URLs (both rs/rss hosts); seed.db stores the relative
# path after /NovelCover/Big/ so the on-device cover resolver stays unchanged.
COVER_PREFIX = re.compile(
    r"^(?:https?:)?//(?:rs|rss)\.sfacg\.com/web/novel/images/NovelCover/Big/"
)

FINAL_COLUMNS = [
    "nid", "title", "author", "genre", "price_type", "status", "contest",
    "words", "clicks", "favs", "praises", "featured", "cover_url", "updated_at",
    "est_year", "est_date", "est_conf", "tags",
    "fav_pctl", "click_pctl", "praise_pctl", "pr", "pctl_pr",
    "form", "lqs", "lqs_pctl", "vel_pctl", "is_licensed",
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


def load_dataset(path: Path) -> tuple[dict[int, dict], dict]:
    """读自制数据集（唯一真源）：每 nid 一行，保留全部书，不做过滤。"""
    records: dict[int, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            nid = int(row["nid"])
            if nid in records:
                raise SystemExit(f"dataset has duplicate nid {nid}")
            records[nid] = row
    stats = {"path": str(path.relative_to(REPO)).replace("\\", "/"),
             "lines": len(records), "sha256": sha256(path)}
    return records, stats


def relative_cover(url: str | None) -> str | None:
    """数据集里的绝对 URL → seed.db 的相对路径（域名/前缀不入库）。"""
    if not url:
        return None
    m = COVER_PREFIX.match(url)
    if not m:
        raise SystemExit(f"unexpected cover URL in dataset: {url[:100]}")
    return url[m.end():]


def clean_dataset(records: dict[int, dict]) -> tuple[pd.DataFrame, dict, list, dict]:
    """复用 build_csv 的行清洗/剔除判据，但输入是自制数据集（已归并重复行）。"""
    tally, fixes = blank_tally(), []
    rows = []
    for nid in sorted(records):
        row = dict(records[nid])
        row["status"] = row.get("status") or None   # 空状态在源里是空串
        rows.append(B.clean_row(row, tally, fixes))
    df = pd.DataFrame(rows, columns=C.COLUMN_NAMES)
    for name, dtype, _n, _src, _desc in C.COLUMNS:
        df[name] = pd.array(df[name], dtype="Int64") if dtype == "Int64" \
            else df[name].astype(dtype)

    ln_mask = df["author"].isin(C.LICENSED_LN_AUTHORS)
    tally["licensed_ln_total"] = int(ln_mask.sum())
    tally["licensed_ln_with_banner"] = int((ln_mask & (df["featured"] == 1)).sum())

    masks = B.drop_mask(df)
    dropped = pd.concat(masks, axis=1).any(axis=1)
    dropped_info = {"rows": int(dropped.sum()),
                    "rules": {k: int(v.sum()) for k, v in masks.items()}}
    df = df.loc[~dropped].reset_index(drop=True)

    # 封面来自数据集：默认图/共享伪影已由 dataset/build.py 处理，这里只压前缀。
    # dataset 的 cover 是绝对 URL；保留两种主机但剥掉公共前缀，引擎按相对路径存。
    covers = {nid: relative_cover(row.get("cover")) for nid, row in records.items()}
    df["cover_url"] = df["id"].map(covers)
    nonnull = df["cover_url"].notna()
    if df.loc[nonnull, "cover_url"].duplicated().any():
        dup = df.loc[nonnull, "cover_url"].value_counts()
        raise SystemExit(f"duplicate cover paths after dataset load: {int((dup > 1).sum())}")
    return df, tally, fixes, dropped_info


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
    rows = []
    for nid in ids:
        row = dict(records[nid])
        row["status"] = row.get("status") or None
        rows.append(B.clean_row(row, tally, fixes))
    df = pd.DataFrame(rows, columns=C.COLUMN_NAMES)
    for name, dtype, _n, _src, _desc in C.COLUMNS:
        if dtype == "Int64":
            df[name] = pd.array(df[name], dtype="Int64")
        else:
            df[name] = df[name].astype(dtype)
    bad = df[df["status"].isna() | df["genre"].isna()]
    if not bad.empty:
        raise SystemExit(f"licensed rows failed cleaning: {bad['id'].tolist()}")
    # 授权 47 本也用数据集里的 cover-check 当期封面；早期爬虫共用的坏推荐位封面
    # 已由 dataset/build.py 覆盖，不能再无条件清空。
    covers = {nid: relative_cover(row.get("cover")) for nid, row in records.items()}
    df["cover_url"] = df["id"].map(covers)
    if df["cover_url"].isna().any():
        bad = df.loc[df["cover_url"].isna(), "id"].tolist()
        raise SystemExit(f"licensed rows missing cover: {bad}")
    df["is_licensed"] = 1
    return df


def build_frames() -> tuple[pd.DataFrame, dict]:
    if not DATASET.exists():
        raise SystemExit(f"missing {DATASET}; run: cd dataset && uv run python build.py")
    records, dataset_info = load_dataset(DATASET)
    if len(records) != EXPECT_DATASET_ROWS:
        raise SystemExit(f"dataset rows {len(records)} != {EXPECT_DATASET_ROWS}")
    log(f"dataset: {dataset_info['path']} / {len(records):,} books")

    analysis_df, tally, fixes, dropped = clean_dataset(records)
    if len(analysis_df) != EXPECT_ANALYSIS_ROWS:
        raise SystemExit(f"analysis rows {len(analysis_df)} != {EXPECT_ANALYSIS_ROWS}")

    ln_ids = sorted(nid for nid, row in records.items()
                    if row["author"] in C.LICENSED_LN_AUTHORS)
    if len(ln_ids) != EXPECT_LICENSED:
        raise SystemExit(f"licensed rows {len(ln_ids)} != {EXPECT_LICENSED}")
    ln_df = licensed_rows(records, ln_ids)
    if len(ln_df) != EXPECT_LICENSED:
        raise SystemExit(f"licensed cleaned rows {len(ln_df)} != {EXPECT_LICENSED}")
    # Licensed books stay outside the scoring universe, but `form` is a
    # classification (not a score): every book must carry one.
    licensed_form = pd.Series(FM.classify(ln_df).to_numpy(),
                              index=ln_df["id"].to_numpy())

    df = pd.concat([analysis_df, ln_df], ignore_index=True)
    df["is_licensed"] = df["is_licensed"].fillna(0).astype("int8")
    covers = df["cover_url"].dropna()
    if covers.duplicated().any():
        dup = covers.value_counts()
        raise SystemExit(f"duplicate cover paths after licensed merge: {int((dup > 1).sum())}")
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(est[["id", "est_date", "est_year", "est_conf"]], on="id", how="left")
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

    # D2 deep ranks: full-universe Top-200 per generation and metric.
    deep = build_deep_ranks(universe, DEEP_TOP_N)

    # V3 admission: four clean anchors (favs Top-20k, monthly, banner,
    # short dual-percentile) + every deep-rank book + E.9 contest floor.
    # Time channels are retired (diagnostic only); V0 kept for audit trail.
    universe["upd"] = pd.to_datetime(universe["updated_at"], errors="coerce")
    universe = SP.add_velocity(universe, CONTENT_END)
    quality = LQ.compute(universe)
    res = SP.admit(universe, CONTENT_END, deep=set(deep["nid"]))
    checks = SP.postconditions(universe, res)
    for name, ok, detail in checks:
        log(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    if not all(ok for _name, ok, _detail in checks):
        raise SystemExit("V3 postconditions failed; seed not rebuilt")
    if len(res["ids"]) != EXPECT_ADMITTED:
        raise SystemExit(f"admitted {len(res['ids'])} != {EXPECT_ADMITTED}")

    seed_ids = res["ids"] | set(ln_ids)
    if len(seed_ids) != EXPECT_SEED:
        raise SystemExit(f"seed {len(seed_ids)} != {EXPECT_SEED}")

    extra = ["form", "lqs", "lqs_pctl", "vel_pctl"]
    universe[extra] = quality[extra]
    pctl_cols = ["id", "fav_pctl", "click_pctl", "praise_pctl", "pr", "pctl_pr"] + extra
    seed = df[df["id"].isin(seed_ids)].merge(universe[pctl_cols], on="id", how="left")
    seed["form"] = seed["form"].fillna(seed["id"].map(licensed_form))
    if seed["form"].isna().any():
        raise SystemExit(f"{int(seed['form'].isna().sum())} rows missing form")
    seed = seed.rename(columns={"id": "nid"})
    seed = seed[FINAL_COLUMNS].sort_values("nid").reset_index(drop=True)
    seed["est_date"] = pd.to_datetime(seed["est_date"]).dt.strftime("%Y-%m-%d")
    # Coverage uses the eligible denominator (E.11 连载 short/medium + E.12
    # invalid 剔除), consistent with P3. Full-universe favs fall by design —
    # ineligible books have no admission资格 and are not a coverage regression.
    eligible_favs = float(universe.loc[~universe["id"].isin(res["ineligible"]),
                                       "favs"].sum())
    coverage = float(seed.loc[seed["is_licensed"] == 0, "favs"].sum()
                     / eligible_favs)
    if coverage < EXPECT_COVERAGE_MIN:
        raise SystemExit(f"favs coverage {coverage:.4%} < {EXPECT_COVERAGE_MIN:.2%}")

    meta = {
        "load": dataset_info,
        "analysis_rows": len(analysis_df),
        "licensed_rows": len(ln_df),
        "dropped_rows": dropped["rows"],
        "dropped_rules": dropped["rules"],
        "universe_rows": len(universe),
        "admitted": len(res["ids"]),
        "baseline_v0": len(res["baseline"]),
        "admission_detail": {
            "top_favs": len(res["base"]),
            "monthly": len(res["monthly"]),
            "featured": len(res["featured"]),
            "short": len(res["short"]),
            "time_excluded": len(res["excluded_time"]),
            "time_gated_diagnostic": len(res["gated"]),
            "time_cut_diagnostic": len(res["cut"]),
            "deep": len(res["deep"]),
            "contest_floor": {
                "contests": len(res["contest_detail"]),
                "added": len(res["contest_added"]),
                "shortfalls": {k: v for k, v in res["contest_detail"].items()
                               if v["need"] > 0},
            },
            "abandoned": {
                "total": len(res["abandoned"]),
                "in_seed": len(res["abandoned_in_seed"]),  # 仅征文保底豁免
                "exempt_pctl_098": len(res["abandon_exempt"]),  # E.13 经质量锚入种
            },
            "invalid": {
                "total": len(res["invalid"]),
                "in_seed": len(res["invalid"] & set(res["ids"])),  # 恒为 0（P6）
            },
        },
        "postconditions": checks,
        "favs_coverage": coverage,
        "lqs_scored": int(quality["lqs"].notna().sum()),
        "seed_rows": len(seed),
        "licensed_ids": ln_ids,
        "licensed_banner": int((ln_df["featured"] == 1).sum()),
        "tally": tally,
        "genre_fixes": fixes,
        "deep_ranks": deep,
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
            deep = meta["deep_ranks"]
            conn.executemany(
                f"INSERT INTO deep_ranks({','.join(DEEP_COLUMNS)})"
                f" VALUES({','.join('?' * len(DEEP_COLUMNS))})",
                [tuple(bind(v) for v in row)
                 for row in deep.itertuples(index=False, name=None)],
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
                    ("admitted", str(meta["admitted"])),
                    ("baseline_v0", str(meta["baseline_v0"])),
                    ("stats_universe", str(meta["universe_rows"])),
                    ("favs_coverage", f"{meta['favs_coverage']:.6f}"),
                    ("lqs_scored", str(meta["lqs_scored"])),
                    ("deep_metrics", ",".join(DEEP_METRICS)),
                    ("deep_top_n", str(DEEP_TOP_N)),
                    ("deep_rank_rows", str(len(meta["deep_ranks"]))),
                    ("deep_seed_hit", str(int(meta["deep_ranks"]["nid"]
                                              .isin(set(seed["nid"])).sum()))),
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
    if not DATASET.exists():
        raise SystemExit(f"missing {DATASET}; run: cd dataset && uv run python build.py")
    if not paths.MONTHLY_RANKS.exists():
        raise SystemExit(
            f"missing {paths.MONTHLY_RANKS}; archived monthly ranks are a seed source"
        )

    seed, meta = build_frames()
    log(f"seed rows: {len(seed)} (quality-anchored admitted {meta['admitted']} + licensed "
        f"{meta['licensed_rows']}; V0 was {V0_SEED})")
    log(f"favs coverage: {meta['favs_coverage']:.2%} | lqs scored in universe: "
        f"{meta['lqs_scored']:,}")
    log(f"deep ranks: {len(meta['deep_ranks'])} rows "
        f"({len(DEEP_METRICS)} metrics x top {DEEP_TOP_N}, full universe)")

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
            "baseline_v0": meta["baseline_v0"],
            "admitted_v3": meta["admitted"],
            "licensed_added": meta["licensed_rows"],
            "seed": len(seed),
            "deep_rank_rows": len(meta["deep_ranks"]),
            "lqs_scored_universe": meta["lqs_scored"],
        },
        "admission_detail": meta["admission_detail"],
        "favs_coverage": round(meta["favs_coverage"], 6),
        "postconditions": [
            {"name": str(name), "pass": bool(ok), "detail": str(detail)}
            for name, ok, detail in meta["postconditions"]
        ],
        "source": {
            "dataset": "local:dataset/out/books.jsonl",
            "dataset_sha256": meta["load"]["sha256"],
            "analysis_rows": meta["analysis_rows"],
            "dropped_rows": meta["dropped_rows"],
            "upstream": C.SOURCE["repo"],
            "upstream_asset": C.SOURCE["asset"],
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

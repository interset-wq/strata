"""Build app/assets/seed.db.gz for the Strata app.

The analysis pipeline (analysis/pipeline/build_csv.py) deliberately drops the
47 licensed Japanese light novels because their reused nids corrupt dating.
The product seed must keep them: they are searchable and detail-visible, but
carry is_licensed=1, NULL percentiles, and never enter A-class rankings.

Usage (from anywhere):
    cd analysis
    uv run python ../app/tools/seedbuild/build_seed.py

The snapshot boundary is 2026-05-03, but the catalogue is only ever partially
refreshed (rank_missing + contest_new carry 2026-11 observations), so the seed
version / content_end mark the last partial update (2026-11-24) rather than a
full snapshot date. Count assertions below fail loudly if the upstream dataset
moves without the calibre being re-decided.

V3 (2026-11-19): the book source is `dataset/out/books.jsonl` (our own 15-column
catalogue, App-verified covers), admission is `seed_policy.admit()` (quality
anchors + every deep-rank book, **no new-book discovery channel**), and `form` is a build-time column. The 2026-11-19 follow-up removed the time channels
entirely: new books are structurally disadvantaged by cumulative favourites, so
a dedicated channel for them is unfair to the older library. E.31 replaces the
old automatic per-contest floor with a human-curated floor list and removes all
automatic exemptions from the `short/medium` completion rule.
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
import runtime_metrics as RM  # noqa: E402
from deep_ranks import DEEP_COLUMNS, METRICS as DEEP_METRICS  # noqa: E402
from deep_ranks import TOP_N as DEEP_TOP_N  # noqa: E402
from deep_ranks import build_deep_ranks, seed_coverage  # noqa: E402

ASSETS = REPO / "app" / "assets"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
DATASET = REPO / "dataset" / "out" / "books.jsonl"
AWARD_CSV = ANALYSIS / "out" / "contest_awards_normalized.csv"

SCHEMA_VERSION = 8  # v8: dropped archived build-only metrics lqs/lqs_pctl/vel_pctl (see schema.sql)
SEED_VERSION = "20261124.32"  # .32: E.32 新增人工黑名单（假短/假中篇），优先级高于人工豁免
CONTENT_END = pd.Timestamp("2026-11-24")  # 数据集从不全量刷新：标注最近一次部分更新时间，非快照上界
GEN_MIN, GEN_MAX = 2007, 2026  # E.30: 2026 由"出界"改为正常世代，与其他年份一样走 admit 渠道筛选

# Pinned calibre (see AGENTS.md and app/docs/02-data-model.md).
EXPECT_UNIVERSE = 249_885       # 241,864 + 8,021 本 2026（库内 4,023 + 征文新书 3,998）
EXPECT_ANALYSIS_ROWS = 249_885  # 245,887 + 3,998 征文新书（E.29 部分更新）
EXPECT_DATASET_ROWS = 252_336   # v20261124.8: 248,338 + 3,998 征文新书（14 征 793/794）
EXPECT_LICENSED = 47
EXPECT_ADMITTED = 18_837       # E.31: 取消自动保底/自动豁免后 18,880 → 18,837（剔除 43 本）
EXPECT_SEED = 18_884           # 18,837 + 47 licensed
EXPECT_COVERAGE_MIN = 0.9640   # 覆盖率仍 96.40%（合格书分母同步缩小），门槛不变
# v5 contest awards (docs/award-winners-as-seed-source.md): net 911 rows over
# 11 editions; the 602 shortlist rows are excluded upstream of this CSV.
# Display-only facts: award never feeds admission or ordering
# (docs/contest-display-in-app.md §6 red line). Pinned per edition.
EXPECT_AWARD_ROWS = 911
AWARD_EDITION_COUNTS = {
    "十二征": 363, "十三征": 446,
    "七征冬征": 16, "六征冬征": 16, "八征冬征": 10, "九征冬征": 10,
    "2024春征": 16, "2024秋征": 11, "2025春征": 10, "2025秋征": 7,
    "2026春征": 6,
}
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
    "form",
    "cqs", "cqs_state", "cps", "len_norm", "is_licensed",
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


def load_awards() -> pd.DataFrame:
    """Load the normalized award table (net 911 rows, 11 editions).

    One-shot analysis output (docs/award-winners-as-seed-source.md §8): the
    602 shortlist rows are already excluded upstream, so this CSV is the only
    award source. Pinned counts fail loudly if the file moves.
    """
    if not AWARD_CSV.exists():
        raise SystemExit(
            f"missing {AWARD_CSV}; one-shot analysis output, see "
            f"docs/award-winners-as-seed-source.md §8"
        )
    df = pd.read_csv(AWARD_CSV, encoding="utf-8-sig", dtype={"nid": "int64"})
    if len(df) != EXPECT_AWARD_ROWS:
        raise SystemExit(f"award rows {len(df)} != expected {EXPECT_AWARD_ROWS}")
    if (df["nid"] <= 0).any():
        raise SystemExit("award rows with non-positive nid")
    if df.duplicated(subset=["nid", "edition"]).any():
        raise SystemExit("duplicate (nid, edition) award rows")
    if (df["award"].isna() | (df["award"].astype(str).str.strip() == "")).any():
        raise SystemExit("award rows with empty award")
    edition_counts = df["edition"].value_counts().to_dict()
    if edition_counts != AWARD_EDITION_COUNTS:
        raise SystemExit(
            f"award edition counts {edition_counts} != pinned "
            f"{AWARD_EDITION_COUNTS}"
        )
    return df[["nid", "edition", "award", "category", "source_nid"]]


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

    # Calendar universe table (v4, app/docs/14): estimated whole-platform
    # releases per day. Source = full dataset INCLUDING licensed; display
    # range = founding year GEN_MIN .. GEN_MAX (content right-censored at
    # CONTENT_END). The bundled seed is a clickable subset of this table;
    # the engine fills zero days for the UI.
    cal_days = pd.to_datetime(df["est_date"]).dt.strftime("%Y-%m-%d")
    cal_range = cal_days.between(f"{GEN_MIN}-01-01", f"{GEN_MAX}-12-31")
    cal = (cal_days[cal_range]
           .value_counts()
           .sort_index()
           .reset_index(name="universe_count"))
    cal.columns = ["day", "universe_count"]
    calendar_universe = cal.reset_index(drop=True)
    if len(calendar_universe) < 1000:
        raise SystemExit(
            f"calendar universe days {len(calendar_universe)} looks wrong")

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
    # short dual-percentile) + every deep-rank book + E.31 manual contest floor.
    # Time channels are retired (diagnostic only); V0 kept for audit trail.
    universe["upd"] = pd.to_datetime(universe["updated_at"], errors="coerce")
    universe = SP.add_velocity(universe, CONTENT_END)
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

    universe["form"] = FM.classify(universe)

    # v6 runtime quality metrics (app/docs/18-runtime-metrics.md, report 24):
    # form-isolated cqs/cps calibration over the analysis universe, precomputed
    # for seed books; the calib_* tables ship so the engine can band and score
    # discovered books at runtime (phase 2). Clicks never enters the formulas.
    scores, rt = RM.build(universe)
    universe = universe.merge(scores, on="id", how="left")

    # v7 eras anchors: the nid-axis dating curve ships with the seed so the
    # engine can estimate est_year for discovered books at runtime
    # (app/docs/18-runtime-metrics.md P2).
    anchors_df = eras.load_anchors()[["nid", "day"]].copy()
    anchors_df["day"] = anchors_df["day"].astype("int64")
    if len(anchors_df) < 280:
        raise SystemExit(f"eras anchors {len(anchors_df)} < 280")

    pctl_cols = ["id", "fav_pctl", "click_pctl", "praise_pctl", "pr", "pctl_pr"] \
        + ["form"] + ["cqs", "cqs_state", "cps", "len_norm"]
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
                "manual_only": True,
                "contests": len(res["contest_detail"]),
                "added": len(res["contest_added"]),
                "shortfalls": {k: v for k, v in res["contest_detail"].items()
                               if v["need"] > 0},
            },
            "abandoned": {
                "total": len(res["abandoned"]),
                "in_seed": len(res["abandoned_in_seed"]),  # 恒为 0（P5）
                "manual_exempt": len(res["manual_exempt"]),  # 人工清单逐本放行
                "manual_blacklist": len(res["manual_blacklist"]),  # E.32 优先于豁免
            },
            "invalid": {
                "total": len(res["invalid"]),
                "in_seed": len(res["invalid"] & set(res["ids"])),  # 恒为 0（P6）
            },
            "fake_complete_p10": {
                "total": len(res["fake_complete"]),
                "in_seed": len(res["fake_complete"] & set(res["ids"])),  # 恒为 0（P10）
            },
        },
        "postconditions": checks,
        "manual_exempt": res["manual_exempt"],
        "manual_blacklist": res["manual_blacklist"],
        "favs_coverage": coverage,
        "seed_rows": len(seed),
        "licensed_ids": ln_ids,
        "licensed_banner": int((ln_df["featured"] == 1).sum()),
        "tally": tally,
        "genre_fixes": fixes,
        "deep_ranks": deep,
        "calendar_universe": calendar_universe,
        "runtime": rt,
        "eras_anchors": anchors_df,
    }
    return seed, meta


def write_db(seed: pd.DataFrame, meta: dict, db_path: Path,
             awards: pd.DataFrame) -> dict:
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
                "INSERT INTO calendar_universe(day, universe_count) VALUES(?, ?)",
                [(day, int(count))
                 for day, count in meta["calendar_universe"]
                                     .itertuples(index=False, name=None)],
            )
            conn.executemany(
                "INSERT INTO contest_awards(nid, edition, award, category,"
                " source_nid) VALUES(?, ?, ?, ?, ?)",
                [tuple(bind(v) for v in row)
                 for row in awards.itertuples(index=False, name=None)],
            )
            for table, cols in [
                ("calib_fav_bounds", ("form", "est_year", "p50", "p75", "p90")),
                ("calib_len_anchors", ("form", "lo", "hi")),
                ("calib_cqs_median", ("form", "est_year", "genre", "fband",
                                      "med", "cell_n")),
                ("calib_cps_median", ("form", "est_year", "band", "genre",
                                      "med")),
            ]:
                frame = meta["runtime"]["tables"][table]
                conn.executemany(
                    f"INSERT INTO {table}({','.join(cols)})"
                    f" VALUES({','.join('?' * len(cols))})",
                    [tuple(bind(v) for v in row)
                     for row in frame.itertuples(index=False, name=None)],
                )
            conn.executemany(
                "INSERT INTO eras_anchors(nid, day) VALUES(?, ?)",
                [(int(nid), int(day)) for nid, day in
                 meta["eras_anchors"].itertuples(index=False, name=None)],
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
                    ("deep_metrics", ",".join(DEEP_METRICS)),
                    ("deep_top_n", str(DEEP_TOP_N)),
                    ("deep_rank_rows", str(len(meta["deep_ranks"]))),
                    ("deep_seed_hit", str(int(meta["deep_ranks"]["nid"]
                                              .isin(set(seed["nid"])).sum()))),
                    ("calendar_universe_days",
                     str(len(meta["calendar_universe"]))),
                    ("award_rows", str(len(awards))),
                    ("calibration_version", SEED_VERSION),
                    ("cqs_scored", str(meta["runtime"]["cqs_scored"])),
                    ("cqs_stable", str(meta["runtime"]["cqs_stable"])),
                    ("cps_scored", str(meta["runtime"]["cps_scored"])),
                    ("cqs_mu0", f"{meta['runtime']['mu0']:.6f}"),
                    ("eras_anchor_rows", str(len(meta["eras_anchors"]))),
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
    awards = load_awards()
    meta["awards"] = awards
    log(f"seed rows: {len(seed)} (quality-anchored admitted {meta['admitted']} + licensed "
        f"{meta['licensed_rows']}; V0 was {V0_SEED})")
    log(f"favs coverage: {meta['favs_coverage']:.2%}")
    log(f"runtime metrics: cqs scored {meta['runtime']['cqs_scored']:,} "
        f"(stable {meta['runtime']['cqs_stable']:,}) | cps scored "
        f"{meta['runtime']['cps_scored']:,} | mu0={meta['runtime']['mu0']:.3f}")
    log(f"deep ranks: {len(meta['deep_ranks'])} rows "
        f"({len(DEEP_METRICS)} metrics x top {DEEP_TOP_N}, full universe)")
    log(f"contest awards: {len(awards)} rows "
        f"({len(AWARD_EDITION_COUNTS)} editions, display-only)")

    work = REPO / "temp" / "seedbuild"
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / "seed.db"
    info = write_db(seed, meta, db_path, awards)

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
            "award_rows": len(awards),
            "cqs_scored": meta["runtime"]["cqs_scored"],
            "cqs_stable": meta["runtime"]["cqs_stable"],
            "cps_scored": meta["runtime"]["cps_scored"],
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

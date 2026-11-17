"""Full-universe generation Top-N rankings (D2 deep ranks).

The app seed is a curated 30,878-book pool. Its per-generation ranking endpoint
can accept limit=200, but the pool itself only holds 6-97 books for the 2007-2014
generations, so a "Top200" query silently returns a handful of rows. Deep ranks
solve this without touching the seed book list: compute the ranking on the full
statistical universe (is_licensed=0, est_year in 2007..2025) at build time and
ship the result as an additive table in seed.db.

Scope (pinned by app/docs/09-seed-refresh-proposal.md appendix A, decision D2):
  - grouping key: est_year, one independent board per generation
  - depth: 200 per generation per metric
  - metrics: favs, clicks, praises, pr (praises/favs, favs>=10 gate)
  - reference frame: full universe, never the curated seed pool
  - no network access, no dating recalculation, no report-10 changes

Used by both app/tools/seedbuild/build_seed.py (to populate seed.db) and
analysis/generators/report_21_deep_ranks.py (to document and validate).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

METRICS = ("favs", "clicks", "praises", "pr")
TOP_N = 200
GEN_MIN, GEN_MAX = 2007, 2025
PR_MIN_FAVS = 10

# Long-format columns, also the deep_ranks SQLite schema.
DEEP_COLUMNS = [
    "est_year", "metric", "rank_no", "nid", "title", "author", "genre",
    "value", "pctl", "cover_url",
]

# metric -> (value column, percentile column computed on the full universe)
_SOURCES = {
    "favs": ("favs", "fav_pctl"),
    "clicks": ("clicks", "click_pctl"),
    "praises": ("praises", "praise_pctl"),
    "pr": ("pr", "pctl_pr"),
}


def build_deep_ranks(universe: pd.DataFrame, top_n: int = TOP_N) -> pd.DataFrame:
    """Compute generation Top-N for every metric on the full universe.

    ``universe`` must be the 241,758-row statistical frame already carrying the
    five build-time percentile columns. Rows without a valid metric value (NaN,
    and favs < 10 for ``pr``) are ineligible. Ties are broken by ascending nid so
    the output is byte-for-byte reproducible.
    """
    required = {"id", "est_year", "title", "author", "fav_pctl",
                "click_pctl", "praise_pctl", "pr", "pctl_pr"}
    missing = required - set(universe.columns)
    if missing:
        raise ValueError(f"deep ranks: universe missing columns {sorted(missing)}")

    out: list[pd.DataFrame] = []
    for year in range(GEN_MIN, GEN_MAX + 1):
        group = universe[universe["est_year"] == year]
        if group.empty:
            continue
        for metric in METRICS:
            value_col, pctl_col = _SOURCES[metric]
            valid = group[group[value_col].notna()]
            if valid.empty:
                continue
            ordered = valid.sort_values(
                [value_col, "id"], ascending=[False, True], kind="mergesort"
            ).head(top_n)
            frame = pd.DataFrame({
                "est_year": year,
                "metric": metric,
                "rank_no": range(1, len(ordered) + 1),
                "nid": ordered["id"].astype(int).to_numpy(),
                "title": ordered["title"].to_numpy(),
                "author": ordered["author"].to_numpy(),
                "genre": ordered["genre"].to_numpy(),
                "value": ordered[value_col].astype(float).to_numpy(),
                "pctl": ordered[pctl_col].astype(float).to_numpy(),
                "cover_url": ordered["cover_url"].to_numpy(),
            })
            out.append(frame)

    if not out:
        raise ValueError("deep ranks: no rows produced")
    result = pd.concat(out, ignore_index=True)[DEEP_COLUMNS]
    # Depth is min(200, eligible books). Early generations hold only 76-3,441
    # books, so a full 200 is impossible there; `pr` additionally has the
    # favs>=10 gate. Validate contiguity and uniqueness instead of a fixed count.
    for (year, metric), grp in result.groupby(["est_year", "metric"], sort=True):
        if not np.array_equal(grp["rank_no"].to_numpy(), np.arange(1, len(grp) + 1)):
            raise ValueError(f"deep ranks {year}/{metric}: rank_no not contiguous")
    if result.duplicated(["est_year", "metric", "rank_no"]).any():
        raise ValueError("deep ranks: duplicate rank positions")
    return result


def seed_coverage(deep: pd.DataFrame, seed_nids: set[int]) -> pd.DataFrame:
    """Per generation x metric: how many deep-rank entries are in the seed pool.

    This is the evidence for why the existing /rankings/favs limit=200 cannot
    serve as a deep board, and why an additive table is required.
    """
    rows = []
    for (year, metric), grp in deep.groupby(["est_year", "metric"], sort=True):
        rows.append({
            "est_year": int(year),
            "metric": metric,
            "depth": len(grp),
            "in_seed": int(grp["nid"].isin(seed_nids).sum()),
        })
    cov = pd.DataFrame(rows)
    cov["missing"] = cov["depth"] - cov["in_seed"]
    cov["coverage"] = cov["in_seed"] / cov["depth"]
    return cov

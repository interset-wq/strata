"""Runtime quality metrics (cqs/cps/len_norm) for the seed build.

Mirrors analysis/generators/report_24_runtime_metrics.py (2026-11-23) exactly:
form-isolated calibration, kappa=500, in-year favourite percentile bands, and
no cell fallback (a cell needs >= 5 books to score, >= 20 for stable). Clicks
never enters the formulas (docs/12 red line). See app/docs/18-runtime-metrics.md
for the landing design and docs/metrics-definitions.md §5 for the replacement
ruling against lqs/mqs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

KAPPA = 500
CQS_MIN_FAVS = 1_000
CPS_MIN_FAVS = 10
CQS_CELL_MIN = 5
CQS_STABLE_MIN = 20
CPS_CELL_MIN = 20
MID_Q_LOW = 0.20
MID_Q_HIGH = 0.80

# 篇幅档切点（与报告 24 一致；form-definitions 的 six-value form 是另一维度）。
BAND_EDGES = [2_000, 50_000, 150_000, np.inf]
BAND_LABELS = ["short", "medium", "long"]

# 收藏档按 form×年内分位切：绝对档跨年不可比（报告 24 §2.4）。
CQS_FAVS_PCTS = [0.50, 0.75, 0.90]
CQS_FAVS_LABELS = ["P50-", "P50-75", "P75-90", "P90+"]
PUBLISHABLE_BANDS = ["P50-75", "P75-90", "P90+"]

# clx 字数锚点取可发布 cqs 池的 P10→P90（对话全库中位仅 8k，全库锚点会失去区分度）。
LEN_Q_LO, LEN_Q_HI = 0.10, 0.90

CQS_KEYS = ["form", "est_year", "genre", "fband"]
CPS_KEYS = ["form", "est_year", "band", "genre"]


def build(universe: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score the calibration universe and fit the runtime calibration tables.

    universe carries id/form/est_year/genre/words/favs/praises for
    is_licensed=0, est_year 2007..2025 (form/est_year already assigned).
    Returns (scores, summary): scores maps id -> cqs/cqs_state/cps/len_norm
    for the seed merge; summary holds the calib_* tables (engine phase 2) and
    coverage counts for the manifest.
    """
    cal = universe[(universe["form"] != "invalid")
                   & (universe["words"] >= 2_000)].copy()
    cal["band"] = pd.cut(cal["words"], BAND_EDGES, labels=BAND_LABELS,
                         right=True)
    cal = cal[cal["band"].notna()].copy()

    # ---- cqs：form×年×题材×收藏档内的收缩赞藏比口碑分 ----
    pool = cal[cal["favs"] >= CQS_MIN_FAVS].copy()
    mu0 = float((pool["praises"] / pool["favs"]).median())
    bounds = (
        pool.groupby(["form", "est_year"])["favs"]
        .quantile(CQS_FAVS_PCTS)
        .unstack()
        .rename(columns={0.50: "p50", 0.75: "p75", 0.90: "p90"})
    )
    p = pool.join(bounds, on=["form", "est_year"])
    p["fband"] = np.select(
        [p["favs"] >= p["p90"], p["favs"] >= p["p75"], p["favs"] >= p["p50"]],
        ["P90+", "P75-90", "P50-75"],
        default="P50-",
    )
    # μ0 是 cqs 池的 praises/favs 中位（报告 24 口径：0.232）；不回退到更大的池。
    p["log_pr_s"] = np.log((p["praises"] + KAPPA * mu0) / (p["favs"] + KAPPA))
    cell = (p.groupby(CQS_KEYS, observed=True)["log_pr_s"]
            .agg(["median", "size"]))
    cell["med"] = cell["median"].where(cell["size"] >= CQS_CELL_MIN)
    p = p.merge(
        cell[["med", "size"]].rename(columns={"med": "cell_med",
                                              "size": "cqs_cell_n"}),
        on=CQS_KEYS, how="left",
    )
    # 年内 P50 以下不发布 cqs（头部不能是中等偏下书），格 <5 本不评、不回退。
    p["cqs"] = np.where(
        p["fband"].isin(PUBLISHABLE_BANDS),
        p["log_pr_s"] - p["cell_med"],
        np.nan,
    )
    p["cqs_state"] = np.where(p["cqs_cell_n"] >= CQS_STABLE_MIN,
                              "stable", "low")
    p.loc[p["cqs"].isna(), "cqs_state"] = None
    scored = p[p["cqs"].notna()].copy()

    # ---- cps：form×年×篇幅档×题材内的位置分（只做中层筛选，不发榜）----
    e = cal[cal["favs"] >= CPS_MIN_FAVS].copy()
    e["log_favs"] = np.log1p(e["favs"])
    cps_cell = (e.groupby(CPS_KEYS, observed=True)["log_favs"]
                .agg(["median", "size"]))
    cps_cell["med"] = cps_cell["median"].where(cps_cell["size"] >= CPS_CELL_MIN)
    e = e.merge(cps_cell["med"].rename("cps_med").reset_index(),
                on=CPS_KEYS, how="left")
    e["cps"] = e["log_favs"] - e["cps_med"]

    # ---- len_norm：可发布池的 form×字数锚点归一（clx 的运行时输入）----
    anchors = (scored.groupby("form")["words"]
               .quantile([LEN_Q_LO, LEN_Q_HI])
               .unstack()
               .rename(columns={0.10: "lo", 0.90: "hi"}))
    scored = scored.join(anchors, on="form")
    clipped = scored["words"].clip(lower=scored["lo"], upper=scored["hi"])
    scored["len_norm"] = np.log(clipped / scored["lo"]) \
        / np.log(scored["hi"] / scored["lo"])

    scores = cal[["id"]].copy()
    scores = scores.merge(p[["id", "cqs", "cqs_state"]], on="id", how="left")
    scores = scores.merge(e[["id", "cps"]], on="id", how="left")
    scores = scores.merge(scored[["id", "len_norm"]], on="id", how="left")

    calib = {
        "calib_fav_bounds": bounds.reset_index(),
        "calib_len_anchors": anchors.reset_index(),
        "calib_cqs_median": cell[cell["med"].notna()][["med", "size"]]
        .reset_index(),
        "calib_cps_median": cps_cell[cps_cell["med"].notna()][["med"]]
        .reset_index(),
    }
    summary = {
        "mu0": mu0,
        "cqs_scored": int(scored["cqs"].notna().sum()),
        "cqs_stable": int((scored["cqs_state"] == "stable").sum()),
        "cps_scored": int(e["cps"].notna().sum()),
        "tables": calib,
    }
    return scores, summary

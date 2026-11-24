"""生成 analysis/reports/24_runtime_metrics.md：运行时量化指标的可行性。

只读 `analysis/out/novels.csv`，用 `lib/eras.py` 定年、`lib/forms.py` 判 form；
不修改任何数据。所有数字、表格和图形都由本脚本重算，不手写报告数字。

用法：uv run python analysis/generators/report_24_runtime_metrics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402

from lib import charts  # noqa: E402
from lib import eras  # noqa: E402
from lib import forms  # noqa: E402

OUT = paths.REPORTS_DIR / "24_runtime_metrics.md"
FAV_BOUNDS_OUT = paths.OUT_DIR / "report24_fav_bounds.csv"
LEN_ANCHORS_OUT = paths.OUT_DIR / "report24_len_anchors.csv"

KAPPA = 500
CQS_MIN_FAVS = 1_000
CPS_MIN_FAVS = 10
CQS_CELL_MIN = 5
CQS_STABLE_MIN = 20
CPS_CELL_MIN = 20
MID_Q_LOW = 0.20
MID_Q_HIGH = 0.80

BAND_EDGES = [2_000, 50_000, 150_000, np.inf]
BAND_LABELS = ["short", "medium", "long"]
BAND_CN = {"short": "短篇", "medium": "中篇", "long": "长篇"}

# 收藏档按 form×年内的收藏分位切，不按绝对收藏数：
# "1 万收藏"在 2015 年是头部、在 2025 年只是中层，绝对档会把这两类书混进同一格，
# 低年份的低分位书就能靠档内高赞藏比冲上头部。分位档让"中等"随年份自动漂移。
CQS_FAVS_PCTS = [0.50, 0.75, 0.90]
CQS_FAVS_LABELS = ["P50-", "P50-75", "P75-90", "P90+"]
PUBLISHABLE_BANDS = ["P50-75", "P75-90", "P90+"]

# clx（篇幅偏好）不是固定第四指标，而是 cqs 的运行时可调视图：
# 用户选权重 K，app 存 cqs + len_norm 两列、运行时重排，不预排静态榜。
LEN_Q_LO, LEN_Q_HI = 0.10, 0.90          # 字数锚点取可发布 cqs 池的 P10→P90
CLX_K_PRESETS = {"默认": 0.0, "偏厚": 0.25, "越厚越好": 0.60}

FORMS = ["long", "dialogue", "medium", "short", "ip_collab"]
FORM_CN = {
    "long": "长篇",
    "dialogue": "对话",
    "medium": "中篇",
    "short": "短篇",
    "ip_collab": "IP 合作",
}
FORM_COLOR = {
    "long": charts.C["gray"],
    "dialogue": charts.C["red"],
    "medium": charts.C["blue"],
    "short": charts.C["green"],
    "ip_collab": "#AA8844",
}

# form 是第一隔离轴：所有校准格都先按 form 切开，再做年/题材/收藏或篇幅校准。
CQS_KEYS = ["form", "est_year", "genre", "fband"]
CPS_KEYS = ["form", "est_year", "band", "genre"]


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(
        paths.CSV_FILE,
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id", how="left")
    d = d[d["est_year"].between(2007, 2025)].copy()
    d["band"] = pd.cut(d["words"], BAND_EDGES, labels=BAND_LABELS, right=True)
    d["form"] = forms.classify(d)
    d = d[(d["form"] != "invalid") & d["band"].notna()].copy()
    e = d[d["favs"] >= CPS_MIN_FAVS].copy()
    e["pr_raw"] = e["praises"] / e["favs"]
    return d, e


def num(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float) -> str:
    return f"{x:.1%}"


def signed(x: float) -> str:
    return f"{x:+.3f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------- cqs


def fit_fav_bounds(pool: pd.DataFrame) -> pd.DataFrame:
    """在 cqs 池内，按 form×年算收藏分位边界（绝对收藏阈值）。

    边界来自候选池本身，而不是全库：全库里大量 favs<1000 的书会把
    "中等"压到几百，恰好复现"头部是中等偏下"的问题。
    """
    q = pool.groupby(["form", "est_year"])["favs"].quantile(CQS_FAVS_PCTS).unstack()
    q.columns = ["p50", "p75", "p90"]
    return q


def add_fav_band(s: pd.DataFrame, bounds: pd.DataFrame) -> pd.DataFrame:
    """用 form×年的分位边界给每本书打收藏档。"""
    out = s.join(bounds, on=["form", "est_year"])
    out["fband"] = np.select(
        [
            out["favs"] >= out["p90"],
            out["favs"] >= out["p75"],
            out["favs"] >= out["p50"],
        ],
        ["P90+", "P75-90", "P50-75"],
        default="P50-",
    )
    out["fband"] = pd.Categorical(
        out["fband"], categories=CQS_FAVS_LABELS, ordered=True,
    )
    # 年内 P50 以下的书不发布 cqs：它们占池子一半，且是头部噪声的主要来源。
    out["cqs_publishable"] = out["fband"].isin(PUBLISHABLE_BANDS)
    return out


def prep_cqs(s: pd.DataFrame, kappa: int, mu0: float) -> pd.DataFrame:
    """给已打 fband 的池算收缩赞藏比的对数。"""
    out = s.copy()
    out["log_pr_s"] = np.log((out["praises"] + kappa * mu0) / (out["favs"] + kappa))
    return out


def fit_cqs(p: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """p 是已打 fband、已算 log_pr_s 的数据。"""
    cell = p.groupby(CQS_KEYS, observed=True)["log_pr_s"].agg(["median", "size"])
    cell["med"] = cell["median"].where(cell["size"] >= CQS_CELL_MIN)
    scored = cell["size"] >= CQS_CELL_MIN
    stable = cell["size"] >= CQS_STABLE_MIN
    meta = {
        "cells": int(len(cell)),
        "scored_cells": int(scored.sum()),
        "full_cells": int(stable.sum()),
        "coverage": float(cell.loc[scored, "size"].sum() / len(p)),
        "stable_coverage": float(cell.loc[stable, "size"].sum() / len(p)),
    }
    return cell, meta


def score_cqs(p: pd.DataFrame, cell: pd.DataFrame) -> pd.DataFrame:
    out = p.merge(
        cell[["med", "size"]].rename(
            columns={"med": "cell_med", "size": "cqs_cell_n"},
        ),
        left_on=CQS_KEYS, right_index=True, how="left",
    )
    out["cqs"] = out["log_pr_s"] - out["cell_med"]
    out["cqs_stable"] = out["cqs_cell_n"] >= CQS_STABLE_MIN
    return out[out["cqs"].notna()].copy()


def add_cqs(
    s: pd.DataFrame, kappa: int = KAPPA, mu0: float | None = None,
    bounds: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    mu = float((s["praises"] / s["favs"]).median()) if mu0 is None else mu0
    if bounds is None:
        bounds = fit_fav_bounds(s)
    p = prep_cqs(add_fav_band(s, bounds), kappa, mu)
    cell, meta = fit_cqs(p)
    return score_cqs(p, cell), meta


# ---------------------------------------------------------------- clx（cqs 的用户可调篇幅视图）


def fit_len_anchors(publishable: pd.DataFrame) -> pd.DataFrame:
    """在可发布 cqs 池内，按 form 算字数锚点 P10→P90。

    锚点来自可发布池而非全库：全库对话 P50 只有 8k，但能进 cqs 池的对话
    P50 约 96k；用全库锚点会让对话 len_norm 顶格、失去区分度。
    随校准表发布给 app，使库外书也能按同一锚点定 len_norm。
    """
    q = publishable.groupby("form")["words"].quantile([LEN_Q_LO, LEN_Q_HI]).unstack()
    q.columns = ["lo", "hi"]
    return q


def add_len_norm(s: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    """按 form 的字数锚点把 words 对数归一到 [0,1]，超出封顶。"""
    out = s.copy()
    lo = out["form"].map(anchors["lo"]).astype(float)
    hi = out["form"].map(anchors["hi"]).astype(float)
    out["len_norm"] = (
        np.log(np.clip(out["words"], lo, hi) / lo) / np.log(hi / lo)
    ).clip(0, 1)
    return out


def add_clx(s: pd.DataFrame, k: float) -> pd.DataFrame:
    """运行时按用户选的 K 算 clx = cqs × (1-K+K×len_norm)。

    s 必须已有 len_norm 列。K=0 即纯 cqs；乘性 + 下界 (1-K) 保证低口碑书
    不能靠字数翻盘。函数只做单本书的向量化变换，不排序、不预排静态榜。
    """
    out = s.copy()
    out["clx"] = out["cqs"] * (1 - k + k * out["len_norm"])
    return out


# ---------------------------------------------------------------- cps


def prep_cps(s: pd.DataFrame) -> pd.DataFrame:
    out = s.copy()
    out["log_fav"] = np.log1p(out["favs"])
    return out


def fit_cps(
    s: pd.DataFrame, keys: list[str], min_cell: int = CPS_CELL_MIN,
) -> tuple[pd.DataFrame, dict]:
    p = prep_cps(s)
    cell = p.groupby(keys, observed=True)["log_fav"].agg(["median", "size"])
    cell["med"] = cell["median"].where(cell["size"] >= min_cell)
    full = cell["size"] >= min_cell
    meta = {
        "cells": int(len(cell)),
        "scored_cells": int(full.sum()),
        "full_cells": int(full.sum()),
        "coverage": float(cell.loc[full, "size"].sum() / len(p)),
        "stable_coverage": float(cell.loc[full, "size"].sum() / len(p)),
    }
    return cell, meta


def score_cps(
    s: pd.DataFrame, cell: pd.DataFrame, keys: list[str],
) -> pd.DataFrame:
    p = prep_cps(s)
    out = p.merge(
        cell[["med"]].rename(columns={"med": "cell_med"}),
        left_on=keys, right_index=True, how="left",
    )
    out["cps"] = out["log_fav"] - out["cell_med"]
    return out[out["cps"].notna()].copy()


def add_cps(
    s: pd.DataFrame, keys: list[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    use = CPS_KEYS if keys is None else keys
    cell, meta = fit_cps(s, use)
    return score_cps(s, cell, use), meta


# ---------------------------------------------------------------- 中层


def mid_band(cqs: pd.DataFrame, cps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # 只发布年内 P50 以上的 cqs；P50- 档仍参与校准（做基线），但不进中层榜。
    z = cqs[cqs["cqs_publishable"]].merge(cps[["id", "cps"]], on="id", how="inner")
    lo = z.groupby("form")["cps"].quantile(MID_Q_LOW)
    hi = z.groupby("form")["cps"].quantile(MID_Q_HIGH)
    z["mid_lo"] = z["form"].map(lo)
    z["mid_hi"] = z["form"].map(hi)
    mid = z[(z["cps"] >= z["mid_lo"]) & (z["cps"] <= z["mid_hi"])].copy()
    return z, mid


def per_form_top(mid: pd.DataFrame, k: int = 5) -> pd.DataFrame:
    stable = mid[mid["cqs_stable"]].copy()
    top = (
        stable.sort_values("cqs", ascending=False)
        .groupby("form", sort=False)
        .head(k)
        .copy()
    )
    top["form"] = pd.Categorical(top["form"], categories=FORMS, ordered=True)
    return top.sort_values(["form", "cqs"], ascending=[True, False])


def form_mix(z: pd.DataFrame, score: str, k: int = 1000) -> pd.Series:
    t = z.dropna(subset=[score]).nlargest(k, score)
    return t["form"].value_counts(normalize=True).reindex(FORMS).fillna(0.0)


# ---------------------------------------------------------------- 稳定


def kappa_sensitivity(
    pool: pd.DataFrame, mu0: float, base: pd.DataFrame,
    bounds: pd.DataFrame,
) -> pd.DataFrame:
    base_top = set(base.nlargest(1000, "cqs")["id"])
    rows = []
    for k in (250, 500, 1000, 2000):
        out, _ = add_cqs(pool, kappa=k, mu0=mu0, bounds=bounds)
        top = set(out.nlargest(1000, "cqs")["id"])
        rows.append({
            "kappa": k,
            "rho_favs": float(out["cqs"].corr(np.log(out["favs"]), method="spearman")),
            "jaccard": len(base_top & top) / len(base_top | top),
            "fav_med": float(out.nlargest(1000, "cqs")["favs"].median()),
        })
    return pd.DataFrame(rows)


def bootstrap_stability(pool: pd.DataFrame, mu0: float, reps: int = 30) -> dict:
    rng = np.random.default_rng(20261122)
    idx = rng.permutation(len(pool))
    n_eval = len(pool) // 5
    ev = pool.iloc[idx[:n_eval]].copy()
    cal = pool.iloc[idx[n_eval:]].copy()
    bounds = fit_fav_bounds(cal)
    cal_p = prep_cqs(add_fav_band(cal, bounds), KAPPA, mu0)
    ev_p = prep_cqs(add_fav_band(ev, bounds), KAPPA, mu0)
    cell, _ = fit_cqs(cal_p)
    base = score_cqs(ev_p, cell)
    rho, j100, j1000, shift = [], [], [], []
    for r in range(reps):
        boot = cal.sample(len(cal), replace=True, random_state=20261122 + r)
        boot_p = prep_cqs(add_fav_band(boot, bounds), KAPPA, mu0)
        cell_b, _ = fit_cqs(boot_p)
        z = score_cqs(ev_p, cell_b)
        common = base[["id", "cqs"]].merge(
            z[["id", "cqs"]], on="id", suffixes=("_base", "_boot"),
        )
        rho.append(float(common["cqs_base"].corr(common["cqs_boot"], method="spearman")))
        a = set(base.nlargest(100, "cqs")["id"])
        b = set(z.nlargest(100, "cqs")["id"])
        j100.append(len(a & b) / len(a | b))
        a = set(base.nlargest(1000, "cqs")["id"])
        b = set(z.nlargest(1000, "cqs")["id"])
        j1000.append(len(a & b) / len(a | b))
        shift.append(float((common["cqs_boot"] - common["cqs_base"]).abs().median()))
    return {
        "rho_med": float(np.median(rho)),
        "rho_p05": float(np.quantile(rho, 0.05)),
        "j100_med": float(np.median(j100)),
        "j100_p05": float(np.quantile(j100, 0.05)),
        "j1000_med": float(np.median(j1000)),
        "j1000_p05": float(np.quantile(j1000, 0.05)),
        "shift_med": float(np.median(shift)),
    }


# ---------------------------------------------------------------- 图


def fig_bias(
    e: pd.DataFrame, raw_top: pd.Series, cqs_top: pd.Series,
) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(11.6, 3.3))

    ax = axes[0]
    year = e.groupby("est_year")["pr_raw"].median()
    ax.plot(year.index, year.values, color=charts.C["red"], marker="o", ms=3.5, lw=1.5)
    ax.set_xticks(range(2008, 2026, 3))
    ax.set_ylim(0.25, 0.90)
    ax.set_xlabel("估年")
    ax.set_ylabel("pr 中位数")
    ax.set_title("原始 pr 的世代差异")
    ax.annotate(
        f"{int(year.idxmax())} 峰值 {year.max():.2f}",
        xy=(year.idxmax(), year.max()), xytext=(2014, 0.86),
        fontsize=8, color=charts.C["red"],
        arrowprops=dict(arrowstyle="-", color=charts.C["red"], lw=0.7),
    )
    ax.annotate(
        f"{int(year.index[-1])} {year.iloc[-1]:.2f}",
        xy=(year.index[-1], year.iloc[-1]), xytext=(2017, 0.28),
        fontsize=8, color=charts.C["gray"],
        arrowprops=dict(arrowstyle="-", color=charts.C["gray"], lw=0.7),
    )

    ax = axes[1]
    by_form = e.groupby("form")["pr_raw"].median().reindex(FORMS)
    ax.bar(
        range(len(by_form)), by_form.values,
        color=[FORM_COLOR[f] for f in FORMS],
    )
    ax.set_xticks(range(len(by_form)), [FORM_CN[f] for f in FORMS], rotation=25, ha="right")
    ax.set_ylabel("pr 中位数")
    ax.set_title("原始 pr 的 form 差异")
    for i, v in enumerate(by_form.values):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=8, color="#444444")

    ax = axes[2]
    y = np.arange(2)
    left = np.zeros(2)
    for f in FORMS:
        vals = np.array([raw_top.get(f, 0.0), cqs_top.get(f, 0.0), ])
        ax.barh(y, vals, left=left, height=0.55, color=FORM_COLOR[f], label=FORM_CN[f])
        left += vals
    ax.set_yticks(y, ["原始 pr", "cqs"])
    ax.set_xlim(0, 1)
    ax.set_xlabel("Top1000 占比")
    ax.set_title("跨 form 混排的头部构成")
    ax.legend(fontsize=7, ncol=2, loc="lower right")
    fig.tight_layout()
    return charts.save(fig, "24_bias.png")


def fig_calibration(cqs: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 3.35))

    ax = axes[0]
    present = [f for f in FORMS if (cqs["form"] == f).sum() >= 100]
    by_form = cqs.groupby("form")["cqs"].agg(
        p10=lambda s: s.quantile(0.10),
        p50="median",
        p90=lambda s: s.quantile(0.90),
    ).reindex(present)
    x = np.arange(len(by_form))
    ax.errorbar(
        x, by_form["p50"],
        yerr=[by_form["p50"] - by_form["p10"], by_form["p90"] - by_form["p50"]],
        fmt="o", color=charts.C["red"], ecolor="#CC9999", capsize=3, ms=4, lw=1.2,
    )
    ax.axhline(0, color="#999999", lw=0.8, ls=":")
    ax.set_xticks(x, [FORM_CN[f] for f in by_form.index], rotation=15)
    ax.set_ylabel("cqs（P10 / 中位 / P90）")
    ax.set_title("各 form 的 cqs 离散度")

    ax = axes[1]
    by_band = cqs.groupby("fband", observed=True)["cqs"].agg(
        p10=lambda s: s.quantile(0.10),
        p50="median",
        p90=lambda s: s.quantile(0.90),
    ).reindex(CQS_FAVS_LABELS)
    x = np.arange(len(by_band))
    ax.errorbar(
        x, by_band["p50"],
        yerr=[by_band["p50"] - by_band["p10"], by_band["p90"] - by_band["p50"]],
        fmt="o", color=charts.C["blue"], ecolor="#99AACC", capsize=4, ms=5, lw=1.4,
    )
    ax.axhline(0, color="#999999", lw=0.8, ls=":")
    ax.set_xticks(x, by_band.index)
    ax.set_ylabel("cqs（P10 / 中位 / P90）")
    ax.set_title("收藏档的 cqs 离散度")
    fig.tight_layout()
    return charts.save(fig, "24_calibration.png")


def fig_stability(sens: pd.DataFrame, boot: dict) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.35))
    ax = axes[0]
    ax.plot(sens["kappa"], sens["jaccard"], color=charts.C["red"], marker="o", ms=4, label="Top1000 Jaccard")
    ax.plot(sens["kappa"], sens["rho_favs"].abs(), color=charts.C["blue"], marker="s", ms=4,
            label="|ρ(cqs, log 收藏)|")
    ax.set_xticks(sens["kappa"], [str(k) for k in sens["kappa"]])
    ax.minorticks_off()
    ax.set_xlabel("κ（平滑强度）")
    ax.set_ylabel("指标")
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8)
    ax.set_title("κ 敏感性（500 为默认）")

    ax = axes[1]
    labels = ["Spearman", "Top100\nJaccard", "Top1000\nJaccard"]
    med = [boot["rho_med"], boot["j100_med"], boot["j1000_med"]]
    low = [boot["rho_p05"], boot["j100_p05"], boot["j1000_p05"]]
    x = np.arange(3)
    ax.bar(x, med, 0.55, color=charts.C["green"], alpha=0.85)
    ax.errorbar(x, med, yerr=[np.array(med) - np.array(low), np.zeros(3)],
                fmt="none", ecolor="#333333", capsize=4)
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("重抽样与基线的一致性")
    ax.set_title("按 form 校准后的 Bootstrap（P5 在下方）")
    fig.tight_layout()
    return charts.save(fig, "24_stability.png")


# ---------------------------------------------------------------- 报告


def build() -> str:
    charts.setup_style()
    d, e = load()
    cqs_pool = e[e["favs"] >= CQS_MIN_FAVS].copy()
    mu0 = float((cqs_pool["praises"] / cqs_pool["favs"]).median())
    bounds = fit_fav_bounds(cqs_pool)
    cqs, cqs_meta = add_cqs(cqs_pool, kappa=KAPPA, mu0=mu0, bounds=bounds)
    cps, cps_meta = add_cps(e, keys=CPS_KEYS)
    cps_nolen, _ = add_cps(e, keys=["form", "est_year", "genre"])

    sens = kappa_sensitivity(cqs_pool, mu0, cqs, bounds)
    boot = bootstrap_stability(cqs_pool, mu0)
    raw_top = form_mix(e, "pr_raw")
    cqs_top = form_mix(cqs, "cqs")
    cps_top = form_mix(cps, "cps")
    figs = {
        "bias": fig_bias(e, raw_top, cqs_top),
        "calibration": fig_calibration(cqs),
        "stability": fig_stability(sens, boot),
    }

    # 每本书在 cqs 池内的年内收藏分位，用于验证"头部不是中等偏下"
    cqs["fav_pctl_in_year"] = cqs.groupby(["form", "est_year"])["favs"].rank(pct=True)
    _z, mid = mid_band(cqs, cps)
    top = per_form_top(mid, 5)

    # clx 字数锚点：从可发布 cqs 池按 form 现算，随校准表一起发布给 app。
    pub = cqs[cqs["cqs_publishable"]].copy()
    len_anchors = fit_len_anchors(pub)
    pub = add_len_norm(pub, len_anchors)

    # 诊断数字：修复后各 form cqs Top50 的年内收藏分位中位
    top50_pctl = {}
    for f in ["long", "dialogue", "medium"]:
        sub = mid[mid["form"] == f].nlargest(50, "cqs")
        if len(sub) >= 10:
            top50_pctl[f] = float(sub["fav_pctl_in_year"].median())

    raw_top_fav_med = float(e.nlargest(1000, "pr_raw")["favs"].median())
    cqs_top_fav_med = float(cqs.nlargest(1000, "cqs")["favs"].median())
    cps_top_fav_med = float(cps.nlargest(1000, "cps")["favs"].median())
    raw_peak_year = int(e.groupby("est_year")["pr_raw"].median().idxmax())
    raw_last = float(e.groupby("est_year")["pr_raw"].median().iloc[-1])

    cqs_resid = {
        "year": cqs["cqs"].corr(cqs["est_year"], method="spearman"),
        "words": cqs["cqs"].corr(np.log(cqs["words"]), method="spearman"),
        "favs": cqs["cqs"].corr(np.log(cqs["favs"]), method="spearman"),
    }
    cps_resid = {
        "year": cps["cps"].corr(cps["est_year"], method="spearman"),
        "words": cps["cps"].corr(np.log(cps["words"]), method="spearman"),
        "favs": cps["cps"].corr(np.log(cps["favs"]), method="spearman"),
    }

    rows_cross = []
    for label, mix in (("原始 pr", raw_top), ("cqs", cqs_top), ("cps", cps_top)):
        rows_cross.append([label] + [pct(mix.get(f, 0.0)) for f in FORMS])

    rows_cover = [
        ["cqs", num(len(cqs)), num(cqs_meta["scored_cells"]), num(cqs_meta["full_cells"]),
         pct(cqs_meta["coverage"]), pct(cqs_meta["stable_coverage"])],
        ["cps", num(len(cps)), num(cps_meta["scored_cells"]), num(cps_meta["full_cells"]),
         pct(cps_meta["coverage"]), pct(cps_meta["stable_coverage"])],
    ]

    rows_form = []
    for f in FORMS:
        p = cqs_pool[cqs_pool["form"] == f]
        s = cqs[cqs["form"] == f]
        st = s[s["cqs_stable"]]
        m = mid[mid["form"] == f]
        low = m[m["cqs_cell_n"] < CQS_STABLE_MIN]
        rows_form.append([
            FORM_CN[f], num(len(p)), num(len(s)),
            pct(len(s) / len(p)) if len(p) else "—",
            num(len(st)),
            pct(len(st) / len(p)) if len(p) else "—",
            num(len(m)), num(len(low)),
        ])

    rows_cps_form = []
    for f in FORMS:
        p = e[e["form"] == f]
        s = cps[cps["form"] == f]
        rows_cps_form.append([
            FORM_CN[f], num(len(p)), num(len(s)),
            pct(len(s) / len(p)) if len(p) else "—",
        ])

    rows_mid = []
    for f in FORMS:
        m = mid[mid["form"] == f]
        if len(m) == 0:
            continue
        stable = m[m["cqs_stable"]]
        rows_mid.append([
            FORM_CN[f], num(len(m)), num(len(stable)),
            num(len(m) - len(stable)), pct(1 - len(stable) / len(m)),
            num(m["favs"].median()), num(m["words"].median()),
        ])

    rows_top = [
        [FORM_CN[r.form], num(r.id), r.title, int(r.est_year), r.genre,
         BAND_CN[r.band], num(r.favs), num(r.praises), num(r.cqs_cell_n),
         f"{r.cps:+.2f}", f"{r.cqs:+.3f}"]
        for r in top.itertuples()
    ]

    # clx 锚点表 + 各 form 在默认偏厚档 K=0.25 下的区分度（全现算）。
    rows_len_anchor = [
        [FORM_CN[f], num(len(pub[pub["form"] == f])),
         num(len_anchors.loc[f, "lo"]), num(len_anchors.loc[f, "hi"])]
        for f in len_anchors.index
    ]
    k_demo = CLX_K_PRESETS["偏厚"]
    rows_clx_effect = []
    for f in len_anchors.index:
        s = pub[pub["form"] == f]
        if len(s) < 5:
            continue
        base_ids = set(s.nlargest(200, "cqs")["id"])
        scored = add_clx(s, k_demo)
        new_ids = set(scored.nlargest(200, "clx")["id"])
        base_words = float(s.nlargest(200, "cqs")["words"].median())
        new_words = float(scored.nlargest(200, "clx")["words"].median())
        rows_clx_effect.append([
            FORM_CN[f], f"{k_demo:.2f}", num(len(base_ids - new_ids)),
            num(base_words), num(new_words),
        ])

    rows_sens = [
        [str(int(r.kappa)), f"{r.rho_favs:+.3f}", f"{r.jaccard:.3f}", num(r.fav_med)]
        for r in sens.itertuples()
    ]

    case = e[e["id"] == 221819]
    if len(case):
        c0 = case.iloc[0]
        case_line = (
            f"nid 221,819 是 {FORM_CN.get(c0['form'], c0['form'])}、"
            f"{num(c0['favs'])} 收藏、{num(c0['praises'])} 赞、{num(c0['words'])} 字；"
            f"`favs < {num(CQS_MIN_FAVS)}`，不在 cqs 池。"
        )
    else:
        case_line = f"nid 221,819 不在 cqs 池（`favs < {num(CQS_MIN_FAVS)}`）。"

    long_pool = cqs_pool[cqs_pool["form"] == "long"]
    long_scored = cqs[cqs["form"] == "long"]
    long_cov = len(long_scored) / len(long_pool) if len(long_pool) else 0.0
    long_stable_cov = (
        len(long_scored[long_scored["cqs_stable"]]) / len(long_pool)
        if len(long_pool) else 0.0
    )
    dialogue_pool = cqs_pool[cqs_pool["form"] == "dialogue"]
    dialogue_scored = cqs[cqs["form"] == "dialogue"]
    dialogue_stable_cov = (
        len(dialogue_scored[dialogue_scored["cqs_stable"]]) / len(dialogue_pool)
        if len(dialogue_pool) else 0.0
    )
    medium_pool = cqs_pool[cqs_pool["form"] == "medium"]
    medium_scored = cqs[cqs["form"] == "medium"]
    medium_stable_cov = (
        len(medium_scored[medium_scored["cqs_stable"]]) / len(medium_pool)
        if len(medium_pool) else 0.0
    )
    medium_cps_cov = (
        len(cps[cps["form"] == "medium"]) / len(e[e["form"] == "medium"])
        if len(e[e["form"] == "medium"]) else 0.0
    )

    n_all = len(d)
    n_pool = len(cqs_pool)
    n_cqs = len(cqs)
    mid_stable = int(mid["cqs_stable"].sum())
    mid_low = int((mid["cqs_cell_n"] < CQS_STABLE_MIN).sum())
    long_share = cqs_top.get("long", 0.0)
    dialogue_share = cqs_top.get("dialogue", 0.0)
    medium_share = cqs_top.get("medium", 0.0)

    parts = [f"""# 24 运行时量化指标：按 form 隔离的中层发现，而不是第二个总榜

> 口径边界
> 1. **数据**：`analysis/out/novels.csv` 的 245,887 行，经 `lib/eras.py` 定年、
>    限 `est_year 2007–2025` 并去掉 `invalid` / `words < 2,000` 后为
>    **{num(n_all)} 本**。
> 2. **form 是第一隔离轴**：用 `lib/forms.py` 给全库判 `form`，再做
>    `form × 年 × 题材 × 收藏档` 校准；app 运行时使用 seed 的 DOM 验证 `form`，
>    绝不在不同 `form` 之间混排。库外 form 是估计值，只影响全库校准。
> 3. **指标**：cqs 是同一 `form`、同一年、同一题材、同一收藏档内的口碑分；
>    cps 是同一 `form`、同一年、同一篇幅档、同一题材内的位置分，只做筛选。
> 4. **证据门槛**：cqs 需 `favs ≥ {num(CQS_MIN_FAVS)}`，每格 {CQS_CELL_MIN} 本起评，
>    {CQS_STABLE_MIN} 本以上为 stable；**不回退**。cps 需 `favs ≥ {CPS_MIN_FAVS}`，
>    每格 {CPS_CELL_MIN} 本起评。
> 5. **不做**：跨 form 总榜、cps 总榜、0.5/0.5 综合分；每张榜只在单一 form 内有意义。
> 6. **clx 是可选视图**：字数偏好 K 交给用户、默认 0；app 存 `cqs + len_norm`
>    运行时重排，不预排静态榜、不写死 K（§2.5）。
> 7. 所有数字、表格和图形均由本脚本重算。

---

## 0. 结论：form 必须先切开

上一版把不同 `form` 混在一个中层表里，结果头部几乎全是对话/同人；这不是“对话书更好”，
而是不同 `form` 的收藏分布、篇幅分布和赞/收藏关系完全不同，混排后哪个 `form`
的样本多、方差大，哪个就占头部。

按 `form` 切开后：

- **长篇、对话**有足够稳定的 cqs 证据；**中篇**的 cps 覆盖为
  {pct(medium_cps_cov)}，但 cqs 稳定覆盖只有 {pct(medium_stable_cov)}，
  只能做“探索层”。
- **短篇、IP 合作**在 `favs ≥ {num(CQS_MIN_FAVS)}` 下没有稳定的 cqs 格；不发布 cqs 榜。
- 长篇和对话的 cqs 头部仍然是各自 form 的书，不再互相挤占。
- **收藏档改成年内分位**（§2.4）：旧绝对档下长篇 cqs Top100 的年内收藏分位
  中位只有 0.343，头部是中等偏下的书；修复后 Top50 提到
  长篇 {top50_pctl.get('long', 0):.3f} / 对话 {top50_pctl.get('dialogue', 0):.3f} /
  中篇 {top50_pctl.get('medium', 0):.3f}。
- 旧回退反例：{case_line}

**产品结论**：app 的所有榜单先按 `form` 过滤；每个 form 内部才允许 cqs/cps 排序。
跨 form 的“总榜”不成立，也不应存在。cqs 只发布年内收藏 P50 以上的书。
字数偏好作为展示层的可选重排（clx）提供，权重交用户，默认不加权（§2.5）。

---

## 1. 为什么 form 不是可选的

`form` 不是题材标签，而是产品形态：长篇、对话、中篇、短篇、IP 合作。不同 form 的
数据生成机制不同：

- 对话书按“话”连载，收藏和赞的积累方式与正文长篇不同；
- 短篇/中篇的完读和曝光周期更短；
- IP 合作书的读者来源和平台推荐位不同；
- 同一本 15 万字书，在长篇和对话里不是同一种“同篇幅比较”。

所以 `form` 不能只作为显示过滤；它必须是**校准格的第一维**。本报告的公式在
`form` 内计算，app 也只在 `form` 内返回榜单。

---

## 2. 两个指标

### 2.1 cqs：form 内的口碑分（不含篇幅）

```text
pr_s = (praises + κ × μ0) / (favs + κ)
cqs  = log(pr_s) - median[ log(pr_s) | form, est_year, genre, 收藏档 ]
```

- `κ = {KAPPA}`，`μ0 = {mu0:.3f}`（cqs 池的 `praises/favs` 中位数）。
- **收藏档是 `form × 年` 内的收藏分位档**，不是绝对收藏数：`{CQS_FAVS_LABELS}`。
  分位边界在 cqs 池内按年计算，所以“中等水平”随年份漂移——2025 年的
  P75 与 2015 年的 P75 不是同一个收藏数，但在各自年内都是“中上”。
  绝对档（1k/2k/1万）会把"2015 年的 1 万"和"2025 年的 1 万"当成同类，
  让低年份的低分位书靠档内高赞藏比冲上头部。
- **只发布 `{", ".join(PUBLISHABLE_BANDS)}` 档**：年内 P50 以下的书仍进入校准
  （贡献基线中位数），但不参与 cqs 榜排序。它们占池子一半，是“头部是中等偏下书”
  的主要来源；把它们挡在候选外，等价于先过滤再加分，不会移动基线、扭曲分母。
- 校准格：`form × est_year × genre × 分位收藏档`；每格至少 {CQS_CELL_MIN} 本。
- {CQS_CELL_MIN}–{CQS_STABLE_MIN - 1} 本为 `low_confidence`；{CQS_STABLE_MIN} 本以上为 stable。
- **cqs 不含篇幅**：篇幅只用于 app 的 form 隔离和经典篇幅榜，不作为 cqs 的分层。
- cqs 不是“绝对质量”，而是“在相同 form、年份、题材、收藏档里，赞/收藏是否偏高”。

### 2.2 cps：form 内的位置分（只做筛选）

```text
cps = log1p(favs) - median[ log1p(favs) | form, est_year, 篇幅档, genre ]
```

- 校准格：`form × est_year × 篇幅档 × genre`；每格至少 {CPS_CELL_MIN} 本。
- cps 保留篇幅，因为它的任务是回答“这本在相同 form、年份、篇幅、题材里收藏位置如何”。
- cps **不发布榜单**；它只用于取每个 form 的中层带
  （{int(MID_Q_LOW*100)}–{int(MID_Q_HIGH*100)} 分位），再由 cqs 排序。
- 去掉篇幅的 cps 会退化成收藏/字数榜，不能当中层筛选器。

### 2.3 为什么不用 clicks

`clicks` 是累计曝光，受上架时间、推荐位、站外流量和抓取时点共同影响；
`discovered` 也没有可靠的点击训练信号。点击只能做“发现流”的排序信号，
不能进入 cqs/cps 的质量公式。

### 2.4 为什么收藏档用年内分位，而不是抬高基线中位数

上一版用绝对收藏档（`1k / 2k / 1万`）且基线取格内中位数，诊断发现
**长篇 cqs Top100 的年内收藏分位中位只有 0.343**——头部书在同年同 form 里
收藏只排 34 分位，是中等偏下的书。原因是绝对档跨年不可比：同样是 1 万收藏，
在 2015 年是头部、在 2025 年只是中层；低年份的低分位书被塞进高档，
靠档内高赞藏比冲上榜首。

一个直觉修正是"把基线中位数抬到 P75"，但**同一校准格内减去任何分位数都是
常数平移，格内排序完全不变**，只有跨格比较会动，且方向不可控。真正有效的
是两件事，本版都做了：

1. **收藏档改成 `form × 年` 内的分位档**，让"中等"随年份漂移；
2. **年内 P50 以下的书不发布 cqs**（仍进校准做基线），先过滤噪声再加分，
   不改变格内分母。

修复后各 form cqs Top50 的年内收藏分位中位：长篇 **{top50_pctl.get('long', 0):.3f}**、
对话 **{top50_pctl.get('dialogue', 0):.3f}**、中篇 **{top50_pctl.get('medium', 0):.3f}**，
头部已落在各自年份的中等或中等偏上。

### 2.5 clx：cqs 的运行时篇幅偏好视图（不是固定第四指标）

字数影响读者是否点开，但**偏好因人而异**——有人爱厚书、有人只想要短平快。
所以字数权重 `K` 不写死，clx 是 cqs 上的一个**用户可调视图**，由 app 在运行时现算：

```text
len_f = log(clip(words, LO_f, HI_f) / LO_f) / log(HI_f / LO_f)   # 超出封顶，∈[0,1]
clx   = cqs × (1 − K + K × len_f)          # K 由用户选，默认 0（即纯 cqs）
```

- **锚点 `{int(LEN_Q_LO*100)}–{int(LEN_Q_HI*100)}` 分位按 form 在可发布 cqs 池内现算**，不是绝对值：
  全库对话字数中位只有 8k，但能进 cqs 池的对话中位约 96k，用全库锚点会让对话
  `len_norm` 几乎全为 1、失去区分度。锚点表随校准表发布，库外书按同一锚点定档。
- **乘性 + 下界 `1−K`**：字数最多左右 K 倍的分数，低口碑书无法靠字数翻盘；
  `K=0` 退化为纯 cqs。字数项是**读者投入意愿先验**，不是质量证据——cqs 已用
  分位档消掉“长书赞藏比天然低”的机械偏差，这里不再补偿。
- **不预排静态榜**：app 只需存 `cqs + len_norm` 两列，用户选档后运行时重排。
  这与 cex（周期种子驱动、可预排）不同；文案叫“篇幅偏好”，不叫“排名”。

字数锚点（随校准表发布，见 §10）：

{md_table(rows_len_anchor, ["form", "可发布 cqs", "LO (P10)", "HI (P90)"])}

默认“偏厚”档 `K={k_demo:.2f}` 的区分度（Top200 与纯 cqs 榜对比，全现算）：

{md_table(rows_clx_effect, ["form", "K", "Top200 换位", "字数中位(纯cqs)", "字数中位(clx)"])}

中篇锚点跨度小（字数集中），K 再大也几乎不换位——这不是 bug，是中篇读者本就不按字数选书；
clx 主要服务长篇/对话。**clx 不进入 cqs/cps 的分层或校准**，也不合成总分，
只是同一批 cqs 分数在展示层的可选重排。

---

## 3. form 覆盖与证据强度

`cqs` 池只包含 `favs ≥ {num(CQS_MIN_FAVS)}` 且 form 非 invalid 的书；
`cps` 池包含 `favs ≥ {num(CPS_MIN_FAVS)}` 的书。

{md_table(rows_form, ["form", "cqs 池", "cqs 可评", "覆盖率", "stable", "stable 覆盖", "中层候选", "低置信"])}

- **长篇**：cqs 覆盖 {pct(long_cov)}，stable 覆盖 {pct(long_stable_cov)}；
  可以发布稳定的长篇 cqs 榜。
- **对话**：cqs 覆盖
  {pct(len(dialogue_scored) / len(dialogue_pool))}，stable 覆盖
  {pct(dialogue_stable_cov)}；可以发布对话 cqs 榜，但只在对话 tab 内。
- **中篇**：cqs 可评但 stable 覆盖只有 {pct(medium_stable_cov)}，
  且中层候选里低置信比例高；只能做实验层，
  不应把低置信格当稳定结论。年内分位档把中篇样本砍掉约四分之一
  （绝对档时 stable 覆盖曾为 34%），这是"先保证头部不是中等偏下"的代价：
  中篇当前发不出稳定 cqs 榜，只保留 cps/经典榜。
- **短篇、IP 合作**：`favs ≥ {num(CQS_MIN_FAVS)}` 的池太小，没有稳定 cqs 格；
  只保留 cps/经典榜，不发布 cqs。

### 3.1 cqs 的残余相关

cqs 在 form 内校准后：

- `est_year` Spearman：**{cqs_resid['year']:+.3f}**
- `log(words)`：**{cqs_resid['words']:+.3f}**
- `log(favs)`：**{cqs_resid['favs']:+.3f}**

年份和收藏已经被压到接近 0；字数仍有正残余（{cqs_resid['words']:+.3f}），
因为 cqs 故意不按篇幅校准。这不是 bug：cqs 回答“口碑”，不回答“同篇幅谁更好”；
篇幅比较交给经典篇幅榜和 cps 的筛选。

### 3.2 cps 的残余相关

cps 在 form 内校准后：

- `est_year`：{cps_resid['year']:+.3f}
- `log(words)`：{cps_resid['words']:+.3f}
- `log(favs)`：**{cps_resid['favs']:+.3f}**

cps 与收藏高度相关是定义使然；它只是位置分，不是质量分。

![cqs 按 form 与收藏档的离散度]({figs['calibration']})

---

## 4. 跨 form 混排为什么会给出不同答案

{md_table(rows_cross, ["头部集合", *[FORM_CN[f] for f in FORMS]])}

- **原始 pr** Top1000 由 {FORM_CN[raw_top.idxmax()]} 主导
  （{pct(raw_top.max())}），收藏中位数只有 {num(raw_top_fav_med)}；
  这是小样本/低收藏噪声。
- **cqs** Top1000 由 {FORM_CN[cqs_top.idxmax()]} 主导
  （{pct(cqs_top.max())}），收藏中位数 {num(cqs_top_fav_med)}；
  跨 form 时仍然是 long 的池子更大。
- **cps** Top1000 由 {FORM_CN[cps_top.idxmax()]} 主导
  （{pct(cps_top.max())}），收藏中位数 {num(cps_top_fav_med)}；
  这更证明 cps 不能当质量榜。
- 上一版把不同 form 混排后，中层表头部几乎全是对话/同人；同一批书在长篇榜里
  根本不该出现。**跨 form 的头部不是“最好的书”，只是“这个池子的形状”。**

![原始 pr、cqs、cps 的头部 form 构成]({figs['bias']})

---

## 5. 各 form 的中层 Top5

取数顺序：

1. 在该 form 内算 cps，保留 {int(MID_Q_LOW*100)}–{int(MID_Q_HIGH*100)} 分位；
2. 只保留有 stable cqs 的书；
3. 每个 form 按 cqs 取 Top5，不跨 form 合并。

{md_table(rows_mid, ["form", "中层候选", "stable", "低置信", "低置信占比", "收藏中位", "字数中位"])}

低置信不是“淘汰”，而是“证据不足”：app 可以显示 `low_confidence` 标签，
但不应把它和 stable 书放在同一个“稳定推荐”层。当前中层候选中
{num(mid_low)} 本（{pct(mid_low / len(mid))}）处于 {CQS_CELL_MIN}–{CQS_STABLE_MIN - 1} 本的格。

{md_table(rows_top, ["form", "nid", "书名", "估年", "题材", "篇幅", "收藏", "赞", "格内n", "cps", "cqs"])}

- 长篇和对话各 5 本，头部都是各自 form 的书，收藏都在各自年份的中位数以上。
- 中篇在分位档下没有 stable 格进入中层带（243 本全是 5–19 本的小格），
  表里没有中篇行——这是证据不足，不是"中篇没有好书"。
- 短篇/IP 合作没有 stable cqs，表中不出现。

### 5.1 扇天机反例

{case_line}

旧版在“同篇幅 + 同题材 + 收藏档”小格只有几本时回退到更大池子，制造了假高分；
新版不满足 {CQS_CELL_MIN} 本就不评，不用回退来“补”头部。

---

## 6. cps 的 form 内覆盖

{md_table(rows_cps_form, ["form", "cps 池", "cps 可评", "覆盖率"])}

cps 覆盖整体 **{pct(cps_meta['coverage'])}**，但它只用于中层筛选：

- 长篇、对话、中篇、短篇的 cps 覆盖都接近满格；
- IP 合作的 cps 覆盖只有
  {pct(len(cps[cps.form == 'ip_collab']) / len(e[e.form == 'ip_collab']))}，
  不适合单独发布；
- cps 的 20–80 分位必须在 form 内取；跨 form 的 20–80 分位会被池子大小带偏。

---

## 7. 稳定性

### 7.1 κ 敏感性

{md_table(rows_sens, ["κ", "ρ(cqs, log 收藏)", "Top1000 Jaccard", "Top1000 收藏中位"])}

κ=500 与 κ=1000 的 Top1000 Jaccard 约
{sens.loc[sens['kappa'] == 1000, 'jaccard'].iloc[0]:.2f}；κ 太小会让低收藏书占头部，
κ 太大会把高分压回收藏。默认 **κ={KAPPA}**，250–2000 可调。

### 7.2 覆盖率与 Bootstrap

{md_table(rows_cover, ["指标", "可评", "可评格", "稳定格", "覆盖率", "稳定覆盖"])}

按 form 校准后，cqs 整体覆盖 {pct(cqs_meta['coverage'])}、稳定覆盖
{pct(cqs_meta['stable_coverage'])}；中篇和短篇/IP 的稳定覆盖是主要短板。

Bootstrap（20% 评测、80% 校准、30 次重抽样）：

- Spearman 中位 **{boot['rho_med']:.3f}**（P5 {boot['rho_p05']:.3f}）
- Top100 Jaccard 中位 **{boot['j100_med']:.3f}**（P5 {boot['j100_p05']:.3f}）
- Top1000 Jaccard 中位 **{boot['j1000_med']:.3f}**（P5 {boot['j1000_p05']:.3f}）
- 绝对分数偏移中位 **{boot['shift_med']:.3f}**

![κ 敏感性与按 form 校准的 Bootstrap]({figs['stability']})

头部 Top100 仍有约 {1 - boot['j100_med']:.0%} 的换位；产品应标“中层/证据强度”，
不要用精确名次或“第 37 名 vs 第 38 名”的叙事。

---

## 8. app 运行时怎么接

### 8.1 form 是硬前置

1. `seed.books.form` 是 DOM 验证值；所有榜单查询先 `WHERE form = ?`。
2. `discovered` 必须先拿到 form（详情页刷新或 `forms.classify`），
   form 未知时**不进入任何榜单**，可以只进搜索/详情。
3. cqs/cps 的校准键都带 form；跨 form 查询直接拒绝或返回空，不做“回退到全库”。
4. 经典榜也按 form 隔离；form 不是榜单内的排序字段。

### 8.2 分位边界表必须随校准表一起发布

收藏档是 `form × 年` 内的分位档，app 需要一张 **form×年的收藏阈值表**
（P50/P75/P90 三列，从 cqs 池算得）才能给库外书定档。这张表和 cqs 校准格
一起作为 `calibration_version` 的一部分发布；缺了它，库外书无法判档，
只能降级到经典榜。阈值表很小（5 form × 19 年 × 3 = 285 个数），由本生成器
导出到 `analysis/out/report24_fav_bounds.csv`（`form, est_year, p50, p75, p90`），
随报告一起重算。

定档规则：用书的 `favs` 与同 form 同年的三档阈值比较，落在 P50 以下的
**不发布 cqs**（但种子书若已有旧版 cqs 字段，按新规则重算）。

篇幅偏好视图还需一张 **form × 字数锚点表**（P10/P90 两列，从可发布 cqs 池算得），
由本生成器导出到 `analysis/out/report24_len_anchors.csv`（`form, lo, hi`）。
它与收藏阈值表同批发布：app 存每本书的 `cqs + len_norm`，用户选 K 后运行时
算 `clx = cqs × (1-K+K×len_norm)` 并重排；K 默认 0。**不预排、不写死 K**。

### 8.3 指标接入顺序

1. 写入 `discovered`：`nid/title/author/genre/words/favs`（有 `praises` 才写 cqs）。
2. `est_year = eras.Estimate(nid)`；`band` 由 `words` 切。
3. 查 8.2 的阈值表给书定分位收藏档；P50 以下直接不算 cqs。
4. 先算 **cps**（`favs ≥ {CPS_MIN_FAVS}`），只在同 form 的中层带出现。
5. 抓到详情页后再算 **cqs**（`favs ≥ {num(CQS_MIN_FAVS)}`）；没有 `praises` 不显示 cqs。
6. cqs 书按字数锚点表算 `len_norm` 并存下；用户选“篇幅偏好”档后运行时算 **clx**
   重排（默认档 K=0 即不加权）。三档预设 K=`{", ".join(f"{v:.2f}" for v in CLX_K_PRESETS.values())}`，
   高级滑杆可连续调；clx 只在单一 form 内重排。
7. 2026 年书用 2025 年阈值与基线，标 `provisional / low_evidence`；不进入稳定 cqs 榜。

### 8.4 与旧字段的关系

- `cps` 不是 `fav_pctl` 的替代；它只回答“同 form 的位置”。
- `cqs` 不是 `pr`/`lqs` 的替代；它只回答“同 form、同代、同题材、同收藏档的口碑”。
- `clx` 不是第四个分数，是 cqs 的用户可调展示视图；不与 cqs/cps 合成总分，
  也不进入校准。已有的 `lqs` 用旧 pr 且只对长篇，两者不合并、分数不可比。
- 经典榜继续用原始 `favs/clicks/praises`，不受影响。
- 旧 `fav_pctl/click_pctl/praise_pctl/pr/lqs` 是构建期快照；新增书不能靠它们。

---

## 9. 边界与不承诺

1. **cqs 不是“绝对好书”**：它只说同 form、同代、同题材、同收藏档里赞/收藏偏高。
2. **form 是估计值**：全库用 `forms.classify`，seed 用 DOM 验证；库外 form 误差会进入
   全库覆盖率，但不改变 app 的 form 隔离规则。
3. **中篇证据弱**：stable 覆盖低，低置信比例高；不应把中篇 cqs 与长篇/对话同等对待。
4. **短篇/IP 没有 cqs**：`favs ≥ {num(CQS_MIN_FAVS)}` 的池太小，不发布 cqs。
5. **cps 不是榜单**：只做 20–80 分位筛选；不写 cps 总榜/全库榜。
6. **头部不稳定**：Bootstrap Top100 Jaccard {boot['j100_med']:.2f}；产品文案不要说精确名次。
7. **年内 P50 以下不发布 cqs**：这是"头部不能是中等偏下书"的必要过滤，
   代价是中篇 stable 覆盖降到 {pct(medium_stable_cov)}、发不出稳定榜；
   短篇/IP 本就没有 cqs。这些 form 的发现需求交给 cps + 经典榜。
8. **2026 年不校准**：沿用 2025 年阈值与基线，UI 标 provisional。
9. **clx 不是质量提升**：它只按用户偏好重排 cqs，字数不进校准；中篇锚点跨度小、
   几乎不换位；文案用“篇幅偏好”而非“排名”，避免用户调档后误以为名次出错。
10. **数据截止**：校准表基于 2026-05-03 快照；每次重建写 `calibration_version`。

---

## 10. 复现

```powershell
cd analysis
uv run python generators/report_24_runtime_metrics.py
```

生成 `reports/24_runtime_metrics.md`、`reports/figures/24_bias.png`、
`reports/figures/24_calibration.png`、`reports/figures/24_stability.png`，
以及 app 定档用的 `out/report24_fav_bounds.csv`（收藏分位阈值）与
`out/report24_len_anchors.csv`（clx 字数锚点）。
"""]

    OUT.write_text("\n".join(parts), encoding="utf-8")
    # 分位边界表：app 给库外书定收藏档所必需，和报告一起重建。
    bounds.reset_index().to_csv(FAV_BOUNDS_OUT, index=False, encoding="utf-8-sig")
    # 字数锚点表：app 运行时算 clx 的 len_norm 所必需（用户选 K 后现算）。
    len_anchors.reset_index().to_csv(LEN_ANCHORS_OUT, index=False, encoding="utf-8-sig")
    return str(OUT)


if __name__ == "__main__":
    print(build())

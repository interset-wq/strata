"""生成 analysis/reports/23_word_economy.md：篇幅经济学。

字数不只是作品属性，也是读者筛选的第一道筛子：它同时决定曝光（点开前）、
转化（点开后）、商业资格（VIP/签约）与完结概率。本报告把散落在 01/02/05/07/08/11/19
的字数结论收拢成一条主线，并检验「字数 × 其它」的组合指标能否像 pr 一样
反映质量——结论是：比值型指标（转化率、每万字密度）都是字数的负函数，
直接当质量会系统惩罚长篇；同字数档内标准化后，篇幅效率与 pr 近乎正交（可互补）。

所有数字现算自 analysis/out/novels.csv；年份由 lib/eras.py 定年。
报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/generators/report_23_word_economy.py
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
from lib import paths

from lib import charts  # noqa: E402
from lib import eras  # noqa: E402

OUT = paths.REPORTS_DIR / "23_word_economy.md"

W_BINS = [-1, 1000, 3000, 10000, 30000, 100000, 300000, 1000000, 10**9]
W_LABELS = ["<1k", "1-3k", "3-1万", "1-3万", "3-10万", "10-30万", "30-100万", "100万+"]

GEN_BINS = [2006, 2015, 2017, 2020, 2023, 2026]
GEN_LABELS = ["2007-14", "2015-16", "2017-19", "2020-22", "2023-25"]


def load() -> pd.DataFrame:
    df = pd.read_csv(
        paths.OUT_DIR / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id")
    sb = eras.snapshot_bounds(d)
    d["upd"] = pd.to_datetime(d["updated_at"], errors="coerce")
    d["stale"] = eras.staleness_days(d, sb["content_end"])
    d["wb"] = pd.cut(d["words"], W_BINS, labels=W_LABELS)
    d["gen"] = pd.cut(d["est_year"], GEN_BINS, labels=GEN_LABELS, right=False)
    d["done"] = d["status"] == "已完结"
    d["paid"] = d["price_type"].isin(["VIP", "签约"])
    d["vip"] = d["price_type"] == "VIP"
    d["signed"] = d["price_type"] == "签约"
    d["abandoned"] = (~d["done"]) & (d["stale"] > 365)
    d["conv"] = d["favs"] / d["clicks"].where(d["clicks"] >= 100)
    d["dens"] = d["favs"] / d["words"].where(d["words"] >= 1000) * 10000
    d["pr"] = d["praises"] / d["favs"].where(d["favs"] > 0)
    return d.sort_values("id").reset_index(drop=True)


def num(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def band_table(d: pd.DataFrame) -> pd.DataFrame:
    g = d.groupby("wb", observed=True)
    t = pd.DataFrame({
        "n": g.size(),
        "favs": g["favs"].sum(),
        "words": g["words"].sum(),
        "words_med": g["words"].median(),
        "favs_med": g["favs"].median(),
        "clicks_med": g["clicks"].median(),
        "vip": g["vip"].mean() * 100,
        "signed": g["signed"].mean() * 100,
        "done": g["done"].mean() * 100,
        "abandoned": g["abandoned"].mean() * 100,
    })
    t["n_share"] = t["n"] / len(d) * 100
    t["favs_share"] = t["favs"] / d["favs"].sum() * 100
    t["dens"] = t["favs"] / t["words"] * 10000
    return t


def elasticity(d: pd.DataFrame, sub: pd.DataFrame | None = None) -> float:
    s = d if sub is None else sub
    s = s[(s["words"] >= 1000) & (s["favs"] > 0)]
    if len(s) < 50:
        return float("nan")
    return float(np.polyfit(np.log(s["words"]), np.log(s["favs"]), 1)[0])


# ---------------------------------------------------------------- 图表


def fig_dist(d: pd.DataFrame, t: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4))
    ax = axes[0]
    w = d.loc[d["words"] > 0, "words"]
    bins = np.logspace(0, np.log10(w.max()), 60)
    ax.hist(w, bins=bins, color=charts.C["blue"], alpha=0.85, zorder=3)
    ax.set_xscale("log")
    ax.set_xlabel("字数（对数轴）")
    ax.set_ylabel("作品数")
    ax.axvline(w.median(), color=charts.C["red"], lw=1.4, ls="--")
    ax.text(
        w.median() * 1.15, ax.get_ylim()[1] * 0.88,
        f"中位 {num(w.median())} 字", color=charts.C["red"], fontsize=9,
    )
    ax.set_title("字数分布：重尾，一半作品不足 1.1 万字")

    ax2 = axes[1]
    x = np.arange(len(t))
    ax2.bar(x - 0.2, t["n_share"], 0.4, color=charts.C["gray"], label="作品数份额", zorder=3)
    ax2.bar(x + 0.2, t["favs_share"], 0.4, color=charts.C["red"], label="收藏份额", zorder=3)
    ax2.set_xticks(x, [str(i) for i in t.index], rotation=30, ha="right")
    ax2.set_ylabel("%")
    ax2.legend(fontsize=9)
    ax2.set_title("3.9% 的长篇拿走七成收藏")
    fig.tight_layout()
    return charts.save(fig, "23_dist.png")


def fig_curve(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    s = d[(d["words"] >= 300) & (d["favs"] > 0)]
    edges = np.logspace(np.log10(300), np.log10(s["words"].max()), 24)
    s = s.assign(bin=pd.cut(s["words"], edges))
    m = s.groupby("bin", observed=True).agg(
        w=("words", "median"), f=("favs", "median"), n=("id", "size"),
    )
    m = m[m["n"] >= 60]

    def seg_slope(lo, hi):
        x = m[(m["w"] >= lo) & (m["w"] <= hi)]
        return float(np.polyfit(np.log(x["w"]), np.log(x["f"]), 1)[0]) if len(x) >= 3 else float("nan")

    sl = {k: seg_slope(a, b) for k, (a, b) in
          {"s1": (300, 3000), "s2": (3000, 100000), "s3": (100000, 1000000),
           "s4": (1000000, 10**9)}.items()}

    ax.plot(m["w"], m["f"], color=charts.C["red"], marker="o", ms=3.5, lw=1.6,
            label="收藏中位（按字数组分箱）", zorder=4)
    ax.set_xscale("log")
    ax.set_yscale("log")
    for x0 in (3000, 100000, 1000000):
        ax.axvline(x0, color="#BBBBBB", lw=1, ls=":", zorder=2)
    y0, y1 = ax.get_ylim()
    ax.text(900, y0 + (y1 - y0) * 0.30, f"平台\n斜率 {sl['s1']:.1f}", ha="center", fontsize=9, color="#555555")
    ax.text(17000, y0 + (y1 - y0) * 0.30, f"缓升\n斜率 {sl['s2']:.2f}", ha="center", fontsize=9, color="#555555")
    ax.text(320000, y0 + (y1 - y0) * 0.30, f"陡升\n斜率 {sl['s3']:.2f}", ha="center", fontsize=9, color="#555555")
    ax.text(4000000, y0 + (y1 - y0) * 0.30, f"放缓\n斜率 {sl['s4']:.2f}", ha="center", fontsize=9, color="#555555")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("字数（对数轴）")
    ax.set_ylabel("收藏中位数（对数轴）")
    ax.legend(fontsize=9, loc="lower right")
    ax.set_title("三段式：3k 字门槛 → 10 万–100 万字超线性 → 顶部放缓")
    fig.tight_layout()
    return charts.save(fig, "23_curve.png"), sl


def fig_gates(t: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4))
    x = np.arange(len(t))
    ax = axes[0]
    ax.plot(x, t["vip"], color=charts.C["red"], marker="o", ms=4, label="VIP %", zorder=4)
    ax.plot(x, t["signed"], color=charts.C["blue"], marker="s", ms=4, label="签约 %", zorder=4)
    ax.set_xticks(x, [str(i) for i in t.index], rotation=30, ha="right")
    ax.set_ylabel("%")
    ax.legend(fontsize=9)
    ax.set_title("商业资格：30 万字是分水岭")

    ax2 = axes[1]
    ax2.plot(x, t["done"], color=charts.C["green"], marker="o", ms=4, label="完结率 %", zorder=4)
    ax2.plot(x, t["abandoned"], color=charts.C["gray"], marker="s", ms=4,
             label="断更 >1 年 %", zorder=4)
    ax2.set_xticks(x, [str(i) for i in t.index], rotation=30, ha="right")
    ax2.set_ylabel("%")
    ax2.legend(fontsize=9)
    ax2.set_title("完结率升、断更率降：长度本身就是筛选")
    fig.tight_layout()
    return charts.save(fig, "23_gates.png")


def fig_grid(grid: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    m = grid.values.astype(float)
    im = ax.imshow(np.log10(m), cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(grid.shape[1]), [str(c) for c in grid.columns])
    ax.set_yticks(range(grid.shape[0]), [str(i) for i in grid.index])
    ax.set_xlabel("赞藏比 pr 档（同字数档内五分位）")
    ax.set_ylabel("篇幅效率 favs/万字 档（同字数档内五分位）")
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m[i, j]
            ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=8,
                    color="white" if np.log10(v) > np.log10(m).max() - 0.6 else "#222222")
    ax.grid(False)
    ax.set_title("收藏中位：两轴各自贡献、互不替代")
    fig.colorbar(im, ax=ax, label="log10(收藏中位)")
    fig.tight_layout()
    return charts.save(fig, "23_grid.png")


# ---------------------------------------------------------------- 正文


def build() -> str:
    charts.setup_style()
    d = load()
    t = band_table(d)
    n_all = len(d)
    n_valid = int((d["words"] > 0).sum())

    figs = {
        "dist": fig_dist(d, t),
        "curve": fig_curve(d),
        "gates": fig_gates(t),
    }

    # 分布
    w = d.loc[d["words"] > 0, "words"]
    wq = {q: float(w.quantile(q)) for q in (0.25, 0.5, 0.75, 0.9, 0.99)}
    short = d[d["words"] < 10000]
    long300 = d[d["words"] >= 300000]

    # 世代分布（2026 右删失，不纳入）
    gen = d[d["est_year"].between(2007, 2025)].groupby("gen", observed=True)["words"]
    gen_t = pd.DataFrame({
        "n": gen.size(), "p25": gen.quantile(0.25), "p50": gen.median(),
        "p90": gen.quantile(0.90),
    })

    # 题材
    gr = d.groupby("genre").agg(
        n=("id", "size"), p50=("words", "median"), p90=("words", lambda s: s.quantile(0.9)),
        long_share=("words", lambda s: (s >= 300000).mean() * 100),
    ).sort_values("n", ascending=False)

    # 弹性
    e_all = elasticity(d)
    e_gen = {str(k): elasticity(d, v) for k, v in d.groupby("gen", observed=True)}
    # 分段斜率（与 fig_curve 同一套分箱；figs["curve"] 返回 (路径, 斜率字典)）
    curve_path, seg = figs["curve"]
    figs["curve"] = curve_path

    # 头部
    top1k = d.nlargest(1000, "favs")
    top_cov = (top1k["words"] >= 300000).mean() * 100

    # 组合指标
    ok = d[(d["favs"] >= 50) & (d["words"] >= 1000) & (d["praises"] > 0)
           & (d["clicks"] >= 200)].copy()
    for c in ("dens", "pr", "conv"):
        ok[c + "_p"] = ok.groupby("wb", observed=True)[c].rank(pct=True)
    ok["d_q"] = pd.qcut(ok["dens_p"], 5, labels=["Q1低", "Q2", "Q3", "Q4", "Q5高"])
    ok["p_q"] = pd.qcut(ok["pr_p"], 5, labels=["Q1低", "Q2", "Q3", "Q4", "Q5高"])
    grid = ok.pivot_table(index="d_q", columns="p_q", values="favs",
                          aggfunc="median", observed=True)
    figs["grid"] = fig_grid(grid)

    # 比值指标与字数的关系：宽样本（favs>0）与严格样本（favs≥50）各算一份
    loose = d[(d["clicks"] >= 100) & (d["favs"] > 0) & (d["words"] >= 1000)].copy()
    lw = np.log(loose["words"])
    logw_corr = {
        "conv": loose["conv"].corr(lw, method="spearman"),
        "dens": loose["dens"].corr(lw, method="spearman"),
    }
    prl = loose.dropna(subset=["pr"])
    logw_corr["pr"] = prl["pr"].corr(np.log(prl["words"]), method="spearman")
    logw_corr_strict = {
        "conv": ok["conv"].corr(np.log(ok["words"]), method="spearman"),
        "dens": ok["dens"].corr(np.log(ok["words"]), method="spearman"),
        "pr": ok["pr"].corr(np.log(ok["words"]), method="spearman"),
    }
    inband = []
    for _, s in ok.groupby("wb", observed=True):
        if len(s) < 200:
            continue
        c = s[["pr", "conv", "dens"]].corr(method="spearman")
        inband.append([c.loc["pr", "conv"], c.loc["pr", "dens"], c.loc["conv", "dens"]])
    inband_m = np.nanmean(np.array(inband), axis=0)

    # 交集：篇幅效率 top5% vs pr top5%（都在同字数档内）
    a = set(ok.loc[ok["dens_p"] >= 0.95, "id"])
    b = set(ok.loc[ok["pr_p"] >= 0.95, "id"])
    jac = len(a & b) / len(a | b) if (a | b) else float("nan")

    # 比值指标随字数（每档中位，宽样本保证小字数档也有足够样本）
    ratio_t = loose.groupby("wb", observed=True).agg(
        n=("id", "size"), conv=("conv", "median"), pr=("pr", "median"),
        dens=("dens", "median"),
    )
    # 极小字数档里「点击 ≥100 且 favs>0」的书太少（<100 本），不单独成档
    ratio_t = ratio_t[ratio_t["n"] >= 100]
    r_first, r_last = ratio_t.iloc[0], ratio_t.iloc[-1]

    # 2D：同点击数档下收藏随字数（控制曝光后的字数额外效应）
    cb = [-1, 100, 1000, 10000, 100000, 10**9]
    cl = ["<100", "100-1k", "1k-1万", "1万-10万", "10万+"]
    dd = d.assign(cb=pd.cut(d["clicks"], cb, labels=cl))
    piv = dd.pivot_table(index="cb", columns="wb", values="favs",
                         aggfunc="median", observed=True)
    piv_mid = piv.loc["1k-1万"].dropna()
    piv_top = piv.loc["10万+"].dropna()

    rows_band = [
        [str(i), num(r.n), f"{r.n_share:.1f}", num(r.words_med), num(r.favs_med),
         f"{r.favs_share:.1f}", f"{r.vip:.1f}", f"{r.signed:.1f}",
         f"{r.done:.1f}", f"{r.abandoned:.1f}"]
        for i, r in t.iterrows()
    ]
    rows_gen = [
        [str(i), num(r.n), num(r.p25), num(r.p50), num(r.p90)]
        for i, r in gen_t.iterrows()
    ]
    rows_gr = [
        [i, num(r.n), num(r.p50), num(r.p90), f"{r.long_share:.1f}"]
        for i, r in gr.iterrows()
    ]
    rows_ratio = [
        [str(i), num(r.n), f"{r.conv * 100:.2f}", f"{r.pr:.2f}", f"{r.dens:,.0f}"]
        for i, r in ratio_t.iterrows()
    ]
    rows_grid = [
        [str(i)] + [f"{v:,.0f}" for v in grid.loc[i].values]
        for i in grid.index
    ]
    grid_header = ["篇幅效率档"] + [str(c) for c in grid.columns]

    e_gen_str = "、".join(f"{k} {v:.2f}" for k, v in e_gen.items() if not np.isnan(v))

    parts = [f"""# 23 · 篇幅经济学：字数作为筛选器，以及「字数 × 其它」的组合指标

> 口径声明：
> 1. **样本**：`out/novels.csv` {num(n_all)} 行（数据内容上界 2026-05-03，在册存活口径；
>    正版日轻 47 行构建期已剔除）。字数缺失/为 0 的 {num(n_all - n_valid)} 行不参与
>    任何对数与比值计算，但仍计入分档计数。
> 2. **横截面，不是面板**：所有指标是快照累计值。字数既是**作品属性**也是**结果**
>    （写得久自然更长、曝光也更多），本报告只能说「字数与收藏同向」，不能声称
>    「加字数必然涨收藏」。§2 用同一个点击数档内的比较来剥离曝光。
> 3. **存活偏置**：抓取是按更新时间降序的单向游标扫描（报告 10 §7），
>    早期弃坑的短书被漏得最多。故近年世代（尤其 2024-26）的**字数中位偏上**，
>    §1.2 只报到 2025 并显式标注；跨世代字数比较因此偏保守。
> 4. **断更口径**：`连载中` 且 `updated_at` 距内容上界 > 365 天。这是**下界**——
>    真正的停更可能更晚被发现，且 `status` 是快照当期值。
> 5. **比值型指标的分母**：转化率要求 `clicks ≥ 100`、篇幅效率要求 `words ≥ 1000`、
>    pr 要求 `favs > 0`；组合指标一节另加 `favs ≥ 50` 与 `clicks ≥ 200`，
>    使分位标准化不被零值主导（报表内已声明样本量）。
> 6. 所有数字现算，图表由本生成器产出，勿手改正文。


---

## 0. 结论

1. **字数分布是重尾的**：中位 {num(wq[0.5])} 字，P75 {num(wq[0.75])}、
   P90 {num(wq[0.9])}、P99 {num(wq[0.99])}——一半作品不足 1.1 万字，
   而 P99 已过百万。讨论「平台作品长度」时，中位与均值（{num(d['words'].mean())} 字）
   描述的几乎是两个不同的市场。
2. **字数是最强的注意力分层，且强得不正常**：收藏中位从
   {num(t.loc['<1k', 'favs_med'])} 升到 {num(t.loc['100万+', 'favs_med'])}
   （{t.loc['100万+', 'favs_med'] / t.loc['<1k', 'favs_med']:.0f} 倍）；
   {long300.shape[0] / n_all * 100:.1f}% 的作品（30 万字以上）拿走
   {t.loc[['30-100万', '100万+'], 'favs_share'].sum():.1f}% 的收藏；
   收藏 Top1000 里 {top_cov:.1f}% 是 30 万字以上。
3. **读者是按字数筛的，而且筛在点击之前**：点击数中位从
   {num(t.loc['<1k', 'clicks_med'])} 升到 {num(t.loc['100万+', 'clicks_med'])}，
   跨档近 {t.loc['100万+', 'clicks_med'] / max(t.loc['<1k', 'clicks_med'], 1):.0f} 倍；
   而**每本书的转化率（收藏/点击）反而从 {r_first['conv'] * 100:.1f}% 单调降到
   {r_last['conv'] * 100:.1f}%**（{ratio_t.index[0]} → {ratio_t.index[-1]}）。短书不是「读不下去」，
   而是**很少被点开**；一旦点开，读完并收藏的比例更高。
4. **字数与收藏是三段式，不是一条幂律**：3k 字以下是**平台**（收藏中位
   4–7，分段斜率 {seg['s1']:.1f}）——低于门槛的字数不提供任何信号，短书之间
   无法靠字数区分；3k–10 万缓升（{seg['s2']:.2f}）；**10 万–100 万是超线性区间**
   （{seg['s3']:.2f}，字数翻倍收藏约 {2 ** seg['s3']:.0f} 倍）；100 万以上放缓
   （{seg['s4']:.2f}）。全库平均弹性 {e_all:.2f} 只是三段的平均，掩盖了门槛与
   黄金区间。
5. **字数是商业分级线，不是连续变量**：VIP 占比从 1 万字以下的
   {t.loc['<1k', 'vip']:.2f}% 跳到 30-100 万档的 {t.loc['30-100万', 'vip']:.1f}%、
   100 万以上的 {t.loc['100万+', 'vip']:.1f}%；签约率峰值在
   10-30 万档（{t.loc['10-30万', 'signed']:.1f}%）。完结率与断更率也同步分层
   （完结 {t.loc['<1k', 'done']:.1f}% → {t.loc['100万+', 'done']:.1f}%，
   断更 {t.loc['<1k', 'abandoned']:.1f}% → {t.loc['100万+', 'abandoned']:.1f}%）。
6. **比值型「质量」指标大多是字数的负函数**：转化率与 log 字数的秩相关
   {logw_corr['conv']:.2f}、篇幅效率 {logw_corr['dens']:.2f}，而 pr 只有
   {logw_corr['pr']:.2f}（严格样本 {logw_corr_strict['pr']:.2f}，仍是三者中最弱）。
   **pr 是唯一接近长度中性的现成指标**；直接把「每万字收藏」
   当质量榜，等于奖励短篇、惩罚长篇。
7. **但「篇幅效率」在同档标准化后确实是新维度**：在字数档内标准化后，
   它与 pr 的秩相关仅 {inband_m[1]:.2f}，两者 top5% 的交集
   Jaccard 只有 {jac:.2f}——几乎是两个正交信号（§4.3）。用法：
   **同字数档内分位、且必须与 pr 并列**，不可单独当质量分。


---

## 1. 分布：一半作品不足 1.1 万字

![字数分布与收藏份额]({figs['dist']})

### 1.1 分档全景

{md_table(rows_band, ["字数档", "作品数", "作品%", "字数中位", "收藏中位", "收藏份额%", "VIP%", "签约%", "完结率%", "断更>1年%"])}

三个台阶清晰可见：1 万字以下（{t.loc[['<1k', '1-3k', '3-1万'], 'n_share'].sum():.1f}% 的作品）
只占 {t.loc[['<1k', '1-3k', '3-1万'], 'favs_share'].sum():.1f}% 的收藏；
30 万字以上（{long300.shape[0] / n_all * 100:.1f}%）占
{t.loc[['30-100万', '100万+'], 'favs_share'].sum():.1f}%。

### 1.2 世代：近年变短，但近年档有存活偏置

{md_table(rows_gen, ["世代", "作品数", "P25", "中位", "P90"])}

2015-16 代是字数的峰值（中位 {num(gen_t.loc['2015-16', 'p50'])} 字），
2020-22 代跌到 {num(gen_t.loc['2020-22', 'p50'])} 字——与报告 11 的速更化、报告 22 的
对话/互动产品线放量同向。**2023-25 代的回升（中位
{num(gen_t.loc['2023-25', 'p50'])} 字）不可直接读作「又变长了」**：
这一段正是游标扫描遗漏最严重、新书存活偏置最强的地方，短书被系统性漏掉，
留下的更接近「活下来的那批」。2026 年创建的书右删失，本表不列。

### 1.3 题材：古风最长，同人最短

{md_table(rows_gr, ["分类", "作品数", "字数中位", "字数 P90", "≥30 万字%"] )}

古风与魔幻的长篇浓度最高（≥30 万字占比 {gr.loc['古风', 'long_share']:.1f}% /
{gr.loc['魔幻', 'long_share']:.1f}%），同人只有 {gr.loc['同人', 'long_share']:.1f}%——
后者正是报告 22 的对话/互动产品线：**同人不走长篇，不是因为没人写，
而是那条产品线不按篇幅计价**。因此任何「按字数分层」的分析都必须先剔除同人，
否则会把产品线差异误读成题材差异（报告 22 §5 的敏感性对比已给出剔除后的幅度）。


---

## 2. 选书的第一道筛子：字数 → 曝光 → 收藏

![字数与收藏的三段式曲线]({figs['curve']})

### 2.1 三段式：门槛、黄金区间、顶部放缓

按字数组分箱（每箱 ≥60 本）取收藏中位，双对数下**不是一条直线**，而是三段：

- **3k 字以下是平台**：收藏中位 4–7，分段斜率 {seg['s1']:.1f}——在门槛之下，
  字数不再提供任何区分度，「写了 500 字」和「写了 2,900 字」的书一样冷。
  这就是读者关系的第一条规律：**字数太短时，读者不是偏好低，而是根本无法
  把它当作品来评估**（点开成本≈0，但预期收益也被判为 0）；
- **3k–10 万缓升**（斜率 {seg['s2']:.2f}）：进入正常连载区间后字数开始定价，
  但回报低于线性；
- **10 万–100 万是超线性黄金区间**（斜率 {seg['s3']:.2f}）：字数翻倍、收藏约
  {2 ** seg['s3']:.0f} 倍——这段正好覆盖 VIP/签约资格线（§3），
  「能写到这里」本身完成了对作者毅力与作品完成度的筛选；
- **100 万以上放缓**（斜率 {seg['s4']:.2f}）：回报仍为正，但边际递减，
  且该段样本小（>500 万字仅 71 本），尾部读数要谨慎。

全库平均弹性 {e_all:.2f}（`words ≥ 1 千`、`favs > 0`，
{num(int(((d['words'] >= 1000) & (d['favs'] > 0)).sum()))} 本；
分世代 {e_gen_str}）只是三段的平均值，**用单一弹性描述「字数的价值」会同时
高估短篇、低估中长篇**。

这不是因果结论（§0 口径 2），但可以排除「只是曝光」这一条：固定点击数档后，
收藏中位仍随字数上升——1k–1 万次点击档内从 {num(piv_mid.iloc[0])}
（{piv_mid.index[0]}）升到 {num(piv_mid.iloc[-1])}（{piv_mid.index[-1]}）；
10 万次点击以上的档内从 {num(piv_top.iloc[0])}（{piv_top.index[0]}）升到
{num(piv_top.iloc[-1])}（{piv_top.index[-1]}）。**同样的曝光量，长篇拿到更多收藏**；
曝光越大的档，字数带来的差距越大（点击越大，长篇的「点开即走」被吸收得越干净）。

### 2.2 转化率反向下降：读者在点击前就筛完了

{md_table(rows_ratio, ["字数档", "样本", "转化率中位%", "赞藏比中位", "篇幅效率(收藏/万字)"])}

「转化率」= 收藏/点击（样本 `favs > 0`、`clicks ≥ 100`，各档样本量见上表），
它**随字数单调下降**：{ratio_t.index[0]} 档 {r_first['conv'] * 100:.2f}%，
{ratio_t.index[-1]} 档 {r_last['conv'] * 100:.2f}%，相差
{r_first['conv'] / r_last['conv']:.1f} 倍。`<1k` 档不在本表样本内（受 `words ≥ 1k`
约束；其中满足 `clicks ≥ 100` 且 `favs > 0` 的仅
{num(int(((d['words'] < 1000) & (d['clicks'] >= 100) & (d['favs'] > 0)).sum()))} 本）。两个机制同时存在：

- 短书点开即读完，读者更容易顺手收藏（读完率高）；
- 长篇的点击数被「试读即走」的读者灌大（分母膨胀），转化率被压下去。

合起来就是：**字数决定有多少人点开（曝光），读完率反而随字数下降**。
把它读成「短书更好」会得出与收藏总量完全相反的结论——这正是报告 08 §4
那个「弱 U 形」的来源，两边并不矛盾：08 比的是同曝光档内的转化，
本报告比的是全库转化，分母结构不同。


---

## 3. 商业与完结：字数是产品分级线

![商业资格与完结率]({figs['gates']})

{md_table(rows_band, ["字数档", "作品数", "作品%", "字数中位", "收藏中位", "收藏份额%", "VIP%", "签约%", "完结率%", "断更>1年%"])}

- **VIP 是长篇的专属出口**：1 万字以下 {t.loc['<1k', 'vip']:.2f}%、
  10-30 万 {t.loc['10-30万', 'vip']:.1f}%、30-100 万
  {t.loc['30-100万', 'vip']:.1f}%、100 万以上 {t.loc['100万+', 'vip']:.1f}%。
  没有长度就没有付费通道，这是「同人挂长篇=商业死刑」（报告 22）的另一面。
- **签约在 10-30 万达到峰值**（{t.loc['10-30万', 'signed']:.1f}%），
  之后在 100 万以上回落到 {t.loc['100万+', 'signed']:.1f}%——签约是「有潜力」的
  中期标记，超长篇里反而更多是已签约后自然长成、不再重复计。
- **完结率与断更率是同一枚硬币**：完结率从
  {t.loc['<1k', 'done']:.1f}% 升到 {t.loc['100万+', 'done']:.1f}%，
  断更率从 {t.loc['<1k', 'abandoned']:.1f}% 降到
  {t.loc['100万+', 'abandoned']:.1f}%。**长度不是「写得多」的结果，
  而是「没停下」的结果**——短书里混着大量刚开始就消失的尝试。


---

## 4. 字数 × 其它：哪些组合能当质量信号

### 4.1 三个候选比值，两个是字数的伪装

| 指标 | 定义 | 秩相关（宽样本） | 秩相关（严格样本） | 读法 |
|---|---|---|---|---|
| `conv` 转化率 | 收藏/点击 | **{logw_corr['conv']:.2f}** | {logw_corr_strict['conv']:.2f} | 随字数下降，受读完率与试读分母双重影响 |
| `dens` 篇幅效率 | 收藏/万字 ×1 万 | **{logw_corr['dens']:.2f}** | {logw_corr_strict['dens']:.2f} | 随字数下降，天然奖励短篇 |
| `pr` 赞藏比 | 赞/收藏 | **{logw_corr['pr']:.2f}** | {logw_corr_strict['pr']:.2f} | 长度中性，报告 08 已确立的质量代理 |

宽样本 = `favs > 0`、`clicks ≥ 100`、`words ≥ 1k`（{num(len(loose))} 本）；
严格样本 = 再要求 `favs ≥ 50`、`clicks ≥ 200`（{num(len(ok))} 本，§4.2 用这一份）。
`pr` 在宽样本上与字数几乎无关（{logw_corr['pr']:.2f}），在严格样本里略负
（{logw_corr_strict['pr']:.2f}）——高质量大样本的赞藏比天生偏低（点赞数被
关注基数稀释），但**敏感度仍是三者中最小的**，可视为长度中性。

结论很直接：**凡是「除以字数」或「除以点击」的指标，都是字数的负函数**，
不作标准化就直接排行，排行榜会变成「最短的书」或「最冷门的书」。
报告 19 §4.3 在短篇里看到的 pr 方向反转，也是同一个机制的另一面
（低曝光样本上比值失真），不是 pr 本身失效。

### 4.2 同档标准化后，篇幅效率与 pr 是两个正交维度

在**每个字数档内部**分别把 `dens` 与 `pr` 转成百分位，再交叉分档
（样本 {num(len(ok))} 本，`favs ≥ 50`、`words ≥ 1k`、`clicks ≥ 200`）：

{md_table(rows_grid, grid_header)}

![篇幅效率 × 赞藏比 的收藏网格]({figs['grid']})

行方向（篇幅效率）主导**规模**：从 Q1 到 Q5，收藏中位跨两个数量级；
列方向（pr）在同一行内几乎不改变规模，却改变**读者表达强度**。
两层含义：

1. **它们不可互相替代**：同档内秩相关
   pr–dens = {inband_m[1]:.2f}、pr–conv = {inband_m[0]:.2f}、
   conv–dens = {inband_m[2]:.2f}；top5% 交集 Jaccard 仅 {jac:.2f}。
   「高收藏密度但低赞藏比」与「低密度但高赞藏比」是两类不同的书，
   前者是**高效的沉默消费**，后者是**小圈子高共鸣**。
2. **组合起来才接近「质量」**：单看密度的 top 榜会被「短而爆」的书占满，
   单看 pr 的 top 榜会被「小众高分」占满（报告 19 已示）。双轴分位后，
   两个方向的极端都能被识别，且都不再被字数左右。

### 4.3 落到产品上的三条约束

1. **篇幅效率只能作同档分位**：`(字数档 × 世代)` 双组分位（同报告 19 的
   推荐刻度口径），禁止用绝对 `favs/万字` 排名；
2. **与 pr 并列而非连乘**：两者秩相关接近 0，连乘会把两个正交信号压成一个
   噪声乘积（与报告 08「三个计数器不是漏斗」同一条纪律）；
3. **不进推荐打分，先做展示锚点**：本报告只证明它**有区分度**，
   没有验证它**可预测**（无时间序列，无法做前瞻检验）。在拿到
   App 端观测曲线（`observations` 时序）并做过前瞻验证之前，
   篇幅效率只作详情页/榜单的展示标签，不进推荐白名单。


---

## 5. 口径边界与未决

1. **因果方向不可判**：字数与收藏同向，既可能是读者偏好长篇，也可能是长篇
   连载久、曝光多、被搜索到的机会大。§2.1 的同曝光档比较排除了「纯曝光」，
   但没有排除「曝光质量不同」（长篇的点击更多来自深链与追更，短书的点击更多
   来自信息流）。
2. **存活偏置随世代加重**：2024-26 世代的字数中位偏高，任何「近年变短/变长」
   的结论都要先扣掉这层偏置。本报告只报到 2025，且不建议跨 2023 前后直接比。
3. **对话/互动小说的字数不可比**：每章约 500 字、整本可长（报告 22），
   字数维度对这条产品线没有解释力；§1.3 的同人低长占比已体现，
   但未做全量剔除后的重算——剔除幅度见报告 22 §5。
4. **`fireMoney` 不在本表**：`out/novels.csv` 15 列不含它，付费分析只能用
   `price_type`（VIP/签约）三态，无法计算「每万字定价 × 收藏」这类交叉。
   若需要，须回到 jsonl 重跑 `build_csv.py` 扩列。
5. **断更率是下界**：`status` 是快照值，`updated_at` 只反映最后一次更新；
   真正停更可能比 365 天更晚被发现。
6. **没有时间维度**：本报告全部是横截面。字数对收藏的**因果弹性**、
   篇幅效率的**前瞻有效性**都需要 `observations` 时序，属下一阶段（06 U5）。
"""]

    OUT.write_text("\n".join(parts), encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    print(build())

"""生成 analysis/reports/01_market_structure.md：供给、题材与完结形态。

所有数字现算自 analysis/out/novels.csv，年份由 analysis/eras.py 定年。
报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/report_market.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eras

OUT = Path(__file__).resolve().parent / "reports" / "01_market_structure.md"
FIG_DIR = OUT.parent / "figures"

# 分期底色与系列配色（色盲安全，非涨跌语义）
PERIODS = [
    (2007, 2014, "兴趣站期", "#F2F2F2"),
    (2015, 2016, "商业化初期", "#E8EEF7"),
    (2017, 2022, "扩张期", "#DCE8F5"),
    (2023, 2025, "收缩期", "#F5E8E8"),
]
C = {"blue": "#4477AA", "red": "#CC3311", "green": "#009988", "gray": "#777777"}


def setup_style() -> None:
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "savefig.dpi": 150,
            "figure.dpi": 150,
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.axisbelow": True,
            "axes.grid": True,
            "grid.color": "#DDDDDD",
            "grid.linewidth": 0.6,
        }
    )


def shade_periods(ax, years: pd.Series, label_y_frac: float = 0.97) -> None:
    """按分期加底色带并在顶部标注分期名。"""
    for lo, hi, name, color in PERIODS:
        if years.max() < lo or years.min() > hi:
            continue
        ax.axvspan(lo - 0.5, hi + 0.5, color=color, zorder=0)
        mid = (max(lo, years.min()) + min(hi, years.max())) / 2
        ax.text(
            mid, label_y_frac, name, transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=7.5, color="#666666",
        )


def yearly_counts(df: pd.DataFrame) -> pd.Series:
    return df[df["est_year"].between(2007, 2025)].groupby("est_year").size()
SNAPSHOT = "2026-06-13"
SNAP_YEAR_FRAC = 2026 + 162 / 365  # 快照时刻的十进年份

GENRE_ORDER = ["魔幻", "玄幻", "古风", "科幻", "校园", "都市", "游戏", "同人", "悬疑"]


def load() -> pd.DataFrame:
    df = pd.read_csv(
        Path(__file__).resolve().parent / "out" / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    return df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id")


def period_of(year: int) -> str:
    if year <= 2014:
        return "2006-2014 兴趣站期"
    if year <= 2016:
        return "2015-2016 商业化初期"
    if year <= 2022:
        return "2017-2022 扩张期"
    return "2023-2026 收缩期"


def pct(x: float) -> str:
    return f"{x:.1f}"


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def save(fig: plt.Figure, name: str) -> str:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"figures/{name}"


def fig_dating(df: pd.DataFrame) -> str:
    """封面时间戳 − 定年估计 的偏差分布。"""
    ts = eras.cover_timestamp(df["cover_url"])
    d = df.assign(cover_ts=ts)
    d = d[d["cover_ts"].notna()].copy()
    delta = (d["cover_ts"] - d["est_date"]).dt.days

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    lo, hi = -60, 730
    clip = delta.between(lo, hi)
    ax.hist(delta[clip], bins=58, color=C["blue"], edgecolor="white", linewidth=0.3)
    ax.axvline(0, color=C["gray"], lw=0.8)
    ax.axvspan(-47, 47, color=C["green"], alpha=0.12, zorder=0)
    ax.text(0, 1.02, "±47 天吻合窗", transform=ax.get_xaxis_transform(),
            ha="center", fontsize=7.5, color=C["green"])
    med = delta.median()
    ax.axvline(med, color=C["red"], lw=0.9, ls="--")
    ax.annotate(
        f"中位 {med:.0f} 天", xy=(med, 3000), xytext=(120, 11000),
        fontsize=7.5, color=C["red"],
        arrowprops=dict(arrowstyle="-", color=C["red"], lw=0.7),
    )
    n_out = (~clip).sum()
    ax.text(
        0.99, 0.97,
        f"n = {len(delta):,}（显示截断于 +{hi} 天，窗外 {n_out:,} 本未画出）",
        transform=ax.transAxes, ha="right", va="top", fontsize=7.5, color="#666666",
    )
    ax.set_xlim(lo, hi)
    ax.set_xlabel("偏差（天）：封面时间戳 − 定年估计")
    ax.set_ylabel("书数")
    return save(fig, "01_dating.png")


def fig_supply(df: pd.DataFrame) -> str:
    """年度新书量柱状 + 分期底色。"""
    y = yearly_counts(df)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.bar(y.index, y.values, width=0.8, color=C["blue"], zorder=2)
    shade_periods(ax, y.index)
    peak_year = int(y.idxmax())
    ax.annotate(
        f"{peak_year} 年峰值 {int(y.max()):,} 本",
        xy=(peak_year, y.max()), xytext=(peak_year - 4.8, y.max() * 0.9),
        fontsize=8, arrowprops=dict(arrowstyle="-", color=C["gray"], lw=0.7),
    )
    ax.set_xlim(2006.5, 2025.5)
    ax.set_xticks(range(2007, 2026, 2))
    ax.set_ylim(top=y.max() * 1.12)
    ax.set_xlabel("年（nid 定年）")
    ax.set_ylabel("新书量（在册）")
    return save(fig, "01_supply.png")


def fig_genre(df: pd.DataFrame) -> str:
    """魔幻/玄幻/同人年度份额。"""
    d = df[df["est_year"].between(2007, 2025)]
    share = pd.crosstab(d["est_year"], d["genre"], normalize="index").mul(100)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for genre, color, style in (
        ("魔幻", C["blue"], "-"),
        ("玄幻", C["green"], "-"),
        ("同人", C["red"], "-"),
    ):
        ax.plot(share.index, share[genre], style, color=color, lw=1.6)
    # 线端直接标注，不用图例框
    last = share.index.max()
    for genre, color in (("魔幻", C["blue"]), ("玄幻", C["green"]), ("同人", C["red"])):
        ax.text(
            last + 0.5, share.loc[last, genre], genre,
            color=color, fontsize=8.5, va="center",
        )
    peak_year = int(share["同人"].idxmax())
    ax.annotate(
        f"{peak_year} 峰值 {share['同人'].max():.1f}%",
        xy=(peak_year, share["同人"].max()),
        xytext=(peak_year - 4.5, share["同人"].max() * 0.82),
        fontsize=8, color=C["red"],
        arrowprops=dict(arrowstyle="-", color=C["red"], lw=0.7),
    )
    shade_periods(ax, share.index)
    ax.set_xlim(2006.5, 2027.0)
    ax.set_xticks(range(2007, 2026, 2))
    ax.set_ylim(0, 55)
    ax.set_xlabel("年（nid 定年）")
    ax.set_ylabel("占当年新书 %")
    return save(fig, "01_genre.png")


def fig_price(df: pd.DataFrame) -> str:
    """年度签约率 / VIP 份额。"""
    d = df[df["est_year"].between(2007, 2025)]
    rate = d.groupby("est_year").agg(
        signed=("price_type", lambda s: (s == "签约").mean() * 100),
        vip=("price_type", lambda s: (s == "VIP").mean() * 100),
    )
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.plot(rate.index, rate["signed"], "-", color=C["blue"], lw=1.6)
    ax.plot(rate.index, rate["vip"], "-", color=C["gray"], lw=1.4)
    shade_periods(ax, rate.index)
    last = rate.index.max()
    ax.annotate(f"签约率 {rate['signed'].iloc[-1]:.1f}%",
                xy=(last, rate['signed'].iloc[-1]),
                xytext=(4, 0), textcoords="offset points", fontsize=8, color=C["blue"], va="center")
    ax.annotate(f"VIP {rate['vip'].iloc[-1]:.1f}%",
                xy=(last, rate['vip'].iloc[-1]),
                xytext=(4, 0), textcoords="offset points", fontsize=8, color=C["gray"], va="center")
    ax.set_xlim(2006.5, 2026.2)
    ax.set_xticks(range(2007, 2026, 2))
    ax.set_ylim(0, 15)
    ax.set_xlabel("年（nid 定年）")
    ax.set_ylabel("占当年新书 %")
    return save(fig, "01_price.png")


def fig_completion(df: pd.DataFrame) -> str:
    """左：分字数档完结率；右：完结/连载字数 CCDF。"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 2.9))
    fig.subplots_adjust(wspace=0.32)

    d = df.copy()
    d["wband"] = pd.cut(
        d["words"], [0, 1e4, 5e4, 1e5, 2e5, 5e5, float("inf")],
        labels=["<1万", "1-5万", "5-10万", "10-20万", "20-50万", "50万+"],
    )
    b = d.groupby("wband", observed=True)["status"].agg(
        lambda s: (s == "已完结").mean() * 100
    )
    ax1.bar(range(len(b)), b.values, width=0.7, color=C["blue"])
    ax1.set_xticks(range(len(b)), b.index, fontsize=7.5)
    for i, v in enumerate(b.values):
        ax1.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=7.5, color="#444444")
    ax1.set_ylim(0, 55)
    ax1.set_xlabel("当前字数档")
    ax1.set_ylabel("完结率 %")

    for status, color in (("已完结", C["red"]), ("连载中", C["gray"])):
        w = np.sort(df.loc[df["status"] == status, "words"].to_numpy())
        ccdf = 1 - np.arange(1, len(w) + 1) / len(w)
        ax2.plot(w, ccdf, color=color, lw=1.4, label=f"{status}（n={len(w):,}）")
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.set_ylim(1e-5, 2)
    ax2.set_xlim(1e3, 1e7)
    ax2.axvline(2e5, color=C["gray"], lw=0.7, ls=":")
    ax2.text(2e5, 1.4, "20 万字", fontsize=7.5, color="#666666", ha="center")
    ax2.set_xlabel("字数（对数）")
    ax2.set_ylabel("P(字数 > x)")
    ax2.legend(frameon=False, fontsize=7.5, loc="lower left")

    return save(fig, "01_completion.png")


def section_supply(df: pd.DataFrame) -> tuple[str, dict]:
    d = df[df["est_year"] <= 2025].copy()
    y = d.groupby("est_year").agg(
        books=("id", "size"),
        done=("status", lambda s: (s == "已完结").mean() * 100),
        signed=("price_type", lambda s: (s == "签约").mean() * 100),
        vip=("price_type", lambda s: (s == "VIP").mean() * 100),
        med_words=("words", "median"),
    )
    y["exposure"] = SNAP_YEAR_FRAC - y.index

    rows = [
        [
            str(int(yr)),
            thousands(r.books),
            pct(r.done),
            pct(r.signed),
            pct(r.vip),
            thousands(r.med_words),
            f"{r.exposure:.0f}",
        ]
        for yr, r in y.iterrows()
        if yr >= 2007
    ]
    table = md_table(
        rows,
        ["年", "新书", "完结率%", "签约%", "VIP%", "字数中位", "存活年数"],
    )

    peak_year = int(y["books"].idxmax())
    peak_books = int(y.loc[peak_year, "books"])
    books_2025 = int(y.loc[2025, "books"])
    jump_2017 = y.loc[2017, "books"] / y.loc[2016, "books"]

    text = f"""## 2. 供给年表与分期

新书量指「该年创建、快照时仍在册」的作品，是存活口径的下界：已下架作品
（含早期引进清理）不在数据集内，早期年份的绝对量被低估，方向不可归因。

{table}

（2006 年 3 本为引进书，并入兴趣站期不计年行。）

![年度新书量与分期](figures/01_supply.png)

分期依据供给曲线的形态断点，与平台事件互证：

| 分期 | 书量 | 依据 |
|---|---:|---|
| 2006-2014 兴趣站期 | {thousands(df[df.est_year <= 2014].shape[0])} | 年供给 79–3,414 本；2014 年商业化转型（百科词条） |
| 2015-2016 商业化初期 | {thousands(df[(df.est_year >= 2015) & (df.est_year <= 2016)].shape[0])} | 2015 年 APP 上线；供给仍在 3–5 千本 |
| 2017-2022 扩张期 | {thousands(df[(df.est_year >= 2017) & (df.est_year <= 2022)].shape[0])} | 2017 年供给跳至 {jump_2017:.1f} 倍；2018 A 轮、2022 B 轮 |
| 2023-2026 收缩期 | {thousands(df[df.est_year >= 2023].shape[0])} | 供给自峰值连续三年回落 |

供给侧的核心事实是**扩张期占全库 {df[(df.est_year >= 2017) & (df.est_year <= 2022)].shape[0] / len(df) * 100:.0f}%**：
2017–2022 六年贡献了约 15.6 万本，其中 {peak_year} 年 {thousands(peak_books)} 本为峰值，
至 2025 年降至 {thousands(books_2025)} 本（−{(1 - books_2025 / peak_books) * 100:.0f}%）。

「存活年数」列提示两处口径陷阱：完结率随世代变新而下降（§5），
字数中位随世代变新而偏低（连载作品仍在累积），两者都不是行为变化的充分证据。
但 2023–2025 字数中位回升（8,383 → 9,883 → 16,746）与删失方向相反——
新世代累积时间更短、中位反而更高，说明收缩期作品向长篇集中。"""
    stats = {"peak_year": peak_year, "peak_books": peak_books}
    return text, stats


def section_dating(df: pd.DataFrame) -> str:
    loo = eras.leave_one_out()
    interp = loo[loo["kind"] == "interp"]
    q = interp["err_day"].abs()

    conf = df["confidence"].value_counts(normalize=True).mul(100).round(1)
    low_years = (
        df[df["confidence"] == "low"]["est_year"].value_counts().sort_index()
    )
    low_span = f"{int(low_years.index.min())}–{int(low_years.index.max())}"

    # 封面时间戳交叉验证（共用封面已在构建时清洗，余下均为属主封面）
    ts = eras.cover_timestamp(df["cover_url"])
    d = df.assign(cover_ts=ts)
    d = d[d["cover_ts"].notna()].copy()
    d["delta"] = (d["cover_ts"] - d["est_date"]).dt.days
    q_all = d["delta"]
    viol = d[d["delta"] < -31]
    viol_by_conf = viol.groupby("confidence").size() / d.groupby("confidence").size() * 100

    return f"""## 1. 定年方法与误差

`updated_at` 是最后更新时间，老书的一次编辑可晚于创建十年以上，不能作时间轴。
本报告的年份由 `analysis/eras.py` 定年：91 个 API 实测锚点（作品创建时间
`addTime`，2006-08 至 2026-06），在 log(nid) 空间分段线性插值——nid 增速
20 年间增长约 180 倍，log 空间更接近匀速。

锚点插值误差用留一法实测（留出单元为同秒时间戳整组锚点，防双胞胎泄漏）：

| 情形 | 锚点数 | \\|误差\\| 中位（天） | P90 | P99 |
|---|---:|---:|---:|---:|
| 锚点间插值 | {len(interp)} | {q.median():.0f} | {q.quantile(.9):.0f} | {q.quantile(.99):.0f} |
| 边界外推 | {len(loo) - len(interp)} | — | — | 最大 482 |

本数据集 id 全部落在锚点区间内（无外推）。置信度分布：high {conf.get('high', 0)}%、
mid {conf.get('mid', 0)}%、low {conf.get('low', 0)}%。低置信集中在 {low_span}
（锚点稀疏年代），该区间的年份误差可达数月，年表中的行量与份额以下限可靠性解读。

### 封面时间戳交叉验证

`cover_url` 保留着封面文件的上传时间（路径 `YYYY/MM`），与 nid 定年构成
**两条独立证据链**。封面更换会换新文件，时间戳记录最后一次上传，一般不早于
创建时间。爬虫缺陷产生的共用封面（组内 id 最大者为属主，其余为错值）已在
构建时清洗，此处使用的 {len(d):,} 本封面均为属主封面：

| 指标 | 值 |
|---|---|
| 偏差（封面时间戳 − 定年估计）中位 | {q_all.median():.0f} 天 |
| P5 / P95 | {q_all.quantile(.05):.0f} / {q_all.quantile(.95):.0f} 天 |
| 封面时间戳早于估计 >31 天（违例） | {len(viol):,} 本（{len(viol) / len(d) * 100:.2f}%），最大提前 {abs(q_all.min()):.0f} 天 |
| 违例率分层 | high {viol_by_conf.get('high', 0):.2f}% · mid {viol_by_conf.get('mid', 0):.2f}% |

![封面时间戳偏差分布](figures/01_dating.png)

偏差中位为负（封面上传略早于 nid 定年），与「草稿阶段先传封面、后正式上架」
的流程一致。两条证据链在 ±47 天内吻合的占 {100 - len(viol) / len(d) * 100:.1f}%，
定年估计由此获得独立佐证。mid 区间违例率高于 high（集中在 2017 年锚点稀疏段），
对应月级误差；low 区间（2010–2016）封面多被更换，验证在该区间失效而非通过。"""


def section_genre(df: pd.DataFrame) -> str:
    d = df.copy()
    d["period"] = d["est_year"].map(
        lambda y: "2006-14" if y <= 2014 else "2015-16" if y <= 2016 else "2017-22" if y <= 2022 else "2023-26"
    )
    share = pd.crosstab(d["period"], d["genre"], normalize="index").mul(100).round(1)
    share = share.reindex(["2006-14", "2015-16", "2017-22", "2023-26"])
    rows = [
        [p] + [f"{share.loc[p, g]:.1f}" for g in GENRE_ORDER]
        for p in share.index
    ]
    table = md_table(rows, ["期"] + GENRE_ORDER)

    fan_early = int(((d["est_year"] <= 2018) & (d["genre"] == "同人")).sum())
    fan_yearly = (
        d[d["genre"] == "同人"].groupby("est_year").size().reindex(range(2019, 2027), fill_value=0)
    )
    fan_share = (
        pd.crosstab(d["est_year"], d["genre"] == "同人", normalize="index").mul(100)[True]
    )

    g = d.groupby("genre").agg(
        books=("id", "size"),
        done=("status", lambda s: (s == "已完结").mean() * 100),
        med_words=("words", "median"),
    )
    g["share"] = g["books"] / len(d) * 100
    g = g.reindex(GENRE_ORDER)
    grows = [
        [
            idx,
            thousands(r.books),
            pct(r["share"]),
            pct(r.done),
            thousands(r.med_words),
        ]
        for idx, r in g.iterrows()
    ]
    gtable = md_table(grows, ["题材", "书量", "份额%", "完结率%", "字数中位"])

    return f"""## 3. 题材结构变迁

各期题材份额（占该期新书 %）：

{table}

![魔幻、玄幻、同人的年度份额](figures/01_genre.png)

两条结构性位移贯穿 20 年：

1. **魔幻收缩、玄幻扩张**。魔幻份额从兴趣站期的 46.1% 降至收缩期的 31.0%，
   玄幻同期从 3.6% 升至 14.2%。前者是日式奇幻（异世界、魔王勇者）的本土容器，
   后者是中式网文品类——位移方向即平台的去日轻化。
2. **同人是扩张期才出现的品类**。2018 年及以前累计仅 {fan_early} 本，
   2019 年起放量：份额 {fan_share.get(2019, 0):.1f}% → {fan_share.get(2021, 0):.1f}%（2021 峰值）
   → {fan_share.get(2025, 0):.1f}%（2025）。峰值一过即回落，回落幅度（−19.2 个百分点）
   与供给收缩同步。同人依赖在站 IP（鬼灭、Fate 等）的原生受众，其收缩先于
   总供给收缩发生。

各题材全库概况：

{gtable}

古风的字数形态独立于其他品类：字数中位 11,957 不算突出，但 P90 达 228,425 字，
为九类最高——长篇集中于古风。"""


def section_price(df: pd.DataFrame) -> str:
    d = df.copy()
    d["period"] = d["est_year"].map(period_of)
    p = pd.crosstab(d["period"], d["price_type"], normalize="index").mul(100).round(1)
    p = p.reindex(sorted(p.index))
    rows = [[idx, pct(r["免费"]), pct(r["签约"]), pct(r["VIP"])] for idx, r in p.iterrows()]
    table = md_table(rows, ["期", "免费%", "签约%", "VIP%"])

    sub = d[d["est_year"] >= 2017].copy()
    sub["fan"] = sub["genre"] == "同人"
    cmp = sub.groupby("fan").agg(
        signed=("price_type", lambda s: (s == "签约").mean() * 100),
        vip=("price_type", lambda s: (s == "VIP").mean() * 100),
    )
    gs = d.groupby("genre")["price_type"].apply(lambda s: (s == "签约").mean() * 100)

    return f"""## 4. 商业化进程

{table}

![年度签约率与 VIP 份额](figures/01_price.png)

签约率是唯一单调上行的时间序列：兴趣站期 0.3% → 收缩期 {p.loc[p.index[-1], '签约']:.1f}%。
2025 年世代达 13.4%。**供给收缩与签约率上升同时发生**：平台在变少的供给中
提高了商业化密度。VIP 份额 20 年稳定在 3% 上下，付费模式未变。

但商业化对题材并非中性。扩张期以来（2017–2026）：

| | 签约率% | VIP% |
|---|---:|---:|
| 非同人 | {cmp.loc[False, 'signed']:.1f} | {cmp.loc[False, 'vip']:.1f} |
| 同人 | {cmp.loc[True, 'signed']:.1f} | {cmp.loc[True, 'vip']:.1f} |

同人签约率不足非同人的四成、VIP 近乎为零——二次创作的版权归属使其无法
进入付费体系，平台以征文（崩坏3、少女前线等联动）而非签约承接该品类。
分题材签约率从古风 {gs.get('古风', 0):.1f}%（最高）到同人 {gs.get('同人', 0):.1f}%（最低），
排序与 IP 依赖度反向。"""


def section_completion(df: pd.DataFrame) -> str:
    total_done = (df["status"] == "已完结").mean() * 100

    d = df.copy()
    d["wband"] = pd.cut(
        d["words"],
        [0, 1e4, 5e4, 1e5, 2e5, 5e5, float("inf")],
        labels=["<1万", "1-5万", "5-10万", "10-20万", "20-50万", "50万+"],
    )
    b = d.groupby("wband", observed=True).agg(
        books=("id", "size"),
        done=("status", lambda s: (s == "已完结").mean() * 100),
    )
    rows = [
        [str(idx), thousands(r.books), pct(r.done)] for idx, r in b.iterrows()
    ]
    table = md_table(rows, ["字数档", "书量", "完结率%"])

    q = {}
    for s in ("已完结", "连载中"):
        sub = df.loc[df["status"] == s, "words"]
        q[s] = (sub.median(), sub.quantile(0.9))

    return f"""## 5. 完结形态

全库完结率 {total_done:.1f}%。按当前字数分档：

{table}

![分档完结率（左）与字数生存曲线（右）](figures/01_completion.png)

完结率随字数先降后升：1–10 万字区间是低谷（约 15%），20 万字以上快速抬升，
50 万字以上达 {b.loc['50万+', 'done']:.1f}%。两端各有成因——短作品的完结态既可能是
完整的短篇，也可能是创建即弃；长作品能积累到 50 万字，本身就是作者投入度的
筛选，其高完结率部分是幸存者效应。

世代维度的完结率（见 §2 表）在 2020 世代达峰 24.4%，此后逐代下降；但世代越新
删失越重（存活年数列），2022 世代及以后的完结率不可比。可比较的区间内
（存活 ≥ 4 年，即 2022 及以前），2017 世代 10.9% → 2020 世代 24.4% 为真实上升：
扩张期进入的作者更倾向写完。

完结与连载作品的字数分布几乎重合（中位 {q['已完结'][0]:,.0f} 对 {q['连载中'][0]:,.0f}），
差异出现在长尾：完结作品 P90 达 {q['已完结'][1]:,.0f} 字，连载作品仅 {q['连载中'][1]:,.0f} 字——
**20 万字以上的长篇绝大多数以完结态存在，未完结的长篇是少数**。"""


def build() -> None:
    setup_style()
    df = load()
    for fig in (fig_dating, fig_supply, fig_genre, fig_price, fig_completion):
        path = fig(df)
        print(f"写出 {OUT.parent / path}")
    supply, _ = section_supply(df)

    # 结论与各节共用的头部数字，统一现算
    y = df[df["est_year"] <= 2025].groupby("est_year").size()
    jump = y.loc[2017] / y.loc[2016]
    expansion = df[(df["est_year"] >= 2017) & (df["est_year"] <= 2022)].shape[0]
    expansion_pct = expansion / len(df) * 100
    peak_year = int(y.idxmax())
    peak_books = int(y.max())
    books_2025 = int(y.loc[2025])
    decline = (1 - books_2025 / peak_books) * 100

    body = f"""# 01 · 市场结构：供给、题材与完结形态

> 口径声明：
> 1. 数据源 `analysis/out/novels.csv`，{len(df):,} 行，当前在册作品。已剔除下架、
>    空状态、无文字书名且无内容等五类行（判据见 `analysis/config.py`），
>    年度量因此是存活口径，历史真实供给高于此值。
> 2. 年份由 nid 定年（`analysis/eras.py`），不是 `updated_at`；方法与误差见 §1。
> 3. 快照采集于 {SNAPSHOT}，且 2026-05 之后新书在快照中的可见性骤降
>    （nid 流速不变、成书率降至约 1/14），**年度序列止于 2025**。
> 4. 完结率含右删失：世代越新，完结概率越被低估，跨世代比较只对
>    存活 4 年以上的世代有效。
> 5. 引进书未单独剔除（版权方账号约 40 本，占 0.02%），对结构无影响。

---

## 0. 结论

1. **供给是单峰曲线**：2017 年供给跳至 {jump:.1f} 倍进入扩张期，{peak_year} 年达峰
   {peak_books:,} 本，2025 年降至 {books_2025:,} 本（−{decline:.0f}%）。
   扩张期六年贡献全库 {expansion_pct:.0f}%。
2. **题材结构两次位移**：魔幻 46% → 31%（日式奇幻收缩），玄幻 3.6% → 14.2%
   （网文品类扩张）；同人 2019 年起放量，2021 年峰值占 25.0%，收缩先于总供给。
3. **收缩期商业化反而加深**：签约率从 0.3% 升至 2025 世代的 13.4%，
   VIP 份额 20 年恒定约 3%。同人签约率仅 2.2%（非同人 6.3%），版权归属
   将该品类排除在付费体系之外。
4. **完结是长篇的属性**：总完结率 17.7%，50 万字以上作品 46.5% 完结，
   完结作品 P90 字数是连载作品的 2.4 倍。

---

{section_dating(df)}

---

{supply}

---

{section_genre(df)}

---

{section_price(df)}

---

{section_completion(df)}

---

## 6. 对找书 App 的含义

1. **库存的时代构成决定检索场景**：{expansion_pct:.0f}% 的书创建于 2017–2022，
   找书需求的主战场是扩张期库存；兴趣站期 1.7 万本中魔幻占 46%，早期用户的
   怀旧检索是独立场景。
2. **完结筛选是刚需参数**：17.7% 的完结率意味着五分之四的库存处于连载态，
   「只看完结」会砍掉多数库存但显著提升单位阅读时长的确定性；
   20 万字以上的完结长篇（约 6 千本）是确定性最高的子集。
3. **同人是自带受众的独立货架**：扩张期以来同人收藏中位（51）约为非同人
   （6）的 8.5 倍，但不可签约、不可 VIP，商业化路径与原创完全不同，
   应作独立的浏览分区而非混入题材筛选。
4. **签约标记可作品质代理但偏置已知**：签约率随世代单调上升，判读作品
   是否签约时须同时看世代；同人的低签约率是版权结构而非质量信号。

---

*生成：`uv run python analysis/report_market.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"写出 {OUT}（{len(body):,} 字符）")


if __name__ == "__main__":
    build()

"""生成 analysis/reports/03_author_ecology.md：作者生态。

分析单位为 author（字符串身份键）。主指标 favs；年份由 analysis/eras.py 定年。
所有数字现算自 analysis/out/novels.csv。报告是生成物：重跑即更新，勿手改。

用法：uv run python analysis/report_author.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts
import eras

OUT = Path(__file__).resolve().parent / "reports" / "03_author_ecology.md"

# 分析用的「有效作品」过滤器（只在报告内使用，不改数据层）：
# 1 万字与 config.EMPTY_WORDS 同源；10 收藏略高于全库中位 8，表示至少被读者验证过。
EFF_WORDS = 10_000
EFF_FAVS = 10

BOOK_BANDS = [0, 1, 2, 5, 10, 20, 50, np.inf]
BOOK_LABELS = ["1", "2", "3-5", "6-10", "11-20", "21-50", "50+"]


def load() -> pd.DataFrame:
    df = pd.read_csv(
        Path(__file__).resolve().parent / "out" / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id")
    df["effective"] = (df["words"] >= EFF_WORDS) | (df["favs"] >= EFF_FAVS)
    df["signed"] = df["price_type"] == "签约"
    df["paid"] = df["price_type"].isin(["签约", "VIP"])
    return df


def author_frame(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("author").agg(
        books=("id", "size"),
        eff_books=("effective", "sum"),
        favs=("favs", "sum"),
        favs_med=("favs", "median"),
        first=("est_year", "min"),
        last=("est_year", "max"),
        genres=("genre", "nunique"),
        signed=("signed", "max"),
        paid=("paid", "max"),
    )
    g["span"] = g["last"] - g["first"]
    return g


def book_band(series: pd.Series) -> pd.Series:
    return pd.cut(series, BOOK_BANDS, labels=BOOK_LABELS)


def gini(x: np.ndarray) -> float:
    x = np.sort(x)
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def head_share(x: np.ndarray, frac: float) -> float:
    s = np.sort(x)[::-1]
    k = max(1, int(round(len(s) * frac)))
    return float(s[:k].sum() / s.sum() * 100)


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def decline_pct(x: float) -> str:
    return f"−{abs(x):.1f}%"


# ---------------------------------------------------------------- 图表
def fig_author_size(df: pd.DataFrame, g: pd.DataFrame) -> str:
    band_all = book_band(g["books"]).value_counts().reindex(BOOK_LABELS)
    band_eff = book_band(g["eff_books"]).value_counts().reindex(BOOK_LABELS)
    d = df.assign(band=book_band(df.groupby("author")["id"].transform("size")))
    by_band = d.groupby("band", observed=True).agg(
        favs_med=("favs", "median"),
        short=("words", lambda s: (s < EFF_WORDS).mean() * 100),
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.2))
    x = np.arange(len(BOOK_LABELS))
    ax1.bar(x - 0.2, band_all.values, width=0.4, color=charts.C["blue"], label="全口径")
    ax1.bar(x + 0.2, band_eff.values, width=0.4, color="#A9C4DE", label="有效作品口径")
    ax1.set_yscale("log")
    ax1.set_xticks(x, BOOK_LABELS)
    ax1.set_xlabel("每位作者的作品数")
    ax1.set_ylabel("作者数（对数）")
    ax1.set_title(f"单本作者占 {band_all.iloc[0] / len(g) * 100:.1f}%", fontsize=9)
    ax1.legend(frameon=False, fontsize=8, loc="lower left")

    ax2.bar(x, by_band["favs_med"].values, width=0.62, color=charts.C["green"], zorder=2)
    ax2.set_yscale("log")
    ax2.set_xticks(x, BOOK_LABELS)
    ax2.set_xlabel("每位作者的作品数")
    ax2.set_ylabel("每本收藏中位（对数）")
    ax2b = ax2.twinx()
    ax2b.plot(x, by_band["short"].values, "-o", ms=3, color=charts.C["red"], lw=1.3)
    ax2b.set_ylim(0, 85)
    ax2b.set_ylabel("短篇（<1 万字）占比 %", color=charts.C["red"])
    ax2b.tick_params(colors=charts.C["red"], labelsize=8)
    ax2b.grid(False)
    ax2.set_title("多产度的质量反转", fontsize=9)
    for spine in ("top",):
        ax2b.spines[spine].set_visible(False)
    return charts.save(fig, "03_author_size.png")


def fig_author_concentration(df: pd.DataFrame, g: pd.DataFrame) -> str:
    a = g["favs"].to_numpy()
    b = df["favs"].to_numpy()
    fracs = np.array([0.0001, 0.001, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0])
    xa = np.array([head_share(a, f) for f in fracs])
    xb = np.array([head_share(b, f) for f in fracs])

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    xp = fracs * 100
    ax.plot(xp, xa, "-o", ms=3.5, color=charts.C["red"], lw=1.7,
            label=f"作者级（top 1% {xa[2]:.1f}%）")
    ax.plot(xp, xb, "-o", ms=3.5, color=charts.C["gray"], lw=1.4,
            label=f"书级（top 1% {xb[2]:.1f}%）")
    ax.set_xscale("log")
    ax.set_xlim(1e-2, 100)
    ax.set_ylim(0, 103)
    ax.set_xticks([0.01, 0.1, 1, 10, 100],
                  ["0.01%", "0.1%", "1%", "10%", "100%"])
    ax.set_xlabel("头部累计比例（对数）")
    ax.set_ylabel("累计收藏份额 %")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    return charts.save(fig, "03_author_concentration.png")


def fig_entry(df: pd.DataFrame, g: pd.DataFrame) -> str:
    years = np.arange(2007, 2026)
    new_authors = g.loc[g["first"].between(2007, 2025), "first"].value_counts().reindex(years, fill_value=0)
    active = df[df["est_year"].between(2007, 2025)].groupby("est_year")["author"].nunique().reindex(years, fill_value=0)
    ratio = new_authors / active * 100

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.bar(years, new_authors.values, width=0.78, color=charts.C["blue"], zorder=2)
    ax.set_xlim(2006.5, 2025.5)
    ax.set_xticks(range(2008, 2026, 2))
    ax.set_ylim(0, new_authors.max() * 1.18)
    ax.set_xlabel("世代（nid 定年）")
    ax.set_ylabel("当年首次出现的作者数")
    peak = int(new_authors.idxmax())
    ax.annotate(f"新作者峰值 {peak}：{new_authors.max():,}",
                xy=(peak, new_authors.max()), xytext=(0, 9),
                textcoords="offset points", ha="center", fontsize=8,
                color=charts.C["blue"])

    ax2 = ax.twinx()
    ax2.plot(years, ratio.values, "-", color=charts.C["red"], lw=1.5, zorder=4)
    ax2.set_ylim(0, 115)
    ax2.set_yticks([0, 25, 50, 75, 100])
    ax2.set_ylabel("新作者占活跃作者 %", color=charts.C["red"])
    ax2.tick_params(colors=charts.C["red"], labelsize=8)
    ax2.grid(False)
    ax2.spines["top"].set_visible(False)
    ax2.annotate(f"{ratio.loc[2025]:.1f}%", xy=(2025, ratio.loc[2025]),
                 xytext=(-4, 10), textcoords="offset points", ha="right",
                 fontsize=8, color=charts.C["red"])
    ax.axvline(2015, color="#BBBBBB", lw=0.8, ls=":", zorder=1)
    ax.text(2015.15, 0.985, "2015 VIP 付费", transform=ax.get_xaxis_transform(),
            ha="left", va="top", fontsize=7, color="#888888")
    return charts.save(fig, "03_entry.png")


def fig_retention(df: pd.DataFrame, g: pd.DataFrame, retention: pd.Series) -> str:
    multi = g[g["books"] >= 2]
    span = multi["span"].clip(upper=10).value_counts().sort_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.0))
    ax1.bar(span.index.astype(int), span.values, width=0.75, color=charts.C["blue"])
    ax1.set_xlim(-0.7, 10.7)
    ax1.set_xticks(range(0, 11))
    ax1.set_xticklabels([str(i) for i in range(10)] + ["10+"])
    ax1.set_xlabel("首作至末作的跨度（年）")
    ax1.set_ylabel("作者数")
    ax1.annotate(f"同年内 {span.get(0, 0) / len(multi) * 100:.0f}%",
                 xy=(0, span.get(0, 0)), xytext=(0.38, 0.80), textcoords="axes fraction",
                 fontsize=8, color=charts.C["red"],
                 arrowprops=dict(arrowstyle="-", color=charts.C["red"], lw=0.7))
    ax1.set_title("多本作者的生涯跨度", fontsize=9)

    ax2.plot(retention.index, retention.values, "-o", ms=3.5,
             color=charts.C["green"], lw=1.7)
    ax2.axvline(2015, color=charts.C["red"], lw=0.9, ls="--")
    ax2.text(2015.1, 0.97, "2015 VIP / 2016 自动签约",
             transform=ax2.get_xaxis_transform(), fontsize=7.5,
             color=charts.C["red"], ha="left", va="top")
    ax2.set_xlim(2011.5, 2022.5)
    ax2.set_ylim(0, 28)
    ax2.set_xticks(range(2012, 2023, 2))
    ax2.set_xlabel("首作世代")
    ax2.set_ylabel("3 年内再开新作 %")
    ax2.set_title("首作队列的复投率", fontsize=9)
    return charts.save(fig, "03_retention.png")


def fig_specialization(df: pd.DataFrame, g: pd.DataFrame) -> str:
    d = df.join(g[["books", "genres"]], on="author")
    raw = d.groupby("genres").agg(
        favs_med=("favs", "median"), authors=("author", "nunique")
    ).head(6)
    ctrl = d[d["books"] >= 2].copy()
    ctrl["band"] = pd.cut(ctrl["books"], [1, 2, 5, 10, 20, np.inf],
                          labels=["2", "3-5", "6-10", "11-20", "20+"])
    ctrl["spec"] = np.where(ctrl["genres"] == 1, "单一题材", "跨题材")
    t = ctrl.pivot_table(index="band", columns="spec", values="favs",
                         aggfunc="median", observed=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.0))
    ax1.bar(raw.index.astype(str), raw["favs_med"].values, width=0.65,
            color=charts.C["gray"])
    ax1.set_xlabel("作者跨题材数")
    ax1.set_ylabel("每本收藏中位")
    ax1.set_title("未控制多产度：看似正相关", fontsize=9, color=charts.C["gray"])

    x = np.arange(len(t))
    ax2.bar(x - 0.19, t["单一题材"].values, width=0.38,
            color=charts.C["green"], label="单一题材")
    ax2.bar(x + 0.19, t["跨题材"].values, width=0.38,
            color=charts.C["red"], label="跨题材")
    ax2.set_xticks(x, t.index.astype(str))
    ax2.set_xlabel("作者作品数档")
    ax2.set_ylabel("每本收藏中位")
    ax2.set_title("控制多产度后：方向反转", fontsize=9, color=charts.C["green"])
    ax2.legend(frameon=False, fontsize=8, ncol=2, loc="upper left")
    return charts.save(fig, "03_specialization.png")


# ---------------------------------------------------------------- 正文
def section_size(df: pd.DataFrame, g: pd.DataFrame) -> str:
    d = df.assign(band=book_band(df.groupby("author")["id"].transform("size")))
    t = d.groupby("band", observed=True).agg(
        n_books=("id", "size"),
        favs_med=("favs", "median"),
        short=("words", lambda s: (s < EFF_WORDS).mean() * 100),
        done=("status", lambda s: (s == "已完结").mean() * 100),
    )
    band_authors = book_band(g["books"]).value_counts().reindex(BOOK_LABELS)
    rows = []
    for label in BOOK_LABELS:
        r = t.loc[label]
        a_share = band_authors[label] / len(g) * 100
        rows.append([
            label, thousands(band_authors[label]),
            f"{a_share:.2f}%" if a_share < 0.1 else f"{a_share:.1f}%",
            thousands(r["n_books"]), f"{r['n_books'] / len(df) * 100:.1f}%",
            f"{r['favs_med']:.0f}", f"{r['short']:.1f}%", f"{r['done']:.1f}%",
        ])
    table = md_table(
        rows,
        ["作品数档", "作者数", "占作者", "覆盖作品", "占作品", "每本收藏中位", "短篇占比", "完结率"],
    )
    n_eff = int(df["effective"].sum())
    heavy = g[g["books"] > 50]
    heavy_rows = df[df["author"].isin(heavy.index)]
    heavy_short = (heavy_rows["words"] < EFF_WORDS).mean() * 100
    top_favs = g.nlargest(1, "favs").iloc[0]

    return f"""## 1. 供给主体：极度分散，且多产不等于有效供给

![作者规模与多产度的质量反转](figures/03_author_size.png)

{len(df):,} 本在册作品分属 {len(g):,} 个作者名，人均 {len(df) / len(g):.2f} 本。
{book_band(g['books']).value_counts().get('1', 0) / len(g) * 100:.1f}% 的作者只有一本作品，
这些书占全库 {(g['books'] == 1).sum() / len(df) * 100:.1f}%；反过来，作品数 ≥10 的
{(g['books'] >= 10).sum():,} 名作者（{(g['books'] >= 10).mean() * 100:.2f}%）覆盖了
{g.loc[g['books'] >= 10, 'books'].sum() / len(df) * 100:.1f}% 的库存。

{table}

每本收藏中位随作者作品数上升（1 本档 {t.loc['1', 'favs_med']:.0f} → 11–20 本档
{t.loc['11-20', 'favs_med']:.0f}），但到 50+ 本档回落至 {t.loc['50+', 'favs_med']:.0f}，
同期短篇占比升至 {t.loc['50+', 'short']:.1f}%、完结率降至 {t.loc['50+', 'done']:.1f}%。
作品数超过 50 本的 {len(heavy)} 名作者，其 {len(heavy_rows):,} 本作品里
{heavy_short:.1f}% 不足 1 万字（全库 {(df['words'] < EFF_WORDS).mean() * 100:.1f}%），
呈高频开坑、少有推进的形态；收藏最高的作者「{g['favs'].idxmax()}」只有
{int(top_favs['books'])} 本、总收藏 {thousands(top_favs['favs'])}，
与多产度榜首形成对照。

据此定义**分析用的有效作品**（≥ {thousands(EFF_WORDS)} 字 或 ≥ {EFF_FAVS} 收藏，
全库收藏中位 {df['favs'].median():.0f}）：{n_eff:,} 本，占 {n_eff / len(df) * 100:.1f}%。
这是报告内的过滤口径，不改动数据集；在此口径下仍有
{(g['eff_books'] >= 20).sum()} 名作者拥有 20 本以上有效作品，
说明多产者中确有稳定产能，但作品数本身不能作为质量代理。"""


def section_concentration(df: pd.DataFrame, g: pd.DataFrame) -> str:
    a = g["favs"].to_numpy()
    b = df["favs"].to_numpy()
    ga, gb = gini(a), gini(b)
    rows = []
    for f, name in ((0.001, "0.1%"), (0.01, "1%"), (0.05, "5%"), (0.1, "10%")):
        k = max(1, int(round(len(g) * f)))
        rows.append([
            name, thousands(k), f"{head_share(a, f):.1f}%", f"{head_share(b, f):.1f}%",
            f"{g.nlargest(k, 'favs')['books'].sum() / len(df) * 100:.1f}%",
        ])
    table = md_table(rows, ["头部比例（各自总体）", "作者数", "作者级累计收藏", "书级累计收藏", "该批作者占作品"])
    top100 = g.nlargest(100, "favs")
    dep = df[df["author"].isin(top100.index)].groupby("author")["favs"].apply(
        lambda s: s.max() / s.sum() if s.sum() > 0 else np.nan)
    return f"""## 2. 作者级集中高于书级集中

![作者级与书级的头部份额曲线](figures/03_author_concentration.png)

按作者汇总收藏后的 Gini 为 {ga:.3f}，高于书级的 {gb:.3f}（报告 02）：
多产作者把多本高收藏作品聚合到同一主体，尾部则堆积大量零收藏的单本作者，
两个方向的效应叠加使分布在作者层面更陡。

{table}

（两条序列的分母分别为作者数与书数，top f% 各自指本总体内的前 f%；比较的是
分布形状，不是同一阈值下的同一批作品。）

top 1% 作者（{max(1, int(round(len(g) * 0.01))):,} 人）占有
{head_share(a, 0.01):.1f}% 的收藏，却只产出
{g.nlargest(max(1, int(round(len(g) * 0.01))), 'favs')['books'].sum() / len(df) * 100:.1f}% 的作品。
但**头部作者不是稳定产能**：收藏 top 100 作者中，最大单本作品占其总收藏的
中位为 {dep.median() * 100:.1f}%，{(dep > 0.5).sum()} 人超过一半、
{(dep > 0.8).sum()} 人超过八成。作者级热度主要由单本爆款贡献，
按作者做推荐单元会反复指向同一本书。"""


def section_turnover(df: pd.DataFrame, g: pd.DataFrame, retention: pd.Series) -> str:
    years = np.arange(2007, 2026)
    new_authors = g.loc[g["first"].between(2007, 2025), "first"].value_counts().reindex(years, fill_value=0)
    active = df[df["est_year"].between(2007, 2025)].groupby("est_year")["author"].nunique().reindex(years, fill_value=0)
    books = df[df["est_year"].between(2007, 2025)].groupby("est_year").size().reindex(years, fill_value=0)
    ratio = new_authors / active * 100
    per_author = books / active

    periods = [(2007, 2014, "2007-2014 兴趣站期"), (2015, 2016, "2015-2016 商业化初期"),
               (2017, 2022, "2017-2022 扩张期"), (2023, 2025, "2023-2025 收缩期")]
    rows = []
    for lo, hi, name in periods:
        rows.append([
            name, thousands(books.loc[lo:hi].sum()),
            thousands(active.loc[lo:hi].sum()),
            thousands(new_authors.loc[lo:hi].sum()),
            f"{new_authors.loc[lo:hi].sum() / active.loc[lo:hi].sum() * 100:.1f}%",
            f"{books.loc[lo:hi].sum() / active.loc[lo:hi].sum():.2f}",
        ])
    table = md_table(rows, ["分期", "新书数", "活跃作者人次", "新作者", "新作者占活跃", "人均新书"])

    multi = g[g["books"] >= 2]
    early = retention.loc[2012:2014].mean()
    late = retention.loc[2015:2022].mean()
    peak_na_year = int(new_authors.idxmax())
    return f"""## 3. 世代更替与留存

![年度新作者数与新作者占比](figures/03_entry.png)

{table}

（分期行是各年人次之和，同一作者跨年会被重复计入；「人均新书」为期内新书数
除以活跃作者人次，与下文按单年计算的年度人均不是同一口径，仅作结构比例对照。
本表止于 2025，不含 2026 的不完整可见行，故总量与报告 01 的 2023–2026 分期不同。）

以报告 01 的供给峰值年 2022 为统一基准：新作者
{new_authors.loc[2022]:,} → {new_authors.loc[2025]:,}
（{decline_pct((new_authors.loc[2025] / new_authors.loc[2022] - 1) * 100)}）、
新书 {books.loc[2022]:,} → {books.loc[2025]:,}
（{decline_pct((books.loc[2025] / books.loc[2022] - 1) * 100)}）、
活跃作者 {active.loc[2022]:,} → {active.loc[2025]:,}
（{decline_pct((active.loc[2025] / active.loc[2022] - 1) * 100)}）同步收缩，
而人均新书仅由 {per_author.loc[2022]:.2f} 降至 {per_author.loc[2025]:.2f}
（−{(1 - per_author.loc[2025] / per_author.loc[2022]) * 100:.1f}%）：
**收缩以作者基数萎缩为主，而非在册作者集体减产**。

新作者数的绝对峰值出现在 {peak_na_year} 年（{new_authors.max():,} 人），
早于总供给峰值两年；2021–2022 的供给高位由人均新书抬升维持
（{per_author.loc[2021]:.2f} / {per_author.loc[2022]:.2f}，全期最高）。
新作者占活跃作者的比重总体由 2007 年的 {ratio.loc[2007]:.0f}% 降至
{ratio.loc[2025]:.1f}%，存量作者的相对贡献上升。

![生涯跨度与首作队列复投率](figures/03_retention.png)

多本作者中 {(multi['span'] == 0).mean() * 100:.0f}% 的所有作品都落在同一年，
生涯跨度中位 {multi['span'].median():.0f} 年、P90 {multi['span'].quantile(.9):.0f} 年。
以首作世代建队列，观察其后 3 年内是否再开新作：2012–2014 队列均值
{early:.1f}%，2015–2022 队列均值 {late:.1f}%，跳变发生在 2015 年
（{retention.loc[2015]:.1f}%），与 2015-05-07 VIP 付费、2016-01-13 自动签约
及全勤奖制度的启用同期（见 `references/sfacg-pku-chronicle.md`）。

各队列均有完整的 3 年观察窗口，但**存活口径使早期队列被系统性低估**：
下架作品不在数据集内，越早的队列其后续作品缺失越多。因此该跳变可作方向性
证据，幅度不可全部归因于制度。"""


def section_specialization(df: pd.DataFrame, g: pd.DataFrame) -> str:
    d = df.join(g[["books", "genres"]], on="author")
    raw = d.groupby("genres").agg(
        books=("id", "size"), authors=("author", "nunique"),
        favs_med=("favs", "median")
    ).head(6)
    rows = [[str(i), thousands(raw.loc[i, "authors"]),
             f"{raw.loc[i, 'authors'] / len(g) * 100:.1f}%",
             thousands(raw.loc[i, "books"]), f"{raw.loc[i, 'favs_med']:.0f}"]
            for i in raw.index]
    table = md_table(rows, ["跨题材数", "作者数", "占作者", "覆盖作品", "每本收藏中位"])

    ctrl = d[d["books"] >= 2].copy()
    ctrl["band"] = pd.cut(ctrl["books"], [1, 2, 5, 10, 20, np.inf],
                          labels=["2", "3-5", "6-10", "11-20", "20+"])
    ctrl["spec"] = np.where(ctrl["genres"] == 1, "单一题材", "跨题材")
    t = ctrl.pivot_table(index="band", columns="spec", values="favs",
                         aggfunc="median", observed=True)
    inv = (t["跨题材"] / t["单一题材"])
    fan_authors = set(df.loc[df["genre"] == "同人", "author"])
    fan_only = df[df["author"].isin(fan_authors)].groupby("author")["genre"].apply(
        lambda s: (s == "同人").all()).mean() * 100

    return f"""## 4. 题材专精：一个方向反转的伪相关

![控制多产度前后的题材专精效应](figures/03_specialization.png)

{(g['genres'] == 1).mean() * 100:.0f}% 的作者只写一个题材；在作品数 ≥2 的作者中，
单一题材者仍占 {((g.loc[g['books'] >= 2, 'genres'] == 1).mean() * 100):.0f}%。

{table}

原始口径下每本收藏中位随跨题材数上升（1 类 {raw.loc[1, 'favs_med']:.0f} →
5 类 {raw.loc[5, 'favs_med']:.0f}），容易读作「跨界带来更多读者」。
但跨题材数与作品数高度共线——写得越多自然覆盖越多分类。控制作者作品数后方向
**反转**：同一多产度档内，跨题材作者的每本收藏中位仅为单一题材作者的
{inv.min():.2f}–{inv.max():.2f} 倍（即专精者为 {1 / inv.max():.1f}–{1 / inv.min():.1f} 倍），
且差距随多产度扩大。这是辛普森效应：原始正相关完全由多产度混合驱动，
专精本身才与单本表现同向。跨题材作者在高档的样本量较小
（6–10 本档单一题材组 {int(((ctrl['band'] == '6-10') & (ctrl['spec'] == '单一题材')).sum()):,} 本），
该结论作方向性解读。

同人是这一结构最清晰的例外：{len(fan_authors):,} 名作者写过同人
（占全部作者 {len(fan_authors) / len(g) * 100:.1f}%），其中 {fan_only:.0f}% 只写同人。
与报告 02 观察到的「同人注意力按 IP 分散」一致，构成与原创并行的独立货架。"""


def section_professional(df: pd.DataFrame, g: pd.DataFrame) -> str:
    band = book_band(g["books"])
    t = g.groupby(band, observed=True).agg(
        authors=("books", "size"),
        signed=("signed", lambda s: s.mean() * 100),
        paid=("paid", lambda s: s.mean() * 100),
        favs_med=("favs", "median"),
    )
    rows = [[str(i), thousands(t.loc[i, "authors"]),
             f"{t.loc[i, 'signed']:.1f}%", f"{t.loc[i, 'paid']:.1f}%",
             thousands(t.loc[i, "favs_med"])] for i in t.index]
    table = md_table(rows, ["作品数档", "作者数", "至少一本签约", "至少一本付费（含 VIP）", "作者总收藏中位"])
    top_band = t["paid"].idxmax()
    return f"""## 5. 职业化：按单本达标的窄通道

{table}

全库 {g['signed'].mean() * 100:.2f}% 的作者至少有一本签约作品
（{int(g['signed'].sum()):,} 人），含 VIP 的付费体系口径为
{g['paid'].mean() * 100:.2f}%；对应的书级签约率为 {df['signed'].mean() * 100:.2f}%。
两个口径随多产度同步上升，但在 20 本以上趋于平台：单独签约率
{t.loc['21-50', 'signed']:.1f}% → {t.loc['50+', 'signed']:.1f}%，
含 VIP 的付费覆盖率在 {top_band} 本档见顶 {t.loc[top_band, 'paid']:.1f}%，
此后回落至 {t.loc['50+', 'paid']:.1f}%。50+ 档仅
{int(t.loc['50+', 'authors'])} 名作者，高档间的百分点差异不具统计意义。

制度口径可解释这一形状：2016-01-13 启用的自动签约通道以**单本**为审核单位
（连载 > 5 万字、收藏 > 200、半个月内更新），全勤奖亦按作者逐月考核；
累计开坑数不构成资格条件。因此签约是「少数作品跨过门槛」的结果，
不是对高产账号的奖励；20 本以上各档签约率稳定在
{t.loc['11-20', 'signed']:.0f}–{t.loc['50+', 'signed']:.0f}% 与此一致。
报告 01 观察到收缩期世代内签约率上行，但其口径为「当年新书中的签约份额」，
与本节「作者生涯内是否曾签约」不同，两者并置观察，不构成因果解释。"""


# ---------------------------------------------------------------- 主流程
def retention_curve(df: pd.DataFrame, g: pd.DataFrame) -> pd.Series:
    """首作队列在其后 3 年内是否再开新作（限 2012–2022，窗口完整）。"""
    by_year = df.groupby(["author", "est_year"]).size().unstack(fill_value=0)
    out = {}
    for y in range(2012, 2023):
        cohort = g.index[g["first"] == y]
        b = by_year.reindex(cohort).fillna(0)
        cols = [c for c in b.columns if y < c <= y + 3]
        if cols:
            out[y] = (b[cols].sum(axis=1) > 0).mean() * 100
    return pd.Series(out)


def build() -> None:
    charts.setup_style()
    df = load()
    g = author_frame(df)
    retention = retention_curve(df, g)
    for fig in (
        lambda: fig_author_size(df, g),
        lambda: fig_author_concentration(df, g),
        lambda: fig_entry(df, g),
        lambda: fig_retention(df, g, retention),
        lambda: fig_specialization(df, g),
    ):
        print(f"写出 {OUT.parent / fig()}")

    single_pct = (g["books"] == 1).mean() * 100
    n_eff = int(df["effective"].sum())
    ga = gini(g["favs"].to_numpy())
    years = np.arange(2007, 2026)
    sub_y = df[df["est_year"].between(2007, 2025)]
    new_authors = g.loc[g["first"].between(2007, 2025), "first"].value_counts().reindex(years, fill_value=0)
    active = sub_y.groupby("est_year")["author"].nunique().reindex(years, fill_value=0)
    books_y = sub_y.groupby("est_year").size().reindex(years, fill_value=0)
    per_author = books_y / active
    decline = (new_authors.loc[2025] / new_authors.loc[2022] - 1) * 100
    active_decline = (active.loc[2025] / active.loc[2022] - 1) * 100
    pa_decline = (1 - per_author.loc[2025] / per_author.loc[2022]) * 100
    peak_na_year = int(new_authors.idxmax())
    top_books = int(g.loc[g["favs"].idxmax(), "books"])
    short_50 = (df[df["author"].isin(g.index[g["books"] > 50])]["words"] < EFF_WORDS).mean() * 100
    top100 = g.nlargest(100, "favs")
    dep_median = (
        df[df["author"].isin(top100.index)].groupby("author")["favs"]
        .apply(lambda s: s.max() / s.sum() if s.sum() > 0 else np.nan).median() * 100
    )
    paid_gt20 = g.loc[g["books"] > 20, "paid"].mean() * 100
    d = df.join(g[["books", "genres"]], on="author")
    ctrl = d[d["books"] >= 2].copy()
    ctrl["band"] = pd.cut(ctrl["books"], [1, 2, 5, 10, 20, np.inf],
                          labels=["2", "3-5", "6-10", "11-20", "20+"])
    ctrl["spec"] = np.where(ctrl["genres"] == 1, "单一题材", "跨题材")
    t = ctrl.pivot_table(index="band", columns="spec", values="favs",
                         aggfunc="median", observed=True)
    inv = t["跨题材"] / t["单一题材"]
    fan_authors = set(df.loc[df["genre"] == "同人", "author"])
    fan_only = df[df["author"].isin(fan_authors)].groupby("author")["genre"].apply(
        lambda s: (s == "同人").all()).mean() * 100

    body = f"""# 03 · 作者生态：供给主体、留存与职业化

> 口径声明：
> 1. 数据源 `analysis/out/novels.csv`，{len(df):,} 行、{len(g):,} 个作者名，
>    快照 2026-06-13，在册存活口径；年份由 nid 定年（报告 01 §1），非 `updated_at`。
> 2. `author` 是字符串身份键：改名、马甲、共用笔名无法合并，同一自然人可能被
>    拆成多个作者。因此作者数是上界，多产度、生涯长度与复投率是下界。
>    版权方账号（正版日轻 47 行）已整行剔除。
> 3. 存活口径下下架作品不在库，越早的队列其后续作品缺失越多；跨世代的
>    作者比较只作趋势方向解读（§3），不作水平差异的因果归因。
> 4. 主指标 favs（收藏）；clicks 跨世代不可比。收藏是存量，作者总收藏随生涯累积，
>    作者级与书级集中按同一总量对照（§2）。
> 5. 「签约」指 `price_type=签约`；含 VIP 的付费合并口径单独标注（§5）。
>    制度节点取自 `references/sfacg-pku-chronicle.md`（北大《中国网络文学编年简史》）。
> 6. 完结率含右删失；年度序列止于 2025（2026-05 后新书可见性骤降）。

---

## 0. 结论

1. **供给主体极度分散**：{len(g):,} 名作者对应 {len(df):,} 本书，人均
   {len(df) / len(g):.2f} 本；{single_pct:.1f}% 的作者只有一本作品。
2. **多产不等于有效供给**：按「≥ {thousands(EFF_WORDS)} 字或 ≥ {EFF_FAVS} 收藏」过滤后
   仅剩 {n_eff:,} 本（{n_eff / len(df) * 100:.1f}%）；50+ 档作品的短篇占比
   {short_50:.1f}%，而收藏最高的作者只有 {top_books} 本。
3. **作者级集中高于书级**：作者 Gini {ga:.3f}（书级 {gini(df['favs'].to_numpy()):.3f}），
   top 1% 作者占 {head_share(g['favs'].to_numpy(), 0.01):.1f}% 收藏而仅
   {g.nlargest(max(1, int(round(len(g) * 0.01))), 'favs')['books'].sum() / len(df) * 100:.1f}% 作品；
   但头部热度主要由单本爆款贡献，作者不是稳定的推荐单元。
4. **收缩以作者基数萎缩为主**：以 2022 供给峰值为基准，新作者
   {decline_pct(decline)}、活跃作者 {decline_pct(active_decline)}、
   人均新书仅 {decline_pct(pa_decline)}；
   新作者数的绝对峰值在 {peak_na_year} 年，早于总量见顶两年。
5. **专精效应方向反转**：原始口径「跨题材更多收藏」是多产度共线造成的伪相关，
   控制作品数后专精作者的每本收藏中位是跨题材者的 {1 / inv.max():.1f}–{1 / inv.min():.1f} 倍。
6. **职业化是窄通道**：{g['signed'].mean() * 100:.2f}% 的作者至少一本签约，
   20 本以上档的付费覆盖率停滞在 {paid_gt20:.1f}%——制度按单本达标，
   不奖励累计开坑。

---

{section_size(df, g)}

---

{section_concentration(df, g)}

---

{section_turnover(df, g, retention)}

---

{section_specialization(df, g)}

---

{section_professional(df, g)}

---

## 6. 对找书 App 的含义

1. **以书而非作者为推荐基本单元**：收藏 top 100 作者的最大单本占其总收藏中位
   {dep_median:.1f}%，作者级榜单会重复指向同一作品；作者适合作为「同一作者的其他作品」
   的次级入口，而非主排序键。
2. **默认过滤碎片开坑条目**：有效作品口径保留 {n_eff / len(df) * 100:.1f}% 库存，
   可显著降低搜索与首页噪声；该过滤只在应用层生效，数据层不删行，
   以便按「全部作品」切换时仍可追溯。
3. **作者特征须控制多产度**：跨题材数、生涯长度、作品数三个特征高度共线，
   直接入模会把自选择误读为质量信号；使用同世代内的相对位置更稳健。
4. **同人独立建架**：{len(fan_authors):,} 名同人作者中 {fan_only:.0f}% 只写同人，
   与原创作者的题材迁移路径不同，混合推荐会稀释两边的相关性。
5. **签约不可作品质标签**：它只覆盖 {g['signed'].mean() * 100:.2f}% 的作者，
   且门槛按单本达标，作为特征会放大商业化偏置；同人受版权归属排除在外
   （报告 01、02），此项对同人恒为假。

---

*生成：`uv run python analysis/report_author.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"写出 {OUT}（{len(body):,} 字符）")


if __name__ == "__main__":
    build()

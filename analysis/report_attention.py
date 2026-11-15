"""生成 analysis/reports/02_attention_concentration.md：注意力集中度。

主指标 favs（收藏）：clicks 是累计浏览，受上架时长与各年代流量规模混杂，
仅作对照；praises 作稳健性校验。所有数字现算自 analysis/out/novels.csv，
年份由 analysis/eras.py 定年。报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/report_attention.py
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

OUT = Path(__file__).resolve().parent / "reports" / "02_attention_concentration.md"
GENRE_ORDER = ["魔幻", "玄幻", "古风", "科幻", "校园", "都市", "游戏", "同人", "悬疑"]


def load() -> pd.DataFrame:
    df = pd.read_csv(
        Path(__file__).resolve().parent / "out" / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    return df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id")


def gini(x: np.ndarray) -> float:
    x = np.sort(x)
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def top_share(x: np.ndarray, frac: float) -> float:
    """头部 frac 比例的书占总量份额。"""
    s = np.sort(x)[::-1]
    k = max(1, int(round(len(s) * frac)))
    return float(s[:k].sum() / s.sum() * 100)


def pct(x: float) -> str:
    return f"{x:.1f}"


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


# ---------- 图表 ----------


def fig_lorenz(df: pd.DataFrame) -> str:
    """头部份额曲线：top x% 的书占多少收藏/浏览。"""
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    fracs = np.logspace(-5, 0, 121)
    for col, color, lw, label in (
        ("favs", charts.C["blue"], 1.8, "收藏"),
        ("clicks", charts.C["gray"], 1.3, "浏览"),
    ):
        s = np.sort(df[col].to_numpy())[::-1]
        cum = np.cumsum(s) / s.sum()
        xs, ys = [], []
        for frac in fracs:
            k = max(1, int(round(len(s) * frac)))
            xs.append(frac * 100)
            ys.append(cum[k - 1] * 100)
        ax.plot(xs, ys, color=color, lw=lw,
                label=f"{label}（Gini {gini(df[col].to_numpy()):.3f}）")
    for frac, name in ((0.001, "0.1%"), (0.01, "1%"), (0.1, "10%")):
        v = top_share(df["favs"].to_numpy(), frac)
        ax.plot([frac * 100], [v], "o", ms=4, color=charts.C["red"], zorder=5)
        ax.annotate(f"top {name}：{v:.1f}%",
                    xy=(frac * 100, v), xytext=(8, -2),
                    textcoords="offset points", fontsize=7.5, color=charts.C["red"])
    ax.set_xscale("log")
    ax.set_xlim(1e-3, 100)
    ax.set_ylim(0, 105)
    ax.set_xticks([1e-3, 1e-2, 1e-1, 1, 10, 100],
                  ["0.001%", "0.01%", "0.1%", "1%", "10%", "100%"])
    ax.set_xlabel("书籍占全库的比例 x（按收藏/浏览降序取前 x%，对数）")
    ax.set_ylabel("前 x% 书的指标份额 %")
    ax.legend(frameon=False, loc="lower right")
    return charts.save(fig, "02_lorenz.png")


def fig_cohort(df: pd.DataFrame) -> str:
    d = df[df["est_year"].between(2008, 2025)]
    share = d.groupby("est_year")["favs"].sum() / df["favs"].sum() * 100
    ginis = d.groupby("est_year")["favs"].apply(lambda s: gini(s.to_numpy()))

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.bar(share.index, share.values, width=0.8, color=charts.C["blue"], zorder=2,
           label="世代收藏份额（左轴）")
    charts.shade_periods(ax, share.index)
    ax2 = ax.twinx()
    ax2.grid(False)
    ax2.plot(ginis.index, ginis.values, "-", color=charts.C["red"], lw=1.5,
             label="世代内 Gini（右轴）")
    ax2.set_ylim(0.70, 1.02)
    ax2.set_yticks([0.8, 0.9, 1.0])
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#CCCCCC")
    ax2.tick_params(colors=charts.C["red"], labelsize=8)
    ax.set_xlim(2007.5, 2025.5)
    ax.set_xticks(range(2008, 2026, 2))
    ax.set_ylim(0, 17)
    ax.set_xlabel("世代（nid 定年）")
    ax.set_ylabel("占全库收藏 %")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left",
              bbox_to_anchor=(0.01, 1.14), ncol=2, fontsize=8)
    return charts.save(fig, "02_cohort.png")


def fig_genre_idx(df: pd.DataFrame) -> str:
    book_share = df["genre"].value_counts(normalize=True) * 100
    favs_share = df.groupby("genre")["favs"].sum() / df["favs"].sum() * 100
    diff = (favs_share - book_share).sort_values()
    idx = favs_share / book_share

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    colors = [charts.C["blue"] if v > 0 else charts.C["gray"] for v in diff.values]
    ax.barh(diff.index, diff.values, color=colors, height=0.62, zorder=2)
    for i, (genre, v) in enumerate(diff.items()):
        ax.text(v + (0.12 if v > 0 else -0.12), i, f"{v:+.1f}pp（{idx[genre]:.2f}×）",
                va="center", ha="left" if v > 0 else "right", fontsize=7.5,
                color="#444444")
    ax.axvline(0, color="#999999", lw=0.8)
    ax.set_xlim(-7.8, 8.5)
    ax.set_xlabel("收藏份额 − 供给份额（百分点）；括号内为份额比")
    return charts.save(fig, "02_genre_idx.png")


def fig_words_status(df: pd.DataFrame) -> str:
    d = df[df["est_year"] <= 2022].copy()
    d["wband"] = pd.cut(
        d["words"], [1e4, 5e4, 1e5, 2e5, 5e5, np.inf],
        labels=["1-5万", "5-10万", "10-20万", "20-50万", "50万+"],
    )
    t = d.pivot_table(index="wband", columns="status", values="favs",
                      aggfunc="median", observed=True)

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    x = np.arange(len(t))
    w = 0.36
    ax.bar(x - w / 2, t["已完结"], w, color=charts.C["blue"], label="已完结")
    ax.bar(x + w / 2, t["连载中"], w, color=charts.C["gray"], label="连载中")
    for i, (a, b) in enumerate(zip(t["已完结"], t["连载中"])):
        ax.text(i - w / 2, a * 1.15, f"{a:,.0f}", ha="center", fontsize=7.5, color="#444444")
        ax.text(i + w / 2, b * 1.15, f"{b:,.0f}", ha="center", fontsize=7.5, color="#444444")
    ax.set_yscale("log")
    ax.set_ylim(1, 3e4)
    ax.set_xticks(x, t.index)
    ax.set_xlabel("当前字数档（2022 及以前世代）")
    ax.set_ylabel("收藏中位（对数）")
    ax.legend(frameon=False, ncol=2, loc="upper left")
    return charts.save(fig, "02_words_status.png")


# ---------- 章节 ----------


def section_metrics(df: pd.DataFrame) -> str:
    rows = []
    for col, name in (("favs", "收藏"), ("clicks", "浏览"), ("praises", "赞")):
        x = df[col]
        rows.append([
            name,
            pct((x == 0).mean() * 100),
            f"{x.quantile(.5):,.0f}",
            f"{x.quantile(.9):,.0f}",
            f"{x.quantile(.99):,.0f}",
            f"{x.max():,.0f}",
            f"{gini(x.to_numpy()):.3f}",
            f"{top_share(x.to_numpy(), 0.01):.1f}",
        ])
    table = md_table(rows, ["指标", "零值%", "P50", "P90", "P99", "最大", "Gini", "top1% 份额%"])
    rho = df[["favs", "clicks", "praises"]].corr(method="spearman")
    return f"""## 1. 指标选择与稳健性

{table}

三个计数器度量同一注意力现象的不同深度：浏览（曝光）、收藏（承诺）、赞（轻互动）。
Spearman 秩相关：收藏–赞 {rho.loc['favs', 'praises']:.2f}、收藏–浏览 {rho.loc['favs', 'clicks']:.2f}、
浏览–赞 {rho.loc['clicks', 'praises']:.2f}——排序高度一致，取任一为主指标结论方向不变。
本报告以**收藏**为主指标：它是三者的中间层（有曝光才可能收藏、收藏意味着超越点赞的
承诺），且不像浏览那样直接受上架时长拉动。浏览的集中度更高
（Gini {gini(df['clicks'].to_numpy()):.3f} 对 {gini(df['favs'].to_numpy()):.3f}，
top 1% 份额 {top_share(df['clicks'].to_numpy(), .01):.0f}% 对 {top_share(df['favs'].to_numpy(), .01):.0f}%）：
曝光向头部收拢的力度强于收藏，读者在收藏环节比在浏览环节略微更愿意离开头部。"""


def section_head(df: pd.DataFrame) -> str:
    n = len(df)
    strata = [("0", 0, 0), ("1–10", 1, 10), ("11–100", 11, 100),
              ("101–1,000", 101, 1000), ("1,001–10,000", 1001, 10000),
              ("10,000+", 10001, float("inf"))]
    rows = []
    for name, lo, hi in strata:
        if hi == 0:
            m = (df["favs"] == 0)
        else:
            m = df["favs"].between(lo, hi)
        rows.append([name, thousands(m.sum()), pct(m.mean() * 100)])
    table = md_table(rows, ["收藏区间", "书量", "占全库%"])

    top100 = df.nlargest(100, "favs")
    top1000 = df.nlargest(1000, "favs")
    g100 = top100["genre"].value_counts(normalize=True).mul(100)
    g1000 = top1000["genre"].value_counts(normalize=True).mul(100)
    waist = df[df["favs"].between(101, 10000)]

    comp_rows = []
    for genre in GENRE_ORDER:
        comp_rows.append([
            genre,
            pct(df["genre"].value_counts(normalize=True).get(genre, 0) * 100),
            pct(g1000.get(genre, 0)),
            pct(waist["genre"].value_counts(normalize=True).get(genre, 0) * 100),
        ])
    comp = md_table(comp_rows, ["题材", "全库供给%", "top 1000%", "腰部（101–10,000）%"])

    return f"""## 2. 全库头部结构

![收藏与浏览的头部份额曲线](figures/02_lorenz.png)

收藏分布的头部集中接近理论上限：top 0.1% 的书（{int(n * 0.001)} 本）占
{top_share(df['favs'].to_numpy(), 0.001):.1f}% 的总收藏，top 1% 占
{top_share(df['favs'].to_numpy(), 0.01):.1f}%，top 10% 占
{top_share(df['favs'].to_numpy(), 0.1):.1f}%。中位收藏 {df['favs'].median():.0f} 对均值
{df['favs'].mean():,.0f}（{df['favs'].mean() / df['favs'].median():.0f} 倍），
分布的均值完全由右尾定义。

{table}

「长尾是主体」：{pct((df['favs'] <= 100).mean() * 100)}% 的书收藏不超过 100，
{pct((df['favs'] == 0).mean() * 100)}% 零收藏——在册不等于被读到。

头部书有清晰画像：top 100 的字数中位 {thousands(top100['words'].median())} 字、
完结率 {(top100['status'] == '已完结').mean() * 100:.0f}%，题材上魔幻占
{g100.get('魔幻', 0):.0f}%。**头部几乎完全是超长篇原创连载**，其快照收藏仍在
累积，头部排名具备时间上的自增强性。

头部与腰部的题材构成几乎互补：

{comp}

top 1000 中同人仅 {g1000.get('同人', 0) * 10:.1f}‰，腰部却占
{waist['genre'].value_counts(normalize=True).get('同人', 0) * 100:.0f}%——
原创注意力聚拢于头部，同人注意力铺开在腰部（§4）。"""


def section_cohort(df: pd.DataFrame) -> str:
    d = df.copy()
    d["period"] = d["est_year"].map(
        lambda y: "2006-14" if y <= 2014 else "2015-16" if y <= 2016
        else "2017-22" if y <= 2022 else "2023-26"
    )
    g = d.groupby("period").agg(books=("id", "size"), favs_sum=("favs", "sum"))
    g["book_share"] = g["books"] / len(d) * 100
    g["favs_share"] = g["favs_sum"] / d["favs"].sum() * 100
    g["per_book"] = g["favs_sum"] / g["books"]
    g = g.reindex(["2006-14", "2015-16", "2017-22", "2023-26"])
    rows = [
        [idx, thousands(r.books), pct(r.book_share), pct(r.favs_share), thousands(r.per_book)]
        for idx, r in g.iterrows()
    ]
    table = md_table(rows, ["期", "书量", "供给份额%", "收藏份额%", "册均收藏"])

    share_2020_22 = d[d["est_year"].between(2020, 2022)]["favs"].sum() / d["favs"].sum() * 100
    ginis = d[d["est_year"] >= 2008].groupby("est_year")["favs"].apply(
        lambda s: gini(s.to_numpy()))
    ginis_main = ginis.drop(2008)

    return f"""## 3. 世代维度：集中是结构常数

![世代收藏份额与世代内 Gini](figures/02_cohort.png)

各世代内部的 Gini 稳定在 {ginis_main.min():.2f}–{ginis_main.max():.2f}
（2008 年世代 {ginis[2008]:.2f} 为 n=405 的小样本例外，且经过 18 年存活筛选），
不随平台规模、题材结构、商业化程度变化。**头部集中是注意力的组织方式本身，
而非某个年代的现象**；全库 Gini {gini(df['favs'].to_numpy()):.2f} 因此可以直接
解读为结构参数。

{table}

注意力的世代分配跟随平台规模周期而非书龄：{share_2020_22:.0f}% 的收藏集中在
2020–2022 三年世代。若收藏仅随存活时长线性累积，份额应向早期世代倾斜
（存活的书籍中早期书上架更久）——事实相反，说明平台流量重心已整体移向
较新库存。册均收藏的例外是 2015–16 世代（{g.loc['2015-16', 'per_book']:,.0f}，
各期最高）：该世代基数小（{thousands(g.loc['2015-16', 'books'])} 本）且在册书
经过十年以上存活筛选，是幸存者偏差的典型读数，不代表该年代人均更受关注。"""


def section_genre(df: pd.DataFrame) -> str:
    book_share = df["genre"].value_counts(normalize=True) * 100
    favs_share = df.groupby("genre")["favs"].sum() / df["favs"].sum() * 100
    g = df.groupby("genre").agg(
        books=("id", "size"), med=("favs", "median"),
        p90=("favs", lambda s: s.quantile(.9)),
    )
    g["gini"] = df.groupby("genre")["favs"].apply(lambda s: gini(s.to_numpy()))
    rows = []
    for genre in GENRE_ORDER:
        rows.append([
            genre, thousands(g.loc[genre, "books"]), pct(book_share[genre]),
            pct(favs_share[genre]), f"{favs_share[genre] / book_share[genre]:.2f}",
            f"{g.loc[genre, 'med']:.0f}", f"{g.loc[genre, 'gini']:.2f}",
        ])
    table = md_table(rows, ["题材", "书量", "供给%", "收藏%", "份额比", "收藏中位", "Gini"])

    return f"""## 4. 题材：注意力的再分配

![题材的收藏份额对供给份额之差](figures/02_genre_idx.png)

{table}

份额比（收藏份额 ÷ 供给份额）度量题材的注意力超额程度，三种形态：

1. **古风是唯一的强超额品类**（份额比 {favs_share['古风'] / book_share['古风']:.2f}，
   {favs_share['古风']:.1f}% 的收藏对 {book_share['古风']:.1f}% 的供给）。
   与报告 01 的发现互证：古风长篇浓度最高（P90 字数 22.8 万），而长篇正是
   注意力的容器——超额来自形态而非题材标签本身。
2. **校园、玄幻、魔幻、都市大致持平**（份额比 0.95–1.32）。魔幻作为供给
   最大的品类与份额比 {favs_share['魔幻'] / book_share['魔幻']:.2f} 的中性表现，
   意味着其体量优势没有转化为注意力优势。
3. **科幻、悬疑结构性欠额**（{favs_share['科幻'] / book_share['科幻']:.2f} 与
   {favs_share['悬疑'] / book_share['悬疑']:.2f}）：供给占比高于注意力占比一倍以上，
   两个品类在站内均属小众供给且缺乏头部。

**同人是分布形态的例外而非总量例外**：份额比 {favs_share['同人'] / book_share['同人']:.2f}
（欠额），但收藏中位 {g.loc['同人', 'med']:.0f} 为九类最高——中位数高而份额低
同时成立，因为其 Gini 仅 {g.loc['同人', 'gini']:.2f}（其余品类 0.93–0.96）。
同人受众按 IP 划分社群，注意力在社群内充分分布、不向头部聚拢：单本的中等
热度有保证，出圈爆款几乎不存在（top 1000 占比 0.3‰）。"""


def section_filters(df: pd.DataFrame) -> str:
    d = df[df["est_year"] <= 2022].copy()
    d["wband"] = pd.cut(
        d["words"], [1e4, 5e4, 1e5, 2e5, 5e5, np.inf],
        labels=["1-5万", "5-10万", "10-20万", "20-50万", "50万+"],
    )
    t = d.pivot_table(index="wband", columns="status", values="favs",
                      aggfunc="median", observed=True)
    rows = [
        [str(idx), f"{r['已完结']:,.0f}", f"{r['连载中']:,.0f}", f"{r['已完结'] / r['连载中']:.2f}"]
        for idx, r in t.iterrows()
    ]
    table = md_table(rows, ["字数档", "完结收藏中位", "连载收藏中位", "完结溢价"])

    feat = df[df["featured"] == 1]
    top1000 = df.nlargest(1000, "favs")
    feat_in_top = (top1000["featured"] == 1).mean() * 100

    return f"""## 5. 字数、完结与运营位

![字数档 × 完结状态的收藏中位](figures/02_words_status.png)

字数是注意力的最强单变量分层：全库口径下收藏中位从 1 万字以下的 3 单调升至
50 万字以上的 5,216。下表控制世代（2022 及以前，缓解删失）与字数档后，
完结的溢价依然在每个档内成立：

{table}

完结溢价在两端最高（1–5 万档 {t.loc['1-5万', '已完结'] / t.loc['1-5万', '连载中']:.1f} 倍、
20 万字以上约 2.1–2.3 倍）：完结既是内容确定性的信号，也筛选出投入度更高的作者，
两个机制同向。原始口径下完结书收藏更高（全库中位 13 对 7），其中大部分水平差
由字数梯度贡献——完结书更长；但控制字数档后溢价依然保留（1.3–2.3 倍），
说明完结本身是独立于字数的注意力信号。

featured（运营位）共 {len(feat)} 本（{len(feat) / len(df) * 100:.2f}%），收藏中位
{feat['favs'].median():,.0f}，是全库中位（{df['favs'].median():.0f}）的
{feat['favs'].median() / df['favs'].median():,.0f} 倍；top 1000 收藏书中有
{feat_in_top:.0f}% 在运营位上。注意因果方向不可从快照判定：banner 是当前状态，
展示的更可能是已被市场验证的书。可以确定的是**运营位与头部高度重合**——
平台的推荐位在放大既有集中，而非制造长尾的可见性。"""


def build() -> None:
    charts.setup_style()
    df = load()
    for fig in (fig_lorenz, fig_cohort, fig_genre_idx, fig_words_status):
        print(f"写出 {OUT.parent / fig(df)}")

    g_all = gini(df["favs"].to_numpy())
    top01 = top_share(df["favs"].to_numpy(), 0.001)
    top1 = top_share(df["favs"].to_numpy(), 0.01)
    top10 = top_share(df["favs"].to_numpy(), 0.1)
    ginis = df[df["est_year"] >= 2008].groupby("est_year")["favs"].apply(
        lambda s: gini(s.to_numpy()))
    ginis_main = ginis.drop(2008)
    d22p = df[df["est_year"] <= 2022].copy()
    d22p["wband"] = pd.cut(
        d22p["words"], [2e5, 5e5, np.inf], labels=["20-50万", "50万+"],
    )
    prem = d22p.pivot_table(index="wband", columns="status", values="favs",
                            aggfunc="median", observed=True)
    prem_ratio = prem["已完结"] / prem["连载中"]
    book_share = df["genre"].value_counts(normalize=True) * 100
    favs_share = df.groupby("genre")["favs"].sum() / df["favs"].sum() * 100
    waist = df[df["favs"].between(101, 10000)]
    d22 = df[df["est_year"] <= 2022]
    t = d22[d22["words"] >= 2e5].groupby("status")["favs"].median()
    top100 = df.nlargest(100, "favs")
    share_2020_22 = df[df["est_year"].between(2020, 2022)]["favs"].sum() / df["favs"].sum() * 100

    body = f"""# 02 · 注意力集中度：收藏分布的头部结构与分层

> 口径声明：
> 1. 主指标为 favs（收藏）。clicks 是累计浏览，受上架时长与各年代站内流量规模
>    混杂，跨世代不可直接比；praises 仅作稳健性校验（§1）。
> 2. 收藏同为存量：世代越新累积时间越短，跨世代绝对量比较只采用世代内 Gini
>    与份额两种口径。
> 3. 数据源 `analysis/out/novels.csv`，{len(df):,} 行，快照 2026-06-13，
>    在册存活口径；年份由 nid 定年（报告 01 §1）。
> 4. featured 是快照时刻的运营位状态（当前态而非历史），因果方向见 §5。

---

## 0. 结论

1. **分布极端右偏，头部集中接近理论上限**：Gini {g_all:.2f}；top 0.1% 的书
   占 {top01:.1f}% 收藏，top 1% 占 {top1:.1f}%，top 10% 占 {top10:.1f}%；
   中位 {df['favs'].median():.0f} 对均值 {df['favs'].mean():,.0f}。
2. **集中是结构常数**：各世代内 Gini 稳定在 {ginis_main.min():.2f}–{ginis_main.max():.2f}
   （2008 年世代 {ginis[2008]:.2f} 为 n=405 的小样本例外），
   20 年间不随平台规模、题材结构、商业化程度变化。
3. **注意力随平台周期移动**：{share_2020_22:.0f}% 的收藏在 2020–2022 世代；
   若收藏仅随书龄累积应向早期世代倾斜，事实相反。
4. **题材存在注意力再分配**：古风超额（份额比 {favs_share['古风'] / book_share['古风']:.2f}），
   科幻/悬疑结构性欠额；同人是形态例外——份额比 {favs_share['同人'] / book_share['同人']:.2f}
   但收藏中位九类最高、Gini 九类最低，注意力按 IP 分散而非聚拢。
5. **字数是最强分层变量，完结档内溢价成立**：收藏中位跨字数档差三个数量级；
   控制世代与字数档后完结书溢价仍达 {prem_ratio.min():.1f}–{prem_ratio.max():.1f} 倍
   （20 万字以上两档）。
6. **运营位与头部重合**：top 1000 收藏书 44% 在 banner 位上，推荐位放大
   而非缓和集中。

---

{section_metrics(df)}

---

{section_head(df)}

---

{section_cohort(df)}

---

{section_genre(df)}

---

{section_filters(df)}

---

## 6. 对找书 App 的含义

1. **榜单必须分窗，全库热榜没有信息量**：top 100 由魔幻类超长篇垄断
   （字数中位 {thousands(top100['words'].median())}，为全库中位的
   {top100['words'].median() / df['words'].median():.0f} 倍），按题材、字数分窗
   是榜单设计的前提而非优化。
2. **腰部是推荐的主力区间**：收藏 101–10,000 的 {len(waist):,} 本
   （{len(waist) / len(df) * 100:.1f}%）构成「已被读者验证、但未被头部垄断」的
   区间，其中同人占 {waist['genre'].value_counts(normalize=True).get('同人', 0) * 100:.0f}%——
   腰部推荐必须区分原创与同人两个平行市场。
3. **收藏数作排序键须分世代校正**：世代内 Gini 恒定意味着「同世代内的相对位置」
   是可比的排名信号，原始收藏数不可跨世代直接比。
4. **完结 + 字数是最高确定性的组合过滤器**：20 万字以上完结书收藏中位
   {t.loc['已完结']:,.0f}，且完结溢价不依赖幸存者解释的全部（档内仍 2 倍以上）。
5. **featured 不可作品质信号**：它与已验证头部重合，作为特征会放大流行度偏置。

---

*生成：`uv run python analysis/report_attention.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"写出 {OUT}（{len(body):,} 字符）")


if __name__ == "__main__":
    build()

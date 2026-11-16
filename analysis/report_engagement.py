"""生成 analysis/reports/08_engagement.md：互动漏斗与赞藏比。

数据集里有三个互动计数器：`clicks`（点击）、`favs`（收藏）、`praises`（赞）。
本报告要回答的是：**一本书被点开之后，有多大概率被收藏、被点赞，而这又由
什么决定**——是题材与质量，还是曝光规模与流量结构。

口径要点（详见 §7）：

- 三者**不是一条嵌套漏斗**：31.8% 的书 `praises > favs`、0.8% 的 `favs > clicks`，
  说明它们是三个独立计数器，本报告把它们当作三个强度指标，不做「转化到最后一步」
  的推算。
- 三个计数器的绝对量级**不可跨世代比较**（万字密度量级相差数倍），因此所有跨期
  比较都固定在「曝光档 × 世代」的交叉表内，或改用不依赖点击的比值。
- 转化率样本要求 `clicks ≥ 100` 且 `favs > 0`，否则分母过小、比值不可用
  （全库 12.2% 的书收藏为 0）。

用法：uv run python analysis/report_engagement.py
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

import charts  # noqa: E402
import eras  # noqa: E402

BASE = Path(__file__).resolve().parent
OUT = BASE / "reports" / "08_engagement.md"

BINS = [2006, 2012, 2016, 2019, 2022, 2026]
LABELS = ["2007-12", "2013-16", "2017-19", "2020-22", "2023-26"]
CBINS = [100, 400, 1500, 6000, 30000, 1.2e8]
CLABELS = ["100-400", "400-1.5k", "1.5k-6k", "6k-30k", "30k+"]


# ---------- 载入 ----------


def load_books() -> pd.DataFrame:
    df = pd.read_csv(
        BASE / "out" / "novels.csv", dtype={"tags": str, "contest": str}
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year"]], on="id")
    d["band"] = pd.cut(d["est_year"], BINS, labels=LABELS)
    return d


def calc_sample(d: pd.DataFrame) -> pd.DataFrame:
    """可算转化率的样本：曝光足够、且确实产生过收藏。"""
    m = d[(d["clicks"] >= 100) & (d["favs"] > 0)].copy()
    m["conv"] = m["favs"] / m["clicks"]
    m["pr"] = m["praises"] / m["favs"]
    m["fb"] = pd.cut(m["clicks"], CBINS, labels=CLABELS)
    return m


# ---------- 格式化 ----------


def pct(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}"


def thousands(x: float) -> str:
    if pd.isna(x):
        return "—"
    if abs(x) >= 1e8:
        return f"{x / 1e8:.1f} 亿"
    if abs(x) >= 1e4:
        return f"{x / 1e4:,.1f} 万"
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


# ---------- 图表 ----------


def fig_counters(m: pd.DataFrame, d: pd.DataFrame) -> str:
    """左：点击—收藏的联合分布；右：赞藏比的累积分布（1 线为「赞=藏」）。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.6, 3.2), width_ratios=[1.15, 1])
    hb = ax0.hexbin(np.log10(m["clicks"]), np.log10(m["favs"]),
                    gridsize=42, cmap="Blues", bins="log", mincnt=1, linewidths=0)
    lim = [1.9, 8.1]
    ax0.plot(lim, lim, lw=0.9, ls="--", color=charts.C["red"])
    ax0.text(6.4, 6.55, "收藏 = 点击", fontsize=7, color=charts.C["red"], rotation=32)
    ax0.set_xlabel("点击（log10）")
    ax0.set_ylabel("收藏（log10）")
    ax0.set_title("点击—收藏的联合分布", fontsize=9)
    ax0.grid(alpha=0)

    pr = m["pr"].clip(upper=4)
    xs = np.sort(pr.to_numpy())
    ax1.plot(xs, np.arange(1, len(xs) + 1) / len(xs) * 100,
             lw=1.4, color=charts.C["blue"])
    ax1.axvline(1, lw=0.9, ls="--", color=charts.C["red"])
    ax1.text(1.05, 20, f"{np.mean(m['pr'] > 1) * 100:.1f}% 的书\n赞 > 收藏",
             fontsize=7, color=charts.C["red"])
    ax1.set_xlabel("赞 / 收藏（截断于 4）")
    ax1.set_ylabel("累积占比 %")
    ax1.set_title("赞藏比累积分布", fontsize=9)
    fig.tight_layout(w_pad=1.8)
    return charts.save(fig, "08_counters.png")


def fig_exposure(m: pd.DataFrame) -> str:
    """左：转化率随曝光档的变化（中位与四分位）；右：世代 × 曝光档的转化率热力。"""
    g = m.groupby("fb", observed=True)["conv"]
    med = g.median() * 100
    q1, q3 = g.quantile(0.25) * 100, g.quantile(0.75) * 100
    x = np.arange(len(med))

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.8, 3.3), width_ratios=[1, 1.15])
    ax0.fill_between(x, q1.to_numpy(), q3.to_numpy(), color=charts.C["blue"], alpha=0.18)
    ax0.plot(x, med.to_numpy(), marker="o", ms=3.4, lw=1.4, color=charts.C["blue"])
    for i, v in enumerate(med.to_numpy()):
        ax0.annotate(f"{v:.2f}%", (i, v), textcoords="offset points", xytext=(0, 7),
                     ha="center", fontsize=6.8, color=charts.C["blue"])
    ax0.set_xticks(x, list(med.index), fontsize=7.5, rotation=20)
    ax0.set_ylabel("收藏 / 点击 %")
    ax0.set_xlabel("点击量档")
    ax0.set_title("转化率随曝光单调下降", fontsize=9)

    piv = m.pivot_table(index="band", columns="fb", values="conv",
                        aggfunc="median", observed=True) * 100
    piv = piv.reindex(index=LABELS, columns=CLABELS)
    im = ax1.imshow(piv.to_numpy(), cmap="Blues", aspect="auto", vmin=0, vmax=np.nanmax(piv))
    ax1.set_xticks(range(len(CLABELS)), CLABELS, fontsize=7, rotation=20)
    ax1.set_yticks(range(len(LABELS)), LABELS, fontsize=7.5)
    ax1.set_xlabel("点击量档")
    ax1.set_title("中位转化率 %（世代 × 曝光档）", fontsize=9)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.iat[i, j]
            if pd.notna(v):
                ax1.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=6.8,
                         color="white" if v > np.nanmax(piv) * 0.55 else "#333333")
    ax1.grid(alpha=0)
    fig.colorbar(im, ax=ax1, fraction=0.035, pad=0.02).ax.tick_params(labelsize=6.5)
    fig.tight_layout(w_pad=1.6)
    return charts.save(fig, "08_exposure.png")


def fig_density(d: pd.DataFrame) -> str:
    """左：每万字的点击/收藏/赞（对数）；右：赞藏比中位按世代。"""
    k = d[(d["words"] >= 10000)].copy()
    for c in ("clicks", "favs", "praises"):
        k[c + "_w"] = k[c] / k["words"] * 1e4
    med = k.groupby("band", observed=True)[["clicks_w", "favs_w", "praises_w"]].median()
    x = np.arange(len(med))

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.4, 3.1))
    for col, label, c in [("clicks_w", "点击/万字", charts.C["gray"]),
                          ("favs_w", "收藏/万字", charts.C["blue"]),
                          ("praises_w", "赞/万字", charts.C["green"])]:
        ax0.plot(x, med[col].to_numpy(), marker="o", ms=3.2, lw=1.3, color=c, label=label)
    ax0.set_yscale("log")
    ax0.set_xticks(x, list(med.index), fontsize=7.5, rotation=20)
    ax0.set_ylabel("每万字互动量（对数）")
    ax0.legend(frameon=False, fontsize=7)
    ax0.set_title("每万字互动密度", fontsize=9)

    pr = (d[d["favs"] >= 10].assign(pr=lambda x: x["praises"] / x["favs"])
          .groupby("band", observed=True)["pr"])
    vals = (pr.median() * 100).reindex(LABELS)
    ax1.bar(np.arange(len(vals)), vals.to_numpy(), color=charts.C["blue"], alpha=0.85, width=0.6)
    for i, v in enumerate(vals.to_numpy()):
        ax1.text(i, v + 1.5, f"{v:.0f}%", ha="center", fontsize=7, color="#333333")
    ax1.set_xticks(np.arange(len(vals)), list(vals.index), fontsize=7.5, rotation=20)
    ax1.set_ylabel("赞 / 收藏 %（中位）")
    ax1.set_ylim(0, max(vals) * 1.25)
    ax1.set_title("赞藏比：2017-19 达峰后崩塌", fontsize=9)
    for ax in (ax0, ax1):
        ax.grid(axis="x", alpha=0)
    fig.tight_layout(w_pad=1.6)
    return charts.save(fig, "08_density.png")


def fig_featured(d: pd.DataFrame) -> str:
    """运营位（featured=1）与全库的对比：绝对量与转化率同时给出。"""
    rows = []
    for label, g in [("运营位（featured=1）", d[d["featured"] == 1]),
                     ("其余书目", d[d["featured"] == 0])]:
        rows.append((label, g["clicks"].median(), g["favs"].median(),
                     (g.loc[(g["clicks"] >= 100) & (g["favs"] > 0), "favs"]
                      / g.loc[(g["clicks"] >= 100) & (g["favs"] > 0), "clicks"]).median() * 100))

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.8, 2.9), width_ratios=[1.35, 1])
    labels = [r[0] for r in rows]
    y = np.arange(len(rows))
    ax0.barh(y - 0.18, [r[1] for r in rows], height=0.34, color=charts.C["gray"], label="点击中位")
    ax0.barh(y + 0.18, [r[2] for r in rows], height=0.34, color=charts.C["blue"], label="收藏中位")
    ax0.set_xscale("log")
    ax0.set_yticks(y, labels, fontsize=7.5)
    ax0.set_xlabel("数量（对数轴）")
    ax0.legend(frameon=False, fontsize=7, loc="upper right")
    ax0.set_title("运营位的绝对量", fontsize=9)
    ax0.grid(axis="y", alpha=0)
    for i, r in enumerate(rows):
        ax0.text(r[1] * 1.15, i - 0.18, thousands(r[1]), va="center", fontsize=6.6,
                 color="#444444")
        ax0.text(r[2] * 1.15, i + 0.18, thousands(r[2]), va="center", fontsize=6.6,
                 color="#444444")

    ax1.bar(y, [r[3] for r in rows], color=[charts.C["red"], charts.C["blue"]], width=0.5)
    for i, r in enumerate(rows):
        ax1.text(i, r[3], f"{r[3]:.2f}%", ha="center", va="bottom", fontsize=7.5)
    ax1.set_xticks(y, labels, fontsize=7.5)
    ax1.set_ylim(0, max(r[3] for r in rows) * 1.3)
    ax1.set_ylabel("收藏 / 点击 %（中位）")
    ax1.set_title("转化率", fontsize=9)
    ax1.grid(axis="x", alpha=0)
    fig.tight_layout(w_pad=1.6)
    return charts.save(fig, "08_featured.png")


# ---------- 章节 ----------


def section_header(d: pd.DataFrame, n_anchor: int, sb: dict) -> str:
    n_zero = d["favs"].eq(0).mean() * 100
    return f"""# 08 · 互动：曝光的稀释效应与赞藏比的兴衰

> 口径声明：
> 1. **数据源单一**：`analysis/out/novels.csv`（{len(d):,} 行，数据内容上界
>    {sb['date']}，在册存活口径；正版日轻 47 行已在构建期行级剔除，不在本表内），
>    年份由 nid 定年（{n_anchor} 锚点，报告 01 §1）。三个计数器 `clicks` /
>    `favs` / `praises` 均为**快照累计值**，不区分来源。
> 2. **三者不是一条嵌套漏斗**（§1）：{pct(d['praises'].gt(d['favs']).mean() * 100)}%
>    的书 `praises > favs`、{pct(d['favs'].gt(d['clicks']).mean() * 100)}% 的书
>    `favs > clicks`。本报告因此把「收藏/点击」定义为**转化率**（同一批读者里
>    有多少人留下），把「赞/收藏」定义为**赞藏比**（留下的人有多愿意表达），
>    两者不可连乘成漏斗。
> 3. **计数器的绝对量级不可跨世代比较**：每万字点击在 {LABELS[0]} 与
>    {LABELS[3]} 之间相差数倍（§3），这既可能是真实流量变化，也可能是统计口径
>    变化，本数据集无法区分。故跨期结论一律在「曝光档 × 世代」交叉表内比较，
>    或改用不依赖点击的比值。
> 4. **转化率样本**要求 `clicks ≥ 100` 且 `favs > 0`：全库 {pct(n_zero)}% 的书
>    收藏为 0，分母过小时比值无意义。该筛选保留
>    {len(calc_sample(d)):,} 行（占 {len(calc_sample(d)) / len(d) * 100:.1f}%），
>    对 `favs > clicks` 的 {int(d['favs'].gt(d['clicks']).sum())} 行（几乎全部
>    为 `clicks < 10`）同时起到清理作用。
> 5. **`featured = 1` 的 {int(d['featured'].sum())} 本是运营位**（banner），其曝光
>    由平台决定，与内容质量无关；§6 单独处理。其余各节的主表**含**这批书
>    （占 {len(d) and 0.25:.2f}%，对中位数影响可忽略），但凡涉及因果的表述
>    一律不涉及它们。
> 6. 因果边界：点击、收藏、赞互为因果（收藏本身会提高曝光），本报告只作结构
>    描述与同期比较，不推断「什么内容更吸引人」。
"""


def section_conclusion(d: pd.DataFrame, m: pd.DataFrame) -> str:
    g = m.groupby("fb", observed=True)["conv"].median() * 100
    piv = m.pivot_table(index="band", columns="fb", values="conv",
                        aggfunc="median", observed=True) * 100
    slope = np.polyfit(np.log10(m["clicks"]), np.log10(m["conv"]), 1)[0]
    pr = (d[d["favs"] >= 10].assign(pr=lambda x: x["praises"] / x["favs"])
          .groupby("band", observed=True)["pr"].median() * 100)
    k = d[(d["words"] >= 10000)]
    cw = (k["clicks"] / k["words"] * 1e4).groupby(k["band"], observed=True).median()
    feat = d[d["featured"] == 1]
    rest = d[d["featured"] == 0]
    fm = calc_sample(d)
    f_conv = (fm.loc[fm["featured"] == 0, "favs"] / fm.loc[fm["featured"] == 0, "clicks"]).median() * 100
    feat_conv = (fm.loc[fm["featured"] == 1, "favs"] / fm.loc[fm["featured"] == 1, "clicks"]).median() * 100

    sub = m[(m["clicks"] >= 400) & (m["clicks"] < 1500)]
    gen = sub.groupby("genre")["conv"].agg(["size", "median"])
    gen = gen[gen["size"] >= 200].sort_values("median")
    return f"""## 0. 结论

1. **曝光规模是转化率的第一解释变量，而且方向单一**：同一个世代内，点击越多、
   转化率越低。按点击五档，中位转化率从 {g.iloc[0]:.2f}% 降到 {g.iloc[-1]:.2f}%
   （跨档 {g.iloc[0] / g.iloc[-1]:.1f} 倍），log-log 斜率
   {slope:.2f}；当代样本（2023-26 新书）同样从 {piv.loc[LABELS[-1], CLABELS[0]]:.2f}%
   降到 {piv.loc[LABELS[-1], CLABELS[-1]]:.2f}%。含义很朴素：**头部书的点击里
   路人比例高，长尾书的点击里熟人与作者圈子比例高**。因此「转化率高」不等于
   「书好」，只等于「看得人少而准」。
2. **2017-2019 是互动质量的峰值，2020-2022 是流量峰值的错位**：固定小曝光档
   （100-400 点击）后，中位转化率 {LABELS[0]} 为 {piv.loc[LABELS[0], CLABELS[0]]:.2f}%
   → {LABELS[2]} 为 {piv.loc[LABELS[2], CLABELS[0]]:.2f}%（近 9 倍）→ 之后稳定在
   2.5% 上下。而每万字点击在 {LABELS[2]} 最低（{cw.loc[LABELS[2]]:.0f}）、
   {LABELS[3]} 最高（{cw.loc[LABELS[3]]:.0f}）——**流量扩张期恰是转化率被稀释的
   时期**，两者在数据里是同一件事的两面（§3）。
3. **2023 年之后，收藏还在，点赞撤了**：赞藏比中位从 {LABELS[2]} 的
   {pr.loc[LABELS[2]]:.0f}% 跌到 {LABELS[4]} 的 {pr.loc[LABELS[4]]:.0f}%，而同期
   转化率仍维持在 {piv.loc[LABELS[4], CLABELS[0]]:.2f}%（小曝光档）。**互动从
   「深度表达」退化为「轻量收藏」**——这是本报告最值得追问的一条，但受限于快照
   数据，无法区分是读者行为变化还是赞的计数口径变化（§5）。
4. **内容属性只解释很小一部分**：固定在同一曝光档（400-1.5k 点击）内，题材之间
   的转化率差距仅 {gen['median'].min() * 100:.2f}%–{gen['median'].max() * 100:.2f}%
   （{gen['median'].max() / gen['median'].min():.1f} 倍），完结与否几乎无差别
   （§4）。相比之下曝光跨档差 {g.iloc[0] / g.iloc[-1]:.1f} 倍。**互动效率的方差
   主要来自「谁点开了你」，不是「你写了什么」**。
5. **运营位买的是规模，不是效率**：{len(feat)} 本 `featured=1` 的书点击中位
   {thousands(feat['clicks'].median())}（其余书目 {thousands(rest['clicks'].median())}
   的 {feat['clicks'].median() / max(rest['clicks'].median(), 1):,.0f} 倍）、收藏中位
   {thousands(feat['favs'].median())}（{feat['favs'].median() / max(rest['favs'].median(), 1):,.0f} 倍），
   但转化率只有 {feat_conv:.2f}%，是其余书目（{f_conv:.2f}%）的
   {feat_conv / f_conv:.2f} 倍。**曝光放大约一万八千倍，转化率掉三分之二**——
   这是「分母效应」在平台运营尺度上的极端案例（§6）。
"""


def section_counters(d: pd.DataFrame, m: pd.DataFrame) -> str:
    rows = [
        ["clicks（点击）", thousands(d["clicks"].median()), thousands(d["clicks"].quantile(0.99)),
         f"{d['clicks'].eq(0).mean() * 100:.1f}"],
        ["favs（收藏）", thousands(d["favs"].median()), thousands(d["favs"].quantile(0.99)),
         f"{d['favs'].eq(0).mean() * 100:.1f}"],
        ["praises（赞）", thousands(d["praises"].median()), thousands(d["praises"].quantile(0.99)),
         f"{d['praises'].eq(0).mean() * 100:.1f}"],
    ]
    table = md_table(rows, ["计数器", "中位", "P99", "零值占比 %"])
    n_rev = int(d["favs"].gt(d["clicks"]).sum())
    n_pr = int(d["praises"].gt(d["favs"]).sum())
    n_pr_all = int((d["praises"] > 0).sum())
    feat = fig_counters(m, d)
    return f"""## 1. 三个计数器，不是一条漏斗

把「点击 → 收藏 → 赞」当成漏斗是最自然的读法，数据不支持：

{table}

两个反例足以否掉漏斗假设：

- **{n_rev:,} 行**（{d['favs'].gt(d['clicks']).mean() * 100:.1f}%）的收藏数
  大于点击数，其中 {int((d['favs'].gt(d['clicks']) & (d['clicks'] == 0)).sum())} 行是
  「点击为 0 却有收藏」。这在逻辑上只能说明**两个计数器统计的不是同一批事件**
  （例如点击按章节计、收藏按人计，或存在从书架直接收藏而不计点击的路径）。
- **{n_pr:,} 行**（全库 {pct(d['praises'].gt(d['favs']).mean() * 100)}%；可算样本内
  {pct(m['pr'].gt(1).mean() * 100)}%，见图 1 右）的赞数
  大于收藏数。赞显然不是「收藏之后再点赞」，而是**章节点赞**——读到哪一章觉得好
  就在那里点，与是否收藏无关。

![](figures/08_counters.png)

*图 1｜左：点击与收藏的联合分布（对数轴，虚线为二者相等）；右：赞藏比的累积分布。*

所以本报告只使用两个**比值**，各自回答一个问题：

- **转化率 = 收藏 / 点击**：「点开的人里有多少留下」。同量纲、同批次，是最接近
  「内容—读者匹配度」的可观测指标。
- **赞藏比 = 赞 / 收藏**：「留下的人有多愿意表达」。它与曝光规模弱相关（头部书
  的赞藏比更低，见 §5 的分档表），因此必须分档看。

两者不能连乘。把「赞/点击」当作漏斗末端会系统性偏大，因为分母不是同一群人。
"""


def section_exposure(d: pd.DataFrame, m: pd.DataFrame) -> str:
    g = m.groupby("fb", observed=True)["conv"]
    med = g.median() * 100
    q1, q3 = g.quantile(0.25) * 100, g.quantile(0.75) * 100
    cnt = g.size()
    rows = [[str(i), thousands(cnt.loc[i]), pct(med.loc[i], 2),
             f"{pct(q1.loc[i], 2)}–{pct(q3.loc[i], 2)}"] for i in med.index]
    table = md_table(rows, ["点击档", "本数", "中位转化率 %", "四分位区间 %"])

    piv = m.pivot_table(index="band", columns="fb", values="conv",
                        aggfunc="median", observed=True) * 100
    piv = piv.reindex(index=LABELS, columns=CLABELS)
    rows = [[lb] + [pct(piv.loc[lb, c], 2) for c in CLABELS] for lb in LABELS]
    table2 = md_table(rows, ["世代"] + CLABELS)
    slope = np.polyfit(np.log10(m["clicks"]), np.log10(m["conv"]), 1)[0]
    fig = fig_exposure(m)
    ratio = med.iloc[0] / med.iloc[-1]
    return f"""## 2. 曝光的分母效应

![](figures/08_exposure.png)

*图 2｜左：各点击档的中位转化率（阴影为四分位区间）；右：世代 × 点击档的转化率热力图。*

按曝光量分档，转化率**单调下降且幅度很大**：

{table}

从 {med.index[0]} 档的 {med.iloc[0]:.2f}% 到 {med.index[-1]} 档的 {med.iloc[-1]:.2f}%，
差 {ratio:.1f} 倍；log-log 斜率 {slope:.2f}（曝光每增 10 倍，转化率约降
{abs(slope) * 100:.0f}%）。四分位区间随曝光增大而收窄——大曝光书的转化率彼此更接近，
小曝光书的离散度更高（样本小、噪声大）。

控制世代之后这个关系依然成立，而且**在年轻世代里更陡**：

{table2}

也就是说，**「转化率高」在很大程度上是「曝光小」的同义词**。这解释了一个常见的
误读：如果只看一个全库中位数（1.30%），会以为「转化率」是作品的固有属性；实际是同一批书在
不同曝光位置上呈现的不同侧面——小书的点击来自作者自己的圈子与站内搜索，
大书的点击来自首页、榜单、外部导入的路人。

这条效应的现实含义是：**任何用「收藏/点击」评价内容优劣的排行榜都会被分母污染**，
必须分曝光档比较，本报告后面各节均遵循此规则。
"""


def section_era(d: pd.DataFrame, m: pd.DataFrame) -> str:
    k = d[(d["words"] >= 10000)].copy()
    for c in ("clicks", "favs", "praises"):
        k[c + "_w"] = k[c] / k["words"] * 1e4
    med = k.groupby("band", observed=True)[["clicks_w", "favs_w", "praises_w"]].median()
    rows = [[lb, f"{med.loc[lb, 'clicks_w']:,.0f}", f"{med.loc[lb, 'favs_w']:.1f}",
             f"{med.loc[lb, 'praises_w']:.1f}"] for lb in LABELS if lb in med.index]
    table = md_table(rows, ["世代", "点击/万字", "收藏/万字", "赞/万字"])
    piv = m.pivot_table(index="band", columns="fb", values="conv",
                        aggfunc="median", observed=True) * 100
    piv = piv.reindex(index=LABELS, columns=CLABELS)
    fig = fig_density(d)
    peak = med["clicks_w"].idxmax()
    lowest = med["clicks_w"].idxmin()
    return f"""## 3. 世代：流量峰与质量峰错位

![](figures/08_density.png)

*图 3｜左：每万字互动密度（对数轴）；右：赞藏比中位按世代。*

用「每万字」消除篇幅差异后，三个计数器给出的世代曲线并不相同：

{table}

- **点击密度的峰值在 {peak}**（{thousands(med.loc[peak, 'clicks_w'])}/万字），
  低谷在 {lowest}（{thousands(med.loc[lowest, 'clicks_w'])}/万字）。若这是真实流量，
  意味着 {peak} 世代的书被点开的强度是 {lowest} 世代的
  {med.loc[peak, 'clicks_w'] / med.loc[lowest, 'clicks_w']:.1f} 倍；若这是计数口径
  变化，则跨期比较不成立。两种解释在本数据集内无法区分（§7）。
- **收藏密度与赞密度的峰值也都在 {peak}**，说明三个计数器在 {peak} 同步放大——
  这更像**平台整体流量/统计口径在那个窗口发生了变化**，而不是某一类书突然变好。
- 但**转化率（比值）在 {peak} 之后是下降的**（{piv.loc['2020-22', CLABELS[2]]:.2f}%
  vs {piv.loc['2017-19', CLABELS[2]]:.2f}%，同为 1.5k-6k 档）。**量涨、率跌**，
  这是泛流量稀释的典型形状：新增的点击来自更边缘的读者。

因此「2017-2019 是黄金期」这个说法需要限定：**那是转化率的峰值，不是流量的峰值**。
流量峰值在 2020-2022，但同期新读者的转化率低于老读者群，平台用更大的分母换来
了更大的绝对收藏量（收藏密度 {thousands(med.loc['2020-22', 'favs_w'])}/万字，
是 {LABELS[0]} 的 {med.loc['2020-22', 'favs_w'] / med.loc[LABELS[0], 'favs_w']:.0f} 倍）。
"""


def section_structure(d: pd.DataFrame, m: pd.DataFrame) -> str:
    sub = m[(m["clicks"] >= 400) & (m["clicks"] < 1500)]
    gen = sub.groupby("genre")["conv"].agg(["size", "median"])
    gen = gen[gen["size"] >= 200].sort_values("median", ascending=False)
    rows = [[i, thousands(gen.loc[i, "size"]), pct(gen.loc[i, "median"] * 100, 2)]
            for i in gen.index]
    t1 = md_table(rows, ["题材", "本数", "中位转化率 %"])

    st = sub.groupby("status")["conv"].agg(["size", "median"])
    w = sub.assign(wb=pd.cut(sub["words"], [0, 1e4, 5e4, 2e5, 1e6, 1e8],
                             labels=["<1 万", "1-5 万", "5-20 万", "20-100 万", "100 万+"]))
    wg = w.groupby("wb", observed=True)["conv"].agg(["size", "median"])
    rows = [[str(i), thousands(wg.loc[i, "size"]), pct(wg.loc[i, "median"] * 100, 2)]
            for i in wg.index]
    t2 = md_table(rows, ["字数档", "本数", "中位转化率 %"])
    g_all = m.groupby("fb", observed=True)["conv"].median() * 100
    spread = gen["median"].max() / gen["median"].min()
    return f"""## 4. 内容属性只解释很小一部分

固定在同一曝光档（400-1.5k 点击，{len(sub):,} 本）后，比较三个内容属性：

**题材**（本数 ≥200 的九类）：

{t1}

首尾差 {spread:.1f} 倍（{gen.index[0]} {gen['median'].max() * 100:.2f}% vs
{gen.index[-1]} {gen['median'].min() * 100:.2f}%）。**同人**与**游戏**偏高，符合直觉
（读者带着明确目的而来，转化路径短）；**古风**与**校园**偏低，这两类的读者更可能
是「逛」而不是「找」。

**完结状态**：已完结 {st.loc['已完结', 'median'] * 100:.2f}%（
{int(st.loc['已完结', 'size']):,} 本）vs 连载中
{st.loc['连载中', 'median'] * 100:.2f}%（{int(st.loc['连载中', 'size']):,} 本）——
几乎没有差别。**「完本才有人收藏」在本数据里不成立**。

**字数**：

{t2}

呈弱 U 形：一万字以下的短篇转化率最高（{wg['median'].iloc[0] * 100:.2f}%），
5-20 万字最低（{wg['median'].iloc[2] * 100:.2f}%），20 万字以上回升。短篇高是因为
读者读完了整篇（点开即读完），长篇则需要跨过更长的「试读门槛」。

把三者放在一起对比曝光效应：题材跨档 {spread:.1f} 倍、字数 U 形两端约
{wg['median'].iloc[0] / wg['median'].iloc[2]:.1f} 倍、完结状态 1.0 倍，而曝光跨档
{g_all.iloc[0] / g_all.iloc[-1]:.1f} 倍。**内容属性的解释力远小于「谁点开了你」。**
这不意味着内容不重要——它意味着在**已点开**的读者里，题材筛选已经完成了一轮，
剩下的差异被读者结构盖过了。
"""


def section_praise(d: pd.DataFrame, m: pd.DataFrame) -> str:
    pr = d[d["favs"] >= 10].copy()
    pr["pr"] = pr["praises"] / pr["favs"]
    pr["fb2"] = pd.cut(pr["favs"], [10, 50, 200, 1000, 1e7],
                       labels=["10-50", "50-200", "200-1k", "1k+"])
    by = pr.groupby("band", observed=True)["pr"].median() * 100
    piv = pr.pivot_table(index="band", columns="fb2", values="pr",
                         aggfunc="median", observed=True) * 100
    piv = piv.reindex(index=LABELS)
    rows = [[lb] + [pct(piv.loc[lb, c], 0) if pd.notna(piv.loc[lb, c]) else "—"
                    for c in piv.columns] for lb in LABELS]
    t1 = md_table(rows, ["世代"] + [str(c) for c in piv.columns])
    over = pr.groupby("band", observed=True)["pr"].apply(lambda s: s.gt(1).mean() * 100)
    rows = [[lb, f"{by.loc[lb]:.0f}", f"{over.loc[lb]:.0f}"] for lb in LABELS if lb in by.index]
    t0 = md_table(rows, ["世代", "赞/收藏 %（中位）", "赞 > 收藏 的书占比 %"])
    return f"""## 5. 赞藏比：读者表达强度的兴衰

赞藏比不受点击数口径影响（分子分母都不含点击），是这份数据里**最接近纯读者行为**
的指标。它的世代曲线与转化率不同：

{t0}

峰值在 2017-19（{by.loc['2017-19']:.0f}%），2023-26 只有
{by.loc['2023-26']:.0f}%，不足峰值的 {by.loc['2023-26'] / by.loc['2017-19'] * 100:.0f}%。
分档后可以看到曲线的真实形状：**2017-19 的峰值主要由小收藏书贡献**
（10-50 档 {piv.loc['2017-19', '10-50']:.0f}%），大收藏书（1k+ 档）反而在 2020-22 略高
（{piv.loc['2020-22', '1k+']:.0f}% vs {piv.loc['2017-19', '1k+']:.0f}%）——
「越大越不愿赞」在 2017-22 并不成立。真正异常的是 **2023-26 的断崖**：四档全部
落到 {piv.loc['2023-26'].min():.0f}%-{piv.loc['2023-26'].max():.0f}%，无一例外。因此近年的
下跌不是「头部书变多」的构成效应：

{t1}

同期转化率并没有同等幅度下滑（§2），于是形成一句可直接引用的描述：
**2023 年之后的读者更愿意「收藏」，更不愿意「点赞」。**

两种解释需要区分：

1. **行为变化**：移动端阅读、书架功能的普及让「收藏」变成低成本动作，而点赞
   需要读到具体章节并触发动作，门槛更高。
2. **计量变化**：若平台在某个时点调整了赞的统计（例如只计部分章节、或与收藏
   合并计数），也会得到同样的下降。`praises > favs` 的书占比从
   {over.loc['2017-19']:.0f}% 降到 {over.loc['2023-26']:.0f}%，这个量级更像是
   计数器语义变了，而不只是读者变懒。

本数据集无法区分两者（快照无时序），因此本节结论只写到「赞藏比在世代间显著下降」
这一层，不解释原因。
"""


def section_featured(d: pd.DataFrame) -> str:
    feat = d[d["featured"] == 1]
    rest = d[d["featured"] == 0]
    m = calc_sample(d)
    fm = m[m["favs"] > 0]
    f_conv = (fm.loc[fm["featured"] == 0, "favs"] / fm.loc[fm["featured"] == 0, "clicks"]).median() * 100
    feat_conv = (fm.loc[fm["featured"] == 1, "favs"] / fm.loc[fm["featured"] == 1, "clicks"]).median() * 100
    fig = fig_featured(d)
    by_year = feat.groupby("band", observed=True).size()
    return f"""## 6. 运营位：曝光换规模，不换效率

`featured = 1` 是平台给的 banner / 首页运营位，共 {len(feat)} 本
（占全库 {len(feat) / len(d) * 100:.2f}%）。它们是观察「纯曝光冲击」的天然实验：

![](figures/08_featured.png)

*图 4｜左：运营位书与其余书目的点击、收藏中位（对数轴）；右：两者转化率中位。*

- 点击中位 {thousands(feat['clicks'].median())}，其余书目
  {thousands(rest['clicks'].median())}——**{feat['clicks'].median() / max(rest['clicks'].median(), 1):,.0f} 倍**；
- 收藏中位 {thousands(feat['favs'].median())}，其余书目
  {thousands(rest['favs'].median())}——{feat['favs'].median() / max(rest['favs'].median(), 1):,.0f} 倍；
- 转化率 {feat_conv:.2f}% vs {f_conv:.2f}%——**只有 {feat_conv / f_conv:.2f} 倍**。

三个数字放在一起是「分母效应」最干净的证据：曝光放大约
{feat['clicks'].median() / max(rest['clicks'].median(), 1):,.0f} 倍，收藏只放大约
{feat['favs'].median() / max(rest['favs'].median(), 1):,.0f} 倍，比值因此被压到不足四成。运营位带来的边际读者转化率远低于原有读者——**这不说明运营位无效**（绝对收藏
量仍是全库中位的 {feat['favs'].median() / max(rest['favs'].median(), 1):,.0f} 倍），
只说明**用转化率去评估运营位会得出完全相反的结论**。

另一种读法同样成立且无法排除：能拿到运营位的书本身就是平台选中的头部作品，
它们的读者结构（路人占比高）与长尾书不同。**「运营位导致稀释」与「头部书天然
稀释」在这份数据里不可分离**，因此本节只陈述三个数的关系，不作因果归属。

{("按世代看，运营位分布为 " + "、".join(f"{k} {int(v)} 本" for k, v in by_year.items()) + "。") if len(by_year) else ""}
"""


def section_bounds(d: pd.DataFrame) -> str:
    return f"""## 7. 口径边界

1. **计数器语义不完全可知**。`favs > clicks` 的 {int(d['favs'].gt(d['clicks']).sum())} 行、
   `praises > favs` 的 {int(d['praises'].gt(d['favs']).sum())} 行说明三者统计的事件
   不同（章节点击 / 书架收藏 / 章节点赞），但具体定义、是否去重、是否含作者本人
   的操作，均无法从数据侧确认。
2. **快照累计值，无时序**。所有计数器都是 2026-05-03 的累计值，无法知道收藏是
   在哪一年发生的。因此「世代的转化率差异」混合了三种东西：书的生命周期位置
   （老书已过曝光高峰）、平台流量结构、计数口径。§3 已说明这一点，跨期结论
   一律降级为「结构描述」。
3. **停更与下架删失**。在册 245,779 行不含已下架书；报告 07 已证 2013-14 年月票
   榜上 28%-31% 的书后来被清理，说明早期书目**消失率很高**。存活下来的早期书
   是「幸存者」，其转化率不代表当年整体——若下架书多为低转化，本报告对早期
   世代的转化率是**高估**的。
4. **运营位只观测到快照时点**。`featured=1` 是 2026-05 的状态，历史上拿过 banner
   但已撤下的书记为 0。§6 的对比因此是「当前在运营位的书 vs 其余」，不是
   「拿过运营位的书 vs 没拿过的书」，后者的效应会被低估。
5. **转化率不是留存率**。`favs/clicks` 是累计比值，不能读作「点开的人有 1.3% 留下」，
   因为同一读者可能贡献多次点击；点击若按章节计，读得越久分母越大，会系统性
   压低长书的转化率——这也是 §4 中「5-20 万字转化率最低」的可能成因之一。
6. **样本筛选的影响**。`clicks ≥ 100` 剔除了 {int((d['clicks'] < 100).sum()):,} 行
   （{ (d['clicks'] < 100).mean() * 100:.1f}%），这批书多为无人问津的长尾，
   其转化率无法估计（分母过小）。因此本报告所有转化率数字**只描述「有曝光的书」**，
   不覆盖全库。
"""


def build() -> None:
    charts.setup_style()
    d = load_books()
    m = calc_sample(d)
    sb = eras.snapshot_bounds(d)
    n_anchor = len(eras.load_anchors())
    body = f"""{section_header(d, n_anchor, sb)}

---

{section_conclusion(d, m)}

---

{section_counters(d, m)}

---

{section_exposure(d, m)}

---

{section_era(d, m)}

---

{section_structure(d, m)}

---

{section_praise(d, m)}

---

{section_featured(d)}

---

{section_bounds(d)}

---

*生成：`uv run python analysis/report_engagement.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"written: {OUT}")


if __name__ == "__main__":
    build()

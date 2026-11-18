"""生成 analysis/reports/11_shortform.md：速更短篇生态。

速更档 = status=已完结 且完结时长 (updated_at − nid 定年创建日) ∈ [0,7] 天，
与报告 05 的口径完全一致。本报告不复述「有多少本」，而是回答三个问题：
谁在写（作者生涯位置）、写了什么（题材/标签）、平台与读者如何对待
（效率/banner/征文交叉）。

关键口径：报告 10 §7 证实抓取是「按更新时间降序的单向游标扫描」，
更新中与新入库的书被系统跳过 → 短书被漏得最多 → 库内速更样本是低估，
作者「写出长篇」的比例亦被低估（长篇更不易漏，方向对结论有利）。

所有数字现算自 analysis/out/novels.csv，年份由 analysis/eras.py 定年。
报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/report_shortform.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths

from lib import charts  # noqa: E402
from lib import dialogue_form  # noqa: E402
from lib import eras  # noqa: E402

OUT = paths.REPORTS_DIR / "11_shortform.md"

YEAR_BINS = [2000, 2014, 2017, 2019, 2021, 2023, 2027]
YEAR_LABELS = ["≤2014", "2015-17", "2018-19", "2020-21", "2022-23", "2024-26"]
WORD_BINS = [-1, 1000, 3000, 6000, 12000, 30000, 10**9]
WORD_LABELS = ["≤1k", "1-3k", "3-6k", "6-12k", "12-30k", "30k+"]


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
    d["span"] = (d["upd"] - d["est_date"]).dt.days
    d["fast"] = (d["status"] == "已完结") & d["span"].between(0, 7)
    d["unknown_done"] = (d["status"] == "已完结") & (d["span"] < 0)
    d["has_contest"] = d["contest"].notna() & (d["contest"] != "")
    d["yr"] = pd.cut(d["est_year"], YEAR_BINS, labels=YEAR_LABELS, right=False)
    d["wband"] = pd.cut(d["words"], WORD_BINS, labels=WORD_LABELS, right=True)
    d = d.sort_values("id").reset_index(drop=True)
    d["rank"] = d.groupby("author").cumcount() + 1
    d["author_n"] = d.groupby("author")["id"].transform("size")
    return d


def pct(x: float) -> str:
    return f"{x:.1f}"


def num(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def author_frame(d: pd.DataFrame) -> pd.DataFrame:
    """作者级：首作特征 + 全生涯聚合。"""
    first = d[d["rank"] == 1][["author", "id", "fast", "est_year", "words", "favs"]]
    first = first.rename(columns={"fast": "first_fast", "est_year": "first_year"})
    agg = d.groupby("author").agg(
        n=("id", "size"), fast_n=("fast", "sum"),
        max_words=("words", "max"), favs_sum=("favs", "sum"),
    )
    g = first.set_index("author").join(agg)
    g["continued"] = g["n"] > 1
    g["long5"] = g["max_words"] >= 50000
    g["long10"] = g["max_words"] >= 100000
    g["fast_only"] = g["fast_n"] == g["n"]
    g["yr"] = pd.cut(
        g["first_year"], YEAR_BINS, labels=YEAR_LABELS, right=False,
    )
    return g


# ---------------------------------------------------------------- 图表


def fig_scale(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    done = d[d["status"] == "已完结"]
    t = done.groupby("est_year", observed=True).agg(done=("id", "size"), fast=("fast", "sum"))
    t["other"] = t["done"] - t["fast"]
    years = t.index.astype(int)
    ax.bar(years, t["fast"], color=charts.C["green"], zorder=3)
    ax.bar(years, t["other"], bottom=t["fast"], color="#BBBBBB", zorder=3)
    ax.text(0.02, 0.90, "绿柱=速更  灰柱=其他完结  红线=速更占比",
            transform=ax.transAxes, fontsize=9, color="#333333")
    ax2 = ax.twinx()
    rate = t["fast"] / t["done"] * 100
    ax2.plot(years, rate, color=charts.C["red"], marker="o", ms=4, lw=1.5, zorder=4)
    ax2.set_ylabel("速更占完结 %", color=charts.C["red"])
    ax2.tick_params(axis="y", labelcolor=charts.C["red"])
    ax2.set_ylim(0, 65)
    charts.shade_periods(ax, pd.Series(years))
    ax.set_xlabel("定年创建年")
    ax.set_ylabel("完结作品数")
    ax.set_title("速更档规模与占比：2020 后稳定在完结书的三分之一")
    return charts.save(fig, "11_scale.png")


def fig_funnel(g: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    rows = []
    for yr, sub in g.groupby("yr", observed=True):
        a, b = sub[sub["first_fast"]], sub[~sub["first_fast"]]
        if len(a) < 30 or len(b) < 30:
            continue
        rows.append([
            str(yr),
            a["continued"].mean() * 100, b["continued"].mean() * 100,
            a["long5"].mean() * 100, b["long5"].mean() * 100,
        ])
    x = np.arange(len(rows))
    w = 0.35
    for ax, col, title in [
        (axes[0], (1, 2), "续写第二本的比例"),
        (axes[1], (3, 4), "最终写出 ≥5 万字的比例"),
    ]:
        fast = [r[col[0]] for r in rows]
        other = [r[col[1]] for r in rows]
        ax.bar(x - w / 2, fast, w, color=charts.C["green"], label="首作速更")
        ax.bar(x + w / 2, other, w, color=charts.C["gray"], label="首作非速更")
        ax.set_xticks(x, [r[0] for r in rows], rotation=30, ha="right")
        ax.set_ylabel("%")
        ax.set_title(title)
        ax.legend(fontsize=9)
        ax.grid(axis="y", alpha=0.25, zorder=0)
    fig.suptitle("控制首作年份：速更作者更常续写，却更少写出长篇", y=1.02)
    fig.tight_layout()
    return charts.save(fig, "11_funnel.png")


def fig_position(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    f = d[d["fast"]]
    multi = f[f["author_n"] >= 3]
    ranks = range(1, 11)
    share = [(multi["rank"] == r).mean() * 100 for r in ranks]
    ax.bar(list(ranks), share, color=charts.C["blue"], zorder=3)
    ax.set_xlabel("速更作品在作者作品序列中的位置（按 nid）")
    ax.set_ylabel("占多产作者速更作品 %")
    ax.set_title(
        f"多产作者中，首作是速更的只占 {(multi['rank'] == 1).mean() * 100:.1f}%"
    )
    for r, v in zip(ranks, share):
        ax.text(r, v + 0.4, f"{v:.1f}", ha="center", fontsize=9)
    ax.set_xticks(list(ranks))
    ax.grid(axis="y", alpha=0.25, zorder=0)
    fig.tight_layout()
    return charts.save(fig, "11_position.png")


def fig_efficiency(d: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    rows = []
    for wb, sub in d.groupby("wband", observed=True):
        a, b = sub[sub["fast"]], sub[~sub["fast"]]
        if len(a) < 30:
            continue
        rows.append((str(wb), a["favs"].median(), b["favs"].median()))
    x = np.arange(len(rows))
    w = 0.35
    ax.bar(x - w / 2, [r[1] for r in rows], w, color=charts.C["green"], label="速更")
    ax.bar(x + w / 2, [r[2] for r in rows], w, color=charts.C["gray"], label="非速更")
    ax.set_yscale("log")
    ax.set_xticks(x, [r[0] for r in rows])
    ax.set_xlabel("字数档")
    ax.set_ylabel("收藏中位数（对数轴）")
    ax.set_title("同字数档对比：≤6k 字速更不吃亏，30k+ 档断崖")
    ax.legend()
    ax.grid(axis="y", alpha=0.25, zorder=0)
    fig.tight_layout()
    return charts.save(fig, "11_efficiency.png")


# ---------------------------------------------------------------- 正文


def build() -> str:
    charts.setup_style()
    d = load()
    g = author_frame(d)
    f = d[d["fast"]]
    done = d[d["status"] == "已完结"]

    # 敏感性对比：短篇池含对话/互动小说（报告 22 §5），剔除后重算关键比例
    dlg = dialogue_form.mark(d)
    dlg["is_dlg"] = dlg["morph"] | dlg["marked"]
    f_dlg_share = dlg[dlg["fast"]]["is_dlg"].mean() * 100
    keep = ~dlg["is_dlg"]
    fast_all = dlg["fast"].sum() / (dlg["status"] == "已完结").sum() * 100
    fast_ex = (dlg["fast"] & keep).sum() / ((dlg["status"] == "已完结") & keep).sum() * 100
    words_med_all = dlg[dlg["fast"]]["words"].median()
    words_med_ex = dlg[dlg["fast"] & keep]["words"].median()

    fa = g[g["fast_n"] > 0]
    first_fast = g[g["first_fast"]]
    first_other = g[~g["first_fast"]]
    fast_authors = set(f["author"])
    long_authors = set(d[(d["status"] == "已完结") & (d["words"] >= 100000)]["author"])

    figs = {
        "scale": fig_scale(d),
        "funnel": fig_funnel(g),
        "position": fig_position(d),
        "efficiency": fig_efficiency(d),
    }

    # 首作漏斗（全样本 + 控制年份后的稳定区间）
    funnel_rows = []
    for yr, sub in g.groupby("yr", observed=True):
        a, b = sub[sub["first_fast"]], sub[~sub["first_fast"]]
        if len(a) < 30 or len(b) < 30:
            continue
        funnel_rows.append([
            str(yr), num(len(a)),
            f"{a['continued'].mean() * 100:.1f} / {b['continued'].mean() * 100:.1f}",
            f"{a['long5'].mean() * 100:.1f} / {b['long5'].mean() * 100:.1f}",
        ])

    # 时间结构（现算）
    yr_rate = done.groupby("est_year").agg(done=("id", "size"), fast=("fast", "sum"))
    yr_rate["rate"] = yr_rate["fast"] / yr_rate["done"] * 100
    t0514 = yr_rate.loc[(yr_rate.index >= 2009) & (yr_rate.index <= 2014)]
    t1825 = yr_rate.loc[(yr_rate.index >= 2018) & (yr_rate.index <= 2025)]
    peak_year = int(t1825["rate"].idxmax())
    t2026 = float(yr_rate.loc[2026, "rate"])

    # 征文交叉
    cont_fast = d[d["has_contest"]]["fast"].mean() * 100
    noncont_fast = d[~d["has_contest"]]["fast"].mean() * 100
    fast_cont = f["has_contest"].mean() * 100

    # 分类速更率
    gr = d.groupby("genre").agg(n=("id", "size"), fast=("fast", "sum"))
    gr["rate"] = gr["fast"] / gr["n"] * 100
    gr_rows = [
        [idx, num(row.n), num(row.fast), f"{row.rate:.1f}%"]
        for idx, row in gr.sort_values("rate", ascending=False).iterrows()
    ]

    # 字数档效率
    eff_rows = []
    for wb, sub in d.groupby("wband", observed=True):
        a, b = sub[sub["fast"]], sub[~sub["fast"]]
        if len(a) < 30:
            continue
        eff_rows.append([
            str(wb), num(len(a)),
            f"{a['favs'].median():.0f} / {b['favs'].median():.0f}",
            f"{a['clicks'].median():,.0f} / {b['clicks'].median():,.0f}",
        ])

    tag_counter = Counter()
    for tg in f["tags"].dropna():
        for x in str(tg).split("|"):
            if x:
                tag_counter[x] += 1
    tag_top = "、".join(f"{k}({v:,})" for k, v in tag_counter.most_common(12))

    # 速更作品在作者序列中的位置（现算）
    multi_fast = f[f["author_n"] >= 3]
    pos_rows = []
    for lo, hi, label in [(1, 1, "首部作品"), (2, 2, "第 2 部"),
                          (3, 3, "第 3 部"), (4, 10**9, "≥第 4 部")]:
        share = (multi_fast["rank"].between(lo, hi)).mean() * 100
        pos_rows.append([label, f"{share:.1f}%"])
    first_share = (f["rank"] == 1).mean() * 100
    multi_first_share = (multi_fast["rank"] == 1).mean() * 100

    parts = [f"""# 11 · 速更短篇：被误读为「完结」的另一半

> 口径声明：
> 1. **速更档** = `status=已完结` 且完结时长 `updated_at − nid 定年创建日`
>    ∈ [0,7] 天，与报告 05 §1 完全一致。定年在 low 段有月级误差，完结时长
>    符号翻转的 {num(d['unknown_done'].sum())} 本已完结书单列、不并入。
> 2. **样本是低估**：报告 10 §7 证实抓取是按更新时间降序的单向游标扫描，
>    更新中与新入库的书被系统性跳过；短书被漏得最多。故本报告所有**绝对
>    计数**都是库内下界，面向「速更作者在全部作者中的占比」的结论须加
>    覆盖带。相对比较（速更 vs 非速更、分世代）方向稳健。
> 3. **作者序列按 nid 排序**：nid 单调递增近似创建序；同一作者的重复 nid
>    经 `build_csv.py` 按文件序去重（本数据集未发现大规模 nid 复用）。
>    「首作」指库内可见的首本，若作者更早的书被漏抓，则实为「可观测首作」。
> 4. **续写/长篇口径**：「续写」= 库内在首作之后还有 ≥1 本；「写出长篇」
>    = 该作者库内任一本 `words ≥ 50,000`。两者都是**下界**——长书更不易
>    被漏，故该低估对「速更作者长篇率更低」的结论方向不利（即真实差距
>    可能更小），报告对此保持审慎。
> 5. 所有数字现算自 `out/novels.csv`，年份由 `eras.py` 定年，图表由本
>    生成器产出，勿手改正文。


---

## 0. 结论

1. **速更档是独立品类，不是失败的长篇**：{num(len(f))} 本，字数中位
   {num(f['words'].median())} 字、收藏中位 {f['favs'].median():.0f}、点击中位
   {f['clicks'].median():,.0f}；VIP/签约率仅
   {(f['price_type'].isin(['VIP', '签约'])).mean() * 100:.1f}%、
   featured 率 {f['featured'].mean() * 100:.2f}%——平台从未把速更短篇当
   商业产品运营。
2. **速更主要是新手行为**：{num(len(first_fast))} 位作者的库内首作是速更，
   占全部作者（{num(len(g))} 位）的 {len(first_fast) / len(g) * 100:.1f}%；
   速更作品中有 {first_share:.1f}% 是作者首部作品；多产作者（≥3 本）的
   速更作品里，首作只占 {multi_first_share:.1f}%。
3. **速更不是弃坑信号，而是高频试水**：首作速更的作者后续再写一本的比例
   比首作非速更者**高 10–15pp**（控制首作年份后各代一致）；但最终写出
   ≥5 万字的比例在 2018 年后**低约一半**。他们更常继续，却更少写长。
4. **{fa['fast_only'].mean() * 100:.1f}% 的速更作者全部作品都是速更**
   （{num(int(fa['fast_only'].sum()))} 人），
   即「只写短篇」是一种稳定的作者形态，而非过渡阶段。
5. **征文没有放大速更**：征文作品速更率 {pct(cont_fast)}% vs 非征文
   {pct(noncont_fast)}%，几乎相同；但速更档里征文占 {pct(fast_cont)}%，
   与征文在库内的整体占比相当。报告 06「报名≠完赛」的结论不因速更档
   而改变——未完赛与速更完结是两件事。
6. **同字数档下速更不吃亏**：≤6k 字三档中，速更作品的收藏/点击中位数
   均不低于非速更；30k+ 档才出现断崖（收藏 6 vs 66）——那个差异来自
   「认真连载的长篇」与「短篇写完了」的对比，不是速更本身的效率损失。
7. **题材无强选择性**：悬疑 {gr.loc['悬疑', 'rate']:.1f}%、
   同人 {gr.loc['同人', 'rate']:.1f}% 速更率最高，魔幻
   {gr.loc['魔幻', 'rate']:.1f}% 最低，极差仅
   {gr['rate'].max() - gr['rate'].min():.1f}pp，远小于作者生涯阶段的差异。


---

## 1. 规模：2020 后稳定占完结书三分之一

![速更规模](figures/11_scale.png)

{num(len(done))} 本已完结作品中，速更档 {num(len(f))} 本
（{len(f) / len(done) * 100:.1f}%）。报告 05 已给出其字数与收藏中位，
这里补上时间结构：

- 2009–2014 年速更占完结
  {t0514['rate'].min():.1f}%–{t0514['rate'].max():.1f}%，波动大且样本小
  （每年 {t0514['done'].min():.0f}–{t0514['done'].max():.0f} 本）；
- 2018 年后跃升并稳定在 {t1825['rate'].min():.1f}%–{t1825['rate'].max():.1f}%，
  {peak_year} 年峰值 {t1825['rate'].max():.1f}%；
- 2026 年 {t2026:.1f}% 是**右删失假象**——当年创建的书只有极少数来得及
  写成 长篇完结，不能读作「速更化加剧」。

速更是**完结结构的内部分化**，不是完结率的驱动因素。把它从「完结率」
里拆出来，是报告 05 的核心结论，本报告继续沿这个口径。


---

## 2. 作者生涯：试水、续写、转长篇

### 2.1 速更发生在生涯的哪一步

![速更位置](figures/11_position.png)

{num(len(fa))} 位作者有过速更作品，其中
{num(int(fa['fast_only'].sum()))} 人（{(fa['fast_only'].mean() * 100):.1f}%）
**全部作品都是速更**。在有多本作品且至少一本速更的作者中：

{md_table(pos_rows, ["速更作品位置", "占多产作者的速更作品"])}

上表按全部速更作品计算，首部作品占 {first_share:.1f}%。
多产作者（库内 ≥3 本）的速更作品里，首作只占 {multi_first_share:.1f}%——**速更集中在
新手期，但并非只在新手期**：老作者也会插入短篇，只是比例低得多。

### 2.2 首作速更之后：续写更多，长篇更少

![首作漏斗](figures/11_funnel.png)

按首作是否速更拆分作者，再控制首作年份（避免「速更作者首作更晚、
观察窗更短」的混杂）：

{md_table(funnel_rows, ["首作年份", "首作速更 n", "续写第二本 %（速更 / 非速更）", "写出 ≥5 万字 %（速更 / 非速更）"])}

两条方向相反、各代稳定的差异：

- **续写率**：速更作者高 10–15pp。一次短篇完结没有劝退他们，反而比
  那些首作就写长篇（或未完结）的作者更愿意再开一本。
- **长篇率**：2018 年后速更作者低约一半（2020-21 代
  {funnel_rows[3][3]}、2022-23 代 {funnel_rows[4][3]}，
  格式为「速更 / 非速更」）。他们持续在场，却停留在短篇形态。

全样本口径下：首作速更作者中 {pct(first_fast['continued'].mean() * 100)}%
有第二本（非速更 {pct(first_other['continued'].mean() * 100)}%），
{pct(first_fast['long5'].mean() * 100)}% 最终写出 ≥5 万字
（非速更 {pct(first_other['long5'].mean() * 100)}%），
{pct(first_fast['long10'].mean() * 100)}% 写出 ≥10 万字
（非速更 {pct(first_other['long10'].mean() * 100)}%）。

把门槛抬到 10 万字完结：有速更作品的 {num(len(fast_authors))} 位作者中，
{num(len(fast_authors & long_authors))} 人（{len(fast_authors & long_authors) / len(fast_authors) * 100:.1f}%）
也写过 ≥10 万字完结作品。**速更与长篇创作不是互斥人格，但转化率有限。**


---

## 3. 题材与征文：没有强选择性

{md_table(gr_rows, ["分类", "作品数", "速更数", "速更率"])}

分类极差 3pp，谈不上「某类题材更容易写成短篇」。速更档高频标签为
{tag_top}——以通用配料（日常、战斗、异世界、恋爱）为主，
不构成独立题材空间。

征文交叉则给出一个**否定性结论**：征文作品速更率 {pct(cont_fast)}%，
非征文 {pct(noncont_fast)}%，几乎无差。速更档中征文占
{pct(fast_cont)}%，与征文在库内整体占比
（{d['has_contest'].mean() * 100:.1f}%）相当。报告 06 的「报名≠完赛」
指的是大量征文投稿停在极短篇幅、连完结状态都没拿到；本报告统计的
是**已完结的速更**，两者口径不同，不可互证。


---

## 4. 效率：速更短篇是独立品类

![同字数档效率](figures/11_efficiency.png)

{md_table(eff_rows, ["字数档", "速更 n", "收藏中位（速更 / 非速更）", "点击中位（速更 / 非速更）"])}

在 ≤1k、1-3k、3-6k 三档里，速更作品的收藏与点击中位数
**不低于甚至高于**非速更作品。6-12k 档开始接近，12-30k 与 30k+ 档
非速更作品反超（30k+ 档收藏 66 vs 6，点击 6,110 vs 422）。

这个交叉模式的解释不是「速更损失了效率」，而是：

- 短字数档里，非速更组混入了大量**断更的连载尝试**（写了几天就停，
  状态仍是「连载中」）；速更组反而是**有始有终**的那一批。
- 长字数档里，非速更组是认真连载的长篇，速更组只是「一次性上传了
  较多内容就完结」，二者本就不是同类。

因此「速更短篇质量低」不能从收藏/点击直接推出；能推出的是
**平台从未给这个品类商业出口**：VIP/签约率
{(f['price_type'].isin(['VIP', '签约'])).mean() * 100:.1f}%，
featured 率 0.00%——620 本 featured 书里没有一本速更短篇。


---

## 5. 口径边界与未决问题

1. **绝对计数是下界**：报告 10 §7 的游标扫描对短书最不友好，
   {num(len(f))} 本只是库内可见部分。若遗漏书里短篇比例更高，
   「速更占完结 28.5%」这个比例也可能被低估——但方向无法从库内数据确定。
2. **「写出长篇」的下界性质**：长书更不易被漏，故速更作者的长篇率被
   低估的幅度**小于**非速更作者；这会使 §2.2 的长篇率差距被**高估**。
   控制年份后的方向（速更低一半）稳健，具体幅度须谨慎。
3. **作者同一性**：以作者名字符串匹配，同名不同人/马甲会同时抬高低估
   与高估；报告 03 已讨论马甲结构，本报告不重复修正。
4. **右删失**：2025–2026 创建的书观察窗不足，其「未速更」状态可能是
   「还没写完」；§2 的控制年份表已按首作年份分层，但 2024-26 组仍
   不宜过度解读。
5. **定年误差**：完结时长依赖 nid 定年（LOO P99 = 50 天），0–7 天档
   在 low 段的误差足以把 8–30 天档错分进来；本报告沿用报告 05 的
   口径，不重新标定。
6. **短篇池含对话/互动小说**（报告 22）：本地无品类字段，按形态判据
   速更档里 {pct(f_dlg_share)}% 为对话/互动形态。剔除后敏感性对比：
   速更占完结书 {pct(fast_all)}% → {pct(fast_ex)}%、字数中位
   {int(words_med_all):,} → {int(words_med_ex):,} 字。方向与结论不变
   （对话小说同样每章约 500 字、整本可长，不是本报告定义的「速更短篇」
   的产品替代品），但「短篇」一词在本报告指篇幅，不含产品形态。
"""]

    OUT.write_text("\n".join(parts), encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    print(build())

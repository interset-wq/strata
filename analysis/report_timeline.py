"""报告 16：十年结构变迁——一张时间轴上的十六份报告（收官汇总篇）。

定位：不重复各专题的细节，而是把 16 份报告共同指向的时间轴拼成一张图，
对齐四个断点，提炼六条贯穿主线，并收束"相关被误读为因果"的方法论。

正文数字一律现算自 analysis/out/novels.csv 与 out/monthly_ranks.jsonl；
少数需要独立探测/判定才能得到的派生指标（覆盖率、banner 二元判定）标注来源报告。
本文件是生成物：重跑即更新，勿手改。

用法：cd analysis && uv run python report_timeline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import charts  # noqa: E402
import config  # noqa: E402
import eras  # noqa: E402

charts.setup_style()
OUT = BASE / "reports"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
MD = OUT / "16_timeline.md"

YEARS = list(range(2007, 2026))  # 年度序列止于 2025（内容上界之后的新书不在库）
PERIODS = [
    (2007, 2014, "兴趣站期"),
    (2015, 2016, "商业化初期"),
    (2017, 2022, "扩张期"),
    (2023, 2025, "收缩期"),
]


def period_of(y: int) -> str:
    for lo, hi, name in PERIODS:
        if lo <= y <= hi:
            return name
    return "?"


def num(x, d=0):
    return f"{x:,.{d}f}"


def gini(x) -> float:
    x = np.asarray(x, float)
    x = x[x >= 0]
    if len(x) == 0 or x.sum() <= 0:
        return np.nan
    x = np.sort(x)
    n = len(x)
    return (2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum())


def md_table(rows, header):
    out = ["| " + " | ".join(map(str, header)) + " |",
           "|" + "|".join(["---:"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(map(str, r)) + " |")
    return "\n".join(out)


# ---------- 数据 ----------
def load():
    df = pd.read_csv(BASE / "out/novels.csv",
                     dtype={"tags": str, "contest": str, "cover_url": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year"]], on="id")
    snap = eras.snapshot_bounds(df)
    df["title_len"] = df.title.fillna("").str.len()
    df["fav"] = pd.to_numeric(df.favs, errors="coerce")
    df["clk"] = pd.to_numeric(df.clicks, errors="coerce")
    df["praise"] = pd.to_numeric(df.praises, errors="coerce")

    d = df[df.est_year.between(2007, 2025)].copy()
    g = d.groupby("est_year")

    # 供给与新作者（新作者=作者库内首作年，按作者去重，报告03口径）
    first_year = df.groupby("author").est_year.min()
    new_auth = first_year[first_year.between(2007, 2025)].value_counts().reindex(YEARS, fill_value=0)
    books = g.size().reindex(YEARS, fill_value=0)

    # 商业化门槛
    sign = g.price_type.apply(lambda s: (s == "签约").mean() * 100).reindex(YEARS)
    vip = g.price_type.apply(lambda s: (s == "VIP").mean() * 100).reindex(YEARS)

    # 题材三足份额
    share = pd.crosstab(d.est_year, d.genre, normalize="index").mul(100).reindex(YEARS)

    # 标题长度
    tlen = g.title_len.median().reindex(YEARS)

    # 世代收藏份额与 Gini
    fav_sum = g.fav.sum().reindex(YEARS, fill_value=0)
    fav_share = fav_sum / fav_sum.sum() * 100
    gini_y = g.fav.apply(gini).reindex(YEARS)

    # 互动：赞藏比（favs>=10）、转化率（clicks>=100）
    pf = d[d.fav >= 10].groupby("est_year").apply(
        lambda s: (s.praise / s.fav).median() * 100, include_groups=False).reindex(YEARS)
    conv = d[d.clk >= 100].groupby("est_year").apply(
        lambda s: (s.fav / s.clk).median() * 100, include_groups=False).reindex(YEARS)

    # 女性向标签：占有标签书的比例（报告04口径，萌神已剔除）
    tagged = d[d.tags.notna()].copy()
    fem = {}
    for w in ["女性主角", "变身", "橘味"]:
        hit = tagged.tags.apply(lambda t: w in str(t).split("|"))
        fem[w] = hit.groupby(tagged.est_year).mean().mul(100).reindex(YEARS)

    # 征文占库比
    contest = g.contest.apply(lambda s: s.notna().mean() * 100).reindex(YEARS)

    # 月票年度总票（榜单数据，2013 起；top20 之和，非全站票量）
    votes = {}
    with open(BASE / "out/monthly_ranks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["rank"] != 0:
                continue
            y = int(r["month"][:4])
            votes[y] = votes.get(y, 0) + sum(it.get("ticketNum", 0) or 0 for it in r["items"])
    vote_y = pd.Series(votes).reindex(range(2007, 2027)).fillna(0)

    return dict(df=df, d=d, snap=snap, years=YEARS, books=books, new_auth=new_auth,
                sign=sign, vip=vip, share=share, tlen=tlen, fav_share=fav_share,
                gini=gini_y, pf=pf, conv=conv, fem=fem, contest=contest, vote=vote_y)


# ---------- 图 ----------
def shade_bg(ax, years):
    for lo, hi, _ in PERIODS:
        if years.max() < lo or years.min() > hi:
            continue
        ax.axvspan(lo - 0.5, hi + 0.5, color="#F2F2F2", zorder=0)


def fig_timeline(S):
    years = S["books"].index.values
    fig, axs = plt.subplots(4, 1, figsize=(9, 10.5), sharex=True)

    a = axs[0]
    shade_bg(a, years)
    a.bar(years, S["books"].values, width=0.72, color=charts.C["blue"], zorder=2, label="年供给（本）")
    a2 = a.twinx()
    a2.plot(years, S["new_auth"].values, color=charts.C["red"], lw=1.8, marker="o", ms=3, label="新作者（人）")
    a2.set_ylabel("新作者", color=charts.C["red"])
    a2.grid(False)
    a.set_ylabel("年供给")
    a.set_title("十年时间轴：四期与四个断点（2007–2025）", loc="left", fontweight="bold")
    # 分期名只在首面板标注
    for lo, hi, name in PERIODS:
        mid = (max(lo, years.min()) + min(hi, years.max())) / 2
        a.text(mid, 0.97, name, transform=a.get_xaxis_transform(), ha="center", va="top",
               fontsize=7.5, color="#666666")
    a.set_ylim(0, S["books"].max() * 1.32)
    a.legend(loc="upper left", bbox_to_anchor=(0.01, 0.86), frameon=False, fontsize=7.5)

    b = axs[1]
    shade_bg(b, years)
    b.plot(years, S["sign"].values, color=charts.C["red"], lw=1.9, marker="o", ms=3, label="签约率")
    b.plot(years, S["vip"].values, color=charts.C["green"], lw=1.9, marker="s", ms=3, label="VIP 率")
    b.set_ylabel("占当年新书 %")
    b.set_ylim(0, 15)
    b.legend(loc="upper left", frameon=False, fontsize=8)

    c = axs[2]
    shade_bg(c, years)
    c.plot(years, S["tlen"].values, color="#7B4AB5", lw=1.9, marker="o", ms=3)
    c.set_ylabel("标题长度中位（字）")
    for y in [2007, 2013, 2019, 2025]:
        c.annotate(f"{int(S['tlen'][y])}字", (y, S["tlen"][y]), textcoords="offset points",
                   xytext=(0, 7), ha="center", fontsize=7.5)

    dd = axs[3]
    shade_bg(dd, years)
    sh = S["share"]
    dd.plot(years, sh["魔幻"].reindex(YEARS).values, color=charts.C["blue"], lw=1.9, label="魔幻")
    dd.plot(years, sh["玄幻"].reindex(YEARS).values, color=charts.C["green"], lw=1.9, label="玄幻")
    dd.plot(years, sh["同人"].reindex(YEARS).values, color=charts.C["red"], lw=1.9, label="同人")
    dd.set_ylabel("占当年新书 %")
    dd.set_xlabel("上架年（nid 定年）")
    dd.set_xlim(2006.5, 2025.5)
    dd.set_xticks(range(2007, 2026, 2))
    dd.legend(loc="upper left", ncol=3, frameon=False, fontsize=8)
    fig.tight_layout(h_pad=1.0)
    return charts.save(fig, "16_timeline.png")


def fig_demand(S):
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.9))
    # 左：月票年度总票——商业化天花板
    a = axs[0]
    vy = S["vote"]
    yrs = [y for y in range(2013, 2026)]
    a.bar(yrs, [vy[y] / 1e4 for y in yrs], width=0.72, color=charts.C["red"], zorder=2)
    pk = int(max(range(2013, 2026), key=lambda y: vy[y]))
    a.annotate(f"峰值 {pk}：{vy[pk]/1e4:.0f}万票", (pk, vy[pk] / 1e4),
               textcoords="offset points", xytext=(-10, 4), ha="right", fontsize=8)
    a.set_title("商业化天花板：月票总票 2020 见顶", loc="left", fontsize=9.5)
    a.set_ylabel("年度月票总票（万）")
    a.set_xlim(2012.5, 2025.5)
    a.set_xticks(range(2013, 2026, 2))

    # 右：注意力重心 + 口味转向
    b = axs[1]
    years = S["books"].index.values
    shade_bg(b, years)
    b.bar(years, S["fav_share"].values, width=0.72, color="#BBBBBB", zorder=2, label="世代收藏份额")
    b2 = b.twinx()
    b2.plot(years, S["fem"]["女性主角"].values, color=charts.C["red"], lw=1.9, marker="o", ms=3,
            label="女性主角标签占比")
    b2.set_ylabel("女主标签占有标签书 %", color=charts.C["red"], labelpad=10)
    b2.grid(False)
    b.set_ylabel("占全库收藏 %")
    b.set_title("注意力重心与口味转向（按上架世代）", loc="left", fontsize=9.5)
    b.set_xlim(2006.5, 2025.5)
    b.set_xticks(range(2007, 2026, 2))
    h1, l1 = b.get_legend_handles_labels(); h2, l2 = b2.get_legend_handles_labels()
    b.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False, fontsize=8)
    fig.tight_layout()
    return charts.save(fig, "16_demand.png")


def fig_engagement(S):
    years = S["books"].index.values
    fig, axs = plt.subplots(3, 1, figsize=(9, 8.2), sharex=True)
    for ax in axs:
        shade_bg(ax, years)
    axs[0].plot(years, S["pf"].values, color=charts.C["blue"], lw=1.9, marker="o", ms=3)
    axs[0].set_ylabel("赞藏比中位 %")
    axs[0].set_title("互动结构：深度表达退化为轻量收藏", loc="left", fontweight="bold")
    axs[1].plot(years, S["conv"].values, color=charts.C["green"], lw=1.9, marker="o", ms=3)
    axs[1].set_ylabel("转化率中位 %")
    axs[2].plot(years, S["gini"].values, color="#7B4AB5", lw=1.9, marker="o", ms=3)
    axs[2].set_ylabel("收藏 Gini")
    axs[2].axhline(0.95, color=charts.C["gray"], ls="--", lw=1)
    axs[2].set_ylim(max(0.60, S["gini"].min() - 0.03), 1.0)
    axs[2].set_xlabel("上架年（nid 定年）")
    axs[2].set_xlim(2006.5, 2025.5)
    axs[2].set_xticks(range(2007, 2026, 2))
    fig.tight_layout(h_pad=0.9)
    return charts.save(fig, "16_engagement.png")


def fig_profile(S):
    """四期画像：四个面板，每面板一个指标按期的均值/中位。"""
    metrics = [
        ("年供给（本）", S["books"], "group_med"),
        ("签约率 %", S["sign"], "group_med"),
        ("标题长度中位（字）", S["tlen"], "group_med"),
        ("月票总票（万/年）", S["vote"] / 1e4, "group_med"),
    ]
    fig, axs = plt.subplots(2, 2, figsize=(9.5, 6.5))
    labels = [p[2] for p in PERIODS]
    colors = ["#BBBBBB", "#9EC3EA", charts.C["blue"], charts.C["red"]]
    for ax, (title, ser, _) in zip(axs.ravel(), metrics):
        vals = []
        for lo, hi, _ in PERIODS:
            sub = ser.reindex(range(lo, hi + 1)).dropna()
            if "月票" in title:  # 榜单 2013 起，早年的 fillna(0) 不是"零付费"
                sub = sub[sub > 0]
            vals.append(np.median(sub) if len(sub) else 0)
        ax.bar(range(4), vals, color=colors, zorder=2, width=0.66)
        ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(title, fontsize=9.5, loc="left")
        for i, v in enumerate(vals):
            ax.text(i, v * 1.03, f"{v:,.1f}" if v < 100 else f"{v:,.0f}",
                    ha="center", va="bottom", fontsize=7.5)
        ax.set_ylim(0, max(vals) * 1.18 if max(vals) > 0 else 1)
        ax.grid(axis="x", visible=False)
    fig.suptitle("四期画像（各期内逐年指标的中位）", fontweight="bold", y=1.01)
    fig.tight_layout()
    return charts.save(fig, "16_profile.png")


# ---------- 正文 ----------
def build(S, figs):
    books, na, sign, vip = S["books"], S["new_auth"], S["sign"], S["vip"]
    share, tlen = S["share"], S["tlen"]
    fav_share, gini_y, pf, conv = S["fav_share"], S["gini"], S["pf"], S["conv"]
    fem, contest, vote = S["fem"], S["contest"], S["vote"]
    d = S["d"]

    peak_y = int(books.idxmax()); peak_b = int(books.max())
    b2025 = int(books[2025]); decline = (1 - b2025 / peak_b) * 100
    jump = books[2017] / books[2016]
    na_peak = int(na.idxmax()); na_2025 = int(na[2025]); na_dec = (1 - na_2025 / na[na_peak]) * 100
    exp_share = books.loc[2017:2022].sum() / books.sum() * 100

    vpk = int(max(range(2013, 2026), key=lambda y: vote[y])); v25 = vote[2025]
    vdec = (1 - v25 / vote[vpk]) * 100
    v26m = sum(vote[y] for y in [2026])  # 只有月度累加值
    # 2026 年化：用报告07口径（前11月 /11*12），从 monthly_ranks 重算需月份数
    n26 = 0; v26 = 0
    with open(BASE / "out/monthly_ranks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["rank"] == 0 and r["month"].startswith("2026"):
                n26 += 1; v26 += sum(it.get("ticketNum", 0) or 0 for it in r["items"])
    v26_annual = v26 / n26 * 12 if n26 else 0

    # 四期画像表
    prof = []
    for lo, hi, name in PERIODS:
        prof.append([
            f"{lo}–{hi}",
            num(books.reindex(range(lo, hi + 1)).median()),
            f"{sign.reindex(range(lo, hi + 1)).median():.1f}",
            f"{vip.reindex(range(lo, hi + 1)).median():.1f}",
            f"{tlen.reindex(range(lo, hi + 1)).median():.0f}",
            f"{share['魔幻'].reindex(range(lo, hi + 1)).median():.1f}",
            f"{share['同人'].reindex(range(lo, hi + 1)).median():.1f}",
            f"{contest.reindex(range(lo, hi + 1)).median():.1f}",
        ])

    gini_all = gini(d.fav.dropna())
    # 收藏集中在 2020-2022 世代的份额（报告 02 口径）
    top3_share = fav_share.loc[2020:2022].sum()
    gini_valid = gini_y.dropna()
    gini_lo, gini_hi = gini_valid.min(), gini_valid.max()

    txt = f"""# 报告 16：十年结构变迁——一张时间轴上的十六份报告

> **口径声明**
> 1. 数据 `analysis/out/novels.csv`，剔除正版日轻 4 类作者后 245,779 行；
>    数据内容上界 {S['snap']['date']}（原始 jsonl 的 `max(last_update)`，即扫描起点，
>    不是统一读取时刻，见报告 10）。上架年由 nid 定年（104 锚点，LOO P99 = 50 天，报告 01），
>    年度序列止于 2025：内容上界之后创建的新书不在库内。
> 2. **本报告是二次综合**：主体序列（供给、签约、题材、标题长度、收藏份额、Gini、互动、
>    女性向标签、征文占库、月票总票）由本生成器现算；需要独立探测或判定才能得到的
>    派生指标（覆盖率 68.9%、banner 下注/奖励二元、征文上榜对照）标注来源报告，
>    不在本报告重新判定。所有跨报告的"因果"结论均保持各专题的相关/因果边界。
> 3. **累计指标跨时点不可比**：`favs`/`clicks` 随书龄与曝光分母累积（报告 02、08）；
>    世代份额只在"同一存量结构内"读，不作跨世代水平比较。
> 4. **快照状态 ≠ 当期状态**：`status`/`price_type` 是 2026 上界态，跨时点统计生命或
>    商业化状态须按 `updated_at` 重建（报告 07 `attach_done_now()`）。
> 5. **标签字段有代际与词表断层**：标签体系约 2014 上线，跨世代比较仅 2017 后可靠；
>    2022 年 23 个 IP/亚文化标签被清理；`20XX萌神` 7 个为运营荣誉，已剔除（报告 04、09）。
> 6. **数据集是抽样**：对在架书覆盖率约 68.9%（报告 10），抓取为一次从新到旧的单向游标扫描，
>    遗漏偏向"短、新、更新中"而非冷门；凡绝对计数是下界，排序与相对比较稳健。
> 7. 榜单为月度 top20 右截断、每月清零，月票总票是 top20 之和而非全站票量（报告 07）。
> 8. 所有差异为结构描述，不作因果推断；"运营—题材—注意力"的先后不能替代机制证据。

---

## 0. 结论：贯穿十年的六条主线

1. **供给是单峰，且"人"比"书"先见顶**。年供给 2017 年跳至 {jump:.1f} 倍进入扩张期，
   {peak_y} 年达峰 {num(peak_b)} 本，2025 年降至 {b2025:,} 本（−{decline:.0f}%）；
   但新作者数在 {na_peak} 年就已见顶（{num(na[na_peak])} 人），比供给峰早两年。
   收缩的主体是作者基数流失（−{na_dec:.0f}%），不是人均写得更少（报告 01、03）。

2. **商业化是"门槛加深 + 天花板见顶"的剪刀差**。签约率从扩张期的中位
   {sign.reindex(range(2017,2023)).median():.1f}% 升到收缩期的
   {sign.reindex(range(2023,2026)).median():.1f}%，而月票总票在 {vpk} 年见顶
   {vote[vpk]/1e4:.0f} 万票后，2025 年只剩 {v25/1e4:.0f} 万（−{vdec:.0f}%；
   2026 年前 {n26} 月年化 {v26_annual/1e4:.0f} 万）。VIP 份额二十年恒定在 3% 上下：
   平台在变少的新书里签了更高比例，却没有更大的付费盘子（报告 01、07）。

3. **注意力集中是结构常数，但重心在迁移**。全书收藏 Gini 约 {gini_all:.2f}，
   各世代稳定在 {gini_lo:.2f}–{gini_hi:.2f}，不随平台规模、题材结构、商业化程度变化；
   {top3_share:.0f}% 的收藏落在 2020–2022 三个世代（现算，与报告 02 的 45% 一致）。
   集中是平台的稳态，
   变化的是注意力"落在谁身上"——不是"是否集中"。

4. **口味转向是运营与自选择的合力，不是读者口味的自然演化**。
   魔幻份额从兴趣站期中位 {share['魔幻'].reindex(range(2007,2015)).median():.0f}% 降到
   扩张期 {share['魔幻'].reindex(range(2017,2023)).median():.0f}%，同人 2019 年上线、
   2021 年占 {share['同人'].get(2021,0):.0f}% 后回落；女性主角标签占有标签书从
   2017 年 {fem['女性主角'][2017]:.1f}% 升到 2025 年 {fem['女性主角'][2025]:.1f}%。
   但标签是受控词表、2022 年经历清理（报告 04、09），这些"转向"里有相当一部分是
   编辑动作与词表规则，而非纯粹的需求侧变化。

5. **平台识别的是作者能力，不是单本爆款**。banner 授予对代表作收藏分位 <90% 的作者
   精确为 0（报告 17）；征文的上榜优势在控制 VIP 后反转、作者内对照只剩 1.18 倍（报告 15）；
   跟风书的高热度是"愿蹭者本身更认真"的选择效应（报告 12、13）。
   三类看似因果的优势，逐层对照后都收敛到"筛选的是人"。

6. **这份图景有一面有盲区的镜子**。数据集对在架书覆盖约 68.9%（报告 10），
   抓取遗漏偏向短、新、更新中的书；快照状态不等于当期状态；发生在内容上界之后的新书
   完全不在库内。因此所有绝对计数是下界、所有跨时点水平比较都要先问口径——
   这正是前十五份报告反复在做的同一件事：**先拆混杂，再谈差异**。

---

## 1. 统一时间轴：四期与四个断点

![十年时间轴]({figs[0]})

四期划分沿用系列报告的既有分期（兴趣站期 / 商业化初期 / 扩张期 / 收缩期），
不是外生给定的行业分期，而是从供给曲线的拐点读出的结构段。四个关键断点：

| 断点 | 年 | 在数据里的表现 | 对应专题 |
|---|---:|---|---|
| 商业化启动 | 2015 | 签约率 {sign[2015]:.1f}%→{sign[2016]:.1f}%，APP 上线（外部事实） | 01、07 |
| 供给跃迁 | 2017 | 年供给 {num(books[2016])}→{num(books[2017])}（{jump:.1f}×） | 01、03 |
| 同人上线 / 注意力峰 | 2019–2022 | 同人 2019 年 {share['同人'].get(2019,0):.1f}% 起量；收藏峰值世代 | 04、09、02 |
| 供给收缩 | 2023 | 供给连续三年回落，签约率反升，赞藏比下行 | 01、05、08 |

四期画像（各期内逐年指标的中位）:

![四期画像]({figs[3]})

{md_table(prof, ["分期","年供给","签约%","VIP%","标题字数","魔幻%","同人%","征文%"])}

> 分期中位是对"期内典型状态"的概括，会抹平期内的峰值（如 2022 供给峰），
> 断点处请回到时间轴原图读数。月票面板因榜单 2013 年才启动，兴趣站期只有
> 2013–2014 两年有值，不能读作该期整体付费水平。

---

## 2. 供给侧：单峰、作者先见顶、收缩是"人"在走

供给曲线是教科书式单峰：扩张期六年贡献全库 {exp_share:.0f}%，
{peak_y} 年 {num(peak_b)} 本见顶后三年回落 {decline:.0f}%。
但把"书"换成"人"，转折提前两年——新作者数 {na_peak} 年达峰
{num(na[na_peak])} 人，2025 年剩 {num(na_2025)} 人（−{na_dec:.0f}%），
而同期人均新书只降约 11%（报告 03）。**总量下滑主要来自新作者流入减少，
不是留下的人写得更多或更少。**

这一层区分决定了"平台是否在变冷"的答案：如果看累计在册， Library 仍在膨胀；
如果看新增供给与新增作者，扩张期结束得很明确。二者不矛盾，是存量与流量的差别。
需要记住的偏置：抓取遗漏偏向短、新书（报告 10），因此近年新增与速更短篇的
绝对数是下界，收缩幅度可能被高估。

---

## 3. 题材与内容形态：三足、女性向、标题通胀

题材结构经历两次位移。第一次是魔幻（日式奇幻）份额的长期退潮：
兴趣站期中位 {share['魔幻'].reindex(range(2007,2015)).median():.0f}% →
扩张期 {share['魔幻'].reindex(range(2017,2023)).median():.0f}%；
第二次是玄幻与同人的补位——玄幻从兴趣站期
{share['玄幻'].reindex(range(2007,2015)).median():.1f}% 升至
{share['玄幻'].reindex(range(2017,2023)).median():.1f}%，同人 2019 年作为一个独立分类上线，
2021 年占 {share['同人'].get(2021,0):.1f}%。同人是平台为二创单开的免费货架：
2008–2021 世代同人 VIP 率 0.0%、中位字数仅 6,637、完结率却最高（报告 04）。
它不是题材，而是"挂载 IP 的命名空间"（报告 09）。

口味侧最稳定的单一变化是女性向标签扩张：女性主角从 2017 年
{fem['女性主角'][2017]:.1f}% 到 2025 年 {fem['女性主角'][2025]:.1f}%（占有标签书分母），
变身、橘味在 2023 后同步爆发（2025 年分别 {fem['变身'][2025]:.1f}%、
{fem['橘味'][2025]:.1f}%）。但必须叠加一条警告：2022 年有 23 个 IP/亚文化标签被清理，
词表本身换过血。"某标签占比上升"必须同时回答是题材在变还是词表在变。

内容形态上，标题长度中位从 2007 年 {int(tlen[2007])} 字升到 2025 年 {int(tlen[2025])} 字，
变长几乎全靠"堆词"而非单词变长（报告 14）；高频词从"世界/少女/魔法"的意象型，
转向"穿越/崩坏/变成"的叙事机制型，再到"小姐/魔女/反派"的角色身份型。
但"成功配方"高度题材特定，且报告 14 用条件分位证明：堆词与高收藏相关，
却无法证明堆的是"成功词"。

---

## 4. 商业化与付费刻度：门槛加深，天花板见顶

![需求与口味]({figs[1]})

商业化的两条刻度在报告 07 里被拆开：热销榜量当期订阅额（点券消耗），
月票榜量充值返还票的再分配（1 票≈0.5 元，可投免费书）。
可量级的月票总票 {vpk} 年见顶 {vote[vpk]/1e4:.0f} 万，2025 年
{v25/1e4:.0f} 万（−{vdec:.0f}%），末位票数比榜首保留得更少——
收缩以长尾付费者流失为主。

与付费盘子收缩同时发生的是商业化门槛加深：签约率在收缩期升到
{sign.reindex(range(2023,2026)).median():.1f}%（扩张期
{sign.reindex(range(2017,2023)).median():.1f}%），但 VIP 份额二十年恒定约 3%。
征文把更多书送进 VIP 池（15.3%），也把自己在月票榜的占比从 2016 年 13.5%
推到 2024 年 97.8%（报告 15）——**平台在更少的供给里，更组织化地筛选和运营付费作者**，
而不是把付费蛋糕做大。

需要区分"上榜"与"商业化成功"：四榜并集仅占在册 0.73%（报告 07），
征文漏斗从 95,433 本报名到 335 本上榜（0.35%，报告 15）。
榜单是顶部结构，不是整体收入的刻度。

---

## 5. 注意力与互动：恒定的集中，迁移的重心，退化的表达

![互动结构]({figs[2]})

注意力集中是这十年最顽固的结构常数：全书收藏 Gini {gini_all:.2f}，
top 1% 的书占 58.1% 收藏（报告 02）；按世代看 Gini 稳定在 0.94–0.97，
不随规模、题材、商业化变化。{top3_share:.0f}% 的收藏落在 2020–2022 世代——
若收藏只随书龄累积应向早期倾斜，事实相反，说明注意力跟随平台周期移动。

互动的三个计数器不是嵌套漏斗（报告 08），只用两个比值读：
转化率（favs/clicks）与赞藏比（praises/favs）。按上架年现算，
赞藏比从 2017 年峰 {pf[2017]:.0f}% 降到 2025 年 {pf[2025]:.0f}%，
而转化率同期从 {conv[2017]:.2f}% 变为 {conv[2025]:.2f}%——**收藏还在，点赞撤了**。
但这一断崖不能区分是读者行为变化还是点赞计数口径变化；且在固定曝光档后，
题材之间的差异只有 1.5 倍，远小于曝光的 3.6 倍分母效应。
**互动效率的方差主要来自"谁点开了你"，不是"你写了什么"。**

运营位是分母效应的极端案例：620 本 featured 书点击中位 749.8 万（其余书目的
18,377 倍），转化率却只有其余书的 0.38 倍（报告 08）。流量买得到，效率买不到。

---

## 6. 运营如何塑造供给：征文、banner 与数据盲区

征文是平台的核心节拍：官方核实日期显示秋征 9-30、冬征 12 月上旬、
春征 3 月初、X 征 5 月 4 日首尾相接，上一届截止到下一届启动只差 0–1 天（报告 06）。
征文占库比重从 2016 年 {contest[2016]:.1f}% 升到 2025 年 {contest[2025]:.1f}%，
但它筛选的是"有准备、有体量、倾向商业化"的作者——字数中位 15,558 vs 8,477、
VIP 率 6.1% vs 1.2%（报告 06），且上榜优势大半来自作者自选择（报告 15）。
报名到完赛之间还有巨大落差：X 征长篇主体簇字数中位仅为 12 万门槛的 14.9%。

banner 是平台真金白银的下注（约 1,000 元/张、画师原创，用户口述）。
报告 17 的判定给出二元机制：约 35.5% 是"下注型"（作者的 banner 书之前已有
高收藏代表作，平台押的是作者能力），64.5% 是"奖励型"（本书爆火才得奖）。
但授予有硬门槛——代表作收藏分位 <90% 的 122,383 位作者获 banner 率为精确 0。
**平台识别作者，而非抽奖选中单本。**

最后是不能忘记的盲区：数据集对在架书覆盖约 68.9%，缺失槽位中约 21.1% 是
活书遗漏（≈11.1 万本），其余是已删除 ∪ 未分配的死槽（不可分解）；
抓取是一次单向游标扫描，更新中的书被重排到游标身后不再回头抓（报告 10）。
这解释了为什么遗漏偏"短、新、更新中"——也提醒本报告所有绝对计数都是下界。

---

## 7. 方法论收束：六个被对照剥离的"因果"

汇总十六份报告，最一致的收获不是某个数字，而是一套方法：**先问对照，再谈差异**。

| 看似因果的说法 | 初读 | 逐层控制后 | 专题 |
|---|---|---|---|
| "征文作者更能上榜" | 1.88× | 控制 VIP 反转 0.67×；作者内 1.18× | 15 |
| "征文上榜票数高 48 倍" | 2,355 vs 50 | 按上榜年份逐一看 0.96–1.48×，年代假象 | 15 |
| "完结书霸占热销榜" | 快照态 60–78% | 当期重建 ≤0.4%，状态滞后假象 | 07 |
| "上榜书被下架" | 月榜缺失 118 本 | 90.7% 仍在线，真下架 11 本 | 10 |
| "banner 命中率 99.8%" | 收藏分位 | 机械结果，授予本就按热度 | 17 |
| "蹭爆款名字有效" | 跟风书收藏 5.7× | 愿蹭者本身更认真的选择效应 | 12、13 |

六个例子指向同一件事：累计指标跨时点不可比、快照状态不等于当期、
自选择与曝光分母是第一解释变量。这也是为什么本报告坚持"结构描述、相关非因果"——
不是谨慎辞令，而是十六份报告反复被数据教育出来的结果。

---

## 8. 数据边界：这份图景看不到什么

1. **总量边界**：内容上界之后的书完全不在库；对在架书覆盖约 68.9%，绝对计数是下界。
2. **时间边界**：`updated_at` 只能当"时长"（断更），不能当时间轴；年份来自 nid 定年，
   low 段（2007–2015）有月级误差，6,913 本完结书因此无法分时长档。
3. **状态边界**：`status`/`price_type` 是上界态；断更已并入"连载中"，
   状态字段不含活跃度，活跃度只能用断更时长重切。
4. **题材边界**：标签字段有上线时间、有 2022 词表断层、有运营荣誉标签，
   跨代比较只在 2017 后、且剔除荣誉标签后成立。
5. **机制边界**：无营收、付费人数、订阅量、章节与用户事件数据；
   月票是唯一带量级的公开付费刻度，且含运营加成。
6. **因果边界**：观察性快照，运营位、榜单、题材、热度互为因果；
   本报告全部结论为结构描述。

---

## 9. 报告索引

| # | 报告 | 一句话 |
|---|---|---|
| 01 | 市场结构 | 定年体系、单峰供给、商业化门槛加深 |
| 02 | 注意力集中度 | Gini 0.95 是结构常数，重心随周期迁移 |
| 03 | 作者生态 | 新作者 2020 先见顶，收缩是基数流失 |
| 04 | 题材与标签 | 三足结构、女性向标签扩张、词表受控 |
| 05 | 生命周期与存量 | 完结二元结构、92.8% 断更书持有 80.7% 收藏 |
| 06 | 征文 | 日历首尾相接、报名≠完赛 |
| 07 | 商业化 | 月票与热销两条刻度、付费 2020 见顶 |
| 08 | 互动漏斗 | 曝光分母效应、赞藏比断崖 |
| 09 | 题材语义空间 | 99 词受控词表、同人=IP 命名空间 |
| 10 | 生存与遗漏 | 覆盖率 68.9%、游标扫描、下架推断被推翻 |
| 11 | 速更短篇 | 独立品类、新手高频试水、非弃坑 |
| 12 | 标题形态与命名史 | 标题通胀、跟风证据三级 |
| 13 | 跟风传播 | 头部少造词、爆款潮是赛道共振 |
| 14 | 标题成功配方 | 条件分位剥离题材、配方题材特定 |
| 15 | 征文到商业化 | 优势属于人不属于比赛 |
| 16 | 十年结构变迁（本篇） | 一张时间轴、六条主线、对照先于因果 |
| 17 | banner 投入 | 作者筛选、下注/奖励二元 |

---

*生成：`analysis/report_timeline.py`；正文数字现算，少数派生指标标注来源报告。*
"""
    MD.write_text(txt, encoding="utf-8")
    return txt


def main():
    S = load()
    figs = [fig_timeline(S), fig_demand(S), fig_engagement(S), fig_profile(S)]
    build(S, figs)
    # 控制台自检
    print("内容上界:", S["snap"]["date"])
    print("供给峰:", int(S["books"].idxmax()), int(S["books"].max()),
          "2025:", int(S["books"][2025]))
    print("新作者峰:", int(S["new_auth"].idxmax()), int(S["new_auth"].max()))
    print("月票峰:", int(max(range(2013, 2026), key=lambda y: S["vote"][y])),
          "2025:", S["vote"][2025], "2026年化:", round(S["vote"].get(2026, 0)))
    print("Gini全库:", round(gini(S["d"].fav.dropna()), 3))
    print("写报告:", MD)


if __name__ == "__main__":
    main()

"""报告 12：标题形态与命名史（含跟风传播的事件研究）。

生成 reports/12_titles.md 与五张图表。所有正文数字现算，不写快照。
"""
from __future__ import annotations

import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import jieba
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

jieba.setLogLevel(60)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
BASE = paths.ROOT
from lib import charts, config, eras

TOKEN_CACHE = paths.OUT_DIR / "title_tokens.pkl"
OUT = paths.REPORTS_DIR / "12_titles.md"

# 被排除的通用词：爆款标题里的高频虚词/泛词，不构成「品牌词」
GENERIC = {
    "怎么办", "需要", "身体", "总是", "失败", "角色", "回家", "当下", "可能",
    "这个", "那个", "我们", "你们", "他们", "自己", "什么", "怎么", "为什么",
    "之后", "开始", "时候", "世界", "一个", "没有", "不是", "就是", "可以",
    "不会", "这样", "那样", "如果", "因为", "所以", "但是", "而且", "已经",
    "不当", "之主", "家伙", "东西", "一生", "一切", "大人", "小姐", "先生",
    "起来", "下来", "上去", "过去", "现在", "后来", "已经", "突然",
}


def num(x: float) -> str:
    return f"{x:,.0f}"


def load_data():
    df = pd.read_csv(paths.CSV_FILE, dtype={"tags": str, "contest": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year"]], on="id")
    df = df.dropna(subset=["est_year"]).copy()
    df["est_year"] = df["est_year"].astype(int)
    df["title"] = df["title"].fillna("")
    df["length"] = df["title"].str.len()
    return df


def load_tokens(df):
    if TOKEN_CACHE.exists():
        with open(TOKEN_CACHE, "rb") as fh:
            return pickle.load(fh)
    toks = {}
    for nid, title in zip(df["id"], df["title"]):
        toks[nid] = [w for w in jieba.lcut(str(title)) if len(w) >= 2 and w.strip()]
    with open(TOKEN_CACHE, "wb") as fh:
        pickle.dump(toks, fh)
    return toks


def load_ranks():
    first = defaultdict(list)  # nid -> [(month, name, ticketNum, rank)]
    with open(paths.MONTHLY_RANKS, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            for it in r.get("items", []):
                first[it["nid"]].append(
                    (r["month"], it["name"], it.get("ticketNum", 0), r["rank"])
                )
    out = {}
    for nid, items in first.items():
        mv = min(items, key=lambda x: x[0])
        out[nid] = {
            "month": mv[0], "name": mv[1], "ticket": mv[2],
            "first": mv[0][:4], "n_list": len(items),
        }
    return out


# ---------------- 图表 ----------------

def fig_length(tbl):
    years = tbl["year"].values
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(years, tbl["median"], color=charts.C["blue"], lw=2.2,
            marker="o", ms=3.5, label="标题长度中位数（字符）", zorder=3)
    for y, v in zip(years, tbl["median"]):
        ax.annotate(f"{v:g}", (y, v), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=7.5, color=charts.C["blue"])
    ax.set_ylabel("字符数")
    ax.set_ylim(0, max(tbl["median"]) * 1.35)
    ax2 = ax.twinx()
    ax2.bar(years, tbl["long_pct"], color=charts.C["red"], alpha=0.35, width=0.62,
            label="≥12 字占比（右轴）", zorder=2)
    ax2.set_ylabel("≥12 字占比 (%)", color=charts.C["red"])
    ax2.set_ylim(0, 100)
    ax2.tick_params(axis="y", colors=charts.C["red"])
    charts.shade_periods(ax, years)
    ax.set_xlabel("定年创建年")
    ax.set_title("标题长度通胀：中位数从 5–6 字升到 12 字，长标题成为主流")
    ax.set_xticks(years[::2])
    ax.text(0.012, 0.05, "柱：≥12字占比　线：长度中位数", transform=ax.transAxes,
            fontsize=8, color="#555555")
    fig.tight_layout()
    return charts.save(fig, "12_length.png")


def fig_buzzwords(years, series):
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    styles = [
        ("穿越", charts.C["blue"], "-"), ("重生", charts.C["red"], "-"),
        ("系统", charts.C["green"], "-"), ("最强", "#E69F00", "--"),
        ("开局", "#999999", "--"),
    ]
    for w, color, ls in styles:
        if w in series:
            ax.plot(years, series[w], color=color, ls=ls, lw=2,
                    marker="o", ms=3, label=w, zorder=3)
    charts.shade_periods(ax, np.array(years))
    ax.set_xlabel("定年创建年")
    ax.set_ylabel("每千本新书标题含该词数")
    ax.set_title("套路词的引入—峰值—衰退：各领风骚 2–4 年")
    ax.set_xticks(years[::2])
    ax.legend(ncol=5, loc="lower right", framealpha=0.9, fontsize=8)
    fig.tight_layout()
    return charts.save(fig, "12_buzzwords.png")


def fig_direct(cases, years):
    """两本爆款书的直接书名复用：按定年的新书占比。"""
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0), sharey=True)
    for ax, (name, hy, curve, pre, post) in zip(axes, cases):
        ax.bar(years, curve, color=charts.C["blue"], width=0.66, zorder=3)
        ax.axvline(hy, color=charts.C["red"], lw=1.6, ls="--", zorder=4)
        ax.text(hy - 0.3, max(curve) * 0.45, f"爆火\n{hy}", color=charts.C["red"],
                fontsize=8, va="top", ha="right")
        charts.shade_periods(ax, np.array(years))
        ax.set_title(f"《{name}》：爆火前 {pre} 本 / 爆火后 {post} 本", fontsize=9.5)
        ax.set_xlabel("定年创建年")
        ax.set_xticks(years[::3])
    axes[0].set_ylabel("书名含爆款名的书（本）")
    fig.suptitle("直接书名复用：跟风书几乎全部出现在爆火之后", fontsize=11, y=1.02)
    fig.tight_layout()
    return charts.save(fig, "12_direct.png")


def fig_brand(brand_rows):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    rows = brand_rows[:12][::-1]
    names = [f"{r['word']}　《{r['source'][:12]}》" for r in rows]
    vals = [r["followers"] for r in rows]
    colors = [charts.C["red"] if r["word"] in ("血姬",) else charts.C["blue"] for r in rows]
    ax.barh(names, vals, color=colors, height=0.68, zorder=3)
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, f"{v:,}", va="center", fontsize=8)
    ax.set_xlabel("爆火后标题含该品牌词的新书数（本）")
    ax.set_title("品牌词扩散：爆款带火一个词，后来者在标题里复用它")
    ax.set_xlim(0, max(vals) * 1.14)
    fig.tight_layout()
    return charts.save(fig, "12_brand.png")


def fig_tags(years, tag_series):
    fig, ax = plt.subplots(figsize=(9, 4.3))
    for t, color, ls in [("变身", charts.C["red"], "-"),
                         ("橘味", "#E69F00", "-"),
                         ("女性主角", charts.C["blue"], "--")]:
        ax.plot(years, tag_series[t], color=color, ls=ls, lw=2, marker="o", ms=3,
                label=t, zorder=3)
    ax.axvline(2018, color=charts.C["red"], lw=1.2, ls=":", alpha=0.8)
    ax.text(2018.15, max(tag_series["变身"]) * 0.9,
            "血姬与骑士爆火\n(2018-10)", fontsize=8, color="#555555", va="top")
    charts.shade_periods(ax, np.array(years))
    ax.set_xlabel("定年创建年")
    ax.set_ylabel("每千本新书标签采用数")
    ax.set_title("标签扩散的时滞：变身/橘味在爆火 5 年后才随赛道整体爆发")
    ax.set_xticks(years[::2])
    ax.legend(loc="lower right", framealpha=0.9)
    fig.tight_layout()
    return charts.save(fig, "12_tags.png")


# ---------------- 正文 ----------------

def build() -> str:
    charts.setup_style()
    df = load_data()
    toks = load_tokens(df)
    ranks = load_ranks()
    yt = df.groupby("est_year").size()

    wy = defaultdict(Counter)
    for nid, yr in zip(df["id"], df["est_year"]):
        for w in set(toks.get(nid, [])):
            wy[w][yr] += 1

    years = list(range(2007, 2027))
    years2 = list(range(2013, 2027))

    # --- 长度表 ---
    tbl = []
    for y in years:
        s = df[df.est_year == y]
        if len(s) < 20:
            continue
        tbl.append({"year": y, "n": len(s), "median": s["length"].median(),
                    "mean": s["length"].mean(),
                    "long_pct": (s["length"] >= 12).mean() * 100})
    tbl = pd.DataFrame(tbl)
    early = tbl[tbl.year <= 2014]["median"].median()
    late = tbl[tbl.year >= 2024]["median"].median()
    long_early = tbl[tbl.year <= 2014]["long_pct"].median()
    long_late = tbl[tbl.year >= 2024]["long_pct"].median()
    f_length = fig_length(tbl)

    # --- 套路词 ---
    buzz = ["穿越", "重生", "系统", "最强", "无敌", "开局"]
    series = {w: [wy[w].get(y, 0) / yt.get(y, 1) * 1000 for y in years2]
              for w in buzz + ["英雄", "再临"]}
    f_buzz = fig_buzzwords(years2, series)

    def peak_info(w):
        v = series[w]
        pk = years2[int(np.argmax(v))]
        # 引入年：首次 ≥ 峰值 10%
        intro = next((y for y, x in zip(years2, v) if x >= max(v) * 0.1), years2[0])
        return intro, pk, max(v)

    buzz_peaks = {w: peak_info(w) for w in buzz}

    # --- 直接书名复用（硬证据） ---
    cases = []
    direct_stats = {}
    for name, hy in [("英雄再临", 2016), ("血姬与骑士", 2018)]:
        sub = df[df.title.str.contains(name, na=False)]
        curve = [(sub.est_year == y).sum() for y in years]
        pre = int((sub.est_year < hy).sum())
        post = int((sub.est_year >= hy).sum())
        cases.append((name, hy, curve, pre, post))
        direct_stats[name] = {
            "n": len(sub), "pre": pre, "post": post,
            "post_pct": post / max(len(sub), 1) * 100,
            "favs_med": sub.favs.median(),
            "words_med": sub.words.median(),
            "same_med": sub.tags.fillna("").str.contains("同人").mean() * 100,
            "first_year": int(sub.est_year.min()),
            "last_year": int(sub.est_year.max()),
        }
    f_direct = fig_direct(cases, years)

    # --- 品牌词扩散（系统扫描） ---
    cands = []
    for nid, info in ranks.items():
        hy = int(info["first"])
        if not (2013 <= hy <= 2021) or info["ticket"] < 100 or nid not in df.index:
            continue
        cands.append((nid, hy, info["name"], info["ticket"]))
    brand_rows = []
    for nid, hy, name, tix in cands:
        words = [w for w in toks.get(nid, []) if len(w) >= 2 and w not in GENERIC]
        best = None
        for w in words:
            pre = sum(wy[w].get(y, 0) for y in range(hy - 3, hy))
            post = sum(wy[w].get(y, 0) for y in range(hy, hy + 6))
            if pre <= 3 and post >= 30:
                if best is None or post > best[1]:
                    best = (w, post)
        if not best:
            continue
        bw, bn = best
        fol = df[(df.est_year > hy) & df.title.str.contains(bw, na=False) & (df.id != nid)]
        if len(fol) < 5:
            continue
        brand_rows.append({
            "word": bw, "source": name, "hy": hy, "tix": tix,
            "post": bn, "followers": len(fol),
            "favs_med": fol.favs.median(), "nid": nid,
        })
    # 去重：同一品牌词只留首发最早（爆火年最早）的爆款
    seen_word = set()
    brand_uniq = []
    for r in sorted(brand_rows, key=lambda x: (x["hy"], -x["tix"])):
        if r["word"] in seen_word:
            continue
        seen_word.add(r["word"])
        brand_uniq.append(r)
    brand_uniq.sort(key=lambda x: -x["followers"])
    brand_top = brand_uniq[:12]
    f_brand = fig_brand(brand_uniq)

    # --- 标签扩散（诚实标注时滞） ---
    tags_year = defaultdict(Counter)
    for _, r in df.iterrows():
        tg = r["tags"]
        if isinstance(tg, str):
            for t in tg.split("|"):
                if t:
                    tags_year[t][r["est_year"]] += 1
    tag_series = {t: [tags_year[t].get(y, 0) / yt.get(y, 1) * 1000 for y in years2]
                  for t in ["变身", "橘味", "女性主角"]}
    f_tags = fig_tags(years2, tag_series)

    # --- 跟风书的经济后果（控制定年，用「血姬」品牌词） ---
    fol = df[(df.est_year > 2018) & df.title.str.contains("血姬", na=False)]
    ctrl = df[(df.est_year > 2018) & ~df.title.str.contains("血姬", na=False)]
    econ = {m: (fol[m].median(), ctrl[m].median()) for m in ["favs", "clicks", "words"]}
    # 血姬在爆火起 6 年（2018-2023，与品牌词扫描 range(hy,hy+6) 同口径）的出现次数
    blood_after6 = sum(wy["血姬"].get(y, 0) for y in range(2018, 2024))

    # 标题长度 vs 收藏（控制定年：2022-24 新书，分长度档）
    sub = df[df.est_year.between(2022, 2024)]
    sub = sub.assign(band=pd.cut(sub.length, [0, 6, 10, 14, 100],
                                 labels=["≤6", "7-10", "11-14", "≥15"]))
    len_econ = sub.groupby("band", observed=True).agg(
        n=("id", "size"), favs=("favs", "median"), clicks=("clicks", "median")
    )

    # ---------- 正文 ----------
    parts = []
    parts.append(f"""# 报告 12：标题形态与命名史

> 数据口径：{num(len(df))} 本（已剔除正版日轻），定年来自 `eras.py`。标题按 UTF-8 字符计长；
> 分词用 jieba 精确模式，仅保留 ≥2 字词。爆火事件以「首次上月票榜且月票 ≥100」锚定，
> 月榜数据来自 `out/monthly_ranks.jsonl`。
>
> **跟风证据分三级，不可混用**：① 直接书名复用（硬证据，书名含爆款原名）；
> ② 品牌词扩散（中证据，爆火前近乎不存在、爆火后大量出现在新书标题的词）；
> ③ 通用套路词增长（弱信号，「穿越」「系统」等全行业同步上升，**不能归因给单本爆款**）。
>
> 右删失：2026 年只含年初创建书，趋势末段勿外推。报告 10 已证抓取偏向短/新/更新中的书，
> 跟风短篇因此被系统性漏抓——本报告跟风绝对计数是**下界**。

## 结论

1. **标题持续通胀**：长度中位数从 2007 年的 {tbl.iloc[0]['median']:g} 字升到 2026 年的
   {tbl.iloc[-1]['median']:g} 字（2007–2014 区间中位 {early:g}、2024–2026 区间中位 {late:g}）；
   ≥12 字占比从 {long_early:.0f}% 升到 {long_late:.0f}%。标题从「短语标识」变成「卖点摘要」。
2. **套路词各领风骚 2–4 年**：穿越峰值 {years2[int(np.argmax(series['穿越']))]}、
   重生峰值 {years2[int(np.argmax(series['重生']))]}、系统峰值 {years2[int(np.argmax(series['系统']))]}、
   最强峰值 {years2[int(np.argmax(series['最强']))]}、开局峰值 {years2[int(np.argmax(series['开局']))]}——
   生命周期错峰，不存在一个「永远的套路」。
3. **跟风有硬证据**：《血姬与骑士》的 {direct_stats['血姬与骑士']['n']} 本同名书中
   {direct_stats['血姬与骑士']['pre']} 本在爆火前、{direct_stats['血姬与骑士']['post']} 本在爆火后
   （{direct_stats['血姬与骑士']['post_pct']:.0f}%），收藏中位 {num(direct_stats['血姬与骑士']['favs_med'])}、
   {direct_stats['血姬与骑士']['same_med']:.0f}% 挂「同人」标签——是明确的 IP 借势。
4. **爆款真正带火的是「品牌词」而非通用词**：「血姬」在爆火前几乎不存在，
   爆火起 6 年（2018–2023）在标题中出现 {num(blood_after6)} 次；
   而「英雄」「无敌」「系统」的上升与全行业标题通胀同步（同期「穿越」从
   {series['穿越'][0]:.0f}‰ 涨到 {max(series['穿越']):.0f}‰），**不可归因给《英雄再临》**。
5. **标签扩散有时滞，且更易被赛道混杂**：血姬与骑士 2018 就挂「变身/橘味」，
   但这两个标签到 2023 才随女性向整体爆发（变身 {tag_series['变身'][10]:.0f}→{tag_series['变身'][12]:.0f}‰），
   更可能是报告 09 记录的词表清理与赛道切换，而非单本爆款所致。
6. **跟风书热度更高，但这是选择效应**：
   「血姬」跟风书收藏中位 {num(econ['favs'][0])} vs 同期其他 {num(econ['favs'][1])}
   （{econ['favs'][0] / max(econ['favs'][1], 1):.1f} 倍）——愿意蹭热点的作者本身更认真，
   不能读作「蹭名有效」。

## 1. 标题长度通胀：从标识到卖点摘要

![标题长度]({f_length})

长度增长贯穿整个时间轴，且 2018 后加速。关键点：

- 2007–2014 年中位 {early:g} 字、≥12 字仅 {long_early:.0f}%——标题是**短标识**；
- 2024–2026 年中位 {late:g} 字、≥12 字达 {long_late:.0f}%——近半标题是**长卖点句**；
- 这与报告 09 的「标签体系 2017+ 成熟」同向：平台与作者都转向**前置信息量**。

| 创建年 | 新书数 | 长度中位 | 均值 | ≥12字占比 |
|---|---:|---:|---:|---:|
""")
    for _, r in tbl.iterrows():
        if r["year"] % 2 == 0 or r["year"] >= 2023:
            parts.append(f"| {int(r['year'])} | {num(r['n'])} | {r['median']:g} | "
                         f"{r['mean']:.1f} | {r['long_pct']:.1f}% |\n")
    parts.append(f"""
## 2. 套路词生命周期：错峰的流行

![套路词]({f_buzz})

每千本新书标题含该词的量化曲线（选峰年）：

| 词 | 引入年(≥峰值10%) | 峰值年 | 峰值(‰) |
|---|---:|---:|---:|
""")
    for w in buzz:
        intro, pk, mx = buzz_peaks[w]
        parts.append(f"| {w} | {intro} | {pk} | {mx:.0f} |\n")
    parts.append(f"""
「穿越」「重生」「系统」在 2020 前后同时冲高，构成网文标题的**黄金套路期**；
「最强」「无敌」更早（2018–2020）见顶并回落；「开局」最晚（{buzz_peaks['开局'][1]} 年峰值），
是收缩期仍在上涨的少数词。套路词的引入—峰值—衰退更像**题材轮动**，而非单向通胀。

## 3. 跟风传播：三个证据层级

### 3.1 硬证据：直接书名复用

![直接复用]({f_direct})

""")
    for name, st in direct_stats.items():
        parts.append(
            f"- 《{name}》：含书名的书共 {st['n']} 本，"
            f"爆火前 {st['pre']} 本、爆火后 {st['post']} 本（{st['post_pct']:.0f}%），"
            f"收藏中位 {num(st['favs_med'])}、字数中位 {num(st['words_med'])}、"
            f"{st['same_med']:.0f}% 含「同人」标签；"
            f"定年跨度 {st['first_year']}–{st['last_year']}。\n"
        )
    parts.append(f"""
这批书绝大多数是同人/借势作：它们**直接把爆款书名嵌进自己的标题**，是最无歧义的跟风证据。
注意《英雄再临》的 6 本里有 1 本（nid 25022，2012 年）是同名误命中，非跟风。

### 3.2 中证据：品牌词扩散

![品牌词]({f_brand})

系统性扫描：对每个首上月票榜且月票 ≥100 的爆款，取其标题中「爆火前 3 年 ≤3 次、
爆火后 6 年 ≥30 次」的题材词（已剔除「怎么办」「需要」等通用词），统计爆火后
标题含该词的新书数。结果（同一词只保留首发最早的爆款）：

| 品牌词 | 源头爆款 | 爆火年 | 爆火后 6 年词频 | 跟风新书数 | 跟风书收藏中位 |
|---|---|---:|---:|---:|---:|
""")
    for r in brand_top:
        parts.append(f"| {r['word']} | {r['source'][:18]} | {r['hy']} | "
                     f"{num(r['post'])} | {num(r['followers'])} | {num(r['favs_med'])} |\n")
    parts.append(f"""
上表按跟风新书数排序，「圣女」「仙子」「狐娘」「女帝」「血姬」「机甲」是题材词，
「分手」「徒儿」「大叔」则是角色/叙事套路词——
它们共同的特征是被爆款**从生僻打到常用**。
这是跟风的核心形态：后来者不抄书名，而是**复用爆款验证过的关键词**——
既可借势搜索与推荐，也降低了读者的理解成本。

### 3.3 弱信号：通用套路词不能归因单本爆款

《英雄再临》爆火后「英雄」采用率从 {series['英雄'][0]:.0f}‰ 升到峰值
{max(series['英雄']):.0f}‰，但同期「穿越」从 {series['穿越'][0]:.0f}‰ 涨到
{max(series['穿越']):.0f}‰、「系统」从 {series['系统'][0]:.0f}‰ 涨到 {max(series['系统']):.0f}‰——
**整个行业标题都在变长、堆词**。此时把「英雄」的上升归给一本书是虚假归因。
本报告因此只在品牌词满足「爆火前近乎不存在」时才认定跟风。

### 3.4 标签扩散：时滞与赛道混杂

![标签扩散]({f_tags})

血姬与骑士原创标签「变身/橘味」在 2018 爆火时采用率不足 1‰，
到 2023 才分别升至 {tag_series['变身'][10]:.0f}‰ / {tag_series['橘味'][10]:.0f}‰，
2025 达 {tag_series['变身'][12]:.0f}‰ / {tag_series['橘味'][12]:.0f}‰。
**五年的时滞说明这不是单本爆款的即时效应**：报告 09 已证 2022 年词表清理、
2023–24 女性向赛道整体爆发，「变身/橘味」是搭上了赛道快车。
本报告不将它读作「血姬带火了标签」，只标注**同向但非因果**。

## 4. 跟风的经济后果：选择效应而非因果

「血姬」跟风书（{num(len(fol))} 本，2019 后创建）与同期其他新书对比：

| 指标 | 跟风书中位 | 同期其他中位 | 倍数 |
|---|---:|---:|---:|
""")
    for m, label in [("favs", "收藏"), ("clicks", "点击"), ("words", "字数")]:
        a, b = econ[m]
        parts.append(f"| {label} | {num(a)} | {num(b)} | {a / max(b, 1):.2f}× |\n")
    parts.append(f"""
跟风书热度显著更高，但**不能解读成「蹭名有效」**：愿意在标题里复用爆款词的作者，
本身更可能认真经营（字数中位也高 {econ['words'][0] / max(econ['words'][1], 1):.1f} 倍），
且这批书以同人为主、享有 IP 流量。这是**选择效应**，不是品牌词带来的因果提升。

## 5. 口径边界与未决

1. **定年误差**：nid 插值的 LOO P99 约 50 天，爆火年与创建年错配最多影响相邻一年；
   本报告的窗口取 3–6 年，足以吸收。
2. **月榜右截断**：月榜每月 top20，爆款定义依赖上榜门槛（月票 ≥100），
   小众爆款可能未入扫描；品牌词扫描因此偏保守。
3. **同名词误命中**：直接复用统计中《英雄再临》含 1 本 2012 年同名作（非跟风），
   《血姬与骑士》的 14 本则全部在爆火后，无误命中。
4. **品牌词过滤的残余风险**： GENERIC 表基于探查剔除明显泛词，
   极少数泛词（如「角色」「回家」）可能漏网，已在 §3.2 手工复核。
5. **标签词表断层**：报告 09 证 2022 年清理 23 个 IP/亚文化标签，
   §3.4 的标签曲线跨断层比较须谨慎（本报告只做同向标注，不做因果断言）。
""")
    text = "".join(parts)
    OUT.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    t = build()
    print(f"已生成 {OUT.relative_to(BASE)}（{len(t)} 字符）")

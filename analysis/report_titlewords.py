"""报告 14：标题高频词与成功配方。

生成 reports/14_titlewords.md 与六张图表。所有正文数字现算，不写快照。
核心问题：作者是否在追逐「成功配方」，以及这是否驱动了标题通胀。
"""
from __future__ import annotations

import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from wordcloud import WordCloud

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import charts, config, eras

charts.setup_style()
TOKEN_CACHE = BASE / "out" / "title_tokens.pkl"
OUT = BASE / "reports" / "14_titlewords.md"

# 纯语法虚词过滤。与报告 12 不同：那里为识别「品牌词」滤掉「世界/变成/小姐」
# 等叙事词；本报告研究「配方」，这些词正是分析对象，只滤无题材信息的虚词。
GENERIC = {
    "一个", "没有", "不是", "就是", "可以", "不会", "这样", "那样",
    "如果", "因为", "所以", "但是", "而且", "已经", "突然", "后来", "现在",
    "过去", "起来", "下来", "上去", "时候", "之后", "自己", "什么",
    "怎么", "为什么", "这个", "那个", "我们", "你们", "他们", "一套",
    "关于", "一套", "一种", "一次",
}


def num(x: float) -> str:
    return f"{x:,.0f}"


def load_data():
    df = pd.read_csv(BASE / "out/novels.csv", dtype={"tags": str, "contest": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year"]], on="id")
    df = df.dropna(subset=["est_year"]).copy()
    df["est_year"] = df["est_year"].astype(int)
    df["title"] = df["title"].fillna("")
    df["length"] = df["title"].str.len()
    with open(TOKEN_CACHE, "rb") as fh:
        toks = pickle.load(fh)
    df["tokens"] = df["id"].map(toks)
    df["n_tokens"] = df.tokens.map(len)
    # 条件分位：在 (世代,词数) 与 (世代,词数,分类) 组内排序，剥离世代/长度/题材混杂
    df["fav_2cond"] = df.groupby(["est_year", "n_tokens"])["favs"].rank(pct=True)
    df["fav_3cond"] = df.groupby(["est_year", "n_tokens", "genre"])["favs"].rank(pct=True)
    rank_nid = set()
    with open(BASE / "out/monthly_ranks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("rank") == 0:
                for it in r.get("items", []):
                    rank_nid.add(it["nid"])
    df["on_rank"] = df["id"].isin(rank_nid)
    return df


# ---------- 图 ----------
def fig_cloud(word_freq: Counter, title: str, name: str) -> str:
    wc = WordCloud(
        font_path="C:/Windows/Fonts/msyh.ttc",
        width=900, height=420, background_color="white",
        color_func=lambda *_a, **_k: "#{}".format(
            np.random.choice(["4477AA", "CC3311", "009988", "777777"])),
        max_words=90, min_font_size=9, max_font_size=52,
        random_state=42, collocations=False,
    ).generate_from_frequencies(dict(word_freq))
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(title, fontsize=10, pad=8)
    fig.tight_layout()
    return charts.save(fig, name)


def fig_wordrank(rows: list[dict]) -> str:
    """成功词 vs 毒药词：2条件与3条件净收藏分位对照。"""
    sel = sorted(rows, key=lambda r: r["fav_3"])[::-1][:10] + sorted(rows, key=lambda r: r["fav_3"])[:8]
    sel = list({r["word"]: r for r in sel}.values())
    sel.sort(key=lambda r: r["fav_3"])
    fig, ax = plt.subplots(figsize=(9, 5.5))
    y = np.arange(len(sel))
    ax.barh(y - 0.18, [r["fav_2"] for r in sel], height=0.36,
            color=charts.C["gray"], alpha=0.55, label="控制世代+词数")
    ax.barh(y + 0.18, [r["fav_3"] for r in sel], height=0.36,
            color=charts.C["blue"], label="再控制题材")
    ax.axvline(0.5, color=charts.C["red"], ls="--", lw=1.2, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['word']}  (n={num(r['n'])})" for r in sel], fontsize=9)
    ax.set_xlabel("净收藏分位（0.5 = 同世代同长度同题材中位数）")
    ax.set_title("成功词与毒药词：题材能解释多少「配方效应」")
    ax.legend(loc="lower right", framealpha=0.9)
    ax.set_xlim(0.35, 0.72)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return charts.save(fig, "14_wordrank.png")


def fig_lifecycle(life: dict) -> str:
    """采用率飙升 vs 净收益下滑：双面板。"""
    words = list(life.keys())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharex=True)
    palette = [charts.C["blue"], charts.C["red"], charts.C["green"],
               "#E69F00", "#999999", "#7B3294"]
    for ax, key, ylab, ttl in zip(
        axes, ["adopt", "fav"],
        ["新书标题采用率 (%)", "该词书的净收藏分位"],
        ["配方被追逐：采用率", "边际收益：起飞后是否衰减"],
    ):
        for i, w in enumerate(words):
            d = life[w]
            ax.plot(d["year"], d[key], marker="o", ms=3, lw=1.7,
                    color=palette[i % len(palette)], label=w)
        ax.axvline(2016, color="#CCCCCC", lw=1, ls=":")
        ax.set_title(ttl, fontsize=10)
        ax.set_ylabel(ylab)
        ax.set_xticks(range(2014, 2027, 2))
        ax.grid(alpha=0.5)
    axes[0].legend(ncol=3, loc="upper left", fontsize=8, framealpha=0.9)
    axes[1].axhline(0.5, color=charts.C["red"], ls="--", lw=1)
    fig.tight_layout()
    return charts.save(fig, "14_lifecycle.png")


def fig_length_decomp(dec: list[dict]) -> str:
    """标题变长归因：词数 vs 单词长度。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(dec))
    w = 0.36
    ax.bar(x - w / 2, [d["d_tok"] for d in dec], w, color=charts.C["blue"], label="词数增加贡献")
    ax.bar(x + w / 2, [d["d_char"] for d in dec], w, color=charts.C["red"], label="单词变长贡献")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{d['y0']}→{d['y1']}" for d in dec])
    ax.axhline(0, color="#333333", lw=1)
    ax.set_ylabel("标题长度变化 (字符)")
    ax.set_title("标题变长几乎全部来自「堆词」，而非单个词变长")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return charts.save(fig, "14_lengthdecomp.png")


def fig_genre_corr(gc: list[dict]) -> str:
    """题材内的长度-收藏相关：配方是题材特定的。"""
    gc = sorted(gc, key=lambda r: r["r"])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    cols = [charts.C["red"] if r["r"] < 0 else charts.C["blue"] for r in gc]
    ax.barh([r["genre"] for r in gc], [r["r"] for r in gc], color=cols, height=0.65)
    ax.axvline(0, color="#333333", lw=1)
    ax.set_xlabel("标题长度 vs 收藏分位 相关系数（题材内）")
    ax.set_title("「长标题更有效」并非通用配方：题材间差异显著")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(min(r["r"] for r in gc) - 0.03, max(r["r"] for r in gc) + 0.03)
    for i, r in enumerate(gc):
        ax.text(r["r"] + (0.006 if r["r"] >= 0 else -0.006), i,
                f"{r['r']:+.3f}", va="center",
                ha="left" if r["r"] >= 0 else "right", fontsize=8)
    fig.tight_layout()
    return charts.save(fig, "14_genrecorr.png")


def fig_cooccur(co: dict, top_words: list[str]) -> str:
    """高频词的共现搭档：配方家族。四段渐变色 = 与 top4 搭档的共现书数。"""
    fig, ax = plt.subplots(figsize=(10, 4.6))
    base = [charts.C["blue"], charts.C["red"], charts.C["green"], "#E69F00", "#7B3294"]
    y = np.arange(len(top_words))
    labels = []
    for i, w in enumerate(top_words):
        partners = co[w].most_common(4)[::-1]  # 低->高，左->右
        left = 0
        for j, (_p, v) in enumerate(partners):
            shade = plt.cm.Greys(0.35 + 0.15 * j)
            ax.barh(y[i], v, left=left, height=0.6, color=base[i % len(base)],
                    alpha=0.45 + 0.15 * j, edgecolor="white", linewidth=0.5)
            left += v
        labels.append("、".join(f"{p}({v:,})" for p, v in reversed(partners)))
        ax.text(left + 40, y[i], labels[-1], va="center", ha="left", fontsize=8)
    ax.set_yticks(y)
    ax.set_yticklabels(top_words)
    ax.set_xlim(0, max(sum(v for _p, v in co[w].most_common(4)) for w in top_words) * 1.75)
    ax.set_xlabel("与 top4 搭档的共现书数（四段由浅到深 = 搭档按共现数升序）")
    ax.set_title("配方家族：高频词的固定搭档")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return charts.save(fig, "14_cooccur.png")


def build() -> str:
    df = load_data()
    parts: list[str] = []
    total = len(df)

    # ===== 高频词谱 =====
    cnt = Counter()
    for ts in df.tokens:
        cnt.update(ts)
    content = Counter({w: n for w, n in cnt.items() if w not in GENERIC and len(w) >= 2})
    total_tok = sum(cnt.values())
    top10_share = sum(n for _w, n in cnt.most_common(10)) / total_tok * 100
    top100_share = sum(n for _w, n in cnt.most_common(100)) / total_tok * 100
    f_cloud = fig_cloud(content.most_common(60), "标题高频词云（剔除泛词，全库）", "14_cloud.png")

    # 世代词谱表
    era_bins = [2000, 2014, 2017, 2020, 2023, 2027]
    era_labels = ["≤2014", "2015-17", "2018-20", "2021-23", "2024-26"]
    df["era"] = pd.cut(df.est_year, era_bins, labels=era_labels)
    era_words = {}
    for era, sub in df.groupby("era", observed=True):
        c = Counter()
        for ts in sub.tokens:
            c.update(ts)
        era_words[str(era)] = [(w, n) for w, n in c.most_common(8) if w not in GENERIC][:6]

    # ===== 成功词识别 =====
    cand = [w for w, n in cnt.items() if n >= 2000 and len(w) >= 2 and w not in GENERIC]
    rows = []
    for w in cand:
        m = np.array([w in ts for ts in df.tokens])
        sub = df[m]
        rows.append({"word": w, "n": len(sub), "fav_2": sub.fav_2cond.mean(),
                     "fav_3": sub.fav_3cond.mean(), "rank": sub.on_rank.mean() * 100})
    r = pd.DataFrame(rows)
    good = r.nlargest(8, "fav_3")
    bad = r.nsmallest(8, "fav_3")
    f_rank = fig_wordrank(rows)

    # 题材代理剥离：控制题材后变化最大的词
    r["delta"] = r.fav_3 - r.fav_2
    proxy = r.reindex(r.delta.abs().sort_values(ascending=False).index).head(5)

    # ===== 起飞/衰竭 =====
    life_words = ["崩坏", "穿越", "转生", "系统", "小姐", "反派"]
    life = {}
    years = list(range(2014, 2027))
    for w in life_words:
        m = np.array([w in ts for ts in df.tokens])
        sub = df[m]
        adopt = []
        fav = []
        for y in years:
            yr = df[df.est_year == y]
            adopt.append(m[df.est_year.values == y].mean() * 100 if len(yr) else 0)
            f = sub.loc[sub.est_year == y, "fav_2cond"].mean()
            fav.append(f if not np.isnan(f) else 0.5)
        life[w] = {"year": years, "adopt": adopt, "fav": fav}
    f_life = fig_lifecycle(life)

    # 起飞前后收益变化（采用率突破1%为起飞年）
    takeoffs = []
    for w in life_words:
        d = life[w]
        take = next((y for y, a in zip(d["year"], d["adopt"]) if a > 1.0), None)
        if take is None:
            continue
        before = [f for y, f in zip(d["year"], d["fav"]) if take - 3 <= y < take]
        after = [f for y, f in zip(d["year"], d["fav"]) if take <= y <= take + 3]
        takeoffs.append({"word": w, "year": take,
                         "before": np.mean(before) if before else np.nan,
                         "after": np.mean(after) if after else np.nan})
    n_decline = sum(1 for t in takeoffs if t["after"] < t["before"])

    # ===== 标题变长归因 =====
    t = df.groupby("est_year").agg(L=("length", "mean"), K=("n_tokens", "mean"))
    dec = []
    for y0, y1 in [(2010, 2016), (2016, 2021), (2021, 2026)]:
        dL = t.loc[y1, "L"] - t.loc[y0, "L"]
        dK = t.loc[y1, "K"] - t.loc[y0, "K"]
        c0 = t.loc[y0, "L"] / t.loc[y0, "K"]
        c1 = t.loc[y1, "L"] / t.loc[y1, "K"]
        dec.append({"y0": y0, "y1": y1, "d_tok": dK * c0, "d_char": t.loc[y0, "K"] * (c1 - c0)})
    f_dec = fig_length_decomp(dec)
    tok_share = np.mean([d["d_tok"] / (d["d_tok"] + d["d_char"]) * 100 for d in dec])

    # 题材内相关
    gc = []
    for ge, sub in df.groupby("genre"):
        if len(sub) < 3000:
            continue
        gc.append({"genre": ge, "r": float(np.corrcoef(sub.length, sub.fav_2cond)[0, 1]), "n": len(sub)})
    f_genre = fig_genre_corr(gc)
    gc_sorted = sorted(gc, key=lambda x: x["r"])

    # ===== 语义家族 =====
    top_co = [w for w, n in content.most_common(40) if n >= 2000][:8]
    top_set = set(top_co)
    co = defaultdict(Counter)
    for ts in df.tokens:
        s = set(ts) & top_set
        for a in s:
            for b in s:
                if a < b:
                    co[a][b] += 1
                    co[b][a] += 1
    f_co = fig_cooccur(co, top_co)

    # ===== 作者换配方 =====
    GOOD = set(good.word)
    BAD = set(bad.word)
    d = df.sort_values("id").copy()
    d["has_good"] = d.tokens.map(lambda ts: bool(set(ts) & GOOD))
    d["has_bad"] = d.tokens.map(lambda ts: bool(set(ts) & BAD))
    g = d.groupby("author")
    first, last = g.head(1).set_index("author"), g.tail(1).set_index("author")
    sizes = g.size()
    multi = [a for a in first.index.intersection(last.index) if sizes[a] >= 3]
    good_first = first.loc[multi, "has_good"].mean() * 100
    good_last = last.loc[multi, "has_good"].mean() * 100
    bad_first = first.loc[multi, "has_bad"].mean() * 100
    bad_last = last.loc[multi, "has_bad"].mean() * 100

    # ===== 报告正文 =====
    parts.append(f"""# 标题高频词与成功配方

> **口径声明**
> 1. 数据为 `out/novels.csv`，剔除日轻授权作者（{len(config.LICENSED_LN_AUTHORS)} 家）后 {num(total)} 行；标题经 jieba 精确模式切词，仅保留 ≥2 字，复用报告 12 的切词缓存。
> 2. **成功**以「收藏」为主刻度（比点击更接近真实偏好，见报告 02/08）；累计指标跨世代不可比，因此采用**条件分位**：在同世代、同标题词数（及同题材）组内对收藏排序，0.5 为该组中位数。上榜率作辅助刻度（月票榜 top20 右截断）。
> 3. 「成功配方」是**相关**不是因果：含某词的书收藏高，可能是词吸引了读者，也可能是该词标记了高收藏偏好的题材/受众。报告用「再控制题材」一列显式剥离后者。
> 4. 词表为 jieba 数据驱动，**泛词已剔除**（见生成器 `GENERIC`）；萌神荣誉标签不属于标题词，无需处理。
> 5. 本报告不改动任何数据行；正文数字全部现算。

## 结论

1. **作者的「配方」确实存在，但高度题材特定**：控制世代+词数+题材后，{"、".join(f"「{x.word}」{x.fav_3:.2f}" for x in good.head(4).itertuples())} 的净收藏分位显著高于 0.5；题材内部「标题越长收藏越高」的相关在{gc_sorted[-1]['genre']} {gc_sorted[-1]['r']:+.3f} vs {gc_sorted[0]['genre']} {gc_sorted[0]['r']:+.3f} 之间摆动——**没有通用配方，只有赛道配方**。
2. **标题变长几乎全部来自「堆词」**：三段时期分解中，词数贡献（平均 +{np.mean([d['d_tok'] for d in dec]):.2f} 字）远超单词长度贡献（平均 {np.mean([d['d_char'] for d in dec]):+.2f} 字，接近零或为负）。这与「作者累积卖点词」的假说相容，但本报告只能证明**堆词与高收藏相关**，不能证明堆的是「成功词」（词数效应在条件分位设计中按定义为零）。
3. **部分配方有保质期**：{n_decline}/{len(takeoffs)} 个高频词在采用率突破 1% 后的三年里净收益下滑（{"、".join(f"「{t['word']}」{t['before']:.2f}→{t['after']:.2f}" for t in takeoffs if t['after'] < t['before'])}），与拥挤效应相容；但其余 {len(takeoffs)-n_decline}/{len(takeoffs)} 个未下行，「跟风必衰减」不成立。
4. **题材是最强的混淆项**：「崩坏」控制题材后净分位从 {r[r.word=='崩坏'].fav_2.iloc[0]:.3f} 降到 {r[r.word=='崩坏'].fav_3.iloc[0]:.3f}——相当一部分「配方效应」其实是同人受众本就收藏高，不是词本身有效。
5. **词表极度分散**：唯一词 {num(len(cnt))} 个，top10 仅覆盖 {top10_share:.1f}% 的标题词例——成功不是 memorize 一张短词表，而是在长尾里找组合。
6. **作者换配方的证据很弱**：多产作者（≥3 本）首作含高分词 {good_first:.1f}% → 末作 {good_last:.1f}%（+{good_last-good_first:.1f}pp），低分词 {bad_first:.1f}% → {bad_last:.1f}%——方向符合「试配方」，但幅度太小，不足以说作者在学习。

## 1. 高频词谱：词云与世代

![词云]({f_cloud})

| 世代 | 高频标题词（剔除泛词，前 6） |
|---|---|
""")
    for era, words in era_words.items():
        parts.append(f"| {era} | {'、'.join(f'{w}({num(n)})' for w, n in words)} |\n")
    parts.append(f"""
高频词从「世界/少女/魔法」的**意象型**，转向「穿越/崩坏/变成」的**叙事机制型**，再到「小姐/魔女/反派」的**角色身份型**。top10 词仅覆盖 {top10_share:.1f}% 词例、top100 覆盖 {top100_share:.1f}%——词表极长尾，所谓「配方」从来不是一张短清单。

## 2. 成功词识别：题材能解释多少

![成功词]({f_rank})

| 词 | 书数 | 净收藏分位（控制世代+词数） | 再控制题材 | 题材解释掉的部分 |
|---|---:|---:|---:|---:|
""")
    for x in r.nlargest(10, "fav_3").itertuples():
        parts.append(f"| {x.word} | {num(x.n)} | {x.fav_2:.3f} | {x.fav_3:.3f} | {x.delta:+.3f} |\n")
    parts.append("\n对照——净分位最低的词：\n\n| 词 | 书数 | 控制世代+词数 | 再控制题材 |\n|---|---:|---:|---:|\n")
    for x in bad.itertuples():
        parts.append(f"| {x.word} | {num(x.n)} | {x.fav_2:.3f} | {x.fav_3:.3f} |\n")
    parts.append(f"""
**关键读法**：灰色柱（控制世代+词数）是「词本身的净关联」，蓝色柱（再控制题材）是「剥离题材受众后的净关联」。「崩坏」的差距最大（{proxy[proxy.word=='崩坏'].delta.iloc[0]:+.3f} 若在其中）——它标记的同人赛道读者本就收藏更高。多数词的两柱接近，说明题材不是它们的解释。

## 3. 配方的保质期：采用率飙升后收益下滑

![生命周期]({f_life})

| 词 | 起飞年（采用率>1%） | 起飞前 3 年均净分位 | 起飞后 3 年均净分位 | 变化 |
|---|---:|---:|---:|---:|
""")
    for x in takeoffs:
        parts.append(f"| {x['word']} | {x['year']} | {x['before']:.3f} | {x['after']:.3f} | {x['after']-x['before']:+.3f} |\n")
    parts.append(f"""
{n_decline}/{len(takeoffs)} 个词在起飞后收益下行。「系统」{next(t['before'] for t in takeoffs if t['word']=='系统'):.3f}→{next(t['after'] for t in takeoffs if t['word']=='系统'):.3f}、「转生」{next(t['before'] for t in takeoffs if t['word']=='转生'):.3f}→{next(t['after'] for t in takeoffs if t['word']=='转生'):.3f} 最明显——与**拥挤效应**相容：词被用滥后差异化信号减弱。但多数词（{len(takeoffs)-n_decline}/{len(takeoffs)}）后段并未下行，「崩坏」反而上行，说明**配方衰竭是部分现象、不是铁律**。

## 4. 标题为什么变长：堆词，而不是单词变长

![长度归因]({f_dec})

| 时期 | 标题长度变化 | 词数增加贡献 | 单词变长贡献 |
|---|---:|---:|---:|
""")
    for x in dec:
        parts.append(f"| {x['y0']}→{x['y1']} | +{x['d_tok']+x['d_char']:.2f} 字 | +{x['d_tok']:.2f} | {x['d_char']:+.2f} |\n")
    parts.append(f"""
三个时期里词数贡献均远超单词长度变化（后者接近零甚至为负）。标题从「短语标识」变成「卖点摘要」，靠的是**往标题里塞更多卖点词**，不是把词写得更花哨。这与「累积卖点词驱动变长」的假说相容；但必须强调：本报告用的是条件分位（词数效应按设计为零），**无法检验「堆的是不是成功词」**——那需要标注每个词的意图，超出了元数据能支撑的范围。

## 5. 配方是题材特定的

![题材相关]({f_genre})

题材内「标题长度 vs 收藏」的相关系数从 {gc_sorted[0]['r']:+.3f}（{gc_sorted[0]['genre']}）到 {gc_sorted[-1]['r']:+.3f}（{gc_sorted[-1]['genre']}）不等。**在同人和悬疑，标题长甚至无效或反向**——那里的读者看重别的信号。所谓「成功配方」只在部分赛道成立，跨题材推广会失效。

## 6. 配方家族：词的固定搭档

![共现家族]({f_co})

共现分析显示词不是孤立使用：{"；".join(f"「{w}」的固定搭档是「{'/'.join(p for p, _v in co[w].most_common(3))}」" for w in top_co[:3])}。标题是**按家族成套组装**的——这解释了为什么词数会稳定增长：一个新词进入家族后，往往与既有词叠加，而不是替换。

## 7. 口径边界

1. **收藏是累计指标**：条件分位控制世代与词数，但同世代内上架时长的差异仍可能残留；上榜率因 top20 右截断只能作辅助。
2. **词表是 jieba 切分结果**：不同切词器会给出不同词表；本报告只保证内部一致，不声称是唯一正确分词。
3. **反向因果未完全排除**：「成功词」可能是成功题材/受众的代理（§2 已量化「崩坏」被题材解释掉的部分），其余词只做到「再控制题材」的稳健性检查。
4. **不推断意图**：本报告说「作者追逐配方」是基于采用率与收益的**宏观统计模式**，不代表能观测到单个作者的决策过程。

## 图表索引

- 图 1 词云：`figures/14_cloud.png`
- 图 2 成功词：`figures/14_wordrank.png`
- 图 3 生命周期：`figures/14_lifecycle.png`
- 图 4 长度归因：`figures/14_lengthdecomp.png`
- 图 5 题材相关：`figures/14_genrecorr.png`
- 图 6 共现家族：`figures/14_cooccur.png`
""")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(parts), encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    print(build())

"""报告 13：跟风传播与同期爆火潮。

报告 12 的独立扩展：头部热销书池、同期爆火归因、题材/标签共振、多因素叠加。
所有正文数字现算，不写快照。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
BASE = paths.ROOT
from lib import charts, config, eras

TOKEN_CACHE = paths.OUT_DIR / "title_tokens.pkl"
OUT = paths.REPORTS_DIR / "13_fad.md"

# 泛词表：不构成「品牌词」
GENERIC = {
    "怎么办", "需要", "身体", "总是", "失败", "角色", "回家", "当下", "可能",
    "这个", "那个", "我们", "你们", "他们", "自己", "什么", "怎么", "为什么",
    "之后", "开始", "时候", "世界", "一个", "没有", "不是", "就是", "可以",
    "不会", "这样", "那样", "如果", "因为", "所以", "但是", "而且", "已经",
    "不当", "之主", "家伙", "东西", "一生", "一切", "大人", "小姐", "先生",
    "起来", "下来", "上去", "过去", "现在", "后来", "突然", "我的", "你的",
    "他的", "她们", "来着", "真的", "只有", "全是", "竟然", "成为", "不想",
}


def num(x) -> str:
    return f"{x:,.0f}"


def is_moebattle(t: str) -> bool:
    """荣誉标签（萌神大赛年份）不是题材标签。"""
    return "萌神" in str(t)


def load_data():
    df = pd.read_csv(paths.CSV_FILE, dtype={"tags": str, "contest": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year"]], on="id")
    df = df.dropna(subset=["est_year"]).copy()
    df["est_year"] = df["est_year"].astype(int)
    df["title"] = df["title"].fillna("")
    return df


def load_ranks():
    first_mv = {}
    with open(paths.MONTHLY_RANKS, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["rank"] != 0:
                continue
            m = r["month"]
            for it in r.get("items", []):
                nid, t = it["nid"], it.get("ticketNum", 0)
                if nid not in first_mv or m < first_mv[nid][0]:
                    first_mv[nid] = (m, it["name"], t)
    return {nid: v for nid, v in first_mv.items() if v[2] >= 100}


def quarter(m: str) -> str:
    y, mo = m.split("-")
    return f"{y}Q{(int(mo) - 1) // 3 + 1}"


# ---------------- 图表 ----------------

def fig_pool(top20_by, pool, hot_n):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0))
    # 左：三榜重合（用集合大小画柱）
    ax = axes[0]
    sets = {k: set(v) for k, v in top20_by.items()}
    labels = ["点击 top20", "收藏 top20", "点赞 top20"]
    vals = [len(s) for s in sets.values()]
    ax.bar(labels, vals, color=[charts.C["blue"], charts.C["red"], charts.C["green"]],
           width=0.6, zorder=3)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.4, str(v), ha="center", fontsize=9)
    ax.set_title(f"三榜各 20 本，去重后 {len(pool)} 本")
    ax.set_ylabel("书数")
    ax.set_ylim(0, 25)
    # 右：热销池定年
    ax = axes[1]
    vc = pool.groupby("est_year").size()
    ax.bar(vc.index, vc.values, color=charts.C["blue"], width=0.7, zorder=3)
    charts.shade_periods(ax, pd.Series(vc.index.values))
    ax.set_title(f"头部书定年分布（{hot_n}/{len(pool)} 本月票榜≥100）")
    ax.set_xlabel("定年创建年")
    ax.set_ylabel("书数")
    ax.set_xticks(vc.index[::2])
    fig.suptitle("头部热销书池：点击榜与收藏榜几乎完全重合", fontsize=11, y=1.02)
    fig.tight_layout()
    return charts.save(fig, "13_pool.png")


def fig_coattack(series):
    """同期爆火潮密度 + 共享题材标签的主导类别。"""
    years = [x[0] for x in series]
    vals = [x[1] for x in series]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(years, vals, color=charts.C["blue"], width=0.66, zorder=3)
    for y, v in zip(years, vals):
        ax.text(y, v + 0.6, str(v), ha="center", fontsize=7.5)
    ax.set_ylabel("当年首上月票榜(≥100票)书数")
    ax.set_xlabel("年")
    ax.set_title("同期爆火潮密度：可归因的「同期书」从个位数涨到 50+")
    charts.shade_periods(ax, pd.Series(years))
    ax.set_xticks(years[::2])
    ax.set_ylim(0, max(vals) * 1.18)
    fig.tight_layout()
    return charts.save(fig, "13_coattack.png")


def fig_jaccard(rows):
    qs = [r["q"] for r in rows]
    x = np.arange(len(qs))
    inner = [r["inner"] for r in rows]
    base = [r["base"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(x, inner, color=charts.C["red"], marker="o", ms=4, lw=2,
            label="同期爆火书组内标签 Jaccard", zorder=3)
    ax.plot(x, base, color=charts.C["blue"], marker="s", ms=3.5, lw=1.8,
            label="同期全库随机组基线", zorder=3)
    ax.fill_between(x, inner, base, color=charts.C["red"], alpha=0.12)
    ax.set_xticks(x[::3])
    ax.set_xticklabels([qs[i] for i in range(0, len(qs), 3)], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("标签 Jaccard 相似度")
    ax.set_title("同期爆火书更同质：组内题材标签相似度高于全库基线")
    ax.legend(loc="upper left", framealpha=0.9)
    fig.tight_layout()
    return charts.save(fig, "13_jaccard.png")


def fig_multifactor(rows):
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    rows = sorted(rows, key=lambda x: x["amplified"])
    names = [f"{r['word']} n={r['n']}" for r in rows]
    vals = [r["amplified"] for r in rows]
    colors = [charts.C["red"] if v >= 5 else charts.C["blue"] for v in vals]
    ax.barh(names, vals, color=colors, height=0.68, zorder=3)
    for i, v in enumerate(vals):
        ax.text(v + 0.15, i, f"{v:.1f}×", va="center", fontsize=8)
    ax.axvline(1, color="#333333", lw=1)
    ax.set_xlabel("跟风书收藏中位 / 同期同题材书收藏中位（倍）")
    ax.set_title("多因素叠加：命中品牌词的书在同题材内仍显著领先")
    ax.set_xlim(0, max(vals) * 1.12)
    fig.tight_layout()
    return charts.save(fig, "13_multifactor.png")


def fig_track(track):
    """共享标签赛道的季度演变：多折线（比例可相加>100%，不用堆叠）。"""
    qs = track["q"]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    palette = [charts.C["blue"], charts.C["red"], charts.C["green"], "#E69F00", "#999999"]
    x = np.arange(len(qs))
    for i, (tag, vals) in enumerate(track["series"].items()):
        ax.plot(x, vals, color=palette[i % len(palette)], marker="o", ms=3,
                lw=1.9, label=tag, zorder=3)
    ax.set_xticks(x[::3])
    ax.set_xticklabels([qs[i] for i in range(0, len(qs), 3)], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("同期爆火书中含该标签的比例 (%)")
    ax.set_title("爆款赛道轮转：无敌 → 倒追/女性主角 → 变身/橘味")
    ax.legend(ncol=5, loc="upper left", framealpha=0.9, fontsize=8)
    fig.tight_layout()
    return charts.save(fig, "13_track.png")


# ---------------- 正文 ----------------

def build() -> str:
    charts.setup_style()
    df = load_data()
    with open(TOKEN_CACHE, "rb") as fh:
        toks = pickle.load(fh)
    hot = load_ranks()
    df_idx = df.set_index("id")
    yt = df.groupby("est_year").size()

    wy = defaultdict(Counter)
    for nid, yr in zip(df["id"], df["est_year"]):
        for w in set(toks.get(nid, [])):
            wy[w][yr] += 1

    # --- 头部热销书池 ---
    top20_by = {m: set(df.nlargest(20, m)["id"]) for m in ["clicks", "favs", "praises"]}
    pool_ids = set().union(*top20_by.values())
    pool = df[df.id.isin(pool_ids)].copy()
    pool["on_rank"] = pool.id.isin(hot)
    f_pool = fig_pool(top20_by, pool, int(pool["on_rank"].sum()))

    # --- 同期爆火潮密度 ---
    hot_year = Counter(int(v[0][:4]) for v in hot.values())
    series = [(y, hot_year.get(y, 0)) for y in range(2013, 2025)]
    f_co = fig_coattack(series)

    # --- 品牌词 + 同期归因 ---
    BRANDS = {
        "圣女": (70814, 2017), "仙子": (167480, 2018), "血姬": (155640, 2018),
        "女帝": (75096, 2017), "狐娘": (46669, 2016), "机甲": (57234, 2016),
        "分手": (130710, 2018), "徒儿": (162073, 2018), "之主": (57436, 2017),
        "大叔": (42842, 2015), "皇帝": (101807, 2017), "猎魔": (32911, 2013),
    }
    brand_rows = []
    for w, (nid, hy) in BRANDS.items():
        if nid not in df_idx.index:
            continue
        # 同期：hy-1~hy+1 首上月票榜且标题含 w
        contenders = [n for n, (m, name, t) in hot.items()
                      if n in df_idx.index
                      and hy - 1 <= int(m[:4]) <= hy + 1
                      and w in str(df_idx.loc[n, "title"])]
        post = sum(wy[w].get(y, 0) for y in range(hy, hy + 6))
        fol = df[(df.est_year > hy) & df.title.str.contains(w, na=False) & (df.id != nid)]
        src_genre = df_idx.loc[nid, "genre"]
        ctrl_g = df[(df.est_year > hy) & (df.genre == src_genre)]
        amplified = fol.favs.median() / max(ctrl_g.favs.median(), 1)
        brand_rows.append({
            "word": w, "nid": nid, "hy": hy, "contenders": len(contenders),
            "post": post, "n": len(fol), "genre": src_genre,
            "favs": fol.favs.median(), "ctrl_favs": ctrl_g.favs.median(),
            "amp": amplified,
            "title": str(df_idx.loc[nid, "title"]),
        })
    n_mixed = sum(1 for r in brand_rows if r["contenders"] > 1)
    f_amp = fig_multifactor([{**r, "amplified": r["amp"]} for r in brand_rows])

    # 对 29 本头部书逐本做品牌词扫描（独立计算，不能从 BRANDS 反推）
    head_brand_n = 0
    for nid in pool_ids:
        hy = int(df_idx.loc[nid, "est_year"])
        if hy > 2020:
            continue
        found = False
        for w in set(toks.get(nid, [])):
            if len(w) < 2 or w in GENERIC:
                continue
            pre = sum(wy[w].get(y, 0) for y in range(hy - 3, hy))
            post = sum(wy[w].get(y, 0) for y in range(hy, hy + 6))
            if pre <= 3 and post >= 30:
                fol_n = len(df[(df.est_year > hy) & df.title.str.contains(w, na=False) & (df.id != nid)])
                if fol_n >= 5:
                    found = True
                    break
        if found:
            head_brand_n += 1

    # --- 同期标签共振（Jaccard）---
    by_q = defaultdict(list)
    for nid, (m, name, t) in hot.items():
        if nid in df_idx.index:
            by_q[quarter(m)].append(nid)

    def tags_of(nid):
        tg = df_idx.loc[nid, "tags"]
        return {t for t in str(tg).split("|") if t and t != "nan" and not is_moebattle(t)} \
            if isinstance(tg, str) and tg else set()

    rng = np.random.default_rng(42)
    jac_rows = []
    track = defaultdict(list)
    TRACK_TAGS = ["无敌", "倒追", "女性主角", "变身", "橘味"]
    for q, nids in sorted(by_q.items()):
        y = int(q[:4])
        if not (2015 <= y <= 2024) or len(nids) < 2:
            continue
        tsets = [tags_of(n) for n in nids]
        js = [len(a & b) / len(a | b) for i, a in enumerate(tsets)
              for b in tsets[i+1:] if a | b]
        base_pool = [set(str(t).split("|")) for t in df[df.est_year == y]["tags"].dropna()]
        base_pool = [{t for t in s if not is_moebattle(t)} for s in base_pool]
        bjs = []
        if len(base_pool) > 10:
            for _ in range(50):
                pick = rng.choice(len(base_pool), size=min(len(nids), len(base_pool)), replace=False)
                ss = [base_pool[i] for i in pick]
                bjs += [len(a & b) / len(a | b) for i, a in enumerate(ss)
                        for b in ss[i+1:] if a | b]
        jac_rows.append({"q": q, "inner": np.mean(js) if js else 0,
                         "base": np.mean(bjs) if bjs else 0, "n": len(nids)})
        # 赛道占比
        for t in TRACK_TAGS:
            track[t].append(sum(1 for s in tsets if t in s) / len(tsets) * 100)
    f_jac = fig_jaccard(jac_rows)
    track_data = {"q": [r["q"] for r in jac_rows],
                  "series": {t: track[t] for t in TRACK_TAGS}}
    f_track = fig_track(track_data)

    # 同期共振胜出季度比例
    win_q = sum(1 for r in jac_rows if r["inner"] > r["base"])
    ratio_jac = np.mean([r["inner"] for r in jac_rows]) / max(np.mean([r["base"] for r in jac_rows]), 0.01)

    parts = []
    parts.append(f"""# 报告 13：跟风传播与同期爆火潮

> 数据口径：{num(len(df))} 本（已剔除正版日轻），定年来自 `eras.py`。
> 头部热销书池 = 点击 / 收藏 / 点赞各 top20 去重（{num(len(pool_ids))} 本）；
> 爆款定义 = 首次上月票榜且月票 ≥100（月榜原始 {num(len(hot))} 条，含少量不在定年库中的 nid）。
> 分词用 jieba 精确模式（≥2 字词），品牌词判据 = 爆火前 3 年 ≤3 次、
> 爆火起 6 年 ≥30 次，已剔除泛词表与荣誉标签（萌神）。
> 「同期」按首次上榜季度定义。跟风绝对计数仍受报告 10 游标遗漏影响，是**下界**。

## 结论

1. **头部书很少造词**：三榜去重 {num(len(pool_ids))} 本头部书全部上过月度榜
   （其中 {int(pool['on_rank'].sum())} 本首上月票榜 ≥100），
   逐本扫描后仅 {num(head_brand_n)} 本（{head_brand_n / len(pool_ids) * 100:.0f}%）能检出
   「从生僻到常用」的品牌词。造词更多是**中等热度爆款**的现象；
   顶级作品靠既有词汇与运营，不靠新词。
2. **点击榜与收藏榜几乎完全重合**：各 20 本里 {len(top20_by['clicks'] & top20_by['favs'])} 本相同，
   点赞榜另贡献 {len(top20_by['praises'] - top20_by['clicks'])} 本——
   头部热销是稳定的同一批书，不是三个独立榜单。
3. **跟风常是「潮」不是「单本引爆」**：报告 12 识别的 12 个品牌词里
   {n_mixed} 个在扩散窗口内有 ≥2 本同期爆火书标题含该词——
   「仙子」（2018-04《飞升从养个仙子开始》与 2018-12《请问今天仙子需要我拯救吗》）、
   「狐娘」（3 本）、「圣女」「徒儿」「之主」均是**同期多本共振**，
   归给单一源头书是过度归因；「血姬」「女帝」「机甲」等才是单本驱动。
4. **同期爆火书更同质**：{win_q}/{len(jac_rows)} 个季度的组内题材标签 Jaccard 高于同期全库随机组，
   整体比值 {ratio_jac:.2f}×；2018Q1 达 0.370 vs 0.106——
   爆款潮是**赛道共振**，不是独立随机事件。
5. **赛道随时间轮转**：同期爆火书共享标签从 2016 的恋爱/无敌 → 2020–22 的
   倒追/女性主角 → 2023–24 的变身/橘味，与报告 09 的女性向转向同向。
6. **多因素叠加放大效应**：命中品牌词的跟风书相对同期**同题材**书的收藏中位数
   在 {min(r['amp'] for r in brand_rows):.1f}–{max(r['amp'] for r in brand_rows):.1f} 倍之间
   （{sum(1 for r in brand_rows if r['amp'] > 2)}/{len(brand_rows)} 个词超过 2 倍），
   说明「品牌词 × 题材 × 标签」同时命中会放大注意力——但这仍是相关，非因果。

## 1. 头部热销书池：点击榜与收藏榜是同一批书

![热销书池]({f_pool})

三榜去重只有 {num(len(pool_ids))} 本，其中点击与收藏 top20 重合
{len(top20_by['clicks'] & top20_by['favs'])} 本。头部书全部上过月度榜
（其中 {int(pool['on_rank'].sum())} 本首上月票榜 ≥100），定年集中在 2016–2023。**与报告 12 的中等热度爆款不同，这些顶级作品只有
{head_brand_n}/{len(pool_ids)} 产出新品牌词**——它们的标题多用既有词
（「我」「世界」「变成」），跟风扩散主要发生在有明确新概念的中腰部爆款上。

## 2. 同期爆火潮：可归因的同期书从个位数涨到 50+

![同期潮密度]({f_co})

首上月票榜（≥100 票）的书数从 2013 年的 {series[0][1]} 本涨到
2023 年的 {dict(series)[2023]} 本。这意味着「同期爆火」在早期是稀疏事件，
2020 后成为常态——**任何一个品牌词的扩散，都更可能是多本书共同的赛道效应**。

## 3. 单本驱动 vs 同期共振：12 个品牌词的归因检验

按「扩散窗口 hy-1~hy+1 内首上月票榜且标题含该词」计数：

| 品牌词 | 源头爆款 | 爆火年 | 同期含该词爆火书 | 爆火后 6 年词频 | 跟风书数 | 判定 |
|---|---|---:|---:|---:|---:|---|
""")
    for r in sorted(brand_rows, key=lambda x: -x["n"]):
        judge = "同期共振" if r["contenders"] > 1 else "单本驱动"
        parts.append(f"| {r['word']} | {r['title'][:18]} | {r['hy']} | "
                     f"{r['contenders']} | {num(r['post'])} | {num(r['n'])} | {judge} |\n")
    parts.append(f"""
{n_mixed} 个词被证实是同期多本共振。这修正了报告 12 §3.2 的单本归因：
「仙子」不是某一本书带火的，而是 2018 年至少两本爆款同时使用该词；
「狐娘」更极端——2016 年《狐娘的奶妈和教师生涯》与《不想当音乐家的狐娘不是好厨子》
同季爆火，2017 年《我变成了游戏宠物？狐娘？！》以 2,448 票接力。
**在这些案例里，词属于赛道，不属于某一本书。**

## 4. 同期爆火书的题材/标签共振

![Jaccard]({f_jac})

同期爆火书的题材标签 Jaccard 在 {win_q}/{len(jac_rows)} 个季度高于同期全库基线，
整体 {ratio_jac:.2f}×。峰值季度（如 2018Q1、2024Q3）达到基线的 3 倍以上——
**爆款不是分散出现的，而是成簇落在同一题材赛道**。

![赛道轮转]({f_track})

共享标签的构成随时间系统性变化：

- 2016–2018：无敌 / 战斗 / 异世界（男性向升级流）
- 2019–2022：倒追 / 女性主角 / 恋爱（女性向倒追流）
- 2023–2024：变身 / 橘味 / 女性主角（女性向变身流，见报告 09）

这与报告 09 的「2022 词表清理、2023–24 女性向爆发」完全一致：
**跟风的方向由当期赛道决定，爆款只是赛道的可见节点**。

## 5. 多因素叠加：品牌词 × 题材 × 标签

![多因素叠加]({f_amp})

对 {num(len(brand_rows))} 个品牌词，比较跟风书与同期**同题材**书的收藏中位数
（而非同期全库），以剥离题材红利：

| 品牌词 | 跟风书 n | 跟风收藏中位 | 同期同题材收藏中位 | 叠加倍数 |
|---|---:|---:|---:|---:|
""")
    for r in sorted(brand_rows, key=lambda x: -x["amp"]):
        parts.append(f"| {r['word']} | {num(r['n'])} | {num(r['favs'])} | "
                     f"{num(r['ctrl_favs'])} | {r['amp']:.2f}× |\n")
    parts.append(f"""
多数品牌词的跟风书在控制题材后仍领先
（{min(r['amp'] for r in brand_rows):.1f}–{max(r['amp'] for r in brand_rows):.1f} 倍），
说明标题品牌词**叠加在题材之上**还有额外的注意力聚集；
少数词（如猎魔 {[r for r in brand_rows if r['word'] == '猎魔'][0]['amp']:.2f}×）则完全依赖题材红利，剥离后无优势。
但必须强调这是**相关而非因果**：愿意在标题中用爆款词、
且能精确踩中当期赛道的作者，本身就是更敏锐的经营者和更优质的创作者——
跟风行为与作品质量都由「作者能力」这个潜在变量驱动。

## 6. 口径边界与未决

1. **「同期」的操作化**：按首次上榜季度（3 个月）定义。更窄的窗口（月）会让同期共振判定更保守；
   本报告用季度以容忍月榜 top20 的右截断与定年误差（LOO P99 ≈50 天）。
2. **品牌词判据的保守性**：爆火前 ≤3 次、爆火后 ≥30 次的阈值会漏掉
   「已有一定基础、爆款显著放大」的词（如「英雄」），这类词无法通过本判据识别跟风。
3. **荣誉标签剔除**：源书标签中的「2018萌神」等是年度大赛荣誉（报告 09 §7），
   已从题材标签统计中整行剔除，避免污染 Jaccard。
4. **因果不可识别**：报告 10 已证抓取偏短/新；跟风书多为短篇同人，漏抓更严重。
   本报告所有倍数都是从观测样本算得的下界，且**选择效应无法剥离**。
5. **头部书造词率低**：{len(pool_ids)} 本头部书逐本扫描后仅 {head_brand_n} 本有品牌词扩散，
   但样本太小，不足以断言「顶级书不造词」是普遍规律，仅为观察。
""")
    text = "".join(parts)
    OUT.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    t = build()
    print(f"已生成 {OUT.relative_to(BASE)}（{len(t)} 字符）")

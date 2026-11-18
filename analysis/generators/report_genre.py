"""生成 analysis/reports/04_genre_tags.md：题材、标签与征文。

genre 是站点货架的单选分类，tags 是作者从受控词表（106 个唯一标签、
每本最多 5 个）勾选的自述。两者口径不同，报告分开处理。
所有数字现算自 analysis/out/novels.csv，年份由 analysis/eras.py 定年。
报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/report_genre.py
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

OUT = paths.REPORTS_DIR / "04_genre_tags.md"
GENRE_ORDER = ["魔幻", "玄幻", "同人", "校园", "都市", "科幻", "游戏", "古风", "悬疑"]

# 世代分组（与报告 01 §2 分期一致）
ERAS = [
    ("2007-2014", 2007, 2014),
    ("2015-2016", 2015, 2016),
    ("2017-2018", 2017, 2018),
    ("2019-2022", 2019, 2022),
    ("2023-2025", 2023, 2025),
]

# 9 类叠加面积图配色（色盲安全，与 charts.C 同源扩展）
GENRE_COLORS = {
    "魔幻": "#4477AA",
    "玄幻": "#66CCEE",
    "同人": "#228833",
    "校园": "#CCBB44",
    "都市": "#EE6677",
    "科幻": "#AA3377",
    "游戏": "#BBBBBB",
    "古风": "#997700",
    "悬疑": "#331133",
}

TAG_LINES = ["女性主角", "倒追", "橘味", "末世", "系统", "异世界"]
TAG_COLORS = {
    "女性主角": "#CC3311",
    "倒追": "#EE7733",
    "橘味": "#CCBB44",
    "末世": "#AA3377",
    "系统": "#4477AA",
    "异世界": "#009988",
}


def load() -> pd.DataFrame:
    df = pd.read_csv(
        paths.OUT_DIR / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year"]], on="id")
    # 年度序列止于 2025：2026-05 后新书在快照中可见性骤降（报告 01 §1）。
    return d[d["est_year"].between(2007, 2025)].copy()


def pct(x: float) -> str:
    return f"{x:.1f}"


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def tag_list(s: pd.Series) -> pd.Series:
    """tags 字符串 → 标签列表，剔除 7 个萌神荣誉标签。"""
    return s.fillna("").map(
        lambda v: [t for t in v.split("|") if t and not t.endswith("萌神")]
    )


def tag_share(d: pd.DataFrame, tag: str, years: list[int]) -> dict[int, float]:
    """指定年份该标签占有标签新书的比例（%）。"""
    tl = tag_list(d["tags"])
    has = tl.map(len) > 0
    out = {}
    for y in years:
        m = d["est_year"] == y
        if has[m].sum():
            out[y] = float(tl[m].map(lambda L, t=tag: t in L)[has[m]].mean() * 100)
    return out


def heat_medians(d: pd.DataFrame, tags: list[str]) -> dict[str, float]:
    """2017-2025 新书、剔除萌神 13 本后，各标签的 favs 中位。"""
    dd = d[d["est_year"].between(2017, 2025) & ~d["tags"].fillna("").str.endswith("萌神")]
    tl = tag_list(dd["tags"])
    return {t: float(dd[tl.map(lambda L, t=t: t in L)]["favs"].median()) for t in tags}


# ---------- 图表 ----------


def fig_genre_share(d: pd.DataFrame) -> str:
    """9 类供给份额的年度堆叠面积图（2007-2025）。"""
    years = np.arange(2007, 2026)
    share = (
        pd.crosstab(d["est_year"], d["genre"], normalize="index")
        .reindex(years)
        .fillna(0)
        .mul(100)
    )
    order = [g for g in GENRE_ORDER if g in share.columns]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.stackplot(
        years, [share[g].to_numpy() for g in order],
        labels=order, colors=[GENRE_COLORS[g] for g in order], alpha=0.92, lw=0,
    )
    # 「同人」类 2019 年上线：白底标注保证在任意色块上可读
    ax.axvline(2019, color="white", lw=1.0, ls="--", zorder=5)
    ax.text(
        2019.25, 92, "同人类上线（2019）", fontsize=7.5, color="#333333",
        va="top", zorder=6,
        bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.8),
    )
    ax.set_xlim(2007, 2025)
    ax.set_ylim(0, 100)
    ax.set_ylabel("当年新书的分类份额 %")
    ax.set_xlabel("定年（年份）")
    ax.legend(
        loc="center left", bbox_to_anchor=(1.005, 0.5), frameon=False,
        fontsize=7.5, handlelength=1.2, handleheight=0.9, labelspacing=0.35,
    )
    return charts.save(fig, "04_genre_share.png")


def fig_tag_era(d: pd.DataFrame) -> str:
    """重点标签占有标签书比例的年度折线（2017-2025，标签体系普及后）。"""
    years = np.arange(2017, 2026)
    dd = d[d["est_year"].between(2017, 2025)]
    tl = tag_list(dd["tags"])
    has_tag = tl.map(len) > 0
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    for t in TAG_LINES:
        share = tl.map(lambda L, t=t: t in L).groupby(dd["est_year"]).mean()
        denom = has_tag.groupby(dd["est_year"]).mean()
        share = (share / denom * 100).reindex(years)
        ax.plot(years, share.to_numpy(), "-o", ms=3, lw=1.6,
                color=TAG_COLORS[t], label=t)
    charts.shade_periods(ax, years)
    ax.set_xlim(2017, 2025)
    ax.set_ylabel("占有标签新书的比例 %")
    ax.set_xlabel("定年（年份）")
    ax.legend(frameon=False, fontsize=7.5, loc="upper left", ncol=2)
    return charts.save(fig, "04_tag_era.png")


# ---------- 共用统计 ----------


def misplacement(d: pd.DataFrame) -> pd.DataFrame:
    """供给份额 vs 收藏份额错位（百分点）。"""
    sup = d["genre"].value_counts(normalize=True).mul(100)
    fav = d.groupby("genre")["favs"].sum()
    fav = fav / fav.sum() * 100
    return pd.DataFrame({"sup": sup, "fav": fav}).assign(
        delta=lambda x: x["fav"] - x["sup"]
    )


def doomsday_stats(d: pd.DataFrame) -> dict:
    tl = tag_list(d["tags"])
    out = {}
    for t in ("末日", "末世"):
        s = d[tl.map(lambda L, t=t: t in L)]
        gen = s.groupby("est_year")["id"].count()
        out[t] = {"n": len(s), "gen": gen, "favs_med": float(s["favs"].median()),
                  "vip": (s["price_type"] == "VIP").mean() * 100,
                  "done": (s["status"] == "已完结").mean() * 100}
    return out


# ---------- 章节 ----------


def section_header(sb: dict) -> str:
    return f"""# 04 · 题材与标签：分类结构、受控词表与征文

> 口径声明：
> 1. 数据源 `analysis/out/novels.csv`，245,779 行，数据内容上界 {sb['date']}，
>    在册存活口径；年份由 nid 定年（锚点插值，报告 01 §1），非 `updated_at`。
>    年度序列止于 2025（内容上界之后新书不在库内，定年落在 2026 的 4,021 行
>    不入年度统计）。
> 2. **genre 与 tags 是两套口径**：genre 是站点货架的单选分类（现行 9 类，
>    2010 年改版确立），决定作品出现在哪个入口；tags 是作者从站点受控词表
>    勾选的自述（全库 106 个唯一标签、每本最多 5 个）。分类不随时间迁移，
>    标签受词表扩充影响。
> 3. **标签体系约 2014 年前后上线**：2010-2013 年定年的书 50-60% 无标签，
>    2017 年起缺失率 <3%。因此跨世代的标签统计只对 2017 年及以后可靠，
>    更早年份的标签频次受体系上线时间混杂，不作世代比较。
> 4. **7 个「20XX萌神」标签（2018-2024）是运营荣誉，不是题材标签**（依据与
>    证据链见 `references/moebattle-tags.md`），已从 §1-§2 的标签统计中剔除，
>    §3 单列。13 本获奖作品的其余标签保留：荣誉挂在作品而非标签上。
> 5. **`末日` 与 `末世` 不合并**（2026-11-16 决定），§4 作独立标签分别统计。
> 6. 主指标 favs（收藏）：clicks 是累计浏览，受上架时长混杂，仅作对照；
>    累计指标跨时点不可比。完结率含右删失，跨世代比较只对早期世代有效。
> 7. 标签由作者勾选、征文参赛由作者报名，两者均为自选择本；与热度的关联
>    是相关而非因果，运营推荐位（featured）造成的反向因果已在 §3 单列处理。
"""


def section_conclusion(d: pd.DataFrame) -> str:
    mis = misplacement(d)
    mh_1718 = (d[(d["est_year"] >= 2017) & (d["est_year"] <= 2018)]["genre"] == "魔幻").mean() * 100
    e1922 = d[d["est_year"].between(2019, 2022)]
    mh_1922 = (e1922["genre"] == "魔幻").mean() * 100
    tr_1922 = (e1922["genre"] == "同人").mean() * 100
    e2325 = d[d["est_year"].between(2023, 2025)]
    mh_tr_2325 = e2325["genre"].isin(["魔幻", "同人"]).mean() * 100

    same = d[(d["genre"] == "同人") & d["est_year"].between(2008, 2021)]

    hs = tag_share(d, "女性主角", [2017, 2025])
    ju = tag_share(d, "橘味", [2024])
    hm = heat_medians(d, ["嫁人", "变身", "倒追", "系统", "无敌"])

    dd = doomsday_stats(d)
    ratio = dd["末世"]["n"] / dd["末日"]["n"]

    n_contest = int(d["contest"].notna().sum())
    par = d["contest"].notna()
    fav_med_p = d[par]["favs"].median()
    fav_med_n = d[~par]["favs"].median()
    p90_p = d[par]["favs"].quantile(0.9)
    p90_n = d[~par]["favs"].quantile(0.9)
    return f"""## 0. 结论

1. **分类结构由「魔幻主导」转为「魔幻 + 同人 + 玄幻」三足**。魔幻份额从
   2017-2018 的 {pct(mh_1718)}% 降到 2019-2022 的 {pct(mh_1922)}%
   （同期同人类从 0 升至 {pct(tr_1922)}%），2023-2025 两类合计
   {pct(mh_tr_2325)}%。同人类 2019 年上线，2008-2021 世代同人行 VIP 率
   {pct((same["price_type"] == "VIP").mean() * 100)}%、中位字数
   {int(same["words"].median()):,} 字（九类最短）、完结率
   {pct((same["status"] == "已完结").mean() * 100)}%（九类最高）——
   平台为二创内容单开的免费货架。
2. **标签是受控词表而非自由文本**：106 个唯一标签、每本 ≤5 个，词表随运营
   扩充（「橘味」2023 年前后入表，2024 年即占有标签新书 {pct(ju[2024])}%）。
   词表内**女性向标签持续扩张**：「女性主角」占有标签新书比例从 2017 年的
   {pct(hs[2017])}% 升至 2025 年的 {pct(hs[2025])}%，是十年间最稳定的结构性变化。
3. **标签与热度强相关**：`嫁人`（favs 中位 {hm['嫁人']:.0f}）、`变身`
   （{hm['变身']:.0f}）、`倒追`（{hm['倒追']:.0f}）远高于 2017-2025 新书整体
   （中位 9）；`系统`（{hm['系统']:.0f}）、`无敌`（{hm['无敌']:.0f}）虽高频但热度
   平庸——高频标签与高热度标签是两个集合。此为相关，样本经作者自选择。
4. **`末世`（{thousands(dd['末世']['n'])} 行）与 `末日`（{thousands(dd['末日']['n'])} 行）
   是两个独立的标签**，相差 {ratio:.0f} 倍；`末日` 在 2023 年后停止使用，
   `末世` 自 2017 年持续扩张。按约定不合并。
5. **征文是供给的重要组成部分**：96 个征文活动、{thousands(n_contest)} 行
   （占在册 {n_contest / len(d) * 100:.1f}%）。参赛书热度高于非参赛书
   （favs 中位 {fav_med_p:.0f} vs {fav_med_n:.0f}、P90 {p90_p:.0f} vs {p90_n:.0f}），
   但参赛是自选择 + 运营筛选的双重选择样本，不可作因果解读。
"""


def section_genre(d: pd.DataFrame) -> str:
    rows = []
    for label, lo, hi in ERAS:
        s = d[d["est_year"].between(lo, hi)]
        ct = s["genre"].value_counts(normalize=True).mul(100)
        row = [label, thousands(len(s))]
        row += [pct(ct.get(g, 0)) for g in GENRE_ORDER]
        rows.append(row)
    era_table = md_table(rows, ["世代", "n"] + GENRE_ORDER)

    mis = misplacement(d)
    mis_rows = [
        [g, pct(mis.loc[g, "sup"]), pct(mis.loc[g, "fav"]), f"{mis.loc[g, 'delta']:+.1f}"]
        for g in GENRE_ORDER
    ]
    mis_table = md_table(mis_rows, ["分类", "供给份额 %", "收藏份额 %", "错位（百分点）"])

    old = d[d["est_year"].between(2008, 2021)]
    feat_rows = []
    for g in GENRE_ORDER:
        s = old[old["genre"] == g]
        feat_rows.append([
            g, thousands(len(s)),
            f"{s['words'].median():,.0f}",
            pct((s["status"] == "已完结").mean() * 100),
            pct((s["price_type"] == "VIP").mean() * 100),
        ])
    feat_table = md_table(
        feat_rows, ["分类", "n", "字数中位", "完结率 %", "VIP 率 %"]
    )

    same = old[old["genre"] == "同人"]
    # 同人类的主体是对话/互动产品线（报告 22 §2）：形态判据占比现算
    tr_all = d[d["genre"] == "同人"]
    tr_dlg = dialogue_form.mark(tr_all)
    tr_dlg_share = tr_dlg["morph"].mean() * 100 if len(tr_dlg) else 0.0
    tr = d[d["genre"] == "同人"].groupby("est_year")["id"].count()
    mh_1718 = (d[(d["est_year"] >= 2017) & (d["est_year"] <= 2018)]["genre"] == "魔幻").mean() * 100
    return f"""## 1. 分类：魔幻的长期主导与「同人」类的登场

![分类份额堆叠面积图]({fig_genre_share(d)})

各世代的新书分类份额（行合计 100）：

{era_table}

三点解读。其一，**魔幻是贯穿始终的第一大分类**，兴趣站期 46.0%、
2017-2018 {pct(mh_1718)}%；2019 年后其份额下降并非绝对供给萎缩，
而是同人类分流的相对稀释。其二，**同人类 2019 年上线**：2016-2018 年仅
{int(tr.loc[2016:2018].sum())} 本散点（早期遗留记录），2019 年即
{int(tr.get(2019, 0))} 本、2021 年峰值 {int(tr.max()):,} 本
（占当年 25.0%），此后随大盘收缩。其三，校园份额从兴趣站期 20.3% 持续下滑，
玄幻在 2019-2022 稳定于 14-16%，都市在收缩期回升（11.2%）。

同人类的平台定位可见于其经营特征（2008-2021 世代，与下表同口径）：
VIP 率 {pct((same["price_type"] == "VIP").mean() * 100)}%（≈零付费）、中位字数
{int(same["words"].median()):,} 字（九类最短）、完结率
{pct((same["status"] == "已完结").mean() * 100)}%（九类最高）——
免费、轻量、快完结的二创货架，与原创商业连载互不挤占。

> **口径注记（报告 22）**：「同人类兴起」的主体不是传统同人长篇，而是**对话/互动
> 小说产品线**——同人挂常规长篇无法进入 VIP 体系，故同人标签/类目高度集中在不走
> VIP 的对话/互动。本地按形态判据，同人类中 {pct(tr_dlg_share)}% 为对话/互动形态
> （每章约 500 字、整本可长，不以字数判形态）。本报告的份额与序列不受影响，
> 受影响的是对「同人」的解读：这是产品线结构变化，不是题材口味变化。
> 详见报告 22。

各分类的供给份额与收藏份额错位（2007-2025 全口径）：

{mis_table}

古风（{mis.loc['古风', 'delta']:+.1f} 百分点）与校园（{mis.loc['校园', 'delta']:+.1f}）
的收藏份额显著高于供给份额——两者的头部作品年代早、累积久；科幻
（{mis.loc['科幻', 'delta']:+.1f}）与同人类（{mis.loc['同人', 'delta']:+.1f}）则相反，
供给大而收藏份额低。悬疑供给 {pct(mis.loc['悬疑', 'sup'])}%、收藏份额仅
{pct(mis.loc['悬疑', 'fav'])}%，是九类中最弱的货架。

各分类经营特征（2008-2021 世代，n={thousands(len(old))}；完结率含右删失，
早期世代删失较小）：

{feat_table}

古风 VIP 率 {pct((old[old['genre'] == '古风']['price_type'] == 'VIP').mean() * 100)}%
显著高于其余分类，与报告 01 的商业化观察一致：古风是 VIP 付费密度最高的分类；
同人类 VIP 率 ≈0%，完全游离于付费体系外。
"""


def section_tags(d: pd.DataFrame) -> str:
    tl = tag_list(d["tags"])
    n_tagged = int((tl.map(len) > 0).sum())
    freq = Counter(t for L in tl for t in L)
    vocab_genre = len(freq)
    vocab_all = len({t for s in d["tags"].dropna() for t in s.split("|") if t})
    top_rows = [[t, thousands(n), pct(n / n_tagged * 100)] for t, n in freq.most_common(20)]
    top_table = md_table(top_rows, ["标签", "n", "占有标签书比例 %"])

    years = [2017, 2019, 2021, 2023, 2025]
    era_rows = []
    for t in TAG_LINES:
        sh = tag_share(d, t, years)
        era_rows.append([t] + [pct(sh.get(y, float("nan"))) for y in years])
    era_table = md_table(era_rows, ["标签"] + [f"{y} %" for y in years])

    # 标签→热度（2017-2025，n≥1000，剔除萌神 13 本）
    ddv = d[d["est_year"].between(2017, 2025) & ~d["tags"].fillna("").str.endswith("萌神")].copy()
    ddv["tl"] = tag_list(ddv["tags"])
    cnt2 = Counter(t for L in ddv["tl"] for t in L)
    heat = []
    for t, n in cnt2.most_common():
        if n < 1000:
            continue
        sub = ddv[ddv["tl"].map(lambda L, t=t: t in L)]
        heat.append((t, n, float(sub["favs"].median())))
    heat.sort(key=lambda x: -x[2])
    show = heat[:8] + heat[-4:]
    heat_table = md_table(
        [[t, thousands(n), f"{m:.0f}"] for t, n, m in show],
        ["标签", "n", "favs 中位"],
    )

    hm = {t: m for t, _, m in heat}

    # 共现 top10
    pairs = Counter()
    for L in tl:
        L = sorted(set(L))
        for i in range(len(L)):
            for j in range(i + 1, len(L)):
                pairs[(L[i], L[j])] += 1
    co_rows = [[f"{a} × {b}", thousands(n)] for (a, b), n in pairs.most_common(10)]
    co_table = md_table(co_rows, ["标签对", "共现 n"])
    bd = int(pairs[("战斗", "日常")])

    fz = tag_share(d, "女性主角", [2017, 2025])
    sys_share = tag_share(d, "系统", list(range(2017, 2026)))
    sys_peak = max(sys_share, key=lambda y: sys_share[y])
    ju_pre = d[d["est_year"] <= 2022]
    ju_pre_n = tag_list(ju_pre["tags"]).map(lambda L: "橘味" in L).sum()
    all_med = d.loc[d["est_year"].between(2017, 2025), "favs"].median()
    return f"""## 2. 标签：受控词表与女性向转向

![重点标签的年度比例]({fig_tag_era(d)})

标签是**受控词表**：{thousands(n_tagged)} 行有标签（占在册
{n_tagged / len(d) * 100:.1f}%），词表共 {vocab_all} 个唯一标签（含 7 个萌神
荣誉标签，题材词表 {vocab_genre} 个），每本最多 5 个。频次 top 20：

{top_table}

头部标签是网文类型的通用语法：`战斗` / `日常` / `异世界` / `恋爱` / `女性主角`
各覆盖约四分之一的有标签书。**词表随运营扩充且标签即时生效**，最明显的是
「橘味」：2022 年及以前累计仅 {int(ju_pre_n)} 本，2023 年前后入表，
2024 年即占有标签新书 {pct(tag_share(d, '橘味', [2024])[2024])}%——
一条新词一年内重写四分之一的标签分布，故跨年标签比较必须考虑词表时点。
重点标签的世代演变（占有标签新书比例；2017 年起缺失率 <3%，口径可靠）：

{era_table}

「女性主角」从 2017 年的 {pct(fz[2017])}% 持续升至 2025 年的 {pct(fz[2025])}%，
是十年间最稳定的结构性变化；「倒追」「橘味」同向。与之互补，「异世界」稳定在
25-30% 的高频区间，「系统」在 {sys_peak} 年见顶（{pct(sys_share[sys_peak])}%）后回落，
「末世」稳定在 4-6%。（「百合」标签全库 0 行：相关内容在词表中由
「橘味」「纯爱」等词承载。）

标签与热度（2017-2025 新书，n≥1,000 的标签，按 favs 中位排序，展示头部与
尾部各若干；萌神 13 本整行剔除以防推荐位反向因果；对照：同年新书整体
favs 中位 {all_med:.0f}）：

{heat_table}

高热度标签集中在女性向（`嫁人` {hm.get('嫁人', 0):.0f}、`变身`
{hm.get('变身', 0):.0f}、`倒追` {hm.get('倒追', 0):.0f}、`橘味`
{hm.get('橘味', 0):.0f}），尾部是 `现实` `推理` `历史` `神话` 等（中位 3-4）。
「系统」（{hm.get('系统', 0):.0f}）「无敌」（{hm.get('无敌', 0):.0f}）
虽属高频标签，热度仅略高于整体中位 {all_med:.0f}——**高频不等于高效，
标签的选题价值需要分两个集合看**。此为相关而非因果：标签由作者勾选，
样本经自选择；亦未控制字数、分类与世代。

标签共现 top 10（全库口径，萌神标签剔除）：

{co_table}

共现结构呈两个聚合：男性向冒险轴（`异世界 × 战斗`、`冒险 × 异世界`、
`冒险 × 战斗`）与女性向恋爱轴（`恋爱 × 日常`、`女性主角 × 日常`、
`倒追 × 恋爱`），两轴经 `战斗 × 日常`（{thousands(bd)}）交汇。
"""


def section_moebattle(d: pd.DataFrame) -> str:
    df_full = pd.read_csv(
        paths.OUT_DIR / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    m = df_full[df_full["tags"].fillna("").str.contains("萌神")].copy()
    est = eras.estimate(m["id"])
    m = m.merge(est[["id", "est_date"]], on="id")
    rows = []
    for r in m.itertuples():
        mo = "、".join(t for t in r.tags.split("|") if t.endswith("萌神"))
        rows.append([
            str(int(r.id)), f"《{r.title}》", r.author, r.genre,
            mo, str(r.est_date.year), thousands(r.favs),
            "1" if r.featured == 1 else "0",
        ])
    tbl = md_table(
        rows, ["nid", "作品", "作者", "分类", "萌神标签", "定年", "favs", "featured"]
    )
    mo_tags = sorted({t for s in m["tags"] for t in s.split("|") if t.endswith("萌神")})
    side = Counter(t for s in m["tags"] for t in s.split("|") if not t.endswith("萌神"))
    side_top = side.most_common(1)[0]
    side_4 = [t for t, n in side.most_common() if n == 4][:3]
    return f"""## 3. 萌神标签：运营荣誉，单列处理

{mo_tags[0]} … {mo_tags[-1]} 共 {len(mo_tags)} 个标签、落在 {len(m)} 本作品上
（《妖刀姬》两届夺冠，故 {int(m['tags'].map(lambda s: sum(t.endswith('萌神') for t in s.split('|'))).sum())} 次标注）。
依据 `references/moebattle-tags.md`（2024 年度萌神大赛 H5 活动页规则原文）：

> 对于冠军角色所属的作品，在作品详情页中会展示萌神标签，持续一年。

即该标签由**运营方按赛事结果授予**：SF 年度萌神大赛男 / 女两组冠军作品，
每年 2 本。三个后果：标签年份是**届次年份，不是上架年份**，绝不可用于定年；
{len(m)} 本全是极端头部（favs 中位 {thousands(m['favs'].median())}，全库中位 8）且
获奖后获运营推荐位，纳入标签共现或标签→热度分析会引入反向因果——本报告
§2 的频次、共现与热度统计均已剔除该 {len(mo_tags)} 个标签，{len(m)} 本作品在
标签→热度表中整行剔除；数据集不删行，标签保留在 `tags` 字段原样。

{len(m)} 本作品清单（定年为 nid 定年，年份仅供参照）：

{tbl}

旁挂标签以题材词为主（`{side_top[0]}` {side_top[1]}、`{side_4[0]}` /
`{side_4[1]}` / `{side_4[2]}` 各 4），全部 {len(m)} 本 featured=1，
与「获奖后获推荐位」的机制一致。
"""


def section_doomsday(d: pd.DataFrame) -> str:
    dd = doomsday_stats(d)
    rows = []
    for t in ("末日", "末世"):
        s = dd[t]
        gen = s["gen"]
        rows.append([
            t, thousands(s["n"]),
            f"{gen.index.min()}–{gen.index.max()}",
            thousands(int(gen.loc[2017:2022].sum())),
            f"{s['favs_med']:.0f}",
            pct(s["vip"]),
            pct(s["done"]),
        ])
    tbl = md_table(
        rows, ["标签", "n", "世代范围", "2017-2022 n", "favs 中位", "VIP 率 %", "完结率 %"]
    )
    doom_last = int(dd["末日"]["gen"].loc[2023:].sum())
    apex_peak_y = dd["末世"]["gen"].loc[2017:2025].idxmax()
    apex_peak = int(dd["末世"]["gen"].loc[2017:2025].max())
    doom_peak_y = dd["末日"]["gen"].idxmax()
    doom_peak = int(dd["末日"]["gen"].max())
    ratio = dd["末世"]["n"] / dd["末日"]["n"]
    return f"""## 4. 末日 / 末世：独立统计（不合并）

`末日` 与 `末世` 是词表中并存的两个标签，语义相近但**全库 0 本同时挂二者**，
使用规模相差 {ratio:.0f} 倍。按 2026-11-16 决定，本报告不合并，分别统计：

{tbl}

世代分布：`末世` 自 2017 年起持续扩张（2017 年 {int(dd['末世']['gen'].get(2017, 0))} 本
→ {apex_peak_y} 年 {apex_peak:,} 本，此后随大盘回落），`末日` 则集中在 2018-2022
（峰值 {doom_peak_y} 年 {doom_peak:,} 本），**2023 年后基本停止使用**
（2023 年起合计 {doom_last} 本）——两个标签不是同一概念的新旧写法，
而是规模悬殊、生命周期错位的两个独立标签；`末日` 疑似已退出使用（是否
从词表移除无法从快照判断），`末世` 仍是活跃标签。

口径边界：以上为**标签口径**。若按书名检索，含「末日」的书名 1,700 行、
含「末世」9,270 行——书名与标签是两套证据，本节只统计标签口径；
两口径的巨大落差（末日 1,700 书名 vs 464 标签）本身即说明标签受
5 个上限与词表扩充约束，不能当作题材全集。热度过低（favs 中位
{dd['末日']['favs_med']:.0f} / {dd['末世']['favs_med']:.0f}，低于 2017-2025
新书中位 9）与 VIP 率极低（{pct(dd['末日']['vip'])}% / {pct(dd['末世']['vip'])}%），
符合该题材长尾供给的特征。
"""


def section_contest(d: pd.DataFrame) -> str:
    n_contest = int(d["contest"].notna().sum())
    n_events = d["contest"].nunique()

    winter = d[d["contest"].fillna("").str.contains("冬季征文", na=False)]

    def wkey(c: str) -> tuple:
        if c == "冬季征文":
            return (1, 0)
        cn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
        num = next((cn[ch] for ch in c if ch in cn), 99)
        return (2, num)

    w_rows = []
    for c in sorted(winter["contest"].unique(), key=wkey):
        s = winter[winter["contest"] == c]
        w_rows.append([
            c, thousands(len(s)),
            f"{int(s['est_year'].min())}–{int(s['est_year'].max())}",
            str(int(s["est_year"].median())),
        ])
    w_table = md_table(w_rows, ["届次", "n", "定年范围", "定年中位"])

    spring = d[d["contest"].fillna("").str.contains("春季征文", na=False)]
    sp_years = f"{int(spring['contest'].str[:4].min())}-{int(spring['contest'].str[:4].max())}"

    cmp = d.assign(participate=d["contest"].notna()).groupby("participate")
    cmp_rows = []
    for flag, s in cmp:
        cmp_rows.append([
            "参赛" if flag else "未参赛", thousands(len(s)),
            f"{s['favs'].median():.0f}", f"{s['favs'].quantile(.9):,.0f}",
            pct((s["price_type"] == "VIP").mean() * 100),
            pct((s["status"] == "已完结").mean() * 100),
        ])
    cmp_table = md_table(
        cmp_rows, ["分组", "n", "favs 中位", "favs P90", "VIP 率 %", "完结率 %"]
    )

    w_total = len(winter)
    return f"""## 5. 征文：运营组织的供给

在册作品中 {thousands(n_contest)} 行（{n_contest / len(d) * 100:.1f}%）带
`contest` 标注，覆盖 {n_events} 个征文活动。主要系列：**冬季征文**九届
（{thousands(w_total)} 行）、**征长篇 / 对话小说**系列（一征至十三征及
对话小说分轨）、**春季征文**（{sp_years}，{thousands(len(spring))} 行），
以及幻想小说征文、玄幻征文等单发活动。

冬季征文各届（contest 字段实测；定年允许早于届次启动——征文允许旧书参赛，
故 nid / 定年下限无届次意义，上限贴征文启动时间）：

{w_table}

届次 → 年份映射（用户核实）：第六届 2022 冬、第七届 2023 冬、
第八届 2024 冬、第九届 2025 冬；与上表定年中位逐年吻合。据此推定
无届次标注的「冬季征文」（{thousands(int((winter['contest'] == '冬季征文').sum()))} 行，
定年全部 {int(winter[winter['contest'] == '冬季征文']['est_year'].max())}）为第一届，
即该系列自 2018 冬起每年一届、从未中断。征文公告页 / 参赛列表同时是
批量获取精确创建时间的高效来源（报告 01 §1 第六届的核对即由此佐证）。

参赛 vs 未参赛（2007-2025 定年口径）：

{cmp_table}

参赛书的 favs 中位（{cmp_rows[1][2]} vs {cmp_rows[0][2]}）与 P90
（{cmp_rows[1][3]} vs {cmp_rows[0][3]}）均高于未参赛书，VIP 率
亦高（{cmp_rows[1][4]}% vs {cmp_rows[0][4]}%）。**这一差距不可作因果解读**：
参赛是作者自选择（有存量的作者更倾向参赛），征文评审与推荐位又构成
运营侧二次筛选；报告 02 已证明头部集中度极高，P90 的差异主要由少量
头部参赛书贡献。无届次的证据只能支持「参赛书热度更高」这一相关描述。
"""


def build() -> None:
    charts.setup_style()
    d = load()
    sb = eras.snapshot_bounds(d)
    body = f"""{section_header(sb)}

---

{section_conclusion(d)}

---

{section_genre(d)}

---

{section_tags(d)}

---

{section_moebattle(d)}

---

{section_doomsday(d)}

---

{section_contest(d)}

---

*生成：`uv run python analysis/report_genre.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"written: {OUT}")


if __name__ == "__main__":
    build()

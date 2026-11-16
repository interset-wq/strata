"""生成 analysis/reports/05_lifecycle_stock.md：作品生命周期与存量结构。

数据只到「书」这一层，没有章节与读者事件，因此本报告不做「读者行为」推断，
只回答三个由现有字段直接支撑的问题：

1. `status` 的「已完结」到底指什么——它混合了速更短篇与长篇连载完成；
2. `status` 的「连载中」到底指什么——构建时断更已并入连载中，活跃度须另算；
3. 收藏是存量，存量书架的注意力固化到什么程度。

所有数字现算自 analysis/out/novels.csv（原始 jsonl 的派生表），年份由
analysis/eras.py 定年；活跃度基准是数据内容上界（eras.snapshot_bounds）。
报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/report_lifecycle.py
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

OUT = Path(__file__).resolve().parent / "reports" / "05_lifecycle_stock.md"

GENRE_ORDER = ["魔幻", "校园", "玄幻", "古风", "都市", "同人", "游戏", "科幻", "悬疑"]

# 完结时长分档（天）。span = updated_at − nid 定年创建日
SPAN_BANDS = [
    (0, 7, "0–7 天"),
    (8, 30, "8–30 天"),
    (31, 90, "31–90 天"),
    (91, 364, "91–364 天"),
    (365, 10 ** 9, "≥365 天"),
]

# 断更时长分档（末次更新距内容上界）
STALE_BANDS = [
    (0, 90, "≤90 天"),
    (91, 365, "91–365 天"),
    (366, 730, "1–2 年"),
    (731, 10 ** 9, ">2 年"),
]


def load() -> pd.DataFrame:
    df = pd.read_csv(
        Path(__file__).resolve().parent / "out" / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id")
    sb = eras.snapshot_bounds(d)
    d["upd"] = pd.to_datetime(d["updated_at"], errors="coerce")
    # 末次更新距内容上界：断更时长（不依赖定年，故不受定年误差影响）
    d["stale"] = eras.staleness_days(d, sb["content_end"])
    # 完结时长：末次更新 − nid 定年创建日（依赖定年，low 段有月级误差）
    d["span"] = (d["upd"] - d["est_date"]).dt.days
    d["fast"] = (d["status"] == "已完结") & d["span"].between(0, 7)
    d["mid_done"] = (d["status"] == "已完结") & d["span"].between(8, 364)
    d["long_done"] = (d["status"] == "已完结") & (d["span"] >= 365)
    d["neg_done"] = (d["status"] == "已完结") & (d["span"] < 0)
    d["band"] = pd.cut(
        d["stale"], bins=[b[0] for b in STALE_BANDS] + [STALE_BANDS[-1][1] + 1],
        labels=[b[2] for b in STALE_BANDS], right=True,
    )
    return d


def pct(x: float) -> str:
    return f"{x:.1f}"


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------- 图表


def fig_completion_bands(d: pd.DataFrame) -> str:
    """完结时长分档：作品数占比与收藏中位（双轴）。"""
    fin = d[d["status"] == "已完结"]
    neg = int((fin["span"] < 0).sum())
    counts, favs, labels = [], [], []
    for lo, hi, name in SPAN_BANDS:
        s = fin[fin["span"].between(lo, hi)]
        counts.append(len(s))
        favs.append(s["favs"].median() if len(s) else np.nan)
        labels.append(name)

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    x = np.arange(len(labels))
    share = np.array(counts) / len(fin) * 100
    ax.bar(x, share, width=0.62, color=charts.C["blue"], zorder=3)
    for i, (c, s) in enumerate(zip(counts, share)):
        ax.text(i, s - 0.8, f"{c:,}", ha="center", va="top", fontsize=7.5, color="white", zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("占已完结作品比重（%）")
    ax.set_ylim(0, max(share) * 1.30)
    ax.set_xlabel("完结时长（末次更新 − 定年创建日）")

    ax2 = ax.twinx()
    ax2.plot(x, favs, "o-", color=charts.C["red"], lw=1.4, ms=5, zorder=6)
    for i, f in enumerate(favs):
        if not np.isnan(f):
            ax2.annotate(f"{f:,.0f}", (i, f), textcoords="offset points",
                         xytext=(0, 9), ha="center", fontsize=7.5, color=charts.C["red"],
                         zorder=7,
                         bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
    ax2.set_yscale("log")
    ax2.set_ylim(2, 4500)
    ax2.set_ylabel("该档收藏数中位（对数轴）")
    ax2.grid(False)
    ax.text(0.015, 0.985, f"已完结 {len(fin):,} 本；另有 {neg:,} 本因定年误差不可分档（未计入）",
            transform=ax.transAxes, ha="left", va="top", fontsize=7.5, color="#666666")
    return charts.save(fig, "05_completion_bands.png")


def fig_done_decomp(d: pd.DataFrame) -> str:
    """按定年：完结率的来源构成（堆叠）+ 总完结率折线。"""
    y = d[d["est_year"].between(2007, 2025)]
    g = y.groupby("est_year")
    total = g["status"].apply(lambda s: (s == "已完结").mean() * 100)
    fast = g["fast"].mean() * 100
    mid = g["mid_done"].mean() * 100
    longd = g["long_done"].mean() * 100
    neg = g["neg_done"].mean() * 100
    yrs = total.index.to_numpy()

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.bar(yrs, fast, width=0.68, color=charts.C["green"], zorder=3, label="速更（0–7 天完结）")
    ax.bar(yrs, mid, width=0.68, bottom=fast, color="#66CCEE", zorder=3, label="中速（8–364 天完结）")
    ax.bar(yrs, longd, width=0.68, bottom=fast + mid, color=charts.C["red"], zorder=3, label="长篇（≥365 天完结）")
    ax.bar(yrs, neg, width=0.68, bottom=fast + mid + longd, color="#BBBBBB", zorder=3,
           label="定年误差不可分")
    ax.plot(yrs, total, "o-", color=charts.C["blue"], lw=1.4, ms=3.5, zorder=5,
            label="总完结率（= 堆叠高度）")
    charts.shade_periods(ax, yrs)
    ax.set_xlim(2006.5, 2025.5)
    ax.set_ylim(0, max(total) * 1.25)
    ax.set_ylabel("占该年作品比重（%）")
    ax.set_xticks(list(range(2008, 2026, 2)))
    ax.legend(frameon=False, fontsize=7, loc="upper center",
              bbox_to_anchor=(0.5, -0.16), ncol=5)
    ax.axvline(2021.5, color="#999999", lw=0.8, ls=":")
    ax.text(2010.0, 0.82, "2022 起该年作品未满 4 年，长篇完结率受右删失",
            transform=ax.get_xaxis_transform(), fontsize=7, color="#666666", va="top")
    return charts.save(fig, "05_done_decomp.png")


def fig_stock_attention(d: pd.DataFrame) -> str:
    """断更分档：作品占比 vs 收藏份额（存量固化）。"""
    total_favs = d["favs"].sum()
    rows = []
    for lo, hi, name in STALE_BANDS:
        s = d[d["stale"].between(lo, hi)]
        rows.append((name, len(s), len(s) / len(d) * 100, s["favs"].sum() / total_favs * 100))

    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    w = 0.36
    ax.bar(x - w / 2, [r[2] for r in rows], width=w, color=charts.C["blue"], zorder=3, label="作品数占比")
    ax.bar(x + w / 2, [r[3] for r in rows], width=w, color=charts.C["red"], zorder=3, label="收藏份额")
    for i, r in enumerate(rows):
        ax.text(i - w / 2, r[2] + 1.2, f"{r[2]:.1f}%", ha="center", fontsize=7.5, color="#333333")
        ax.text(i + w / 2, r[3] + 1.2, f"{r[3]:.1f}%", ha="center", fontsize=7.5, color="#333333")
    ax.set_xticks(x)
    ax.set_xticklabels([r[0] for r in rows], fontsize=8)
    ax.set_ylabel("占比（%）")
    ax.set_ylim(0, max(max(r[2] for r in rows), max(r[3] for r in rows)) * 1.18)
    ax.set_xlabel("末次更新距内容上界（断更时长）")
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    return charts.save(fig, "05_stock_attention.png")


# ---------------------------------------------------------------- 各节


def section_header(d: pd.DataFrame, sb: dict) -> str:
    n_fin = int((d["status"] == "已完结").sum())
    return f"""# 05 · 作品生命周期：完结的二元结构、断更存量与注意力固化

> 口径声明：
> 1. 数据源 `analysis/out/novels.csv`，{len(d):,} 行（原始 jsonl 的派生表），
>    数据内容上界 {sb['date']}，在册存活口径；年份由 nid 定年（锚点插值，
>    报告 01 §1），非 `updated_at`。
> 2. **「连载中」不等于在更**：构建时把「断更」并入「连载中」（判据见
>    `analysis/config.py` 的 status 清洗规则），故状态字段不含任何活跃度信息。
>    本报告的活跃度一律由 `updated_at` 相对内容上界的间隔推导（断更时长），
>    不依赖定年，因而也不受定年误差影响。
> 3. **「已完结」是两种东西**：{n_fin:,} 本已完结作品里，近三成在 7 天内完结、
>    字数中位仅四千余字——那是速更短篇，不是长篇连载的完成。故「完结率」不能
>    单读，必须与完结时长联读（§1、§2）。
> 4. 完结时长 = `updated_at` − nid 定年创建日。定年在 low 段有月级误差（报告 01 §1），
>    {int(((d['status'] == '已完结') & (d['span'] < 0)).sum()):,} 本已完结作品因
>    定年晚于其唯一一次更新时间而无法分档，本报告单列不并入任何档位。
> 5. 收藏是存量：跨时点不可比（报告 02 口径 2）。本报告只比较**同一存量结构内**
>    的份额，不作跨世代的水平比较，也不把相关性读作因果。
> 6. 分类与标签均为作者自选择（报告 04 口径 2、7）；运营位（featured）是当前态，
>    与热度的因果方向不可从快照判定。
> 7. 本报告不含任何读者侧推断：数据集只有书层字段，没有章节、评论或用户事件，
>    「注意力」一词仅指 `favs` / `clicks` / `praises` 三个计数器。"""


def section_conclusion(d: pd.DataFrame) -> str:
    fin = d[d["status"] == "已完结"]
    neg = int((fin["span"] < 0).sum())
    fast = int(d["fast"].sum())
    longd = int(d["long_done"].sum())
    y = d[d["est_year"].between(2007, 2025)]
    g = y.groupby("est_year")
    total = g["status"].apply(lambda s: (s == "已完结").mean() * 100)
    fastr = g["fast"].mean() * 100
    midr = g["mid_done"].mean() * 100
    longr = g["long_done"].mean() * 100
    y2018, y2020, y2021 = total.loc[2018], total.loc[2020], total.loc[2021]
    l2016, l2021 = longr.loc[2016], longr.loc[2021]
    d_total = y2020 - y2018
    d_fast = fastr.loc[2020] - fastr.loc[2018]
    d_mid = midr.loc[2020] - midr.loc[2018]
    d_long = longr.loc[2020] - longr.loc[2018]
    ong = d[d["status"] == "连载中"]
    act90 = int((ong["stale"] <= 90).sum())
    dead90 = int((ong["stale"] > 365).sum())
    total_favs = d["favs"].sum()
    stale1y = d[d["stale"] > 365]
    live90 = d[d["stale"] <= 90]
    fan = d[d["genre"] == "同人"]
    fan_act = (fan["stale"] <= 90).mean() * 100
    fan_favs = fan["favs"].median()
    other_act = d[d["genre"] != "同人"]["stale"].pipe(lambda s: (s <= 90).mean() * 100)
    return f"""## 0. 结论

1. **「完结」是二元结构，完结率是混合量**。{len(fin):,} 本已完结作品中，
   {fast:,} 本（{fast / len(fin) * 100:.1f}%）在 7 天内完结、字数中位
   {fin[fin['span'].between(0, 7)]['words'].median():,.0f} 字、收藏中位
   {fin[fin['span'].between(0, 7)]['favs'].median():.0f}——这是速更短篇；
   真正连载一年以上才完结的只有 {longd:,} 本（{longd / len(fin) * 100:.1f}%），
   字数中位 {fin[fin['span'] >= 365]['words'].median():,.0f} 字、收藏中位
   {fin[fin['span'] >= 365]['favs'].median():,.0f}。另有 {neg:,} 本同属「一次上传
   即定稿」形态、但因定年误差无法定档；若一并计入，速更形态合计占已完结作品
   {(fast + neg) / len(fin) * 100:.1f}%。全库「完结率
   {(d['status'] == '已完结').mean() * 100:.1f}%」若不拆开读，会把一次性投稿
   当成长篇完成度。
2. **2019–2021 完结率的抬升来自短周期完结，长篇完结率同期在可比队列里已下滑**。
   总完结率 {y2018:.1f}%（2018）→ {y2020:.1f}%（2020）→ {y2021:.1f}%（2021），
   两年增量 {d_total:+.1f} 个百分点中，一年内完结贡献
   {d_fast + d_mid:+.1f}（速更 {d_fast:+.1f}、中速 {d_mid:+.1f}），
   长篇完结率只贡献 {d_long:+.1f}；而长篇完结率从 2016 年峰值 {l2016:.1f}%
   降到 2021 年 {l2021:.1f}%。平台「完成度」指标的上升与长篇连载的推进不是同一件事。
3. **「连载中」名不副实**：{len(ong):,} 本连载中作品里，{dead90:,} 本
   （{dead90 / len(ong) * 100:.1f}%）已断更超过一年，近 90 天仍有更新的只有
   {act90:,} 本（{act90 / len(ong) * 100:.1f}%）。全库层面，末次更新距内容上界
   不超过 90 天的作品仅 {len(live90):,} 本（{len(live90) / len(d) * 100:.1f}%）。
4. **收藏是存量资产，且高度固化**：断更超过一年的 {len(stale1y):,} 本作品
   （占 {len(stale1y) / len(d) * 100:.1f}%）持有全库
   {stale1y['favs'].sum() / total_favs * 100:.1f}% 的收藏；近 90 天在更的
   {len(live90):,} 本只占 {live90['favs'].sum() / total_favs * 100:.1f}%。
   新书几乎撬不动存量——2025 年新建的 {int((d['est_year'] == 2025).sum()):,} 本
   仅占全库收藏的 {d[d['est_year'] == 2025]['favs'].sum() / total_favs * 100:.1f}%。
5. **同人是「一次性投稿」货架**：该类近 90 天活跃率仅 {fan_act:.2f}%
   （全库其余类别 {other_act:.2f}%），速更完结占比最高，收藏中位
   {fan_favs:.0f} 却远高于其余类别——热度来自集中爆发，而非持续连载。
6. **由此产生的读法修正**：报告 01 的完结率、报告 02 的收藏集中、报告 03 的
   作者留存，都应读作「存量书架的当前状态」，而不是「当年的创作表现」。"""


def section_completion(d: pd.DataFrame) -> str:
    fin = d[d["status"] == "已完结"]
    neg = int((fin["span"] < 0).sum())
    rows = []
    for lo, hi, name in SPAN_BANDS:
        s = fin[fin["span"].between(lo, hi)]
        rows.append([
            name, thousands(len(s)), pct(len(s) / len(fin) * 100),
            thousands(s["words"].median()) if len(s) else "—",
            f"{s['favs'].median():.0f}" if len(s) else "—",
            f"{s['clicks'].median():,.0f}" if len(s) else "—",
        ])
    table = md_table(
        rows, ["完结时长", "本数", "占已完结%", "字数中位", "收藏中位", "浏览中位"]
    )
    fast = fin[fin["span"].between(0, 7)]
    longd = fin[fin["span"] >= 365]
    return f"""## 1. 「完结」是两种东西

状态字段的「已完结」不区分作品体量与连载时长。把已完结作品按**完结时长**
（末次更新 − nid 定年创建日）分档后，两类作品的画像几乎没有重叠：

{table}

另有 {neg:,} 本已完结作品的定年晚于其唯一一次更新时间（多为一次上传即定稿的
速更短篇，low 段月级定年误差足以翻转符号），无法分档，单列不并入。

- **速更档（0–7 天）**：{len(fast):,} 本，字数中位 {fast['words'].median():,.0f} 字、
  收藏中位 {fast['favs'].median():.0f}、浏览中位 {fast['clicks'].median():,.0f}。
  它们在平台上留下的痕迹接近「一条动态」，而不是一个可运营的内容资产。
- **长篇档（≥365 天）**：{len(longd):,} 本，字数中位 {longd['words'].median():,.0f} 字、
  收藏中位 {longd['favs'].median():,.0f}、浏览中位 {longd['clicks'].median():,.0f}。

两档收藏中位相差约 {longd['favs'].median() / max(fast['favs'].median(), 1):.0f} 倍。
因此「完结率 {pct((d['status'] == '已完结').mean() * 100)}%」这一全库指标，
若不同时给出完结时长分布，会把「一次性投稿」与「长篇写完」读成同一件事。

![完结时长分档](figures/05_completion_bands.png)"""


def section_decomp(d: pd.DataFrame) -> str:
    y = d[d["est_year"].between(2007, 2025)]
    g = y.groupby("est_year")
    total = g["status"].apply(lambda s: (s == "已完结").mean() * 100)
    fast = g["fast"].mean() * 100
    mid = g["mid_done"].mean() * 100
    longd = g["long_done"].mean() * 100
    neg = g["neg_done"].mean() * 100
    rows = []
    for yr in total.index:
        n = int((y["est_year"] == yr).sum())
        rows.append([
            str(int(yr)), thousands(n), pct(total.loc[yr]),
            pct(fast.loc[yr] + mid.loc[yr]), pct(fast.loc[yr]),
            pct(mid.loc[yr]), pct(longd.loc[yr]), pct(neg.loc[yr]),
        ])
    table = md_table(
        rows, ["定年", "作品数", "总完结率%", "一年内完结%", "其中速更(0–7天)%",
               "中速(8–364天)%", "长篇(≥365天)%", "定年不可分%"]
    )
    d_total = total.loc[2020] - total.loc[2018]
    d_fast = fast.loc[2020] - fast.loc[2018]
    d_mid = mid.loc[2020] - mid.loc[2018]
    d_long = longd.loc[2020] - longd.loc[2018]
    share = (fast.loc[2020] + mid.loc[2020] - fast.loc[2018] - mid.loc[2018]) / d_total * 100
    return f"""## 2. 完结率的结构性来源：短周期涌入，长篇停滞

按定年把完结按**完结时长**拆成四档后，「完结率」的走势可以被解释：

{table}

- **总完结率**在 2018 年 {total.loc[2018]:.1f}% → 2020 年 {total.loc[2020]:.1f}%
  → 2021 年 {total.loc[2021]:.1f}%，在扩张期达到高位。
- 2018→2020 的 {d_total:+.1f} 个百分点增量中，**一年内完结贡献
  {d_fast + d_mid:+.1f}（占 {share:.0f}%）**，其中速更 {d_fast:+.1f}、
  中速 {d_mid:+.1f}；长篇完结率只贡献 {d_long:+.1f}。
- 而在**可比队列**（2018 年及以前，均已满 4 年）里，长篇完结率从 2016 年峰值
  {longd.loc[2016]:.1f}% 降到 2017 年 {longd.loc[2017]:.1f}%、
  2018 年 {longd.loc[2018]:.1f}%，已在下滑；2021 年 {longd.loc[2021]:.1f}%
  同受右删失影响而不可直接比较。
- 2022 年起该年作品未满 4 年，长篇完结率被压低，与实际推进程度无关；
  跨世代比较只对 2018 年及以前的队列有效（口径 4）。

即：扩张期的「完成度上升」是**投稿结构变化**（短篇与同人向作品涌入），
不是**长篇连载能力提升**。两个变量在原始完结率里被合并，方向甚至相反。

![完结率结构分解](figures/05_done_decomp.png)"""


def section_active(d: pd.DataFrame) -> str:
    ong = d[d["status"] == "连载中"]
    fin = d[d["status"] == "已完结"]
    rows = []
    for lo, hi, name in STALE_BANDS:
        s1 = int(ong["stale"].between(lo, hi).sum())
        s2 = int(fin["stale"].between(lo, hi).sum())
        rows.append([name, thousands(s1), pct(s1 / len(ong) * 100),
                     thousands(s2), pct(s2 / len(fin) * 100)])
    table = md_table(rows, ["断更时长", "连载中本数", "占连载中%", "已完结本数", "占已完结%"])
    act90 = int((ong["stale"] <= 90).sum())
    dead = int((ong["stale"] > 365).sum())
    live90 = d[d["stale"] <= 90]
    return f"""## 3. 「连载中」不等于在更

构建时「断更」被并入「连载中」（状态清洗规则见 `analysis/config.py`），因此
状态字段不含活跃度信息。用 `updated_at` 相对内容上界重新度量：

{table}

- **{len(ong):,} 本「连载中」作品里，{dead:,} 本（{dead / len(ong) * 100:.1f}%）
  已断更超过一年**，近 90 天仍有更新的只有 {act90:,} 本（{act90 / len(ong) * 100:.1f}%）。
- 全库层面，末次更新距内容上界 ≤90 天的作品只有 {len(live90):,} 本
  （{len(live90) / len(d) * 100:.1f}%），却要承担 {live90['favs'].sum() / d['favs'].sum() * 100:.1f}%
  的收藏。
- 已完结作品里仍有 {int((fin['stale'] <= 365).sum()):,} 本在一年内被编辑过
  （{int((fin['stale'] <= 365).sum()) / len(fin) * 100:.1f}%）——完结并非不可动，
  修订与重上架仍在发生。

因此「连载中」应读作**未标记完结**，而不是「在更」。任何以状态字段为分母的
供给或留存指标，都需要先按断更时长重新切分。"""


def section_stock(d: pd.DataFrame) -> str:
    total_favs = d["favs"].sum()
    rows = []
    for lo, hi, name in STALE_BANDS:
        s = d[d["stale"].between(lo, hi)]
        rows.append([
            name, thousands(len(s)), pct(len(s) / len(d) * 100),
            pct(s["favs"].sum() / total_favs * 100),
            f"{s['favs'].median():.0f}",
        ])
    table = md_table(rows, ["断更时长", "本数", "作品占比%", "收藏份额%", "收藏中位"])
    stale1y = d[d["stale"] > 365]
    live90 = d[d["stale"] <= 90]
    y2025 = d[d["est_year"] == 2025]
    peak = d[d["est_year"] == 2022]
    return f"""## 4. 存量注意力固化：新书撬不动存量

收藏是累积量，作品一旦停止更新，其收藏就固化在快照里不再变化。于是存量书架
的注意力分布，与「当下谁在写」几乎脱钩：

{table}

- **断更超过一年的 {len(stale1y):,} 本作品（{len(stale1y) / len(d) * 100:.1f}%）
  持有全库 {stale1y['favs'].sum() / total_favs * 100:.1f}% 的收藏**；
- 近 90 天在更的 {len(live90):,} 本（{len(live90) / len(d) * 100:.1f}%）只占
  {live90['favs'].sum() / total_favs * 100:.1f}%；
- **2025 年新建的 {len(y2025):,} 本只占全库收藏的
  {y2025['favs'].sum() / total_favs * 100:.1f}%**，而 2022 年新建的
  {len(peak):,} 本已积累到 {peak['favs'].sum() / total_favs * 100:.1f}%。

存量与增量之间的时间差是结构性的：收藏的复利来自「写得久」，而不是「写得多」。
这解释了报告 02 观察到的头部集中——头部的位置在几年内很难被新书替换；
也意味着任何以收藏为目标的运营动作，面对的是一块**几乎不再流动**的存量。

![存量注意力分布](figures/05_stock_attention.png)"""


def section_genre(d: pd.DataFrame) -> str:
    total_favs = d["favs"].sum()
    rows = []
    for g in GENRE_ORDER:
        s = d[d["genre"] == g]
        rows.append([
            g, thousands(len(s)), pct((s["stale"] <= 90).mean() * 100),
            pct(s["fast"].mean() * 100), pct(s["long_done"].mean() * 100),
            pct(s["favs"].sum() / total_favs * 100),
            f"{s['favs'].median():.0f}", thousands(s["words"].median()),
        ])
    table = md_table(
        rows, ["分类", "本数", "近 90 天活跃%", "速更完结%", "长篇完结%", "收藏份额%", "收藏中位", "字数中位"]
    )
    fan = d[d["genre"] == "同人"]
    others = d[d["genre"] != "同人"]
    return f"""## 5. 九类的生命周期形态

{table}

- **同人**是极端的一次性货架：近 90 天活跃率 {pct((fan['stale'] <= 90).mean() * 100)}%
  为九类最低（其余类别 {pct((others['stale'] <= 90).mean() * 100)}%），
  速更完结率 {pct(fan['fast'].mean() * 100)}% 偏高，而收藏中位
  {fan['favs'].median():.0f} 远高于其余类别——一次性投稿 + 爆发式关注，
  与报告 04 的「免费二创货架」判断一致。
- **魔幻**同时是体量第一（{len(d[d['genre'] == '魔幻']):,} 本）与存量收藏第一
  （{pct(d[d['genre'] == '魔幻']['favs'].sum() / total_favs * 100)}%）的分类，
  活跃率 {pct((d[d['genre'] == '魔幻']['stale'] <= 90).mean() * 100)}% 属中游。
- **悬疑**体量最小（{len(d[d['genre'] == '悬疑']):,} 本）但速更完结率最高
  （{pct(d[d['genre'] == '悬疑']['fast'].mean() * 100)}%），形态上偏短平快。
- 九类的近 90 天活跃率整体都极低（{pct(min((d[d['genre'] == g]['stale'] <= 90).mean() * 100 for g in GENRE_ORDER))}%–{pct(max((d[d['genre'] == g]['stale'] <= 90).mean() * 100 for g in GENRE_ORDER))}%）；
  分类之间的真正差异不在活跃度，而在**存量收藏的沉淀速度**——同人活跃率最低却
  收藏中位最高（{fan['favs'].median():.0f}），悬疑两者皆低。"""


def section_limits(d: pd.DataFrame, sb: dict) -> str:
    n_low = int((d["confidence"] == "low").sum())
    return f"""## 6. 口径边界

1. **无读者侧数据**：数据集只有书层字段（无章节、无评论、无用户事件），
   本报告的「注意力」仅指 `favs` / `clicks` / `praises` 三个计数器；
   断更时长反映的是作品侧行为，不是读者行为。
2. **断更时长不依赖定年**（只用 `updated_at` 与内容上界），故不受 low 段
   {n_low:,} 本月级定年误差影响；完结时长依赖定年，已完结作品中有
   {int(((d['status'] == '已完结') & (d['span'] < 0)).sum()):,} 本因符号翻转无法分档，
   已单列。分档结论按档位表述，不作精确天数推断。
3. **状态字段经过清洗**：断更并入连载中、空状态整行剔除（`analysis/config.py`），
   在册口径下架作品不在库，越早的队列缺失越多。
4. **收藏不可跨时点比**：本报告只比较存量结构内的份额，不比较世代绝对量。
5. **自选择**：分类、标签、征文均由作者自行选择；活跃度与收藏的关联是相关而非因果。
6. **未解问题**：`updated_at` 记录的是最后一次章节更新，无法区分「多次更新后停更」
   与「一次上传即定稿」——速更档与断更档在字段上同构，只能借字数与状态交叉推断。"""


def build() -> None:
    charts.setup_style()
    d = load()
    sb = eras.snapshot_bounds(d)
    for fig in (fig_completion_bands, fig_done_decomp, fig_stock_attention):
        path = fig(d)
        print(f"写出 {OUT.parent / path}")

    body = f"""{section_header(d, sb)}

---

{section_conclusion(d)}

---

{section_completion(d)}

---

{section_decomp(d)}

---

{section_active(d)}

---

{section_stock(d)}

---

{section_genre(d)}

---

{section_limits(d, sb)}

---

*生成：`uv run python analysis/report_lifecycle.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"written: {OUT}")


if __name__ == "__main__":
    build()

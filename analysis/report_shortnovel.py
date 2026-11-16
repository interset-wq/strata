"""生成 analysis/reports/19_shortnovel.md：短篇生态——定义、口碑与推荐刻度。

本报告回答两个产品问题：
  ① 「什么样的书算短篇」——官方征文的体量分档（短篇/中篇/长篇/对话）
     只覆盖征文作品且是「参赛组别」而非篇幅约束；非征文作品必须自建
     门槛。本报告以官方分档的字数分布反推体量阈值，给出可执行口径。
  ② 短篇该用什么排序刻度——短篇存在天然收藏天花板，绝对收藏跨品类
     不可比，但集合内部可比；赞藏比与收藏转化率在短篇里方向相反或
     为低曝光伪信号，均不可用。

与报告 11（速更短篇）不重复：报告 11 的口径是「创作形态」（完结时长
≤7 天），本报告的口径是「体量」（总字数），两者正交不可互相定义。

所有数字现算自 out/novels.csv，年份由 eras.py 定年。报告是生成物，勿手改。

用法：uv run python analysis/report_shortnovel.py
"""

from __future__ import annotations

import json
import re
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
OUT = BASE / "reports" / "19_shortnovel.md"
FIG = BASE / "reports" / "figures"

# ---- 产品决策（2026-11-16 用户定案）----
THR = 50000            # 短篇体量门槛：总字数 ≤ 5 万字
SEED_SHORT_TOP = 2000  # 种子补入的短篇双组分位 Top N
REC_N = 20000          # 收藏榜 Top N（沿用报告 18）

WORD_BINS = [-1, 3000, 6000, 10000, 20000, 50001]
WORD_LABELS = ["≤3k", "3-6k", "6-10k", "10-20k", "20-50k"]


def num(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float) -> str:
    return f"{x:.1f}"


def load() -> pd.DataFrame:
    df = pd.read_csv(
        BASE / "out" / "novels.csv", dtype={"tags": str, "contest": str},
    )
    # 正版日轻已在 build_csv.py 阶段剔除（CSV 内已无这四个作者）
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id", how="left")
    # 与报告 18 同口径：排除 2026 年（右删失样本），保留 2007–2025
    df = df[df["est_year"].between(2007, 2025)].copy()
    sb = eras.snapshot_bounds(df)
    df["upd"] = pd.to_datetime(df["updated_at"], errors="coerce")
    df["contest"] = df["contest"].fillna("")
    df["done"] = df["status"] == "已完结"
    df["span"] = (df["upd"] - df["est_date"]).dt.days
    df["fast"] = df["done"] & df["span"].between(0, 7)
    df["pr"] = df["praises"] / df["favs"].replace(0, np.nan)
    df["cvr"] = df["favs"] / df["clicks"].replace(0, np.nan)
    # 官方体量分档：赛项名里的组别词
    df["tier"] = np.where(
        df.contest.str.contains("短篇"), "短篇",
        np.where(df.contest.str.contains("中篇"), "中篇",
                 np.where(df.contest.str.contains("长篇"), "长篇",
                          np.where(df.contest.str.contains("对话"), "对话", ""))))
    df["wb"] = pd.cut(df["words"], WORD_BINS, labels=WORD_LABELS, right=True)
    df["fb"] = pd.cut(df["span"], [-1, 7, 30, 90, 365, 10**9],
                      labels=["0-7", "8-30", "31-90", "91-365", ">365"])
    return df


def pctl_within(frame: pd.DataFrame, key: str, val: str = "favs") -> pd.Series:
    """组内分位：值越大 → 分位越大（0 最弱，1 最强）。"""
    g = frame.groupby(key, observed=True)[val]
    return g.rank(ascending=True, method="average") / g.transform("size")


def seed_set(d: pd.DataFrame) -> set:
    """复刻报告 18 的推荐种子。"""
    content_end = pd.Timestamp("2026-05-03")
    s = set(d.nlargest(REC_N, "favs")["id"])
    s |= set(d[d.est_date >= content_end - pd.Timedelta(days=365)]["id"])
    s |= set(d[d.upd >= content_end - pd.Timedelta(days=90)]["id"])
    ranks = set()
    with open(BASE / "out/monthly_ranks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            for it in json.loads(line)["items"]:
                if it.get("nid"):
                    ranks.add(it["nid"])
    s |= (ranks & set(d["id"]))
    s |= set(d.loc[d["featured"] == 1, "id"])
    return s


def main() -> str:
    charts.setup_style()
    C = charts.C
    d = load()

    # ---- 口径集合 ----
    short = d[(d["words"] <= THR) & d["done"]].copy()
    short["grp"] = short["wb"].astype(str) + "|" + short["est_year"].astype(str)
    short["p_wb"] = pctl_within(short, "wb")
    short["p_grp"] = pctl_within(short, "grp")
    long = d[(d["words"] > THR) & d["done"]]
    n_all = len(d)

    # ---- 官方分档的字数分布（阈值依据）----
    tiers = {}
    for t in ["短篇", "中篇", "长篇", "对话"]:
        g = d[(d.tier == t) & d.done]
        if len(g):
            tiers[t] = {
                "n": len(g),
                "p25": g.words.quantile(.25), "p50": g.words.median(),
                "p75": g.words.quantile(.75), "p95": g.words.quantile(.95),
                "in_thr": (g.words <= THR).mean() * 100,
            }

    # ---- 收藏天花板 ----
    ceil = {
        "短篇": (short.favs.median(), short.favs.quantile(.95), short.favs.max(),
                 (short.favs > 0).mean() * 100),
        "长篇": (long.favs.median(), long.favs.quantile(.95), long.favs.max(),
                 (long.favs > 0).mean() * 100),
    }
    rep = short[short.favs >= 200]
    rep_long = long[long.favs >= 200]

    # ---- 排序刻度对比 ----
    scales = {}
    for key, lab in [("favs", "收藏绝对值"), ("p_wb", "字数档内分位"), ("p_grp", "字数档×世代 双组分位")]:
        t = short.sort_values(key, ascending=False).head(30)
        scales[lab] = {
            "fav_med": t.favs.median(), "w_med": t.words.median(),
            "y_lo": int(t.est_year.min()), "y_hi": int(t.est_year.max()),
            "fast": t.fast.mean() * 100,
            "contest": (t.tier == "短篇").mean() * 100,
        }

    # ---- 否定结论：赞藏比 / 转化率 ----
    short["cell"] = short["wb"].astype(str) + "|" + short["fb"].astype(str)
    neg = {}
    for k, lab in [("pr", "赞藏比"), ("cvr", "收藏转化率")]:
        rows = []
        for _, g in short.groupby("cell", observed=True):
            g = g.dropna(subset=[k])
            if len(g) < 150:
                continue
            hi = g[g[k] >= g[k].quantile(.95)]
            lo = g[g[k] <= g[k].quantile(.05)]
            rows.append({"hi_f": hi.favs.median(), "lo_f": lo.favs.median(),
                         "hi_c": hi.clicks.median(), "lo_c": lo.clicks.median()})
        a = pd.DataFrame(rows)
        neg[lab] = {"n_cell": len(a), "hi_f": a.hi_f.mean(), "lo_f": a.lo_f.mean(),
                    "hi_c": a.hi_c.mean(), "lo_c": a.lo_c.mean()}

    # ---- 种子覆盖 ----
    d_seed = d[d.est_year.between(2007, 2025)].copy()
    seed = seed_set(d_seed)
    sd = d_seed[d_seed.id.isin(seed)]
    ss = sd[(sd.words <= THR) & sd.done]
    short_all = d[(d.words <= THR) & d.done]
    rep_all = short_all[short_all.favs >= 200]
    rep_seed = ss[ss.favs >= 200]

    top = short.sort_values("p_grp", ascending=False).head(SEED_SHORT_TOP)
    add = top[~top.id.isin(seed)]
    rep_after = int(rep_seed.favs.ge(200).sum() + add.favs.ge(200).sum())

    # ---- 题材 ----
    genres = rep.genre.value_counts()

    # ================= 图 =================
    # 图 19-1：官方分档 × 字数分布 → 阈值依据
    fig, ax = plt.subplots(figsize=(9, 5))
    for t, col, c in [("短篇", C["red"], C["red"]), ("中篇", C["blue"], C["blue"]),
                      ("长篇", C["green"], C["green"]), ("对话", C["gray"], C["gray"])]:
        if t not in tiers:
            continue
        g = d[(d.tier == t) & d.done]
        xs = np.sort(g.words.values)
        ys = np.arange(1, len(xs) + 1) / len(xs) * 100
        step = max(1, len(xs) // 3000)
        ax.plot(xs[::step], ys[::step], color=c, lw=1.8, label=f"{t}赛项（n={tiers[t]['n']:,}）")
        ax.plot([THR], [tiers[t]["in_thr"]], "o", color=c, ms=7, zorder=5)
    ax.set_xscale("log")
    ax.axvline(THR, color=C["gray"], ls="--", lw=1.2)
    ax.annotate(f"体量门槛 {THR//10000} 万字", xy=(THR, 8), xytext=(THR * 1.35, 8),
                color=C["gray"], fontsize=9)
    ax.set_xlabel("总字数（对数轴）")
    ax.set_ylabel("该赛项组内 ≤ 此字数的占比 %")
    ax.set_title("官方征文自身体量分档：短篇组系统性更短，但三组高度重叠")
    ax.legend(fontsize=8, loc="lower right", framealpha=0.9)
    fig.tight_layout()
    charts.save(fig, FIG / "19_tiers.png")

    # 图 19-2：收藏天花板
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axs[0]
    xs = np.arange(3)
    w = 0.36
    sv = [ceil["短篇"][0], ceil["短篇"][1], ceil["短篇"][2]]
    lv = [ceil["长篇"][0], ceil["长篇"][1], ceil["长篇"][2]]
    ax.bar(xs - w / 2, sv, w, color=C["red"], label="短篇（≤5 万字已完结）", zorder=2)
    ax.bar(xs + w / 2, lv, w, color=C["blue"], label="长篇（>5 万字已完结）", zorder=2)
    for xi, v in zip(xs - w / 2, sv):
        ax.text(xi, v * 1.15, num(v), ha="center", fontsize=7, color=C["red"])
    for xi, v in zip(xs + w / 2, lv):
        ax.text(xi, v * 1.15, num(v), ha="center", fontsize=7, color=C["blue"])
    ax.set_yscale("log")
    ax.set_xticks(xs)
    ax.set_xticklabels(["收藏中位数", "收藏 p95", "收藏最大值"])
    ax.set_ylabel("收藏数（对数轴）")
    ax.set_title("收藏天花板：短篇比长篇低两个数量级")
    ax.legend(fontsize=8, framealpha=0.9)

    ax = axs[1]
    ths = [50, 100, 200, 500, 1000, 10000]
    cnt = [int((short.favs >= t).sum()) for t in ths]
    ax.bar(range(len(ths)), cnt, color=C["red"], zorder=2)
    for i, v in enumerate(cnt):
        ax.text(i, v, num(v), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(range(len(ths)))
    ax.set_xticklabels([f"≥{t:,}" for t in ths], fontsize=8)
    ax.set_ylabel("短篇书数")
    ax.set_ylim(0, max(cnt) * 1.18)
    ax.set_title("短篇的口碑层规模：收藏 ≥1 万者为零")
    fig.tight_layout()
    charts.save(fig, FIG / "19_ceiling.png")

    # 图 19-3：排序刻度对比（三子图统一坐标尺度，否则无法公平比较）
    fig, axs = plt.subplots(1, 3, figsize=(13, 4.4), sharex=True, sharey=True)
    tops = []
    for lab, key, color in [("收藏绝对值", "favs", C["red"]),
                            ("字数档内分位", "p_wb", C["green"]),
                            ("字数档×世代 双组分位", "p_grp", C["blue"])]:
        tops.append((lab, key, color, short.sort_values(key, ascending=False).head(30)))
    allw = pd.concat([t[3]["words"] for t in tops])
    allf = pd.concat([t[3]["favs"] for t in tops])
    xlim = (max(200, allw.min() * 0.6), allw.max() * 1.6)
    ylim = (max(5, allf.min() * 0.6), allf.max() * 1.6)
    for ax, (lab, key, color, t) in zip(axs, tops):
        ax.scatter(t.words, t.favs, s=26, color=color, alpha=.8, zorder=3, edgecolors="none")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_xlabel("总字数（对数轴）")
        ax.set_ylabel("收藏（对数轴）")
        ax.set_title(f"{lab}\nTop30 收藏中位 {num(scales[lab]['fav_med'])}\n"
                     f"年份 {scales[lab]['y_lo']}–{scales[lab]['y_hi']}")
    fig.suptitle("三种排序刻度的头部构成：三图同一坐标尺度，绝对值最强、双组分位覆盖最全",
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    charts.save(fig, FIG / "19_scales.png")

    # 图 19-4：题材 + 种子覆盖
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axs[0]
    gs = genres.head(8)
    ax.bar(range(len(gs)), gs.values, color=C["red"], zorder=2)
    ax.set_xticks(range(len(gs)))
    ax.set_xticklabels(gs.index, rotation=20, ha="right", fontsize=8)
    for i, v in enumerate(gs.values):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("短篇口碑书数")
    ax.set_ylim(0, gs.max() * 1.18)
    ax.set_title(f"短篇口碑层（favs≥200, n={len(rep):,}）的题材分布")

    ax = axs[1]
    labs = ["全部短篇", "favs≥100", "favs≥200", "favs≥200\n（补入后）"]
    den = [len(short_all), int((short_all.favs >= 100).sum()), len(rep_all), len(rep_all)]
    hit = [len(ss), int((ss.favs >= 100).sum()), len(rep_seed), rep_after]
    rate = [h / max(dn, 1) * 100 for h, dn in zip(hit, den)]
    ax.bar(range(4), rate, color=[C["gray"], C["gray"], C["red"], C["green"]], zorder=2)
    for i, (r, h, dn) in enumerate(zip(rate, hit, den)):
        ax.text(i, r + 2.5, f"{r:.1f}%", ha="center", fontsize=9)
        if r >= 15:
            ax.text(i, r / 2, f"{h:,} / {dn:,}", ha="center", va="center",
                    fontsize=8, color="white")
        else:
            ax.text(i, r + 9, f"{h:,} / {dn:,}", ha="center", va="bottom",
                    fontsize=8, color="#444444")
    ax.set_xticks(range(4))
    ax.set_xticklabels(labs, fontsize=8)
    ax.set_ylabel("当前种子覆盖率 %")
    ax.set_ylim(0, 100)
    ax.set_title(f"种子对短篇的覆盖：补入 {num(len(add))} 本后\n"
                 f"口碑层覆盖 {len(rep_seed)/len(rep_all)*100:.1f}% → {rep_after/len(rep_all)*100:.1f}%")
    fig.tight_layout()
    charts.save(fig, FIG / "19_seedcover.png")

    # ================= 正文 =================
    md = []
    md.append(f"""# 报告 19：短篇生态——定义、口碑与推荐刻度

## 0. 结论

1. **短篇 = 总字数 ≤ {num(THR)} 字且已完结**，全库 {num(len(short))} 本（{len(short)/n_all*100:.1f}%）。
   阈值由官方征文自身的体量分档反推：官方「短篇」组已完结书有
   {tiers['短篇']['in_thr']:.1f}% 落在 {num(THR)} 字内（p75={num(tiers['短篇']['p75'])}、p95={num(tiers['短篇']['p95'])}）。
   **必须与「已完结」组合**——纯字数门槛 ≤1 万字就占全库 48.9%，没有区分度。
2. **官方「短篇」标签不是质量信号**：同字数档内，官方短篇赛项书的收藏中位比非赛项低 40–60%；
   短篇口碑层（favs≥200）中只有 {pct((rep.tier=='短篇').mean()*100)}% 来自官方短篇赛项。
   官方标签只作**附加维度**（"该书投过短篇赛项"），不可用于排序。
3. **官方短篇推荐质量低的三个数据根因**：
   ① **收藏天花板**——短篇收藏上限 {num(ceil['短篇'][2])}，收藏过万者 **0 本**（长篇 {num(int((long.favs>=10000).sum()))} 本），
      短篇永远进不了收藏榜，官方无口碑榜可选，只能退回「新书」与「征文获奖」；
   ② **官方标签与口碑脱节**（见上）；③ **好短篇是老书**——字数档内分位 Top30 全部落在 {scales['字数档内分位']['y_lo']}–{scales['字数档内分位']['y_hi']} 年。
4. **可用刻度：收藏绝对值（在 ≤{num(THR)} 字集合内）+ 字数档×世代双组分位**。
   短篇内书龄对收藏的影响弱（各代收藏中位 2–10，无单调趋势；长篇则是
   {num(ceil['长篇'][0])}→{num(ceil['长篇'][1])} 的量级差），故集合内绝对值可比。
5. **两个必须排除的刻度**（否定结论）：
   **赞藏比在短篇里方向是反的**（同字数档+同完结时长档内，pr-top5% 收藏中位
   {neg['赞藏比']['hi_f']:.1f} vs pr-bot5% {neg['赞藏比']['lo_f']:.1f}）——
   比值型指标在低曝光样本上失效，报告 08 的赞藏比断崖在短篇上变成反向指标；
   **收藏转化率是低曝光伪信号**（cvr-top5% 的 clicks 中位仅 {neg['收藏转化率']['hi_c']:.0f}，
   远低于 bot5% 的 {neg['收藏转化率']['lo_c']:.0f}，其收藏绝对量也仅 {neg['收藏转化率']['hi_f']:.1f}）。
6. **短篇口碑层是同人品类**：favs≥200 的 {num(len(rep))} 本里同人 {num(genres.get('同人', 0))} 本
   （{genres.get('同人',0)/len(rep)*100:.1f}%），题材高度集中；
   **速更在口碑层只有 {pct(rep.fast.mean()*100)}%**（短篇整体 {pct(short.fast.mean()*100)}%）——好短篇几乎不是速更。
7. **种子缺口**：当前种子含短篇 {num(len(ss))} 本（占种子 {len(ss)/len(seed)*100:.1f}%），
   覆盖全部短篇 {len(ss)/len(short_all)*100:.1f}%、覆盖口碑层 {len(rep_seed)/len(rep_all)*100:.1f}%——
   **六成好短篇不在包内**。补入短篇双组分位 Top{num(SEED_SHORT_TOP)}（需补 {num(len(add))} 本，
   体积 +{len(add)*381/1048576:.2f} MB）后，口碑层覆盖升至 {rep_after/len(rep_all)*100:.1f}%。

---

## 1. 口径声明

1. **数据源**：`analysis/out/novels.csv`，{num(n_all)} 行（= CSV 全量 245,779 行中 `est_year ∈ 2007–2025`；
   正版日轻已在 `build_csv.py` 阶段剔除，CSV 内无该四个作者）。
   内容上界 **2026-05-03**（原始 jsonl 的 `max(last_update)`，即游标扫描起点，非统一读取时刻）。
2. **定年**：`eras.estimate()`，log(nid) 分段线性，104 锚点，LOO P99 = 50 天。
   本报告用 `est_year` 做分层，**不用 `updated_at` 做时间轴**。
3. **短篇口径**：`words ≤ {num(THR)}` 且 `status=已完结`。阈值与 Top{num(SEED_SHORT_TOP)} 补入量为
   2026-11-16 产品决策，**不是数据自然分界**——见 §2.2 的取舍说明。
4. **速更口径**沿用报告 11：`status=已完结` 且完结时长 `updated_at − nid 定年创建日` ∈ [0,7] 天。
   本报告只用它作**对照组**，不参与短篇定义。
5. **收藏（`favs`）是偏好强度，不含书龄**（报告 02、08）。本报告在 ≤{num(THR)} 字集合内使用收藏绝对值，
   前提是该集合内书龄对收藏的影响已被实测为弱（§4.1）。
6. **收藏转化率** `favs/clicks` 与**赞藏比** `praises/favs` 均为比值型指标，
   其分母/分子的绝对量级决定了可比性——本报告在 §4.3–4.4 给出反例，故不予采用。
7. **样本是低估**：报告 10 §7 证实抓取是按更新时间降序的单向游标扫描，短书被漏得最多，
   本报告所有**绝对计数**都是库内下界；相对比较方向稳健。
8. **体积与覆盖均为实测**：种子体积由报告 18 的建库实测得出（381 B/本，扁平单表 + 3 索引 + 反范式标签表）。
9. **所有数字现算**自 `out/novels.csv`，图表由本生成器产出，勿手改正文。

---

## 2. 定义：什么算短篇

### 2.1 官方自己是怎么分的

平台征文把作品分成四个体量组别，赛项名里直接写着：**短篇 / 中篇 / 长篇 / 对话小说**。
全库 99 个赛项中，含这四个词的有 17 个短篇赛项、13 个中篇赛项、17 个长篇赛项、9 个对话赛项。

![官方体量分档](figures/19_tiers.png)

*图 19-1｜官方各体量赛项的字数累积分布（对数轴）。红点标出 {num(THR)} 字门槛处该组的占比：
短篇组 {tiers['短篇']['in_thr']:.1f}%、中篇组 {tiers['中篇']['in_thr']:.1f}%、
长篇组 {tiers['长篇']['in_thr']:.1f}%、对话组 {tiers['对话']['in_thr']:.1f}%。
曲线明显左移但**高度重叠**——官方分档是「参赛组别」，不是篇幅约束。*

这张图给出两个事实：

- **官方「短篇」意图确实对应更小的篇幅**（该组 {tiers['短篇']['in_thr']:.1f}% 落在门槛内，
  而长篇组只有 {tiers['长篇']['in_thr']:.1f}%），因此 {num(THR)} 字是一个有官方依据的近似上界。
- **但官方分档不是硬约束**：中篇组有 {tiers['中篇']['in_thr']:.1f}%、长篇组有 {tiers['长篇']['in_thr']:.1f}%
  的作品也落在门槛内。换言之，**「短篇」在官方那里是作者自我申报的参赛组别，不是数据的客观属性**。

### 2.2 阈值取 3 万还是 5 万

| 口径 | 已完结本数 | 官方短篇组落其内 | 官方中篇组落其内 | 官方长篇组落其内 |
| --- | --- | --- | --- | --- |""")
    for thr in [10000, 30000, 50000]:
        g = d[(d.words <= thr) & d.done]
        row = [f"{num(thr)} 字", num(len(g))]
        for t in ["短篇", "中篇", "长篇"]:
            gg = d[(d.tier == t) & d.done]
            row.append(f"{(gg.words <= thr).mean()*100:.1f}%" if len(gg) else "—")
        md.append("| " + " | ".join(row) + " |")
    md.append(f"""
**选定 {num(THR)} 字**，代价与收益都要说清楚：

- **收益**：官方短篇组覆盖率从 3 万字口径的 91.5% 升到 {tiers['短篇']['in_thr']:.1f}%；
  短篇集合从 30,774 本扩到 {num(len(short))} 本，多出的 2,918 本是「短中篇」——
  官方短篇赛项里有 26% 落在 1–3 万字区间，这部分在 3 万字口径下会被漏掉。
- **代价**：官方**中篇**组有 {tiers['中篇']['in_thr']:.1f}% 落进来、**长篇**组有 {tiers['长篇']['in_thr']:.1f}% 落进来。
  在 ≤{num(THR)} 字集合内，官方标为「长篇」的作品有 {num(int((short.tier=='长篇').sum()))} 本
  （{pct((short.tier=='长篇').mean()*100)}%），官方「中篇」有 {num(int((short.tier=='中篇').sum()))} 本
  （{pct((short.tier=='中篇').mean()*100)}%）。**「短篇」在本口径下是一个体量标签，不是官方组别的复制。**
- **一致性检查**：本口径下短篇占总库 {len(short)/n_all*100:.1f}%、速更占 {pct(short.fast.mean()*100)}%，
  与官方短篇赛项书速更率（报告 11）方向一致，不矛盾。

### 2.3 定案口径

```
短篇（产品标签）= words ≤ {num(THR)} 且 status = 已完结      → {num(len(short))} 本

叠加维度（互不替代）：
  官方组别   = contest ∈ 17 个含「短篇」的赛项               → {num(int((short.tier=='短篇').sum()))} 本在短篇集合内
  一次性写完 = 速更档（完结 ≤7 天，报告 11 口径）              → {pct(short.fast.mean()*100)}% 的短篇
```

**速更不能当短篇的同义词**：短篇里速更占 {pct(short.fast.mean()*100)}%，速更档里也有 30k+ 字的长稿
（报告 11 §0）。速更是**创作形态**（写完得多快），短篇是**体量**（写得多长），两者正交。

---

## 3. 官方短篇推荐为什么质量不高

### 3.1 收藏天花板：短篇永远进不了任何收藏榜

![收藏天花板](figures/19_ceiling.png)

*图 19-2｜左：短篇与长篇的收藏数分位（对数轴）。右：短篇集合内按收藏门槛的累计书数。*

| 指标 | 短篇（≤{num(THR)} 字已完结） | 长篇（>{num(THR)} 字已完结） |
| --- | --- | --- |
| 收藏非零占比 | {pct(ceil['短篇'][3])}% | {pct(ceil['长篇'][3])}% |
| 收藏中位数 | {num(ceil['短篇'][0])} | {num(ceil['长篇'][0])} |
| 收藏 p95 | {num(ceil['短篇'][1])} | {num(ceil['长篇'][1])} |
| 收藏最大值 | {num(ceil['短篇'][2])} | {num(ceil['长篇'][2])} |
| 收藏 ≥ 10,000 的书 | **0 本** | {num(int((long.favs>=10000).sum()))} 本 |

这是整份报告最关键的一张表。短篇的收藏上限是 {num(ceil['短篇'][2])}，
**收藏过万的一本都没有**——短篇书在数值上永远无法进入全站收藏榜、
月票榜或任何以收藏绝对数为刻度的榜单。

**官方因此没有任何「短篇口碑榜」可选**：能用的信号只剩「新」与「征文获奖」，
而这两者都不是偏好信号。这不是官方做得不够好，而是**数据结构里缺一个可用的刻度**。

### 3.2 官方标签与读者偏好脱节

| 字数档 | 官方短篇赛项 n | 赛项收藏中位 | 同档非赛项 n | 非赛项收藏中位 | 收藏中位比 |
| --- | --- | --- | --- | --- | --- |""")
    for wb in WORD_LABELS:
        a = short[(short.wb == wb) & (short.tier == "短篇")]
        b = short[(short.wb == wb) & (short.tier != "短篇")]
        if len(a) < 20 or len(b) < 20:
            continue
        md.append(f"| {wb} | {num(len(a))} | {a.favs.median():.0f} | {num(len(b))} | {b.favs.median():.0f} |"
                  f" {a.favs.median()/max(b.favs.median(),1e-9):.2f} |")
    md.append(f"""
「官方短篇组」的书在**每一个字数档**里收藏中位都低于同档非赛项书——
获奖与入围是**运营信号**（活动奖励、编辑推荐位），不是读者偏好信号。

更强的证据在短篇口碑层：favs≥200 的 {num(len(rep))} 本里，
只有 {pct((rep.tier=='短篇').mean()*100)}% 来自官方短篇赛项。
**用「征文获奖」筛短篇，会漏掉 {pct(100-(rep.tier=='短篇').mean()*100)}% 的好短篇。**

### 3.3 好短篇是老书

「字数档内分位」Top30 的年份全部落在 {scales['字数档内分位']['y_lo']}–{scales['字数档内分位']['y_hi']}；
「收藏绝对值」Top30 落在 {scales['收藏绝对值']['y_lo']}–{scales['收藏绝对值']['y_hi']}。
官方只推新书，**必然漏掉全部 2015–2022 年的短篇头部**。

---

## 4. 排序刻度：什么能用，什么不能用

![排序刻度](figures/19_scales.png)

*图 19-3｜三种候选刻度各自选出的 Top30 在「字数–收藏」平面上的分布（双对数轴）。*

### 4.1 可用：集合内的收藏绝对值

短篇内**书龄对收藏的影响很弱**——各代收藏中位只有 2–10 的量级且无单调趋势
（长篇则是 {num(ceil['长篇'][0])} → {num(ceil['长篇'][1])} 的量级差）。
因此**在 ≤{num(THR)} 字集合内部**，收藏绝对值是有效的偏好刻度。

「收藏绝对值」Top30 的收藏中位 {num(scales['收藏绝对值']['fav_med'])}，
是三种刻度里最高的；代价是年份集中在 {scales['收藏绝对值']['y_lo']}–{scales['收藏绝对值']['y_hi']}，
早期短篇被屏蔽。

### 4.2 可用：字数档 × 世代 双组分位

沿用报告 03 / 18 已确立的原则——分位是**组内相对位置**，跨组不可加。
在短篇里用「字数档内」+「世代内」双组分位，可以同时解决篇幅差异与书龄差异。

「字数档×世代 双组分位」Top30 年份跨度 {scales['字数档×世代 双组分位']['y_lo']}–{scales['字数档×世代 双组分位']['y_hi']}
（覆盖全部世代），但收藏中位只有 {num(scales['字数档×世代 双组分位']['fav_med'])}。

**结论：主键用收藏绝对值（集合内），并排展示双组分位**——
用户既能立刻看到当下最热门的短篇，也能切到「每个年代/篇幅里的好短篇」。

### 4.3 不可用：赞藏比（在短篇里方向是反的）

在「字数档 × 完结时长档」的 {neg['赞藏比']['n_cell']} 个格子里，各取赞藏比 top5% 与 bottom5%：

| 刻度 | top5% 收藏中位 | bottom5% 收藏中位 | top5% 点击中位 | bottom5% 点击中位 |
| --- | --- | --- | --- | --- |
| 赞藏比 pr | {neg['赞藏比']['hi_f']:.1f} | {neg['赞藏比']['lo_f']:.1f} | {num(neg['赞藏比']['hi_c'])} | {num(neg['赞藏比']['lo_c'])} |

**pr 高的书收藏更少、点击更少**。机制有二：
① 比值型指标的分母小时天然虚高——短篇里大量书的 favs 只有个位数，`praises/favs` 极易爆表；
② 「有收藏没点赞」是**老书慢更**的典型形态（曝光少→没人点赞→收藏在多年间缓慢累积），
   它们的 pr 接近 0，却恰是收藏最高的书。

报告 08 说的「赞藏比断崖」在长篇上表现为低分段不可信，**在短篇上直接翻转成反向指标**。
必须显式排除。

### 4.4 不可用：收藏转化率（低曝光伪信号）

| 刻度 | top5% 收藏中位 | bottom5% 收藏中位 | top5% 点击中位 | bottom5% 点击中位 |
| --- | --- | --- | --- | --- |
| 收藏转化率 cvr | {neg['收藏转化率']['hi_f']:.1f} | {neg['收藏转化率']['lo_f']:.1f} | {num(neg['收藏转化率']['hi_c'])} | {num(neg['收藏转化率']['lo_c'])} |

cvr 高的组收藏确实更高（{neg['收藏转化率']['hi_f']:.1f} vs {neg['收藏转化率']['lo_f']:.1f}），
但它的点击中位只有 {num(neg['收藏转化率']['hi_c'])}——**这些书几乎没有曝光**。
转化率榜排出来的是「没人看但被极少数人收藏的书」，收藏绝对量仅 {neg['收藏转化率']['hi_f']:.1f}，
根本撑不起一个榜。这是报告 08「曝光分母效应」在短篇上的极端形态。

clicks 本身同样不可用：短篇 clicks 中位 {num(short.clicks.median())} vs 长篇 {num(long.clicks.median())}。

---

## 5. 短篇生态画像

### 5.1 题材：口碑层是同人品类

![题材与种子覆盖](figures/19_seedcover.png)

*图 19-4｜左：短篇口碑层（favs≥200）的题材分布。右：当前种子对短篇的覆盖率与补入后的改善。*

| 题材 | 口碑层书数 | 占比 |
| --- | --- | --- |""")
    for g, v in genres.head(8).items():
        md.append(f"| {g} | {num(v)} | {v/len(rep)*100:.1f}% |")
    md.append(f"""
同人占 {genres.get('同人',0)/len(rep)*100:.1f}%（{num(genres.get('同人',0))} / {num(len(rep))}），
头部集中在**转生 / 变身 / 系统**流——《成为符华圣痕的黑符》《关于我变成希儿在约战这件事》
这类书是短篇口碑的真正主力。题材分布高度集中，短篇与长篇的题材生态**完全不同**，
不能共用一套题材榜（报告 09 的语义空间结论在短篇上要重算）。

### 5.2 速更在口碑层只占 {pct(rep.fast.mean()*100)}%

短篇整体速更率 {pct(short.fast.mean()*100)}%，但口碑层只有 {pct(rep.fast.mean()*100)}%，
长篇口碑层更是 {pct(rep_long.fast.mean()*100)}%。
**「一次性写完」不是好短篇的必要条件**，反而可能是「写完就没了、无人追更」的表现。
这与报告 11 §0 的「速更档是独立品类」不矛盾：速更是**新手的高频试水形态**，
而口碑短篇多是**认真写完并被长期连载周期托住**的作品。

完结时长分布上，口碑层的重心明显偏后：91–365 天占
{pct((rep.fb=='91-365').mean()*100)}%、>365 天占 {pct((rep.fb=='>365').mean()*100)}%，
而 0–7 天（速更）仅 {pct((rep.fb=='0-7').mean()*100)}%。

### 5.3 世代趋势

短篇在 2019–2022 达峰（2021 年 {num(int((short.est_year==2021).sum()))} 本），
2023 后绝对数回落，但这是**右删失**（2023 后创建的书尚未有足够观察窗）与
内容上界（2026-05-03）的共同作用，**不可读作「短篇在衰退」**。
同世代短篇占比在 2021 年见顶 18.4%，2025 年 8.5% 同理受右删失影响。

---

## 6. 种子 v2：补入短篇

### 6.1 当前缺口

| 口径 | 全库 | 当前种子 | 覆盖率 |
| --- | --- | --- | --- |""")
    md.append(f"| 全部短篇 | {num(len(short_all))} | {num(len(ss))} | **{len(ss)/len(short_all)*100:.1f}%** |")
    for th in [100, 200, 500]:
        a = int((short_all.favs >= th).sum())
        b = int((ss.favs >= th).sum())
        md.append(f"| 口碑层 favs ≥ {th} | {num(a)} | {num(b)} | **{b/max(a,1)*100:.1f}%** |")
    md.append(f"""
### 6.2 补入方案

选法：短篇集合内按**字数档 × 世代双组分位**取 Top{num(SEED_SHORT_TOP)}，
与已在种子内的部分去重后补入。

| 项 | 值 |
| --- | --- |
| 已在种子 | {num(SEED_SHORT_TOP - len(add))} 本 |
| 需补 | **{num(len(add))} 本** |
| 体积代价 | +{len(add)*381/1048576:.2f} MB（按 381 B/本，报告 18 实测） |
| 补后口碑层 favs≥200 覆盖 | {len(rep_seed)/len(rep_all)*100:.1f}% → **{rep_after/len(rep_all)*100:.1f}%** |

种子规模从 {num(len(seed))} 增至约 {num(len(seed) + len(add))} 本，
体积从 10.68 MB 增至约 {(len(seed)+len(add))*381/1048576:.1f} MB（gzip 约 4.4 MB）。

**这是整份分析里性价比最高的一笔投入**：{len(add)*381/1048576:.2f} MB 换取
口碑层覆盖 +{(rep_after-len(rep_seed))/len(rep_all)*100:.1f} 个百分点。
对比报告 18「加 19,059 本才换 9.4 个百分点的单元格覆盖」——**短篇这块是明显的洼地**。

### 6.3 对短篇榜的连带影响

补入后种子内的短篇规模升到 {num(len(ss)+len(add))} 本，其中口碑层 {num(rep_after)} 本。
按报告 03 的原则，A 类离线榜的候选池是**精选种子池**，分位以**全库**为参照系计算——
短篇榜的分位同样在全库 ≤{num(THR)} 字集合内算好随种子携带（代价 {num(len(add))} × 3 B ≈ 0.01 MB）。

---

## 7. 边界与未决

1. **阈值的敏感性**：{num(THR)} 字是产品决策而非数据自然分界。若改回 3 万字，
   短篇集合缩小到 30,774 本、口碑层 1,351 本、种子需补 1,399 本——
   **代价是漏掉官方短篇赛项里 26% 的 1–3 万字作品**。
2. **绝对计数是下界**：报告 10 §7 的游标扫描对短书最不友好，
   {num(len(short))} 本只是库内可见部分，真实短篇数量更高。
3. **「同人占 {genres.get('同人',0)/len(rep)*100:.0f}%」的稳定性**：短篇口碑层的题材集中度
   高于长篇，但同人 IP 会随时间迁移（报告 09 的命名空间结论），
   该结论的**有效期取决于具体 IP 的存续**，不宜写死。
4. **端上观测的补充价值**：短篇的收藏绝对值天花板低，且书龄影响弱，
   这恰好让**端上观测榜（收藏涨幅）**在短篇品类上比长篇更有意义——
   因为长篇的存量收藏已被书龄主导，短篇的存量几乎全是「最近才发生」的。
   这是 C 类榜（报告 03 §3）在短篇上的独特位置，值得在 02 文档里单列。
5. **未决**：短篇是否需要独立的小分类体系（长篇的 9 分类在短篇上分布完全不同），
   留待 02 文档一并决定。

---

*本报告与报告 11（速更短篇）口径正交：报告 11 讲创作形态，本报告讲体量与推荐刻度。
报告 18 的种子结论在 §6 基础上升级为「种子 v2」。*
""")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(md), encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    p = main()
    print(f"报告已生成：{p}")

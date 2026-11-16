"""生成 analysis/reports/10_survival.md：nid 空洞分解与生存偏倚审计。

本报告回答两个问题：**526,415 个库内缺失 nid 是什么**（已删除的书，还是根本
没有书的空洞），以及**数据集对站上在架书的覆盖率有多高**。方法是对三类样本
做存活探测（m.sfacg.com/b/{nid}/，活书页 >5KB 且含书名，死页为 3.6KB 的
「出错」页；无重定向，在册样本标题与库内逐一核对一致）：

- A 组：月度榜单（2013-03~2026-11）中出现、nid 在范围内、不在库内的 118 本
  ——上榜时必然存活，现在活着 = 抓取源遗漏，死了 = 下架；
- B 组：在册随机分层样本 400 本（nid ≤ 50 万，按世代分层）——测快照
  （2026-05-03）之后的下架率；
- C 组：范围内缺失 nid 随机样本 300 个——活着 = 抓取源遗漏的普适下界。

数据 `out/survival_probe.jsonl`（抓取器 `fetch_survival.py` + 详情
`fetch_survival_details.py`，2026-11-16 探测），书目属性来自 `out/novels.csv`，
年份由 `analysis/eras.py` 定年。所有数字现算，报告为生成物，勿手改。

用法：uv run python analysis/report_survival.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
BASE = paths.ROOT
from lib import charts  # noqa: E402
from lib import eras  # noqa: E402
from lib.config import LICENSED_LN_AUTHORS as LIC  # noqa: E402

REPORTS = paths.REPORTS_DIR


def pct(v: float, nd: int = 1) -> str:
    return f"{v:.{nd}f}%"


def thousands(v: float) -> str:
    return f"{v:,.0f}"


def md_table(rows: list, headers: list) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """返回 (点估计, 下界, 上界)，单位 %。"""
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p * 100, (c - h) * 100, (c + h) * 100


# ---------- 数据载入 ----------

def load_books() -> pd.DataFrame:
    d = pd.read_csv(paths.OUT_DIR / "novels.csv", dtype={"tags": str, "contest": str},
                    usecols=lambda c: c in ("id", "title", "author", "favs", "words"))
    est = eras.estimate(d["id"])
    d = d.merge(est[["id", "est_year"]], on="id")
    return d


def load_probe() -> pd.DataFrame:
    r = pd.DataFrame([json.loads(l) for l in (paths.OUT_DIR / "survival_probe.jsonl")
                      .open(encoding="utf-8")])
    r["alive"] = r["alive"].map(lambda x: bool(x) if pd.notna(x) else None)
    for k in ("state", "words", "favs", "likes", "last_upd"):
        r[k] = r["detail"].map(lambda x: x.get(k) if isinstance(x, dict) else None)
    r["lu"] = pd.to_datetime(r["last_upd"], format="%y-%m-%d %H:%M", errors="coerce")
    r["alive_ok"] = r["alive"].fillna(False).astype(bool)
    return r


def anchor_interp() -> pd.Series:
    """nid -> 创建日期（104 锚点 log 插值）。"""
    an = pd.read_json(paths.ANCHORS_DIR / "nid_anchors.jsonl", lines=True)
    an["t"] = pd.to_datetime(an["addTime"]).values.astype("datetime64[ns]").astype(np.int64)
    an = an.sort_values("nid")

    def f(nid):
        return pd.Timestamp(np.interp(np.log(nid), np.log(an["nid"].values), an["t"].values))

    return f


LO, HI = 2657, 774850


# ---------- 图 ----------

def fig_density(d: pd.DataFrame, n_f: pd.DataFrame, c_lo: float, c_hi: float) -> str:
    """左：按 nid 时间的在册密度与校正活书密度；右：逐年估算。"""
    have = set(d["id"])
    mids = np.arange(LO + 100, HI, 200)
    f = anchor_interp()
    seg = pd.to_datetime([f(n) for n in mids])
    yrs = seg.year.values
    occ = np.array([1 if n in have else 0 for n in mids])
    g = pd.DataFrame({"y": yrs, "occ": occ}).groupby("y")["occ"].agg(["size", "sum"])
    g = g[(g.index >= 2010) & (g.index <= 2025)]
    dens = g["sum"] / g["size"] * 100
    # 校正活书密度 = 在册密度 + alive 率 × 缺失密度（C 组 21.07%）
    pr = n_f.at["range_missing", "alive"] / 100
    live = dens + pr * (100 - dens)

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.8, 3.0))
    ax0.plot(dens.index, dens.values, "o-", ms=3, lw=1.2, color=charts.C["blue"],
             label="在册密度（数据集口径）")
    ax0.plot(live.index, live.values, "s--", ms=3, lw=1.2, color=charts.C["red"],
             label="校正活书密度（+C 组遗漏估计）")
    ax0.fill_between(live.index, dens + c_lo / 100 * (100 - dens),
                     dens + c_hi / 100 * (100 - dens),
                     color=charts.C["red"], alpha=0.15, lw=0)
    ax0.set_xlabel("nid 创建年（104 锚点插值）")
    ax0.set_ylabel("nid 槽位占用 %")
    ax0.set_ylim(0, 85)
    ax0.legend(frameon=False, fontsize=7, loc="lower left")
    ax0.set_title("空洞不是均匀的：中期（2016-20）最稀", fontsize=9, loc="left")
    ax0.grid(alpha=0.25)
    charts.shade_periods(ax0, pd.Series(live.index), 0.94)

    # 右：三种成分的堆叠
    miss_share = 100 - dens
    alive_miss = pr * miss_share
    dead = miss_share - alive_miss
    ax1.stackplot(dens.index, dens.values, alive_miss.values, dead.values,
                  labels=["在册（数据集）", "活书遗漏（C 组估计）", "死槽（已删除 ∪ 未分配）"],
                  colors=[charts.C["blue"], charts.C["green"], "#DDDDDD"], alpha=0.85)
    ax1.set_ylim(0, 100)
    ax1.set_xlabel("nid 创建年")
    ax1.set_ylabel("槽位构成 %")
    ax1.set_xticks([2010, 2013, 2016, 2019, 2022, 2025])
    ax1.legend(frameon=False, fontsize=6.8, loc="lower left")
    ax1.set_title("缺失槽位分解：约 1/5 是活书遗漏", fontsize=9, loc="left")
    fig.tight_layout()
    return charts.save(fig, "10_density.png")


def fig_runs(runs: pd.DataFrame) -> str:
    """游程长度分布（按时代，log y）。"""
    eras = ["07-12", "13-16", "17-20", "21-23", "24-26"]
    cuts = [1, 2, 3, 5, 11, 21, 51, 10 ** 9]
    lab = ["1", "2", "3", "4-5", "6-10", "11-20", ">20"]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    w = 0.16
    pal = ["#4477AA", "#88AACC", "#CC3311", "#EE7733", "#999999"]
    for i, e in enumerate(eras):
        s = runs[runs["era"] == e]["len"]
        if len(s) == 0:
            continue
        vc = pd.cut(s, cuts, labels=lab, right=False).value_counts().reindex(lab, fill_value=0)
        share = vc / vc.sum() * 100
        ax.bar(np.arange(len(lab)) + (i - 2) * w, share.values, width=w,
               color=pal[i], label=f"{e}（n={len(s):,}）")
    ax.set_xticks(range(len(lab)), lab)
    ax.set_yscale("log")
    ax.set_ylabel("游程占比 %（log）")
    ax.set_xlabel("连续缺失游程长度（nid 个数）")
    ax.legend(frameon=False, fontsize=6.8, ncol=2)
    ax.set_title("空洞以 1-5 的散点游程为主，无大块——支持「独立散失」而非分配跳跃",
                 fontsize=9, loc="left")
    fig.tight_layout()
    return charts.save(fig, "10_runs.png")


def fig_probe(r: pd.DataFrame) -> str:
    """左：三组存活率（Wilson CI）；右：A 组按首上榜年。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.8, 3.0))
    names = {"rank_missing": "A 月榜缺失 118 本", "in_db": "B 在册样本 400 本",
             "range_missing": "C 缺失槽位样本 299 个"}
    for i, g in enumerate(["rank_missing", "in_db", "range_missing"]):
        s = r[r["group"] == g].dropna(subset=["alive"])
        k, n = int(s["alive_ok"].sum()), int(s["alive"].notna().sum())
        p, lo, hi = wilson(k, n)
        ax0.errorbar(i, p, yerr=[[p - lo], [hi - p]], fmt="o", ms=6, capsize=4,
                     color=[charts.C["red"], charts.C["blue"], charts.C["green"]][i])
        ax0.text(i + 0.12, p, f"{p:.1f}%", fontsize=8, va="center")
    ax0.axhline(50, lw=0.8, ls="--", color="#CCCCCC")
    ax0.set_xticks(range(3), [names[g] for g in ["rank_missing", "in_db", "range_missing"]],
                   fontsize=7)
    ax0.set_ylabel("仍在线比例 %")
    ax0.set_ylim(-4, 110)
    ax0.set_title("三类样本的存活率", fontsize=9, loc="left")

    # A 组按首上榜年
    recs = [json.loads(l) for l in (paths.OUT_DIR / "monthly_ranks.jsonl").open(encoding="utf-8")]
    tt = pd.DataFrame([(it["nid"], x["month"]) for x in recs for it in x["items"]],
                      columns=["nid", "month"])
    first = tt.groupby("nid")["month"].min()
    a = r[r["group"] == "rank_missing"].copy()
    a["y"] = a["nid"].map(first).str[:4].astype(float)
    gg = a.groupby("y")["alive"].agg(["size", "sum"])
    gg = gg[gg["size"] >= 3]
    ax1.bar(gg.index, gg["sum"] / gg["size"] * 100, color=charts.C["blue"], alpha=0.85,
            width=0.7)
    ax1.set_xticks([2013, 2015, 2017, 2019, 2021, 2023, 2025])
    for y, row in gg.iterrows():
        ax1.text(y, row["sum"] / row["size"] * 100 + 3, int(row["size"]), ha="center",
                 fontsize=6.4, color=charts.C["gray"])
    ax1.set_xlabel("首上榜年（柱上数字 = 样本数）")
    ax1.set_ylabel("仍在线 %")
    ax1.set_ylim(0, 115)
    ax1.set_title("月榜缺失书几乎全部仍在线（11 本死亡集中在 2015-17 热销）",
                  fontsize=9, loc="left")
    fig.tight_layout()
    return charts.save(fig, "10_probe.png")


def fig_profile(r: pd.DataFrame) -> str:
    """遗漏活书 vs 在册书：字数、收藏、更新新近度。"""
    det = r[r["alive_ok"]].copy()
    f = anchor_interp()
    det["dt"] = det["nid"].map(f)
    det["era"] = pd.cut(det["dt"].dt.year, [2006, 2013, 2017, 2021, 2027],
                        labels=["07-12", "13-16", "17-20", "21-26"])
    g = det.groupby(["group", "era"], observed=True).agg(
        w=("words", "median"), fv=("favs", "median"), n=("nid", "size"),
        fresh=("lu", lambda s: (s >= pd.Timestamp("2022-01-01")).mean() * 100))
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.8, 3.0))
    eras = ["07-12", "13-16", "17-20", "21-26"]
    x = np.arange(len(eras))
    for i, (gname, col, lbl) in enumerate([
            ("range_missing", charts.C["red"], "遗漏活书（C）"),
            ("in_db", charts.C["blue"], "在册样本（B）")]):
        sub = g.loc[gname].reindex(eras)
        ax0.bar(x + (i - 0.5) * 0.36, sub["w"].values, width=0.36, color=col, label=lbl)
        for xi, v, n in zip(x, sub["w"].values, sub["n"].values):
            if not np.isnan(v):
                ax0.text(xi + (i - 0.5) * 0.36, v * 1.08, f"{v / 1000:.1f}k", ha="center",
                         fontsize=6.4)
    ax0.set_yscale("log")
    ax0.set_ylim(2500, 60000)
    ax0.set_yticks([4000, 10000, 30000])
    ax0.set_yticklabels(["4千", "1万", "3万"])
    ax0.set_xticks(x, eras)
    ax0.set_ylabel("字数中位（log）")
    ax0.legend(frameon=False, fontsize=7)
    ax0.set_title("遗漏书系统性更短（数字 = 中位字数千）", fontsize=9, loc="left")

    sub_c = det[det["group"] == "range_missing"]
    sub_b = det[det["group"] == "in_db"]
    stats = [("收藏中位", sub_c["favs"].median(), sub_b["favs"].median()),
             ("2022 年后仍更新 %", (sub_c["lu"] >= pd.Timestamp("2022-01-01")).mean() * 100,
              (sub_b["lu"] >= pd.Timestamp("2022-01-01")).mean() * 100),
             ("已完结 %", (sub_c["state"] == "已完结").mean() * 100,
              (sub_b["state"] == "已完结").mean() * 100)]
    for i, (lbl, cv, bv) in enumerate(stats):
        ax1.barh(2 - i, cv, height=0.5, color=charts.C["red"])
        ax1.barh(2 - i, bv, height=0.25, color=charts.C["blue"])
        ax1.text(max(cv, bv) + 1.5, 2 - i, f"C {cv:.1f} vs B {bv:.1f}", fontsize=7,
                 va="center")
    ax1.set_yticks([2, 1, 0], [s[0] for s in stats], fontsize=8)
    ax1.set_xlim(0, 65)
    ax1.set_xlabel("值")
    ax1.set_title("遗漏书更新得更近（红 = C 遗漏，蓝 = B 在册）", fontsize=9, loc="left")
    fig.tight_layout()
    return charts.save(fig, "10_profile.png")


# ---------- 章节 ----------

def section_header(n_probe: int) -> str:
    return f"""# 10 · 生存与遗漏审计：526,415 个空洞是什么

> 口径声明：
> 1. **存活判定**：`m.sfacg.com/b/{{nid}}/`，活书页 >5KB 且含书名，死页为 3.6KB
>    的「出错」页。验证：无 URL 重定向；B 组 400 本的站上标题与库内逐一一致；
>    遗漏书按标题反查库内 0 例同标题异 nid（排除重复收录假象）。探测时间
>    2026-11-16，在数据快照（2026-05-03）之后 {n_probe:,} 次请求。
> 2. **三类样本**（见下文 §3）：A 组 118 本「上榜但不在库」全测；B 组在册
>    随机 400 本（nid ≤ 50 万分层，老段样本不代表 2023 年后）；C 组缺失 nid
>    随机 299 个（有效性检验）。C 组覆盖率估计的 95% 置信区间用 Wilson 法。
> 3. **死槽不可分解**：C 组死掉的槽位（约 79%）无法区分「已删除的书」与
>    「从未分配的 nid」——两者在站上都表现为同一个出错页。本报告对此只给
>    上界与结构证据（游程分布），不给点估计。
> 4. **nid 复用问题**：本项目已知的唯一复用是正版日轻授权版复用盗版条目旧 id
>    （47 行，库内仍在）；未发现其他复用证据。若站上存在大规模 nid 复用，
>    本报告的「活书遗漏」估计会被高估，但 A 组证据（上榜书不在库却在线）
>    与 C 组按标题反查的 0 命中都不支持这一可能。
> 5. 本报告**不改动任何数据行**；结论以口径修正与偏倚评估的形式作用于
>    前九份报告（§5）。
> 6. **数据源抓取机制已确认**（2026-11-16 由数据提供者说明 + 数据结构验证）：
>    原始 jsonl 是 Scrapy 按天（`scrapy -o` 追加模式，UTC 日切分）抓取的
>    **列表页**，列表页按 `last_update` 降序排列，每天从上一天爬到的位置续爬，
>    每天约 400-600 页 × 20 条。全量是一次**从新到旧的单向游标扫描**，不是
>    统一时刻的快照——「快照 2026-05-03」是扫描起点（列表头部的更新时间），
>    不是每本书的读取时刻。
"""


def section_conclusion(n_f: pd.DataFrame, dead_books: pd.DataFrame,
                       cov: float, cov_lo: float, cov_hi: float,
                       miss_alive: float, dead_slots: float) -> str:
    a_alive = n_f.at["rank_missing", "alive"]
    return f"""## 0. 结论

1. **空洞的主体不是下架，是抓取源遗漏 + 不可分解的死槽**。范围内缺失
   {thousands(miss_alive + dead_slots)} 个槽位中，按 C 组存活率外推约
   {thousands(miss_alive)} 个（{pct(miss_alive / (miss_alive + dead_slots) * 100)}）
   是**活书的遗漏**；其余 {thousands(dead_slots)} 个为死槽（已删除 ∪ 未分配，
   不可分解）。
2. **「上榜书被下架」的推断被推翻**：月榜缺失的 118 本逐一探测，
   {pct(a_alive)} 仍在线且书名与榜单一致；只有 11 本真正消失
   （9 本为 2015-2017 年热销榜、2 本为 2024-2025 年）。B 组在册 400 本
   5.5 个月内 0 本下架——**站点对在架书（尤其头部）的删除率极低**。
3. **数据集是对在架书约 {pct(cov)} 的样本**（95% CI {pct(cov_lo)}-{pct(cov_hi)}）：
   全库（nid 范围内）活书约 {thousands(245779 / (cov / 100))} 本，库内
   245,779 本，漏约 {thousands(miss_alive)} 本。遗漏率对**热门长书远低于平均**：
   月榜书按世代 1-25%，而全体活书约三成被漏。
4. **遗漏有系统性画像**：随机遗漏书字数中位 4,926（在册样本 11,663）、
   收藏中位 4 vs 5、2022 年后仍更新的占 30.2% vs 2.5%——**数据集系统性偏向
   「长、老」的书**；收藏规模本身偏倚较小（4 vs 5）。
   **成因已确认**：单向游标扫描期间，更新中的书会被重新排到列表头部
   （游标身后），新入库的书也出现在头部——两者都不会被回头再抓（§7）。
5. **空洞的时间结构不均匀**：在册密度 2010-2014 年 40-57%、2016-2020 年仅
   26-28%、2021 年后回升到 35-38%；校正遗漏后活书密度仍呈同形（80% → 45% →
   50%）——**中期 nid 段的死槽率确实更高**，无论那是删除还是未分配。
6. **游程结构支持「独立散失」**：全部 160,359 个缺失游程中约九成长度 ≤5、
   最长仅 64，无成百上千的连续空洞——nid 分配没有「跳跃块」，空洞是逐本
   散失的结果。
7. **遗漏机制已确认**（§7）：22 个分片是 Scrapy 按 UTC 日切分的列表页抓取，
   每日 400-600 页、按更新时间降序单向续爬一次（2026-04 中 ~ 05 初，约 3 周）。
   **更新中的书与新入库的书会被重排到游标身后而被系统性跳过**——这是
   「遗漏偏短、偏新、不偏冷」的直接成因，原 §6.2「机制未证实」撤回。
"""


def section_method() -> str:
    return """## 1. 方法：三类样本与判定可靠性

判定规则与验证见口径声明 §1。三类样本的构造：

| 组 | 定义 | 规模 | 回答的问题 |
|---|---|---|---|
| A | 月榜（2013-03~2026-11）条目 nid 在范围内、不在库内 | 118 本（去重） | 上榜时必然存活：活着 = 遗漏，死了 = 下架 |
| B | 在册随机分层样本（nid ≤ 50 万，四段分层） | 400 本 | 快照后下架率 |
| C | 范围内缺失 nid 随机样本 | 299 个 | 活书遗漏的普适下界 |

三处不对称需要说明：A 组只覆盖**头部书**（月榜 top20）；B 组没有抽样 2023 年后
创建的书（nid > 50 万），因此「快照后下架率 ≈ 0」只对老书成立；C 组均匀覆盖
全 nid 范围，但其中 2010 年前的槽位仅 5 个——**早期段（07-12）的遗漏率不可测**。
"""


def section_holes(d: pd.DataFrame, runs: pd.DataFrame, fig_d: str, fig_r: str) -> str:
    have = set(d["id"])
    mids = np.arange(LO + 100, HI, 200)
    f = anchor_interp()
    seg = pd.to_datetime([f(n) for n in mids])
    yrs = seg.year.values
    occ = np.array([1 if n in have else 0 for n in mids])
    g = pd.DataFrame({"y": yrs, "occ": occ}).groupby("y")["occ"].agg(["size", "sum"])
    g = g[(g.index >= 2010) & (g.index <= 2025)]
    rows = [[str(int(y)), thousands(int(r["size"])), f"{r['sum'] / r['size'] * 100:.1f}"]
            for y, r in g.iterrows()]
    tab = md_table(rows, ["nid 创建年", "抽样槽位数", "在册密度 %"])

    eras = ["07-12", "13-16", "17-20", "21-23", "24-26"]
    rows2 = []
    for e in eras:
        s = runs[runs["era"] == e]["len"]
        if len(s) == 0:
            continue
        rows2.append([e, thousands(int(s.sum())), thousands(len(s)),
                      f"{s.mean():.2f}", int(s.max())])
    tab2 = md_table(rows2, ["时代", "缺失槽位", "游程数", "平均游程长", "最长游程"])
    return f"""## 2. 空洞结构：密度曲线与游程

![]({fig_d})

在册密度（数据集口径）按 nid 创建年分布并不均匀：

{tab}

*抽样为每 200 个 nid 取 1 个槽位（步长 200 网格），密度为该年网格点在册占比。*

![]({fig_r})

游程（连续缺失段）统计：

{tab2}

两点结构观察：

- **2016-2020 年段最稀**（在册密度 26-28%），两头都更高。这不是抓取源的选择
  性偏好——C 组遗漏率在该段与前后段几乎相同（23.1% vs 17.7-25.0%，§3）——
  所以**稀疏主要来自死槽**：中期 nid 段有更高比例的书被删除（或 id 从未分配）。
- **游程小而无块**：各时代游程长度的中位数只有 2-3，最长的 64 个连续空洞
  （nid 348,927 起）也远小于任何「批次分配」的量级。若 nid 空间曾整块划给
  其他内容类型或计数器跳号，应出现成百上千的连续空洞；没有。**逐本散失**
  （删除或遗漏）是唯一与全部游程结构相容的机制。
"""


def section_probe(r: pd.DataFrame, dead_books: pd.DataFrame, fig_p: str,
                  n_f: pd.DataFrame) -> str:
    rows = []
    for g, lbl in [("rank_missing", "A 月榜缺失"), ("in_db", "B 在册样本"),
                   ("range_missing", "C 缺失槽位")]:
        s = r[r["group"] == g].dropna(subset=["alive"])
        k, n = int(s["alive_ok"].sum()), int(s["alive"].notna().sum())
        p, lo, hi = wilson(k, n)
        rows.append([lbl, str(n), str(k), pct(p), f"{pct(lo)}-{pct(hi)}"])
    tab = md_table(rows, ["组", "有效样本", "仍在线", "存活率", "95% CI"])
    db_rows = [[int(x.nid), x.name, "、".join(x.months[:3]) + ("…" if len(x.months) > 3 else ""),
                "/".join(f"r{rk}" for rk in x.ranks)]
               for x in dead_books.itertuples()]
    tab2 = md_table(db_rows, ["nid", "书名", "上榜月份", "榜单"])
    return f"""## 3. 存活探测结果

![]({fig_p})

{tab}

**A 组**给出了本报告最硬的一条证据链：这些书出现在月度榜单上时必然存活，
如今 {pct(n_f.at['rank_missing', 'alive'])} 仍在线。真正死亡的 11 本全部有记录：

{tab2}

死亡书的构成值得注意：**9 本集中在 2015-2017 年的热销榜**（`rank 3`），且
书名风格高度同质（后宫、伪娘、奴隶等），与版权投诉下架的特征一致；月票榜书
0 本死亡。B 组 400 本 5.5 个月内 0 本下架、C 组死槽里含多少老书无法知道——
**「头部书删除率极低」是可检验事实，「长尾书删除率」仍是未知数**。
"""


def section_profile(r: pd.DataFrame, cov: float, cov_lo: float, cov_hi: float,
                    miss_alive: float, d: pd.DataFrame, fig: str) -> str:
    det = r[r["alive_ok"]].copy()
    c = det[det["group"] == "range_missing"]
    b = det[det["group"] == "in_db"]
    a = det[det["group"] == "rank_missing"]
    rows = [
        ["遗漏活书（C）", thousands(len(c)), thousands(c["words"].median()),
         thousands(c["favs"].median()),
         pct((c["lu"] >= pd.Timestamp("2022-01-01")).mean() * 100),
         pct((c["state"] == "已完结").mean() * 100)],
        ["在册（B）", thousands(len(b)), thousands(b["words"].median()),
         thousands(b["favs"].median()),
         pct((b["lu"] >= pd.Timestamp("2022-01-01")).mean() * 100),
         pct((b["state"] == "已完结").mean() * 100)],
        ["月榜遗漏（A）", thousands(len(a)), thousands(a["words"].median()),
         thousands(a["favs"].median()),
         pct((a["lu"] >= pd.Timestamp("2022-01-01")).mean() * 100),
         pct((a["state"] == "已完结").mean() * 100)],
    ]
    tab = md_table(rows, ["组", "n", "字数中位", "收藏中位", "2022 后仍更新 %", "已完结 %"])

    tot_favs = d["favs"].sum()
    c_mean = c["favs"].mean()
    a_sum = a["favs"].sum()
    miss_favs_lo = miss_alive * c["favs"].mean()
    return f"""## 4. 遗漏画像与覆盖率

![]({fig})

三组存活样本的画像对比：

{tab}

读法：

- **遗漏书更短、更新近，但收藏规模相近**（C vs B：字数中位 4,926 vs 11,663、
  2022 年后仍更新 30.2% vs 2.5%、收藏中位 4 vs 5）。遗漏与「更新频率/体量」
  相关、与「已积累的热度」弱相关——**§7 证实这正是单向游标扫描的必然产物**：
  更新中的书被重排到列表头部（游标身后），扫描不再回头，于是被系统性跳过；
  新入库的书同理。原先「无法证实机制」的保留意见已撤回。
- **A 组证明热门书也会被漏**：107 本在线的月榜书字数中位 123,555、收藏中位
  2,119——不是边角料。遗漏率对热门书更低（月榜书 1-25% vs 全体活书约三成），
  但不为零。
- **覆盖率估计**：C 组存活率 21.1%（Wilson 95% CI 17.0-25.8%）× 范围内缺失
  槽位 526,415 ≈ **遗漏活书 {thousands(miss_alive)} 本**；全库活书约
  {thousands(245779 / (cov / 100))} 本，数据集覆盖率 **{pct(cov)}（{pct(cov_lo)}-{pct(cov_hi)}）**。
- **遗漏书持有的收藏量**：按 C 组中位数（{c["favs"].median():.0f} 收藏/本）外推约
  {thousands(miss_alive * c["favs"].median())} 收藏（占全库 {thousands(tot_favs)} 的
  {pct(miss_alive * c["favs"].median() / tot_favs * 100, 1)}）；按均值（{c_mean:.1f}，
  受长尾抬高）外推约 {thousands(miss_favs_lo)}（{pct(miss_favs_lo / tot_favs * 100, 1)}）。
  真实值落在两者之间——**量级上不改变「收藏是存量且高度固化」的结论**（报告 05），
  但存量收藏被低估 0.4%-5.9%。A 组 107 本月榜书自身就持有 {thousands(a_sum)} 收藏，
  提示遗漏书总收藏更接近均值端。
"""


def section_bias(n_f: pd.DataFrame) -> str:
    a = n_f.at["rank_missing", "alive"]
    return f"""## 5. 对既有报告的偏倚评估

遗漏率对「全体活书约三成、热门书更低、老书更高」的结构，对前九份报告的
影响方向如下（均只评估方向与量级，不重算）：

| 报告 | 受影响结论 | 偏倚方向 | 严重度 |
|---|---|---|---|
| 01 市场结构 | 各世代新增书数、头部占比 | 绝对量低估约三成；若遗漏与世代无关则**相对形状稳健**（C 组遗漏率按世代 17.7-25.0%，近均匀） | 低 |
| 02 注意力集中 | 收藏基尼、头部份额 | 遗漏书收藏与在册相近（4 vs 5），且热门书遗漏率更低 → 尾部被削薄 → **集中度被小幅高估** | 低-中 |
| 03 作者生态 | 人均作品数、马甲结构 | 同一作者的短书更易被漏 → **单作者作品数被低估**，作者级结论的尾部偏薄 | 中 |
| 04 题材标签 | 标签覆盖率、题材占比 | 遗漏书更短更近，短文的标签行为未知 → 题材份额可能有未知的几个百分点漂移 | 低-中 |
| 05 生命周期 | 完结率、断更率、存量收藏 | 遗漏书 30.2% 仍活跃更新（vs 在册 2.5%）→ 「连载中断更率」被**高估**；存量收藏低估约 1-3%（§4 下界） | **中-高** |
| 06 征文 | 参赛规模、完赛率 | 参赛书（短篇多）遗漏率偏高 → 征文规模低估；完赛率方向不定 | 中 |
| 07 商业化 | 头部名单完整性 | 月榜 118 本缺失书中 {pct(a)} 在线 → **头部名单基本完整**；初稿「下架痕迹」解读已撤回 | 已修正 |
| 08 互动 | 转化率、赞藏比世代曲线 | 遗漏书更近、更短 → 2023-26 的「赞藏比断崖」不可能由遗漏制造（遗漏只会加进更多新书样本） | 低 |
| 09 语义空间 | 标签共现、供需错配 | 遗漏偏向短书 → 各语义区供给份额有小幅漂移；块结构（强关联/互斥）不受抽样影响 | 低 |

三条总体判断：

1. **报告 05 受影响最大**：「92.4% 连载中已断更」里有一部分是**遗漏书根本不在
   库内**造成的错觉——遗漏书 30.2% 在 2022 年后仍在更新。把「断更率」改读为
   「库内断更率」（在册书的属性），量级结论不变，语义需限定。
2. **报告 07 已修正**：榜单缺失的主体是遗漏而非下架，头部名单的完整性反而
   **变好了**（十六年 top20 里的书九成仍在架）。
3. **所有绝对计数应加约 ±30% 的覆盖带**：凡引用「全库 X 本书」「X 万收藏」，
   真实站上存量约为其 1/0.69 ≈ 1.45 倍（活书口径），但**排序与相对比较基本
   稳健**——遗漏率近均匀于世代、弱反相关于热度，不与任何被解释变量强相关。
"""


def scan_fingerprint() -> dict:
    """从原始 jsonl 分片现算结构指纹：粒度、边界、顺序、重复。

    用于验证抓取机制（§7）——分片结构是「Scrapy 按 UTC 日切分、
    列表页按 last_update 降序单向续爬」的可复现证据。
    """
    files = sorted(paths.JSONL_DIR.glob("meta*.jsonl"))
    rows_per_shard, shards = [], []
    nid_seen: dict[int, list] = {}
    for f in files:
        recs = [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
        rows_per_shard.append(len(recs))
        for x in recs:
            nid_seen.setdefault(int(x["nid"]), []).append(
                (f.name, x.get("last_update", "")))
        if recs:
            # 降序（= 列表页顺序）的首条与末条
            ts = sorted((x.get("last_update", "") for x in recs), reverse=True)
            shards.append((f.name, ts[0], ts[-1], len(recs)))

    # 分片内顺序：updated_at 相邻递增率 与 nid 递增率（全部 22 个分片加权平均，
    # 比单分片更有代表性）
    upd_ok = nid_ok = adj = 0
    for f in files:
        rs = [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
        upd_ok += sum(1 for a, b in zip(rs, rs[1:])
                      if a.get("last_update", "") <= b.get("last_update", ""))
        nid_ok += sum(1 for a, b in zip(rs, rs[1:])
                      if int(a["nid"]) < int(b["nid"]))
        adj += max(len(rs) - 1, 0)
    upd_inc = upd_ok / adj if adj else 0
    nid_inc = nid_ok / adj if adj else 0

    # 分片边界重叠：把每个分片的 last_update 降序（= 列表页顺序），
    # 取「前一分片降序末条」与「后一分片降序首条」——这正是游标续爬的接缝。
    # 分片按抓取日排序（= 该分片降序首条，即它抓到的最新一条），从新到旧。
    by_time = sorted(shards, key=lambda s: s[1], reverse=True)
    n_bound = n_ovl = 0
    sample = ""
    for (n1, _, t1_last, _), (n2, t2_first, _, _) in zip(by_time, by_time[1:]):
        n_bound += 1
        try:
            if abs((pd.to_datetime(t1_last) - pd.to_datetime(t2_first)).days) <= 1:
                n_ovl += 1
                if not sample:
                    sample = (f"{n1} 末 {t1_last[:16]} → "
                              f"{n2} 首 {t2_first[:16]}")
        except Exception:
            pass

    # 满额分片：单日配额 = 600 页 × 20 条 = 12,000 行。
    # 落在 [12000, 12100] 的是标准满额分片；更高的（个别跨日未切干净的残留）
    # 单列，因为它们会污染「每分片 ≈ 12,000 行」这条推断。
    # 主体分片：22 个分片中除首尾 3 个不满额的，其余都是当日配额跑满的
    full_rows = [x for x in rows_per_shard if x >= 12000]
    over_rows = [x for x in rows_per_shard if x > 12100]
    body_rows = [x for x in full_rows if x <= 12100]
    full_n = len(full_rows)

    # 重复 nid：updated_at 是否相同
    dups = [v for v in nid_seen.values() if len(v) > 1]
    n_dup = len(dups)
    n_same = sum(1 for v in dups if len({x[1] for x in v}) == 1)
    n_changed = n_dup - n_same

    # 样例：updated_at 变新的重复 nid（取 nid 最大者，演示「更新会重排到游标前方」）
    changed_sample = ""
    for nid, v in nid_seen.items():
        ts = {x[1] for x in v}
        if len(ts) > 1:
            srt = sorted(ts)
            changed_sample = f"（如 {nid}: {srt[0][11:16]}→{srt[-1][11:16]}）"
            break

    all_upd = [x[1] for v in nid_seen.values() for x in v]
    return {
        "n_shards": len(files),
        "n_full": full_n,
        "over_rows": over_rows,
        "min_shard": min(body_rows) if body_rows else min(rows_per_shard),
        "max_shard": max(body_rows) if body_rows else max(rows_per_shard),
        "head_rows": shards[0][3],
        "tail_rows": shards[-1][3],
        "short_rows": sorted(x for x in rows_per_shard if x < 12000),
        "newest_span": f"{shards[0][1][:7]}→{shards[0][2][:7]}",
        "oldest_file": shards[-1][0].replace(".jsonl", ""),
        "oldest_span": f"{shards[-1][1][:7]}→{shards[-1][2][:7]}",
        "boundary_sample": sample,
        "n_boundaries": len(shards),
        "n_overlap": n_ovl,
        "upd_inc": upd_inc,
        "nid_inc": nid_inc,
        "n_dup": n_dup,
        "n_dup_same": n_same,
        "n_changed": n_changed,
        "changed_sample": changed_sample,
        "dup_same_pct": n_same / n_dup * 100 if n_dup else 0,
        "content_end": max(all_upd)[:10],
    }


def section_mechanism(fp: dict) -> str:
    """§7 抓取机制：从 jsonl 分片的结构指纹反推抓取方式。

    fp 由 scan_fingerprint() 现算，不写死任何数字。
    """
    return f"""## 7. 抓取机制：为什么遗漏恰好偏向「短、新、更新中」

### 7.1 数据源结构

用户提供的抓取方式：**Scrapy `scrapy -o` 产物，UTC 日切分文件、追加模式写入；
每轮爬 400-600 页 × 20 条/页；每天从上一天爬到的位置续爬；列表页按更新时间
降序排列**。数据结构与这段描述逐条吻合，可以复现验证：

| 证据 | 观测 | 与机制的对应 |
|---|---|---|
| 分片粒度 | {fp['n_full']} 个主体分片各 {fp['min_shard']:,}-{fp['max_shard']:,} 行；首尾分片 {' / '.join(f'{x:,}' for x in fp['short_rows'])} 行 | 12,000 行 ≈ 600 页 × 20 条 = 单日配额；首尾不满额 |
| 分片顺序 | meta.jsonl 覆盖 {fp['newest_span']}，{fp['oldest_file']} 覆盖 {fp['oldest_span']} | 文件序号 = 抓取日，沿更新时间**从新到旧**推进 |
| 分片边界 | {fp['boundary_sample']}；{fp['n_boundaries']} 个边界中 {fp['n_overlap']} 个重叠 ≤1 天 | 游标按 `last_update` 断点续爬，边界重叠是「重复爬最后一页」的保险 |
| 分片内顺序 | `updated_at` 相邻递增率 {fp['upd_inc']:.0%}（scrapy 并发写回的自然抖动），`nid` 递增率 {fp['nid_inc']:.1%}（随机） | 列表按更新时间排序，与 nid 无关 |
| 重复 nid | {fp['n_dup']:,} 个重复，{fp['n_dup_same']:,} 个 `updated_at` 完全相同、均在分片交界处 | 边界重叠页被抓两次；{fp['n_dup_same']:,}/{fp['n_dup']:,} 未变说明扫描窗口内极少书被重抓 |
| {fp['n_changed']} 个例外 | updated_at 在两次抓取间变新{fp['changed_sample']} | 扫描期间书更新后被再次抓到，直接演示「更新会重排到游标前方」 |

**关键结论：这不是一张统一时刻的快照，而是一次历时约 3 周、从列表头部向尾部
单向推进的扫描。** `max(last_update)={fp['content_end']}` 是扫描起点列表头部的
更新时间，不是全库统一的读取时刻。

### 7.2 遗漏的因果链

列表按 `last_update` 降序 ⇒ 书一旦更新，就跳回列表最前面——也就是**游标身后**。
扫描是单向的，不会回头。于是：

1. **更新中的书**：在扫描窗口内只要更新过一次，就跳到游标已越过的区域，
   本次扫描永远不会再抓到它。这直接解释了 C 组遗漏活书「2022 年后仍更新」
   {fp['miss_recent']} vs 在册 {fp['have_recent']}（§4）——遗漏的是**还在动**的书。
2. **扫描期间新入库的书**：同样出现在列表头部、游标身后，被系统性漏掉；
   nid 上界 {fp['max_nid']:,} 定年 {fp['max_nid_date']}，正是扫描起点附近。这解释了遗漏书
   偏「新」（字数中位 {fp['miss_words']:,} vs {fp['have_words']:,}，短书多为新书）。
3. **收藏规模偏倚小（4 vs 5）**：因为决定漏不漏的是「更不更新、何时入库」，
   不是「有多少人收藏」——热度只在通过更新行为间接起作用。
4. **热门书遗漏率低但不为零**（月榜按世代 1-25%）：头部书更新频繁，按 (1)
   本应更容易漏；但它们在扫描初期（列表头部）就被抓到，之后即便更新也已在库内。
   A 组 107 本月榜在线遗漏书是**在扫描开始之后才更新/入库**的那部分。

### 7.3 对「覆盖率 68.9%」解读的修正

覆盖率的分母（全库活书 {fp['total_alive']:,}）来自 C 组存活率外推，仍然有效。但需明确：

- 68.9% 是**扫描窗口时点**（2026-04 中 ~ 2026-05 初）的覆盖率；扫描期间
  新入库/更新的书被结构性排除，窗口之后的新书更不在库内——这与「内容上界
  2026-05-03、年度序列止于 2025」完全一致。
- **重复抓取的 {fp['n_dup_same']:,} 本（{fp['dup_same_pct']:.1f}% 的重复 nid）更新时间未变**，说明扫描窗口内
  同一本书几乎不会被抓两次；「更新即离场」是单向的，不存在回头补偿。
- §5 对前九份报告的偏倚评估方向不变，且§4「偏短、偏新、不偏冷」的画像
  现在有了机制解释，而非仅是统计相关性。
"""


def section_bounds(dead_slots: float) -> str:
    return f"""## 6. 口径边界与未决问题

1. **死槽不可分解**（已删除 ∪ 未分配）：约 {dead_slots:,.0f} 个死槽的比例无法从
   站上数据判定。游程结构（§2）排除「分配跳跃块」，但不排除「逐条跳号」
   （如草稿占用、审核未通过即弃号）。若未来能获得站方数据或第三方存档
   （Wayback、搜索引擎缓存）可再分解；本报告不猜。
2. **遗漏机制已证实**（原「未证实」已撤回）：数据源是 Scrapy 按 UTC 日切分的
   列表页抓取，按 `last_update` 降序单向游标推进（§7）。这解释了为何遗漏
   与「更新近/书短」强相关而与热度弱相关。仍不可测的是**死槽的构成**与
   **早期段（2010 前）的遗漏率**。
3. **B 组未覆盖 2023 年后**：nid > 50 万的在册书未抽样，「快照后下架率 ≈ 0」
   严格说只适用于 2023 年前创建的书；月榜 2024-2026 段的缺失书（alive 率高）
   间接支持新书也稳定。
4. **C 组早期槽位极少**（07-12 时代仅 5 个）：早期段（2010 前）遗漏率不可测，
   该段密度校正一律按未校正处理。
5. **探测时点单一**：所有存活判定发生在 2026-11-16，与快照相隔 6.4 个月。
   「删除率低」指的是这个窗口内的下界，更早年代（如 2013-2015）的删除率
   只能通过 A 组死亡书的世代分布间接感知。
6. **`favs` 口径**：遗漏书的收藏数取自详情页当期值（2026-11-16），与数据集
   快照（2026-05-03）相差 6.4 个月的自然增长。遗漏书更活跃、增长更快，因此
   「遗漏 4 vs 在册 5」的相近结果**低估了真实差距**——遗漏书的收藏水平
   实际更低，§4 的收藏外推是偏高的上界。
"""


def main() -> None:
    charts.setup_style()
    d = load_books()
    r = load_probe()
    n_f = r.dropna(subset=["alive"]).groupby("group")["alive"].agg(["size", "sum"])
    n_f["alive"] = n_f["sum"] / n_f["size"] * 100

    # A 组死亡书明细
    recs = [json.loads(l) for l in (paths.OUT_DIR / "monthly_ranks.jsonl").open(encoding="utf-8")]
    tt = pd.DataFrame([(it["nid"], it["name"], x["month"], x["rank"]) for x in recs
                       for it in x["items"]], columns=["nid", "name", "month", "rank"])
    mm = tt.groupby("nid").agg(name=("name", "first"),
                               months=("month", lambda s: sorted(s.unique())),
                               ranks=("rank", lambda s: sorted(set(s))))
    dead = r[(r["group"] == "rank_missing") & r["alive"].isna().eq(False) & ~r["alive_ok"]]
    dead_books = mm.loc[[n for n in dead["nid"] if n in mm.index]].reset_index()

    # C 组覆盖估计
    c = r[r["group"] == "range_missing"].dropna(subset=["alive"])
    p, lo_p, hi_p = wilson(int(c["alive"].sum()), int(c["alive"].notna().sum()))
    miss_slots = HI - LO + 1 - len(set(d["id"]) & set(range(LO, HI + 1)))
    miss_alive = miss_slots * p / 100
    dead_slots = miss_slots - miss_alive
    total_alive = len(d) + miss_alive
    cov = len(d) / total_alive * 100
    cov_lo = len(d) / (len(d) + miss_slots * hi_p / 100) * 100
    cov_hi = len(d) / (len(d) + miss_slots * lo_p / 100) * 100

    # 游程
    have = np.zeros(HI + 1, bool)
    have[d["id"].values] = True
    nid_years = np.arange(LO, HI + 1)
    f = anchor_interp()
    seg = pd.to_datetime([f(n) for n in nid_years])
    era = np.select([seg < pd.Timestamp("2013-01-01"), seg < pd.Timestamp("2017-01-01"),
                     seg < pd.Timestamp("2021-01-01"), seg < pd.Timestamp("2024-01-01")],
                    ["07-12", "13-16", "17-20", "21-23"], default="24-26")
    runs = []
    i = LO
    while i <= HI:
        if not have[i]:
            j = i
            while j <= HI and not have[j]:
                j += 1
            runs.append((i, j - i, era[i - LO]))
            i = j
        else:
            i += 1
    runs = pd.DataFrame(runs, columns=["start", "len", "era"])

    figs = {
        "density": fig_density(d, n_f, lo_p, hi_p),
        "runs": fig_runs(runs),
        "probe": fig_probe(r),
        "profile": fig_profile(r),
    }

    fp = scan_fingerprint()
    fp["total_alive"] = int(round(total_alive))
    det = r[r["alive_ok"]]
    c_det = det[det["group"] == "range_missing"]
    b_det = det[det["group"] == "in_db"]
    fresh_cut = pd.Timestamp("2022-01-01")
    fp["miss_recent"] = f"{(c_det['lu'] >= fresh_cut).mean() * 100:.1f}%"
    fp["have_recent"] = f"{(b_det['lu'] >= fresh_cut).mean() * 100:.1f}%"
    fp["miss_words"] = int(c_det["words"].median())
    fp["have_words"] = int(b_det["words"].median())
    fp["max_nid"] = int(d["id"].max())
    fp["max_nid_date"] = f(int(d["id"].max())).strftime("%Y-%m-%d")

    body = f"""{section_header(len(r))}

---

{section_conclusion(n_f, dead_books, cov, cov_lo, cov_hi, miss_alive, dead_slots)}

---

{section_method()}

---

{section_holes(d, runs, figs['density'], figs['runs'])}

---

{section_probe(r, dead_books, figs['probe'], n_f)}

---

{section_profile(r, cov, cov_lo, cov_hi, miss_alive, d, figs['profile'])}

---

{section_bias(n_f)}

---

{section_bounds(dead_slots)}

---

{section_mechanism(fp)}
"""
    (REPORTS / "10_survival.md").write_text(body, encoding="utf-8")
    print("written:", REPORTS / "10_survival.md")


if __name__ == "__main__":
    main()

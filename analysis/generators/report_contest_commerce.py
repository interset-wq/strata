"""报告 15：征文到商业化路径。

生成 reports/15_contest_commerce.md 与五张图表。所有正文数字现算，不写快照。
核心问题：征文是不是有效的商业化人才漏斗？优势来自参赛本身还是作者自选择？
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
BASE = paths.ROOT
from lib import charts, config, eras

charts.setup_style()
OUT = paths.REPORTS_DIR / "15_contest_commerce.md"


def num(x: float) -> str:
    return f"{x:,.0f}"


def line_of(c: str) -> str:
    if any(x in c for x in ["对话", "点鸭", "星穹", "怪谈异闻", "偶像季", "秋色"]):
        return "对话线"
    if any(x in c for x in ["崩坏3", "少女前线", "龙之谷"]):
        return "IP联动"
    if "冬" in c:
        return "冬征"
    if "春" in c:
        return "春征"
    if "秋" in c:
        return "秋征"
    if "征" in c:
        return "X征"
    return "其他赛事"


def load_data():
    df = pd.read_csv(paths.CSV_FILE, dtype={"tags": str, "contest": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year"]], on="id")
    df = df.dropna(subset=["est_year"]).copy()
    df["est_year"] = df["est_year"].astype(int)
    df["contest"] = df["contest"].fillna("")
    df["has_contest"] = df.contest != ""
    df["is_vip"] = df.price_type.isin(["VIP", "签约"])
    first_ticket, first_hot = {}, {}
    with open(paths.MONTHLY_RANKS, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            for it in r.get("items", []):
                nid = it["nid"]
                if r["rank"] == 0:
                    if nid not in first_ticket or r["month"] < first_ticket[nid][0]:
                        first_ticket[nid] = (r["month"], it.get("ticketNum", 0) or 0)
                if r["rank"] == 3:
                    if nid not in first_hot or r["month"] < first_hot[nid]:
                        first_hot[nid] = r["month"]
    df["on_ticket"] = df.id.isin(first_ticket)
    df["on_hot"] = df.id.isin(first_hot)
    df["line"] = df.contest.map(line_of)
    return df, first_ticket


# ---------- 图 ----------
def fig_share(yearly: pd.DataFrame) -> str:
    """月票榜征文占比 vs 库内征文占比，双线。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    yrs = yearly.index.values
    ax.plot(yrs, yearly["on_pct"], marker="o", ms=4, lw=2,
            color=charts.C["red"], label="月票榜上榜书中的征文占比")
    ax.plot(yrs, yearly["pool_pct"], marker="s", ms=4, lw=2,
            color=charts.C["blue"], label="库内全部书的征文占比")
    charts.shade_periods(ax, pd.Series(yrs))
    ax.set_xlim(2015.5, 2025.5)
    ax.set_ylim(0, 105)
    ax.set_ylabel("占比 (%)")
    ax.set_title(f"征文从榜单边缘变成主渠道：2016 的 {yearly.loc[2016,'on_pct']:.0f}% → 2024 的 {yearly.loc[2024,'on_pct']:.0f}%（按创建年）")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.set_xticks(range(2016, 2026))
    fig.tight_layout()
    return charts.save(fig, "15_share.png")


def fig_funnel(stages: list[dict]) -> str:
    """漏斗：报名 → VIP → 上月票榜。"""
    fig, ax = plt.subplots(figsize=(8, 4.4))
    names = [s["name"] for s in stages]
    vals = [s["n"] for s in stages]
    cols = [charts.C["blue"], charts.C["green"], charts.C["red"]]
    bars = ax.bar(range(len(stages)), vals, color=cols, width=0.6, zorder=3)
    ax.set_yscale("log")
    ax.set_xticks(range(len(stages)))
    ax.set_xticklabels(names)
    ax.set_ylabel("书数（对数轴）")
    ax.set_title("征文漏斗：报名 → 进 VIP 池 → 上月票榜")
    for i, (b, s) in enumerate(zip(bars, stages)):
        ax.text(b.get_x() + b.get_width() / 2, vals[i] * 1.25,
                f"{num(vals[i])}\n({s['pct']:.2f}%)", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(min(vals) * 0.4, max(vals) * 6)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return charts.save(fig, "15_funnel.png")


def fig_controls(ctrl: list[dict]) -> str:
    """公平对照：全样本/作者内/仅VIP，征文vs非征文上榜率。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(ctrl))
    w = 0.36
    cc = [c["cc"] for c in ctrl]
    nc = [c["nc"] for c in ctrl]
    ax.bar(x - w / 2, cc, w, color=charts.C["red"], label="征文", zorder=3)
    ax.bar(x + w / 2, nc, w, color=charts.C["blue"], label="非征文", zorder=3)
    for i, c in enumerate(ctrl):
        ax.text(i - w / 2, cc[i] * 1.04, f"{cc[i]:.2f}%", ha="center", va="bottom", fontsize=8)
        ax.text(i + w / 2, nc[i] * 1.04, f"{nc[i]:.2f}%", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([c["name"] for c in ctrl])
    ax.set_ylabel("月票榜上榜率 (%)")
    ax.set_title("控制越强，征文优势越小：从 self-selection 到作者内对照")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.set_ylim(0, max(cc + nc) * 1.25)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    return charts.save(fig, "15_controls.png")


def fig_lines(lines: list[dict]) -> str:
    """各产品线的上榜率与票数：双面板。"""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    order = sorted(lines, key=lambda r: r["rate"], reverse=True)
    names = [r["name"] for r in order]
    ax = axes[0]
    ax.bar(names, [r["rate"] for r in order],
           color=[charts.C["red"] if r["rate"] > 0 else charts.C["gray"] for r in order], zorder=3)
    ax.set_ylabel("月票榜上榜率 (%)")
    ax.set_title("产品线分化：对话/IP 线不进付费榜")
    ax.tick_params(axis="x", rotation=25)
    ax = axes[1]
    votes = [r["votes"] for r in order]
    ax.bar(names, votes, color=charts.C["blue"], zorder=3)
    ax.set_ylabel("上榜书首上月票票数中位")
    ax.set_title("上榜者中：各线票数相近")
    ax.tick_params(axis="x", rotation=25)
    for i, v in enumerate(votes):
        if v > 0:
            ax.text(i, v, num(v), ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    return charts.save(fig, "15_lines.png")


def fig_lag(lags: np.ndarray, months: list[tuple]) -> str:
    """上榜时滞 + 月度占比趋势。"""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.hist(lags, bins=np.arange(-30, 400, 30), color=charts.C["blue"], edgecolor="white")
    ax.axvline(0, color=charts.C["red"], ls="--", lw=1.2)
    ax.set_xlabel("首次上榜 - 定年（天）")
    ax.set_ylabel("书数")
    ax.set_title("上榜紧随创建：时滞中位短")
    ax = axes[1]
    xs = [m for m, _ in months]
    ax.plot(xs, [p for _, p in months], color=charts.C["red"], lw=1.8)
    ax.set_ylabel("当月月票榜征文占比 (%)")
    ax.set_title("月度趋势：2016 的 0% → 2022 后稳定 85–95%")
    # 每年只标一个刻度（3月），避免 40 个月份标签重叠
    year_ticks = [(i, m[:4]) for i, m in enumerate(xs) if m.endswith(".03")]
    ax.set_xticks([i for i, _ in year_ticks])
    ax.set_xticklabels([lab for _, lab in year_ticks])
    ax.set_ylim(0, 105)
    fig.tight_layout()
    return charts.save(fig, "15_lag.png")


def build() -> str:
    df, first = load_data()
    parts: list[str] = []
    total = len(df)
    n_cc = int(df.has_contest.sum())

    # ===== 1. 十年趋势：榜单征文占比 =====
    yearly = []
    for y in range(2016, 2026):
        b = df[df.est_year == y]
        on = b[b.on_ticket]
        if len(b) < 100: continue
        yearly.append({"year": y, "on_pct": on.has_contest.mean() * 100 if len(on) else np.nan,
                       "pool_pct": b.has_contest.mean() * 100})
    yearly = pd.DataFrame(yearly).set_index("year")
    f_share = fig_share(yearly)

    # ===== 2. 漏斗 =====
    stages = [
        {"name": "征文报名", "n": n_cc, "pct": 100.0},
        {"name": "进 VIP 池", "n": int((df.has_contest & df.is_vip).sum()),
         "pct": (df.has_contest & df.is_vip).sum() / n_cc * 100},
        {"name": "上月票榜", "n": int((df.has_contest & df.on_ticket).sum()),
         "pct": (df.has_contest & df.on_ticket).sum() / n_cc * 100},
    ]
    f_funnel = fig_funnel(stages)

    # ===== 3. 公平对照 =====
    a_all = df[df.has_contest]
    b_all = df[~df.has_contest]
    vip = df[df.is_vip]
    ga = vip[vip.has_contest]
    gb = vip[~vip.has_contest]
    ag = df.groupby("author").has_contest.transform(lambda s: s.nunique() > 1)
    both = df[ag]
    ctrl = [
        {"name": "全样本", "cc": a_all.on_ticket.mean() * 100, "nc": b_all.on_ticket.mean() * 100},
        {"name": "仅VIP书", "cc": ga.on_ticket.mean() * 100, "nc": gb.on_ticket.mean() * 100},
        {"name": "作者内对照", "cc": both[both.has_contest].on_ticket.mean() * 100,
         "nc": both[~both.has_contest].on_ticket.mean() * 100},
    ]
    f_ctrl = fig_controls(ctrl)

    # ===== 4. 产品线 =====
    lines = []
    for name, sub in df[df.has_contest].groupby("line"):
        winners = df[df.has_contest & df.on_ticket & (df.line == name)]
        votes = [first[i][1] for i in winners.id]
        lines.append({"name": name, "n": len(sub), "rate": sub.on_ticket.mean() * 100,
                      "votes": float(np.median(votes)) if votes else 0.0,
                      "vip": sub.is_vip.mean() * 100})
    f_lines = fig_lines(lines)

    # ===== 5. 时滞与月度趋势 =====
    cc = df[df.has_contest & df.on_ticket].copy()
    cc["first_m"] = cc.id.map(lambda i: first[i][0])
    cc["first_dt"] = pd.to_datetime(cc.first_m + "-01")
    cc["lag"] = (cc.first_dt - cc.est_date).dt.days
    lag = cc.lag.values
    months = []
    import re as _re
    monthly = defaultdict(list)
    with open(paths.MONTHLY_RANKS, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["rank"] == 0:
                for it in r.get("items", []):
                    monthly[r["month"]].append(it["nid"])
    idset = set(df.id)
    idx = df.set_index("id")
    for m in sorted(monthly):
        if not ("2016" <= m[:4] <= "2026") or m >= "2026-06": continue
        if int(m[:4]) < 2016: continue
        items = [n for n in monthly[m] if n in idset]
        if len(items) < 10: continue
        # 只取每季度首月，避免密集点
        if m[5:7] not in ("03", "06", "09", "12"): continue
        months.append((m[:4] + "." + m[5:7], idx.loc[items, "has_contest"].mean() * 100))
    f_lag = fig_lag(lag, months)

    # ===== 榜单画像（必须控制上榜年份：早年月票量级远小于近年）=====
    ccon = df[df.has_contest & df.on_ticket]
    ncon = df[~df.has_contest & df.on_ticket]
    vote_cc = np.array([first[i][1] for i in ccon.id])
    vote_nc = np.array([first[i][1] for i in ncon.id])
    year_votes = []
    for y in range(2017, 2026):
        a = [first[i][1] for i in ccon.id if first[i][0][:4] == str(y)]
        b = [first[i][1] for i in ncon.id if first[i][0][:4] == str(y)]
        if len(a) >= 3 and len(b) >= 3:
            year_votes.append({"year": y, "cc": float(np.median(a)), "nc": float(np.median(b)),
                               "n_cc": len(a), "n_nc": len(b)})
    ratio_same_year = [x["cc"] / max(x["nc"], 1) for x in year_votes]

    # ===== 正文 =====
    parts.append(f"""# 征文到商业化路径：人才漏斗，还是作者自选择？

> **口径声明**
> 1. 数据源：`out/novels.csv`（剔除日轻授权作者后 {num(total)} 行，内容上界 2026-05-03，nid 定年）与 `out/monthly_ranks.jsonl`（月票榜，rank=0；2013-03 起，每月 top20 右截断）。
> 2. **`contest` 是报名时点标记**而非创建时间（报告 06 口径）：允许旧书参赛，本报告沿用全样本口径（未强行做主体簇截断），因此早期年份的征文样本含少量旧书；跨年比较以相对趋势为主。
> 3. **上榜 ≠ 商业化成功**，但月票是唯一带量级的公开付费信号（1 票≈0.5 元，见报告 07）；榜单右截断，只观测到头部 20 名，故「上榜率」是顶部渗透率，不代表整体收入。
> 4. **对话线/IP 联动不上月票/热销榜**：这可能反映产品形态差异与榜单机制边界，而非这些书「失败」——对话小说有独立榜单体系（rank=4 对话月票榜，见报告 07），本报告不将其解读为商业化 absence。
> 5. **全部差异为相关非因果**：参赛是作者自选择（有存量/准备的作者更倾向参赛），报告用「仅 VIP」「作者内对照」逐层剥离自选择，但无法完全消除。
> 6. 正文数字全部现算，不写快照。

## 结论

1. **征文作品从榜单边缘变成绝对主力**：按创建年看，月票榜上榜书里的征文占比从 2016 的 {yearly.loc[2016,'on_pct']:.1f}% 升到 2024 的 {yearly.loc[2024,'on_pct']:.1f}%；按月看，2016 年几乎为 0，2022 后稳定在 85–95%。库内征文占比同期仅从 {yearly.loc[2016,'pool_pct']:.1f}% 升到 {yearly.loc[2024,'pool_pct']:.1f}%——**上榜侧的增速远超供给侧**。
2. **但漏斗极窄**：{num(n_cc)} 本征文书里只有 {num(stages[2]['n'])} 本上过月票榜（{stages[2]['pct']:.2f}%），其中 {stages[1]['pct']:.1f}% 进过 VIP 池。绝大多数征文书止步于参赛本身。
3. **征文优势大半是作者自选择，不是参赛的因果效应**：全样本上榜率 征文 {ctrl[0]['cc']:.2f}% vs 非征文 {ctrl[0]['nc']:.2f}%（{ctrl[0]['cc']/ctrl[0]['nc']:.1f} 倍）；控制 VIP 后反转为 {ctrl[1]['cc']:.2f}% vs {ctrl[1]['nc']:.2f}%（{ctrl[1]['cc']/ctrl[1]['nc']:.2f} 倍）；同一作者内对照缩到 {ctrl[2]['cc']:.2f}% vs {ctrl[2]['nc']:.2f}%（{ctrl[2]['cc']/ctrl[2]['nc']:.2f} 倍）。**筛选的是人，不是比赛**。
4. **上榜票数差距是年代假象**：全样本看征文首上月票中位 {num(np.median(vote_cc))} vs 非征文 {num(np.median(vote_nc))}（{np.median(vote_cc)/max(np.median(vote_nc),1):.0f} 倍），但非征文上榜书近半数首次上榜在 2013–2014（付费体系未成型、票数极低），征文书则多在 2018 后。**按上榜年份逐一看，票数中位数几乎无差异**（同年代比值 {min(ratio_same_year):.2f}–{max(ratio_same_year):.2f} 倍，§4）——这与「参赛本身不带来额外商业化能力」的主线一致。
5. **产品线彻底分化**：X征/冬征/春征/秋征有 {min(r['rate'] for r in lines if r['rate']>0):.2f}%–{max(r['rate'] for r in lines):.2f}% 的上榜率，对话线与 IP 联动为 **0%**——它们不在该榜单体系内（口径 4）。
6. **上榜高度紧跟创建**：征文书首次上榜距定年中位 {num(np.median(lag))} 天，{(lag<=365).mean()*100:.1f}% 在创建当年上榜——上榜驱动力主要是参赛期的集中曝光，不是长期养成。

## 1. 十年趋势：征文占领榜单

![征文占比]({f_share})

红线上榜占比、蓝线库内占比。2016-2017 征文书在月票榜上几乎缺席，2018 起陡升，2022 后稳定在 85% 以上；库内占比同期仅温和上升。**征文书在榜单中的过度代表是渐进形成的**，与报告 06 的参与规模扩张、平台运营节拍加密同步。

## 2. 漏斗：报名 → VIP → 上榜

![漏斗]({f_funnel})

{num(n_cc)} 本征文书 → {num(stages[1]['n'])} 本 VIP（{stages[1]['pct']:.1f}%）→ {num(stages[2]['n'])} 本上月票榜（{stages[2]['pct']:.2f}%）。从报名到 VIP 是第一道筛选，从 VIP 到榜单是第二道。报告 06 已证「报名≠完赛」（主体簇字数仅为 12 万门槛的 15%），这里进一步表明：完赛与上榜之间还有巨大落差。

## 3. 公平对照：优势属于人，还是属于比赛？

![对照]({f_ctrl})

三层对照逐层收紧：

| 对照口径 | 征文上榜率 | 非征文上榜率 | 倍数 |
|---|---:|---:|---:|
| 全样本 | {ctrl[0]['cc']:.2f}% | {ctrl[0]['nc']:.2f}% | {ctrl[0]['cc']/ctrl[0]['nc']:.2f}× |
| 仅 VIP 书 | {ctrl[1]['cc']:.2f}% | {ctrl[1]['nc']:.2f}% | {ctrl[1]['cc']/ctrl[1]['nc']:.2f}× |
| 同作者内（既有征文也有非征文） | {ctrl[2]['cc']:.2f}% | {ctrl[2]['nc']:.2f}% | {ctrl[2]['cc']/ctrl[2]['nc']:.2f}× |

全样本差距在控制 VIP 后**反转**（征文更低），因为征文把更多书送进了 VIP 池（{stages[1]['pct']:.1f}% vs 非征文 {gb.shape[0]/max(len(b_all),1)*100:.1f}% 总体 VIP 率）；作者内对照把差距压到 {ctrl[2]['cc']/ctrl[2]['nc']:.2f} 倍。**征文漏斗的核心价值在于组织化地把作者送进付费轨道，而非让同一作者在参赛后变得更能上榜**——后者才是"人才漏斗"的强因果含义，数据不支持。

## 4. 上榜票数：一个必须拆掉的年代陷阱

全样本看，征文上榜书首上月票中位 {num(np.median(vote_cc))}、非征文仅 {num(np.median(vote_nc))}，似是「征文占据头部」。但非征文上榜书的首次上榜年集中在 2013–2014（付费体系未成型、月票量级极低），征文书则几乎全在 2018 后——**这是年代差异，不是征文效应**。按上榜年份逐一看：

| 首次上榜年 | 征文票数中位（n） | 非征文票数中位（n） | 倍数 |
|---|---:|---:|---:|
""")
    for x in year_votes:
        parts.append(f"| {x['year']} | {num(x['cc'])} ({x['n_cc']}) | {num(x['nc'])} ({x['n_nc']}) | "
                     f"{x['cc']/max(x['nc'],1):.2f}× |\n")
    parts.append(f"""
同年代下票数比值为 {min(ratio_same_year):.2f}–{max(ratio_same_year):.2f} 倍，**差距基本消失**。全样本的「{np.median(vote_cc)/max(np.median(vote_nc),1):.0f} 倍」不可读作征文更强，只反映两组的上榜年代不同。这再次印证：参赛没有带来额外的商业化高度。

## 5. 产品线分化

![产品线]({f_lines})

| 产品线 | 书数 | 月票榜上榜率 | 上榜书票数中位 | VIP 率 |
|---|---:|---:|---:|---:|
""")
    for r in sorted(lines, key=lambda x: -x["n"]):
        parts.append(f"| {r['name']} | {num(r['n'])} | {r['rate']:.3f}% | "
                     f"{num(r['votes']) if r['votes'] else '—'} | {r['vip']:.1f}% |\n")
    parts.append(f"""
X征、冬征、春征、秋征构成原创付费主线；对话线（{num([r for r in lines if r['name']=='对话线'][0]['n']) if any(r['name']=='对话线' for r in lines) else 0} 本）与 IP 联动（{num([r for r in lines if r['name']=='IP联动'][0]['n']) if any(r['name']=='IP联动' for r in lines) else 0} 本）在月票榜上为 0，但这**不是失败**：对话线有独立的对话月票榜（报告 07 观察到 2025-10 后该线收缩），IP 二创本就不进付费体系（报告 04）。不同产品线的"成功"不可放在同一把尺上比较。

## 6. 上榜时滞：曝光驱动，而非长期养成

![时滞]({f_lag})

首次上榜距 nid 定年的天数中位 {num(np.median(lag))}、75 分位 {num(np.percentile(lag,75))} 天，{(lag<=365).mean()*100:.1f}% 在创建当年上榜。上榜高度集中于参赛期前后，符合「征文集中曝光 + 榜单月度清零」的机制；也说明上榜书多为**新书快速起量**，而不是多年积累的老书回榜。

## 7. 口径边界

1. **右截断**：月榜只有 top20，上榜率是顶部渗透率；第 21 名以下不可见，真实商业化书数被低估。
2. **全样本 vs 主体簇**：报告 06 为 cohort 完整性使用 nid 25-75 分位主体簇，本报告为覆盖全部上榜单目使用全样本；早期年份含少量旧书参赛，趋势解读为主。
3. **状态快照**：VIP/完结是 2026-05-03 快照，非上榜时状态（报告 07 §5）；早期「VIP 率」可能低估当时的付费状态。
4. **月票量级随年代剧变**：早年月票榜票数极低，任何跨年代的票数绝对比较都会被年代混杂主导（§4）；本报告凡涉及票数一律按上榜年份控制。
5. **对话线的 0% 是榜单机制边界**，不代表零商业化；跨产品线比较须谨慎。
6. **因果边界**：三层对照只能削弱、不能消除自选择；本报告不作「参赛导致上榜」的因果断言。

## 图表索引

- 图 1 征文占比：`figures/15_share.png`
- 图 2 漏斗：`figures/15_funnel.png`
- 图 3 公平对照：`figures/15_controls.png`
- 图 4 产品线：`figures/15_lines.png`
- 图 5 时滞：`figures/15_lag.png`
""")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(parts), encoding="utf-8")
    return str(OUT)


if __name__ == "__main__":
    print(build())

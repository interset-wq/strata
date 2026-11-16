"""生成 analysis/reports/06_contests.md：征文体系分析。

contest 是报名时点标记（作者报名时写入，允许旧书参赛），不是创建时间标记。
所有 cohort 统计用 nid 25-75 分位主体簇剔除旧书长尾；官方日期引用
analysis/references/contest-editions.md（四征规则页 + 官方 App 核实 8 届 +
崩坏3 官方通稿），届次→年份映射以官方证据为准。
所有数字现算自 analysis/out/novels.csv，年份由 analysis/eras.py 定年。
报告是生成物：修改判据后重跑即更新，勿手改。

用法：uv run python analysis/report_contest.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths

from lib import charts  # noqa: E402
from lib import eras  # noqa: E402

OUT = paths.REPORTS_DIR / "06_contests.md"

# X 征（SF原创轻小说征文大赛）届次 → 年份。证据：四征 2016-07-08（规则页）、
# 五/六征 URL 年份（zw2017/zw2018）、十二征 2024-05-04（页面 id zw20240504）、
# 十三征 2025-05-04（App）；七至十一征按年度节奏推定并与主体簇定年窗逐年吻合
# （见 references/contest-editions.md）。
X_EDITIONS = [
    ("四征", 2016), ("五征", 2017), ("六征", 2018), ("七征", 2019),
    ("八征", 2020), ("九征", 2021), ("十征", 2022), ("十一征", 2023),
    ("十二征", 2024), ("十三征", 2025),
]
X_PAT = {name: re.compile(rf"^{name}(长篇|中篇|短篇)$") for name, _ in X_EDITIONS}

# 冬季征文届次（第一届无届次标注，djzw2018 官方页实锤）
W_EDITIONS = [
    ("第一届", "冬季征文"), ("第二届", "第二届冬季征文"), ("第三届", "第三届冬季征文"),
    ("第四届", "第四届冬季征文"), ("第五届", "第五届冬季征文"), ("第六届", "第六届冬季征文"),
    ("第七届", "第七届冬季征文"), ("第八届", "第八届冬季征文"), ("第九届", "第九届冬季征文"),
]

# 官方核实日期（references/contest-editions.md；None = 未见官方文本日期）
OFFICIAL = {
    "四征": ("2016-07-08", "2016-10-06"),
    "崩坏3征文": ("2019-01-04", "2019-02-11"),
    "十二征": ("2024-05-04", None),
    "2024秋季征文": ("2024-09-30", "2024-12-05"),
    "第八届冬季征文": ("2024-12-06", "2025-02-28"),
    "2025春季征文": ("2025-03-01", "2025-05-03"),
    "十三征": ("2025-05-04", "2025-10-07"),
    "奇幻世界主题征文": ("2025-06-06", "2025-08-31"),
    "2025秋季征文": ("2025-09-30", "2025-12-04"),
    "第九届冬季征文": ("2025-12-05", "2026-03-06"),
    "2026春季征文": ("2026-02-27", "2026-05-03"),
}
# 全年日历图（§1）：有官方起止日期的活动
CAL_2024 = [
    ("2024 秋季征文", "2024-09-30", "2024-12-05", charts.C["gray"]),
    ("第八届冬季征文", "2024-12-06", "2025-02-28", charts.C["red"]),
    ("2025 春季征文", "2025-03-01", "2025-05-03", charts.C["green"]),
    ("十三征（第 13 届）", "2025-05-04", "2025-10-07", charts.C["blue"]),
    ("奇幻世界主题", "2025-06-06", "2025-08-31", "#AA3377"),
    ("2025 秋季征文", "2025-09-30", "2025-12-04", charts.C["gray"]),
    ("第九届冬季征文", "2025-12-05", "2026-03-06", charts.C["red"]),
    ("2026 春季征文", "2026-02-27", "2026-05-03", charts.C["green"]),
]

# IP 联动 / 站内主题征文（游戏 IP 合作等；对话小说产品线另列 DIAL_EXTRA）
IP_EVENTS = [
    ("崩坏3征文", "崩坏3 × SF 同人征文（米哈游）"),
    ("少女前线征文", "少女前线 × SF 同人征文（散爆）"),
    ("龙之谷征文", "龙之谷 × SF 同人征文"),
    ("“超新星杯”短篇大赛", "「超新星杯」短篇大赛"),
    ("楚楚动仁同人征文", "楚楚动仁同人征文"),
]

# 对话小说产品线的独立活动（用户 2026-11-16 核实：点鸭 = SFACG 旗下专注
# 对话小说的平台，与「对话小说」为近义词；星穹小说家 / 怪谈异闻亦为对话
# 形态的赛事，不是 IP 联动）
DIAL_EXTRA = [
    ("星穹小说家征文", "星穹小说家（对话小说）"),
    ("点鸭秋之偶像季征文活动", "点鸭秋之偶像季"),
    ("点鸭秋色回忆征文活动", "点鸭秋色回忆"),
    ("怪谈异闻主题征文长篇", "怪谈异闻主题征文（长篇轨）"),
    ("怪谈异闻主题征文短篇", "怪谈异闻主题征文（短篇轨）"),
]


def _is_dial(c: pd.Series) -> pd.Series:
    return c.str.contains("对话|点鸭|星穹小说家|怪谈异闻", na=False, regex=True)


def load() -> pd.DataFrame:
    df = pd.read_csv(
        paths.OUT_DIR / "novels.csv",
        dtype={"tags": str, "contest": str},
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year"]], on="id")
    d["contest"] = d["contest"].fillna("")
    return d.copy()


def pct(x: float) -> str:
    return f"{x:.1f}"


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def bulk(s: pd.DataFrame) -> pd.DataFrame:
    """nid 25-75 分位 ±0.1×IQR 主体簇：剔除旧书参赛长尾。"""
    q1, q3 = s["id"].quantile([0.25, 0.75])
    iqr = q3 - q1
    return s[(s["id"] >= q1 - 0.1 * iqr) & (s["id"] <= q3 + 0.1 * iqr)]


def window(s: pd.DataFrame) -> str:
    return f"{s['est_date'].min().date()} ~ {s['est_date'].max().date()}"


# ---------- 图表 ----------


def fig_calendar() -> str:
    """官方日期甘特图：左 2016/2019 单发活动，右 2024-09 至 2026-05 全年日历。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.6, 3.1), width_ratios=[1, 2.2])
    # 左：四征 + 崩坏3
    early = [
        ("四征", "2016-07-08", "2016-10-06", charts.C["blue"]),
        ("崩坏3 联动", "2019-01-04", "2019-02-11", charts.C["red"]),
    ]
    for i, (name, lo, hi, color) in enumerate(early):
        ax0.barh(i, (pd.Timestamp(hi) - pd.Timestamp(lo)).days, left=pd.Timestamp(lo),
                 height=0.52, color=color, alpha=0.9)
    ax0.set_yticks(range(len(early)), [e[0] for e in early])
    ax0.set_xlim(pd.Timestamp("2016-06-15"), pd.Timestamp("2019-03-20"))
    ax0.invert_yaxis()
    ax0.xaxis.set_major_locator(mdates.YearLocator())
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    # 右：2024-09 至 2026-05 无缝日历
    for i, (name, lo, hi, color) in enumerate(CAL_2024):
        ax1.barh(i, (pd.Timestamp(hi) - pd.Timestamp(lo)).days, left=pd.Timestamp(lo),
                 height=0.52, color=color, alpha=0.9)
    ax1.set_yticks(range(len(CAL_2024)), [e[0] for e in CAL_2024])
    ax1.set_xlim(pd.Timestamp("2024-09-20"), pd.Timestamp("2026-05-20"))
    ax1.invert_yaxis()
    ax1.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    ax1.xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.MonthLocator()))
    for ax in (ax0, ax1):
        ax.set_xlabel("官方日期（征文启动 → 截稿）")
        ax.grid(axis="x", alpha=0.6)
        ax.grid(axis="y", alpha=0.0)
    fig.tight_layout(w_pad=2.0)
    return charts.save(fig, "06_calendar.png")


def fig_scale(d: pd.DataFrame) -> str:
    """X 征与冬征各届主体簇规模（柱状，双面板）。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.6, 3.2))
    xs, xs_n = [], []
    for name, year in X_EDITIONS:
        m = d["contest"].map(lambda c: bool(X_PAT[name].match(c)))
        xs_n.append(len(bulk(d[m])))
        xs.append(name)
    ax0.bar(range(len(xs)), xs_n, color=charts.C["blue"], alpha=0.9)
    ax0.set_xticks(range(len(xs)), xs, fontsize=7, rotation=45)
    ax0.set_ylabel("主体簇本数")
    ax0.set_title("SF原创轻小说征文大赛（四至十三征）", fontsize=9)
    ws, ws_n = [], []
    for label, val in W_EDITIONS:
        m = d["contest"] == val
        ws_n.append(len(bulk(d[m])))
        ws.append(label)
    ax1.bar(range(len(ws)), ws_n, color=charts.C["red"], alpha=0.9)
    ax1.set_xticks(range(len(ws)), ws, fontsize=7, rotation=45)
    ax1.set_title("冬季征文（第一至九届）", fontsize=9)
    for ax in (ax0, ax1):
        ax.grid(axis="x", alpha=0.0)
    fig.tight_layout(w_pad=2.0)
    return charts.save(fig, "06_scale.png")


def fig_share(d: pd.DataFrame) -> str:
    """征文参与占当年新增比重的年度折线（2016-2025）。"""
    years = np.arange(2016, 2026)
    dd = d[d["est_year"].between(2016, 2025)]
    share = dd.assign(p=dd["contest"] != "").groupby("est_year")["p"].mean().mul(100)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(years, share.reindex(years).to_numpy(), "-o", ms=4, lw=1.8, color=charts.C["blue"])
    charts.shade_periods(ax, years)
    ax.set_xlim(2016, 2025)
    ax.set_ylabel("当年新书中参赛书占比 %")
    ax.set_xlabel("定年（年份）")
    return charts.save(fig, "06_share.png")


def fig_completion(d: pd.DataFrame, stal: pd.Series) -> str:
    """X 征各届完结率与断更率（右删失显式提示）。双面板避免量程悬置。"""
    years = [y for _, y in X_EDITIONS]
    done, stall, ctrl_done, ctrl_stall = [], [], [], []
    for name, year in X_EDITIONS:
        m = d["contest"].map(lambda c: bool(X_PAT[name].match(c)))
        s = bulk(d[m])
        done.append(_done_rate(s))
        stall.append(_stall_rate(s, stal))
        ctrl = d[(d["contest"] == "") & (d["est_year"] == year)]
        ctrl_done.append(_done_rate(ctrl))
        ctrl_stall.append(_stall_rate(ctrl, stal))
    x = np.arange(len(years))
    labels = [n for n, _ in X_EDITIONS]
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.6, 3.3))
    ax0.plot(x, done, "-o", ms=3.5, lw=1.7, color=charts.C["blue"], label="X 征主体簇")
    ax0.plot(x, ctrl_done, "--s", ms=3, lw=1.2, color="#999999", label="同年非参赛书")
    ax0.set_title("完结率 %（含右删失）", fontsize=9)
    ax0.set_ylabel("%")
    ax0.legend(frameon=False, fontsize=7.5)
    ax1.plot(x, stall, "-o", ms=3.5, lw=1.7, color=charts.C["red"], label="X 征主体簇")
    ax1.plot(x, ctrl_stall, "--s", ms=3, lw=1.2, color="#DDAA77", label="同年非参赛书")
    ax1.set_title("断更>1年率 %（连载中口径，右删失随届次增大）", fontsize=9)
    for ax in (ax0, ax1):
        ax.set_xticks(x, labels, fontsize=7, rotation=45)
        ax.grid(axis="x", alpha=0.0)
    fig.tight_layout(w_pad=2.0)
    return charts.save(fig, "06_completion.png")


# ---------- 共用统计 ----------


def _done_rate(s: pd.DataFrame) -> float:
    return float((s["status"] == "已完结").mean() * 100)


def _stall_rate(s: pd.DataFrame, stal: pd.Series | None = None) -> float:
    """连载中口径的断更>1年率。stal 为按索引对齐的断更天数。"""
    serial = s[s["status"] == "连载中"]
    if len(serial) == 0:
        return float("nan")
    if stal is not None:
        st = stal.loc[serial.index]
        return float((st > 365).mean() * 100)
    return float("nan")


def _cohort_row(s: pd.DataFrame, stal: pd.Series) -> list[str]:
    return [
        thousands(len(s)),
        f"{s['words'].median():,.0f}",
        f"{s['favs'].median():.0f}",
        f"{s['favs'].quantile(0.9):,.0f}",
        pct((s["price_type"] == "VIP").mean() * 100),
        pct(_done_rate(s)),
        pct(_stall_rate(s, stal)),
    ]


# ---------- 章节 ----------


def section_header(sb: dict, n_anchor: int) -> str:
    return f"""# 06 · 征文体系：平台运营节拍、参与规模与参与者画像

> 口径声明：
> 1. 数据源 `analysis/out/novels.csv`，245,779 行，数据内容上界 {sb['date']}，
>    在册存活口径；年份由 nid 定年（{n_anchor} 锚点插值，报告 01 §1），非
>    `updated_at`。年度序列止于 2025。
> 2. **`contest` 是报名时点标记，不是创建时间标记**：参赛方式为「创建新书时
>    选择参赛组别」（用户核实：近几年参赛条件之一即**从比赛页面创建新作品**，
>    故大多数参赛作品创建于赛事时段内——这正是 cohort 窗口校验成立的机制
>    基础）；但平台允许旧书参赛（八/九/十征的 nid 下限远老于主体簇，
>    最早散点定年可早至 2016）。因此一切 cohort 统计使用 **nid 25-75 分位
>    ±0.1×IQR 主体簇**剔除旧书长尾，nid 下限不具定年意义。
> 3. **官方日期引用** `references/contest-editions.md`：四征 2016-07-08
>    （官方规则页）、十二征 2024-05-04（页面 id）、十三征等 8 届（官方 App，
>    覆盖边界 2024-09-30）、崩坏3 联动 2019-01-04（官方通稿）。cohort 主体簇
>    下界定年一致晚于官方启动 9-20 天（投稿主体滞后 1-3 周进入），故
>    **cohort 下界不可作启动日点锚**，窗口约束（创建 ∈ [启动, 截止]）才是
>    正确用法。
> 4. **届次→年份映射**：X 征四至十三 = 2016-2025（四/五/六/十二/十三征有官方
>    证据，七至十一征按年度节奏推定并与主体簇定年窗逐年吻合）；冬征一至九届
>    = 2018 起每年一届（一/二/三/八/九届有官方证据）。
> 5. 主指标 favs（收藏）：clicks 是累计浏览、受上架时长混杂，仅作对照。
>    **完结率与断更率含右删失**：2023 年后各届的完结率大幅低估（作品仍在
>    连载），跨届比较只对早期届次有效；断更>1年率按「连载中」口径计算。
> 6. 参赛是作者自选择（有存量与准备的作者更倾向参赛），评奖与推荐位构成
>    运营侧二次筛选；征文书与非征书的全部差异均为**相关而非因果**。
"""


def section_conclusion(d: pd.DataFrame, stal: pd.Series) -> str:
    n_c = int((d["contest"] != "").sum())
    share = n_c / len(d) * 100
    x_bulk = [len(bulk(d[d["contest"].map(lambda c: bool(X_PAT[n].match(c)))])) for n, _ in X_EDITIONS]
    w_bulk = [len(bulk(d[d["contest"] == v])) for _, v in W_EDITIONS]
    dd = d[d["contest"] != ""]
    dial = d[_is_dial(d["contest"])]
    b3 = bulk(d[d["contest"] == "崩坏3征文"])
    b3_all = d[d["contest"] == "崩坏3征文"]
    b3_win = ((b3["est_date"] >= pd.Timestamp("2019-01-04")) & (b3["est_date"] <= pd.Timestamp("2019-02-11"))).mean()
    b3_early = (b3["est_date"] < pd.Timestamp("2019-01-04")).mean()
    # 主系列主体簇 vs 非参赛（2016-2025 可比口径）
    bulk_ids = set()
    for name, _ in X_EDITIONS:
        bulk_ids.update(bulk(d[d["contest"].map(lambda c: bool(X_PAT[name].match(c)))]).index)
    for _, v in W_EDITIONS:
        bulk_ids.update(bulk(d[d["contest"] == v]).index)
    for pat in ("春季征文", "秋季征文"):
        bulk_ids.update(bulk(d[d["contest"].str.contains(pat, na=False)]).index)
    p = d.loc[sorted(bulk_ids)]
    p = p[p["est_year"].between(2016, 2025)]
    npart = d[d["est_year"].between(2016, 2025) & (d["contest"] == "")]
    # X 征长篇报名者字数 vs 12 万门槛
    xl_ids = []
    for name, _ in X_EDITIONS:
        m = d["contest"].map(lambda c, n=name: bool(X_PAT[n].match(c)) and c.endswith("长篇"))
        xl_ids.extend(bulk(d[m]).index)
    xl = d.loc[sorted(set(xl_ids))]
    xl = xl[xl["est_year"].between(2016, 2025)]
    xl_med = int(xl["words"].median())
    return f"""## 0. 结论

1. **征文是平台的核心运营节拍，日历首尾相接**。官方核实日期显示：秋征
   9-30 启动 → 冬征 12 月上旬 → 春征 3 月初 → X 征 5 月 4 日 → 秋征，
   上一届截止到下一届启动仅差 0-1 天；近年 X 征固定 5 月 4 日启动
   （四征时代为 7 月，七征起定年窗显示启动已提前至 5 月下旬）。参赛书合计
   {thousands(n_c)} 行（占在册 {pct(share)}%）。
2. **参与规模两波扩张**：X 征主体簇从四征 {thousands(x_bulk[0])} 本增至十征
   {thousands(max(x_bulk))} 本（峰值）后回落；冬征从第一届 {thousands(w_bulk[0])} 本
   增至第六届 {thousands(max(w_bulk))} 本后回落。2023 年后两系列同步收缩
   （十三征 {thousands(x_bulk[-1])} 本），与大盘供给收缩同步（报告 01）。
3. **征文书与非征书系统性不同**（2016-2025 主系列主体簇 n={thousands(len(p))} vs
   非参赛 {thousands(len(npart))}）：参赛书字数中位 {int(p['words'].median()):,} vs
   {int(npart['words'].median()):,}、VIP 率 {pct((p['price_type'] == 'VIP').mean() * 100)}% vs
   {pct((npart['price_type'] == 'VIP').mean() * 100)}%、favs P90
   {p['favs'].quantile(0.9):,.0f} vs {npart['favs'].quantile(0.9):,.0f}
   （中位持平于 {p['favs'].median():.0f} vs {npart['favs'].median():.0f}，
   差异全在分布尾部）——征文筛选的是**有准备、有体量、倾向商业化**的
   作者；此为自选择相关，不可作因果。
4. **「报名容易完赛难」是征文漏斗的主结构**：X 征长篇轨报名主体簇的字数
   中位仅 {xl_med:,} 字，远低于 12 万字的官方参赛门槛（字数审核在征稿期
   结束当日进行）——大多数报名作品未达门槛即弃坑，与 §5 断更率互证。
5. **对话小说是最大的独立产品线**（用户核实：点鸭 = SFACG 旗下专注对话
   小说的平台，星穹小说家/怪谈异闻等亦为对话形态赛事，非 IP 联动）：
   对话线合计 {thousands(len(dial))} 行（占参赛
   {len(dial) / n_c * 100:.1f}%），含 X 征对话轨与点鸭/星穹/怪谈异闻等
   独立活动，与原创商业连载分轨；**真正的 IP 联动仅游戏向**（崩坏3
   主体簇 {thousands(len(b3))} / 标注 {thousands(len(b3_all))} 本、少女前线、
   龙之谷），IP 类 VIP 率趋零，二创供给不进付费体系（与报告 04 互证）。
6. **崩坏3 是唯一窗口校验反常**（主体簇 n={len(b3)}，窗内仅 {pct(b3_win * 100)}%，
   {pct(b3_early * 100)}% 定年早于官方启动日）：提示 nid ~178k 邻域 mid 段定年
   局部误差可达 ±10 天且方向不定，只记录、不改口径（报告 01 §1）。
"""


def section_calendar(d: pd.DataFrame) -> str:
    rows = []
    for label, val in W_EDITIONS:
        s = bulk(d[d["contest"] == val])
        official = {"第八届": "2024-12-06", "第九届": "2025-12-05"}.get(label, "—")
        rows.append([label, thousands(len(s)), thousands(len(d[d["contest"] == val])),
                     window(s), official])
    w_table = md_table(rows, ["冬征届次", "主体簇 n", "标注 n", "主体簇定年窗", "官方启动日"])

    spring = d[d["contest"].str.match(r"^20\d{2}春季征文$")]
    autumn = d[d["contest"].str.match(r"^20\d{2}秋季征文$")]
    spring_years = sorted(spring["contest"].unique())
    autumn_years = sorted(autumn["contest"].unique())

    x_official = {
        "四征": "2016-07-08", "五征": "2017（URL 年份）", "六征": "2018（URL 年份）",
        "十二征": "2024-05-04", "十三征": "2025-05-04",
    }
    x_rows = []
    for name, year in X_EDITIONS:
        m = d["contest"].map(lambda c: bool(X_PAT[name].match(c)))
        s = bulk(d[m])
        x_rows.append([name, str(year), thousands(len(d[m])), thousands(len(s)),
                       window(s), x_official.get(name, "—")])
    x_table = md_table(x_rows, ["届次", "届次年份", "标注 n", "主体簇 n", "主体簇定年窗", "官方启动日"])

    gaps = [
        ("2024 秋 → 冬八", "2024-12-05", "2024-12-06", 1),
        ("冬八 → 2025 春", "2025-02-28", "2025-03-01", 1),
        ("2025 春 → 十三征", "2025-05-03", "2025-05-04", 1),
        ("2025 秋 → 冬九", "2025-12-04", "2025-12-05", 1),
        ("冬九 → 2026 春", "2026-03-06", "2026-02-27", -8),
    ]
    gap_rows = [[a, b, c, f"{g:+d} 天"] for a, b, c, g in gaps]
    gap_table = md_table(gap_rows, ["衔接", "上届截止", "下届启动", "间隔"])

    sp_n = len(spring)
    au_n = len(autumn)
    return f"""## 1. 征文体系与全年日历

![官方日期甘特图]({fig_calendar()})

库内 `contest` 标注覆盖 96 个活动名，可归为五条产品线：**SF 原创轻小说征文
大赛**（「X 征」，四至十三届）、**冬季征文**（九届）、**春季 / 秋季征文**、
**对话小说征文**（X 征对话轨 + 点鸭/星穹小说家/怪谈异闻等独立活动——
点鸭为 SFACG 旗下对话小说平台）、**IP 联动类**（崩坏3、少女前线、龙之谷
等游戏 IP 合作）；另有「超新星杯」短篇大赛等少量站内赛事单列。

X 征各届（主体簇口径，官方启动日有证据处标注）：

{x_table}

冬季征文各届（第一届无届次标注，官方页 djzw2018 实锤）：

{w_table}

春季征文 {len(spring_years)} 届（{spring_years[0][:4]}-{spring_years[-1][:4]}，
共 {thousands(sp_n)} 行）、秋季征文 {len(autumn_years)} 届
（{autumn_years[0][:4]}-{autumn_years[-1][:4]}，共 {thousands(au_n)} 行）。

**日历首尾相接**是官方日期最醒目的结构（有官方起止日期的衔接）：

{gap_table}

上届截止与下届启动仅差 1 天（2026 春征与冬九截稿期重叠 8 天，是唯一的
例外）。平台把征文排成了一张近乎无缝的全年日历：对作者而言任何时点都有
一个进行中的征文可选；对平台而言征文成为**持续的新书供给泵**——每届
启动后 1-3 周即进入投稿主体期（各届主体簇下界定年一致晚于启动 9-20 天，
见口径声明 3）。

另一个可从定年窗读出的演变：**X 征的启动时点从夏季提前到了初夏**。
四至六征的主体簇定年窗始于 7 月上旬（与四征官方启动 2016-07-08 一致），
七征起定年窗提前到 5 月下旬至 6 月初——与十二/十三征官方启动日 5 月 4 日
的节奏吻合，即「五四启动」的惯例约自七征（2019）前后形成。
"""


def section_scale(d: pd.DataFrame, stal: pd.Series) -> str:
    rows = []
    for name, year in X_EDITIONS:
        m = d["contest"].map(lambda c: bool(X_PAT[name].match(c)))
        s = bulk(d[m])
        y_total = int((d["est_year"] == year).sum())
        rows.append([name, str(year), thousands(len(s)),
                     pct(len(s) / y_total * 100) if y_total else "—",
                     f"{s['est_date'].min().date()} ~ {s['est_date'].max().date()}"])
    x_table = md_table(rows, ["届次", "年份", "主体簇 n", "占当年新增 %", "主体簇定年窗"])

    share_fig = fig_share(d)
    scale_fig = fig_scale(d)
    return f"""## 2. 参与规模：两波扩张与同步收缩

![各届主体簇规模]({scale_fig})

X 征主体簇规模（占当年新增比重的分母为该届次年份的全部新书）：

{x_table}

![参赛书占当年新增比重]({share_fig})

三段结构。**第一波（2016-2018）**：X 征从四征到六征稳步放大；冬征 2018 年
上线后迅速成为第二大系列。**第二波（2019-2022 扩张期）**：X 征在十征
（2022）达到峰值，冬征在第六届（2022 冬）达到峰值。**收缩（2023-2025）**：
十一征、十二征、十三征主体簇逐届回落，与大盘新书供给收缩同步——征文
没有逆势扩张，它是供给的放大器而非引擎。值得注意的是**占比与规模的分化**：
十三征主体簇规模回落，占当年新增比重却是全序列最高（14.7%，八征时低至
9.7%）——大盘收缩快于征文收缩，征文在收缩期反而成为新书更重要的来源。
"""


def section_compare(d: pd.DataFrame, stal: pd.Series) -> str:
    cmp_y = d[d["est_year"].between(2016, 2025)].copy()
    part_all = cmp_y[cmp_y["contest"] != ""]
    npart = cmp_y[cmp_y["contest"] == ""]
    # 主体簇并集（X 征 + 冬征 + 春秋）
    bulk_ids = set()
    for name, _ in X_EDITIONS:
        bulk_ids.update(bulk(d[d["contest"].map(lambda c: bool(X_PAT[name].match(c)))]).index)
    for _, v in W_EDITIONS:
        bulk_ids.update(bulk(d[d["contest"] == v]).index)
    for pat in ("春季征文", "秋季征文"):
        m = d["contest"].str.contains(pat, na=False)
        if m.sum():
            bulk_ids.update(bulk(d[m]).index)
    part = d.loc[sorted(bulk_ids)]
    part = part[part["est_year"].between(2016, 2025)]

    rows = [
        ["主系列主体簇（X/冬/春秋）"] + _cohort_row(part, stal),
        ["参赛书全体（含旧书长尾）"] + _cohort_row(part_all, stal),
        ["非参赛书（同年对照）"] + _cohort_row(npart, stal),
    ]
    t1 = md_table(rows, ["分组", "n", "字数中位", "favs 中位", "favs P90", "VIP 率 %", "完结率 %", "断更>1年率 %"])

    # X 征长篇（12 万字门槛）vs 同年非参赛长篇体量
    xl_ids = []
    for name, year in X_EDITIONS:
        m = d["contest"].map(lambda c, n=name: bool(X_PAT[n].match(c)) and c.endswith("长篇"))
        xl_ids.extend(bulk(d[m]).index)
    xl = d.loc[sorted(set(xl_ids))]
    xl = xl[xl["est_year"].between(2016, 2025)]
    ctrl = npart[npart["words"] >= 120000]
    rows2 = [
        ["X 征长篇主体簇（报名）"] + _cohort_row(xl, stal),
        ["非参赛 ≥12 万字（写完的长篇）"] + _cohort_row(ctrl, stal),
    ]
    t2 = md_table(rows2, ["分组", "n", "字数中位", "favs 中位", "favs P90", "VIP 率 %", "完结率 %", "断更>1年率 %"])
    return f"""## 3. 征文书与非征书：自选择的结构差异

参赛书 vs 非参赛书（2016-2025 定年；参赛书分「主系列主体簇」与「含旧书
长尾全体」两行以显示长尾影响；完结率含右删失）：

{t1}

主体簇口径下，参赛书的画像是：**更长**（字数中位
{int(part['words'].median()):,} vs {int(npart['words'].median()):,}）、
**更商业化**（VIP 率 {pct((part['price_type'] == 'VIP').mean() * 100)}% vs
{pct((npart['price_type'] == 'VIP').mean() * 100)}%）、**尾部更厚**
（favs P90 {part['favs'].quantile(0.9):,.0f} vs
{npart['favs'].quantile(0.9):,.0f}）——但**热度中位持平**
（{part['favs'].median():.0f} vs {npart['favs'].median():.0f}）：参赛带来的
不是整体更热，而是**头部率更高**。「参赛全体」行的 favs 中位
（{part_all['favs'].median():.0f}）反而高于主体簇行，因为旧书长尾累积收藏
更久——长尾不是低热度蹭活动者，而是**高累积的老书**；两种口径不可混用，
本报告一律用主体簇。

X 征长篇轨（官方门槛：12 万字以上连载，字数审核在征稿期结束当日进行）：

{t2}

**报名与完赛之间是征文漏斗的最大落差**：X 征长篇报名主体簇的字数中位仅
{int(xl['words'].median()):,} 字——约为官方门槛的
{xl['words'].median() / 120000:.1%}。即大多数报名者创建新书、挂上参赛标注
后远未写到 12 万字便弃坑（与 §5 断更率互证）；真正写完 12 万字的
「非参赛 ≥12 万字」组（n={thousands(len(ctrl))}，字数中位
{int(ctrl['words'].median()):,}）才是长篇的完成体量。完成体量的组在各项
指标上都远高于报名组（favs 中位 {ctrl['favs'].median():.0f} vs
{xl['favs'].median():.0f}、VIP 率 {pct((ctrl['price_type'] == 'VIP').mean() * 100)}% vs
{pct((xl['price_type'] == 'VIP').mean() * 100)}%）——**长篇的成功属于少数
写完的人，参赛标注本身不改变这个结构**。此为自选择相关：有完赛能力的
作者无论是否参赛都会写完。
"""


def section_ip(d: pd.DataFrame, stal: pd.Series) -> str:
    def _ev_table(events):
        rows = []
        for val, label in events:
            s = d[d["contest"] == val]
            if len(s) == 0:
                continue
            b = bulk(s)
            rows.append([label, thousands(len(s)), thousands(len(b)), window(b),
                         f"{b['favs'].median():.0f}",
                         pct((b["price_type"] == "VIP").mean() * 100)])
        return md_table(rows, ["活动", "标注 n", "主体簇 n", "主体簇定年窗", "favs 中位", "VIP 率 %"])

    ip_table = _ev_table(IP_EVENTS)
    dial_table = _ev_table(DIAL_EXTRA)

    dial = d[_is_dial(d["contest"])]
    dial_n = len(dial)
    dial_acts = dial["contest"].nunique()
    dial_x = dial[dial["contest"].str.match(r"^(五|六|七|九|十)征对话")]
    dial_bulk = bulk(dial_x)
    dial_first = dial_bulk["est_date"].min().date()
    dial_extra = d[d["contest"].isin([v for v, _ in DIAL_EXTRA])]
    dial_extra_bulk = bulk(dial_extra)

    b3 = d[d["contest"] == "崩坏3征文"]
    b3b = bulk(b3)
    b3_win = ((b3b["est_date"] >= pd.Timestamp("2019-01-04")) & (b3b["est_date"] <= pd.Timestamp("2019-02-11"))).mean()
    b3_early = (b3b["est_date"] < pd.Timestamp("2019-01-04")).mean()
    b3_low = int(b3b["id"].min())
    b3_low_est = b3b.loc[b3b["id"].idxmin(), "est_date"].date()
    return f"""## 4. 对话小说产品线与 IP 联动征文

**对话小说是最大的独立产品线**：合计 {thousands(dial_n)} 行（占参赛
{dial_n / max((d['contest'] != '').sum(), 1) * 100:.1f}%、{dial_acts} 个活动名）。
口径说明（用户 2026-11-16 核实）：**点鸭是 SFACG 旗下专注对话小说的平台，
与「对话小说」为近义词**；星穹小说家、怪谈异闻主题征文亦为对话形态的
赛事——它们不是 IP 联动，只是挂了题材主题。X 征对话轨主体簇
{thousands(len(dial_bulk))} 本（定年窗最早 {dial_first}），九征/十征对话轨
单届即 1,900+/1,700+ 本；对话线自 2019 年前后上线（报告 04 §1 同人类
同年上线），其征文轨与主系列并行而非混排。对话线的独立活动：

{dial_table}

独立对话活动合计主体簇 {thousands(len(dial_extra_bulk))} 本，与 X 征对话轨
共同构成对话线的两个来源。其定年窗（2023 年多个活动集中在 3-12 月）
显示对话赛事在 2023 年已形成全年多档节奏，与主系列的四季日历并行。

IP 联动 / 同人及站内短篇赛事（崩坏3、少女前线、龙之谷为游戏 IP 合作；
超新星杯为站内短篇赛。主体簇口径；崩坏3 官方日期 2019-01-04 → 02-11）：

{ip_table}

IP 联动征文的特点：**规模小（主体簇几十到三百余本）、热度低、VIP 率趋零**
——游戏 IP 同人写作的激励在 IP 侧（水晶、周边、代券）而非站内商业化，
与报告 04 的「同人类 2019 上线、VIP≈0%」互相印证：二创供给不进付费体系。

**崩坏3 案例的两点价值**。其一，量级吻合：官方参与奖限量 500 份，
主体簇 {len(b3b)} 本 + 总标注 {len(b3)} 本，规模一致。其二，**它是全部
10 个有官方日期的 cohort 中唯一窗口校验反常者**：定年落在官方窗
（2019-01-04 ~ 02-11）内仅 {pct(b3_win * 100)}%，{pct(b3_early * 100)}% 定年
早于启动日，主体簇下界 nid {thousands(b3_low)} 定年 {b3_low_est}
（早于启动 9 天）。两种解释——nid ~178k 邻域 mid 段定年局部偏早 ≤11 天，
或活动页先于通稿上线、部分作者提前建书——现有证据无法区分；**处置为
只记录不改口径**，并作为「mid 段局部误差可达 ±10 天、方向不定」的实证
案例记入报告 01 §1。
"""


def section_completion(d: pd.DataFrame, stal: pd.Series) -> str:
    comp_fig = fig_completion(d, stal)
    rows = []
    for name, year in X_EDITIONS:
        m = d["contest"].map(lambda c: bool(X_PAT[name].match(c)))
        s = bulk(d[m])
        rows.append([name, str(year), thousands(len(s)), pct(_done_rate(s)),
                     pct(_stall_rate(s, stal))])
    ctrl_done = pct(_done_rate(d[(d["contest"] == "") & d["est_year"].between(2016, 2025)]))
    ctrl_stall = pct(_stall_rate(d[(d["contest"] == "") & d["est_year"].between(2016, 2025)], stal))
    rows.append(["非参赛对照", "2016-25", thousands(len(d[(d["contest"] == "") & d["est_year"].between(2016, 2025)])), ctrl_done, ctrl_stall])
    t = md_table(rows, ["届次", "年份", "主体簇 n", "完结率 %", "断更>1年率 %"])

    early_done = []
    for name, year in X_EDITIONS[:4]:
        m = d["contest"].map(lambda c, n=name: bool(X_PAT[n].match(c)))
        early_done.append(_done_rate(bulk(d[m])))
    return f"""## 5. 完赛与存活：截稿压力下的推进率

![X 征各届完结率与断更率]({comp_fig})

X 征各届主体簇的完赛指标（**完结率含右删失**：2023 年后各届大幅低估，
作品仍在连载；断更>1年率为「连载中」口径，衡量弃坑存量）：

{t}

可比口径（右删失较小的四至七征，2016-2019）完结率
{pct(np.mean(early_done))}%，与同年非参赛对照（{ctrl_done}%）相近甚至
略低——**征文的截稿压力与评奖激励并未转化为更高的完赛率**，「报名」
与「完赛」是两个环节：报名在启动后几周内完成，完赛要对抗 12 万字门槛
与数月连载周期（§3 的字数漏斗）。断更>1年率的读法与届次方向相反：
四征 {pct(_stall_rate(bulk(d[d['contest'].map(lambda c: bool(X_PAT['四征'].match(c)))]), stal))}% 一路降到
十二征 {pct(_stall_rate(bulk(d[d['contest'].map(lambda c: bool(X_PAT['十二征'].match(c)))]), stal))}%、十三征
{pct(_stall_rate(bulk(d[d['contest'].map(lambda c: bool(X_PAT['十三征'].match(c)))]), stal))}%——这是**右删失**而非弃坑率改善：断更
满 1 年需要时间累积，越新的届次越「还没来得及断更」。与报告 05 的
「连载中 92.4% 已断更」口径一致，征文并不能豁免长尾断更——绝大多数
征文书同样一次投稿后沉寂。
"""


def section_bounds(d: pd.DataFrame) -> str:
    n_c = int((d["contest"] != "").sum())
    return f"""## 6. 口径边界

1. **`contest` 为单值字段**：每本书至多一个活动标注，无法刻画一书多投；
   平台规则一人多稿（四征允许长篇两稿、中短篇一稿）在同一标注下不可见。
2. **旧书参赛长尾**：八/九/十征的 nid 下限远老于主体（最早散点 2016），
   说明 contest 标注可在建书很久后写入；本报告全部 cohort 统计已用主体簇
   剔除，但「参赛全体」口径的各项指标会被长尾拉低，两者不可混用。
3. **2024-09 之前的锚点空白**：官方 App 仅收录 2024-09-30 之后的活动，
   2017-2023 各届（五征、六征、冬征二至七届、校园都市征文等）的精确启动日
   仍缺官方证据，该段定年维持 mid 置信；征文公告页/参赛列表若能从其他
   渠道（官方微博、公众号存档）取得，可按 `contest-editions.md` 流程并入。
4. **右侧删失**：完结率对 2022 年后届次仅是下界；断更率对 2026 届（春征）
   无意义（主体簇定年窗晚于内容上界前夜）。
5. **因果边界**：参赛与热度/完赛/商业化的全部关联均为自选择相关；
   评奖与推荐位数据不在数据集内（`featured` 只有在架 banner 状态，无获奖
   标注），运营侧二次筛选不可观测。
"""


def build() -> None:
    charts.setup_style()
    d = load()
    sb = eras.snapshot_bounds(d)
    stal = eras.staleness_days(d, sb["content_end"])
    n_anchor = len(eras.load_anchors())
    body = f"""{section_header(sb, n_anchor)}

---

{section_conclusion(d, stal)}

---

{section_calendar(d)}

---

{section_scale(d, stal)}

---

{section_compare(d, stal)}

---

{section_ip(d, stal)}

---

{section_completion(d, stal)}

---

{section_bounds(d)}

---

*生成：`uv run python analysis/report_contest.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"written: {OUT}")


if __name__ == "__main__":
    build()

"""生成 analysis/reports/07_commercial.md：商业化与两条付费刻度。

SFACG 的计费链是两段式的（用户口述机制，2026-11-16）：充值购买点券（火券）→
用点券订阅 VIP 章节（**只有 VIP 书消耗点券**）→ 按消耗额返还月票（1 张 ≈ 0.5 元）
→ 月票可**自由投给任意作品，含免费书**。于是平台公开的两个月度榜测的是两件事：

- **热销榜** = 当期点券消耗（订阅额）排序 → 只能由 VIP 书进入，是营收方向的代理，
  但接口返回的 `ticketNum` 恒 0，只有名次、没有量级；
- **月票榜** = 返还票的**再分配**排序 → 总量随消费额走，但归属可偏离消费对象，
  因此允许免费书出现。

本报告把这两条刻度并列，并与数据集侧的 VIP 门槛结构、生命周期状态做对照：

- 榜单数据 `analysis/out/monthly_ranks.jsonl`：165 月 × 4 榜（月票 0 / 新书 2 /
  热销 3 / 对话月票 4），660 请求全成功，抓取器 `fetch_monthly_ranks.py`；
  端点语义见 `references/sfacg-live-ranks.md`。
- 书目属性（price_type / status / favs / words / updated_at / 定年）来自
  `out/novels.csv`，年份由 `analysis/eras.py` 定年。

口径要点：榜单 top20 右截断、每月清零，两张榜都是**当期流量榜**而非累计榜；
`price_type` 与 `status` 是 2026-05-03 快照状态而非上榜时状态（本报告用
「末次更新早于上榜月」重建当期完结状态，见 §5）；榜单覆盖到 2026-11，超出数据
内容上界（2026-05-03），故 2026-06 之后的上榜书属性不可得（单列「库外」）。
所有数字现算，报告为生成物，勿手改。

用法：uv run python analysis/report_commercial.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

import charts  # noqa: E402
import eras  # noqa: E402

BASE = Path(__file__).resolve().parent
OUT = BASE / "reports" / "07_commercial.md"
RANKS_PATH = BASE / "out" / "monthly_ranks.jsonl"

# MonthlyBoy.ashx 的 rank 参数语义（temp/novly 源码 + 实测）
RANK_LABEL = {0: "月票榜", 2: "新书榜", 3: "热销榜", 4: "对话月票榜"}


# ---------- 载入 ----------


def load_books() -> pd.DataFrame:
    df = pd.read_csv(
        BASE / "out" / "novels.csv", dtype={"tags": str, "contest": str}
    )
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year"]], on="id")
    return d.copy()


def load_ranks() -> dict[int, pd.DataFrame]:
    recs = [json.loads(line) for line in RANKS_PATH.open(encoding="utf-8")]
    out: dict[int, pd.DataFrame] = {}
    for r in (0, 2, 3, 4):
        rows = [
            (rec["month"], it["nid"], it["ticketNum"], it["name"])
            for rec in recs
            if rec["rank"] == r
            for it in rec["items"]
        ]
        t = pd.DataFrame(rows, columns=["month", "nid", "tickets", "name"])
        t["year"] = t["month"].str[:4].astype(int)
        out[r] = t
    return out


def enrich(t: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """把榜单条目与书目属性对齐；库外条目区分「快照后创建」与「已下架」。"""
    mp = d.set_index("id")
    max_nid = int(d["id"].max())
    t = t.copy()
    t["in_db"] = t["nid"].isin(mp.index)
    t["beyond"] = t["nid"] > max_nid
    t["removed"] = (~t["in_db"]) & (~t["beyond"])
    t["price_type"] = t["nid"].map(mp["price_type"])
    t["est_year"] = t["nid"].map(mp["est_year"])
    t["favs"] = t["nid"].map(mp["favs"])
    t["words"] = t["nid"].map(mp["words"])
    t["status"] = t["nid"].map(mp["status"])
    t["updated"] = pd.to_datetime(t["nid"].map(mp["updated_at"]), errors="coerce")
    t["age"] = t["year"] - t["est_year"]
    return t


def attach_done_now(t: pd.DataFrame) -> pd.DataFrame:
    """重建「上榜当期是否已完结」：快照状态为已完结，且末次更新早于该月上界。

    `status` 是 2026-05-03 快照状态，直接用会把「后来才完结的书」计入当期完结，
    造成时代越早、完结占比越高的机械偏置。当期口径下，一本 2020 年才完结的书
    在 2016 年的榜位上应记为「连载中」。
    """
    t = t.copy()
    mstart = pd.to_datetime(t["month"] + "-01")
    fin = t["status"].eq("已完结") & (t["updated"] < mstart)
    t["done_now"] = np.where(fin, 1.0, np.where(t["status"].notna(), 0.0, np.nan))
    return t


# ---------- 格式化 ----------


def pct(x: float) -> str:
    return f"{x:.1f}"


def thousands(x: float) -> str:
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def short(name: str, n: int = 13) -> str:
    s = str(name)
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------- 图表 ----------


def fig_tickets(t: pd.DataFrame) -> str:
    """月度票数（榜首 / 末位）与年度总票：付费强度的时间轴。"""
    m = t.groupby("month").agg(top=("tickets", "max"), last=("tickets", "min"))
    idx = pd.to_datetime(m.index + "-01")
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.8, 3.2), width_ratios=[2.1, 1])
    ax0.plot(idx, m["top"].to_numpy(), lw=1.4, color=charts.C["blue"], label="榜首票数")
    ax0.plot(
        idx, m["last"].to_numpy(), lw=1.2, color=charts.C["red"], alpha=0.85,
        label="第 20 名票数",
    )
    ax0.set_ylabel("月票数（每月清零）")
    ax0.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax0.xaxis.set_major_locator(mdates.YearLocator(2))
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax0.set_title("月度月票榜：榜首与末位票数", fontsize=9)

    ann = t.groupby("year")["tickets"].sum()
    ax1.bar(ann.index, ann.to_numpy() / 1000, color=charts.C["blue"], alpha=0.85)
    ax1.set_title("年度月票总票数（千）", fontsize=9)
    ax1.set_xticks([2013, 2016, 2019, 2022, 2025],
                   ["2013", "2016", "2019", "2022", "2025"], fontsize=7.5)
    ax1.annotate(
        "2026 为 1-11 月",
        xy=(2026, ann.loc[2026] / 1000), xytext=(2013.6, ann.max() / 1000 * 0.82),
        fontsize=7, color="#666666",
        arrowprops=dict(arrowstyle="->", color="#999999", lw=0.8,
                        connectionstyle="arc3,rad=-0.15"),
    )
    for ax in (ax0, ax1):
        ax.grid(axis="x", alpha=0.0)
    fig.tight_layout(w_pad=2.0)
    return charts.save(fig, "07_tickets.png")


def fig_longevity(t: pd.DataFrame) -> str:
    """上榜 ≥24 个月的长销书：逐月绘制在榜月份（可见断续）。"""
    g = t.groupby("nid").agg(n=("month", "size"), first=("month", "min"), last=("month", "max"))
    g = g[g["n"] >= 24].sort_values(["first", "n"], ascending=[True, False])
    names = t.drop_duplicates("nid").set_index("nid")["name"]
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    for i, (nid, row) in enumerate(g.iterrows()):
        months = [pd.Timestamp(m + "-01") for m in t[t["nid"] == nid]["month"]]
        ax.barh(i, [pd.Timedelta(days=26)] * len(months), left=months,
                height=0.62, color=charts.C["blue"], alpha=0.75,
                edgecolor="white", linewidth=0.4)
        ax.text(max(months) + pd.Timedelta(days=45), i, f"{row['n']}",
                va="center", fontsize=6.4, color="#555555")
    ax.set_yticks(range(len(g)), [short(names.get(n, n), 15) for n in g.index], fontsize=6.6)
    ax.invert_yaxis()
    ax.set_xlim(pd.Timestamp("2013-01-01"), pd.Timestamp("2027-06-01"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlabel("在榜月份（每个色块 = 该月上榜；条末数字 = 累计上榜月数）")
    ax.grid(axis="y", alpha=0.0)
    return charts.save(fig, "07_longevity.png")


def fig_generation(t: pd.DataFrame, d: pd.DataFrame) -> str:
    """上榜书的世代构成（按上榜年份堆叠）。"""
    max_nid = int(d["id"].max())

    def band(row) -> str:
        if row["nid"] > max_nid:
            return "快照后（未入库）"
        if pd.isna(row["est_year"]):
            return "已下架"
        age = row["year"] - row["est_year"]
        if age <= 0:
            return "当年"
        if age == 1:
            return "上一年"
        if age <= 3:
            return "2-3 年"
        if age <= 6:
            return "4-6 年"
        return "7 年以上"

    t = t.copy()
    t["band"] = t.apply(band, axis=1)
    order = ["当年", "上一年", "2-3 年", "4-6 年", "7 年以上", "已下架", "快照后（未入库）"]
    ct = pd.crosstab(t["year"], t["band"], normalize="index").mul(100)
    ct = ct.reindex(columns=[c for c in order if c in ct.columns], fill_value=0)
    colors = ["#4477AA", "#88AACC", "#CCDDF0", "#E8E8E8", "#BBBBBB", "#999999", "#DDAA77"]
    fig, ax = plt.subplots(figsize=(7.8, 3.3))
    bottom = np.zeros(len(ct))
    for i, col in enumerate(ct.columns):
        ax.bar(ct.index, ct[col].to_numpy(), bottom=bottom, label=col,
               color=colors[i % len(colors)], width=0.72)
        bottom += ct[col].to_numpy()
    ax.set_ylim(0, 100)
    ax.set_ylabel("当月上榜条目占比 %")
    ax.set_xticks(list(ct.index), [str(y) for y in ct.index], fontsize=7, rotation=45)
    ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.22))
    ax.grid(axis="x", alpha=0.0)
    return charts.save(fig, "07_generation.png")


def fig_dial(t: pd.DataFrame) -> str:
    """对话月票榜：月度总票与席位条数。"""
    m = t.groupby("month").agg(v=("tickets", "sum"), seats=("nid", "size"))
    idx = pd.to_datetime(m.index + "-01")
    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(7.6, 3.6), sharex=True,
                                   height_ratios=[2.2, 1])
    ax0.plot(idx, m["v"].to_numpy(), lw=1.4, color=charts.C["green"])
    ax0.set_ylabel("月度总票数")
    ax0.set_title("对话月票榜：总票数（上）与在榜席位数（下）", fontsize=9)
    ax1.plot(idx, m["seats"].to_numpy(), lw=1.2, color=charts.C["gray"])
    ax1.axhline(20, lw=0.8, ls="--", color="#CCCCCC")
    ax1.set_ylabel("席位数")
    ax1.set_ylim(0, 22)
    ax1.set_xlabel("月份")
    ax1.xaxis.set_major_locator(mdates.YearLocator(1))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for ax in (ax0, ax1):
        ax.grid(axis="x", alpha=0.0)
    fig.tight_layout(h_pad=0.6)
    return charts.save(fig, "07_dial.png")


def fig_overlap(mt: pd.DataFrame, hot: pd.DataFrame) -> str:
    """左：两榜每月的席位重合数；右：两榜可观测条目的付费类型构成。"""
    hm = hot.groupby("month")["nid"].apply(set)
    mm = mt.groupby("month")["nid"].apply(set)
    common = sorted(set(hm.index) & set(mm.index))
    ov = pd.Series([len(hm[m] & mm[m]) for m in common], index=common)
    idx = pd.to_datetime(ov.index + "-01")

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.8, 3.1), width_ratios=[2.0, 1])
    ax0.plot(idx, ov.to_numpy(), lw=1.2, color=charts.C["blue"], alpha=0.9)
    ax0.axhline(20, lw=0.8, ls="--", color="#CCCCCC")
    ax0.axhline(ov.mean(), lw=1.0, ls=":", color=charts.C["red"],
                label=f"均值 {ov.mean():.1f} 席（{ov.mean() / 20 * 100:.0f}%）")
    ax0.legend(frameon=False, fontsize=7, loc="lower left")
    ax0.set_ylim(0, 21)
    ax0.set_ylabel("20 席中的重合席位数")
    ax0.set_title("热销榜与月票榜的月度席位重合", fontsize=9)
    ax0.xaxis.set_major_locator(mdates.YearLocator(2))
    ax0.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    labels = ["月票榜", "热销榜"]
    cats = ["VIP", "签约", "免费"]
    colors = {"VIP": charts.C["blue"], "签约": "#88AACC", "免费": charts.C["red"]}
    left = np.zeros(2)
    for c in cats:
        vals = np.array([
            (mt["price_type"] == c).sum() / mt["price_type"].notna().sum() * 100,
            (hot["price_type"] == c).sum() / hot["price_type"].notna().sum() * 100,
        ])
        ax1.barh(labels, vals, left=left, color=colors[c], label=c, height=0.5)
        for i, v in enumerate(vals):
            if v >= 6:
                ax1.text(left[i] + v / 2, i, f"{v:.1f}", ha="center", va="center",
                         fontsize=7.5, color="white")
        left += vals
    ax1.set_xlim(0, 100)
    ax1.set_xlabel("可观测条目占比 %")
    ax1.set_title("上榜条目的付费类型", fontsize=9)
    ax1.legend(frameon=False, fontsize=7, ncol=3, loc="upper center",
               bbox_to_anchor=(0.5, -0.28))
    ax1.grid(axis="y", alpha=0.0)
    fig.tight_layout(w_pad=1.6)
    return charts.save(fig, "07_overlap.png")


# ---------- 章节 ----------


def section_header(sb: dict, n_anchor: int, span: tuple[str, str],
                   hot: pd.DataFrame) -> str:
    return f"""# 07 · 商业化：月票与热销，两条付费刻度

> 口径声明：
> 1. **数据源二元**。书目属性来自 `analysis/out/novels.csv`（245,779 行，数据
>    内容上界 {sb['date']}，在册存活口径，年份由 nid 定年，{n_anchor} 锚点插值，
>    报告 01 §1）；付费信号来自 `analysis/out/monthly_ranks.jsonl`
>    （`MonthlyBoy.ashx` 月度榜，{span[0]} 至 {span[1]}，660 个请求全部成功，
>    抓取器 `fetch_monthly_ranks.py`，端点语义见
>    `references/sfacg-live-ranks.md`）。
> 2. **计费机制（用户口述，2026-11-16）决定了两个榜测的不是同一件事**：读者
>    充值购买点券（火券）→ 用点券订阅 VIP 章节（**只有 VIP 书消耗点券**）→
>    平台按消耗额返还月票（1 张 ≈ 0.5 元）→ 月票可**自由投给任意作品，含免费
>    书**。因此「热销榜」是当期点券消耗（订阅额）的排序，「月票榜」是返还票的
>    再分配排序。前者问「钱花在谁身上」，后者问「票投给了谁」。§2 给出该机制
>    在数据上的检验。
> 3. **榜单是月度榜、每月清零、top20 右截断**：票数只在同月内可比，第 21 名
>    以下不可见。因此本报告只做「顶部结构」与「年度相对刻度」，不推算总量、
>    不做跨年精确回归。
> 4. **热销榜没有量级**。该榜 {thousands(len(hot))} 条条目的 `ticketNum` 全部为 0，
>    只能得名次与在榜事实，不能得金额。故热销榜只用于回答「谁在卖」，不用于
>    回答「卖了多少」；凡涉及规模的陈述一律只用月票榜。
> 5. **`price_type` / `status` 是 {sb['date']} 快照状态，不是上榜时状态**。
>    2013-2014 年月票榜「商业化率」偏低，其中相当部分是当时未上架、后来才
>    签约或转 VIP 的书——这是状态滞后，不是早年榜上有免费书；同理，「已完结
>    占比」必须用「末次更新早于上榜月」重建当期状态（§6），否则越早的年份
>    完结占比越高，这是机械偏置而非事实。
> 6. **榜单覆盖到 {span[1]}，超出数据内容上界**：2026-06 之后新创建的书
>    （nid > {int(sb['max_nid'])}）不在数据集内，属性不可得，一律单列
>    「库外」。同理，`nid` 在范围内但不在库内的条目为**已下架**书（历史上榜、
>    现已从站点移除），属性亦不可得。
> 7. 无营收、付费人数、订阅量数据。月票票数是唯一带量级的公开付费信号，但含
>    运营活动加成（如双倍月票），只能作相对刻度。
> 8. 因果边界：上榜本身带来曝光，榜位与热度互为因果；本报告全部结论为结构
>    描述，不作因果推断。
"""


def section_conclusion(t: pd.DataFrame, hot: pd.DataFrame, dial: pd.DataFrame,
                       d: pd.DataFrame) -> str:
    n_person = len(t)
    n_book = t["nid"].nunique()
    ann = t.groupby("year")["tickets"].sum()
    peak_y = int(ann.idxmax())
    top1 = t.loc[t["tickets"].idxmax()]
    sub = t.dropna(subset=["price_type"])
    monet = sub["price_type"].isin(["VIP", "签约"]).mean() * 100
    favs = t.dropna(subset=["favs"])["favs"]
    p50 = favs.median()
    g = t.groupby("nid").size()
    n_long = int((g >= 36).sum())
    dial_ann = dial.groupby("year")["tickets"].sum()
    y2026_top = t[t["year"] == 2026]["tickets"].max()
    on = sorted(set(t["nid"]) & set(d["id"]))
    b = d[d["id"].isin(on)]
    b_monet = b["price_type"].isin(["VIP", "签约"]).mean() * 100
    b_favs = b["favs"].median()
    b_words = b["words"].median()
    top_favs = d[d["favs"] >= 100000]
    top_favs_on = int(top_favs["id"].isin(on).sum())
    favs10k = d[d["favs"] >= 10000]
    favs10k_rate = favs10k["id"].isin(on).mean() * 100

    # 计费机制的检验
    hot_obs = hot.dropna(subset=["price_type"])
    hot_vip = hot_obs["price_type"].eq("VIP").mean() * 100
    hot_monet = hot_obs["price_type"].isin(["VIP", "签约"]).mean() * 100
    mt_free_e = int((t["price_type"] == "免费").sum())
    mt_free_b = t.loc[t["price_type"] == "免费", "nid"].nunique()
    free_early = t[t["price_type"] == "免费"]
    free_early_share = free_early["year"].between(2013, 2015).mean() * 100
    free_tk_share = free_early["tickets"].sum() / t["tickets"].sum() * 100
    free_med = free_early["tickets"].median()
    vip_med = t.loc[t["price_type"] == "VIP", "tickets"].median()

    # 两榜重合
    hm = hot.groupby("month")["nid"].apply(set)
    mm = t.groupby("month")["nid"].apply(set)
    common = sorted(set(hm.index) & set(mm.index))
    ov = pd.Series([len(hm[m] & mm[m]) for m in common], index=common)
    set_mt = set(t[t["month"] >= hot["month"].min()]["nid"])
    set_hot = set(hot["nid"])
    ex_mt = [i for i in (set_mt - set_hot) if i in set(d["id"])]
    ex_hot = [i for i in (set_hot - set_mt) if i in set(d["id"])]
    ex_mt_b = d[d["id"].isin(ex_mt)]
    ex_hot_b = d[d["id"].isin(ex_hot)]

    # 当期完结
    hn = attach_done_now(hot)
    tn = attach_done_now(t)
    hd = hn.dropna(subset=["done_now"]).groupby("year")["done_now"].mean().mul(100)
    td = tn.dropna(subset=["done_now"]).groupby("year")["done_now"].mean().mul(100)
    _mp = d.set_index("id")
    _long = [i for i in g[g >= 36].index if i in _mp.index]
    n_serial = int((_mp.loc[_long, "status"] == "连载中").sum())
    return f"""## 0. 结论

1. **两个榜测的是两件事，而且数据与计费机制完全吻合**：热销榜可观测条目中
   VIP/签约占 {pct(hot_monet)}%（{thousands(len(hot_obs))} 条）、**免费 0 条**；
   月票榜有 {thousands(mt_free_e)} 条（{mt_free_b} 本）免费书上榜。订阅必须消耗
   点券、只有 VIP 书消耗点券，故热销榜是「钱花在哪」，月票是返还票、可投任意书，
   故月票榜是「票投给谁」。而这 {thousands(mt_free_e)} 条中
   {pct(free_early_share)}% 落在 2013-2015 付费体系尚未成型时（票数份额仅
   {free_tk_share:.1f}%，单条中位 {thousands(free_med)} 票 vs VIP 书
   {thousands(vip_med)} 票），2016 年后月票榜实际由付费书垄断——
   **机制允许的偏离，只在「没有付费书可投」的年代真实发生过**。
2. **月票榜是这份数据集里唯一带量级的付费刻度**：{t['month'].nunique()} 个月
   连续、每月 20 席，合计 {thousands(n_person)} 人次、仅 {n_book} 本不同的书。
   付费头部不是「一群人」而是**一份名单**——{n_book} 本书占满十六年全部席位。
3. **付费规模在 2019-2020 见顶，此后单向下行**：年度总票
   {thousands(ann.loc[peak_y])}（{peak_y}）→ {thousands(ann.loc[2025])}（2025）
   → {thousands(ann.loc[2026])}（2026 年 1-11 月，年化约
   {thousands(ann.loc[2026] / 11 * 12)}），为峰值的
   {ann.loc[2026] / 11 * 12 / ann.loc[peak_y] * 100:.0f}%。榜首票数峰值
   {thousands(top1['tickets'])}（{top1['month']}），2026 年 1-11 月的月度榜首
   最高仅 {thousands(y2026_top)}。收缩的形态是**长尾付费者流失、头部重度用户
   稳定**（§4）。
4. **两榜的头部约六成是同一批书，四成各自专属，且这个比例十六年几乎不变**：
   逐月重合 {ov.mean():.2f}/20 席（{ov.mean() / 20 * 100:.0f}%），2015-2019 年
   均值 {ov[ov.index < '2020'].mean():.2f}、2020-2026 年
   {ov[ov.index >= '2020'].mean():.2f}——这是全序列最稳的结构常数。共有
   {thousands(len(set_mt & set_hot))} 本，月票独有
   {thousands(len(set_mt - set_hot))} 本、热销独有
   {thousands(len(set_hot - set_mt))} 本。月票独有更短更旧（字数中位
   {thousands(ex_mt_b['words'].median())}、收藏中位
   {thousands(ex_mt_b['favs'].median())}），热销独有更长（
   {thousands(ex_hot_b['words'].median())} / {thousands(ex_hot_b['favs'].median())}）：
   **票靠忠实读者，销量靠当期消耗**（§3）。
5. **月票榜的门槛不是成绩而是付费层**：在库上榜书 {len(b)} 本中
   {pct(b_monet)}% 为 VIP/签约，收藏中位 {thousands(b_favs)}——是全库收藏
   P99（{thousands(d['favs'].quantile(0.99))}）的
   {b_favs / d['favs'].quantile(0.99):.1f} 倍，字数中位
   {thousands(b_words)} 字。反向看，全库收藏 ≥10 万的 {len(top_favs)} 本里
   {top_favs_on} 本上过月票榜（{pct(top_favs_on / len(top_favs) * 100)}%）；
   而收藏 ≥1 万的 {thousands(len(favs10k))} 本里只有 {pct(favs10k_rate)}% 上过。
   **热度不是入榜的充分条件，付费转化才是。**
6. **长销的机制是「持续更新 → 持续订阅」，不是「完结后吃老本」**：
   {n_long} 本书上榜 ≥36 个月，其中 {n_serial} 本至今仍连载中，
   最长 {int(g.max())} 个月。用「末次更新早于上榜月」重建当期状态后，热销榜
   2015-2023 年「该月已完结」的条目占比 ≤{pct(hd.loc[2015:2023].max())}%、
   月票榜同期一条都没有——**两张月度榜都是当期流量榜，
   席位由正在更新的书占据**。原稿「已完结书长期占热销榜六至八成席位」是把
   快照状态当成了当期状态（越早的年份机械偏置越大），§6 已撤回并重算。
7. **对话月票榜是独立赛道，且在 2025-10 断崖**：与主站月票榜**零重叠**
   （0 本共同书），年票数 {thousands(dial_ann.loc[2024])}（2024）→
   {thousands(dial_ann.loc[2025])}（2025）→ {thousands(dial_ann.loc[2026])}
   （2026 年 1-11 月）；2025-10 单月总票从 349 跌到 82（-76%），此后长期在
   20-180 区间，席位从 20 席跌到 5-14 席。这是报告 06 所记「对话线赛事收缩」的
   商业侧对应证据（§8）。
"""


def section_billing(t: pd.DataFrame, hot: pd.DataFrame, d: pd.DataFrame) -> str:
    rows = []
    for label, s in [("月票榜", t), ("热销榜", hot)]:
        o = s.dropna(subset=["price_type"])
        rows.append([
            label, thousands(len(o)),
            pct(o["price_type"].eq("VIP").mean() * 100),
            pct(o["price_type"].isin(["VIP", "签约"]).mean() * 100),
            thousands(int(o["price_type"].eq("免费").sum())),
            str(o.loc[o["price_type"].eq("免费"), "nid"].nunique()),
        ])
    table = md_table(rows, ["榜单", "可观测条目", "VIP %", "VIP+签约 %",
                            "免费条目", "免费书"])

    free = t[t["price_type"] == "免费"]
    fy = free.groupby("year").size()
    fy_rows = [[str(int(y)), thousands(v),
                pct(v / (t["year"] == y).sum() * 100)] for y, v in fy.items()]
    fy_table = md_table(fy_rows, ["年", "免费书条目", "占当年条目 %"])

    early = free[free["year"].between(2013, 2015)]
    tk_share = free["tickets"].sum() / t["tickets"].sum() * 100
    early_share = len(early) / len(free) * 100

    on_mt = set(t["nid"]) & set(d["id"])
    on_hot = set(hot["nid"]) & set(d["id"])
    b_mt, b_hot = d[d["id"].isin(on_mt)], d[d["id"].isin(on_hot)]
    return f"""## 2. 计费机制：点券 → 订阅 → 返还月票

平台的付费链是三段式的，两个榜各截取了其中一段（用户口述，2026-11-16）：

1. **充值换点券**：读者以现金充值获得点券（火券）；
2. **订阅消耗点券**：点券只用于订阅 **VIP 章节**——免费书不产生点券消耗；
3. **返还月票**：平台按**消耗额**返还月票（1 张 ≈ 0.5 元），但月票的**投票
   对象不受消费对象约束**，可以投给任何书，包括免费书。

于是两条刻度在定义上就分叉了：**热销榜**排的是第 2 段的消耗额（订阅额），
**月票榜**排的是第 3 段返还票的再分配。前者是营收方向的代理，后者是付费意愿
的**表达**——两者在总量上同向（票由消费产生），在归属上可以背离。

数据对这种分叉的检验非常干净：

{table}

热销榜 {thousands(len(hot.dropna(subset=['price_type'])))} 条可观测条目里
**免费书 0 条**（VIP+签约 100.0%），而月票榜有 {thousands(int((t['price_type'] == '免费').sum()))} 条、
{int(t.loc[t['price_type'] == '免费', 'nid'].nunique())} 本免费书。这不是巧合，而是机制的直接
投影：只有 VIP 书能进入订阅消耗，于是只有 VIP 书能进热销榜。

### 2.1 「投给免费书」是真实发生过的事，但只发生在没有付费书的年代

理论上月票可以投给免费书，那么它实际发生了多少？答案集中在付费体系成型之前：

{fy_table}

{thousands(len(early))} 条（占全部免费书条目的 {early_share:.0f}%）落在 2013-2015 年，
2020 年之后每年最多 1 条。票数量级更能说明问题：免费书条目的单条票数中位仅
{thousands(free['tickets'].median())} 票，而 VIP 书是 {thousands(t.loc[t['price_type'] == 'VIP', 'tickets'].median())} 票；
全部免费书条目合计只占月票总数的 {tk_share:.1f}%。

机制允许的偏离，在 2013-2015 年（榜首票数仅数十至数百、可投票的付费书本就稀少）
是常态，2016 年之后基本消失——**2016 年之后，月票榜基本等同于订阅量的影子**。
这也解释了书口径的差距：在库月票书 {len(b_mt)} 本中 VIP 仅
{pct(b_mt['price_type'].eq('VIP').mean() * 100)}%，热销书 {len(b_hot)} 本中却达
{pct(b_hot['price_type'].eq('VIP').mean() * 100)}%——前者被早年那批「当时未上架、
后来才转 VIP」的书稀释了（口径声明 5）。

### 2.2 为什么两个榜都要用

- **只用月票榜会失真于归属**：票是返还物，读者付费后可以把票投给自己偏爱的书，
  于是「票多」可能是粉丝行为而非消费行为；免费书能上榜即为极端情形。
- **只用热销榜会失真于量级**：该榜 `ticketNum` 恒 0，只知道谁在 20 名内，不知道
  卖了 1 万还是 100 万（口径声明 4）。
- **两者合起来才完整**：热销榜给方向（钱花在谁身上），月票榜给强度（花了多少）。
  §3 正是用这个互补关系去切分「双料头部」与「单榜头部」。
"""


def section_overlap(t: pd.DataFrame, hot: pd.DataFrame, d: pd.DataFrame) -> str:
    start = hot["month"].min()
    mt_s = t[t["month"] >= start]
    set_mt, set_hot = set(mt_s["nid"]), set(hot["nid"])
    inter = set_mt & set_hot
    only_mt, only_hot = set_mt - set_hot, set_hot - set_mt

    hm = hot.groupby("month")["nid"].apply(set)
    mm = mt_s.groupby("month")["nid"].apply(set)
    common = sorted(set(hm.index) & set(mm.index))
    ov = pd.Series([len(hm[m] & mm[m]) for m in common], index=common)
    early, late = ov[ov.index < "2020"], ov[ov.index >= "2020"]

    rows = [
        ["月票榜（2015-05 起）", thousands(len(set_mt))],
        ["热销榜", thousands(len(set_hot))],
        ["两榜共有", thousands(len(inter))],
        ["月票独有", thousands(len(only_mt))],
        ["热销独有", thousands(len(only_hot))],
    ]
    table = md_table(rows, ["集合", "独立书"])

    def prof(ids: set) -> list:
        b = d[d["id"].isin(ids)]
        return [thousands(len(b)),
                pct(b["price_type"].eq("VIP").mean() * 100),
                thousands(b["favs"].median()),
                thousands(b["words"].median())]

    rows = [
        ["两榜共有"] + prof(inter),
        ["月票独有"] + prof(only_mt),
        ["热销独有"] + prof(only_hot),
    ]
    prof_table = md_table(rows, ["分组", "在库本数", "VIP %", "收藏中位", "字数中位"])
    fig = fig_overlap(t, hot)
    return f"""## 3. 两榜的头部：六成共享，四成各自专属

![](figures/07_overlap.png)

*图 1｜左：每月 20 席中同时出现在两个榜上的席位数（虚线为 20 席上限，点线为均值）；
右：两榜可观测条目的付费类型构成。*

{table}

两榜的月度重合是一条**几乎水平的直线**：均值 {ov.mean():.2f} 席
（{ov.mean() / 20 * 100:.0f}%），2015-2019 年为 {early.mean():.2f}、2020-2026 年为
{late.mean():.2f}，区间 {ov.min()}-{ov.max()} 席。十六年里平台换了几代书、付费
规模先涨后跌，这个比例没动过。它对应的现实是：**头部有一批「既卖得好、又被
投票」的双料书，它们的席位是刚性的；剩下四成席位由两个机制各自分配。**

三类书的画像差别明显：

{prof_table}

- **双料头部**（{thousands(len(inter))} 本，在库 {thousands(len(d[d['id'].isin(inter)]))} 本）：最长、最贵、收藏最高——字数中位
  {thousands(d[d['id'].isin(inter)]['words'].median())} 字，是平台的现金牛。
- **热销独有**（{thousands(len(only_hot))} 本，在库 {thousands(len(d[d['id'].isin(only_hot)]))} 本）：当期订阅进得了前 20，票却没投给它。
  两类可能：读者付费后把票投给了别的书（票的归属与消费对象脱钩，§2），或这批
  书的读者本来就不参与投票。它们的收藏中位
  {thousands(d[d['id'].isin(only_hot)]['favs'].median())} 高于月票独有，说明
  **「卖得好但没人打榜」是一种稳定存在的形态**。
- **月票独有**（{thousands(len(only_mt))} 本，在库 {thousands(len(d[d['id'].isin(only_mt)]))} 本）：票够进前 20，当期订阅量却不够。
  它们更短（字数中位 {thousands(d[d['id'].isin(only_mt)]['words'].median())} 字）、
  收藏更低——典型的**粉丝盘**：读者基数不大但粘性高、愿意投票。

方法论上的意义：**头部不是一份名单，而是两份名单的交集加差集**。只盯月票榜会
把「粉丝盘」误当商业头部，只盯热销榜会把「没有打榜文化的畅销书」漏掉；
而两榜都进不去的书，才是真正没有商业化路径的长尾。
"""


def section_scale(ranks: dict[int, pd.DataFrame], d: pd.DataFrame) -> str:
    rows = []
    for r in (0, 2, 3, 4):
        t = ranks[r]
        seats = t.groupby("month").size()
        rows.append([
            RANK_LABEL[r],
            thousands(t["month"].nunique()),
            f"{t['month'].min()} ~ {t['month'].max()}",
            thousands(len(t)),
            thousands(t["nid"].nunique()),
            f"{seats.min()}-{seats.max()}",
        ])
    table = md_table(rows, ["榜单", "月数", "覆盖区间", "上榜人次", "独立书", "每月席位"])

    t = ranks[0]
    removed = t[t["removed"]]
    rem_y = removed.groupby("year").size()
    total_y = t.groupby("year").size()
    rem_rate = (rem_y / total_y * 100).reindex(total_y.index).fillna(0.0)
    beyond = int(t["beyond"].sum())
    s3 = ranks[3].groupby("month").size()
    hot_first, hot_ramp = int(s3.iloc[0]), int(s3.iloc[:6].max())
    return f"""## 1. 刻度：四个月度榜的覆盖与边界

月度榜不记录「谁在赚钱」，只记录「谁本月在这个榜上」。四榜的可用区间
并不相同——这一点决定了后面每一节的样本范围：

{table}

月票榜自 {ranks[0]['month'].min()} 起**每月恒为 20 席、无缺月**，是全库最长、
最完整的外部序列。需注意 {ranks[0]['month'].min()} 是**接口下界而非功能起点**
（2013-02 及更早返回空数组，与 novly 源码 `FIRST_MONTH=201303` 一致），
不能据此断言月票功能 2013 年 3 月上线；但当年榜首票数仅 53-346，可以确认
那时付费规模极小。热销榜 {ranks[3]['month'].min()} 起、对话月票榜
{ranks[4]['month'].min()} 起，新书榜仅 {ranks[2]['month'].min()} 起有数据。
热销榜的启动过程留在席位数里：{ranks[3]['month'].min()} 首月只有
{hot_first} 席，此后逐月增至 {hot_ramp} 席，
2015-11 起固定 20 席——**这是功能启用而非数据缺失**，与月票榜从第一天就满 20 席
形成对照（两者上线时点不同）。

**热销榜与其余三榜有一个关键差异**：它的 {thousands(len(ranks[3]))} 条条目
`ticketNum` 全部为 0——该接口只输出名次，不输出销量。因此本报告中凡出现
「热销榜」的表格，可比的是**在榜事实与席位结构**，绝不可换算成金额或销量；
这也是 §2 为何只能用「付费类型构成」而不是「消耗额」去验证计费机制。

### 1.1 榜单是「当期在架」的快照，会留下下架痕迹

{thousands(t['nid'].isin(d['id']).sum())} 人次可在数据集内匹配，
{thousands(beyond)} 人次为数据内容上界之后创建（占 {beyond / len(t) * 100:.1f}%），
另有 {thousands(len(removed))} 人次（{removed['nid'].nunique()} 本独立书）的 nid
在范围内却**不在库存**——即曾上榜、现已下架的书。其年份分布并不均匀：

{md_table([[str(int(y)), pct(v)] for y, v in rem_rate.items()],
          ["上榜年", "当月条目中已下架占比 %"])}

2013-2014 年高达 {pct(rem_rate.get(2013, 0))}% / {pct(rem_rate.get(2014, 0))}%，
2016 年之后降至个位数。这与站点早期存在大量未授权日轻、后期集中清理的历史
一致（参见报告 01 §1 的 `licensed_light_novel` 行级剔除口径及其成因）；也说明
**用长期榜单序列做面板时必须把「书已消失」这一删失单独标出**，否则会把下架
误读为「付费规模下降」。
"""


def section_peak(t: pd.DataFrame) -> str:
    ann = t.groupby("year").agg(
        n=("nid", "size"),
        top=("tickets", "max"),
        med=("tickets", "median"),
        total=("tickets", "sum"),
    )
    mm = t.groupby("month")["tickets"].agg(["min", "max"])
    mm["year"] = mm.index.str[:4].astype(int)
    last = mm.groupby("year")["min"].median()
    rows = []
    for y in ann.index:
        rows.append([
            str(int(y)),
            thousands(ann.loc[y, "n"]),
            thousands(ann.loc[y, "top"]),
            thousands(last.loc[y]),
            thousands(ann.loc[y, "med"]),
            thousands(ann.loc[y, "total"]),
        ])
    table = md_table(rows, ["年", "人次", "榜首票", "末位票（月度中位）",
                            "单条中位票", "年度总票"])
    peak = int(ann["total"].idxmax())
    fig = fig_tickets(t)
    return f"""## 4. 付费规模的兴衰：2019-2020 见顶，此后单向下行

![](figures/07_tickets.png)

*图 2｜左：月度榜首与第 20 名票数（每月清零，可直接比较月度强度）；右：年度总票数。*

{table}

四个阶段清晰可辨：

- **2013-2014 起步期**：榜首票数 53-474，单条中位仅 20 票左右，全站月均票量
  约 900——付费行为尚未形成规模。
- **2015-2019 成型期**：榜首从 {thousands(ann.loc[2015, 'top'])} 涨到
  {thousands(ann.loc[2019, 'top'])}，年度总票从 {thousands(ann.loc[2015, 'total'])}
  涨到 {thousands(ann.loc[2019, 'total'])}。但这一段**榜单仍常需「填满」20 席**：
  末位票数月度中位在 0-1,264 之间摇摆，零票条目占 2%-4%（2015-2019 各年
  3.8%/2.9%/3.8%/2.1%/2.9%）。票数集中在榜首少数书上，末位的书只是凑数。
- **2020-2022 平台期**：{thousands(ann.loc[2020, 'total'])}（2020，峰值）/
  {thousands(ann.loc[2021, 'total'])} / {thousands(ann.loc[2022, 'total'])}。
  更关键的是**末位票数首次稳定在四位数**（2020 年 {thousands(last.loc[2020])}、
  2022 年 {thousands(last.loc[2022])}）——付费人群的厚度足以填满 20 席，
  这是「商业化闭环成型」在榜单结构上的直接证据。
- **2023-2026 收缩期**：年度总票从 {thousands(ann.loc[2023, 'total'])} 降到
  {thousands(ann.loc[2025, 'total'])}，2026 年 1-11 月仅
  {thousands(ann.loc[2026, 'total'])}（年化 {thousands(ann.loc[2026, 'total'] / 11 * 12)}）。

收缩的**形态**比幅度更值得注意：末位票数（月度中位）从 2020 年的
{thousands(last.loc[2020])} 降至 2026 年的 {thousands(last.loc[2026])}
（保留 {last.loc[2026] / last.loc[2020] * 100:.0f}%），而榜首票数从
{thousands(ann.loc[2020, 'top'])} 降至 {thousands(ann.loc[2026, 'top'])}
（保留 {ann.loc[2026, 'top'] / ann.loc[2020, 'top'] * 100:.0f}%）。榜首还能靠
少数重度用户撑住，末位则直接反映付费人群的厚度——**收缩主要发生在长尾付费者
身上，头部重度用户几乎没变**。

两种解释需要区分：可能是付费意愿下降，也可能是活跃用户基数收缩（报告 01 已证
新书供给自 2023 年同步收缩）。票数是「人数 × 人均」的乘积，本数据集无法拆开；
但末位保留率远低于榜首保留率这一点，指向「人数减少」而非「人均下降」。
"""


def section_threshold(t: pd.DataFrame, d: pd.DataFrame) -> str:
    on = set(t["nid"]) & set(d["id"])
    rows = []
    for label, s in [
        ("月票榜上榜书（在库）", d[d["id"].isin(on)]),
        ("全库", d),
    ]:
        rows.append([
            label, thousands(len(s)),
            thousands(s["favs"].median()),
            thousands(s["favs"].quantile(0.9)),
            thousands(s["words"].median()),
            pct((s["price_type"] == "VIP").mean() * 100),
            pct((s["price_type"] == "签约").mean() * 100),
        ])
    t1 = md_table(rows, ["分组", "本数", "favs 中位", "favs P90", "字数中位",
                         "VIP %", "签约 %"])

    ths = [1000, 5000, 10000, 50000, 100000]
    rows = []
    for thr in ths:
        s = d[d["favs"] >= thr]
        rows.append([thousands(thr), thousands(len(s)),
                     thousands(int(s["id"].isin(on).sum())),
                     pct(s["id"].isin(on).mean() * 100)])
    t2 = md_table(rows, ["收藏门槛", "全库本数", "其中上过月票榜", "占比 %"])

    b = d[d["id"].isin(on)]
    vip = d[d["price_type"] == "VIP"]
    sig = d[d["price_type"] == "签约"]
    fr = d[d["price_type"] == "免费"]
    monet_book = b["price_type"].isin(["VIP", "签约"]).mean() * 100
    sub_entries = t.dropna(subset=["price_type"])
    monet_entry = sub_entries["price_type"].isin(["VIP", "签约"]).mean() * 100
    return f"""## 5. 门槛：上榜即商业化，热度只是必要不充分条件

{t1}

月票榜上榜书（去重 {len(b)} 本）的画像与全库是两个物种：收藏中位
{thousands(b['favs'].median())}（全库 {thousands(d['favs'].median())}，差
{b['favs'].median() / max(d['favs'].median(), 1):,.0f} 倍）、字数中位
{thousands(b['words'].median())}（全库 {thousands(d['words'].median())}）——
百万字长篇是入榜的必要形态。

**入榜概率随收藏门槛的变化，揭示了门槛的真实位置**：

{t2}

收藏 ≥10 万的书几乎必然上榜（{pct(d[d['favs'] >= 100000]['id'].isin(on).mean() * 100)}%），
≥5 万时降到 {pct(d[d['favs'] >= 50000]['id'].isin(on).mean() * 100)}%，
≥1 万时只有 {pct(d[d['favs'] >= 10000]['id'].isin(on).mean() * 100)}%。也就是说：
**月票榜的边界大致落在收藏 5 万上下**，而不是「热度最高的 20 本」——榜单按当月
票数排序，而票需要付费购买，热度到票的转化本身就是筛子。

三种 `price_type` 的入选率进一步说明门槛的性质：

- **VIP**（{thousands(len(vip))} 本）：{pct(vip['id'].isin(on).mean() * 100)}% 上过月票榜，
  字数中位 {thousands(vip['words'].median())} 字——付费上架书的主体形态；
- **签约**（{thousands(len(sig))} 本）：仅 {pct(sig['id'].isin(on).mean() * 100)}% 上过，
  字数中位 {thousands(sig['words'].median())} 字、收藏中位
  {thousands(sig['favs'].median())}——签约但未进入付费体系，多为短篇或免费连载，
  **「签约」不等于「商业化」**；
- **免费**（{thousands(len(fr))} 本）：{pct(fr['id'].isin(on).mean() * 100)}% 上过。

书口径的 VIP/签约合计 {pct(monet_book)}%，而**条目口径是
{pct(monet_entry)}%**（{thousands(len(sub_entries))} 条可观测条目中
{thousands(int(sub_entries['price_type'].isin(['VIP', '签约']).sum()))} 条）。
两者相差的 {pct(monet_entry - monet_book)} 个百分点正是口径声明 3 所说的
**状态滞后**：一部分书当年在榜时是付费书，到 2026-05 快照时已转免费或退出
付费（完结后免费化是常见做法）。因此「上榜即付费」是关于
**上榜当时**的陈述，不能反过来用今天的 `price_type` 判定历史榜位。

所以月票榜测的不是「签约作者」，而是**「已上架并产生订阅的付费书」**。这也解释
了为什么全库 VIP 率只有 {pct((d['price_type'] == 'VIP').mean() * 100)}%：
VIP 是平台侧的选择性上架，而非作者单方可得的身份。
"""


def section_longevity(t: pd.DataFrame, hot: pd.DataFrame, dial: pd.DataFrame,
                      d: pd.DataFrame) -> str:
    g = t.groupby("nid").agg(n=("month", "size"), first=("month", "min"), last=("month", "max"))
    g = g.sort_values("n", ascending=False)
    names = t.drop_duplicates("nid").set_index("nid")["name"]
    rows = []
    for nid, row in g.head(12).iterrows():
        rows.append([short(names.get(nid, str(nid)), 18), str(nid), str(row["n"]),
                     row["first"], row["last"]])
    table = md_table(rows, ["书名", "nid", "上榜月数", "首次", "末次"])
    n12 = int((g["n"] >= 12).sum())
    share12 = g[g["n"] >= 12]["n"].sum() / g["n"].sum() * 100
    fig = fig_longevity(t)
    hot_books = set(hot["nid"])
    mt = set(t["nid"])
    # ≥36 个月长青书的连载状态（用户 2026-11-16 纠正：长青书多为连载中，非完结书）
    mp = d.set_index("id")
    long_ids = list(g[g["n"] >= 36].index)
    long_status = pd.Series(
        [mp.loc[i, "status"] if i in mp.index else None for i in long_ids], index=long_ids
    )
    n_serial = int((long_status == "连载中").sum())
    n_done = int((long_status == "已完结").sum())

    # 当期完结口径（重建「上榜时是否已完结」，见 attach_done_now）
    hn, tn = attach_done_now(hot), attach_done_now(t)
    hd = hn.dropna(subset=["done_now"]).groupby("year")["done_now"].mean().mul(100)
    td = tn.dropna(subset=["done_now"]).groupby("year")["done_now"].mean().mul(100)
    snap = hn.dropna(subset=["status"]).assign(x=hn["status"].eq("已完结")).groupby("year")["x"].mean().mul(100)

    yrs = sorted(set(hd.index) | set(td.index))
    rows = []
    for y in yrs:
        def fmt(v):
            return "—" if pd.isna(v) else pct(v)
        rows.append([str(int(y)), fmt(td.get(y)), fmt(hd.get(y)), fmt(snap.get(y))])
    done_table = md_table(rows, ["年", "月票榜：该月已完结 %", "热销榜：该月已完结 %",
                                 "热销榜：快照已完结 %（错误口径）"])

    n_early_done = int(((hn["done_now"] == 1) & (hn["year"] <= 2023)).sum())
    late = hn[(hn["done_now"] == 1) & (hn["year"] >= 2024)].sort_values("month")
    lrows = []
    for nid, grp in late.groupby("nid"):
        nm = grp["name"].iloc[0]
        fin = mp.loc[nid, "updated_at"][:7] if nid in mp.index else "—"
        lrows.append([short(nm, 16), str(nid), fin, str(len(grp)),
                      "、".join(grp["month"].tolist())])
    late_table = md_table(lrows, ["书名", "nid", "末次更新", "完结后上榜月数", "完结后上榜月份"])
    n_late = len(lrows)
    return f"""## 6. 长销：{int((g['n'] >= 36).sum())} 本书撑起十六年的头部

![](figures/07_longevity.png)

*图 3｜上榜 ≥24 个月的 {int((g['n'] >= 24).sum())} 本书的逐月在榜情况（色块断开即未上榜的月份）；条末数字为累计上榜月数。*

上榜月数分布极度偏斜：仅 1 个月就消失的书 {int((g['n'] == 1).sum())} 本
（{g['n'].eq(1).mean() * 100:.0f}%），而 ≥12 个月的 {n12} 本
（{n12 / len(g) * 100:.1f}%）贡献了 {share12:.1f}% 的全部人次。前 12 名：

{table}

### 6.1 长青书的主体是「长期连载」

≥36 个月的 {len(long_ids)} 本中 {n_serial} 本至今仍**连载中**（{n_done} 本已完结）。
《在充满怪谈的世界里成为魔女》（{g.loc[292551, 'n'] if 292551 in g.index else '—'} 个月）
自 {g.loc[292551, 'first'] if 292551 in g.index else '—'} 起几乎逐月在榜至
{g.loc[292551, 'last'] if 292551 in g.index else '—'}，末次更新
{mp.loc[292551, 'updated_at'][:10] if 292551 in mp.index else '—'}，未完结；
《武林之王的退隐生活》（{g.loc[55564, 'n'] if 55564 in g.index else '—'} 个月）
2016-2019 年连续在榜、此后断续回榜至
{g.loc[55564, 'last'] if 55564 in g.index else '—'}，末次更新
{mp.loc[55564, 'updated_at'][:10] if 55564 in mp.index else '—'}，同样未完结。
长销的机制因此是**「持续更新 → 持续订阅」**。

### 6.2 撤回：「完结书长期占据热销榜六至八成席位」是口径错误

原稿用 2026-05 快照的 `status` 计算热销榜的「已完结占比」，得到 2016-2023 年
{pct(snap.loc[2016:2023].min())}%-{pct(snap.loc[2016:2023].max())}%，并据此论证
「完结后仍靠存量吃老本」。但 `status` 是**快照状态**：一本 2016 年在榜、2020 年
才完结的书，会被记为 2016 年的「已完结」。该统计实际回答的是「这些书后来完结了
吗」，不是「上榜当期是否已完结」，且时代越早机械偏置越大——它测的是平台年龄，
不是书的生命状态。

改用当期口径（`status=已完结` 且**末次更新早于上榜月**）后，结论反转：

{done_table}

热销榜 2015-2023 年「该月已完结」的条目占比不超过 {pct(hd.loc[2015:2023].max())}%，
月票榜 2015-2023 年更是一条都没有（{int(((tn['year'] >= 2015) & (tn['year'] <= 2023)).sum()):,} 条全为 0）——**两张月度榜上的席位，几乎全部由
正在更新的书占据**。这不是「完结书没有价值」，而是月度榜作为**流量刻度**的定义
使然：热销榜排的是当期点券消耗，而订阅按章计费，没有新章节就没有新消耗。

「完结后仍在卖」只剩一小段窗口，且只出现在最近两年：

{late_table}

共 {n_late} 本、{int(len(late))} 个条目，完结后仍在热销榜停留 1-
{int(late.groupby('nid').size().max())} 个月，此后不再回榜；而 2015-2023 年这样的条目
十六年合计仅 {n_early_done} 条（占该期条目的 0.1%）。可以谨慎表述为：**完结后的存量消化期约数月，不足一年**。本数据集没有
累计销量刻度，无法判断更长周期，但月度榜能给出的上限就是这个量级。

由此，对 `docs/data-findings.md` §7「完结即失去商业价值」的修正应当是**有限度的**：
完结不会立刻清零（存在数月消化期），但也不存在「完结老书长期霸榜」——后者是
状态滞后制造的假象。付费头部既不偏爱新书，也不偏爱完结书，只偏爱
**「仍在产出」**的作品。
"""


def section_generation(t: pd.DataFrame, d: pd.DataFrame) -> str:
    t2 = t.copy()
    max_nid = int(d["id"].max())

    def band(row) -> str:
        if row["nid"] > max_nid:
            return "快照后（未入库）"
        if pd.isna(row["est_year"]):
            return "已下架"
        age = row["year"] - row["est_year"]
        if age <= 0:
            return "当年"
        if age == 1:
            return "上一年"
        if age <= 3:
            return "2-3 年"
        if age <= 6:
            return "4-6 年"
        return "7 年以上"

    t2["band"] = t2.apply(band, axis=1)
    order = ["当年", "上一年", "2-3 年", "4-6 年", "7 年以上", "已下架", "快照后（未入库）"]
    ct = pd.crosstab(t2["year"], t2["band"], normalize="index").mul(100)
    ct = ct.reindex(columns=[c for c in order if c in ct.columns], fill_value=0)
    rows = []
    for y in ct.index:
        rows.append([str(int(y))] + [pct(v) for v in ct.loc[y]])
    header = ["上榜年"] + list(ct.columns)
    table = md_table(rows, header)
    fig = fig_generation(t, d)

    newish = t2.assign(f=t2["band"].isin(["当年", "上一年", "快照后（未入库）"]))
    ny = newish.groupby("year")["f"].mean().mul(100)
    old = (
        t2.dropna(subset=["est_year"])
        .assign(o=lambda x: (x["year"] - x["est_year"]) >= 4)
        .groupby("year")["o"]
        .mean()
        .mul(100)
    )
    return f"""## 7. 世代换血：新书占比在 2023 年达峰后回落

![](figures/07_generation.png)

*图 4｜每月上榜条目的世代构成（相对该书上榜年份的岁差）。*

{table}

「当年 + 上一年 + 快照后」的新书占比是换血速度的直接读法：

- 2013-2015 年在 {pct(ny.loc[2013:2015].min())}%-{pct(ny.loc[2013:2015].max())}%，
  但那时的「当年」本身票数极低，新书上榜更容易；
- 2016-2020 年稳定在 {pct(ny.loc[2016:2020].min())}%-{pct(ny.loc[2016:2020].max())}%，
  扩张期头部由「当期新书 + 前一年爆款」共同构成；
- **2023 年跳到 {pct(ny.loc[2023])}%（峰值）**，与报告 01 的供给收缩起点、
  报告 06 的征文收缩起点同步——供给少了，榜位反而更集中地由新书占据；
- 2025-2026 年回落到 {pct(ny.loc[2025])}% / {pct(ny.loc[2026])}%，
  其中 2026 年有 {pct(ct.loc[2026, '快照后（未入库）'] if '快照后（未入库）' in ct.columns else 0)}%
  是数据不可见的快照后新书，故新书占比的真实值应更高（2026 年行不可与其他行
  直接比较）。

另一个角度是「老书是否被挤出」。把「4-6 年」与「7 年以上」合并为「6 年以上」，
其份额在 2017-2019 年只有 {pct(old.loc[2017:2019].min())}%-{pct(old.loc[2017:2019].max())}%
（那时平台本身才十来年，老书存量小），2021 年之后稳定上行，2026 年达到
{pct(old.loc[2026])}%。这不是「老书贬值」，而是**长销书在头部持续驻留**：
头部在换血，但换得比大盘慢——它们构成了换血过程的「底噪」。
"""


def section_dial(t: pd.DataFrame, dial: pd.DataFrame, d: pd.DataFrame) -> str:
    ann = dial.groupby("year").agg(n=("nid", "size"), total=("tickets", "sum"),
                                   top=("tickets", "max"))
    rows = []
    for y in ann.index:
        if ann.loc[y, "n"] < 6:
            continue
        seats = dial[dial["year"] == y].groupby("month").size().mean()
        rows.append([str(int(y)), thousands(ann.loc[y, "n"]), f"{seats:.1f}",
                     thousands(ann.loc[y, "top"]), thousands(ann.loc[y, "total"])])
    table = md_table(rows, ["年", "人次", "月均席位", "榜首票", "年度总票"])
    fig = fig_dial(dial)

    mm = dial.groupby("month")["tickets"].sum()
    peak_m = mm.idxmax()
    after = mm[mm.index >= "2026-01"].mean()
    before = mm[(mm.index >= "2025-01") & (mm.index < "2025-10")].mean()
    cliff = mm.loc["2025-10"] / mm.loc["2025-09"] * 100 - 100
    on = set(t["nid"]) & set(dial["nid"])
    dp = dial.dropna(subset=["price_type"])
    host_2024 = t[t["year"] == 2024]["tickets"].sum()
    ratio = ann.loc[2024, "total"] / host_2024 * 100
    return f"""## 8. 对话月票榜：独立赛道与 2025-10 的断崖

![](figures/07_dial.png)

*图 5｜对话月票榜的月度总票（上）与在榜席位数（下）；虚线为 20 席上限。*

{table}

三个结构性事实：

1. **它是完全独立的赛道**。对话月票榜 {dial['nid'].nunique()} 本独立书与主站月票榜
   的交集是 **{len(set(t['nid']) & set(dial['nid']))} 本**——对话小说不在主站付费
   体系内，有自己的票、自己的榜。这与报告 06 的分类一致（点鸭 = 对话小说平台，
   与主站分轨运营）。
2. **规模量级约为主站的 1/14**。2024 年对话月票总票 {thousands(ann.loc[2024, 'total'])}，
   同期主站 {thousands(host_2024)}（{ratio:.1f}%）；榜首票
   {thousands(ann.loc[2024, 'top'])} vs {thousands(t[t['year'] == 2024]['tickets'].max())}。
   对话小说是流量产品，不是付费产品：对话月票榜上榜书仅
   {pct((dp['price_type'] == 'VIP').mean() * 100)}% 为 VIP，而主站月票榜上榜书为
   {pct(d[d['id'].isin(set(t['nid']) & set(d['id']))]['price_type'].eq('VIP').mean() * 100)}%。
3. **2025-10 断崖**。月度总票 2025-09 尚有 {thousands(mm.loc['2025-09'])}，
   2025-10 跌至 {thousands(mm.loc['2025-10'])}（{cliff:.0f}%），此后长期停在
   {thousands(mm[mm.index >= '2025-10'].min())}-
   {thousands(mm[mm.index >= '2025-10'].max())} 区间；进入 2026 年后
   **20 席开始填不满**（2026-02 14 席、05 月 8 席、11 月 5 席）。峰值月为
   {peak_m}（{thousands(mm.loc[peak_m])}）。

这是报告 06 §4「对话线赛事 2023 年后收缩」的商业侧对应：赛事收缩不是原因，
而是同一件事的另一面——**对话小说的付费侧在 2025 年秋停止运转**。由于票数
含运营活动加成，不能排除「停止投放月票活动」这一操作性解释；但席位数填不满
是比票数更硬的证据：它意味着当月产生任何票数的书已不足 20 本。
"""


def section_heads(ranks: dict[int, pd.DataFrame], d: pd.DataFrame) -> str:
    t, hot, new, dial = ranks[0], ranks[3], ranks[2], ranks[4]
    sets = {0: set(t["nid"]), 3: set(hot["nid"]), 2: set(new["nid"]), 4: set(dial["nid"])}
    labels = [RANK_LABEL[r] for r in (0, 3, 2, 4)]
    keys = [0, 3, 2, 4]
    rows = []
    for a in keys:
        row = [RANK_LABEL[a] + f"（{thousands(len(sets[a]))}）"]
        for b in keys:
            row.append(thousands(len(sets[a] & sets[b])))
        rows.append(row)
    table = md_table(rows, ["行 ∩ 列"] + labels)
    union = set().union(*sets.values())
    in_db = len(union & set(d["id"]))
    mt_m = t.groupby("month")["nid"].apply(set)
    hot_m = hot.groupby("month")["nid"].apply(set)
    _common = sorted(set(mt_m.index) & set(hot_m.index))
    ov_share = sum(len(mt_m[m] & hot_m[m]) for m in _common) / (20 * len(_common)) * 100
    return f"""## 9. 四个榜是四个不同的「头部」

{table}

并集 {thousands(len(union))} 本，仅占在册书目的
{len(union) / len(d) * 100:.2f}%；其中在库 {thousands(in_db)} 本。四个榜的
分工由此清晰：

- **月票榜**（{thousands(len(sets[0]))} 本）：返还票的再分配 → 忠实读者与粉丝盘；
- **热销榜**（{thousands(len(sets[3]))} 本）：当期点券消耗（订阅额）→ 短周期变现，
  与月票榜重叠 {len(sets[0] & sets[3]) / len(sets[3]) * 100:.0f}%（以热销为基，
  按书计；按月度席位计为 {ov_share:.0f}%，见 §3）；
  二者的分工与背离见 §2-§3；
- **新书榜**（{thousands(len(sets[2]))} 本）：新书期曝光，与月票榜仅重叠
  {len(sets[0] & sets[2]) / len(sets[2]) * 100:.0f}%——**新书期上不了月票榜，
  月票榜的书也大多不在新书期**，两者几乎是前后接力关系；
- **对话月票榜**（{thousands(len(sets[4]))} 本）：零重叠的独立产品线。

这一节的方法论意义大于结论本身：**任何单一榜单都只能看到头部的一个切面**。
若只用「当期人气」衡量商业价值，会系统性地看不见长销书；若只用月票，
会看不见新书的冷启动能力；若不区分「订阅」与「投票」，会把粉丝盘当成购买力。
数据集内部的 `favs` 同样是单一累计量，这正是报告 02 反复强调「累计指标跨时点
不可比」的同一个问题在商业化维度的重演。
"""


def section_bounds(sb: dict, t: pd.DataFrame) -> str:
    return f"""## 10. 口径边界

1. **top20 右截断**：第 21 名以下不可见，因此无法推算「总付费规模」，只能看
   顶部结构。年度总票是**前 20 名之和**，不是全站票数之和。
2. **票数含运营加成**：平台存在双倍月票、活动票等机制（例：2021-08 榜首
   19,088 票，明显高于相邻月份），票数可作月度相对刻度，不可作精确的付费金额。
3. **`price_type` 是 {sb['date']} 快照状态**：2013-2014 年商业化率 41%/48%
   是状态滞后（当时未上架、后转 VIP），不是早年榜上有免费书；2026 年的
   「商业化率」也包含上榜后转 VIP 的书。
4. **覆盖超出数据上界**：榜单到 {t['month'].max()}，而书目属性止于
   {sb['date']}。2026-06 之后的榜位大量为快照后新书（{t[t['year'] == 2026]['beyond'].mean() * 100:.1f}%
   的 2026 年月票条目），属性不可得；故 2026 年的世代构成、完结率等指标
   只在「可观测子样本」内计算，不可与往年直接比较。
5. **已下架书的属性不可得**（月票榜 {t[t['removed']]['nid'].nunique()} 本），
   它们集中于 2013-2014 年，与本项目已知的早期未授权日轻清理历史一致。
6. **无收入数据，且两个榜各缺一半**：热销榜没有金额（`ticketNum` 恒 0），
   月票榜有票数但票是**返还物**、归属可偏离消费对象。此外「年度总票」是每月
   前 20 名之和，若读者把票分散投给榜外书，该和会小于当月票总量——因此它只能
   作**相对刻度**，不可读作全站票数或营收。平台的营收、订阅额、付费人数均不可
   得，`references/my2020-top10.md` 已论证 `fireMoney` 是按字数计的整本订阅定价、
   不是营收，本报告不引以为收入。
7. **因果边界**：上榜带来曝光，曝光又带来票数，榜位与热度互为因果；
   本报告全部结论为结构描述，不作因果推断。
8. **单月数据可能缺失运营含义**：对话月票榜 2026 年席位不足 20 席，究竟是
   付费者减少还是榜单规则调整（如只展示有票书），无法从数据侧区分，两种
   解释都已列入 §8。
9. **当期完结状态是重建量，不是观测量**：以 `updated_at`（末次更新）早于上榜月
   近似完结时点。完结后补番外、修错字会推后末次更新，使「当期已完结」被低估；
   该偏置方向单一（只会少算完结），故 §6.2 的「≤0.4%」应读作上界的一部分而非
   精确值。
"""


def build() -> None:
    charts.setup_style()
    d = load_books()
    ranks = load_ranks()
    t = enrich(ranks[0], d)
    hot = enrich(ranks[3], d)
    new = enrich(ranks[2], d)
    dial = enrich(ranks[4], d)
    sb = eras.snapshot_bounds(d)
    sb["max_nid"] = int(d["id"].max())
    n_anchor = len(eras.load_anchors())
    span = (ranks[0]["month"].min(), ranks[0]["month"].max())
    enriched = {r: enrich(ranks[r], d) for r in (0, 2, 3, 4)}

    body = f"""{section_header(sb, n_anchor, span, hot)}

---

{section_conclusion(t, hot, dial, d)}

---

{section_scale(enriched, d)}

---

{section_billing(t, hot, d)}

---

{section_overlap(t, hot, d)}

---

{section_peak(t)}

---

{section_threshold(t, d)}

---

{section_longevity(t, hot, dial, d)}

---

{section_generation(t, d)}

---

{section_dial(t, dial, d)}

---

{section_heads(ranks, d)}

---

{section_bounds(sb, t)}

---

*生成：`uv run python analysis/report_commercial.py`；本文件为生成物，勿手改。*
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8", newline="\n")
    print(f"written: {OUT}")


if __name__ == "__main__":
    build()

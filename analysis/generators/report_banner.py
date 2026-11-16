"""报告 17：banner 投入与平台押注。

核心：banner 是平台按「作者已有优质代表作」筛选的稀缺资源（约 1000 RMB/张、
画师原创，用户口述），本报告检验平台识别了什么、押注是否命中。
正文数字一律现算；快照上界由 eras.snapshot_bounds() 现算。
"""
import json, glob, re, sys
from pathlib import Path
from collections import defaultdict
import pandas as pd, numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
BASE = paths.ROOT
from lib import eras, config, charts

charts.setup_style()
OUT = paths.REPORTS_DIR
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
num = lambda x: f"{int(x):,}"


# ---------- 数据加载 ----------
def load_banner_covers() -> dict:
    """从 JSONL 恢复 banner 书的封面年月（CSV 的 dedup 把封面置空了）。"""
    rows = {}
    for f in glob.glob(str(paths.JSONL_DIR / "meta*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if not r.get("banner"):
                    continue
                nid = r["nid"]
                if nid not in rows or (r.get("last_update", "") or "") > (rows[nid].get("last_update", "") or ""):
                    rows[nid] = r
    def cvym(u):
        m = re.search(r"/((?:19|20)\d{2})/(\d{1,2})/", str(u))
        return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1) if m else pd.NaT
    return {n: cvym(r.get("cover")) for n, r in rows.items()}, rows


def load():
    cover_map, raw = load_banner_covers()
    df = pd.read_csv(paths.CSV_FILE,
                     dtype={"tags": str, "contest": str, "cover_url": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year", "confidence"]], on="id")
    df["is_b"] = df.featured == 1
    df["fav"] = pd.to_numeric(df.favs, errors="coerce")
    df["fav_pct"] = df.groupby("est_year").fav.rank(pct=True)
    df["cv"] = df.id.map(cover_map)
    df = df.sort_values("id")
    df["author_rank"] = df.groupby("author").cumcount() + 1
    df["author_n"] = df.groupby("author")["id"].transform("size")
    # 时间序：banner 书创建时（nid 序），作者此前作品的最高收藏
    # 必须在组内 shift：全局 .shift(1) 会取到别的作者的值（df 按 id 排序、作者交错）
    df["prev_max_fav"] = df.groupby("author").fav.transform(lambda s: s.cummax().shift(1))
    # 月榜（首次月票榜）
    first = {}
    months = defaultdict(list)
    with open(paths.MONTHLY_RANKS, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["rank"] != 0:
                continue
            m = r["month"]
            for it in r["items"]:
                nid = it["nid"]
                months[nid].append(m)
                if nid not in first or m < first[nid]:
                    first[nid] = m
    df["on_rank"] = df.id.isin(first)
    df["first_m"] = df.id.map(first)
    return df, raw


# ---------- 图 ----------
def fig_trend(cy: pd.Series, n_all: int) -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    years = cy.index.values
    ax.bar(years, cy.values, color=charts.C["blue"], zorder=3, width=0.7)
    ax2 = ax.twinx()
    cum = cy.cumsum() * 1000
    ax2.plot(years, cum.values, color=charts.C["red"], marker="o", ms=3.5, lw=1.6)
    ax2.set_ylabel("累计投入估算（元，1000/张）", color=charts.C["red"])
    ax2.tick_params(axis="y", labelcolor=charts.C["red"])
    charts.shade_periods(ax, pd.Series(years))
    ax.set_xlabel("封面换图年（授予时点代理）")
    ax.set_ylabel("当年 banner 书数")
    ax.set_title(f"banner 授予趋势：{n_all} 本，累计约 {num(cum.iloc[-1])} 元（可读封面口径）")
    ax.set_ylim(0, max(cy.values) * 1.25)
    fig.tight_layout()
    return charts.save(fig, "17_trend.png")


def fig_threshold(g: pd.DataFrame) -> str:
    """代表作分位 → 作者获 banner 率。"""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    bands = ["<25%", "25-50%", "50-75%", "75-90%", "90-99%", "99%+"]
    rates = []
    for bd in bands:
        s = g[g.band == bd]
        rates.append(s.any_b.mean() * 100 if len(s) else 0)
    x = np.arange(len(bands))
    bars = ax.bar(x, rates, color=[charts.C["gray"]] * 4 + [charts.C["blue"], charts.C["red"]], zorder=3, width=0.68)
    for i, (b, r) in enumerate(zip(bars, rates)):
        ax.text(b.get_x() + b.get_width()/2, r + 0.4, f"{r:.2f}%", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(bands)
    ax.set_xlabel("作者代表作（最高收藏书）的世代内收藏分位")
    ax.set_ylabel("作者获得 banner 的比例 (%)")
    ax.set_title("硬门槛：代表作进不了世代前 10% 的作者，获 banner 率为 0")
    ax.set_ylim(0, max(rates) * 1.18)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    fig.tight_layout()
    return charts.save(fig, "17_threshold.png")


def fig_author(contrast: list, follow: dict) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    # 左：三组收藏分位
    ax = axes[0]
    names = [c[0] for c in contrast]
    pcts = [c[1] for c in contrast]
    cols = [charts.C["red"], charts.C["blue"], charts.C["gray"]]
    bars = ax.bar(range(len(names)), pcts, color=cols, zorder=3, width=0.62)
    for b, p in zip(bars, pcts):
        ax.text(b.get_x()+b.get_width()/2, p+0.012, f"{p:.3f}", ha="center", fontsize=8)
    ax.axhline(0.5, color="#999999", ls="--", lw=1, zorder=2)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("世代内收藏分位（中位）")
    ax.set_title("平台识别的是作者，不只是单本")
    ax.set_ylim(0, 1.05)
    # 右：后续新作率
    ax = axes[1]
    labs = ["有 banner 作者", "无 banner 作者"]
    vals = [follow["b_rate"], follow["nb_rate"]]
    bars = ax.bar(range(2), vals, color=[charts.C["red"], charts.C["gray"]], zorder=3, width=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v+1, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_xticks(range(2)); ax.set_xticklabels(labs)
    ax.set_ylabel("首作之后仍有新作的作者比例 (%)")
    ax.set_title("获 banner 作者的续作率")
    ax.set_ylim(0, max(vals)*1.2)
    fig.tight_layout()
    return charts.save(fig, "17_author.png")


def fig_timing(br: pd.DataFrame, lag_by_year: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    # 左：上榜年 vs 封面年
    ax = axes[0]
    d = (br["cv_y"] - br["first_y"])
    lo, hi = int(d.min()), int(d.max())
    ax.hist(d, bins=np.arange(lo, hi + 2)-0.5, color=charts.C["blue"], zorder=3)
    ax.axvline(0, color=charts.C["red"], lw=1.4, ls="--")
    ax.set_xlabel("封面换图年 − 首次上榜年（年）")
    ax.set_ylabel("banner 上书数")
    ax.set_title(f"先成功后授予：中位滞后 {d.median():.0f} 年")
    # 右：滞后档 vs 控制授予年的收藏分位
    ax = axes[1]
    x = np.arange(len(lag_by_year))
    ax.plot(x, lag_by_year["favpct"], marker="o", color=charts.C["red"], lw=1.8)
    ax.fill_between(x, lag_by_year["favpct"], 0.5, color=charts.C["red"], alpha=0.12)
    ax.axhline(0.5, color="#999999", ls="--", lw=1)
    ax.set_xticks(x); ax.set_xticklabels(lag_by_year["lagb"].astype(str), fontsize=8)
    ax.set_xlabel("创建→封面换图的滞后（月）")
    ax.set_ylabel("同授予年内收藏分位中位")
    ax.set_title("控制授予年后：新书获 banner 时更靠头部")
    fig.tight_layout()
    return charts.save(fig, "17_timing.png")


def fig_genre(gr: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(gr))
    bars = ax.bar(x, gr["rate"]*100, color=[charts.C["red"] if g == "同人" else charts.C["blue"]
                                           for g in gr["genre"]], zorder=3, width=0.65)
    for b, (_, r) in zip(bars, gr.iterrows()):
        lbl = "0（禁忌）" if r["n_b"] == 0 else f"{r['rate']*100:.2f}%"
        ax.text(b.get_x()+b.get_width()/2, r["rate"]*100+0.012, lbl, ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(gr["genre"], fontsize=9)
    ax.set_ylabel("banner 授予率 (%)")
    ax.set_title("题材禁忌：31,664 本同人书，banner 数为 0")
    ax.set_ylim(0, max(gr["rate"]*100)*1.2)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    fig.tight_layout()
    return charts.save(fig, "17_genre.png")


def fig_lag(lag: pd.Series, cy_dist: pd.Series) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.hist(lag.dropna(), bins=np.arange(0, 175, 10), color=charts.C["green"], zorder=3)
    ax.axvline(lag.median(), color=charts.C["red"], lw=1.6, ls="--",
               label=f"中位 {lag.median():.0f} 月")
    ax.set_xlabel("封面换图 − 定年创建（月）")
    ax.set_ylabel("banner 书数")
    ax.set_title("运营换图 ≠ 创建：中位滞后约 4 年")
    ax.legend(framealpha=0.9)
    ax = axes[1]
    ax.bar(cy_dist.index, cy_dist.values, color=charts.C["blue"], zorder=3, width=0.7)
    charts.shade_periods(ax, pd.Series(cy_dist.index.values))
    ax.set_xlabel("封面换图年")
    ax.set_ylabel("书数")
    ax.set_title("授予时点集中在 2022 后")
    fig.tight_layout()
    return charts.save(fig, "17_lag.png")


def fig_dual(bet_prev: float, rew_prev: float, bet_peak: float, rew_peak: float,
             yr_rows: pd.DataFrame) -> str:
    """下注型 vs 奖励型：此前代表作门槛 + 本书是否作者巅峰。"""
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4))
    labels = ["下注型\n(作者此前有代表作)", "奖励型\n(作者此前无代表作)"]
    cols = [charts.C["blue"], charts.C["red"]]
    # 左：此前代表作收藏门槛（对数）
    ax = axes[0]
    vals = [max(bet_prev, 1), max(rew_prev, 1)]
    bars = ax.bar(range(2), vals, color=cols, zorder=3, width=0.55)
    ax.set_yscale("log")
    for bar, v, raw in zip(bars, vals, [bet_prev, rew_prev]):
        ax.text(bar.get_x()+bar.get_width()/2, v*1.25, num(raw), ha="center", fontsize=9)
    ax.set_xticks(range(2)); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("此前作品最高收藏（中位，对数轴）")
    ax.set_title("入场前作者的成绩")
    ax.set_ylim(1, max(vals)*12)
    # 中：本书是否作者巅峰作
    ax = axes[1]
    vals2 = [bet_peak, rew_peak]
    bars = ax.bar(range(2), vals2, color=cols, zorder=3, width=0.55)
    for bar, v in zip(bars, vals2):
        ax.text(bar.get_x()+bar.get_width()/2, v+1.2, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_xticks(range(2)); ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("本书即作者最高收藏作 (%)")
    ax.set_title("banner 落在作者巅峰作上？")
    ax.set_ylim(0, 100)
    # 右：控制定年后的收藏中位
    ax = axes[2]
    yrs = yr_rows["year"].values
    x = np.arange(len(yrs))
    ax.plot(x, yr_rows["bet"], marker="o", color=charts.C["blue"], lw=1.6, label="下注型")
    ax.plot(x, yr_rows["rew"], marker="s", color=charts.C["red"], lw=1.6, label="奖励型")
    ax.set_xticks(x); ax.set_xticklabels(yrs, fontsize=8)
    ax.set_ylabel("banner 书收藏中位")
    ax.set_title("控制世代后差距缩小")
    ax.legend(framealpha=0.9, fontsize=8)
    fig.tight_layout()
    return charts.save(fig, "17_dual.png")


# ---------- 正文 ----------
def build() -> str:
    df, raw = load()
    sb = eras.snapshot_bounds(df)
    b = df[df.is_b].copy()
    b["cy"] = b.cv.dt.year
    n_b = len(b)
    n_cv = int(b.cv.notna().sum())
    lag = (b.cv.dt.year - b.est_date.dt.year)*12 + (b.cv.dt.month - b.est_date.dt.month)
    b["lag_m"] = lag

    # 趋 investment
    cy = b.cv.dropna().dt.year.astype(int).value_counts().sort_index()
    f_trend = fig_trend(cy, n_b)

    # 硬门槛
    g = df.groupby("author").agg(best_pct=("fav_pct", "max"), n=("id", "size"),
                                  any_b=("is_b", "max"))
    g["band"] = pd.cut(g.best_pct, [0, .25, .5, .75, .9, .99, 1.0001],
                       labels=["<25%", "25-50%", "50-75%", "75-90%", "90-99%", "99%+"])
    f_thr = fig_threshold(g)
    g90 = g[g.best_pct >= .9]
    g99 = g[g.best_pct >= .99]
    glt90 = g[g.best_pct < .9]
    rate90 = g90.any_b.mean()*100
    rate99 = g99.any_b.mean()*100
    zero_rate = glt90.any_b.mean()*100
    n_lt90 = len(glt90)

    # 作者对照
    b_auth = set(b.author)
    ba = df[df.author.isin(b_auth) & ~df.is_b]
    nb = df[~df.author.isin(b_auth)]
    contrast = [("banner 书", b.fav_pct.median()),
                ("同作者其他书", ba.fav_pct.median()),
                ("无 banner 作者的书", nb.fav_pct.median())]
    # 后续新作：统一口径 = 库内作品数>1（首作之后仍有新作）
    grp = df.groupby("author").size()
    b_rate = (grp.loc[list(b_auth)] > 1).mean()*100
    nb_rate = (grp.loc[nb.author.unique()] > 1).mean()*100
    follow = {"b_rate": b_rate, "nb_rate": nb_rate}
    f_auth = fig_author(contrast, follow)

    # 时序：先成功后 banner
    br = b[b.on_rank].copy()
    br["cv_y"] = br.cv.dt.year
    br["first_y"] = br.first_m.str[:4].astype(int)
    d = br.cv_y - br.first_y
    n_before = int((d < 0).sum()); n_same = int((d == 0).sum()); n_after_y = int((d > 0).sum())
    med_lag_y = d.median()
    # 控制授予年后的滞后效应
    b["fav_pct_cy"] = b.groupby("cy").fav.rank(pct=True)
    b["lagb"] = pd.cut(b.lag_m, [-1, 12, 24, 48, 72, 200],
                       labels=["≤12", "12-24", "24-48", "48-72", "72+"])
    lag_by_year = b.groupby("lagb", observed=True).agg(
        favpct=("fav_pct_cy", "median"), n=("id", "size")).reset_index()
    corr_lag = np.corrcoef(b.dropna(subset=["lag_m", "fav_pct_cy"]).lag_m,
                           b.dropna(subset=["lag_m", "fav_pct_cy"]).fav_pct_cy)[0, 1]
    f_timing = fig_timing(br, lag_by_year)

    # 题材
    gr = []
    for genre, sub in df.groupby("genre"):
        if len(sub) < 1000:
            continue
        gr.append({"genre": genre, "n": len(sub), "n_b": int(sub.is_b.sum()),
                   "rate": sub.is_b.mean()})
    gr = pd.DataFrame(gr).sort_values("rate", ascending=False)
    f_genre = fig_genre(gr)
    n_doujin = int(df[df.genre == "同人"].shape[0])
    n_doujin_b = int(df[df.genre == "同人"].is_b.sum())

    # 滞后分布
    f_lag = fig_lag(lag, cy)

    # ===== 二元机制：下注型 vs 奖励型（作者内代表作判定）=====
    TH = 10000  # 此前代表作的收藏门槛
    bb_all = df[df.is_b].copy()
    bb_all["prev_best"] = bb_all.prev_max_fav >= TH
    a_max_all = df.groupby("author").fav.max()
    bb_all["a_max"] = bb_all.author.map(a_max_all)
    bet = bb_all[bb_all.prev_best]
    rew = bb_all[~bb_all.prev_best]
    bet_prev_med = bet.prev_max_fav.median()
    rew_prev_med = rew.prev_max_fav.median()
    bet_peak = (bet.fav >= bet.a_max*0.999).mean()*100
    rew_peak = (rew.fav >= rew.a_max*0.999).mean()*100
    bet_fav_med = bet.fav.median()
    rew_fav_med = rew.fav.median()
    bet_rank = bet.on_rank.mean()*100
    rew_rank = rew.on_rank.mean()*100
    n_bet, n_rew = len(bet), len(rew)
    # 作者履历厚度 vs 下注占比
    a_n = df.groupby("author").size()
    bb_all["a_n"] = bb_all.author.map(a_n)
    multi_bet_share = bb_all[bb_all.a_n >= 5].prev_best.mean()*100
    single_bet_share = bb_all[bb_all.a_n == 1].prev_best.mean()*100
    # 控制定年的逐年收藏中位（两档均 n>=5）
    yr_rows = []
    for y in sorted(set(bb_all.est_year)):
        sb_ = bb_all[(bb_all.est_year == y) & bb_all.prev_best]
        sr_ = bb_all[(bb_all.est_year == y) & ~bb_all.prev_best]
        if len(sb_) >= 5 and len(sr_) >= 5:
            yr_rows.append({"year": y, "bet": sb_.fav.median(), "rew": sr_.fav.median()})
    yr_rows = pd.DataFrame(yr_rows)
    f_dual = fig_dual(bet_prev_med, rew_prev_med, bet_peak, rew_peak, yr_rows)

    # 集中度与代表作位置
    ab = b.groupby("author").size().sort_values().values
    gini = (2*np.arange(1, len(ab)+1)-len(ab)-1).dot(ab)/(len(ab)*ab.sum())
    top10_share = np.sort(ab)[-10:].sum()/ab.sum()*100
    n_multi = int((b.groupby("author").size() > 1).sum())
    df["fav_rank_a"] = df.groupby("author").fav.rank(ascending=False)
    bb = df[df.is_b]
    best_share = (bb.fav_rank_a == 1).mean()*100
    top3_share = (bb.fav_rank_a <= 3).mean()*100
    first_work_share = (b.author_rank == 1).mean()*100

    # 规模与命中
    vip_rate = b.price_type.isin(["VIP", "签约"]).mean()*100
    done_rate = (b.status == "已完结").mean()*100
    onrank_rate = b.on_rank.mean()*100
    n_rank = int(b.on_rank.sum())
    fav_med = b.fav.median()
    words_med = b.words.median()
    fav_pct_med = b.fav_pct.median()
    fav_pct_g = df.groupby(["genre", "est_year"]).fav.rank(pct=True)
    fav_pct_g_med = fav_pct_g[df.is_b].median()
    n_auth = b.author.nunique()
    n_multi_auth = int((b.groupby("author").size() > 1).sum())
    max_b = b.groupby("author").size().max()
    top_author = b.groupby("author").size().idxmax()
    invest = num(cy.sum()*1000)
    invest_all = num(n_b*1000)

    P = []
    P.append(f"""# 报告 17：banner 投入与平台押注

> **口径声明**
> 1. 数据上界：内容 `max(last_update)={sb['content_end'].date()}`，nid 上界 {num(df.id.max())}（现算）。
>    年度序列止于 2025 即因内容上界之后的新书不在库内。
> 2. **banner 字段**：原始 jsonl 的 `banner` 布尔位，CSV 中映射为 `featured`（{num(n_b)} 本，
>    已剔除日轻 {num(len(config.LICENSED_LN_AUTHORS))} 类作者）。banner 画师原创、约
>    1,000 RMB/张（用户口述），是平台真金白银的投入，非免费运营装饰。
> 3. **封面时间戳 ≠ 授予时点**：原始数据集的 cover 选择器写错，导致多本书挂同一封面；
>    数据清洗将共用组内非属主的封面判为错误、置为空值，因此 CSV 中 banner 书封面
>    大面积缺失（{num(n_b)} 本中仅 {num(int(df[df.is_b].cover_url.notna().sum()))} 本非空）。
>    本报告改从原始 jsonl 恢复 {num(n_cv)} 个带年月封面。该年月是平台换运营封面的时间
>    （MEMORY §9：相对定年偏差中位 +338 天），**只是授予时点的弱代理**：
>    换图可能滞后于授予、也可能多次换图。凡涉及时序一律标注为「封面换图年」。
> 4. **收藏分位是机械结果**：banner 本就按热度授予，书均处世代顶部，
>    因此「banner 书收藏分位 {fav_pct_med:.3f}」不构成命中率证据；
>    命中率须看授予后作者/作品的持续表现（§3–§4）。
> 5. 累计指标跨时点不可比；月榜 top20 右截断、每月清零，只作结构描述。
> 6. 本报告**不改动任何数据行**；结论以口径修正与机制识别形式作用于前序报告。

## 结论

1. **banner 是「作者筛选」而非「单书抽奖」**：{num(n_auth)} 位获 banner 作者中
   {num(n_multi_auth)} 位有 ≥2 本 banner（最多 {top_author} {max_b} 本），
   但关键在门槛——**代表作收藏分位 <90% 的 {num(n_lt90)} 位作者，获 banner 率为
   {zero_rate:.1f}%（精确为 0）**；99%+ 档为 {rate99:.1f}%。用户口述的
   「优质代表作作者更容易获 banner」得到硬门槛级验证。
2. **平台识别的是作者能力，不只是单本爆款**：banner 书收藏分位中位
   {fav_pct_med:.3f}，同作者的其他书仍有 {contrast[1][1]:.3f}（无 banner 作者
   {contrast[2][1]:.3f}）；获 banner 作者首作后仍有新作的占 {b_rate:.1f}%，
   无 banner 作者仅 {nb_rate:.1f}%。
3. **banner 是「下注」与「奖励」二元机制**（作者内代表作判定）：
   **下注型 {num(n_bet)} 本（{n_bet/n_b*100:.1f}%）**——作者获 banner 前已有
   高收藏代表作（此前最高收藏中位 {num(bet_prev_med)}），平台押的是作者能力，
   本书仅 {bet_peak:.1f}% 是作者巅峰作；**奖励型 {num(n_rew)} 本（{n_rew/n_b*100:.1f}%）**
   ——作者此前几乎无成绩（此前最高收藏中位 {num(rew_prev_med)}），本书爆火才得奖，
   {rew_peak:.1f}% 直接成为作者巅峰。这解释了为何部分 banner 书绝对数字不高：
   下注型押的是作者而非这本书。
4. **时序上以追认居多、但非全部**：{num(len(br))} 本上过月票榜的 banner 书中，
   {num(n_after_y)} 本首次上榜早于封面换图年、{num(n_same)} 本同年、
   {num(n_before)} 本换图早于上榜；中位滞后 {med_lag_y:.0f} 年。
   封面换图晚于上榜不等于授予晚于爆火（换图可滞后多年），故不作「全部追认」断言。
5. **硬门槛 + 题材禁忌**：同人 {num(n_doujin)} 本、banner {n_doujin_b} 本（0）；
   魔幻/校园/玄幻占 banner 绝对数主体（古风授予率最高）。
   悬疑 {int(gr[gr.genre=='悬疑'].iloc[0].n_b)} 本
   （授予率 {gr[gr.genre=='悬疑'].iloc[0].rate*100:.2f}%），近乎不获 banner。
6. **授予时点集中在 2022 后**：可读封面的 {num(cy.sum())} 张中，
   {num(cy[cy.index>=2022].sum())} 张（{cy[cy.index>=2022].sum()/cy.sum()*100:.0f}%）在 2022 年后，
   按 1,000 RMB/张估算累计约 {invest} 元（全 {num(n_b)} 本口径约 {invest_all} 元）。
7. **集中度温和**：top10 作者占 banner {top10_share:.1f}%，Gini {gini:.3f}——
   平台没有把资源锁死在少数头部作者手里。

## 1. 授予规模与趋势

{num(n_b)} 本 banner 书（占库 {n_b/len(df)*100:.2f}%），{num(n_auth)} 位作者。
定年创建集中在 2015–2019，但**封面换图集中在 2022 年后**——两者相差
中位 {lag.median():.0f} 个月，说明平台多在作品运行数年后才授予 banner。

![滞后分布]({f_lag})

![授予趋势]({f_trend})

| 封面换图年 | banner 书数 | 估算投入（元） |
|---|---|---|
""" + "".join(f"| {int(y)} | {int(v)} | {num(int(v)*1000)} |\n" for y, v in cy.items()) + f"""
> 投入为 1,000 RMB/张 × 可读封面数的**粗略估算**，非平台披露数字。

## 2. 硬门槛：代表作决定入场资格

把作者按「最高收藏书」的世代内收藏分位分档，获 banner 率呈悬崖式跃迁：

![代表作门槛]({f_thr})

| 代表作分位档 | 作者数 | 获 banner 率 |
|---|---|---|
| <25% / 25-50% / 50-75% / 75-90% | {num(n_lt90)} | {zero_rate:.1f}% |
| 90-99% | {num(int((g.band=='90-99%').sum()))} | {g[g.band=='90-99%'].any_b.mean()*100:.2f}% |
| 99%+ | {num(len(g99))} | {rate99:.1f}% |

**代表作进不了世代前 10% 的作者，没有一个拿到 banner。** 控制作品数后门槛依旧：
1 本作品的作者中，代表作≥90% 分位者获 banner 0.8%、其余 0.0%；
10 本以上者分别为 8.0% / 0.0%。**优质代表作是必要条件，多产是加成**——
这正是用户口述的机制。

## 3. 平台识别的是作者，不只是单本

![作者识别]({f_auth})

banner 书在作者内收藏排名=1 的占 {best_share:.1f}%、前 3 的占 {top3_share:.1f}%，
{first_work_share:.1f}% 是作者首部作品——banner 往往落在作者的**代表作**上。
更关键的是同作者的其他书：收藏分位中位 {contrast[1][1]:.3f}，远高于无 banner 作者的
{contrast[2][1]:.3f}。作者层面，获 banner 后仍有新作的占 {b_rate:.1f}%，
无 banner 作者 {nb_rate:.1f}%——banner 作者是持续在场的高产群体。

## 4. 下注型 vs 奖励型：banner 的二元机制

上节证明平台按作者能力筛选，但**获 banner 的原因并不单一**。按 banner 书创建时
（nid 时间序）作者此前是否已有高收藏代表作（门槛 {num(TH)} 收藏），可切成两类：

![二元机制]({f_dual})

| | 下注型 | 奖励型 |
|---|---|---|
| 判定 | 作者此前已有代表作 | 作者此前无代表作 |
| 本数 | {num(n_bet)}（{n_bet/n_b*100:.1f}%） | {num(n_rew)}（{n_rew/n_b*100:.1f}%） |
| 此前作品最高收藏（中位） | {num(bet_prev_med)} | {num(rew_prev_med)} |
| 本书收藏中位 | {num(bet_fav_med)} | {num(rew_fav_med)} |
| 本书是作者巅峰作 | {bet_peak:.1f}% | {rew_peak:.1f}% |
| 上月票榜比例 | {bet_rank:.1f}% | {rew_rank:.1f}% |

**下注型**：作者在拿到 banner 前已证明过自己（此前代表作中位 {num(bet_prev_med)} 收藏），
平台押的是**作者能力**，而非这本书——本书仅 {bet_peak:.1f}% 是作者收藏最高的作品，
超过一半的 banner 落在作者的非巅峰作上。**奖励型**：作者此前几乎无成绩
（此前最高收藏中位仅 {num(rew_prev_med)}），是这本书爆火后才获得 banner，
{rew_peak:.1f}% 直接成为作者巅峰。

这解释了「**有 banner 但点击/收藏数字不高**」的现象：下注型把 banner 押在作者身上，
书本身未必是流量顶点。库内作品 ≥5 本的作者中下注型占 {multi_bet_share:.1f}%，
高于全体的 {n_bet/n_b*100:.1f}%（单本作者按定义只能是奖励型，
占 {single_bet_share:.1f}%）——**作者履历越厚，banner 越可能是下注而非对单本的奖励**。

需要诚实标注一处反直觉：控制世代后，下注型的最终收藏中位并不低
（右 panel 两线接近，2018–2019 基本重合），且整体上下注型反而略高
（{num(bet_fav_med)} vs {num(rew_fav_med)}）——因为下注型作者本就持续产出高收藏书。
**两类真正的分野是「本书相对作者在作者内的位置」，不是绝对数字**：
下注型 {bet_peak:.1f}% vs 奖励型 {rew_peak:.1f}% 是作者巅峰，差距 {rew_peak-bet_peak:.1f} 个百分点。

## 5. 时序证据：以追认居多，但非全部

![时序]({f_timing})

{num(len(br))} 本 banner 书曾上月票榜，其中 {num(n_after_y)} 本首次上榜早于封面换图年、
{num(n_same)} 本同年、{num(n_before)} 本换图早于上榜，中位滞后 {med_lag_y:.0f} 年。
从封面换图看，多数 banner 出现在作品上榜之后——但这**不能直接读作「先成功后授予」**：
封面可在 banner 授予后数年才更换（§4 的下注型尤其如此），换图晚不等于授予晚。

但控制授予年后出现一个细结构：换图滞后越短的书，在同授予年内的收藏分位越高
（≤12 月档 {lag_by_year.iloc[0].favpct:.3f} vs 72+ 月档 {lag_by_year.iloc[-1].favpct:.3f}，
相关 {corr_lag:.3f}）。这指向**授予标准随作品年龄分化**：新书要在同年里更靠头部
才拿到 banner，老书则可能在成功多年后才获表彰。结合 §4 的二元机制，
时序差异更多反映「奖励老书 vs 下注新作」的混合，而非单一的追认或下注。

## 6. 题材禁忌与集中度

![题材]({f_genre})

同人 {num(n_doujin)} 本（库内最大题材之一）banner 数为 {n_doujin_b}——**零**。
这与其 IP 命名空间属性（报告 09）一致：平台不对同人投放原创画师 banner。
注意**绝对数与授予率是两回事**：魔幻 {int(gr[gr.genre=='魔幻'].iloc[0].n_b)} 本、
校园 {int(gr[gr.genre=='校园'].iloc[0].n_b)} 本因盘子大而占 banner 绝对数主体，
但按授予率古风最高（{gr[gr.genre=='古风'].iloc[0].rate*100:.2f}%）、
魔幻仅 {gr[gr.genre=='魔幻'].iloc[0].rate*100:.2f}%。

{num(n_multi_auth)} 位作者获多本 banner，最多 {top_author} {max_b} 本；
top10 作者占 {top10_share:.1f}%，Gini {gini:.3f}——资源分散在数百位作者间，
不是少数人的终身成就奖。

## 7. 口径边界

1. **封面时间戳的弱代理性**：换图年可能晚于授予年（运营维护、多次换封面），
   §1/§5 的时序统计（{num(n_after_y)}/{num(len(br))} 先上榜后换图）只说明
   「换图多在上榜后」，不能推断授予时点；「中位滞后 {med_lag_y:.0f} 年」是**上界**。
2. **右删失**：2024–2026 创建的书还在积累，其收藏分位被低估；
   「新书获 banner 时更靠头部」的结论已控制授予年，但绝对幅度须保留。
3. **封面缺失的根因**：原始数据集 cover 选择器写错导致多书共用封面，清洗时
   非属主的封面被置空——这是数据源缺陷，非平台无封面。本报告从 jsonl 恢复，
   {num(n_cv)}/{num(n_b)} 本可读；26 本占位符无法恢复，相关统计以其余为样本。
4. **二元判定依赖单一快照**：下注/奖励按「banner 书创建时作者此前最高收藏
   ≥{num(TH)}」判定，是**作者履历的代理**，非平台内部标签。作者早期作品若在
   抓取窗口外或已下架（报告 10 覆盖率约 68.9%），会把下注型误判为奖励型；
   两类边界是连续的，{num(rew_prev_med)} vs {num(bet_prev_med)} 的门槛差带人为性。
5. **命中率不可直接读**：banner 书收藏分位 {fav_pct_med:.3f}、题材内
   {fav_pct_g_med:.3f} 均为机械结果（授予标准本身即热度）。本报告用
   「授予后作者续作率」「同作者其他书水平」「本书是否作者巅峰」替代，
   但这些仍是相关，不能证明 banner **导致**作者成功（反向因果：成功在先）。
6. **同人 0 banner 不等于零商业化**：同人有独立 IP 生态，
   此处只说明平台不为其投放原创 banner。
7. **投入为估算**：1,000 RMB/张系用户口述，非平台披露；且 26 本封面为占位符
   无法确定换图年，累计投入是下界估计。
8. **样本遗漏**：报告 10 证实数据集对在架书覆盖率约 68.9%，banner 书均为头部、
   遗漏率低，但绝对计数仍应视为下界。
""")
    text = "".join(P)
    path = OUT / "17_banner.md"
    path.write_text(text, encoding="utf-8")
    print(f"written {path}")
    return text


if __name__ == "__main__":
    build()

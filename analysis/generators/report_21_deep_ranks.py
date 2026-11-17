"""生成 analysis/reports/21_deep_ranks.md：D2「全库世代内 Top200 深榜」。

定位
----
本报告落实 `app/docs/09-seed-refresh-proposal.md` 附录 A 的 D2 决策：官方榜
（web top20、App 无全局日/周/月榜端点）深度不足，我们用本地全库宽表重排出
官方给不出的深榜。它是**新增分析**，不是对报告 10 的修订：

  * 不改报告 10、`lib/eras.py` 的 log(nid) 定年体系与 104 锚点；
  * 不改 App 01–08 设计文档、不改 30,878 本种子书单与 24 列结构；
  * 榜单结果以**追加表**形式进入 seed.db（见 app/docs/10-deep-ranks.md），
    既有分位分母与 /rankings/favs 语义不变。

数据来源只有本地产物：`out/novels.csv` + `anchors/` 定年 + `app/assets/seed.db.gz`。
**零网络请求**；缺文件直接报错，不会自动补采。所有数字现算。

用法：uv run python analysis/generators/report_21_deep_ranks.py
"""

from __future__ import annotations

import gzip
import sqlite3
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ANALYSIS = REPO / "analysis"
sys.path.insert(0, str(ANALYSIS))
sys.path.insert(0, str(REPO / "app" / "tools" / "seedbuild"))

from lib import charts, eras  # noqa: E402
from lib import paths  # noqa: E402
from deep_ranks import GEN_MAX, GEN_MIN, METRICS, PR_MIN_FAVS, build_deep_ranks, seed_coverage  # noqa: E402

OUT = paths.REPORTS_DIR / "21_deep_ranks.md"
SEED_GZ = REPO / "app" / "assets" / "seed.db.gz"
EXPECT_UNIVERSE = 241_758
TOP_N = 200

METRIC_LABEL = {
    "favs": "收藏",
    "clicks": "点击",
    "praises": "点赞",
    "pr": "赞藏比",
}


def num(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float, nd: int = 1) -> str:
    return f"{x * 100:.{nd}f}%"


def load_universe() -> pd.DataFrame:
    """Replicate build_seed.py's statistical universe and its five percentiles."""
    raw = pd.read_csv(paths.CSV_FILE, dtype={"id": int})
    est = eras.estimate(raw["id"]).rename(columns={"confidence": "est_conf"})
    df = raw.merge(est[["id", "est_date", "est_year", "est_conf"]],
                   on="id", how="left")
    uni = df[df["est_year"].between(GEN_MIN, GEN_MAX)].copy()
    if len(uni) != EXPECT_UNIVERSE:
        raise SystemExit(f"universe {len(uni)} != {EXPECT_UNIVERSE}")

    for col, dst in (("favs", "fav_pctl"), ("clicks", "click_pctl"),
                     ("praises", "praise_pctl")):
        uni[col] = pd.to_numeric(uni[col], errors="coerce")
        g = uni.groupby("est_year", observed=True)[col]
        uni[dst] = g.rank(ascending=True, method="average") / g.transform("size")
    uni["pr"] = np.where(
        uni["favs"] >= PR_MIN_FAVS,
        uni["praises"] / uni["favs"].replace(0, np.nan),
        np.nan,
    )
    denom = uni.groupby("est_year", observed=True)["pr"].transform("count")
    uni["pctl_pr"] = (
        uni.groupby("est_year", observed=True)["pr"]
        .rank(ascending=True, method="average") / denom
    )
    return uni


def load_seed_nids() -> set[int]:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "seed.db"
        with gzip.open(SEED_GZ, "rb") as src, db.open("wb") as dst:
            dst.write(src.read())
        conn = sqlite3.connect(db)
        nids = {int(r[0]) for r in conn.execute("SELECT nid FROM books WHERE is_licensed=0")}
        conn.close()
    if len(nids) == 0:
        raise SystemExit("seed.db.gz has no non-licensed books")
    return nids


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def fig_coverage(cov: pd.DataFrame) -> str:
    pivot = cov.pivot(index="est_year", columns="metric", values="coverage")
    pivot = pivot[[m for m in METRICS if m in pivot.columns]]
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    im = ax.imshow(pivot.to_numpy() * 100, cmap="RdYlGn", vmin=0, vmax=100,
                   aspect="auto")
    ax.set_xticks(range(len(pivot.columns)), [METRIC_LABEL[m] for m in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), [str(y) for y in pivot.index])
    ax.set_xlabel("指标")
    ax.set_ylabel("世代（est_year）")
    ax.set_title("现行种子池对全库世代 Top200 的覆盖率")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.iloc[i, j] * 100
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7,
                    color="black" if v > 45 else "white")
    fig.colorbar(im, ax=ax, label="覆盖率 %", shrink=0.85)
    return charts.save(fig, "21_seed_coverage.png")


def fig_thresholds(deep: pd.DataFrame) -> str:
    favs = deep[deep["metric"] == "favs"]
    years = np.arange(GEN_MIN, GEN_MAX + 1)
    lines = {}
    for pos in (1, 50, TOP_N):
        vals = []
        for y in years:
            hit = favs.loc[(favs.est_year == y) & (favs.rank_no == pos), "value"]
            vals.append(float(hit.iloc[0]) if len(hit) else np.nan)
        lines[pos] = vals
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    colors = {1: "#B22222", 50: "#E08A1E", TOP_N: "#2E6DA4"}
    for pos, vals in lines.items():
        ax.plot(years, vals, marker="o", ms=3, lw=1.6, color=colors[pos],
                label=f"Top{pos} 门槛")
    ax.set_yscale("log")
    ax.set_xlabel("世代（est_year）")
    ax.set_ylabel("收藏数（对数轴）")
    ax.set_title("全库世代收藏深榜：入榜门槛随世代变化")
    ax.legend(frameon=False, loc="upper left")
    return charts.save(fig, "21_rank_thresholds.png")


def main() -> None:
    charts.setup_style()
    uni = load_universe()
    deep = build_deep_ranks(uni, TOP_N)
    seed_nids = load_seed_nids()
    cov = seed_coverage(deep, seed_nids)

    fig1 = fig_coverage(cov)
    fig2 = fig_thresholds(deep)

    md: list[str] = []
    md.append("# 报告 21：全库世代内 Top200 深榜（D2）\n")
    md.append("> **定位**：新增分析，不是修订。报告 10、`lib/eras.py` 定年体系、"
              "30,878 本种子书单与 24 列结构、App 01–08 设计文档均未改动。"
              "实现决定见 `app/docs/09-seed-refresh-proposal.md` 附录 A（D2），"
              "落地契约见 `app/docs/10-deep-ranks.md`。\n")
    md.append("> **口径**：统计宇宙 = `out/novels.csv` 剔除正版日轻且 `est_year∈2007–2025` "
              f"共 {num(EXPECT_UNIVERSE)} 行；世代 = `est_year`，逐年独立成榜；"
              "四指标（收藏/点击/点赞/赞藏比）各取 Top200；赞藏比沿用 `favs ≥ 10` 门槛。"
              "**榜单参照系是全库，不是种子池**。全程零网络请求。\n")

    md.append("## 1. 为什么现有 limit=200 端点不等于深榜\n")
    md.append("引擎 `/rankings/favs` 的 `parseLimit` 已允许 `limit=200`，但该端点只查"
              "种子池 `seed.books`。早期世代在种子里只有个位数到几十本，"
              "把 limit 调到 200 并不会凭空补出书。下表是现算覆盖率：\n")
    rows = []
    for y in range(GEN_MIN, GEN_MAX + 1):
        g = cov[cov.est_year == y]
        if g.empty:
            continue
        fav = g[g.metric == "favs"].iloc[0]
        mean = g["coverage"].mean()
        rows.append([str(y), num(int(fav["in_seed"])),
                     f"{int(fav['in_seed']):.0f}/{int(fav['depth'])}",
                     pct(mean, 1)])
    md.append(md_table(["世代", "种子内本数", "深榜命中/深度", "四指标平均覆盖"], rows))
    md.append("")
    md.append(f"![种子覆盖]({fig1})\n")
    total_hit = int(cov["in_seed"].sum())
    total_slots = int(cov["depth"].sum())
    md.append(f"四指标合计 {num(total_slots)} 个榜位，种子池只覆盖 {num(total_hit)} 个"
              f"（{pct(total_hit / total_slots, 1)}）；2007–2014 八个世代合计命中 "
              f"{int(cov[cov.est_year <= 2014]['in_seed'].sum())} / "
              f"{num(int(cov[cov.est_year <= 2014]['depth'].sum()))}。"
              "因此深榜必须建立在全库上，不能靠放宽端点 limit 实现。\n")

    md.append("## 2. 深榜的形状\n")
    md.append("每个世代 × 每个指标 = 一张独立榜，实际深度 = `min(200, 合格书目数)`："
              "2015 以后各世代凑满 200 名，2007 世代全库只有 76 本，"
              "赞藏比榜还受 `favs ≥ 10` 门槛进一步收窄。"
              f"本次共落库 {num(len(deep))} 行、"
              f"{len(range(GEN_MIN, GEN_MAX + 1)) * len(METRICS)} 张榜。"
              "入榜门槛随世代显著变化，说明跨世代比绝对值没有意义：\n")
    thr_rows = []
    for y in (2007, 2010, 2013, 2016, 2019, 2022, 2025):
        g = deep[(deep.metric == "favs") & (deep.est_year == y)]
        if g.empty:
            continue
        vals = {}
        for p in (1, 50, TOP_N):
            hit = g.loc[g.rank_no == p, "value"]
            vals[p] = float(hit.iloc[0]) if len(hit) else None
        fmt = lambda v: "—" if v is None else num(v)
        thr_rows.append([str(y), fmt(vals[1]), fmt(vals[50]), fmt(vals[TOP_N])])
    md.append(md_table(["世代", "第 1 名收藏", "第 50 名收藏", "第 200 名收藏"], thr_rows))
    md.append("")
    md.append(f"![入榜门槛]({fig2})\n")
    md.append("点击与点赞的门槛跨度更大（累计量口径），赞藏比则受 `favs ≥ 10` 限制："
              "早期世代合格样本少，榜单实际深度可能不足 200。生成时对不足 200 的世代"
              "按实际合格数落库，**不补凑数条目**。\n")

    md.append("## 3. 与官方榜的差异\n")
    md.append(md_table(
        ["维度", "官方", "D2 深榜"],
        [
            ["深度", "web 榜 top20；App 无全局日/周/月榜端点", "每世代每指标最多 top200（受合格书目数限制）"],
            ["时间基准", "当期 / 每月清零", f"内容上界快照（2026-05-03，定年不外推）"],
            ["参照系", "全站当期", "全库历史快照，按世代分层"],
            ["数值", "多数榜只给名次或量化值", "给原值 + 全库世代内分位"],
            ["可切分", "固定榜位", "世代 × 指标 × 题材（题材由端上按 genre 过滤）"],
        ]))
    md.append("")
    md.append("官方没有「按世代回看」的榜——这是报告 02/03 的分位论证在产品上的直接延伸。"
              "D2 解决的不是「谁最新」，而是「每个年代的代表作是谁」，"
              "这正是绝对榜会系统性屏蔽的部分。\n")

    md.append("## 4. 边界与红线\n")
    md.append("- **分位不是排名**：每世代冠军的分位都是 1.0，但绝对收藏可能差一个量级；"
              "UI 必须同时给原值与分位，且不提供跨世代加总。\n")
    md.append("- **点击榜须分曝光档**：累计点击受书龄与曝光分母混杂（报告 08），"
              "D2 的点击榜按世代给出，仍不等于曝光分档后的转化率；不做跨书点击涨幅。\n")
    md.append("- **赞藏比门槛**：`favs < 10` 不入 `pr` 榜；短篇禁用比率类指标（报告 19），"
              "本榜不替代短篇榜。\n")
    md.append("- **快照态**：`status` 是 2026-05-03 的快照，不是当期状态；"
              "`updated_at` 只作时长，不作时间轴。\n")
    md.append("- **定年不动**：世代仍由 `log(nid)` 分段线性定年给出，"
              "App API 的 `addTime` 不进定年；报告 10 的覆盖与 U 型结论不受影响。\n")
    md.append("- **数据新鲜度**：D2 依赖内容上界快照，2026-05-03 后新书不在榜内；"
              "维持新鲜需后续按既定增强通路重采，本报告不发起请求。\n")

    md.append("## 5. 复现\n")
    md.append("```bash\n"
              "cd analysis\n"
              "uv run python generators/report_21_deep_ranks.py\n"
              "```\n")
    md.append(f"- 依赖 `out/novels.csv`、`anchors/`、`app/assets/seed.db.gz`；"
              "均为本地产物，缺失即报错。\n"
              "- 榜单落库由 `app/tools/seedbuild/build_seed.py` 完成，"
              "本报告的深榜计算与构建器共用 `app/tools/seedbuild/deep_ranks.py`，"
              "避免口径漂移。\n"
              "- 所有发现为结构描述；相关不等于因果。\n")

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"written {OUT}")
    print(f"deep rows={len(deep)} seed coverage={total_hit}/{total_slots} "
          f"({total_hit / total_slots:.1%})")


if __name__ == "__main__":
    main()

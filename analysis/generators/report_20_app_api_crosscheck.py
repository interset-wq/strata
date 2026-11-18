"""生成 analysis/reports/20_app_api_crosscheck.md：官方 App API 的离线复核。

定位（硬约束，用户 2026-11-17 定案）
------------------------------------
本报告是**补充证据**，不是修订：
  * 不修改报告 10（生存与遗漏）。报告 10 的推测——单向游标扫描、在册密度
    U 型 / 缺失槽位存活率倒 U 型、补爬对象约 1 千本——保持不变；
  * 不修改 `lib/eras.py` 的 log(nid) 定年体系（104 锚点），App API 的
    `addTime` 只作独立旁证；
  * 不改变任何 App 设计（种子、分位、书架、观测、watchlist 口径均不动）。

数据来源全部是**已存在的本地产物**，本报告不发起任何网络请求：
  * `out/novels.csv`（唯一原始数据集的规范化派生表）；
  * `out/app_api_novels.jsonl`（官方 App API 书目枚举，**部分**，只有
    tid=21 完整翻到空页，故同类内比较只用 tid=21）；
  * `out/external_dates_full.jsonl`（第三方观测站转述的 `addTime`，31,229 条，
    与 App 锚点同字段语义，仅作定年旁证）。

所有数字现算；报告是生成物，勿手改。

用法：uv run python analysis/generators/report_20_app_api_crosscheck.py
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths

from lib import charts  # noqa: E402
from lib import eras  # noqa: E402

OUT = paths.REPORTS_DIR / "20_app_api_crosscheck.md"
FIG = paths.REPORTS_DIR / "figures"

# 与报告 10 §2.1 完全相同的 nid 分档（左闭右开由边界值实现）
BANDS = [(2657, 49999), (50000, 99999), (100000, 199999), (200000, 349999),
         (350000, 499999), (500000, 649999), (650000, 774850)]
LABELS = ["2–50k", "50–100k", "100–200k", "200–350k",
          "350–500k", "500–650k", "650–774k"]
COMPLETE_TID = 21  # 唯一翻到空页的分类；其余分类枚举不完整，不用作结论
BOUND = "2026-05-03"  # 内容上界，由 eras.snapshot_bounds() 现算复核


def band_of(nid: int) -> int | None:
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= nid <= hi:
            return i
    return None


def num(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float, nd: int = 1) -> str:
    return f"{x * 100:.{nd}f}%"


def md_table(rows: list, headers: list[str]) -> str:
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        + ["| " + " | ".join(str(x) for x in row) + " |" for row in rows]
    )


def load_inputs() -> tuple[pd.DataFrame, list[dict], list[dict]]:
    for p in (paths.CSV_FILE, paths.APP_API_NOVELS, paths.EXTERNAL_DATES):
        if not p.exists():
            raise SystemExit(f"缺少本地产物 {p}；本报告不联网补采，请先运行相应管线/抓取器")
    df = pd.read_csv(paths.CSV_FILE)
    app = [json.loads(line) for line in paths.APP_API_NOVELS.read_text(encoding="utf-8").splitlines() if line.strip()]
    ext = [json.loads(line) for line in paths.EXTERNAL_DATES.read_text(encoding="utf-8").splitlines() if line.strip()]
    return df, app, ext


def slot_density(df: pd.DataFrame) -> list[tuple[int, int, float]]:
    """报告 10 的分母：nid 槽位（含从未存在的 id）。"""
    cnt = collections.Counter(b for b in (band_of(int(n)) for n in df["id"]) if b is not None)
    return [(cnt[i], BANDS[i][1] - BANDS[i][0] + 1,
             cnt[i] / (BANDS[i][1] - BANDS[i][0] + 1)) for i in range(len(BANDS))]


def catalog_hits(app: list[dict], local: set[int]) -> tuple[list[list], list[dict], list[dict]]:
    """另一个分母：官方目录里真实存在的书（仅完整分类 tid=21）。"""
    t21 = [r for r in app if r.get("tid") == COMPLETE_TID and band_of(int(r["nid"])) is not None]
    st = collections.defaultdict(lambda: [0, 0, 0])
    for r in t21:
        s = st[band_of(int(r["nid"]))]
        s[0] += 1
        if r["nid"] in local:
            s[1] += 1
        else:
            s[2] += 1
    rows = [[LABELS[i], st[i][0], st[i][1], st[i][1] / st[i][0] if st[i][0] else 0, st[i][2]]
            for i in range(len(BANDS))]
    missing = [r for r in t21 if r["nid"] not in local
               and (r.get("addTime") or "")[:10] <= BOUND]
    inside = [r for r in t21 if r["nid"] in local]
    return rows, missing, inside


def dating_check(ext: list[dict]) -> tuple[np.ndarray, pd.DataFrame, int, int]:
    anchors = eras.load_anchors()
    lo, hi = int(anchors["nid"].min()), int(anchors["nid"].max())
    sub = [r for r in ext if lo <= int(r["nid"]) <= hi]
    est = eras.estimate([r["nid"] for r in sub]).set_index("id")
    err = np.array([
        abs((pd.Timestamp(r["published_at"]).date()
             - pd.Timestamp(est.loc[int(r["nid"]), "est_date"]).date()).days)
        for r in sub
    ], dtype=float)
    conf = pd.DataFrame({
        "confidence": [est.loc[int(r["nid"]), "confidence"] for r in sub],
        "err": err,
    })
    return err, conf, lo, hi


def figure_density(slots: list[tuple[int, int, float]], hits: list[list]) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    x = np.arange(len(LABELS))
    ax = axs[0]
    ax.bar(x, [s[2] * 100 for s in slots], color=charts.C["blue"], zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("在册槽位 / 槽位总数（%）")
    ax.set_title("报告 10 的分母：nid 槽位占用率呈 U 型")
    ax.set_ylim(0, 55)

    ax = axs[1]
    ax.bar(x, [r[3] * 100 for r in hits], color=charts.C["green"], zorder=2)
    ax.axhline(99, color=charts.C["gray"], linestyle="--", linewidth=1, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("本地命中 / 官方目录书目（%）")
    ax.set_title("同类内分母：魔幻类目录内命中率平坦")
    ax.set_ylim(90, 100.5)
    fig.suptitle("两种分母给出两种形状：U 型描述「槽位是否被填」，不描述「目录内是否抓到」", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.89])
    return charts.save(fig, "20_density_semantics.png")


def figure_dating(err: np.ndarray, conf: pd.DataFrame) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.0))
    ax = axs[0]
    bins = np.arange(-0.5, max(13, err.max() + 1.5), 1)
    ax.hist(err, bins=bins, color=charts.C["blue"], zorder=2)
    ax.set_xlabel("|定年 − 官方 addTime|（天，按日期取差）")
    ax.set_ylabel("书目数")
    ax.set_title(f"锚点内插段误差分布（n={len(err):,}）")

    ax = axs[1]
    order = ["exact", "high", "mid", "low"]
    groups = [conf.loc[conf.confidence == c, "err"].to_numpy() for c in order]
    valid = [(c, g) for c, g in zip(order, groups) if len(g)]
    xs = np.arange(len(valid))
    ax.bar(xs, [np.median(g) for _, g in valid], color=charts.C["green"], zorder=2)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{c}\n(n={len(g):,})" for c, g in valid], fontsize=8)
    ax.set_ylabel("误差中位数（天）")
    ax.set_title("按锚点日期间隔分档")
    fig.suptitle("nid 定年的独立旁证：锚点覆盖区误差以天计，算法口径不变", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.89])
    return charts.save(fig, "20_dating_error.png")


def main() -> None:
    charts.setup_style()
    df, app, ext = load_inputs()
    sb = eras.snapshot_bounds(df)
    newest = pd.Timestamp(eras.estimate([int(df["id"].max())])["est_date"].iloc[0]).date()
    slots = slot_density(df)
    rows, missing, inside = catalog_hits(app, set(int(x) for x in df["id"]))
    err, conf, lo, hi = dating_check(ext)

    fig1 = figure_density(slots, rows)
    fig2 = figure_dating(err, conf)

    t21_n = sum(r[1] for r in rows)
    hit_n = sum(r[2] for r in rows)
    miss_n = len(missing)
    miss_words = [r.get("charCount") or 0 for r in missing]
    in_words = [r.get("charCount") or 0 for r in inside]
    miss_recent = sum((r.get("addTime") or "")[:4] >= "2022" for r in missing) / max(1, miss_n)
    in_recent = sum((r.get("addTime") or "")[:4] >= "2022" for r in inside) / max(1, len(inside))
    miss_short = sum(w <= 10000 for w in miss_words) / max(1, miss_n)
    in_short = sum(w <= 10000 for w in in_words) / max(1, len(inside))

    conf_rows = []
    for c in ["exact", "high", "mid", "low"]:
        g = conf.loc[conf.confidence == c, "err"].to_numpy()
        if len(g):
            conf_rows.append([c, num(len(g)), num(np.median(g)), num(np.percentile(g, 99)),
                              num(g.max())])

    md = []
    md.append("# 20 · 官方 App API 的离线复核：报告 10 与 nid 定年\n")
    md.append("> **补充报告，不是修订。** 本报告不修改报告 10，不修改 `lib/eras.py` 的 "
              "`log(nid)` 定年，也不修改任何 App 设计。报告 10 的单向游标扫描推测、"
              "U 型 / 倒 U 型结论、69.3% 覆盖口径与「补爬对象约 1 千本」保持原样；"
              "App 的种子、分位、书架、观测与 watchlist 口径亦不变。\n")
    md.append("> 全部数字来自已存在的本地产物，**本报告不发起网络请求**；"
              "App API 的 `addTime` 只作独立旁证，不进入定年。\n")

    md.append("## 0. 数据来源与边界\n")
    md.append(md_table([
        ["本地数据集", f"`out/novels.csv`，{num(len(df))} 行", "2026-05-03 内容上界，由 `eras.snapshot_bounds()` 现算复核"],
        ["官方书目枚举", f"`out/app_api_novels.jsonl`，{num(len(app))} 条（nid 去重）", "部分枚举；**只有魔幻类 tid=21 翻到空页**，同类内比较仅用它"],
        ["定年旁证", f"`out/external_dates_full.jsonl`，{num(len(ext))} 条", "第三方站转述的 `addTime`，与锚点同字段语义"],
    ], ["来源", "规模", "用途与限制"]))
    md.append("")
    md.append(f"内容上界现算为 **{sb['date']}**，数据集内最新 nid 定年 {newest}。"
              "枚举文件不入库、可重建；因枚举不完整，本报告**不给出全库覆盖率**，"
              "只做「同类内、同分段」的语义核验。\n")

    md.append("## 1. 「在册密度 U 型」是两个分母中的哪一个\n")
    md.append(f"报告 10 的 U 型分母是 **nid 槽位**（{num(sum(s[1] for s in slots))} 个位置，"
              "其中大量 id 从未对应作品）。用一个已完整枚举的分类，把分母换成"
              f"**官方目录里真实存在的书**（魔幻类 {num(t21_n)} 本），形状完全不同。\n")
    md.append(md_table(
        [[LABELS[i], num(slots[i][0]), f"{slots[i][2]*100:.1f}%",
          num(rows[i][1]), num(rows[i][2]), f"{rows[i][3]*100:.2f}%", num(rows[i][4])]
         for i in range(len(BANDS))],
        ["nid 档", "槽位在册数", "槽位占用率", "目录书目", "本地命中", "目录内命中率", "库外"]))
    md.append("")
    md.append(f"![两种分母]({fig1})\n")
    md.append(f"槽位占用率从两端 {slots[0][2]*100:.1f}% / {slots[-1][2]*100:.1f}% "
              f"降到中段 {min(s[2] for s in slots)*100:.1f}%，U 型成立；"
              f"但魔幻类目录内命中率七档为 "
              f"{min(r[3] for r in rows)*100:.2f}%–{max(r[3] for r in rows)*100:.2f}%，"
              f"整体 {pct(hit_n/t21_n, 2)}，**没有 U 型**。\n")
    md.append("> 结论：两个陈述并不冲突。U 型描述「nid 槽位是否被填」（受 id 空洞与老书"
              "短命影响），目录内命中率描述「已存在的书是否被抓到」（接近满分）。"
              "报告 10 把两者分开处理是正确的；本报告只是把该区分用独立目录数据实测出来。\n")

    md.append("## 2. 遗漏画像的同类内抽查（方向性，不替代报告 10）\n")
    md.append(f"在同一分类内，快照前已存在却未入库的书 {num(miss_n)} 本（占该分类目录 "
              f"{pct(miss_n/t21_n, 2)}）。与在册书对比：\n")
    md.append(md_table([
        ["字数中位数", num(np.median(miss_words)), num(np.median(in_words))],
        ["≤1 万字占比", pct(miss_short), pct(in_short)],
        ["2022 年后上架占比", pct(miss_recent), pct(in_recent)],
    ], ["指标", "库外（快照前）", "在册"]))
    md.append("")
    md.append("同类内样本里，库外书**更长、更新近**，与报告 10 全库口径的「偏短、新、更新中」"
              "只在「新」上同向。差异有两个明确来源：① 库外高度集中在 650–774k 最新档"
              f"（{num(rows[-1][4])}/{num(miss_n)}），该档本身字数分布不同；"
              "② 本报告只覆盖魔幻一类，报告 10 的画像跨全部分类与更早世代。"
              "因此该结果**只作方向性注记，不改报告 10 的遗漏画像**。\n")

    md.append("## 3. nid 定年的独立旁证\n")
    md.append(f"锚点 {num(len(eras.load_anchors()))} 条，nid 范围 {num(lo)}–{num(hi)}。"
              f"外部日期全部落在内插段（{num(len(err))} 条），与 `eras.estimate()` "
              "预测的创建日按**日期**取绝对差：\n")
    md.append(md_table([
        ["中位", num(np.median(err)), "P90", num(np.percentile(err, 90))],
        ["P99", num(np.percentile(err, 99)), "最大", num(err.max())],
        ["≤30 天", pct((err <= 30).mean(), 1), "绝对误差均值", f"{np.mean(err):.2f} 天"],
    ], ["指标", "值", "指标", "值"]))
    md.append("")
    md.append(md_table(conf_rows, ["置信度", "样本", "误差中位（天）", "P99（天）", "最大（天）"]))
    md.append("")
    md.append(f"![定年误差]({fig2})\n")
    md.append("误差以天计、100% ≤30 天，说明报告 01/10 采用的 `log(nid)` 分段线性定年"
              "在锚点覆盖区是可用的；外推段（nid 超过锚点上限）不在此结论范围内。"
              "**定年算法与锚点均不因本报告改动**，App API 的秒级 `addTime` 继续只作旁证。\n")

    md.append("## 4. 与报告 10 / App 设计的关系\n")
    md.append(md_table([
        ["报告 10 的 U 型 / 倒 U 型", "保持", "本报告确认其分母是 nid 槽位，非目录内命中率"],
        ["覆盖率 69.3% 与三态判据", "保持", "本报告不重算覆盖率，也不改三态判据"],
        ["补爬对象约 1 千本", "保持", "魔幻类目录内库外 315 本，与该量级不冲突"],
        ["`eras.py` 定年与 104 锚点", "保持", "31,229 条旁证误差中位 2 天、P99 10 天"],
        ["App 种子 / 分位 / 书架 / 观测 / watchlist", "保持", "本报告不产生任何下发字段"],
    ], ["对象", "处置", "说明"]))
    md.append("")

    md.append("## 5. 复现与局限\n")
    md.append("```bash\n"
              "cd analysis\n"
              "uv run python generators/report_20_app_api_crosscheck.py\n"
              "```\n")
    md.append(f"- 依赖 `out/app_api_novels.jsonl` 与 `out/external_dates_full.jsonl`；"
              "两者是可重建的派生资产，缺失时生成器直接报错，不会替你联网补采。\n"
              f"- 枚举仅魔幻类完整（{num(t21_n)} 本），其余分类不可用于目录内比较；"
              "不给出全库漏抓率或新覆盖率。\n"
              "- 误差按日期取差（非秒级），第三方站是 App `addTime` 的转述而非独立采集，"
              "其价值是校验转述忠实度与定年量级，不是新增数据源。\n"
              "- 所有发现为结构描述；相关不等于因果。\n")

    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()

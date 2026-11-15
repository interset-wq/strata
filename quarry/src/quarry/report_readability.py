"""出「可读性结构」报告的图和表。

用法：
    uv run python -m quarry.report_readability
"""
from __future__ import annotations

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config, readability as R

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2328"
MUTED = "#6e7781"
DONE_C = "#2f6f8f"
ONGO_C = "#a8c6d6"
DEAD_C = "#dcdcdc"


def _fmt(n) -> str:
    return f"{int(n):,}"


def plot(lad: pd.DataFrame, bands: pd.DataFrame, path) -> None:
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.6, 4.9), dpi=170,
                                  gridspec_kw={"width_ratios": [1.05, 1]})

    # ── 左：可读性阶梯（对数轴，否则 3,766 会看不见）──
    y = list(range(len(lad)))[::-1]
    ax.barh(y, lad["books"], color=DONE_C, height=0.62, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(lad["stage"], fontsize=9, color=INK)
    ax.set_xscale("log")
    ax.set_xlim(1000, 900_000)
    ax.set_title("24.6 万本里，能推荐给人读完的只有 3,766 本", color=INK,
                 fontsize=10.5, loc="left")
    for yy, (_, r) in zip(y, lad.iterrows()):
        tail = "" if r["pct_prev"] >= 100 else f"　（留 {r['pct_prev']:.0f}%）"
        ax.text(r["books"] * 1.15, yy, f"{_fmt(r['books'])}　{r['pct_all']:.2f}%{tail}",
                va="center", fontsize=8.5, color=INK)
    ax.set_xlabel("本数（对数轴）· 右侧小字为「相对上一级的留存」", color=MUTED, fontsize=8.5)

    # ── 右：带内结局率 —— 越长越容易完结，但长到 100 万字仍有坑 ──
    # 0–0.1 万那一档被排除：里面 17,720 本字数中位 506、点击中位 54，
    # 4,496 本标着「完结」但中位只有 428 字，是空壳/试笔，完结率在那里没有意义。
    bands = bands[bands["band"] > 0].reset_index(drop=True)
    x = list(range(len(bands)))
    ax2.plot(x, bands["done_pct"], color=DONE_C, lw=1.8, marker="o", ms=4,
             label="完结率")
    ax2.plot(x, bands["dead_pct"], color="#9aa4ad", lw=1.8, marker="o", ms=4,
             label="断更率")
    ax2.set_xticks(x)
    ax2.set_xticklabels(bands["label"], fontsize=7.8, rotation=38, ha="right")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("带内占比（%）", color=MUTED, fontsize=8.5)
    ax2.set_title("10 万字是一道坎：过坎后完结率 15% → 58%", color=INK,
                  fontsize=10.5, loc="left")
    ax2.legend(frameon=False, fontsize=8, loc="center left")
    last = bands.iloc[-1]
    ax2.annotate(
        f"≥100 万：断更 {last['dead_pct']:.0f}%",
        xy=(x[-1], last["dead_pct"]), xytext=(x[-1] - 2.4, 12),
        fontsize=7.6, color=MUTED, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7),
    )

    for a in (ax, ax2):
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a.spines[s].set_color("#d0d7de")
        a.tick_params(colors=MUTED, labelsize=8)

    fig.text(0.008, 0.985, "可读性：这不是 24.6 万本书，是 3,766 本可读完的书",
             fontsize=13, color=INK, ha="left", va="top")
    fig.text(0.008, 0.945,
             "已剔除引进日轻；结局取 outcome 三值（done/dead/ongoing）；"
             "「可读完」= 完结且 ≥30 万字",
             fontsize=8.2, color=MUTED, ha="left", va="top")

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        lad = R.ladder(con)
        bands = R.word_bands(con)
        out = config.REPORT_DIR / "02_readability.png"
        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        plot(lad, bands, out)
        print(f"→ {out}")
    finally:
        con.close()


if __name__ == "__main__":
    main()

"""出时间轴报告用的图。

一张图说清三件事：
1. 供给曲线（年度新增书，柱）——2015 起飞、2022 见顶、之后塌陷
2. 认可密度（每千本获 banner，线，右轴对数）——2016 见顶后单调下滑
3. 删失区（灰底）——2024 起数据不可当实况读

用法：
    uv run python -m quarry.report_timeline
"""
from __future__ import annotations

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2328"
MUTED = "#6e7781"
ACCENT = "#b3261e"
BAR = "#8fa9c4"


def load_stats() -> pd.DataFrame:
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        return con.execute("select * from era_stats order by year").df()
    finally:
        con.close()


def plot(df: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(11, 5.4), dpi=170)
    x = df["year"].to_numpy()

    ax.bar(x, df["books_new"], color=BAR, width=0.72, label="当年新增书（本）", zorder=2)
    ax.set_ylabel("当年新增书（本）", color=MUTED, fontsize=9)
    ax.tick_params(axis="y", colors=MUTED, labelsize=8)
    ax.tick_params(axis="x", colors=MUTED, labelsize=8)

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#d0d7de")

    # 删失区
    c = df[df["censored"]]["year"]
    if len(c):
        ax.axvspan(c.min() - 0.5, c.max() + 0.5, color="#f0f0f0", zorder=0)
        ax.text(
            c.max() - 0.2, df["books_new"].max() * 0.90,
            "删失区\nbanner 授予\n未发生完", color=MUTED, fontsize=7.5,
            ha="right", va="top", linespacing=1.4,
        )

    # 右轴：认可密度。0 值放到 NaN，否则对数轴会把整段压平。
    dens = df["grant_per_1k"].astype("float64")
    dens = dens.mask(dens <= 0)
    ax2 = ax.twinx()
    ax2.plot(x, dens, color=ACCENT, lw=1.8, marker="o", ms=3.2,
             label="每千本获 banner（‰）", zorder=3)
    ax2.set_yscale("log")
    ax2.set_ylim(0.3, 3000)
    ax2.set_ylabel("每千本获 banner（‰，对数轴）", color=ACCENT, fontsize=9)
    ax2.tick_params(axis="y", colors=ACCENT, labelsize=8)
    ax2.spines["top"].set_visible(False)

    # 峰值由数据决定，不写死——写死过一次，把 2016 当成了密度峰值（其实 2015 更高）
    peak_d = df.loc[df["grant_per_1k"].idxmax()]
    peak_s = df.loc[df["books_new"].idxmax()]
    ax2.annotate(
        f"密度峰值 {int(peak_d['year'])}  {peak_d['grant_per_1k']:.1f}‰",
        xy=(peak_d["year"], peak_d["grant_per_1k"]),
        xytext=(peak_d["year"] - 6.2, 260),
        fontsize=8, color=ACCENT,
        arrowprops=dict(arrowstyle="-", color=ACCENT, lw=0.8),
    )
    ax.annotate(
        f"供给峰值 {int(peak_s['year'])}  {int(peak_s['books_new']):,} 本",
        xy=(peak_s["year"], peak_s["books_new"]),
        xytext=(peak_s["year"] - 0.4, peak_s["books_new"] * 1.21),
        ha="center", fontsize=8, color=INK,
        arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8),
    )

    fig.text(
        0.008, 0.975,
        "菠萝包轻小说（SF 轻小说）二十年：供给与原创作品的认可密度",
        fontsize=13.5, color=INK, ha="left", va="top",
    )
    fig.text(
        0.008, 0.928,
        "供给 2022 见顶；认可密度 2015 见顶后单调下滑。已剔除版权方账号（天闻角川/HJ文库/"
        "丸山黄金）的引进日轻，灰区为右删失",
        fontsize=8.8, color=MUTED, ha="left", va="top",
    )

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False, fontsize=8.5)

    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    df = load_stats()
    out = config.REPORT_DIR / "00_timeline.png"
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    plot(df, out)
    print(f"→ {out}")


if __name__ == "__main__":
    main()

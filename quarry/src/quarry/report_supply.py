"""出「供给崩塌归因」报告的图和表。

用法：
    uv run python -m quarry.report_supply
"""
from __future__ import annotations

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from . import config, supply

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1f2328"
MUTED = "#6e7781"
ACCENT = "#b3261e"
BAR2 = "#8fa9c4"
BAR1 = "#c9d6e2"


def _fmt(n) -> str:
    return "—" if pd.isna(n) else f"{int(n):,}"


def plot(d: pd.DataFrame, r: pd.DataFrame, path) -> None:
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.4, 4.6), dpi=170)
    v = d[d["year"] >= 2015]

    ax.bar(v["year"], v["books_new"], color=BAR2, width=0.7, label="当年首次出现的人", zorder=2)
    ax.bar(v["year"], v["books_old"], bottom=v["books_new"], color=ACCENT, width=0.7,
           label="往年已出现的人", zorder=2)
    ax.set_title("供给 = 新人的书 + 老人的书", color=INK, fontsize=10.5, loc="left")
    ax.set_ylabel("当年新增书（本）", color=MUTED, fontsize=8.5)
    ax.set_xticks(range(2015, 2026, 2))
    ax.set_ylim(0, 46000)

    a = d[d["year"] == 2022].iloc[0]
    b = d[d["year"] == 2025].iloc[0]
    # 标注放左上空白区，不压柱子（压在柱子上过一次，2022 那根正好挡住第三行）
    ax.text(
        2018.15, 43200,
        f"2022 → 2025  −{_fmt(a['books'] - b['books'])} 本",
        fontsize=8.5, color=INK, ha="left", va="top",
    )
    ax.text(
        2018.15, 39700,
        f"新人 −{_fmt(a['books_new'] - b['books_new'])}（73%） · "
        f"老人 −{_fmt(a['books_old'] - b['books_old'])}（27%）",
        fontsize=8.2, color=MUTED, ha="left", va="top",
    )

    for k, c, lab in (("k1", INK, "第 1 年"), ("k2", ACCENT, "第 2 年"), ("k3", "#6e7781", "第 3 年")):
        ax2.plot(r["cohort"], r[k], color=c, lw=1.7, marker="o", ms=3.2, label=lab)
    ax2.set_title("新人留存：首年后还在发书的比例", color=INK, fontsize=10.5, loc="left")
    ax2.set_ylabel("留存率（%）", color=MUTED, fontsize=8.5)
    ax2.set_ylim(0, 20)
    ax2.set_xlim(2014.5, 2024.8)
    ax2.legend(frameon=False, fontsize=8, loc="upper right")
    ax2.annotate(
        "k=1 峰值 17.7%（2020）", xy=(2020, 17.7), xytext=(2015.2, 18.6),
        fontsize=7.5, color=MUTED, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7),
    )

    for a_ in (ax, ax2):
        for s in ("top", "right"):
            a_.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a_.spines[s].set_color("#d0d7de")
        a_.tick_params(colors=MUTED, labelsize=8)

    fig.text(0.008, 0.985, "供给为什么塌：人少了，不是人写少了",
             fontsize=13, color=INK, ha="left", va="top")
    fig.text(0.008, 0.945,
             "已剔除引进日轻；2026-05 起新书只剩约 7% 可见，不进曲线（见报告 §1）",
             fontsize=8.2, color=MUTED, ha="left", va="top")
    ax.legend(frameon=False, fontsize=8, loc="upper left")

    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    try:
        d = supply.by_year(con)
        r = supply.retention(con)
        out = config.REPORT_DIR / "01_supply.png"
        config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        plot(d, r, out)
        print(f"→ {out}")
    finally:
        con.close()


if __name__ == "__main__":
    main()

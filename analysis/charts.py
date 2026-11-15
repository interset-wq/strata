"""报告图表公共设施：风格、配色、分期底色、输出目录。

各 report_*.py 生成器共用，保证系列报告视觉一致。
图表输出至 analysis/reports/figures/，报告内以相对路径 figures/<name> 引用。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

FIG_DIR = Path(__file__).resolve().parent / "reports" / "figures"

# 分期底色（与报告分期一致）
PERIODS = [
    (2007, 2014, "兴趣站期", "#F2F2F2"),
    (2015, 2016, "商业化初期", "#E8EEF7"),
    (2017, 2022, "扩张期", "#DCE8F5"),
    (2023, 2025, "收缩期", "#F5E8E8"),
]

# 系列配色（色盲安全，无涨跌语义）
C = {"blue": "#4477AA", "red": "#CC3311", "green": "#009988", "gray": "#777777"}

_setup_done = False


def setup_style() -> None:
    global _setup_done
    if _setup_done:
        return
    for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "savefig.dpi": 150,
            "figure.dpi": 150,
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.axisbelow": True,
            "axes.grid": True,
            "grid.color": "#DDDDDD",
            "grid.linewidth": 0.6,
        }
    )
    _setup_done = True


def save(fig: plt.Figure, name: str) -> str:
    """保存图表，返回报告内可用的相对路径。"""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"figures/{name}"


def shade_periods(ax, years, label_y_frac: float = 0.97) -> None:
    """按分期加底色带并在顶部标注分期名。"""
    for lo, hi, name, color in PERIODS:
        if years.max() < lo or years.min() > hi:
            continue
        ax.axvspan(lo - 0.5, hi + 0.5, color=color, zorder=0)
        mid = (max(lo, years.min()) + min(hi, years.max())) / 2
        ax.text(
            mid, label_y_frac, name, transform=ax.get_xaxis_transform(),
            ha="center", va="top", fontsize=7.5, color="#666666",
        )

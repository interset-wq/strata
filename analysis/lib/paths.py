"""项目路径的唯一真源。

此前 `config.py`、`eras.py`、`charts.py` 各自用
`Path(__file__).resolve().parent` 推算根目录，脚本又用 5 种不同写法
拼路径（`BASE / "out"`、`Path(__file__).resolve().parent / "out"`、
写死的 `Path("E:/novly-proj/analysis")`……）。结果是「脚本在哪」与
「数据在哪」两件事被混在一起，移动脚本就会静默读错路径。

现在所有路径都从这里派生，与脚本所在位置无关：
`ROOT` 恒等于 analysis/ 根目录（`lib/` 的上一级）。

    from lib import paths
    df = pd.read_csv(paths.CSV_FILE)
"""

from __future__ import annotations

from pathlib import Path

# lib/ 的上一级 = analysis/ 根目录
ROOT = Path(__file__).resolve().parent.parent

# ---- 输入：唯一原始数据集 ----
DATA_DIR = ROOT / "data"
ARCHIVE = DATA_DIR / "dataset.7z"
EXTRACT_DIR = DATA_DIR / "extracted"
JSONL_DIR = EXTRACT_DIR / "dataset" / "data"

# ---- 锚点与参考资料 ----
ANCHORS_DIR = ROOT / "anchors"
NID_ANCHORS = ANCHORS_DIR / "nid_anchors.jsonl"
VERIFIED_DATES = ANCHORS_DIR / "verified_dates.jsonl"
APPROXIMATE_DATES = ANCHORS_DIR / "approximate_dates.jsonl"
CONTEST_SHORT_MEDIUM = ANCHORS_DIR / "contest_short_medium.json"  # E.34: 中短篇赛事 roster union
REFERENCES_DIR = ROOT / "references"

# ---- 产物（不入库，由管线重建）----
OUT_DIR = ROOT / "out"
CSV_FILE = OUT_DIR / "novels.csv"
SQL_FILE = OUT_DIR / "schema.sql"
MANIFEST = OUT_DIR / "manifest.json"
MONTHLY_RANKS = OUT_DIR / "monthly_ranks.jsonl"
SURVIVAL_PROBE = OUT_DIR / "survival_probe.jsonl"
APP_API_NOVELS = OUT_DIR / "app_api_novels.jsonl"          # 官方 App API 书目枚举（可选、部分）
EXTERNAL_DATES = OUT_DIR / "external_dates_full.jsonl"     # 第三方站 addTime 旁证（可选）

# ---- 报告产物 ----
REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

__all__ = [
    "ROOT", "DATA_DIR", "ARCHIVE", "EXTRACT_DIR", "JSONL_DIR",
    "ANCHORS_DIR", "NID_ANCHORS", "VERIFIED_DATES", "APPROXIMATE_DATES",
    "CONTEST_SHORT_MEDIUM",
    "REFERENCES_DIR", "OUT_DIR", "CSV_FILE", "SQL_FILE", "MANIFEST",
    "MONTHLY_RANKS", "SURVIVAL_PROBE", "REPORTS_DIR", "FIGURES_DIR",
    "APP_API_NOVELS", "EXTERNAL_DATES",
]

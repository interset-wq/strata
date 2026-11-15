"""全局路径与常量。所有脚本只从这里取路径，不写死字符串。

数据流（只有一层产物）：
    data/raw/chunks/*.sqlite   上游三片原始快照（gitignored，不随 Release 发布）
              │
              ▼  uv run python -m quarry.build_dataset
    datasets/v1/               我们自己的数据集（gitignored，随 Release 发布）
      ├── strata-v1.duckdb     开箱即用
      ├── parquet/*.parquet    工具无关，长期归档
      └── manifest.json        版本 / 行数 / sha256 / 来源

分析代码只读 `datasets/`，永不读 raw。
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # → quarry/
WORKSPACE = ROOT.parent  # → novly-proj/

# ── 原始快照（只在构建数据集时用）──
_RAW_ENV = os.environ.get("QUARRY_RAW")
RAW_DIR = Path(_RAW_ENV) if _RAW_ENV else ROOT / "data" / "raw" / "chunks"

# ── 自有数据集（分析唯一入口）──
DATASET_VERSION = os.environ.get("QUARRY_DATASET_VERSION", "v1")
DATASET_DIR = Path(
    os.environ.get("QUARRY_DATASET_DIR", ROOT / "datasets" / DATASET_VERSION)
)
DUCKDB_PATH = DATASET_DIR / f"strata-{DATASET_VERSION}.duckdb"
PARQUET_DIR = DATASET_DIR / "parquet"
MANIFEST_PATH = DATASET_DIR / "manifest.json"

REPORT_DIR = ROOT / "reports"
SQL_DIR = ROOT / "sql"
DOCS_DIR = WORKSPACE / "docs"

# ── nid → 日期锚点（API 实测，入库，随数据集一起发布）──
# 85 个点：按全库 nid 的 2.5% 分位均匀采样 + 7 个手工补的早期真锚点。
# 这是定年模型的全部依据，改动必须同步更新 tests 里的留一法断言。
ANCHORS_PATH = Path(
    os.environ.get("QUARRY_ANCHORS", ROOT / "data" / "anchors" / "nid_anchors.jsonl")
)

CHUNKS = ("cold", "warm", "hot")

# 数据集 schema 版本：列结构变化时 +1，读取方据此判断能否兼容
# v2：新增 novels_era（nid 定年）与 era_stats（年表）两张表
SCHEMA_VERSION = 2

# 已知事实基线：断言用。数字变化即代表上游快照或口径变了，必须人工确认后再改。
BASELINE = {
    "novels_total": 246_045,
    "banner_total": 667,
    "banner_warm": 638,
    "banner_hot": 29,
    "cold_has_banner": 0,
    "novel_tags_total": 742_546,
    "tag_total": 106,
    "authors_clean": 137_965,
    "contests_clean": 99,
    "dup_title_author_groups": 9,
    "default_cover": 34_641,
    "zero_click": 4_476,
    "like_negative": 58,
}


def chunk_path(chunk: str) -> Path:
    return RAW_DIR / f"{chunk}_chunk.sqlite"

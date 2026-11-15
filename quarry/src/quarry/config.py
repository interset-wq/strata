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

# 上游交付的三个文件。**只是打包方式，不是数据属性**：上游为了首屏加载把库拆成
# 三个 sqlite 分批解压，切分依据是 status（cold = 2/4 完结·断更，warm = 5/6，
# hot = 3 连载中），一一对应，没有任何信息量。本数据集只在构建期读这三个文件，
# 产物里**不保留 chunk 列**——任何分析需要「完结/断更」这层区分时，直接用 status。
CHUNKS = ("cold", "warm", "hot")

# ── 引进日轻的出版方账号 ──────────────────────────────────
# 为什么按账号识别，而不是按标题或年份：
#   1. 引进日轻由版权方以「出版方账号」上传，banner 也由版权方提供，
#      不代表 SFACG 对原创作品的当期认可。做认可机制分析时必须排除。
#   2. 实测这四个账号名下 47 本书 banner 率 100%（天闻角川 36 + 2号机 1 +
#      HJ文库 9 + 丸山黄金 1），而标题里出现「刀剑神域」「凉宫」的 200+ 本
#      绝大多数是**中国人写的同人**，属于原创，不能排除——标题匹配不可用。
#   3. 年份也不可用：2008-2013 的作者名全是中文网名（魂之重奏、逆鳞.散落），
#      盗版期的整本搬运已不可识别，只有正版引进留下账号痕迹。
# 「丸山黄金」是《Overlord》作者本人的署名账号（1 本，1,711 万人气），
#   属于版权方一侧而非站内作者，故与出版方账号同口径处理。
# 新增账号必须同时更新 BASELINE["import_books"] 与 tests 里的断言。
IMPORT_PUBLISHERS = ("天闻角川", "天闻角川2号机", "HJ文库", "丸山黄金")

# 数据集 schema 版本：列结构变化时 +1，读取方据此判断能否兼容
# v2：新增 novels_era（nid 定年）与 era_stats（年表）两张表
# v3：novels 增 flg_import；era_stats 排除引进日轻，并新增 import 两列
# v4：novels 去掉 chunk 列（上游按 status 的打包切分，非数据属性）
SCHEMA_VERSION = 4

# 已知事实基线：断言用。数字变化即代表上游快照或口径变了，必须人工确认后再改。
BASELINE = {
    "novels_total": 246_045,
    "banner_total": 667,
    # banner 只出现在 status 3（连载中）/ 5 / 6，status 2/4（完结·断更）恒为 0。
    # 原写作「banner 只在 warm 和 hot」，那是分片的同义反复，已换成 status 口径。
    "banner_status_3": 29,
    "banner_status_5_6": 638,
    "banner_status_2_4": 0,
    "status_counts": {2: 42_193, 3: 2_805, 4: 198_532, 5: 1_127, 6: 1_388},
    "novel_tags_total": 742_546,
    "tag_total": 106,
    "authors_clean": 137_965,
    "contests_clean": 99,
    "dup_title_author_groups": 9,
    "default_cover": 34_641,
    "zero_click": 4_476,
    "like_negative": 58,
    # 引进日轻：47 本（角川 36 + 2号机 1 + HJ文库 9 + 丸山黄金 1），banner 47/47
    "import_books": 47,
    "import_banners": 47,
    # 排除引进日轻后的 banner 总数（原 667）
    "banner_original_only": 620,
    # 供给归因的锚点（reports/01_supply.md §2）。2022 是供给峰值，
    # 2025 是最后一个完整采集年。
    "supply_2022": 37_095,
    "supply_2025": 14_574,
    "supply_drop": 22_521,
    # 采集可用上限：2026-04。5 月起「每千个 nid 的成书数」从 ~490 掉到 36，
    # 而 nid 序列仍以 ~72/天 推进 —— 新书是「看不见」，不是「没有」。
    # 见 supply.nid_density()；低于 density_floor 的月份一律不进任何序列。
    "supply_usable_until": "2026-04",
    "density_2026_04": 492,
    "density_2026_05": 36,
    "density_floor": 200,
}


def chunk_path(chunk: str) -> Path:
    return RAW_DIR / f"{chunk}_chunk.sqlite"

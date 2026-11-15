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
# 产物里**不保留 chunk 列**——任何分析需要「完结/断更」这层区分时，直接用 outcome。
CHUNKS = ("cold", "warm", "hot")

# ── 上游 status 的两个派生层，都必须剥掉 ────────────────────────
# 上游 `status` 有 5 个值，看着像「5 种状态」，其实是**两个正交维度压成了一列**：
#
#   维度一：结局（平台状态）  2 完结 / 4 断更 / 3 连载中
#   维度二：A 标（派生状态）  5 = 断更A、6 = 完结A
#
# A 标不是平台状态，是 novel_hub 按规则给「成绩好的完结/断更书」打的标
# （`novel_hub/docs/website.md` 的 Data Rules）。判定式见 A_RULE_SQL。
#
# 实测（2026-11-15）：判定式在非引进的 243,193 本完结/断更书上**零反例**——
#   原 5/6 的 2,468 本全部 rule=True；原 2/4 的 240,725 本全部 rule=False。
# 也就是说 `status` 里的 5/6 相对 2/4 **不携带任何额外信息**，完全可推导。
# 更糟的是 A 标会污染结局分析：A 的实质是「收藏≥1万」（2,468 本里 2,353 本靠
# 这一条进来），而 cold 段的 `like_num` 上限恰好是 9,999 —— A 的阈值比截断线
# 高 1 档，于是「成绩达标」与「数值未被截断」在这个字段里纠缠不清。
# 用 status=6 当「长篇小说」的代表会得到 108.7 万字的中位数，那是**选择偏差**，
# 不是长篇的常态（完结长篇的 65% 落在未达标组）。
#
# 所以我们把它拆成两个语义干净的列：
#   outcome       结局三值，我们的语义，唯一权威的「完结/断更/连载中」
#   stats_precise 数值精度标记 = 原 status ∈ {3,5,6}（5,320 本）。
#                 语义只有一句：**这本的 click/like/praise 来自详情页精确通道，
#                 不是列表页显示值**。跟结局无关，跟质量无关。
STATUS_TO_OUTCOME = {2: "done", 3: "ongoing", 4: "dead", 5: "dead", 6: "done"}
OUTCOMES = ("ongoing", "done", "dead")
# 精确通道对应的原始状态。上游 A 标只打在 2/4 上，3（连载中）本来就走精确通道，
# 所以精度判据是 3/5/6 而不是 5/6 —— 用 5/6 会漏掉 2,805 本连载中的精确值。
PRECISE_STATUS = (3, 5, 6)

# A 判定式，原样抄自 novel_hub/docs/website.md 的 Data Rules：
#   断更/已完结 + (banner OR 人气≥1000万 OR 长评≥60 OR 收藏≥1万 OR 赞≥1万)
# 只用于**审查**（tests 复现零反例），不进 schema —— 它是别人的主观划分，
# 我们要保留的只有「数值精度」那一面，已经落在 stats_precise。
# 上游列名语义：click_num=人气、like_num=收藏、praise_num=赞、review_num=长评。
# 注意 review_num 有 98% 是 NULL（列表页不显示长评数），coalesce 成 0 后
# 判定结果仍与上游一致，说明实际起作用的是其余四条。
A_RULE_SQL = (
    "(coalesce(has_banner, 0) = 1"
    " or coalesce(click_num, 0) >= 10000000"
    " or coalesce(review_num, 0) >= 60"
    " or coalesce(like_num, 0) >= 10000"
    " or coalesce(praise_num, 0) >= 10000)"
)

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
# v5：novels 的 status 拆成 outcome（三值）+ stats_precise（精度标记），删 status
SCHEMA_VERSION = 5

# 已知事实基线：断言用。数字变化即代表上游快照或口径变了，必须人工确认后再改。
BASELINE = {
    "novels_total": 246_045,
    "banner_total": 667,
    # banner 只出现在 stats_precise 的书上（5,320 本里的 667 个），
    # 但跨全部三种结局 —— 209 个在断更书上（那些书的成绩达标，被 A 标选中）。
    "banner_outcome_done": 429,
    "banner_outcome_ongoing": 29,
    "banner_outcome_dead": 209,
    # outcome 三值（非引进 245,998 + 引进 47）
    "outcome_counts": {"done": 43_581, "dead": 199_659, "ongoing": 2_805},
    "stats_precise_true": 5_320,
    # A 判定式零反例的证据（tests 复现）：原 5/6 全 rule=True，原 2/4 全 rule=False
    "a_rule_true": 2_468,
    "a_rule_false": 240_725,
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
    # 可读性结构（reports/02_readability.md）。readable = 完结且 ≥30 万字。
    "done_books": 43_577,
    "dead_books": 199_616,
    "readable_books": 3_766,
    "under_10k_books": 120_204,
    # ≥100 万字的书里仍有这么多是断更 —— 「长 = 安全」是错觉
    "dead_pct_at_1m": 31.4,
}


def chunk_path(chunk: str) -> Path:
    return RAW_DIR / f"{chunk}_chunk.sqlite"

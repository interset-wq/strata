"""路径、来源、码表与列契约。

对字段语义的断言只写在这一处，构建与校验共用，避免两处漂移。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ARCHIVE = DATA_DIR / "dataset.7z"
EXTRACT_DIR = DATA_DIR / "extracted"
SOURCE_DB = EXTRACT_DIR / "dataset" / "database.db"
OUT_DIR = ROOT / "out"
CSV_DIR = OUT_DIR / "csv"
SQL_FILE = OUT_DIR / "schema.sql"
MANIFEST = OUT_DIR / "manifest.json"

SOURCE = {
    "repo": "light-nook-labs/novel_hub",
    "tag": "v0.0.1",
    "asset": "dataset.7z",
    "sha256": "9cd37bc7f3911746e19a17e276e06e4106eb44edde0c4e9ca4bd43bf83e279e7",
}

# ---------------------------------------------------------------- 码表
# 源库把 genre/ptype/status 存为裸整数且无外键，码表在此显式化。

STATUS = {
    1: ("未知", "unknown"),
    2: ("已完结", "done"),
    3: ("连载中", "ongoing"),
    4: ("断更", "dead"),
}

GENRE = {
    1: "未分类",
    2: "魔幻",
    3: "玄幻",
    4: "古风",
    5: "科幻",
    6: "校园",
    7: "都市",
    8: "游戏",
    9: "同人",
    10: "悬疑",
}

PTYPE = {
    2: "免费",
    3: "签约",
    4: "VIP",
}

# 源库存在但整列为 NULL，不导出；记入 manifest.dropped 以便追溯。
DROPPED = {
    "review_num": "全表 NULL（0 个非空值）",
    "comment_num": "全表 NULL（0 个非空值）",
    "db_update": "全表单值，属快照元数据，写 manifest.source.snapshot",
}

# ---------------------------------------------------------------- 列契约
# (列名, dtype, nullable, key, 说明)
# dtype 为写入 CSV 后的目标语义类型，供 pandas 读取时对齐。

SCHEMA: dict[str, list[tuple[str, str, bool, str, str]]] = {
    "novel": [
        ("nid", "int64", False, "PK", "站点作品编号，唯一且单调递增，空洞属正常"),
        ("title", "string", False, "", "书名"),
        ("author_id", "int64", False, "FK author.id", "作者；平台规则下名字唯一且不可改"),
        ("genre_id", "int8", False, "FK genre.id", "分类"),
        ("ptype_id", "int8", False, "FK ptype.id", "发布类型，站方分层"),
        ("status_id", "int8", False, "FK status.id", "站点状态码；1 为未归类"),
        ("contest_id", "Int64", True, "FK contest.id", "征文；NULL 表示未参加"),
        ("word_num", "int64", False, "", "字数，快照时点累计值"),
        ("click_num", "int64", False, "", "人气，累计浏览"),
        ("like_num", "Int64", True, "", "收藏；上游负值已置 NULL"),
        ("praise_num", "int64", False, "", "赞"),
        ("has_banner", "int8", False, "", "站方运营位，0/1，非质量分"),
        ("cover", "string", True, "", "封面文件名；NULL 表示无封面"),
        ("last_update", "string", False, "", "最后更新时间，ISO 8601 无时区"),
    ],
    "author": [
        ("id", "int64", False, "PK", "作者编号"),
        ("name", "string", False, "UNIQUE", "作者名，平台内不可修改"),
    ],
    "tag": [
        ("id", "int64", False, "PK", "标签编号"),
        ("name", "string", False, "UNIQUE", "标签名"),
    ],
    "novel_tag": [
        ("novel_id", "int64", False, "PK,FK novel.nid", "作品编号"),
        ("tag_id", "int64", False, "PK,FK tag.id", "标签编号"),
    ],
    "contest": [
        ("id", "int64", False, "PK", "征文编号"),
        ("name", "string", False, "UNIQUE", "征文名"),
    ],
    "genre": [
        ("id", "int8", False, "PK", "分类码"),
        ("name", "string", False, "UNIQUE", "分类名"),
    ],
    "ptype": [
        ("id", "int8", False, "PK", "发布类型码"),
        ("name", "string", False, "UNIQUE", "发布类型名"),
    ],
    "status": [
        ("id", "int8", False, "PK", "状态码"),
        ("label", "string", False, "", "站点状态字面值"),
        ("outcome", "string", False, "UNIQUE", "机器可读结局，见 config.STATUS"),
    ],
}

# 非负计数列：约束与校验共用
NON_NEGATIVE = ["word_num", "click_num", "praise_num"]

# 派生宽表，仅供人读与快速探索，不作权威数据，可随时重建
FLAT_COLUMNS = [
    "nid",
    "title",
    "author",
    "author_id",
    "genre",
    "genre_id",
    "ptype",
    "ptype_id",
    "status",
    "status_id",
    "outcome",
    "contest",
    "contest_id",
    "tags",
    "word_num",
    "click_num",
    "like_num",
    "praise_num",
    "has_banner",
    "cover",
    "last_update",
]

CSV_KWARGS = dict(index=False, encoding="utf-8", lineterminator="\n", na_rep="")


def schema_columns(table: str) -> list[str]:
    """目标列名，顺序即 CSV 表头顺序。"""
    return [c[0] for c in SCHEMA[table]]

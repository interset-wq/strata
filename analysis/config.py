"""路径、来源、列定义与清洗规则。

对字段语义的断言只写在这一处，构建与校验共用。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ARCHIVE = DATA_DIR / "dataset.7z"
EXTRACT_DIR = DATA_DIR / "extracted"
JSONL_DIR = EXTRACT_DIR / "dataset" / "data"
OUT_DIR = ROOT / "out"
CSV_FILE = OUT_DIR / "novels.csv"
SQL_FILE = OUT_DIR / "schema.sql"
MANIFEST = OUT_DIR / "manifest.json"

SOURCE = {
    "repo": "light-nook-labs/novel_hub",
    "tag": "v0.0.1",
    "asset": "dataset.7z",
    "sha256": "9cd37bc7f3911746e19a17e276e06e4106eb44edde0c4e9ca4bd43bf83e279e7",
    "glob": "meta*.jsonl",
}

# ---------------------------------------------------------------- 枚举域
GENRES = ["魔幻", "玄幻", "古风", "科幻", "校园", "都市", "游戏", "同人", "悬疑"]
PRICE_TYPES = ["免费", "签约", "VIP"]
STATUSES = ["连载中", "已完结"]

# 站点把长期不更新的连载书标为「断更」。这个状态不描述作品本身，
# 只描述更新行为，且在册作品在语义上仍是连载中，故一并归入。
# status 为空的是已下架但 id 未失效的作品，整行剔除，见 DROP_RULES。
STATUS_MAP = {"断更": "连载中", "连载中": "连载中", "已完结": "已完结"}

# 上游把分类写成「X类」的残留共 4 条。先去掉后缀，若仍不命中 9 类，
# 再取前两字试一次；两次都不中即无处可归，整行剔除。
GENRE_SUFFIX = "类"

TAG_SEP = "|"

# 非法字符按 Unicode 大类判定，替换为普通空格：
#   Cc 控制符（含 \t \n \r）  Cf 格式符（零宽、BOM、软连字符、双向覆盖）
#   Co 私用区                   Cs 代理对        Cn 未分配
# 另把非 ASCII 的空白（NBSP、全角空格、em space 等 Zs）归一为普通空格：
# 它们看起来是空格却不是，会让 split / 检索 / 去重全部失效。
INVALID_CATEGORIES = frozenset({"Cc", "Cf", "Co", "Cs", "Cn"})
SPACE_CATEGORY = "Zs"

# 无封面时站点返回占位图而不是空值。文件名以 default 开头即视为无封面，
# 保留 URL 会让人以为封面存在（36,212 行命中，含大小写与 [1] 变体）。
COVER_PLACEHOLDER = "default"

# ---------------------------------------------------------------- 行级剔除
# 剔除的是「这一行不能作为有效记录」，不是「这本书不存在」。三类互不重叠，
# 判定见 build_csv.drop_mask，理由见 DROP_RULES。
#
# 书名必须含文字：任一字母、汉字、假名或注音都算。纯数字（'3'、'2050'）、
# 纯符号（'---'、'？？？？？？'）、数字与符号混合（'1,000'、'1/1'）、
# 罗马数字（'ⅩⅩ'）都不算。
#
# 但无文字标题不等于脏数据：100 行里 44 行有实质内容，最典型的是「0.5」，
# 45.9 万字、6.8 万点击、1,190 收藏，作者只是用符号作标题。删掉会损失真实
# 市场信号。因此只在「也没有任何内容」时剔除，判据是下列两条阈值同时不满足。
EMPTY_WORDS = 10_000
EMPTY_CLICKS = 1_000


# 判据是 str.isalpha 而非正则：它的边界恰好是 Unicode L 类，与 schema.sql 里
# 的 \p{L} 同义。不用 \w——那会把罗马数字（Nl）与连接符（Pc）也算作有效文字。
def has_text_char(value: str) -> bool:
    return any(ch.isalpha() for ch in value)

DROP_RULES = {
    "negative_likes": "收藏为负。站点计数下溢，原值不可信且无法修正出真值。",
    "title_without_text": (
        f"书名不含文字字符，且字数 ≤ {EMPTY_WORDS}、点击 ≤ {EMPTY_CLICKS}，"
        "既无法检索也无内容可依。"
    ),
    "all_zero": "字数、人气、收藏、赞同时为 0，没有任何可观测信号。",
    "status_missing": (
        "status 为空。作品已下架但 id 未失效，数值是下架前快照，"
        "不构成当前可读供给。"
    ),
    "genre_unresolved": "分类不在 9 类内，去后缀与前两字都无法归入，无处可归。",
}

# ---------------------------------------------------------------- 列定义
# (列名, dtype, nullable, 来源列, 说明)
COLUMNS: list[tuple[str, str, bool, str, str]] = [
    ("id", "int64", False, "nid", "站点作品编号，自增主键，存在空洞"),
    ("title", "string", False, "novel_title", "书名"),
    ("author", "string", False, "author", "作者名，平台内唯一且不可改"),
    ("genre", "string", False, "genre", "分类，9 类；无法归入的行已剔除"),
    ("price_type", "string", False, "price_type", "付费类型"),
    ("status", "string", False, "status", "连载状态，断更已并入连载中；空状态行已剔除"),
    ("contest", "string", True, "contest", "参赛征文；空表示未参加"),
    ("words", "int64", False, "word_num", "字数"),
    ("clicks", "int64", False, "click_num", "人气，累计浏览"),
    ("likes", "int64", False, "like_num", "收藏；负值行已整行剔除"),
    ("praises", "int64", False, "praise_num", "赞"),
    ("featured", "int8", False, "banner", "站方运营位，0/1，非质量分"),
    ("cover_url", "string", True, "cover", "封面地址"),
    ("updated_at", "string", False, "last_update", "最后更新时间，ISO 8601 无时区"),
    ("tags", "string", True, "tags", "标签，| 分隔，最多 5 个"),
]

COLUMN_NAMES = [c[0] for c in COLUMNS]
SOURCE_FIELDS = [c[3] for c in COLUMNS]

CSV_KWARGS = dict(index=False, encoding="utf-8", lineterminator="\n", na_rep="")

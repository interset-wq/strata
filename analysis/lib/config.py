"""路径、来源、列定义与清洗规则。

对字段语义的断言只写在这一处，构建与校验共用。
"""

from __future__ import annotations

from pathlib import Path

from lib import paths

ROOT = paths.ROOT
DATA_DIR = paths.DATA_DIR
ARCHIVE = paths.ARCHIVE
EXTRACT_DIR = paths.EXTRACT_DIR
JSONL_DIR = paths.JSONL_DIR
# 月榜遗漏书补充（E.14，2026-11-19）：月榜上榜但缺失于 5 月快照的 108 本，
# 由 analysis/fetchers/build_rank_missing_supplement.py 产出；字段与 meta jsonl
# 同构（15 字段 + 溯源键）。计数为 2026-11 App API 当期值，晚于快照上界。
RANK_MISSING = paths.ROOT.parent / "dataset" / "rank_missing.jsonl"
# 征文清单补采（harvest_contest.py，App API + mobile web）：库外新书按 tag
# 并入。分析口径只放行 E.34 中短篇 union 的 26 个赛事 tag（tag 集合真源为
# `analysis/lib/contest_scope.py::short_medium_tags()`，读 anchors/contest_short_medium.json），
# 长篇赛道（793 等）与春征（789）留档在 dataset 但不进分析口径。
# 字段 15 项同构 + 溯源键；计数为 2026-11 当期值，晚于 2026-05-03 快照上界。
CONTEST_NEW = paths.ROOT.parent / "dataset" / "contest_new.jsonl"
OUT_DIR = paths.OUT_DIR
CSV_FILE = paths.CSV_FILE
SQL_FILE = paths.SQL_FILE
MANIFEST = paths.MANIFEST

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

# 上游把分类写成「X类」的残留共 4 条。这是 2010-04-05 改版时的旧分类体系
#（15 类：热血/冒险/运动/魔幻/武侠/校园/同人/搞笑/爱情/温情/推理/机战/
# 科幻/惊悚/社会），后被现行 9 类取代，少数旧记录未迁移。依据见
# analysis/references/sfacg-pku-chronicle.md（北大《中国网络文学编年简史》）。
# 先去掉后缀，若仍不命中 9 类，再取前两字试一次；两次都不中即无处可归，
# 整行剔除（实测 2 行：冒险类、爱情类）。
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

# 全部非空封面共用此前缀（实测 210,963 行无一例外，其后是 YYYY/MM/ 或直接
# 文件名）。存相对路径：前缀对每行相同，没有信息量，还原时拼回即可。
COVER_BASE = "http://rs.sfacg.com/web/novel/images/NovelCover/Big/"

# ---------------------------------------------------------------- 行级剔除
# 剔除的是「这一行不能作为有效记录」，不是「这本书不存在」。各类互不重叠，
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

# 正版日轻（引进版权方账号）的 nid 不遵守 id 递增：站点早期存在大量盗版日轻，
# 正版上架时复用了同标题盗版条目的旧 id，因此 id 反映的是盗版条目的创建时间
# 而不是该正版书的创建时间。授权到期还会让在册状态与内容失效。
# 四个作者名都是版权方账号（天闻角川、HJ文库等），不是自然人作者；
# 正版日轻一定有 banner（本批实测 47/47 命中），但授权到期可能撤下 banner，
# 故以作者集合为剔除判据，banner 作交叉验证，不写进条件。
LICENSED_LN_AUTHORS = frozenset({"天闻角川", "天闻角川2号机", "丸山黄金", "HJ文库"})


# 判据是 str.isalpha 而非正则：它的边界恰好是 Unicode L 类，与 schema.sql 里
# 的 \p{L} 同义。不用 \w——那会把罗马数字（Nl）与连接符（Pc）也算作有效文字。
def has_text_char(value: str) -> bool:
    return any(ch.isalpha() for ch in value)

DROP_RULES = {
    "negative_favs": "收藏为负。站点计数下溢，原值不可信且无法修正出真值。",
    "title_without_text": (
        f"书名不含文字字符，且字数 ≤ {EMPTY_WORDS}、点击 ≤ {EMPTY_CLICKS}，"
        "既无法检索也无内容可依。"
    ),
    "all_zero": "字数、人气、收藏、赞同时为 0，没有任何可观测信号。",
    "status_missing": (
        "status 为空。作品已下架但详情页仍保留，数值是下架前快照，"
        "不构成当前可读供给。"
    ),
    "genre_unresolved": (
        "分类不在现行 9 类内，去后缀与前两字都无法归入。属 2010 年改版前"
        "15 类旧分类体系的未迁移记录（冒险类、爱情类），非站点 bug 或测试操作；"
        "现行货架无对应入口，对读者无检索价值，故剔除。"
    ),
    "licensed_light_novel": (
        "正版日轻（作者为版权方账号 天闻角川 / 天闻角川2号机 / 丸山黄金 / HJ文库）。"
        "其 nid 复用同标题盗版日轻的旧 id，不遵守 id 递增，会污染定年、世代与"
        "头部统计；授权到期亦可使在册状态失效。本批 47 行全部命中 banner=1。"
    ),
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
    ("favs", "int64", False, "like_num", "收藏数；负值行已整行剔除"),
    ("praises", "int64", False, "praise_num", "赞"),
    ("featured", "int8", False, "banner", "站方运营位，0/1，非质量分"),
    ("cover_url", "string", True, "cover", "封面路径，省略公共前缀 COVER_BASE；空表示无封面"),
    ("updated_at", "string", False, "last_update", "最后更新时间，ISO 8601 无时区"),
    ("tags", "string", True, "tags", "标签，| 分隔，最多 5 个"),
]

COLUMN_NAMES = [c[0] for c in COLUMNS]
SOURCE_FIELDS = [c[3] for c in COLUMNS]

CSV_KWARGS = dict(index=False, encoding="utf-8", lineterminator="\n", na_rep="")

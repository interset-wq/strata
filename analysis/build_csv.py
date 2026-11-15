"""novel_hub 的原始 jsonl → 单张宽表 CSV。

上游的 jsonl 是爬虫直接产物，同一 nid 会因分片重叠出现多次，且字段名是
抓取脚本的内部命名。本脚本做六件事，然后产出唯一一份 CSV：

1. 按 nid 去重，保留最后一条（后抓的覆盖先抓的，实测 click 只增不减）
2. 列重命名，去掉 ``_num`` / ``novel_`` 这类来源痕迹
3. 枚举转真值，并把「断更」并入「连载中」
4. 文本归一：非法字符换空格、非 ASCII 空白归一、压缩连续空格、去首尾空白
5. 清洗：占位封面置空、分类后缀归一、标签去重
6. 剔除整行：负收藏、全零、无文字标题且无内容（见 ``config.DROP_RULES``）

列表字段不展开，标签以 ``|`` 连接在同一行内。

用法：uv run python analysis/build_csv.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import validate

MULTISPACE = re.compile(r" {2,}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 读取
def load_jsonl(directory: Path) -> tuple[dict[int, dict], dict]:
    """按文件名顺序读入，同 nid 后者覆盖前者。"""
    files = sorted(directory.glob(C.SOURCE["glob"]))
    if not files:
        raise SystemExit(f"{directory} 下没有 {C.SOURCE['glob']}")

    records: dict[int, dict] = {}
    lines = 0
    for path in files:
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                lines += 1
                row = json.loads(raw)
                records[int(row["nid"])] = row
    stats = {
        "files": len(files),
        "lines": lines,
        "duplicate_rows": lines - len(records),
    }
    return records, stats


def check_fields(records: dict[int, dict]) -> None:
    """字段集合必须与 COLUMNS 的声明一致，防止上游悄悄加列。"""
    for nid, row in records.items():
        missing = [f for f in C.SOURCE_FIELDS if f not in row]
        if missing:
            raise SystemExit(f"nid {nid} 缺少字段 {missing}")


# ---------------------------------------------------------------- 文本归一
def normalise(value: str) -> tuple[str, int]:
    """非法字符换空格，非 ASCII 空白归一并压缩，最后去首尾空白。"""
    out: list[str] = []
    replaced = 0
    for ch in value:
        cat = unicodedata.category(ch)
        if cat in C.INVALID_CATEGORIES:
            out.append(" ")
            replaced += 1
        elif cat == C.SPACE_CATEGORY and ch != " ":
            out.append(" ")
            replaced += 1
        else:
            out.append(ch)
    return MULTISPACE.sub(" ", "".join(out)).strip(), replaced


def _norm(value: str | None, field: str, tally: dict) -> str:
    raw = value or ""
    cleaned, replaced = normalise(raw)
    if replaced or cleaned != raw:
        entry = tally["text"].setdefault(field, {"rows": 0, "chars": 0})
        entry["rows"] += 1
        entry["chars"] += replaced
    return cleaned


# ---------------------------------------------------------------- 清洗
def clean_status(value: str | None, tally: dict) -> str | None:
    """归一到连载中/已完结。空状态是已下架作品，返回 None 由调用方剔除。"""
    if value is None:
        tally["status_missing"] += 1
        return None
    if value not in C.STATUS_MAP:
        raise SystemExit(f"出现未登记的状态值 {value!r}")
    if value == "断更":
        tally["status_dead_to_ongoing"] += 1
    return C.STATUS_MAP[value]


def clean_genre(value: str, tally: dict, fixes: list) -> str | None:
    """先去掉「类」后缀，再取前两字试一次；都不中即无处可归，返回 None。"""
    if value in C.GENRES:
        return value
    bare = value.removesuffix(C.GENRE_SUFFIX)
    for cand in (bare, bare[:2]):
        if cand in C.GENRES:
            tally["genre_relabelled"] += 1
            fixes.append(f"{value} → {cand}")
            return cand
    tally["genre_unresolved"] += 1
    fixes.append(f"{value} → 剔除")
    return None


def clean_tags(value: list, tally: dict) -> str:
    seen: list[str] = []
    for tag in value:
        cleaned = _norm(tag, "tags", tally)
        if not cleaned:
            tally["tags_dropped"] += 1
        elif cleaned not in seen:
            seen.append(cleaned)
        else:
            tally["tags_deduplicated"] += 1
    return C.TAG_SEP.join(seen)


def clean_row(row: dict, tally: dict, genre_fixes: list) -> dict:
    for col in ("word_num", "click_num", "praise_num", "like_num"):
        tally[f"{col}_zero"] += int(row[col]) == 0

    cover = _norm(row["cover"], "cover_url", tally)
    if cover and cover.rsplit("/", 1)[-1].lower().startswith(C.COVER_PLACEHOLDER):
        tally["cover_placeholder_nulled"] += 1
        cover = None
    elif cover and cover.startswith(C.COVER_BASE):
        cover = cover[len(C.COVER_BASE):]

    status = _norm(row["status"], "status", tally)
    return {
        "id": int(row["nid"]),
        "title": _norm(row["novel_title"], "title", tally),
        "author": _norm(row["author"], "author", tally),
        "genre": clean_genre(_norm(row["genre"], "genre", tally), tally, genre_fixes),
        "price_type": _norm(row["price_type"], "price_type", tally),
        "status": clean_status(status or None, tally),
        "contest": _norm(row["contest"], "contest", tally),
        "words": int(row["word_num"]),
        "clicks": int(row["click_num"]),
        "favs": int(row["like_num"]),
        "praises": int(row["praise_num"]),
        "featured": int(bool(row["banner"])),
        "cover_url": cover,
        "updated_at": _norm(row["last_update"], "updated_at", tally).replace(" ", "T"),
        "tags": clean_tags(row["tags"], tally),
    }


def dedup_covers(df: pd.DataFrame, tally: dict) -> pd.DataFrame:
    """修复 novel_hub 爬虫的选择器缺陷：同一封面文件挂在多本书上。

    缺陷机制：爬虫在详情页抓到了 id 更大的某本书的封面，因此一个共用组内
    只有 id 最大者可能是属主——其余成员的封面时间戳全部晚于自身创建
    （实测组内非属主的 |封面时间戳 − 定年| 中位 348 天，属主 −11 天，
    与唯一封面分布逐分位一致，吻合率 89.8% vs 19.5%，见 analysis/eras.py）。

    处置：组内保留 id 最大者，其余置空。属主判定不依赖时间戳（时间戳只
    用于验证规则），规则本身是纯 id 判据，可随构建复算。
    """
    dup = df["cover_url"].notna() & df["cover_url"].duplicated(keep=False)
    if not dup.any():
        return df
    sub = df[dup]
    owners = sub.groupby("cover_url")["id"].idxmax()
    losers = sub.index.difference(owners)
    tally["cover_shared_bugged"] += len(losers)
    df.loc[losers, "cover_url"] = pd.NA
    return df


def drop_mask(df: pd.DataFrame) -> dict[str, pd.Series]:
    """五类不可用的行，判定在归一之后，互不重叠。"""
    empty = (df["words"] <= C.EMPTY_WORDS) & (df["clicks"] <= C.EMPTY_CLICKS)
    return {
        "negative_favs": df["favs"] < 0,
        "title_without_text": ~df["title"].fillna("").map(C.has_text_char) & empty,
        "all_zero": (df["words"] == 0) & (df["clicks"] == 0),
        "status_missing": df["status"].isna(),
        "genre_unresolved": df["genre"].isna(),
    }


def build(records: dict[int, dict]) -> tuple[pd.DataFrame, dict, list, dict]:
    tally = {
        "text": {},
        "status_missing": 0,
        "status_dead_to_ongoing": 0,
        "genre_relabelled": 0,
        "genre_unresolved": 0,
        "cover_placeholder_nulled": 0,
        "cover_shared_bugged": 0,
        "tags_deduplicated": 0,
        "tags_dropped": 0,
        "word_num_zero": 0,
        "click_num_zero": 0,
        "praise_num_zero": 0,
        "like_num_zero": 0,
    }
    genre_fixes: list[str] = []
    rows = [clean_row(records[nid], tally, genre_fixes) for nid in sorted(records)]
    df = pd.DataFrame(rows, columns=C.COLUMN_NAMES)

    for name, dtype, _n, _src, _desc in C.COLUMNS:
        df[name] = pd.array(df[name], dtype="Int64") if dtype == "Int64" else df[name].astype(dtype)

    masks = drop_mask(df)
    dropped = (
        pd.concat(masks, axis=1).any(axis=1)
        if masks
        else pd.Series(False, index=df.index)
    )
    dropped_info = {
        "rows": int(dropped.sum()),
        "rules": {k: int(v.sum()) for k, v in masks.items()},
        "ids": df.loc[dropped, "id"].tolist(),
    }
    df = df.loc[~dropped].reset_index(drop=True)
    # 行级剔除之后修复封面：被剔除的行不参与属主判定（其封面同为错值）
    df = dedup_covers(df, tally)
    return df, tally, genre_fixes, dropped_info


# ---------------------------------------------------------------- DDL
DUCK_TYPE = {"int64": "BIGINT", "int8": "TINYINT", "Int64": "BIGINT", "string": "VARCHAR"}


def write_ddl(path: Path) -> None:
    lines = []
    for name, dtype, nullable, _src, _desc in C.COLUMNS:
        parts = [f"  {name:<13} {DUCK_TYPE[dtype]}"]
        if not nullable:
            parts.append("NOT NULL")
        if name == "id":
            parts.append("PRIMARY KEY")
        lines.append(" ".join(parts))
    checks = [
        f"status IN ({', '.join(repr(s) for s in C.STATUSES)})",
        f"genre IN ({', '.join(repr(g) for g in C.GENRES)})",
        f"price_type IN ({', '.join(repr(p) for p in C.PRICE_TYPES)})",
        "featured IN (0, 1)",
        "words >= 0",
        "clicks >= 0",
        "favs >= 0",
        "praises >= 0",
        # 至少一个可观测信号，与 drop_mask 的 all_zero 对应
        "words > 0 OR clicks > 0",
        # 与 drop_mask 对应：书名要么含文字，要么有内容——无文字标题的 100 行
        # 里有 44 行是真实作品。用 \p{L} 而非 [:alpha:]，后者在 RE2 里只覆盖
        # ASCII，会把全部中文书名判成空。
        r"length(regexp_replace(title, '[^\p{L}]', '', 'g')) > 0"
        f" OR words > {C.EMPTY_WORDS} OR clicks > {C.EMPTY_CLICKS}",
    ]
    lines.extend(f"  CHECK ({c})" for c in checks)
    body = ",\n".join(lines)
    header = """-- 由 analysis/build_csv.py 生成，勿手改。
-- 行数与清洗明细见 manifest.json，列语义见 config.COLUMNS。
--
-- CSV 不携带约束，本文件是唯一约束载体，DuckDB 导入时生效。
-- 用法（在 out/ 目录下）：duckdb strata.db ".read schema.sql"

"""
    path.write_text(
        header
        + f"CREATE OR REPLACE TABLE novels (\n{body}\n);\n\n"
        + "COPY novels FROM 'novels.csv' (HEADER, NULL '');\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------- 主流程
def main() -> int:
    if not C.JSONL_DIR.exists():
        raise SystemExit(
            f"缺少 jsonl 目录 {C.JSONL_DIR}\n"
            "先运行：uv run --extra archive python analysis/prepare.py"
        )

    records, load_stats = load_jsonl(C.JSONL_DIR)
    check_fields(records)
    df, tally, genre_fixes, dropped = build(records)

    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = C.OUT_DIR / "novels.tmp.csv"
    df.to_csv(tmp, **C.CSV_KWARGS)

    errors = validate.check_file(tmp)
    if errors:
        print(f"校验失败，{len(errors)} 项；未替换 {C.CSV_FILE.name}")
        for e in errors:
            print("  -", e)
        # 保留失败现场供排查，下次构建覆盖
        os.replace(tmp, C.OUT_DIR / "novels.invalid.csv")
        return 1

    os.replace(tmp, C.CSV_FILE)
    write_ddl(C.SQL_FILE)

    manifest = {
        "dataset": "novel_hub",
        "source": C.SOURCE,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "table": "novels",
        "rows": int(len(df)),
        "dropped": {
            "rows": dropped["rows"],
            "rules": {
                k: {"rows": v, "why": C.DROP_RULES[k]} for k, v in dropped["rules"].items()
            },
            "ids": dropped["ids"],
        },
        "file": {
            "name": C.CSV_FILE.name,
            "bytes": C.CSV_FILE.stat().st_size,
            "sha256": sha256(C.CSV_FILE),
        },
        "columns": {
            name: {"from": src, "dtype": dtype, "nullable": nullable, "desc": desc}
            for name, dtype, nullable, src, desc in C.COLUMNS
        },
        "cleaning": {
            "deduplicate": {
                "rule": "同 nid 保留最后一条（文件顺序即抓取顺序）",
                **load_stats,
            },
            "text": {
                "rule": (
                    "Cc/Cf/Co/Cs/Cn 与非 ASCII 空白替换为空格，"
                    "压缩连续空格后去首尾空白"
                ),
                "fields": tally["text"],
            },
            "status": {
                "rule": "断更并入连载中；空状态视为已下架，整行剔除",
                "dead_to_ongoing": tally["status_dead_to_ongoing"],
                "missing_dropped": tally["status_missing"],
            },
            "genre": {
                "rule": "去「类」后缀，再取前两字；都不中即剔除",
                "relabelled": tally["genre_relabelled"],
                "unresolved_dropped": tally["genre_unresolved"],
                "detail": genre_fixes,
            },
            "favs": {"negative_rows_dropped": dropped["rules"]["negative_favs"]},
            "cover": {
                "rule": (
                    f"文件名以 {C.COVER_PLACEHOLDER} 开头视为无封面；"
                    "其余省略公共前缀 COVER_BASE；爬虫缺陷导致的共用封面"
                    "保留组内 id 最大者（属主），其余置空"
                ),
                "placeholder_nulled": tally["cover_placeholder_nulled"],
                "shared_bugged_nulled": tally["cover_shared_bugged"],
            },
            "tags": {
                "deduplicated": tally["tags_deduplicated"],
                "dropped_empty": tally["tags_dropped"],
            },
        },
        "zeros": {
            "words": tally["word_num_zero"],
            "clicks": tally["click_num_zero"],
            "favs": tally["like_num_zero"],
            "praises": tally["praise_num_zero"],
        },
        "distribution": {
            "status": {k: int(v) for k, v in df["status"].value_counts().items()},
            "genre": {k: int(v) for k, v in df["genre"].value_counts().items()},
            "price_type": {
                k: int(v) for k, v in df["price_type"].value_counts().items()
            },
            "featured": {str(k): int(v) for k, v in df["featured"].value_counts().items()},
        },
        "contract": {
            "encoding": "utf-8",
            "bom": False,
            "line_ending": "LF",
            "null": "空串",
            "datetime": "ISO 8601，无时区",
            "list": f"tags 以 {C.TAG_SEP} 连接，不展开成行",
            "text": "无控制符、无零宽字符、无非 ASCII 空白、无首尾空白、无连续空格",
        },
    }
    C.MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"jsonl {load_stats['files']} 个文件 / {load_stats['lines']} 行"
        f" → 去重 {load_stats['duplicate_rows']} 行"
        f" → 剔除 {dropped['rows']} 行 {dropped['rules']}"
    )
    print(f"novels.csv  {len(df)} 行  {C.CSV_FILE.stat().st_size / 1e6:.2f} MB")
    print(f"  状态   {manifest['distribution']['status']}")
    print(f"  文本   {tally['text']}")
    print(f"已发布 {C.CSV_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

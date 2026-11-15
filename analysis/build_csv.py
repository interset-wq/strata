"""novel_hub 的原始 jsonl → 单张宽表 CSV。

上游的 jsonl 是爬虫直接产物，同一 nid 会因分片重叠出现多次，且字段名是
抓取脚本的内部命名。本脚本做四件事，然后产出唯一一份 CSV：

1. 按 nid 去重，保留最后一条（后抓的覆盖先抓的，实测 click 只增不减）
2. 列重命名，去掉 ``_num`` / ``novel_`` 这类来源痕迹
3. 枚举转真值，并把「断更」并入「连载中」
4. 清洗：负收藏置空、分类后缀归一、标签去重

列表字段不展开，标签以 ``|`` 连接在同一行内。

用法：uv run python analysis/build_csv.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import validate


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


# ---------------------------------------------------------------- 清洗
def clean_status(value: str | None, tally: dict) -> str:
    if value not in C.STATUS_MAP:
        raise SystemExit(f"出现未登记的状态值 {value!r}")
    if value is None:
        tally["status_null_to_unknown"] += 1
    elif value == "断更":
        tally["status_dead_to_ongoing"] += 1
    return C.STATUS_MAP[value]


def clean_genre(value: str, tally: dict, fixes: list) -> str:
    if value in C.GENRES:
        return value
    bare = value.removesuffix(C.GENRE_SUFFIX)
    target = bare if bare in C.GENRES else C.UNCLASSIFIED
    tally["genre_relabelled"] += 1
    fixes.append(f"{value} → {target}")
    return target


def clean_tags(value: list, tally: dict) -> str:
    seen: list[str] = []
    for tag in value:
        tag = tag.strip()
        if tag and tag not in seen:
            seen.append(tag)
    if len(seen) != len(value):
        tally["tags_deduplicated"] += 1
    return C.TAG_SEP.join(seen)


def clean_row(row: dict, tally: dict, genre_fixes: list) -> dict:
    likes = int(row["like_num"])
    if likes < 0:
        tally["likes_negative_nulled"] += 1
        likes = None
    else:
        tally["likes_zero"] += likes == 0

    for col in ("word_num", "click_num", "praise_num"):
        tally[f"{col}_zero"] += int(row[col]) == 0

    cover = row["cover"]
    if isinstance(cover, str) and cover.strip():
        basename = cover.rsplit("/", 1)[-1].lower()
        if basename.startswith(C.COVER_PLACEHOLDER):
            tally["cover_placeholder_nulled"] += 1
            cover = None
    return {
        "id": int(row["nid"]),
        "title": row["novel_title"].strip(),
        "author": row["author"].strip(),
        "genre": clean_genre(row["genre"], tally, genre_fixes),
        "price_type": row["price_type"],
        "status": clean_status(row["status"], tally),
        "contest": row["contest"].strip(),
        "words": int(row["word_num"]),
        "clicks": int(row["click_num"]),
        "likes": likes,
        "praises": int(row["praise_num"]),
        "featured": int(bool(row["banner"])),
        "cover_url": cover.strip() if isinstance(cover, str) else None,
        "updated_at": row["last_update"].replace(" ", "T"),
        "tags": clean_tags(row["tags"], tally),
    }


def build(records: dict[int, dict]) -> tuple[pd.DataFrame, dict, list]:
    tally = {
        "status_null_to_unknown": 0,
        "status_dead_to_ongoing": 0,
        "genre_relabelled": 0,
        "likes_negative_nulled": 0,
        "tags_deduplicated": 0,
        "cover_placeholder_nulled": 0,
        "word_num_zero": 0,
        "click_num_zero": 0,
        "praise_num_zero": 0,
        "likes_zero": 0,
    }
    genre_fixes: list[str] = []
    rows = [
        clean_row(records[nid], tally, genre_fixes)
        for nid in sorted(records)
    ]
    df = pd.DataFrame(rows, columns=C.COLUMN_NAMES)

    for name, dtype, _n, _src, _desc in C.COLUMNS:
        if dtype == "Int64":
            df[name] = pd.array(df[name], dtype="Int64")
        elif dtype == "string":
            df[name] = df[name].astype("string")
        else:
            df[name] = df[name].astype(dtype)
    return df, tally, genre_fixes


# ---------------------------------------------------------------- DDL
DUCK_TYPE = {"int64": "BIGINT", "int8": "TINYINT", "Int64": "BIGINT", "string": "VARCHAR"}


def write_ddl(path: Path) -> None:
    cols = C.COLUMNS
    lines = []
    for name, dtype, nullable, _src, _desc in cols:
        parts = [f"  {name:<13} {DUCK_TYPE[dtype]}"]
        if not nullable:
            parts.append("NOT NULL")
        if name == "id":
            parts.append("PRIMARY KEY")
        lines.append(" ".join(parts))
    checks = [
        f"status IN ({', '.join(repr(s) for s in C.STATUSES)})",
        f"genre IN ({', '.join(repr(g) for g in C.GENRES + [C.UNCLASSIFIED])})",
        f"price_type IN ({', '.join(repr(p) for p in C.PRICE_TYPES)})",
        "featured IN (0, 1)",
        "words >= 0",
        "clicks >= 0",
        "praises >= 0",
        "likes IS NULL OR likes >= 0",
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
            f"缺少 jsonl 目录 {C.JSONL_DIR}\n先运行：uv run --extra archive python analysis/prepare.py"
        )

    records, load_stats = load_jsonl(C.JSONL_DIR)
    check_fields(records)
    df, tally, genre_fixes = build(records)

    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = C.OUT_DIR / "novels.tmp.csv"
    df.to_csv(tmp, **C.CSV_KWARGS)

    errors = validate.check_file(tmp)
    if errors:
        print(f"校验失败，{len(errors)} 项；未替换 {C.CSV_FILE.name}")
        for e in errors:
            print("  -", e)
        tmp.unlink()
        return 1

    if C.CSV_FILE.exists():
        C.CSV_FILE.unlink()
    shutil.move(str(tmp), str(C.CSV_FILE))
    write_ddl(C.SQL_FILE)

    manifest = {
        "dataset": "novel_hub",
        "source": C.SOURCE,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "table": "novels",
        "rows": int(len(df)),
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
            "status": {
                "rule": "断更并入连载中；null 记为未知",
                "dead_to_ongoing": tally["status_dead_to_ongoing"],
                "null_to_unknown": tally["status_null_to_unknown"],
            },
            "genre": {"relabelled": tally["genre_relabelled"], "detail": genre_fixes},
            "likes": {"negative_nulled": tally["likes_negative_nulled"]},
            "cover": {
                "rule": f'文件名以 {C.COVER_PLACEHOLDER} 开头视为无封面',
                "placeholder_nulled": tally["cover_placeholder_nulled"],
            },
            "tags": {"deduplicated_rows": tally["tags_deduplicated"]},
        },
        "zeros": {
            "words": tally["word_num_zero"],
            "clicks": tally["click_num_zero"],
            "likes": tally["likes_zero"],
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
        },
    }
    C.MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"jsonl {load_stats['files']} 个文件 / {load_stats['lines']} 行"
          f" → 去重 {load_stats['duplicate_rows']} 行")
    print(f"novels.csv  {len(df)} 行  {C.CSV_FILE.stat().st_size / 1e6:.2f} MB")
    print(f"  状态   {manifest['distribution']['status']}")
    print(f"  分类   {manifest['distribution']['genre']}")
    print(f"已发布 {C.CSV_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

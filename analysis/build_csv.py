"""novel_hub 源库 → 规范化 CSV + 约束 DDL。

产出不是「把 sqlite 导出来」，而是一份可被 pandas 直接消费、且关系约束
可执行的只读快照：

- 每张表只表达一个实体，非键列完全依赖主键
- 枚举值外置为码表，novel 只存外键，不重复字面值
- 缺失值统一为空串，整数列不出现 ``.0``
- 约束写在 ``out/schema.sql``，CSV/Parquet 本身不携带约束

先写临时目录，校验通过后替换 ``out/csv``；失败时上一版产出保持可用。

用法：uv run python analysis/build_csv.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C
import validate

# DDL 建表顺序：父表在前，保证外键可解析
TABLE_ORDER = ["author", "tag", "contest", "genre", "ptype", "status", "novel", "novel_tag"]

DUCK_TYPE = {"int64": "BIGINT", "int8": "TINYINT", "Int64": "BIGINT", "string": "VARCHAR"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_snapshot(con: sqlite3.Connection) -> str:
    """快照时点取自上游 db_update，全表同一值。"""
    row = con.execute("select max(db_update) from novel").fetchone()
    if not row or not row[0]:
        raise RuntimeError("novel.db_update 为空，无法确定快照时点")
    return str(row[0])[:10]


# ---------------------------------------------------------------- 抽取
def build_novel(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql(
        """
        select
            id                                                as nid,
            trim(title)                                       as title,
            author_id,
            genre                                             as genre_id,
            ptype                                             as ptype_id,
            status                                            as status_id,
            contest_id,
            word_num,
            click_num,
            case when like_num < 0 then null else like_num end as like_num,
            praise_num,
            case when has_banner then 1 else 0 end             as has_banner,
            nullif(trim(cover), '')                            as cover,
            strftime('%Y-%m-%dT%H:%M:%S', last_update)        as last_update
        from novel
        order by id
        """,
        con,
    )
    df["like_num"] = df["like_num"].astype("Int64")
    df["contest_id"] = df["contest_id"].astype("Int64")
    for col in ("genre_id", "ptype_id", "status_id", "has_banner"):
        df[col] = df[col].astype("int8")
    return df[C.schema_columns("novel")]


def build_dim(con: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql(
        f"select id, trim(name) as name from {table} order by id", con
    ).astype({"id": "int64", "name": "string"})


def build_novel_tag(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql(
        "select novel_id, tag_id from noveltaglink order by novel_id, tag_id", con
    ).astype({"novel_id": "int64", "tag_id": "int64"})


def build_code_tables() -> dict[str, pd.DataFrame]:
    return {
        "genre": pd.DataFrame(
            [{"id": k, "name": v} for k, v in sorted(C.GENRE.items())]
        ).astype({"id": "int8", "name": "string"}),
        "ptype": pd.DataFrame(
            [{"id": k, "name": v} for k, v in sorted(C.PTYPE.items())]
        ).astype({"id": "int8", "name": "string"}),
        "status": pd.DataFrame(
            [
                {"id": k, "label": label, "outcome": outcome}
                for k, (label, outcome) in sorted(C.STATUS.items())
            ]
        ).astype({"id": "int8", "label": "string", "outcome": "string"}),
    }


def build_flat(
    novel: pd.DataFrame,
    dims: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """派生宽表：只为人读与快速探索，不作权威数据。"""
    tag = dims["tag"]
    link = dims["novel_tag"]
    tag_names = (
        link.merge(tag, left_on="tag_id", right_on="id", how="left")
        .sort_values(["novel_id", "tag_id"])
        .groupby("novel_id")["name"]
        .agg("|".join)
    )
    flat = novel.copy()
    for src, dim, col in (
        ("author_id", "author", "author"),
        ("genre_id", "genre", "genre"),
        ("ptype_id", "ptype", "ptype"),
        ("contest_id", "contest", "contest"),
    ):
        lookup = dims[dim].set_index("id")["name"]
        flat[col] = flat[src].map(lookup)
    flat["status"] = flat["status_id"].map({k: v[0] for k, v in C.STATUS.items()})
    flat["outcome"] = flat["status_id"].map({k: v[1] for k, v in C.STATUS.items()})
    flat["tags"] = flat["nid"].map(tag_names).fillna("")
    return flat[C.FLAT_COLUMNS]


# ---------------------------------------------------------------- DDL
TABLE_NOTE = {
    "author": "作者维表；name 平台内唯一且不可修改",
    "tag": "标签维表",
    "contest": "征文维表",
    "genre": "分类码表，取值见 config.GENRE",
    "ptype": "发布类型码表，取值见 config.PTYPE",
    "status": "状态码表，outcome 为机器可读结局",
    "novel": "作品主表，一行一本；计数为快照时点累计值",
    "novel_tag": "作品与标签的多对多关联",
}


def _checks(table: str) -> list[str]:
    if table != "novel":
        return []
    allowed = lambda d: ", ".join(str(k) for k in sorted(d))  # noqa: E731
    return [
        *(f"{c} >= 0" for c in C.NON_NEGATIVE),
        "like_num IS NULL OR like_num >= 0",
        "has_banner IN (0, 1)",
        f"genre_id IN ({allowed(C.GENRE)})",
        f"ptype_id IN ({allowed(C.PTYPE)})",
        f"status_id IN ({allowed(C.STATUS)})",
    ]


def _ddl(table: str) -> str:
    cols = C.SCHEMA[table]
    column_sql: list[str] = []
    constraint_sql: list[str] = []
    pk_cols = [c[0] for c in cols if "PK" in c[3].split(",")]
    composite_pk = pk_cols if len(pk_cols) > 1 else []

    for col, dtype, nullable, key, _desc in cols:
        parts = [f"  {col:<13} {DUCK_TYPE[dtype]}"]
        if not nullable:
            parts.append("NOT NULL")
        if key == "PK":
            parts.append("PRIMARY KEY")
        elif "UNIQUE" in key.split(","):
            parts.append("UNIQUE")
        column_sql.append(" ".join(parts))

    if composite_pk:
        constraint_sql.append(f"  PRIMARY KEY ({', '.join(composite_pk)})")
    for col, _d, _n, key, _desc in cols:
        for token in key.split(","):
            token = token.strip()
            if token.startswith("FK "):
                parent, parent_col = token[3:].split(".")
                constraint_sql.append(
                    f"  FOREIGN KEY ({col}) REFERENCES {parent}({parent_col})"
                )
    constraint_sql.extend(f"  CHECK ({c})" for c in _checks(table))

    body = ",\n".join(column_sql + constraint_sql)
    note = TABLE_NOTE[table]
    return f"-- {note}\nCREATE OR REPLACE TABLE {table} (\n{body}\n);\n"


def write_ddl(path: Path) -> None:
    header = """-- 由 analysis/build_csv.py 生成，勿手改。
-- 快照时点与行数见 manifest.json，列语义见 config.SCHEMA。
--
-- CSV 与 Parquet 都不携带约束，本文件是唯一约束载体。
-- PK / UNIQUE / NOT NULL / CHECK / FOREIGN KEY 在 DuckDB 导入时即生效。
-- validate.py 在发布前对 CSV 做同等校验，因为绕过 DDL 直接读 CSV 的
-- 消费方（pandas、BI 工具）不受约束保护。
--
-- 用法（在 out/ 目录下）：
--   duckdb strata.db ".read schema.sql"

"""
    body = "\n".join(_ddl(t) for t in TABLE_ORDER)
    loads = "\n".join(
        f"COPY {t} FROM 'csv/{t}.csv' (HEADER, NULL '');" for t in TABLE_ORDER
    )
    path.write_text(
        header + body + "\n-- 导入，父表在前\n" + loads + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------- 诊断
def anomalies(novel: pd.DataFrame, con: sqlite3.Connection) -> dict:
    pairs = con.execute(
        """
        select lower(name) k, group_concat(id || ':' || name, ' | ')
        from author group by lower(name) having count(*) > 1
        order by k
        """
    ).fetchall()
    return {
        "status_unknown": int((novel["status_id"] == 1).sum()),
        "genre_unclassified_nids": sorted(
            int(x) for x in novel.loc[novel["genre_id"] == 1, "nid"]
        ),
        "like_negative_nulled": int(novel["like_num"].isna().sum()),
        "cover_null": int(novel["cover"].isna().sum()),
        "contest_null": int(novel["contest_id"].isna().sum()),
        "placeholder_title_numeric": int(
            novel["title"].str.fullmatch(r"\d+").fillna(False).sum()
        ),
        "author_case_collisions": [f"{k}: {v}" for k, v in pairs],
    }


def zeros(novel: pd.DataFrame) -> dict:
    """计数为 0 是新建作品的真实观测值，保留，不视作缺失。"""
    return {
        col: int((novel[col] == 0).sum())
        for col in ("word_num", "click_num", "like_num", "praise_num")
    }


# ---------------------------------------------------------------- 主流程
def main() -> int:
    if not C.SOURCE_DB.exists():
        raise SystemExit(f"缺少源库 {C.SOURCE_DB}\n先运行：uv run python analysis/prepare.py")

    con = sqlite3.connect(f"file:{C.SOURCE_DB}?mode=ro", uri=True)
    snapshot = read_snapshot(con)

    novel = build_novel(con)
    dims = {
        "author": build_dim(con, "author"),
        "tag": build_dim(con, "tag"),
        "contest": build_dim(con, "contest"),
        "novel_tag": build_novel_tag(con),
        **build_code_tables(),
    }
    tables = {"novel": novel, **dims}
    flat = build_flat(novel, dims)

    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = C.OUT_DIR / "csv.tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()

    for name, df in tables.items():
        df.to_csv(tmp / f"{name}.csv", **C.CSV_KWARGS)
    flat.to_csv(tmp / "novels_flat.csv", **C.CSV_KWARGS)

    errors = validate.check_dir(tmp)
    if errors:
        print(f"校验失败，{len(errors)} 项；未替换 out/csv")
        for e in errors:
            print("  -", e)
        return 1

    if C.CSV_DIR.exists():
        shutil.rmtree(C.CSV_DIR)
    tmp.replace(C.CSV_DIR)
    write_ddl(C.SQL_FILE)

    files = {}
    for p in sorted(C.CSV_DIR.glob("*.csv")):
        files[p.name] = {
            "rows": int(sum(1 for _ in p.open(encoding="utf-8")) - 1),
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
        }

    manifest = {
        "dataset": "novel_hub",
        "source": {**C.SOURCE, "snapshot": snapshot},
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": TABLE_ORDER,
        "derived": {"novels_flat": "由上述表 join 而成，可随时重建，不作权威数据"},
        "rows": {Path(k).stem: v["rows"] for k, v in files.items()},
        "files": files,
        "dropped": C.DROPPED,
        "anomalies": anomalies(novel, con),
        "zeros": zeros(novel),
        "constraints": {
            "carrier": "schema.sql",
            "enforced_by_ddl": [
                "PRIMARY KEY",
                "UNIQUE",
                "NOT NULL",
                "CHECK",
                "FOREIGN KEY",
            ],
            "enforced_by_validate": "发布前对 CSV 复检，覆盖绕过 DDL 的消费方",
        },
        "contract": {
            "encoding": "utf-8",
            "bom": False,
            "line_ending": "LF",
            "null": "空串",
            "datetime": "ISO 8601，无时区",
        },
    }
    C.MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    con.close()

    print(f"快照 {snapshot}  表 {len(tables)} + flat")
    for k, v in files.items():
        print(f"  {k:16} {v['rows']:>7} 行  {v['bytes'] / 1e6:6.2f} MB")
    print(f"已发布 {C.CSV_DIR}  约束 {C.SQL_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

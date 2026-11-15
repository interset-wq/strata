"""对产出目录做结构与约束校验，返回错误清单（空表示通过）。

校验分两层：
- 格式层：编码、BOM、行尾、整数列无小数点、日期格式
- 关系层：主键唯一、外键无孤儿、UNIQUE、CHECK 与非空

失败即拒绝发布，上一版产出保持可用。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def _read(path: Path) -> pd.DataFrame:
    """全列按字符串读入，保留空串，以便逐列判定格式。"""
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)


def _check_file_bytes(path: Path) -> list[str]:
    errs = []
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errs.append(f"{path.name}: 含 UTF-8 BOM")
    if b"\r" in raw:
        errs.append(f"{path.name}: 含 CR，行尾不是 LF")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errs.append(f"{path.name}: 非法 UTF-8（{exc}）")
    if not raw.endswith(b"\n"):
        errs.append(f"{path.name}: 末尾缺少换行")
    return errs


def _check_columns(table: str, df: pd.DataFrame) -> list[str]:
    want = C.schema_columns(table)
    got = list(df.columns)
    if got == want:
        return []
    missing = [c for c in want if c not in got]
    extra = [c for c in got if c not in want]
    detail = []
    if missing:
        detail.append(f"缺少 {missing}")
    if extra:
        detail.append(f"多出 {extra}")
    if not detail:
        detail.append("顺序不一致")
    return [f"{table}: 表头不符，{'；'.join(detail)}"]


def _check_format(table: str, df: pd.DataFrame) -> list[str]:
    errs = []
    for col, dtype, nullable, _key, _desc in C.SCHEMA[table]:
        s = df[col]
        blank = s == ""
        if not nullable and blank.any():
            errs.append(f"{table}.{col}: 非空列出现 {int(blank.sum())} 个空值")
        if dtype in ("int64", "int8", "Int64"):
            bad = s[(~blank) & ~s.str.match(INT_RE)]
            if len(bad):
                errs.append(
                    f"{table}.{col}: {len(bad)} 个值不是规范整数，例 {bad.iloc[0]!r}"
                )
        if dtype == "string" and col == "last_update":
            bad = s[(~blank) & ~s.str.match(TS_RE)]
            if len(bad):
                errs.append(
                    f"{table}.{col}: {len(bad)} 个值不是 ISO 8601，例 {bad.iloc[0]!r}"
                )
    return errs


def _check_keys(table: str, df: pd.DataFrame) -> list[str]:
    errs = []
    single = [c[0] for c in C.SCHEMA[table] if c[3] == "PK"]
    pk_cols = [c[0] for c in C.SCHEMA[table] if "PK" in c[3].split(",")]
    composite = pk_cols if len(pk_cols) > 1 else []
    if composite:
        dup = df.duplicated(subset=composite, keep=False)
        if dup.any():
            errs.append(f"{table}: 复合主键 {composite} 重复 {int(dup.sum())} 行")
    for col in single:
        dup = df[col].duplicated(keep=False)
        if dup.any():
            errs.append(f"{table}.{col}: 主键重复 {int(dup.sum())} 行")
    for col, _d, _n, k, _desc in C.SCHEMA[table]:
        if "UNIQUE" in k.split(","):
            dup = df[col].duplicated(keep=False)
            if dup.any():
                errs.append(f"{table}.{col}: UNIQUE 重复 {int(dup.sum())} 行")
    return errs


def _check_foreign_keys(tables: dict[str, pd.DataFrame]) -> list[str]:
    errs = []
    for table, cols in C.SCHEMA.items():
        for col, _d, _n, key, _desc in cols:
            refs = [k.strip() for k in key.split(",") if k.strip().startswith("FK")]
            if not refs:
                continue
            ref = refs[0][len("FK ") :]
            parent, parent_col = ref.split(".")
            child_vals = tables[table][col]
            child_vals = child_vals[child_vals != ""]
            orphans = ~child_vals.isin(set(tables[parent][parent_col]))
            if orphans.any():
                errs.append(
                    f"{table}.{col}: {int(orphans.sum())} 个值在 {parent}.{parent_col} 中不存在"
                )
    return errs


def _check_constraints(tables: dict[str, pd.DataFrame]) -> list[str]:
    errs = []
    novel = tables["novel"]
    for col in C.NON_NEGATIVE:
        neg = novel[col].astype("int64") < 0
        if neg.any():
            errs.append(f"novel.{col}: 出现 {int(neg.sum())} 个负值")
    like = novel["like_num"]
    present = like[like != ""]
    neg = present[present.astype("int64") < 0]
    if len(neg):
        errs.append(f"novel.like_num: 出现 {len(neg)} 个负值，应已置空")
    banner = set(novel["has_banner"].unique())
    if not banner <= {"0", "1"}:
        errs.append(f"novel.has_banner: 取值越界 {sorted(banner - {'0', '1'})}")
    for src, dim in (
        ("genre_id", "genre"),
        ("ptype_id", "ptype"),
        ("status_id", "status"),
    ):
        unknown = ~novel[src].isin(set(tables[dim]["id"]))
        if unknown.any():
            errs.append(
                f"novel.{src}: {int(unknown.sum())} 个值不在 {dim} 码表中"
            )
    return errs


def _check_flat(tables: dict[str, pd.DataFrame], flat: pd.DataFrame) -> list[str]:
    errs = []
    if list(flat.columns) != C.FLAT_COLUMNS:
        errs.append("novels_flat: 列与 FLAT_COLUMNS 不一致")
    if len(flat) != len(tables["novel"]):
        errs.append(f"novels_flat: 行数 {len(flat)} 与 novel {len(tables['novel'])} 不等")
    if set(flat["nid"]) != set(tables["novel"]["nid"]):
        errs.append("novels_flat: nid 集合与 novel 不一致")
    return errs


def check_dir(directory: Path) -> list[str]:
    errs: list[str] = []
    expected = list(C.SCHEMA) + ["novels_flat"]
    for name in expected:
        p = directory / f"{name}.csv"
        if not p.exists():
            errs.append(f"缺少文件 {name}.csv")
            continue
        errs.extend(_check_file_bytes(p))
    if errs:
        return errs

    tables: dict[str, pd.DataFrame] = {}
    for table in C.SCHEMA:
        df = _read(directory / f"{table}.csv")
        if df.empty:
            errs.append(f"{table}: 0 行")
            continue
        errs.extend(_check_columns(table, df))
        if errs:
            return errs
        errs.extend(_check_format(table, df))
        errs.extend(_check_keys(table, df))
        tables[table] = df

    if errs:
        return errs

    errs.extend(_check_foreign_keys(tables))
    errs.extend(_check_constraints(tables))
    errs.extend(_check_flat(tables, _read(directory / "novels_flat.csv")))
    return errs


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else C.CSV_DIR
    errors = check_dir(target)
    if not errors:
        print(f"校验通过：{target}")
        return 0
    print(f"校验失败，{len(errors)} 项")
    for e in errors:
        print("  -", e)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

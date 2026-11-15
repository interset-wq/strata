"""对产出的 CSV 做格式与取值校验，返回错误清单（空表示通过）。

校验分两层：格式层（编码、行尾、整数与日期写法）与取值层（主键唯一、
枚举落在域内、计数非负）。失败即拒绝发布，上一版产出保持可用。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C

INT_RE = re.compile(r"^(0|[1-9]\d*)$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def _check_bytes(path: Path) -> list[str]:
    errs = []
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        errs.append("含 UTF-8 BOM")
    if b"\r" in raw:
        errs.append("含 CR，行尾不是 LF")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        errs.append(f"非法 UTF-8（{exc}）")
    if not raw.endswith(b"\n"):
        errs.append("末尾缺少换行")
    return errs


def _check_format(df: pd.DataFrame) -> list[str]:
    errs = []
    for name, dtype, nullable, _src, _desc in C.COLUMNS:
        s = df[name]
        blank = s == ""
        if not nullable and blank.any():
            errs.append(f"{name}: 非空列出现 {int(blank.sum())} 个空值")
        if dtype in ("int64", "int8", "Int64"):
            bad = s[(~blank) & ~s.str.match(INT_RE)]
            if len(bad):
                errs.append(f"{name}: {len(bad)} 个值不是规范整数，例 {bad.iloc[0]!r}")
        if name == "updated_at":
            bad = s[(~blank) & ~s.str.match(TS_RE)]
            if len(bad):
                errs.append(f"{name}: {len(bad)} 个值不是 ISO 8601，例 {bad.iloc[0]!r}")
    return errs


def _check_values(df: pd.DataFrame) -> list[str]:
    errs = []

    dup = df["id"].duplicated(keep=False)
    if dup.any():
        errs.append(f"id: 主键重复 {int(dup.sum())} 行")

    for name, allowed in (
        ("status", C.STATUSES),
        ("genre", C.GENRES + [C.UNCLASSIFIED]),
        ("price_type", C.PRICE_TYPES),
        ("featured", ["0", "1"]),
    ):
        bad = df.loc[~df[name].isin(allowed), name]
        if len(bad):
            errs.append(f"{name}: 取值越界 {sorted(set(bad))[:5]}")

    for name in ("words", "clicks", "praises"):
        s = df[name]
        neg = s[(s != "") & (s.astype("int64") < 0)]
        if len(neg):
            errs.append(f"{name}: 出现 {len(neg)} 个负值")

    likes = df["likes"]
    present = likes[likes != ""]
    neg = present[present.astype("int64") < 0]
    if len(neg):
        errs.append(f"likes: 出现 {len(neg)} 个负值，应已置空")

    tags = df["tags"]
    bad = tags[
        tags.str.startswith(C.TAG_SEP)
        | tags.str.endswith(C.TAG_SEP)
        | tags.str.contains(C.TAG_SEP * 2, regex=False)
    ]
    if len(bad):
        errs.append(f"tags: {len(bad)} 行含多余分隔符，例 {bad.iloc[0]!r}")

    for name in ("title", "author"):
        s = df[name]
        ws = s[s != s.str.strip()]
        if len(ws):
            errs.append(f"{name}: {len(ws)} 行首尾有空白")

    return errs


def check_file(path: Path) -> list[str]:
    errs = _check_bytes(path)
    if errs:
        return errs

    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
    if list(df.columns) != C.COLUMN_NAMES:
        missing = [c for c in C.COLUMN_NAMES if c not in df.columns]
        extra = [c for c in df.columns if c not in C.COLUMN_NAMES]
        detail = "；".join(
            x for x in (f"缺少 {missing}" if missing else "", f"多出 {extra}" if extra else "") if x
        )
        return [f"表头不符，{detail or '顺序不一致'}"]
    if df.empty:
        return ["0 行"]

    errs.extend(_check_format(df))
    errs.extend(_check_values(df))
    return errs


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else C.CSV_FILE
    errors = check_file(target)
    if not errors:
        print(f"校验通过：{target}")
        return 0
    print(f"校验失败，{len(errors)} 项")
    for e in errors:
        print("  -", e)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

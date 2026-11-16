"""对产出的 CSV 做格式与取值校验，返回错误清单（空表示通过）。

校验分两层：格式层（编码、行尾、整数与日期写法）与取值层（主键唯一、
枚举落在域内、计数非负）。失败即拒绝发布，上一版产出保持可用。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import config as C

INT_RE = re.compile(r"^(0|[1-9]\d*)$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

# Cc 控制符、常见 Cf 格式符（零宽/软连字符/双向覆盖）、BMP 私用区。
# Cn 未分配字符无法用正则枚举，实际数据中未出现。
INVALID_RE = re.compile(
    "[\x00-\x1f\x7f-\x9f"
    "\u00ad\u061c\u06dd\u070f\u180e"
    "\u200b-\u200f\u202a-\u202e\u2060-\u206f"
    "\ufeff\ufff9-\ufffb"
    "\ue000-\uf8ff]"
)
# 是空白但不是普通空格：NBSP、全角空格、em space 等
ODD_SPACE_RE = re.compile(r"[^\S ]")
MULTISPACE_RE = re.compile(r" {2,}")


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
        ("genre", C.GENRES),
        ("price_type", C.PRICE_TYPES),
        ("featured", ["0", "1"]),
    ):
        bad = df.loc[~df[name].isin(allowed), name]
        if len(bad):
            errs.append(f"{name}: 取值越界 {sorted(set(bad))[:5]}")

    for name in ("words", "clicks", "favs", "praises"):
        s = df[name]
        neg = s[(s != "") & (s.astype("int64") < 0)]
        if len(neg):
            errs.append(f"{name}: 出现 {len(neg)} 个负值")

    # cover_url 已省略公共前缀，有值时必须是相对路径，出现 http 即回归
    cover = df["cover_url"]
    absolute = cover[cover.str.startswith("http", na=False)]
    if len(absolute):
        errs.append(
            f"cover_url: {len(absolute)} 行含绝对地址，例 {absolute.iloc[0][:40]!r}"
        )

    # 封面文件全库唯一：共用是爬虫缺陷，构建时已保留 id 最大者、其余置空
    dup_cover = cover[cover != ""]
    dup = dup_cover[dup_cover.duplicated(keep=False)]
    if len(dup):
        errs.append(f"cover_url: {len(dup)} 行共用封面文件，应仅保留属主")

    # 以下两条对应 build_csv.drop_mask，用同一判据复核，防止剔除逻辑失效
    licensed = df.loc[df["author"].isin(C.LICENSED_LN_AUTHORS), "author"]
    if len(licensed):
        errs.append(
            f"author: {len(licensed)} 行属正版日轻版权方账号（id 不遵守递增），"
            f"例 {licensed.iloc[0]!r}"
        )

    empty = (df["words"].astype("int64") <= C.EMPTY_WORDS) & (
        df["clicks"].astype("int64") <= C.EMPTY_CLICKS
    )
    textless = df.loc[~df["title"].map(C.has_text_char) & empty, "title"]
    if len(textless):
        errs.append(f"title: {len(textless)} 行无文字标题且无内容，例 {textless.iloc[0]!r}")

    shell = (df["words"] == "0") & (df["clicks"] == "0")
    if shell.any():
        errs.append(f"{int(shell.sum())} 行字数与人气同时为 0")

    tags = df["tags"]
    bad = tags[
        tags.str.startswith(C.TAG_SEP)
        | tags.str.endswith(C.TAG_SEP)
        | tags.str.contains(C.TAG_SEP * 2, regex=False)
    ]
    if len(bad):
        errs.append(f"tags: {len(bad)} 行含多余分隔符，例 {bad.iloc[0]!r}")

    errs.extend(_check_text(df))
    return errs


def _check_text(df: pd.DataFrame) -> list[str]:
    """字符串列必须已归一：无非法字符、无非 ASCII 空白、无首尾与连续空格。"""
    errs = []
    for name, dtype, _null, _src, _desc in C.COLUMNS:
        if dtype != "string":
            continue
        s = df[name]
        for pattern, label in (
            (INVALID_RE, "非法字符"),
            (ODD_SPACE_RE, "非 ASCII 空白"),
            (MULTISPACE_RE, "连续空格"),
        ):
            hit = s[s.str.contains(pattern, regex=True, na=False)]
            if len(hit):
                errs.append(f"{name}: {len(hit)} 行含{label}，例 {hit.iloc[0][:30]!r}")
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

"""按 build_csv 的剔除原因分组，抓取页面状态特征。

回答一个问题：`out/manifest.json` 剔除的 2,451 个 nid，页面到底怎么了？
结论见 references/sfacg-endpoints.md §11.5。

用法：
    uv run python analysis/fetchers/probe_page_states.py [--n 20] [--offline]

`--offline` 只重建剔除原因（写 out/_drop_reasons.json），不请求站点。
结果写 out/_page_states_probe.json 与 out/_page_states_summary.md（派生物，不入库）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import config as C
from lib import paths
from pipeline.build_csv import clean_row, drop_mask, load_jsonl

UA = (
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)
BASE = "https://m.sfacg.com/b/{nid}/"

# 三态判据（用户 2026-11-17 定案）：不细分下架原因，不依赖版权声明文案。
# 死亡 = 否定文案；僵尸 = 有详情页但无阅读入口 / 数字字段非法；存活 = 其余。
FEATURES = [
    "点击阅读",
    "目录列表",
    "应版权方要求",  # 仅作辅助记录，充分非必要，不参与判定
    "小说不存在",
    "出错啦",
    "VIP",
]
DEAD_TEXT = ("小说不存在", "出错啦")
READABLE = "点击阅读"
# 结构化判据：div.book_Catalog 下是否有 <a>。比全文关键词更稳定，
# 不依赖下架声明文案（多数僵尸页不写声明）。正则避免引入 bs4 依赖。
_CATALOG_RE = re.compile(r'<div[^>]*class="[^"]*book_Catalog[^"]*"[^>]*>(.*?)</div>', re.S)
_ANCHOR_RE = re.compile(r'<a\b', re.I)

_EMPTY_TALLY = {
    "text": {},
    "status_missing": 0,
    "status_dead_to_ongoing": 0,
    "genre_relabelled": 0,
    "genre_unresolved": 0,
    "cover_placeholder_nulled": 0,
    "cover_shared_bugged": 0,
    "licensed_ln_total": 0,
    "licensed_ln_with_banner": 0,
    "tags_deduplicated": 0,
    "tags_dropped": 0,
    "word_num_zero": 0,
    "click_num_zero": 0,
    "praise_num_zero": 0,
    "like_num_zero": 0,
}


def drop_reasons() -> dict[str, list[int]]:
    """从原始 jsonl 重建每条剔除原因；manifest 只存汇总 id。"""
    records, _ = load_jsonl(C.JSONL_DIR)
    rows = [clean_row(records[nid], dict(_EMPTY_TALLY), []) for nid in sorted(records)]
    df = pd.DataFrame(rows, columns=C.COLUMN_NAMES)
    for col, dtype, *_ in C.COLUMNS:
        df[col] = pd.array(df[col], dtype="Int64") if dtype == "Int64" else df[col].astype(dtype)
    return {name: df.loc[mask, "id"].tolist() for name, mask in drop_mask(df).items()}


def classify(row: dict, numeric_illegal: bool = False) -> str:
    """三态判据：死亡（否定文案）> 僵尸（无阅读入口或数字非法）> 存活。

    主判据是 div.book_Catalog 是否含 <a>（结构化），关键词仅作 fallback。
    """
    if any(row.get(text) for text in DEAD_TEXT):
        return "死亡"
    has_link = row.get("catalog_has_link", not row.get(READABLE, False))
    if numeric_illegal or not has_link:
        return "僵尸"
    return "存活"


def probe(nid: int, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(BASE.format(nid=nid), headers={"User-Agent": UA}, timeout=25)
            r.encoding = "utf-8"
            text = r.text
            catalog = _CATALOG_RE.search(text)
            return {
                "nid": nid,
                "status": r.status_code,
                "size": len(r.content),
                "catalog_has_link": bool(catalog and _ANCHOR_RE.search(catalog.group(1))),
                **{k: k in text for k in FEATURES},
            }
        except requests.RequestException as exc:
            if attempt == retries - 1:
                return {"nid": nid, "error": str(exc)[:120]}
            time.sleep(1.5 * (attempt + 1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=20, help="每组抽样数（默认 20）")
    ap.add_argument("--offline", action="store_true", help="只重建剔除原因，不发请求")
    args = ap.parse_args()

    reasons = drop_reasons()
    json.dump(reasons, open(paths.OUT_DIR / "_drop_reasons.json", "w"), indent=0)
    print(f"剔除原因重建完成：{sum(map(len, reasons.values()))} 条")
    for name, ids in reasons.items():
        print(f"  {name:22} {len(ids):5}")
    if args.offline:
        return 0

    library = set(pd.read_csv(paths.CSV_FILE, usecols=["id"])["id"].tolist())
    rng = random.Random(20261117)
    groups: dict[str, list[int]] = {"存活（CSV 内）": rng.sample(sorted(library), args.n)}
    for name, ids in reasons.items():
        groups[name] = rng.sample(ids, min(args.n, len(ids)))
    groups["死亡（无效 nid）"] = [99999999, 88888888, 77777777, 1, 500]

    # 数字字段非法：从原始记录取，页面 HTML 不直接给出负收藏的语义
    records, _ = load_jsonl(C.JSONL_DIR)
    rows: list[dict] = []
    for name, ids in groups.items():
        for nid in ids:
            row = probe(nid)
            row["group"] = name
            if "error" not in row:
                src = records.get(nid, {})
                illegal = (
                    int(src.get("like_num") or 0) < 0
                    or (int(src.get("word_num") or 0) == 0 and int(src.get("click_num") or 0) == 0)
                )
                row["numeric_illegal"] = illegal
                row["state"] = classify(row, illegal)
            rows.append(row)
            time.sleep(0.25)
        print(f"  {name}: {len(ids)} 本完成")

    json.dump(rows, open(paths.OUT_DIR / "_page_states_probe.json", "w"), ensure_ascii=False, indent=1)

    df = pd.DataFrame(rows)
    lines = [
        "# 页面状态对照（依据构建剔除 id）",
        "",
        "| 组 | n | 体积中位 | 有阅读入口 | 否定文案 | 数字非法 | 判定 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, sub in df.groupby("group", sort=False):
        states = sub["state"].value_counts().to_dict() if "state" in sub else {}
        lines.append(
            f"| {name} | {len(sub)} | {sub['size'].median():.0f} "
            f"| {int(sub[READABLE].sum())}/{len(sub)} "
            f"| {int(sub['出错啦'].sum() + sub['小说不存在'].sum())}/{len(sub)} "
            f"| {int(sub['numeric_illegal'].sum())}/{len(sub)} "
            f"| {states} |"
        )
    summary = "\n".join(lines) + "\n"
    (paths.OUT_DIR / "_page_states_summary.md").write_text(summary, encoding="utf-8")
    print("\n" + summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

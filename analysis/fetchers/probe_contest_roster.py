"""征文参赛清单探针（2026-11-20 实测，端点档案 §7.4 的证据来源）。

验证两套分页接口可用、摸 tagId、统计清单对 db 的补采增量。
只取清单元数据、不取正文、不登录；串行限速、失败即跳过（降级）。

用法（从仓库根运行）：
    uv run --project analysis python analysis/fetchers/probe_contest_roster.py \
        [--tags 704,703,702] [--size 500] [--out analysis/out/contest_roster.csv]

默认 tag 表 = 本轮实证的 14 个（见 docs/contest-roster-harvest.md §2）。
默认与 analysis/out/novels.csv 的 id 列比对，输出 in_db 列。
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
UA = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
      "referer": "https://pages.sfacg.com/h5/act/djzw2020/"}

URL_OLD = "https://pages.sfacg.com/ajax/ashx/Common.ashx"
URL_NEW = "https://pages.sfacg.com/api/essay/getNovels"

# 本轮实证的 tag → (接口, 赛事/赛道)。新 SPA 三轨；旧 H5 单 tag。
TAGS: dict[int, str] = {
    381: "一征冬征", 406: "二征冬征", 408: "七征-1", 409: "七征-中?",
    410: "七征-短?", 411: "七征-4", 412: "七征-5", 415: "三征冬征",
    418: "八征", 454: "四征冬征", 466: "五征冬征",
    702: "十二征-长", 703: "十二征-中", 704: "十二征-短",
}
NEW_TAGS = {702, 703, 704}


def fetch_new(tag: int, size: int, session: requests.Session) -> list[dict]:
    out: list[dict] = []
    for page in range(1, 50):
        try:
            r = session.get(URL_NEW, params={"tagIds": tag, "page": page, "size": size}, timeout=30)
            data = (r.json().get("data") or {})
            nov = data.get("novels") or []
        except Exception:
            break
        out.extend(nov)
        if len(nov) < size:
            break
        time.sleep(0.25)
    return out


def fetch_old(tag: int, session: requests.Session) -> list[dict]:
    out: list[dict] = []
    for pi in range(100):
        try:
            r = session.get(URL_OLD, params={"op": "getNovelsByTag", "tagId": tag, "ps": 200, "pi": pi}, timeout=30)
            nov = (r.json().get("novels") or [])
        except Exception:
            break
        out.extend(nov)
        if len(nov) < 200:
            break
        time.sleep(0.25)
    return out


def normalize(nov: dict, tag: int) -> dict | None:
    # 两套接口字段大小写不同
    nid = nov.get("novelID") or nov.get("NovelID")
    if not nid:
        return None
    return {
        "nid": int(nid),
        "title": nov.get("novelName") or nov.get("NovelName") or "",
        "author": nov.get("authorName") or nov.get("AuthorName") or "",
        "categoryID": nov.get("categoryID") if nov.get("categoryID") is not None else nov.get("CategoryID"),
        "tag": tag,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=",".join(str(t) for t in TAGS), help="逗号分隔的 tagId")
    ap.add_argument("--size", type=int, default=500, help="新接口 size（实测 ≤500 可用）")
    ap.add_argument("--out", default="analysis/out/contest_roster.csv")
    a = ap.parse_args()

    tags = [int(x) for x in a.tags.split(",") if x.strip()]
    sess = requests.Session()
    sess.headers.update(UA)

    recs: list[dict] = []
    for tag in tags:
        nov = fetch_new(tag, a.size, sess) if tag in NEW_TAGS else fetch_old(tag, sess)
        name = TAGS.get(tag, "?")
        for n in nov:
            r = normalize(n, tag)
            if r:
                recs.append(r)
        print(f"tag {tag:4} [{name:12}] rows={len(nov):5}")

    # 去重 + 标注是否在 db
    uniq: dict[int, dict] = {}
    for r in recs:
        uniq.setdefault(r["nid"], r)
    db_path = ROOT / "analysis/out/novels.csv"
    db_ids: set[int] = set()
    if db_path.exists():
        with db_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    db_ids.add(int(row["id"]))
                except (ValueError, KeyError):
                    pass
    for r in uniq.values():
        r["in_db"] = r["nid"] in db_ids

    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["nid", "title", "author", "categoryID", "tag", "in_db"])
        w.writeheader()
        w.writerows(uniq.values())

    total = len(uniq)
    missing = sum(1 for r in uniq.values() if not r["in_db"])
    print(f"\n去重 {total} 本；不在 db {missing} 本（{missing / total:.1%}）" if total else "空")
    print("saved", out)


if __name__ == "__main__":
    main()

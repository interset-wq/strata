"""构建月榜遗漏书补充文件 dataset/rank_missing.jsonl（dataset 与种子的输入）。

## 口径（2026-11-19 用户定：纳入 dataset 与种子）

- 来源：月榜（MonthlyBoy.ashx，2013-03 起）上榜但不在分析库的 nid（报告 10 §A：
  上榜时必然存活）。两处 App API 来源合并：
  ① `out/rank_missing_meta.jsonl`（fetchers/fetch_rank_missing.py 逐本详情）
  ② `out/app_api_novels.jsonl`（既有全字段样本里的对应书）
- **快照上界过滤**：`addTime > 2026-05-03 11:45` 的书是上界之后新建的，
  本来就不该出现在 5 月快照里，不属于「遗漏」——剔除（37 本）。
- **计数为 2026-11 App API 当期值**：这批书缺失于 5 月快照、无 5 月值；
  收藏/点击/字数为建档以来累计值、漂移有限（多为完结多年的长篇头部）。
  文件内 `observed_at` 记录观测时间，dataset manifest 记 `rank_missing_observed`。
- **praise_num（赞）**：App API 无此字段，从手机版详情页 m.sfacg.com/b/{nid}/
  补抓（`赞<small>N</small>`），失败置 0 并在文件内记 `praises_source`。
- 字段映射（App API → novel_hub 15 字段）：novelName→novel_title、
  authorName→author、signStatus(VIP/签约/普通→免费)、typeId→genre（TIDS 表）、
  isFinish→status、charCount→word_num、viewTimes→click_num、markCount→like_num
  （**like_num=收藏**，与 PC jsonl 同义）、novelCover→cover；contest/tags/banner
  缺失，置空/False。另保留 addTime（秒级精确）、authorId、rank_months、best_rank
  等溯源字段（build.py 只读 FIELDS，其余键随文件留档）。

用法：
    uv run python analysis/fetchers/build_rank_missing_supplement.py   # 断点续采
产出：dataset/rank_missing.jsonl
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402
from fetchers.fetch_app_api_novels import TIDS  # noqa: E402

OUT = paths.ROOT.parent / "dataset" / "rank_missing.jsonl"
BOUND = pd.Timestamp("2026-05-03 11:45:00")
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
LIKE = re.compile(r"赞<small>\s*(\d+)</small>")
COLL = re.compile(r"收藏<small>\s*(\d+)</small>")
STATE = re.compile(r"<span>\s*([^<]{1,6}?)\s*</span>\s*<span>\s*(连载中|已完结)")

SIGN_MAP = {"VIP": "VIP", "签约": "签约", "普通": "免费"}
OBSERVED_AT = "2026-11-19"


def load_app_api() -> dict[int, dict]:
    recs: dict[int, dict] = {}
    p = paths.OUT_DIR / "app_api_novels.jsonl"
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("nid"):
            recs[int(d["nid"])] = d
    return recs


def load_rank_meta() -> dict[int, dict]:
    recs: dict[int, dict] = {}
    p = paths.OUT_DIR / "rank_missing_meta.jsonl"
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            recs[int(d["nid"])] = d
    return recs


def load_lib_nids() -> set[int]:
    import csv
    with (paths.OUT_DIR / "novels.csv").open(encoding="utf-8", newline="") as f:
        return {int(row["id"]) for row in csv.DictReader(f)}


def load_rank_entries() -> dict[int, dict]:
    entries: dict[int, dict] = {}
    for line in (paths.OUT_DIR / "monthly_ranks.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        for rank, it in enumerate(r["items"]):
            nid = int(it["nid"])
            e = entries.setdefault(nid, {"rank_months": [], "best_rank": rank})
            if r["month"] not in e["rank_months"]:
                e["rank_months"].append(r["month"])
            e["best_rank"] = min(e["best_rank"], rank)
    return entries


def fetch_page(nid: int) -> dict:
    """手机版详情页 → 赞 / 收藏交叉核对 / 分类（typeId 不在九类表时的兜底）。"""
    for _ in range(3):
        try:
            r = requests.get(f"https://m.sfacg.com/b/{nid}/", timeout=15,
                             headers={"User-Agent": UA})
            break
        except Exception:
            time.sleep(2)
    else:
        return {}
    if len(r.text) < 5000:
        return {}
    like = LIKE.search(r.text)
    coll = COLL.search(r.text)
    state = STATE.search(r.text)
    return {
        "praises": int(like.group(1)) if like else None,
        "coll": int(coll.group(1)) if coll else None,
        "genre": state.group(1) if (state and state.group(1)) else None,
    }


def build_record(d: dict, e: dict, praises: int | None,
                 praises_source: str, coll_check: int | None,
                 genre_hint: str | None = None) -> dict:
    price = SIGN_MAP.get(d.get("signStatus") or "", "免费")
    genre = TIDS.get(d.get("typeId")) or genre_hint or ""
    return {
        "nid": int(d["nid"]),
        "novel_title": d.get("novelName") or "",
        "author": d.get("authorName") or "",
        "price_type": price,
        "contest": "",
        "genre": genre,
        "click_num": int(d.get("viewTimes") or 0),
        "word_num": int(d.get("charCount") or 0),
        "status": "已完结" if d.get("isFinish") else "连载中",
        "last_update": (d.get("lastUpdateTime") or "").replace("T", " "),
        "praise_num": praises if praises is not None else 0,
        "like_num": int(d.get("markCount") or 0),
        "cover": d.get("novelCover") or "",
        "banner": False,
        "tags": [],
        # 溯源字段（build.py 只读上方 15 字段，其余留档）
        "addTime": d.get("addTime"),
        "authorId": d.get("authorId"),
        "rank_months": e.get("rank_months"),
        "best_rank": e.get("best_rank"),
        "observed_at": OBSERVED_AT,
        "praises_source": praises_source,
        "coll_mobile_check": coll_check,
    }


def main() -> None:
    rank = load_rank_entries()
    lib = load_lib_nids()
    missing = set(rank) - lib
    print(f"月榜 {len(rank)} 本去重，不在库 {len(missing)} 本")

    merged: dict[int, dict] = {}
    merged.update(load_app_api())
    merged.update(load_rank_meta())   # 逐本详情覆盖旧样本（字段更全）
    have = {n: merged[n] for n in missing if n in merged and merged[n].get("addTime")}
    dead = sorted(missing - set(merged))
    pre = {n: d for n, d in have.items()
           if pd.Timestamp(d["addTime"]) <= BOUND}
    post = sorted(set(have) - set(pre))
    print(f"App API 有记录 {len(have)}（快照后建档剔除 {len(post)}，已删除 {len(dead)}）"
          f"→ 纳入 {len(pre)} 本")

    done: dict[int, dict] = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                done[int(d["nid"])] = d
        print(f"已有 {len(done)} 条，断点续采")

    todo = [n for n in sorted(pre) if n not in done]
    print(f"待补抓详情 {len(todo)} 本")
    fetched: dict[int, dict] = {}
    ok = fallback = 0
    if todo:
        with OUT.open("a", encoding="utf-8") as fh:
            for i, nid in enumerate(todo, 1):
                page = fetch_page(nid)
                praises = page.get("praises")
                src = "mobile_html" if praises is not None else "zero_fallback"
                if praises is None:
                    fallback += 1
                else:
                    ok += 1
                rec = build_record(pre[nid], rank[nid], praises, src,
                                   page.get("coll"), page.get("genre"))
                fetched[nid] = rec
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                if i % 20 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} 成功 {ok} 兜底 {fallback}")
                time.sleep(0.35)

    # 与既有记录合并重写（保证文件 = 全集，且断点续采不重不漏）
    final = dict(done)
    final.update(fetched)
    for nid in sorted(pre):
        if nid not in final:
            final[nid] = build_record(pre[nid], rank[nid], None, "pending", None)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for nid in sorted(final):
            fh.write(json.dumps(final[nid], ensure_ascii=False) + "\n")
    print(f"写出 {len(final)} 条 → {OUT}")


if __name__ == "__main__":
    main()

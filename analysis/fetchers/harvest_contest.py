"""征文爬虫：只走征文清单 API 获取 nid，不再用 novel_hub 列表页翻页。

## 三个步骤（各自断点续跑，可单独执行）

1. `roster`：按 tag 拉全量参赛清单 → `analysis/out/contest_roster.jsonl`
   每行 {nid, title, author, categoryID, tag, tag_name, series}。
   只取清单元数据（nid/标题/作者/categoryID），不取正文、不登录。

2. `dedup`：roster 与既有 nid（dataset/out/books.jsonl + analysis/out/novels.csv）
   求差集 → `analysis/out/contest_new_nids.jsonl`（待补详情的新书）。

3. `details`：对新 nid 逐个请求详情补齐 dataset 15 字段 →
   `dataset/contest_new.jsonl`（断点续采、失败降级、不写 seed.db）。
   - App API `GET /novels/{nid}`：字数/收藏/点击/状态/建档时间/authorId/封面/categoryId
   - mobile web `m.sfacg.com/b/{nid}/`：赞（App API 无此字段）

## 端点（分页起点以实测为准，NEW 为 page 0 基，OLD 为 pi 0 基）

    NEW GET https://pages.sfacg.com/api/essay/getNovels?tagIds={t}&page={p}&size={n}
    OLD GET https://pages.sfacg.com/ajax/ashx/Common.ashx?op=getNovelsByTag&tagId={t}&ps=200&pi={p}

## 目标清单

`contest_harvest_targets.json`（从权威台账 docs/contest-roster-harvest.md §2 抽取，
100 个 tag 覆盖四季主线/少年/对话/34 个独立赛事）。本次默认只跑 14 征：--tags 793,794。

## 约束

- 串行、间隔 ≥0.5s（清单 0.3s / 详情 0.5s），失败重试 2 次后跳过。
- 判空降 size 重试（500→200→20→3），应对部分 tag 的 size 边界陷阱。
- 清单只覆盖参赛书；字段/口径细节见 docs/contest-roster-harvest.md、docs/contest-roster-fields.md。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from lib import paths  # noqa: E402
from fetch_app_api_novels import TIDS, KEEP, make_headers  # noqa: E402

ROOT = paths.ROOT.parent
OUT = paths.OUT_DIR
TARGETS_FILE = HERE / "contest_harvest_targets.json"

ROSTER_OUT = OUT / "contest_roster.jsonl"
NEW_NIDS_OUT = OUT / "contest_new_nids.jsonl"
DETAIL_OUT = ROOT / "dataset" / "contest_new.jsonl"
BOOKS_JSONL = ROOT / "dataset" / "out" / "books.jsonl"

URL_NEW = "https://pages.sfacg.com/api/essay/getNovels"
URL_OLD = "https://pages.sfacg.com/ajax/ashx/Common.ashx"
UA = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "referer": "https://pages.sfacg.com/h5/act/zw20260504/pc",
}
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")

SIZES = (500, 200, 20, 3)
LIKE = re.compile(r"赞<small>\s*(\d+)</small>")
COLL = re.compile(r"收藏<small>\s*(\d+)</small>")
SIGN_MAP = {"VIP": "VIP", "签约": "签约", "普通": "免费"}
OBSERVED_AT = time.strftime("%Y-%m-%d")

# 默认只跑 14 征（2026，参赛最多的 X 征、一次性拿到大量新书 nid）
DEFAULT_TAGS = "793,794"


def load_targets() -> dict[int, dict]:
    data = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    return {int(x["tag"]): x for x in data}


# ---------------- step 1: roster ----------------

def fetch_new(tag: int, session: requests.Session, delay: float) -> list[dict]:
    """新端点 page 0 基；判空降 size 重试；用 totalPage 截止。"""
    for size in SIZES:
        out: list[dict] = []
        page = 0
        broken = False
        while page < 200:
            try:
                r = session.get(URL_NEW, params={"tagIds": tag, "page": page, "size": size}, timeout=30)
                payload = r.json()
                data = payload.get("data") or {}
                nov = data.get("novels") or []
                total_page = int(data.get("totalPage") or 0)
            except Exception:
                broken = True
                break
            out.extend(nov)
            if len(nov) < size or (total_page and page + 1 >= total_page):
                break
            page += 1
            time.sleep(delay)
        if not broken and out:
            return out
    return []


def fetch_old(tag: int, session: requests.Session, delay: float) -> list[dict]:
    """旧端点 pi 0 基；判空降 ps 重试。"""
    for ps in (200, 100, 20, 3):
        out: list[dict] = []
        pi = 0
        broken = False
        while pi < 500:
            try:
                r = session.get(URL_OLD, params={
                    "op": "getNovelsByTag", "tagId": tag, "ps": ps, "pi": pi,
                }, timeout=30)
                payload = r.json()
                nov = payload.get("novels") or []
                total_page = int(payload.get("totalPage") or 0)
            except Exception:
                broken = True
                break
            out.extend(nov)
            if len(nov) < ps or (total_page and pi + 1 >= total_page):
                break
            pi += 1
            time.sleep(delay)
        if not broken and out:
            return out
    return []


def norm_roster(nov: dict, tag: int, meta: dict) -> dict | None:
    nid = nov.get("novelID") or nov.get("NovelID")
    if not nid:
        return None
    cat = nov.get("categoryID") if nov.get("categoryID") is not None else nov.get("CategoryID")
    return {
        "nid": int(nid),
        "title": nov.get("novelName") or nov.get("NovelName") or "",
        "author": nov.get("authorName") or nov.get("AuthorName") or "",
        "categoryID": cat,
        "tag": tag,
        "tag_name": meta.get("name", "?"),
        "series": meta.get("series", "?"),
    }


def step_roster(tags: list[int], delay: float, out: Path, targets: dict[int, dict]) -> None:
    sess = requests.Session()
    sess.headers.update(UA)
    done: set[int] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["tag"])
                except Exception:
                    pass
        print(f"roster 已有 {len(done)} 个 tag，断点续跑")

    fresh = out.open("a", encoding="utf-8")
    total_new = 0
    for tag in tags:
        if tag in done:
            print(f"tag {tag:4} [{targets.get(tag, {}).get('name', '?'):16}] 已采，跳过")
            continue
        meta = targets.get(tag, {})
        ep = meta.get("endpoint", "new")
        nov = fetch_new(tag, sess, delay) if ep == "new" else fetch_old(tag, sess, delay)
        uniq: dict[int, dict] = {}
        for n in nov:
            rec = norm_roster(n, tag, meta)
            if rec:
                uniq.setdefault(rec["nid"], rec)
        for rec in uniq.values():
            fresh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fresh.flush()
        total_new += len(uniq)
        print(f"tag {tag:4} [{meta.get('name', '?'):16}] 拉取 {len(nov):5} 条 → 去重 {len(uniq):5} 本")
        time.sleep(delay)
    fresh.close()
    print(f"roster 新增 {total_new} 条 → {out}")


# ---------------- step 2: dedup ----------------

def existing_nids() -> set[int]:
    ids: set[int] = set()
    if BOOKS_JSONL.exists():
        with BOOKS_JSONL.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        ids.add(int(json.loads(line)["nid"]))
                    except Exception:
                        pass
    if paths.CSV_FILE.exists():
        with paths.CSV_FILE.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    ids.add(int(row["id"]))
                except (ValueError, KeyError):
                    pass
    return ids


def step_dedup(roster: Path, out: Path) -> None:
    recs: dict[int, dict] = {}
    for line in roster.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            recs.setdefault(int(r["nid"]), r)
    have = existing_nids()
    missing = {nid: r for nid, r in recs.items() if nid not in have}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for nid in sorted(missing):
            f.write(json.dumps(missing[nid], ensure_ascii=False) + "\n")
    print(f"roster 去重 {len(recs)} 本；已有 {len(have)} 本；新 nid {len(missing)} 本 → {out}")


# ---------------- step 3: details ----------------

def fetch_app_detail(nid: int, sess: requests.Session) -> dict:
    for _ in range(3):
        try:
            r = sess.get(f"https://api.sfacg.com/novels/{nid}", timeout=20)
            payload = r.json()
            if payload.get("status", {}).get("httpCode") == 200 and isinstance(payload.get("data"), dict):
                return payload["data"]
        except Exception:
            pass
        time.sleep(1)
    return {}


def fetch_mobile(nid: int) -> dict:
    try:
        r = requests.get(f"https://m.sfacg.com/b/{nid}/", timeout=15, headers={"user-agent": MOBILE_UA})
        if len(r.text) < 5000:
            return {}
        like, coll = LIKE.search(r.text), COLL.search(r.text)
        return {
            "praises": int(like.group(1)) if like else None,
            "coll_check": int(coll.group(1)) if coll else None,
        }
    except Exception:
        return {}


def build_detail(d: dict, roster_rec: dict, mobile: dict) -> dict:
    price = SIGN_MAP.get(d.get("signStatus") or "", "免费")
    return {
        "nid": int(d.get("novelId") or d["nid"]),
        "novel_title": d.get("novelName") or roster_rec.get("title", ""),
        "author": d.get("authorName") or roster_rec.get("author", ""),
        "price_type": price,
        "contest": roster_rec.get("tag_name", ""),
        "genre": TIDS.get(d.get("typeId"), ""),
        "click_num": int(d.get("viewTimes") or 0),
        "word_num": int(d.get("charCount") or 0),
        "status": "已完结" if d.get("isFinish") else "连载中",
        "last_update": (d.get("lastUpdateTime") or "").replace("T", " "),
        "praise_num": mobile.get("praises") if mobile.get("praises") is not None else 0,
        "like_num": int(d.get("markCount") or 0),
        "cover": d.get("novelCover") or "",
        "banner": bool(d.get("bgBanner")),
        "tags": [],
        # 溯源字段（dataset build.py 只读上方 15 字段，其余留档）
        "addTime": d.get("addTime"),
        "authorId": d.get("authorId"),
        "categoryId": d.get("categoryId"),
        "tag": roster_rec.get("tag"),
        "tag_name": roster_rec.get("tag_name"),
        "series": roster_rec.get("series"),
        "observed_at": OBSERVED_AT,
        "praises_source": "mobile_html" if mobile.get("praises") is not None else "zero_fallback",
        "coll_mobile_check": mobile.get("coll_check"),
    }


def step_details(new_nids: Path, out: Path, delay: float, limit: int) -> None:
    roster: dict[int, dict] = {}
    for line in new_nids.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            roster[int(r["nid"])] = r

    done: dict[int, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    done[int(d["nid"])] = d
                except Exception:
                    pass
        print(f"details 已有 {len(done)} 本，断点续采")

    todo = [n for n in sorted(roster) if n not in done]
    if limit > 0:
        todo = todo[:limit]
    print(f"待补详情 {len(todo)} 本")

    sess = requests.Session()
    sess.headers.update(make_headers())
    ok = fallback = 0
    with out.open("a", encoding="utf-8") as fh:
        for i, nid in enumerate(todo, 1):
            d = fetch_app_detail(nid, sess)
            if not d:
                # App API 失败：不写残缺记录，留待下次重跑；避免污染 dataset
                print(f"  {i}/{len(todo)} nid={nid} App API 失败，跳过")
                continue
            mobile = fetch_mobile(nid)
            rec = build_detail(d, roster[nid], mobile)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if mobile.get("praises") is not None:
                ok += 1
            else:
                fallback += 1
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} 成功 {ok} 赞兜底 {fallback}")
            time.sleep(delay)
    print(f"details 完成 → {out}")


# ---------------- main ----------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", choices=["roster", "dedup", "details", "all"], default="all")
    ap.add_argument("--tags", default=DEFAULT_TAGS, help=f"逗号分隔 tagId，默认 14 征 {DEFAULT_TAGS}；传 all 用全部清单")
    ap.add_argument("--delay", type=float, default=0.5, help="串行间隔秒（详情 ≥0.5）")
    ap.add_argument("--roster-delay", type=float, default=0.3, help="清单间隔秒")
    ap.add_argument("--limit", type=int, default=0, help="details 最多处理多少本（0=全部，调试用）")
    ap.add_argument("--roster-out", default=str(ROSTER_OUT))
    ap.add_argument("--new-nids-out", default=str(NEW_NIDS_OUT))
    ap.add_argument("--detail-out", default=str(DETAIL_OUT))
    a = ap.parse_args()

    targets = load_targets()
    if a.tags.strip().lower() == "all":
        tags = sorted(targets)
    else:
        tags = [int(x) for x in a.tags.split(",") if x.strip()]
    unknown = [t for t in tags if t not in targets]
    if unknown:
        print(f"警告：tag {unknown} 不在目标清单，将按新端点处理")

    roster_out, new_out, detail_out = Path(a.roster_out), Path(a.new_nids_out), Path(a.detail_out)
    if a.step in ("roster", "all"):
        step_roster(tags, a.roster_delay, roster_out, targets)
    if a.step in ("dedup", "all"):
        step_dedup(roster_out, new_out)
    if a.step in ("details", "all"):
        step_details(new_out, detail_out, a.delay, a.limit)


if __name__ == "__main__":
    main()

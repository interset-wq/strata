"""`op=novelbytype` 分类枚举端点实测：末页边界、每页条数、页间重叠。

为 `references/sfacg-endpoints.md` §5 的九分类枚举规模表提供可复现依据。
这个端点是全库枚举的唯一公开通道（搜索硬截断 30 条、无分页），
所以边界数字必须能重测，否则「约 25 万本」就是不可核验的断言。

用法：
    uv run --project analysis python analysis/fetchers/probe_novelbytype.py            # 九类全测（约 6 分钟）
    uv run --project analysis python analysis/fetchers/probe_novelbytype.py --tid 21   # 只测魔幻
    uv run --project analysis python analysis/fetchers/probe_novelbytype.py --tid 21 --verify
    uv run --project analysis python analysis/fetchers/probe_novelbytype.py --tid 29 --census  # 整类普查（约 20 分钟）

边界探测写 `out/novelbytype_bounds.json`，整类普查写 `out/novelbytype_census_{tid}.json`
（均为派生物，不入库）。

**端点硬约束**（写错任一条都拿不到数据，且报错信息只有「参数不正确」）：
- 必须 POST，GET 返回 `{"Status":501,"msg":"参数不正确"}`
- 必须带 `Referer: https://m.sfacg.com/search.html?type={tid}`，按 tid 变化
- 表单字段是 `tid` + `pi`（页码，1 起）
- 每页 6 条，约 1.5 KB/页；实测 30 次连续请求不触发限流（与 HTML 搜索不同）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from lib import paths  # noqa: E402

API_HTML5 = "https://m.sfacg.com/API/HTML5.ashx"
OUT_FILE = paths.OUT_DIR / "novelbytype_bounds.json"
GAP = 0.7  # 枚举端点限流宽松，0.7 秒足够

# tid 来自 PC 分类页 book.sfacg.com/List/ 的链接参数
GENRE = {
    21: "魔幻",
    22: "玄幻",
    23: "古风",
    24: "科幻",
    25: "校园",
    26: "都市",
    27: "游戏",
    28: "同人",
    29: "悬疑",
}
PER_PAGE = 6


def _headers(tid: int) -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
        ),
        "Referer": f"https://m.sfacg.com/search.html?type={tid}",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://m.sfacg.com",
    }


def page(tid: int, pi: int, retries: int = 3) -> dict:
    """取某分类第 pi 页。空列表 = 已过末页。

    代理抖动会让单次请求抛 `ProxyError`；整类普查要跑上千次，
    不重试就等于白扫，故在请求层做 3 次退避重试。
    """
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.post(
                API_HTML5,
                params={"op": "novelbytype"},
                data={"tid": str(tid), "pi": pi},
                headers=_headers(tid),
                timeout=25,
            )
            break
        except requests.RequestException as exc:  # 网络/代理故障
            last_err = exc
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    else:  # pragma: no cover
        raise RuntimeError(f"tid={tid} pi={pi} 重试耗尽") from last_err

    body = r.json()
    novels = body.get("Novels") or []
    return {
        "status": r.status_code,
        "api_status": body.get("Status"),
        "bytes": len(r.content),
        "ids": [x.get("NovelID") for x in novels],
        "items": [
            {
                "id": x.get("NovelID"),
                "title": x.get("NovelName"),
                "author": x.get("AuthorName"),
                "type": x.get("TypeName"),
                "score": x.get("Point"),
                "last": x.get("LastUpdate"),
            }
            for x in novels
        ],
    }


def find_last_page(tid: int, hi: int = 40000) -> int:
    """二分找最后一个非空页。

    不变式：`lo` 恒为非空页，`hi` 恒为空页，收敛到 `hi - lo == 1` 时 `lo` 即末页。
    末页上界 40000 页 ≈ 24 万本，够覆盖任何单分类；触到上界说明规模超预期，需复查。
    """
    lo = 1
    if not page(tid, lo)["ids"]:
        return 0
    if page(tid, hi)["ids"]:
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if page(tid, mid)["ids"]:
            lo = mid
        else:
            hi = mid
        time.sleep(GAP)
    return lo


def verify(tid: int, last: int, overlap: int = 2) -> dict:
    """校验三条结构假设：每页 6 条、重复请求稳定、相邻页不重叠。"""
    a = page(tid, 1)
    time.sleep(GAP)
    a2 = page(tid, 1)
    b = page(tid, 2) if last >= 2 else {"ids": []}
    time.sleep(GAP)
    tail_from = max(1, last - overlap)
    tails = []
    for pi in range(tail_from, last + 1):
        tails.append({"pi": pi, "ids": page(tid, pi)["ids"]})
        time.sleep(GAP)
    adjacent_pairs = [
        (tails[i]["pi"], tails[i + 1]["pi"], tails[i]["ids"], tails[i + 1]["ids"])
        for i in range(len(tails) - 1)
    ]
    overlaps = [
        {"p1": p1, "p2": p2, "shared": sorted(set(i1) & set(i2))} for p1, p2, i1, i2 in adjacent_pairs
    ]
    return {
        "per_page": [len(a["ids"]), len(b["ids"])],
        "per_page_bytes": [a["bytes"], b["bytes"]],
        "repeat_stable": a["ids"] == a2["ids"],
        "page1_vs_page2_overlap": sorted(set(a["ids"]) & set(b["ids"])),
        "tail_overlaps": overlaps,
        "tail_pages": tails,
    }


def census(tid: int, last: int) -> dict:
    """整类普查：唯一 nid、重复、空页、与库内/库外的双向差额。

    §5.1 的覆盖口径冲突就是靠这个函数定案的：只有整类扫完才能区分
    「枚举缺书」与「库缺书」，抽样做不到。
    """
    import pandas as pd

    from lib import paths as _paths

    df = pd.read_csv(_paths.CSV_FILE, usecols=["id", "genre"])
    lib = set(df.id.tolist())
    lib_genre = set(df[df.genre == GENRE.get(tid)].id.tolist())
    snap_max = int(df.id.max())  # 快照最大 nid，大于它的都是扫描结束后新建的
    allids: list[int] = []
    empty_pages: list[int] = []
    for pi in range(1, last + 4):  # 多扫 3 页，确认「过末页即空」
        r = page(tid, pi)
        if not r["ids"]:
            empty_pages.append(pi)
        allids += r["ids"]
        time.sleep(0.3)
        if (pi % 200) == 0:
            print(f"    … {pi}/{last + 3} 页，累计 {len(allids)} 条")
    uniq = set(allids)
    outside = uniq - lib
    lib_same = lib_genre
    return {
        "genre": GENRE.get(tid),
        "pages": last + 3,
        "items": len(allids),
        "unique": len(uniq),
        "duplicates": len(allids) - len(uniq),
        "empty_pages": empty_pages,
        "in_library": len(uniq & lib),
        "outside_library": len(outside),
        # 库外要拆成「快照后新建」与「同范围内真遗漏」，否则会把时间差当成漏抓
        "snapshot_max_nid": snap_max,
        "outside_after_snapshot": len([x for x in outside if x > snap_max]),
        "outside_in_range": sorted(x for x in outside if x <= snap_max),
        "library_same_genre": len(lib_same),
        "library_not_enumerated": sorted(lib_same - uniq),
        "all_ids": sorted(uniq),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="novelbytype 分类枚举探测")
    ap.add_argument("--tid", type=int, action="append", help="只测指定分类（可重复）；缺省测九类")
    ap.add_argument("--verify", action="store_true", help="额外校验每页条数/稳定性/页间重叠")
    ap.add_argument("--census", action="store_true", help="对 --tid 指定分类整类普查（约 20 分钟/类）")
    args = ap.parse_args()

    if args.census:
        if not args.tid:
            ap.error("--census 需要 --tid（整类普查一次只做一类）")
        tid = args.tid[0]
        print(f"整类普查 tid={tid}（{GENRE.get(tid, '?')}）…")
        last = find_last_page(tid)
        c = census(tid, last)
        print(
            f"  页 {c['pages']}，条目 {c['items']}，唯一 {c['unique']}，重复 {c['duplicates']}\n"
            f"  空页 {c['empty_pages'][:6]}{'…' if len(c['empty_pages']) > 6 else ''}\n"
            f"  库内 {c['in_library']}（{c['in_library'] / c['unique'] * 100:.1f}%）\n"
            f"  库外 {c['outside_library']} ＝ 快照后新建 {c['outside_after_snapshot']}"
            f"（nid>{c['snapshot_max_nid']}）＋ 同范围真遗漏 {len(c['outside_in_range'])}"
            f"（{(len(c['outside_in_range']) / (c['unique'] - c['outside_after_snapshot']) * 100):.2f}%）\n"
            f"  同类库内共 {c['library_same_genre']}，其中"
            f"{len(c['library_not_enumerated'])}（{len(c['library_not_enumerated']) / c['library_same_genre'] * 100:.1f}%）不在目录里"
        )
        paths.OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_file = paths.OUT_DIR / f"novelbytype_census_{tid}.json"
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(c, fh, ensure_ascii=False, indent=2)
        print(f"写出 {out_file.relative_to(paths.ROOT)}")
        return

    tids = args.tid or sorted(GENRE)
    out: dict = {"probed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "per_page": PER_PAGE, "by_genre": {}}
    total = 0

    for tid in tids:
        name = GENRE.get(tid, "?")
        last = find_last_page(tid)
        tail = page(tid, last)
        est = last * PER_PAGE
        total += est
        entry = {
            "genre": name,
            "last_page": last,
            "approx": est,
            "tail_fill": len(tail["ids"]),
            "tail_ids": tail["ids"],
        }
        if args.verify:
            entry["verify"] = verify(tid, last)
        out["by_genre"][str(tid)] = entry
        print(f"  {name}(tid={tid}): 末页 {last}，约 {est:,} 本；末页填充 {len(tail['ids'])}/{PER_PAGE}")
        time.sleep(0.8)

    out["total_approx"] = total
    print(f"\n合计约 {total:,} 本（{len(tids)} 类）")

    paths.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"写出 {OUT_FILE.relative_to(paths.ROOT)}")


if __name__ == "__main__":
    main()

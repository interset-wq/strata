"""SFACG 端点实测探针：为 `references/sfacg-endpoints.md` 提供可复现数据。

只依赖 `requests`，不引用上游 `sfacg_tools`——那份代码不在仓库内，
本脚本必须能在干净 checkout 上直接跑通，否则参考档案里的数字无法自证。

用法：
    uv run --project analysis python analysis/fetchers/probe_sfacg_api.py
    uv run --project analysis python analysis/fetchers/probe_sfacg_api.py --stress 20

结果写 `out/sfacg_api_probe.json`（派生物，不入库）。

**探测间隔是硬约束**：HTML 搜索连续 ~17 次后会进入静默限流（HTTP 200、
结构正常的页面、标题变成「请输入关键字」），且持续数分钟不掉。
脚本对每次请求强制 sleep `GAP` 秒，`--stress` 是唯一绕过它的入口，运行后
分钟级内不要再用 HTML 搜索，否则所有结果都会被污染成 0 条。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from lib import paths  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
SEARCH_BASE = "https://s.sfacg.com/"
API_HTML5 = "https://m.sfacg.com/API/HTML5.ashx"
API_BOOK = "https://m.sfacg.com/API/Book.ashx"
GAP = 6.0  # 单次探测间隔（秒），低于 5 秒会显著提高限流概率
OUT_FILE = paths.OUT_DIR / "sfacg_api_probe.json"

# ── HTML 搜索页解析 ────────────────────────────────────────────────
# 结构（2026-11-16 实测）：
#   <ul style="width:100%"><li class="Conjunction"><img … alt="标题" /></li>
#   <li><strong class="F14PX"><a href="…/Novel/{nid}" …>标题</a></strong><br />
#     综合信息： 作者/2024/3/25 20:57:58<br />  简介…</li></ul>
_BLOCK = re.compile(r"<ul style=\"width:100%\">(.*?)</ul>", re.S)
_NID = re.compile(r"book\.sfacg\.com/Novel/(\d+)")
_TITLE = re.compile(r'class="orange_link2">(.*?)</a>', re.S)
_COVER = re.compile(r'<img src="([^"]+)"')
_INFO = re.compile(r"综合信息：\s*(.*?)<br\s*/?>", re.S)
_DECLARED = re.compile(r"共搜索到\s*(\d+)\s*个结果")
_THROTTLE = "请输入关键字"


def html_search(keyword: str, extra: dict | None = None) -> dict:
    """直接打 HTML 搜索，保留原始计数、限流指纹与逐条字段。

    不复用任何库：上游 `_parse_html_results` 不检查限流指纹，
    会静默返回空列表，用它做探针会把限流误判成「无结果」。
    """
    params = {"Key": keyword, "SS": "0", "S": "1"}
    if extra:
        params.update(extra)
    r = requests.get(SEARCH_BASE, params=params, headers={"User-Agent": UA}, timeout=25)
    r.encoding = "utf-8"
    html = r.text

    items = []
    for block in _BLOCK.findall(html):
        nid = _NID.search(block)
        if not nid:
            continue
        title = _TITLE.search(block)
        cover = _COVER.search(block)
        info = _INFO.search(block)
        info_txt = re.sub(r"\s+", " ", info.group(1)).strip() if info else ""
        author, _, updated = info_txt.partition("/")
        items.append(
            {
                "id": int(nid.group(1)),
                "title": re.sub(r"\s+", " ", title.group(1)).strip() if title else None,
                "cover": cover.group(1) if cover else None,
                "author": author.strip() or None,
                "updated": updated.strip() or None,
            }
        )

    declared = _DECLARED.search(html)
    return {
        "params": params,
        "status": r.status_code,
        "bytes": len(r.content),
        "declared": int(declared.group(1)) if declared else None,
        "returned": len(items),
        "ids": [x["id"] for x in items],
        "items": items,
        "throttled": _THROTTLE in html,
    }


def json_search(keyword: str) -> dict:
    """H5 JSON 搜索。返回 6–15 条（中位 12），`Tags` 恒为 null。"""
    r = requests.get(
        API_HTML5,
        params={"op": "search", "keyword": keyword, "_": int(time.time() * 1000)},
        headers={"User-Agent": UA},
        timeout=20,
    )
    body = r.json()
    novels = body.get("Novels") or []
    return {
        "status": r.status_code,
        "bytes": len(r.content),
        "n": len(novels),
        "ids": [int(x["NovelID"]) for x in novels],
        "top_keys": list(body.keys()),
        "item_keys": list(novels[0].keys()) if novels else [],
        "tags_nonnull": sum(1 for x in novels if x.get("Tags")),
        "items": [
            {
                "id": int(x["NovelID"]),
                "title": x.get("NovelName"),
                "author": x.get("AuthorName"),
                "score": x.get("Point"),
                "type": x.get("TypeName"),
            }
            for x in novels
        ],
    }


def reffer_search(keyword: str) -> dict:
    """联想词（`op=searchreffer`）。只返回书名，**没有 nid**，不能当搜索用。"""
    r = requests.post(
        API_BOOK,
        params={"op": "searchreffer"},
        data={"keyword": keyword},
        headers={
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://m.sfacg.com",
            "Referer": "https://m.sfacg.com/search.html",
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=20,
    )
    body = r.json()
    return {
        "status": r.status_code,
        "bytes": len(r.content),
        "n": len(body.get("keywords") or []),
        "keywords": body.get("keywords") or [],
    }


def section_cap(out: dict) -> None:
    """§1 HTML 搜索条数上限：宣称值与实际返回条数的关系。"""
    print("[1/9] HTML 搜索条数上限 …")
    rows = []
    for kw in ["英雄", "重生", "少女", "的", "魔法", "转生"]:
        r = html_search(kw)
        rows.append({k: r[k] for k in ("params", "status", "bytes", "declared", "returned", "throttled")})
        print(f"  {kw}: 宣称={r['declared']} 返回={r['returned']} 限流={r['throttled']}")
        time.sleep(GAP)
    out["html_cap"] = rows


def section_paging(out: dict) -> None:
    """§2 分页参数是否有效：Page/page/pi/PageIndex/PageSize 全部无效。"""
    print("[2/9] HTML 分页参数 …")
    base = html_search("重生")
    time.sleep(GAP)
    tests = []
    for extra in [{"Page": "2"}, {"page": "2"}, {"pi": "2"}, {"PageIndex": "2"}, {"PageSize": "50"}]:
        r = html_search("重生", extra)
        tests.append(
            {
                "extra": extra,
                "returned": r["returned"],
                "same_as_base": r["ids"] == base["ids"],
                "first": r["ids"][0] if r["ids"] else None,
            }
        )
        print(f"  {extra}: 返回={r['returned']} 与基线相同={tests[-1]['same_as_base']}")
        time.sleep(GAP)
    out["html_paging"] = {"base_n": base["returned"], "base_first": base["ids"][0] if base["ids"] else None, "tests": tests}


def section_ss_s(out: dict) -> None:
    """§3 `SS` / `S` 参数语义：完全无效（四组组合结果一致）。"""
    print("[3/9] SS / S 参数语义 …")
    rows = []
    for ss, s in [("0", "1"), ("1", "1"), ("0", "0"), ("2", "1")]:
        r = html_search("英雄", {"SS": ss, "S": s})
        rows.append({"SS": ss, "S": s, "returned": r["returned"], "throttled": r["throttled"]})
        print(f"  SS={ss} S={s}: 返回={r['returned']}")
        time.sleep(GAP)
    out["html_ss_s"] = rows


def section_three_way(out: dict, kw: str = "英雄") -> None:
    """§4 三接口集合关系：JSON ⊂ HTML 但非前缀；reffer 只给书名。"""
    print("[4/9] 三接口集合关系 …")
    h = html_search(kw)
    time.sleep(GAP)
    j = json_search(kw)
    time.sleep(GAP)
    p = reffer_search(kw)
    time.sleep(GAP)

    hid, jid = h["ids"], j["ids"]
    hpos = {nid: i for i, nid in enumerate(hid)}
    out["three_way"] = {
        "kw": kw,
        "html_n": len(hid),
        "json_n": len(jid),
        "reffer_n": p["n"],
        "json_only": sorted(set(jid) - set(hid)),
        "html_only_n": len(set(hid) - set(jid)),
        "json_is_prefix_of_html": jid == hid[: len(jid)],
        "json_positions_in_html": [hpos.get(n) for n in jid],
        "html_items": h["items"],
        "json_items": j["items"],
        "reffer_keywords": p["keywords"],
    }
    print(
        f"  HTML={len(hid)} JSON={len(jid)} 联想={p['n']} "
        f"JSON 独有={len(out['three_way']['json_only'])} JSON 是前缀={out['three_way']['json_is_prefix_of_html']}"
    )


def section_fields(out: dict) -> None:
    """§5 HTML 字段完整度：简介/更新时间/封面/作者的覆盖率。"""
    print("[5/9] HTML 字段完整度 …")
    r = html_search("魔法")
    out["html_fields"] = {
        "kw": "魔法",
        "n": r["returned"],
        "with_title": sum(1 for x in r["items"] if x["title"]),
        "with_cover": sum(1 for x in r["items"] if x["cover"]),
        "with_author": sum(1 for x in r["items"] if x["author"]),
        "with_updated": sum(1 for x in r["items"] if x["updated"]),
        "sample": r["items"][:5],
    }
    f = out["html_fields"]
    print(f"  标题={f['with_title']} 封面={f['with_cover']} 作者={f['with_author']} 更新时间={f['with_updated']} / {f['n']}")
    time.sleep(GAP)


def section_self_hit(out: dict, n: int = 12) -> None:
    """§6 精确书名自命中：随机抽库内书名搜回去，看是否命中且排第一。"""
    print("[6/9] 精确书名自命中 …")
    import pandas as pd

    d = pd.read_csv(paths.CSV_FILE, usecols=["id", "title"], dtype={"title": str})
    sample = d[d.title.str.len().between(6, 14)].sample(n, random_state=11)
    rows = []
    for _, row in sample.iterrows():
        r = html_search(row.title)
        rows.append(
            {
                "title": row.title,
                "nid": int(row.id),
                "declared": r["declared"],
                "returned": r["returned"],
                "rank": (r["ids"].index(int(row.id)) + 1) if int(row.id) in r["ids"] else None,
            }
        )
        print(f"  {row.title[:16]} → 名次 {rows[-1]['rank']}")
        time.sleep(GAP)
    out["self_hit"] = {
        "n": len(rows),
        "hits": sum(1 for x in rows if x["rank"]),
        "top1": sum(1 for x in rows if x["rank"] == 1),
        "detail": rows,
    }
    print(f"  命中 {out['self_hit']['hits']}/{n}，第一 {out['self_hit']['top1']}/{n}")


def section_json_reffer_raw(out: dict, kw: str = "英雄") -> None:
    """§7 JSON 与联想的原始字段清单（给参考档案做字段表）。"""
    print("[7/9] JSON / 联想 原始字段 …")
    j = json_search(kw)
    time.sleep(GAP)
    p = reffer_search(kw)
    out["json_raw"] = {k: j[k] for k in ("status", "bytes", "n", "top_keys", "item_keys", "tags_nonnull")}
    out["reffer_raw"] = {k: p[k] for k in ("status", "bytes", "n")}
    print(f"  JSON keys={j['item_keys']} Tags非空={j['tags_nonnull']}/{j['n']}")


def section_stress(out: dict, n: int) -> None:
    """§8 限流压力测试：连续请求直到出现「请输入关键字」，测触发阈值。"""
    print(f"[8/9] 限流压力测试（连续 {n} 次，不 sleep）…")
    rows = []
    for i in range(n):
        r = html_search("英雄")
        rows.append({"i": i + 1, "returned": r["returned"], "declared": r["declared"], "throttled": r["throttled"]})
        if r["throttled"]:
            print(f"  第 {i + 1} 次起被静默限流")
            break
        if (i + 1) % 5 == 0:
            print(f"  已完成 {i + 1} 次，仍正常")
    out["stress"] = {
        "attempted": len(rows),
        "throttled_at": next((x["i"] for x in rows if x["throttled"]), None),
        "rows": rows,
    }


def section_status_trap(out: dict, valid_nid: int = 48704) -> None:
    """§9 状态码陷阱：无效 nid 也返回 HTTP 200，判存在必须查文案。

    这一节的存在是因为报告 10 的存活判据（>5KB 含书名）依赖体积阈值，
    换版式即失效；而本站对不存在的 id 一律返回 200，状态码零信息量。
    """
    print("[9/9] 状态码陷阱（无效 nid）…")
    rows = []
    for label, url, marker in [
        ("pc_invalid", f"https://book.sfacg.com/Novel/{9_999_999}/", "小说不存在"),
        ("m_invalid", f"https://m.sfacg.com/b/{9_999_999}/", "出错啦"),
        ("pc_valid", f"https://book.sfacg.com/Novel/{valid_nid}/", "小说不存在"),
    ]:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        r.encoding = "utf-8"
        title = re.search(r"<title>(.*?)</title>", r.text, re.S)
        rows.append(
            {
                "case": label,
                "status": r.status_code,
                "bytes": len(r.content),
                "title": re.sub(r"\s+", " ", title.group(1)).strip()[:40] if title else None,
                "negative_marker": marker in r.text,
                "marker": marker,
            }
        )
        print(f"  {label}: HTTP {r.status_code}, {len(r.content)} B, 含「{marker}」={marker in r.text}")
        time.sleep(1.5)
    out["status_trap"] = {
        "rows": rows,
        "conclusion": "无效 nid 返回 200；PC 1.6KB/「小说不存在」、移动 3.7KB/「出错啦」——判活只能查文案",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="SFACG 端点实测探针")
    ap.add_argument("--stress", type=int, default=0, metavar="N", help="连续请求 N 次测限流阈值（会触发数分钟不可用）")
    ap.add_argument("--skip", default="", help="跳过的小节编号，逗号分隔，如 6")
    args = ap.parse_args()

    skip = {x.strip() for x in args.skip.split(",") if x.strip()}
    out: dict = {"probed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    # §6 依赖 novels.csv，缺失时可单独跳过
    if "6" not in skip and not paths.CSV_FILE.exists():
        print(f"! 缺 {paths.CSV_FILE.name}，跳过第 6 节（先跑 pipeline/build_csv.py）")
        skip.add("6")
    if "8" not in skip and args.stress <= 0:
        skip.add("8")

    steps = [
        ("1", section_cap),
        ("2", section_paging),
        ("3", section_ss_s),
        ("4", section_three_way),
        ("5", section_fields),
        ("6", section_self_hit),
        ("7", section_json_reffer_raw),
    ]
    for num, fn in steps:
        if num in skip:
            print(f"[{num}/9] 跳过")
            continue
        fn(out)
    if "9" not in skip:
        section_status_trap(out)
    if "8" not in skip:
        section_stress(out, args.stress)

    paths.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n写出 {OUT_FILE.relative_to(paths.ROOT)}")
    for k, v in out.items():
        print(f"  {k}: {'…' if isinstance(v, (list, dict)) else v}")


if __name__ == "__main__":
    main()

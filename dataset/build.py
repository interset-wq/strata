"""构建正式书籍数据集：novel_hub 原始 jsonl → 唯一真源 `books.jsonl` + 派生 `books.csv`。

口径（2026-11-18 用户定）：
- **不 drop 任何书**：本数据集不是分析口径，不做授权剔除、不做存活判定、不按收藏/字数过滤。
  唯一被"合并"的是同一个 `nid` 的多行抓取记录（同一本书被重复抓到），不是删书。
- **只做最基本的字符串处理**：NFC 规范化、控制符/零宽字符→空格、连续空白折叠、去首尾空白。
- **URL 不改写**：保留原始完整 URL；唯一的例外是**默认封面置空串**
  （`defaultNew.jpg` / `default[1].jpg` 等 `default*` 文件，源站根本没给封面）。
- **授权 47 本封面覆盖**：`cover-check/` 是 2026-11-17 重取的当期封面，比快照新，直接覆盖。
- **采集封面并入**：`analysis/out/cover_urls.jsonl`（2026-11-18 逐本 App 采集，10,509 本）
  覆盖 `cover`（采集到默认图不覆盖）。只动 `cover`，不动任何计数字段
  （避免把 11 月的数值混进 5 月快照）。
- **共享封面 = jsonl 抓取伪影，一律置空**（2026-11-18 定案）：原始 jsonl 的 `cover`
  对约 12.4 万本书记的是**页面推荐位里其他书的封面**，不是本书封面。证据：三本抽样
  （nid 594446/594543/239797）官网页面 HTML 中本书真实封面出现两次、共享图只出现一次，
  且 App API 返回的 novelCover 均为前者；而 App 采集的 10,353 张真实封面零重复
  （站方封面 URL 唯一）。判定：同一 `cover` URL 被 ≥2 本书引用 → 全部置空。

用法：
    cd dataset && uv run python build.py [--src GLOB] [--covers PATH] [--crawl PATH] [--out DIR]

产物（`dataset/out/`，不入库）：
    books.jsonl     每行一本书，15 字段，tags 仍是数组
    books.csv       同字段扁平表，tags 用 `|` 连接，banner 为 0/1
    cleanup.jsonl   清洗审计：被替换的字符、被置空的默认封面、被覆盖的授权封面
    manifest.json   输入 sha256、行数、去重数、字段表、输出 sha256
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DEFAULT = str(ROOT / "analysis" / "data" / "extracted" / "dataset" / "data" / "meta*.jsonl")
COVERS_DEFAULT = ROOT / "cover-check" / "covers_raw.jsonl"
CRAWL_DEFAULT = ROOT / "analysis" / "out" / "cover_urls.jsonl"
OUT_DEFAULT = Path(__file__).resolve().parent / "out"

FIELDS = [
    "nid", "novel_title", "author", "price_type", "contest", "genre",
    "click_num", "word_num", "status", "last_update", "praise_num", "like_num",
    "cover", "banner", "tags",
]
TEXT_FIELDS = ["novel_title", "author", "price_type", "contest", "genre", "status", "last_update"]
INT_FIELDS = ["click_num", "word_num", "praise_num", "like_num"]

# C0/C1 控制符、DEL、零宽字符、行/段分隔符、BOM
ILLEGAL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\ufeff]")
WS_RUN = re.compile(r"\s+")


def clean_text(value: object, field: str, audit: list[dict], nid: int) -> str:
    """NFC → 非法字符替换为空格 → 空白折叠 → 去首尾空白。"""
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFC", s)
    hits = ILLEGAL.findall(s)
    if hits:
        s = ILLEGAL.sub(" ", s)
        audit.append({"nid": nid, "field": field, "kind": "illegal_chars",
                      "count": len(hits),
                      "codepoints": sorted({"U+%04X" % ord(c) for c in hits})})
    s = WS_RUN.sub(" ", s).strip()
    return s


def clean_int(value: object, field: str, audit: list[dict], nid: int) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        audit.append({"nid": nid, "field": field, "kind": "unparsable_int",
                      "raw": str(value)[:40]})
        return None


def is_default_cover(url: str) -> bool:
    """源站的占位封面：文件名以 default 开头（defaultNew.jpg / default[1].jpg）。"""
    return url.rsplit("/", 1)[-1].lower().startswith("default")


def load_records(pattern: str) -> tuple[list[dict], list[dict], list[dict]]:
    """读入全部 jsonl，返回 (记录, 输入清单, 清洗审计)。"""
    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f"没有匹配的输入文件：{pattern}")
    inputs, audit, records = [], [], []
    for path in files:
        p = Path(path)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        lines = 0
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                lines += 1
                raw = json.loads(line)
                nid = int(raw["nid"])
                rec = {"nid": nid}
                for f in TEXT_FIELDS:
                    rec[f] = clean_text(raw.get(f), f, audit, nid)
                for f in INT_FIELDS:
                    rec[f] = clean_int(raw.get(f), f, audit, nid)
                rec["cover"] = clean_text(raw.get("cover"), "cover", audit, nid)
                rec["banner"] = bool(raw.get("banner"))
                tags = raw.get("tags") or []
                cleaned = []
                for t in tags if isinstance(tags, list) else []:
                    t2 = clean_text(t, "tags", audit, nid)
                    if t2:
                        cleaned.append(t2)
                rec["tags"] = cleaned
                records.append(rec)
        inputs.append({"path": str(p.relative_to(ROOT)).replace("\\", "/"),
                       "lines": lines, "sha256": digest})
    return records, inputs, audit


def dedupe(records: list[dict]) -> list[dict]:
    """同一 nid 多次抓到：留 last_update 最新的一条；并列时取文件中靠后的一条。"""
    best: dict[int, tuple[str, int, dict]] = {}
    for seq, rec in enumerate(records):
        key = (rec.get("last_update") or "", seq)
        cur = best.get(rec["nid"])
        if cur is None or key > (cur[0], cur[1]):
            best[rec["nid"]] = (key[0], seq, rec)
    return [best[nid][2] for nid in sorted(best)]


def apply_cover_rules(records: list[dict], covers_path: Path, crawl_path: Path | None,
                      audit: list[dict]) -> tuple[dict[str, int], dict[int, str], dict[int, str]]:
    """默认封面置空 → 授权 47 本用 cover-check 覆盖 → 采集封面覆盖（默认图不覆盖）。"""
    stats = {"default_blanked": 0, "empty_cover": 0, "licensed_overrides": 0,
             "crawl_applied": 0, "crawl_refreshed": 0, "crawl_default_skipped": 0,
             "crawl_unmatched": 0}
    for rec in records:
        url = rec["cover"]
        if not url:
            stats["empty_cover"] += 1
        elif is_default_cover(url):
            rec["cover"] = ""
            stats["default_blanked"] += 1   # 逐本可反查：cover 为空即源站默认图，不重复落审计
    licensed: dict[int, str] = {}
    if covers_path.exists():
        by_nid = {r["nid"]: r for r in records}
        for line in covers_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            nid, url = int(item["nid"]), (item.get("cover") or "").strip()
            if not url or nid not in by_nid:
                continue
            licensed[nid] = url
            prev = by_nid[nid]["cover"]
            by_nid[nid]["cover"] = url
            if prev != url:
                stats["licensed_overrides"] += 1
                audit.append({"nid": nid, "field": "cover", "kind": "licensed_override",
                              "before": prev})

    # 采集封面：只取真实图；官方已换回默认图的不覆盖（留给共享伪影判定统一置空）
    expected: dict[int, str] = {}
    if crawl_path is not None and crawl_path.exists():
        by_nid = {r["nid"]: r for r in records}
        for line in crawl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            nid = int(item["nid"])
            url = (item.get("cover_url") or "").strip()
            rec = by_nid.get(nid)
            if rec is None:
                stats["crawl_unmatched"] += 1
                continue
            if not url:
                continue
            if is_default_cover(url):
                stats["crawl_default_skipped"] += 1
                continue
            if nid in licensed:
                continue          # cover-check 更新更晚，且两者无交集
            prev = rec["cover"]
            rec["cover"] = url
            expected[nid] = url
            stats["crawl_applied"] += 1
            if prev != url:
                stats["crawl_refreshed"] += 1
                audit.append({"nid": nid, "field": "cover", "kind": "crawl_cover_refresh",
                              "before": prev.rsplit("/", 1)[-1]})

    # 共享封面 = jsonl 伪影（抓到了推荐位里别的书），全部置空
    counts: dict[str, int] = {}
    for rec in records:
        if rec["cover"]:
            counts[rec["cover"]] = counts.get(rec["cover"], 0) + 1
    shared_urls = {u for u, n in counts.items() if n > 1}
    stats["shared_groups"] = len(shared_urls)
    stats["shared_blanked"] = 0
    for rec in records:
        if rec["cover"] in shared_urls:
            rec["cover"] = ""
            stats["shared_blanked"] += 1
    return stats, licensed, expected


def verify(records: list[dict], licensed: dict[int, str], expected: dict[int, str],
           stats: dict[str, int]) -> None:
    """构建即断言：口径不满足就直接失败，不产出可疑数据。"""
    problems = []
    dead = 0
    for rec in records:
        url = rec["cover"]
        if url:
            if not url.startswith(("http://", "https://")):
                problems.append(f"封面不是绝对 URL：nid={rec['nid']} {url[:60]}")
            elif is_default_cover(url):
                dead += 1
        for f in TEXT_FIELDS + ["cover"]:
            if ILLEGAL.search(rec[f] or ""):
                problems.append(f"残留非法字符：nid={rec['nid']} field={f}")
        for t in rec["tags"]:
            if ILLEGAL.search(t) or not t:
                problems.append(f"标签未清洗：nid={rec['nid']} tag={t!r}")
    if dead:
        problems.append(f"{dead} 条默认封面未置空")
    expected.update(licensed)
    if expected:
        by_nid = {r["nid"]: r["cover"] for r in records}
        wrong = [nid for nid, url in expected.items() if by_nid.get(nid) != url]
        if wrong:
            problems.append(f"{len(wrong)} 本封面未按最新来源覆盖（例 nid={wrong[0]}）")
    if len({r["nid"] for r in records}) != len(records):
        problems.append("nid 仍有重复")
    seen: dict[str, int] = {}
    for rec in records:
        if rec["cover"]:
            seen[rec["cover"]] = seen.get(rec["cover"], 0) + 1
    dupn = sum(1 for n in seen.values() if n > 1)
    if dupn:
        problems.append(f"仍有 {dupn} 个封面 URL 被多本引用（共享伪影未清干净）")
    if problems:
        for p in problems[:20]:
            print("  ✗", p, file=sys.stderr)
        raise SystemExit(f"断言失败：{len(problems)} 项")


def write_outputs(records: list[dict], out_dir: Path) -> dict[str, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jl = out_dir / "books.jsonl"
    with jl.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps({f: rec[f] for f in FIELDS}, ensure_ascii=False) + "\n")
    cp = out_dir / "books.csv"
    with cp.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FIELDS)
        for rec in records:
            row = []
            for f in FIELDS:
                v = rec[f]
                if f == "tags":
                    row.append("|".join(v))
                elif f == "banner":
                    row.append("1" if v else "0")
                elif v is None:
                    row.append("")
                else:
                    row.append(v)
            w.writerow(row)
    return {
        "books.jsonl": {"lines": len(records), "sha256": sha256(jl)},
        "books.csv": {"lines": len(records) + 1, "sha256": sha256(cp)},
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=SRC_DEFAULT, help="原始 jsonl 通配符")
    ap.add_argument("--covers", default=str(COVERS_DEFAULT), help="授权封面 jsonl")
    ap.add_argument("--crawl", default=str(CRAWL_DEFAULT),
                    help="App 采集结果 jsonl（只取 cover_url，默认图不覆盖）")
    ap.add_argument("--out", default=str(OUT_DEFAULT), help="产物目录")
    ap.add_argument("--version", default="20260503.1", help="数据集版本号")
    args = ap.parse_args()

    records, inputs, audit = load_records(args.src)
    lines_read = sum(i["lines"] for i in inputs)
    books = dedupe(records)
    crawl_path = Path(args.crawl) if args.crawl else None
    stats, licensed, expected = apply_cover_rules(books, Path(args.covers), crawl_path, audit)
    verify(books, licensed, expected, stats)
    out_dir = Path(args.out)
    outputs = write_outputs(books, out_dir)

    kinds: dict[str, int] = {}
    for a in audit:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    if crawl_path is not None and crawl_path.exists():
        inputs.append({"path": str(crawl_path.resolve().relative_to(ROOT)).replace("\\", "/"),
                       "lines": len(crawl_path.read_text(encoding="utf-8").splitlines()),
                       "sha256": sha256(crawl_path), "role": "crawl_covers"})
    manifest = {
        "dataset": "strata-books",
        "version": args.version,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "content_upper_bound": max(r["last_update"] for r in books if r["last_update"]),
        "scope": "全量书籍目录，不做授权剔除与存活判定；不用于分析口径",
        "fields": FIELDS,
        "inputs": inputs,
        "counts": {
            "lines_read": lines_read,
            "books": len(books),
            "duplicate_rows_merged": lines_read - len(books),
            **stats,
            "with_tags": sum(1 for r in books if r["tags"]),
        },
        "cleanup": kinds,
        "outputs": outputs,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "cleanup.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for a in audit:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")

    print(f"输入 {len(inputs)} 个文件 / {lines_read:,} 行")
    print(f"书籍 {len(books):,} 本（合并重复行 {lines_read - len(books):,} 行）")
    print(f"默认封面置空 {stats['default_blanked']:,} | 空封面 {stats['empty_cover']:,} "
          f"| 授权封面覆盖 {stats['licensed_overrides']} 本")
    print(f"采集封面：应用 {stats['crawl_applied']:,} 本（其中替换旧图 "
          f"{stats['crawl_refreshed']:,}）| 官方已换默认图 "
          f"{stats['crawl_default_skipped']} | 未匹配 {stats['crawl_unmatched']}")
    print(f"共享伪影封面：{stats['shared_groups']:,} 个 URL / {stats['shared_blanked']:,} 本 → 置空")
    print(f"清洗：{kinds or '无'}")
    print(f"产物 → {out_dir}（books.jsonl / books.csv / cleanup.jsonl / manifest.json）")


if __name__ == "__main__":
    main()

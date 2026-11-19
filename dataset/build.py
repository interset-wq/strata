"""构建正式书籍数据集：novel_hub 原始 jsonl → 唯一真源 `books.jsonl` + 派生 `books.csv`。

口径（2026-11-18 用户定）：
- **不 drop 任何书**：本数据集不是分析口径，不做授权剔除、不做存活判定、不按收藏/字数过滤。
  唯一被"合并"的是同一个 `nid` 的多行抓取记录（同一本书被重复抓到），不是删书。
- **只做最基本的字符串处理**：NFC 规范化、控制符/零宽字符→空格、连续空白折叠、去首尾空白。
- **URL 不改写**：保留原始完整 URL；唯一的例外是**默认封面置空串**
  （`defaultNew.jpg` / `default[1].jpg` 等 `default*` 文件，源站根本没给封面）。
- **授权 47 本封面覆盖**：`cover-check/` 是 2026-11-17 重取的当期封面，比快照新，直接覆盖。
- **采集封面并入**：两份 App API 来源按「旧样本 → 新逐本采集」顺序覆盖 `cover`：
  ① `analysis/out/app_api_novels.jsonl`（2026-11-16/17 全字段样本，取 `novelCover`）；
  ② `analysis/out/cover_urls.jsonl`（2026-11-18/19 逐本采集，11,367 本）。
  采集到默认图不覆盖。只动 `cover`，不动任何计数字段（避免把 11 月的数值混进 5 月快照）。
- **共享封面按「同作者 nid 最大者」重新归属**（2026-11-18 用户定案）：原始 jsonl 的
  `cover` 对约 12 万本书记的是**同作者另一本书（作者其他作品推荐位）的封面**——
  novel_hub 爬虫选择器写错。真主人 = 同作者作品里 nid 最大的那本。
  证据：38,518 个共享组 100% 同作者；App API 抽查 5 组（4 组主人封面 == 共享图，
  同组其他书各自不同；1 组主人已删图 → 整组无封面）。
  规则：组内 `nid` 最大者保留该 URL，其余置空；混作者组与「主人已无封面」组整组置空。
  判重键是 `/NovelCover/Big/` 之后的路径——`rs` / `rss` 是同一图床别名，
  输出仍保留各书原始主机，但种子剥掉主机后不能有撞路径的两张图。
  同账号判定：**用户名大小写不敏感、空格敏感**（App API `authorId` 实证），
  故键只做 casefold；同时已知 `authorId` 优先——改名后名字不同但账号相同（11 组实证）
  仍按同账号处理，`authorId` 冲突才是真混作者。

用法：
    cd dataset && uv run python build.py [--src GLOB] [--covers PATH] [--crawl PATH]
                                         [--api-novels PATH] [--author-ids PATH] [--out DIR]

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
API_NOVELS_DEFAULT = ROOT / "analysis" / "out" / "app_api_novels.jsonl"
AUTHOR_IDS_DEFAULT = Path(__file__).resolve().parent / "author_ids.jsonl"
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


def author_key(name: str) -> str:
    """作者名归一：**只做大小写折叠**（+ 去首尾空白），用于「同作者」判定。

    依据（2026-11-18 用户确认 + App API 实证，见 README「作者身份口径」）：
    - 用户名**不区分大小写** → `kola` / `KOLA` 是同一账号（nid 4131 与 5971
      的 `authorId` 同为 382），故 casefold 合法。
    - 用户名**区分空格** → `镜音 レン`(5780) / `镜音 レ ン`(25615)、
      `First Order`(7505) / `firstorder`(12459)、`dark digger`(16612) /
      `darkdigger`(39896) 是不同账号，故**不得去空格**（旧版去过，已撤）。
    - 不做 NFKC 全角折叠：全角/半角是否为同一账号未经证实，现值也无此案例。
    """
    return (name or "").strip().casefold()


def is_default_cover(url: str) -> bool:
    """源站的占位封面：文件名以 default 开头（defaultNew.jpg / default[1].jpg）。"""
    return url.rsplit("/", 1)[-1].lower().startswith("default")


def cover_key(url: str) -> str:
    """封面的站内唯一路径；rs/rss 是同一图床别名，种子也只存这一段。"""
    return url.split("/NovelCover/Big/", 1)[-1].split("?", 1)[0]


def load_author_ids(*paths: Path | None) -> dict[int, int]:
    """nid → authorId（账号唯一身份）。来源合并，后者覆盖前者：

    1. 采集结果 jsonl（`snapshot.authorId`，App API 当期值，约 1.05 万本）
    2. 探测证据 `author_ids.jsonl`（`fetchers/probe_author_ids.py`，覆盖改名组）
    """
    ids: dict[int, int] = {}
    for path in paths:
        if path is None or not Path(path).exists():
            continue
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            nid = item.get("nid")
            aid = item.get("authorId")
            if aid in (None, ""):
                aid = (item.get("snapshot") or {}).get("authorId")
            if nid in (None, "") or aid in (None, ""):
                continue
            ids[int(nid)] = int(aid)
    return ids


def load_cover_items(paths: list[Path]) -> dict[int, str]:
    """合并 App API 封面来源；后者覆盖前者，空 URL 不覆盖已有值。

    `app_api_novels.jsonl` 用 `novelCover`，逐本采集结果用 `cover_url`。
    默认图也保留在返回值里，交给调用方统一置空并记录「官方已无封面」。
    """
    out: dict[int, str] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            nid = item.get("nid")
            url = (item.get("cover_url") or item.get("novelCover") or "").strip()
            if nid in (None, "") or not url:
                continue
            out[int(nid)] = url
    return out


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


def apply_cover_rules(records: list[dict], covers_path: Path,
                      crawl: dict[int, str], author_ids: dict[int, int],
                      audit: list[dict]) -> tuple[dict[str, int], dict[int, str], dict[int, str], set[int]]:
    """默认封面置空 → 授权 47 本用 cover-check 覆盖 → 多来源 App 采集封面覆盖。"""
    stats = {"default_blanked": 0, "empty_cover": 0, "licensed_overrides": 0,
             "crawl_applied": 0, "crawl_refreshed": 0, "crawl_default_skipped": 0,
             "crawl_unmatched": 0, "shared_groups": 0, "shared_owner_kept": 0,
             "shared_blanked": 0, "shared_owner_coverless": 0, "shared_mixed_author": 0,
             "shared_same_account": 0, "shared_id_conflict": 0}
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
    coverless: set[int] = set()
    by_nid = {r["nid"]: r for r in records}
    for nid, url in crawl.items():
        rec = by_nid.get(nid)
        if rec is None:
            stats["crawl_unmatched"] += 1
            continue
        if is_default_cover(url):
            # 11 月 API 的 default 只说明当下无图；不能反过来抹掉 5 月快照里的
            # 真实 URL。仅当本书原本就无封面时，才记为「官方无图」并挡住共享归属。
            if not rec["cover"]:
                stats["crawl_default_skipped"] += 1
                coverless.add(nid)
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

    # 共享封面 = 同作者其他作品的封面（爬虫选择器错）→ 归还给同作者 nid 最大者
    groups: dict[str, list[dict]] = {}
    for rec in records:
        if rec["cover"]:
            groups.setdefault(cover_key(rec["cover"]), []).append(rec)
    for url, grp in groups.items():
        if len(grp) < 2:
            continue
        stats["shared_groups"] += 1
        # 同账号判定优先级：已知 authorId 冲突 > 全部已知且同 id > 名字同键 > 未知
        ids = {author_ids[r["nid"]] for r in grp if r["nid"] in author_ids}
        names_same = len({author_key(r["author"]) for r in grp}) == 1
        if len(ids) > 1:
            same, why = False, "id_conflict"
        elif len(ids) == 1 and all(r["nid"] in author_ids for r in grp):
            same, why = True, "author_id"     # 同一账号：可能中途改过显示名
        elif names_same:
            same, why = True, "author_name"
        else:
            same, why = False, "name_conflict"   # 身份未知且名字不同 → 保守置空
        if not same:
            stats["shared_mixed_author"] += 1
            if why == "id_conflict":
                stats["shared_id_conflict"] += 1
            owner = None
        else:
            if why == "author_id":
                stats["shared_same_account"] += 1
            cands = [r for r in grp if r["nid"] not in coverless]
            owner = max(cands, key=lambda r: r["nid"]) if cands else None
            if owner is None:
                stats["shared_owner_coverless"] += 1
        keep = owner["nid"] if owner else None
        for rec in grp:
            if keep is not None and rec["nid"] == keep:
                stats["shared_owner_kept"] += 1
                continue
            rec["cover"] = ""
            stats["shared_blanked"] += 1
            audit.append({"nid": rec["nid"], "field": "cover",
                          "kind": "shared_cover_reassigned", "owner": keep})

    # App 样本里极少数 URL 被同账号两本书共用（1 组）；按共享规则归还主人后，
    # 被置空的那本不再是「已应用」的期望值，否则 verify 会误报。
    expected = {nid: url for nid, url in expected.items()
                if by_nid[nid]["cover"] == url}
    return stats, licensed, expected, coverless


def verify(records: list[dict], licensed: dict[int, str], expected: dict[int, str],
           coverless: set[int], stats: dict[str, int]) -> None:
    """构建即断言：口径不满足就直接失败，不产出可疑数据。"""
    problems = []
    dead = 0
    for rec in records:
        url = rec["cover"]
        if url:
            if not url.startswith(("http://", "https://")):
                problems.append(f"封面不是绝对 URL：nid={rec['nid']} {url[:60]}")
            elif "/NovelCover/Big/" not in url:
                problems.append(f"封面路径不符合站内格式：nid={rec['nid']} {url[:60]}")
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
            key = cover_key(rec["cover"])
            seen[key] = seen.get(key, 0) + 1
    dupn = sum(1 for n in seen.values() if n > 1)
    if dupn:
        problems.append(f"仍有 {dupn} 个封面路径（含 rs/rss 别名）被多本引用")
    leaked = [r["nid"] for r in records if r["nid"] in coverless and r["cover"]]
    if leaked:
        problems.append(f"{len(leaked)} 本官方已无封面的书仍带 URL（例 nid={leaked[0]}）")
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
                    help="逐本 App 采集结果 jsonl（cover_url，优先级高）")
    ap.add_argument("--api-novels", default=str(API_NOVELS_DEFAULT),
                    help="全字段 App 样本 jsonl（novelCover，优先级低；传空串禁用）")
    ap.add_argument("--author-ids", default=str(AUTHOR_IDS_DEFAULT),
                    help="authorId 探测证据 jsonl（nid→authorId，用于同账号判定）")
    ap.add_argument("--out", default=str(OUT_DEFAULT), help="产物目录")
    ap.add_argument("--version", default="20260503.6", help="数据集版本号")
    args = ap.parse_args()

    records, inputs, audit = load_records(args.src)
    lines_read = sum(i["lines"] for i in inputs)
    books = dedupe(records)
    crawl_path = Path(args.crawl) if args.crawl else None
    api_path = Path(args.api_novels) if args.api_novels else None
    cover_sources = [p for p in (api_path, crawl_path) if p is not None]
    crawl = load_cover_items(cover_sources)
    author_ids = load_author_ids(api_path, crawl_path,
                                 Path(args.author_ids) if args.author_ids else None)
    stats, licensed, expected, coverless = apply_cover_rules(
        books, Path(args.covers), crawl, author_ids, audit)
    stats["crawl_sources"] = len(crawl)
    verify(books, licensed, expected, coverless, stats)
    out_dir = Path(args.out)
    outputs = write_outputs(books, out_dir)

    kinds: dict[str, int] = {}
    for a in audit:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    for path, role in ((api_path, "app_api_covers"), (crawl_path, "crawl_covers")):
        if path is not None and path.exists():
            inputs.append({"path": str(path.resolve().relative_to(ROOT)).replace("\\", "/"),
                           "lines": len(path.read_text(encoding="utf-8").splitlines()),
                           "sha256": sha256(path), "role": role})
    if args.author_ids and Path(args.author_ids).exists():
        p = Path(args.author_ids)
        inputs.append({"path": str(p.resolve().relative_to(ROOT)).replace("\\", "/"),
                       "lines": len(p.read_text(encoding="utf-8").splitlines()),
                       "sha256": sha256(p), "role": "author_ids"})
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
            "author_ids_known": len(author_ids),
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
    print(f"采集封面：来源 {stats['crawl_sources']:,} 个 nid → 应用 "
          f"{stats['crawl_applied']:,} 本（其中替换旧图 {stats['crawl_refreshed']:,}）"
          f"| 官方已换默认图 {stats['crawl_default_skipped']} "
          f"| 未匹配 {stats['crawl_unmatched']}")
    print(f"共享封面：{stats['shared_groups']:,} 组 → 归还主人 {stats['shared_owner_kept']:,} 本 / "
          f"其余置空 {stats['shared_blanked']:,} 本 | 主人已删图 {stats['shared_owner_coverless']} 组 / "
          f"混作者 {stats['shared_mixed_author']} 组（整组置空，其中 id 冲突 "
          f"{stats['shared_id_conflict']} 组）")
    print(f"  其中按 authorId 判定为同账号（含改名）{stats['shared_same_account']:,} 组"
          f"（authorId 覆盖 {len(author_ids):,} 本）")
    print(f"清洗：{kinds or '无'}")
    print(f"产物 → {out_dir}（books.jsonl / books.csv / cleanup.jsonl / manifest.json）")


if __name__ == "__main__":
    main()

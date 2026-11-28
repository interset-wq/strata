"""1–3 征获奖作品补采：contest-achieve 的 awards.json 是名单真源。

一/二征活动页已下线、三征参赛展为空，官方只在获奖榜 tag 635–649 留下痕迹；
contest-achieve 的 `docs/data/awards.json` 逐本给出已验证的 nid / 标题 / 奖项
（一征 5、二征 7、三征 15）。本脚本取其中库外书，走与 `harvest_contest.py`
相同的 App API + mobile web 详情通路，追加到 `dataset/contest_new.jsonl`
（断点续采、失败降级、不写 seed.db）。

    uv run --project analysis python analysis/fetchers/harvest_awards.py --dry-run
    uv run --project analysis python analysis/fetchers/harvest_awards.py

注意：award tag 只代表获奖榜、不是参赛清单，严禁进 roster 抓取路径
（docs/contest-roster-harvest.md 结论 9）。本脚本只读 awards.json 的 nid，
不拉 tag 清单。数据来自 contest-achieve（AGPL-3.0），只借名单、不复制其代码。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import harvest_contest as hc  # noqa: E402

DEFAULT_AWARDS = Path("E:/contest-achieve/docs/data/awards.json")
# 默认全量补采（用户 2026-11-26 裁定：所有获奖作品强制入种）。
# 只补 1–3 征时显式传 --tag-lo 635 --tag-hi 649。
DEFAULT_TAG_LO, DEFAULT_TAG_HI = 0, 10**9


def load_awards(path: Path, lo: int, hi: int) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for r in rows:
        try:
            tag = int(r.get("contest_track_id") or 0)
            nid = int(r.get("nid") or 0)
        except (TypeError, ValueError):
            continue
        if not lo <= tag <= hi or not nid:
            continue
        out.append({
            "nid": nid,
            "title": r.get("title") or "",
            "author": "",  # awards.json 无作者字段，由 App API 详情覆盖
            "tag": tag,
            "tag_name": r.get("contest_name") or "",
            "series": r.get("series") or "",
            "award": r.get("award") or "",
            "verified": bool(r.get("verified")),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--awards", default=str(DEFAULT_AWARDS), help="contest-achieve/docs/data/awards.json")
    ap.add_argument("--tag-lo", type=int, default=DEFAULT_TAG_LO, help="默认全量；1–3 征传 635")
    ap.add_argument("--tag-hi", type=int, default=DEFAULT_TAG_HI, help="默认全量；1–3 征传 649")
    ap.add_argument("--detail-out", default=str(hc.DETAIL_OUT))
    ap.add_argument("--delay", type=float, default=0.5, help="详情串行间隔秒（≥0.5）")
    ap.add_argument("--limit", type=int, default=0, help="最多补多少本（0=全部，调试用）")
    ap.add_argument("--dry-run", action="store_true", help="只列待补清单，不写文件")
    a = ap.parse_args()

    rows = load_awards(Path(a.awards), a.tag_lo, a.tag_hi)
    have = hc.existing_nids()
    missing = {r["nid"]: r for r in rows if r["nid"] not in have}

    out = Path(a.detail_out)
    done: set[int] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(int(json.loads(line)["nid"]))
                except Exception:
                    pass
    todo = [nid for nid in sorted(missing) if nid not in done]
    if a.limit > 0:
        todo = todo[:a.limit]
    print(f"awards {len(rows)} 本（tag {a.tag_lo}–{a.tag_hi}）；库内 {len(rows) - len(missing)}；"
          f"库外 {len(missing)}；待补 {len(todo)}（contest_new 已采 {len(done)} 本）")
    if a.dry_run:
        for nid in todo:
            r = missing[nid]
            flag = "" if r["verified"] else " [未验证]"
            print(f"  {nid:6} {r['tag_name']:14} {r['award']:4} {r['title']}{flag}")
        return

    sess = requests.Session()
    sess.headers.update(hc.make_headers())
    ok = fail = 0
    with out.open("a", encoding="utf-8") as fh:
        for i, nid in enumerate(todo, 1):
            d = hc.fetch_app_detail(nid, sess)
            if not d:
                print(f"  {i}/{len(todo)} nid={nid} App API 失败，跳过（下次可续采）")
                fail += 1
                continue
            mobile = hc.fetch_mobile(nid)
            rec = hc.build_detail(d, missing[nid], mobile)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            ok += 1
            print(f"  {i}/{len(todo)} nid={nid} {rec['novel_title']} "
                  f"[{rec['contest']}] 赞源={rec['praises_source']}")
            time.sleep(a.delay)
    print(f"完成：{ok} 本写入 {out}；失败 {fail} 本")


if __name__ == "__main__":
    main()

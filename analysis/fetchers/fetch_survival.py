"""抽样探测 nid 存活状态：生存偏倚审计的数据采集。

三类样本（均通过 m.sfacg.com/b/{nid}/ 判定，存活=页面 >5KB 且含书名，死页≈3.6KB）：
- A. 月榜范围内缺失：8,374 条榜单条目中不在库的 118 本（在库=novels.csv）——
  上榜时必然存活，现不在库：活着=抓取源遗漏，死了=下架。
- B. 在册随机样本：按世代分层 400 本——测快照（2026-05-03）之后的下架率。
- C. 范围内缺失随机样本：300 个 nid——活着=抓取源遗漏的普适下界。

输出 out/survival_probe.jsonl。用法：uv run python analysis/fetch_survival.py
"""
import json, random, re, sys, time
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
BASE = paths.ROOT
from lib import eras
from lib.config import LICENSED_LN_AUTHORS as LIC

OUT = paths.OUT_DIR / "survival_probe.jsonl"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def probe(nid: int) -> dict:
    url = f"https://m.sfacg.com/b/{nid}/"
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": UA})
        if r.status_code != 200:
            return {"nid": nid, "alive": False, "http": r.status_code}
        t = r.text
        if len(t) < 5000 or "出错" in t:
            return {"nid": nid, "alive": False, "http": 200}
        m = TITLE_RE.search(t)
        title = m.group(1).split(" - ")[0].strip() if m else ""
        return {"nid": nid, "alive": True, "http": 200, "title": title[:60]}
    except Exception as e:
        return {"nid": nid, "alive": None, "error": str(e)[:80]}


def main():
    df = pd.read_csv(paths.OUT_DIR / "novels.csv", dtype={"tags": str, "contest": str},
                     usecols=lambda c: c in ("id", "author"))
    df = df[~df["author"].isin(LIC)]
    have = set(df["id"])
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_year"]], on="id")

    samples: dict[str, list[int]] = {}

    # A. 月榜范围内缺失（全部）
    recs = [json.loads(l) for l in (paths.OUT_DIR / "monthly_ranks.jsonl").open(encoding="utf-8")]
    rank_nids = {it["nid"] for x in recs for it in x["items"]}
    a = sorted(n for n in rank_nids if n not in have and n <= 774850)
    samples["rank_missing"] = a

    # B. 在册分层随机 400（按世代）
    rng = random.Random(20261116)
    b = []
    for lo, hi, k in [(2657, 30000, 80), (30000, 61157, 100), (61157, 200000, 110),
                      (200000, 500000, 110)]:
        pool = df[(df["id"] > lo) & (df["id"] <= hi)]["id"].tolist()
        b += rng.sample(pool, min(k, len(pool)))
    samples["in_db"] = b

    # C. 范围内缺失随机 300
    missing_pool = rng.sample(range(2657, 774851), 3000)
    missing_pool = [n for n in missing_pool if n not in have]
    samples["range_missing"] = missing_pool[:300]

    done = {}
    if OUT.exists():
        for l in OUT.open(encoding="utf-8"):
            r = json.loads(l)
            done[r["nid"]] = r
    with OUT.open("a", encoding="utf-8") as f:
        for grp, ids in samples.items():
            todo = [n for n in ids if n not in done or done[n]["alive"] is None]
            print(f"{grp}: {len(ids)} 本，待抓 {len(todo)}")
            for i, n in enumerate(todo):
                r = probe(n)
                r["group"] = grp
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                if (i + 1) % 50 == 0:
                    print(f"  {i+1}/{len(todo)}")
                    f.flush()
                time.sleep(0.12)
    print("完成 →", OUT)


if __name__ == "__main__":
    main()

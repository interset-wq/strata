"""抓取 SFACG MonthlyBoy 月度榜单（2013-03 至今，任意月份可查）。

端点: pages.sfacg.com/ajax/act/MonthlyBoy.ashx?op=getRanks&date=YYYY-MM&rank=N
  rank=0 月票榜(top20, ticketNum=月票)   rank=2 新书榜(top10)
  rank=3 热销榜(top20)                  rank=4 对话月票榜(top20)
来源: temp/novly/utils/{monthlyApi,urls,months}.ts
  (FIRST_MONTH=201303, 2013-02 及更早无数据, 2026-11-16 实测确认)

输出: out/monthly_ranks.jsonl，每行一条 {month, rank, fetched_at, items|error}
按设计 out/ 可由本脚本重建；端点语义与抓取日期证据见
analysis/references/sfacg-live-ranks.md。
礼貌抓取: 0.5s 间隔, 失败重试 2 次后记录 {"error": ...}。
"""
import json
import time
from datetime import datetime
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "out" / "monthly_ranks.jsonl"
URL = "https://pages.sfacg.com/ajax/act/MonthlyBoy.ashx"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://pages.sfacg.com/",
}
RANKS = [0, 2, 3, 4]
FIRST = (2013, 3)
LAST = (2026, 11)


def month_iter():
    y, m = FIRST
    while (y, m) <= LAST:
        yield f"{y}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def fetch_one(session: requests.Session, month: str, rank: int) -> dict:
    rec = {"month": month, "rank": rank,
           "fetched_at": datetime.now().isoformat(timespec="seconds")}
    for attempt in range(3):
        try:
            r = session.get(URL, params={"op": "getRanks", "date": month, "rank": rank},
                            headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json().get("data", [])
            rec["items"] = [
                {"nid": it["nid"], "name": it.get("name") or "",
                 "ticketNum": it.get("ticketNum") or 0,
                 "author": it.get("authorName"), "cover": it.get("cover")}
                for it in data
                if isinstance(it.get("nid"), int) and it["nid"] > 0
            ]
            return rec
        except Exception as e:
            time.sleep(2 + attempt * 3)
            rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    n_ok = n_err = n_items = 0
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for month in month_iter():
            for rank in RANKS:
                rec = fetch_one(session, month, rank)
                if "items" in rec:
                    n_ok += 1
                    n_items += len(rec["items"])
                else:
                    n_err += 1
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                time.sleep(0.5)
    print(f"done: months x ranks ok={n_ok} err={n_err} items={n_items} -> {OUT}")


if __name__ == "__main__":
    main()

"""为存活探测中的活书抓取详情页，量化遗漏书的画像（选中偏倚方向）。

解析 m.sfacg.com/b/{nid}/：状态（连载中/已完结）、字数、末次更新、收藏、赞、
征文徽章。仅对 survival_probe.jsonl 中 alive=True 的条目补 detail 字段，
写回 out/survival_probe.jsonl（原地更新）。用法：uv run python analysis/fetch_survival_details.py
"""
import json, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths
import requests

BASE = paths.ROOT
OUT = paths.OUT_DIR / "survival_probe.jsonl"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148")

META = re.compile(r"/ ([\d,]+)字(?:<br>|\s*)(\d{2}-\d{2}-\d{2} \d{2}:\d{2})")
STATE = re.compile(r"(玄幻|魔幻|都市|校园|悬疑|奇幻|轻小说|科幻|游戏|历史|军事|同人|二次元)?"
                   r"(连载中|已完结)")
COLL = re.compile(r"收藏<small>\s*(\d+)</small>")
LIKE = re.compile(r"赞<small>\s*(\d+)</small>")
BADGE = re.compile(r'<p class="(?:book-status|tag)[^"]*"[^>]*>\s*([^<\s][^<]*?)\s*</p>')


def detail(nid: int) -> dict:
    t = None
    for _ in range(3):
        try:
            r = requests.get(f"https://m.sfacg.com/b/{nid}/", timeout=15,
                             headers={"User-Agent": UA})
            t = r.text
            break
        except Exception:
            time.sleep(2)
    if t is None:
        return {"detail_err": True}

    if len(t) < 5000:
        return {"dead": True}
    m = META.search(t)
    s = STATE.search(t)
    c, l = COLL.search(t), LIKE.search(t)
    d = {"dead": False}
    if m:
        d["words"] = int(m.group(1).replace(",", ""))
        d["last_upd"] = m.group(2)
    if s:
        d["state"] = s.group(2)
        d["genre"] = s.group(1)
    if c:
        d["favs"] = int(c.group(1))
    if l:
        d["likes"] = int(l.group(1))
    badges = [x.strip() for x in BADGE.findall(t) if x.strip() and "连载" not in x and "完结" not in x]
    d["badge"] = badges[0][:20] if badges else ""
    return d


def main():
    recs = [json.loads(l) for l in OUT.open(encoding="utf-8")]
    todo = [r for r in recs if r.get("alive") and ("favs" not in r.get("detail", {}) or "words" not in r.get("detail", {}))]
    print(f"待抓详情 {len(todo)}")
    for i, r in enumerate(todo):
        r["detail"] = detail(r["nid"])
        time.sleep(0.15)
        if (i + 1) % 40 == 0:
            print(f"{i+1}/{len(todo)}")
    tmp = OUT.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(OUT)
    print("完成")


if __name__ == "__main__":
    main()

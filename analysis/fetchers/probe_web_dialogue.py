"""用 PC 详情页 DOM 判定对话产品线（权威判据，E.22）。

## 判据（用户 2026-11-19 指定，DOM 实证）

对话小说/互动小说**不支持 Web 阅读**，详情页的「预读章节」区不渲染正文，只放一行提示：

```html
<div class="chapter-info">
  <h3 class="chapter-title"><span class="text">书名&gt;&gt;</span><a class="link"></a></h3>
  <p class="chapter-content chapter-normal">全新的对话小说版本,给你最棒的阅读体验!
     只能在APP上观看哦,扫码下载APP观看吧……</p>
</div>
```

散文页的同一位置是**正文首段**（如「圣堂内，清音和学姐一起穿着暴露的内衣……」/「巫马权背手而立……」）。
故 `.chapter-info .chapter-content` 文本命中「对话小说 / 互动小说」= 对话产品线，否则是散文。

## 为什么不用章节标题

App API `GET /novels/{id}/chaps` 的章节标题在对话书里是「第 N 话」、散文是「第 N 章 / 序章」，
实测是很强的代理（hua 书 34 本抽验 31 本与详情页一致），但**不是确定性证据**：
用「第 N 话」写散文的作者会被误判（576854 / 550853 均为章均 >2100 字、章节叫「话」而
详情页有正文）。详情页文案是产品线的直接声明，作为唯一判据。

## 用法

    cd analysis && uv run python fetchers/probe_web_dialogue.py \
        --csv out/seed_form_medium_review_v19.csv --tag medium

输出 `out/web_dialogue_{tag}.jsonl`（断点续跑，已抓的 nid 跳过）。
`verdict` 三态：`dialogue` / `prose` / `unknown`（正文位为空或「暂无内容……」）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402

DETAIL = "https://book.sfacg.com/Novel/{nid}/"
HEADERS = {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "accept-language": "zh-CN,zh;q=0.9",
}
RE_INFO = re.compile(r'<p class="chapter-content[^"]*">(.*?)</p>', re.S)
RE_TITLE = re.compile(r"<title>\s*(.*?)\s*-", re.S)
# 对话产品线的产品声明（用户指定关键词）
DIALOGUE_KEYS = ("对话小说", "互动小说")
DELAY = 0.7
RETRY = 3


def _clean(html_frag: str) -> str:
    txt = re.sub(r"<[^>]+>", "", html_frag)
    return re.sub(r"\s+", " ", txt).strip()


def probe(nid: int) -> dict:
    last_err = ""
    for attempt in range(RETRY):
        try:
            r = requests.get(DETAIL.format(nid=nid), headers=HEADERS, timeout=25)
            t = r.text
            m = RE_INFO.search(t)
            info = _clean(m.group(1)) if m else ""
            title_m = RE_TITLE.search(t)
            dead = "小说不存在" in t
            if dead:
                verdict = "dead"
            elif not info or info.startswith("暂无内容"):
                verdict = "unknown"
            elif any(k in info for k in DIALOGUE_KEYS):
                verdict = "dialogue"
            else:
                verdict = "prose"
            return {
                "nid": nid,
                "verdict": verdict,
                "status": r.status_code,
                "bytes": len(t),
                "page_title": (title_m.group(1) if title_m else "")[:40],
                "info": info[:80],
            }
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"[:120]
            time.sleep(2 + attempt * 3)
    return {"nid": nid, "verdict": "error", "error": last_err}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = paths.ROOT / csv_path
    df = pd.read_csv(csv_path, dtype={"nid": "int64"})
    out = paths.OUT_DIR / f"web_dialogue_{args.tag}.jsonl"
    done: dict[int, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[int(rec["nid"])] = rec
    todo = [r for r in df.to_dict("records") if int(r["nid"]) not in done]
    print(f"{len(df)} 行，已抓 {len(done)}，待抓 {len(todo)}")

    with out.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(todo, 1):
            nid = int(r["nid"])
            rec = {**probe(nid), "title": str(r.get("title", ""))}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            tag = {"dialogue": "对话", "prose": "散文", "unknown": "无正文",
                   "dead": "死亡", "error": "失败"}[rec["verdict"]]
            print(f"[{i}/{len(todo)}] {nid:7} {tag:4} {rec['title'][:22]:24} | {rec.get('info', '')[:36]}")
            time.sleep(DELAY)

    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    import collections
    print("\n分布:", dict(collections.Counter(x["verdict"] for x in recs)))
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()

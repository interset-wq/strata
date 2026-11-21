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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# 作者区（用户 2026-11-20 指出，后续作者详情页要用）：
# `.author-box .author-desc` = 作者简介（可为空），
# `.author-box .author-mask img@src` = 头像 URL，`.autor-name`（拼写如此）= 显示名。
# App API 不返回 intro/头像，只能从 Web DOM 取；头像 URL 随账号变更，需带抓取时点。
RE_AUTHOR_BOX = re.compile(r'<div class="author-box">(.*?)<div class="side-part', re.S)
RE_AUTHOR_NAME = re.compile(r'class="autor-name"[^>]*>(.*?)</p>', re.S)
RE_AUTHOR_DESC = re.compile(r'class="author-desc"[^>]*>(.*?)</p>', re.S)
RE_AUTHOR_AVATAR = re.compile(r'class="author-mask"[^>]*>\s*<img[^>]+src="([^"]+)"', re.S)
RE_AUTHOR_INFO_AVATAR = re.compile(r'class="author-info[^"]*">\s*<div class="author-mask">\s*'
                                   r'<img[^>]+src="([^"]+)"', re.S)
RE_AUTHOR_INFO_NAME = re.compile(r'class="author-name"[^>]*>\s*<span>(.*?)</span>', re.S)
# 对话产品线的产品声明（用户指定关键词）
DIALOGUE_KEYS = ("对话小说", "互动小说")
DELAY = 0.7
RETRY = 3


def _clean(html_frag: str) -> str:
    txt = re.sub(r"<[^>]+>", "", html_frag)
    return re.sub(r"\s+", " ", txt).strip()


def author_fields(html: str) -> dict[str, str]:
    """作者显示名/简介/头像；intro 可为空串（用户明确：有些作者没写）。"""
    m = RE_AUTHOR_BOX.search(html)
    block = m.group(1) if m else ""
    name = desc = avatar = ""
    if block:
        n, d, a = (RE_AUTHOR_NAME.search(block), RE_AUTHOR_DESC.search(block),
                   RE_AUTHOR_AVATAR.search(block))
        name, desc, avatar = (_clean(n.group(1)) if n else "",
                              _clean(d.group(1)) if d else "",
                              a.group(1).strip() if a else "")
    if not name:
        n = RE_AUTHOR_INFO_NAME.search(html)
        name = _clean(n.group(1)) if n else ""
    if not avatar:
        a = RE_AUTHOR_INFO_AVATAR.search(html)
        avatar = a.group(1).strip() if a else ""
    return {"author_name": name[:60], "author_intro": desc[:1000],
            "author_avatar": avatar[:500]}


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
                **author_fields(t),
            }
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"[:120]
            time.sleep(2 + attempt * 3)
    return {"nid": nid, "verdict": "error", "error": last_err}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--workers", type=int, default=1,
                    help="并发数（默认 1；建议 ≤6，每请求约 1.3s）")
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
    print(f"{len(df)} 行，已抓 {len(done)}，待抓 {len(todo)}，并发 {args.workers}")
    if not todo:
        return

    titles = {int(r["nid"]): str(r.get("title", "")) for r in todo}
    n_done = 0
    with out.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.workers) as ex:
        # 限速由 worker 数决定（每请求约 1.3s），提交侧不再 sleep——否则提交循环
        # 会比完成循环长一个数量级，首个结果要等几分钟才落盘，中途失败全丢。
        futs = {ex.submit(probe, int(r["nid"])): int(r["nid"]) for r in todo}
        for fut in as_completed(futs):
            nid = futs[fut]
            rec = {**fut.result(), "title": titles[nid]}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            n_done += 1
            tag = {"dialogue": "对话", "prose": "散文", "unknown": "无正文",
                   "dead": "死亡", "error": "失败"}[rec["verdict"]]
            if n_done % 20 == 0 or rec["verdict"] in ("error", "dead"):
                print(f"[{n_done}/{len(todo)}] {nid:7} {tag:4} {rec['title'][:22]:24} "
                      f"| {rec.get('info', '')[:36]}", flush=True)

    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    import collections
    print("\n分布:", dict(collections.Counter(x["verdict"] for x in recs)))
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()

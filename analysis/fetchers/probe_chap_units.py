"""用 App API 章节列表判定「对话体 vs 散文」：章节计数单位（话 / 章）真值探针。

## 背景（E.22）

`forms.classify` 的形态估计（ckw / favs 复合指标）在 **中等点击区间** 判别力不足：
中篇档 944 本里 110 本落进无法用阈值线判定的灰区（ckw 10–13、跨作品同人、征文标记缺失）。

App API `GET /novels/{id}/chaps` 每章返回 `title`。实测发现 **对话小说（对话产品线）的
章节计数单位是「第 N 话」**，散文是「第 N 章 / 节」「1、标题」或无编号。这是产品线的
**原生命名惯例**，不是统计估计——比 ckw 之类的复合指标干净得多。

已知真值 39 本对照（`out/form_chapter_probe.jsonl`）：对话书 `hua_ratio = 1.00`，
散文（听雨 / 斗破 / 东方之幻想乡）`hua_ratio = 0.00`，零例外。

## 用法

    cd analysis && uv run python fetchers/probe_chap_units.py \
        --csv out/seed_form_medium_suspect_v19.csv --tag medium_suspect

    # 已有输出会跳过抓过的 nid（断点续跑）
    cd analysis && uv run python fetchers/probe_chap_units.py --csv ... --tag ...

输出 `out/chap_units_{tag}.jsonl`：每行 nid + 单位统计 + 章均字数 + 前 3 个章节标题。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths  # noqa: E402

API = "https://api.sfacg.com/novels"
SALT = "FN_Q29XHVmfV3mYX"
BASIC = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="
DELAY = 0.6

# 对话产品线的计数单位：第1话 / 第 12 话
RE_HUA = re.compile(r"第\s*\d+\s*话")
# 散文常规单位
RE_ZHANG = re.compile(r"第\s*[\d一二三四五六七八九十百千零]+\s*[章节回]")
# 「1、标题」「01 标题」这类
RE_NUM = re.compile(r"^\s*\d{1,4}\s*[、.．:：\s]")


def make_headers() -> dict[str, str]:
    nonce = str(uuid.uuid4()).upper()
    timestamp = int(time.time() * 1000)
    device_token = str(uuid.uuid4()).upper()
    sign = hashlib.md5(
        f"{nonce}{timestamp}{device_token}{SALT}".encode("ascii")
    ).hexdigest().upper()
    return {
        "accept": "application/vnd.sfacg.api+json;version=1",
        "authorization": BASIC,
        "user-agent": f"boluobao/5.0.36(android;32)/H5/{device_token}/H5",
        "sfsecurity": (
            f"nonce={nonce}&timestamp={timestamp}"
            f"&devicetoken={device_token}&sign={sign}"
        ),
        "accept-encoding": "gzip",
    }


def chap_stats(nid: int) -> dict:
    r = requests.get(f"{API}/{nid}/chaps", headers=make_headers(), timeout=20)
    r.raise_for_status()
    payload = r.json()
    http = (payload.get("status") or {}).get("httpCode")
    data = payload.get("data")
    if http != 200 or not isinstance(data, list) or not data:
        return {"n_chaps": 0, "dead": True, "http": http}
    titles = [str(c.get("title") or "") for c in data if isinstance(c, dict)]
    chars = [int(c.get("charCount") or 0) for c in data if isinstance(c, dict)]
    n = len(titles)
    hua = sum(1 for t in titles if RE_HUA.search(t))
    zhang = sum(1 for t in titles if RE_ZHANG.search(t))
    num = sum(1 for t in titles if RE_NUM.match(t))
    return {
        "n_chaps": n,
        "dead": False,
        "http": http,
        "chars_sum": sum(chars),
        "chap_med": round(statistics.median(chars), 1) if chars else 0,
        "chap_max": max(chars) if chars else 0,
        "hua_n": hua,
        "zhang_n": zhang,
        "num_n": num,
        "hua_ratio": round(hua / n, 3),
        "unit_other_ratio": round((n - hua - zhang - num) / n, 3),
        "last_update": str(data[-1].get("updateTime") or ""),
        "title_head": titles[:3],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="含 nid 列的 csv（相对 analysis/ 或绝对路径）")
    ap.add_argument("--tag", required=True, help="输出文件名后缀")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = paths.ROOT / csv_path
    df = pd.read_csv(csv_path, dtype={"nid": "int64"})
    out = paths.OUT_DIR / f"chap_units_{args.tag}.jsonl"
    done: dict[int, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[int(rec["nid"])] = rec

    rows = df.to_dict("records")
    if args.limit:
        rows = rows[: args.limit]
    todo = [r for r in rows if int(r["nid"]) not in done]
    print(f"{len(rows)} 行，已抓 {len(done)}，待抓 {len(todo)}")

    with out.open("a", encoding="utf-8") as fh:
        for i, r in enumerate(todo, 1):
            nid = int(r["nid"])
            try:
                st = chap_stats(nid)
            except Exception as e:  # noqa: BLE001
                st = {"error": str(e)[:120]}
            rec = {
                "nid": nid,
                "title": str(r.get("title", "")),
                "genre": str(r.get("genre", "")),
                "words": int(r.get("words", 0) or 0),
                "ckw": round(float(r.get("ckw", 0) or 0), 2),
                **st,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            flag = "话" if rec.get("hua_ratio", 0) >= 0.5 else "  "
            print(
                f"[{i}/{len(todo)}] {nid:7} {flag} hua={rec.get('hua_n', '-'):>4}/"
                f"{rec.get('n_chaps', '-'):>4} med={rec.get('chap_med', '-'):>7} "
                f"{rec['title'][:24]}"
            )
            time.sleep(DELAY)

    print(f"saved -> {out}")


if __name__ == "__main__":
    main()

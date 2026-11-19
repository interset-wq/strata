"""分层校准采集：用章节真值（章均字数）量化「对话 vs 散文短篇」各判据的误判率。

## 背景

probe_form_chapters.py（39 本）证实：章均字数是对话形态的真值（对话 538–1195，
散文短篇 1430–2797）；clicks/字 复合指标方向正确但有代际效应（老书中位 0.13–0.27
vs 近十年 0.01）。本脚本扩到 ~160 本分层样本，覆盖 字数带 × clicks/字带 × 同人标签，
用于校准 `dialogue_form` 新判据（复合指标 + 同人簇），并测定误判率。

## 用法

    cd analysis && uv run python fetchers/probe_form_calibration.py [--per-cell N]

输出 `out/form_calibration.jsonl`。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app" / "tools" / "seedbuild"))

from lib import paths  # noqa: E402
import seed_policy as SP  # noqa: E402
from lib import forms as FM  # noqa: E402

API = "https://api.sfacg.com/novels"
SALT = "FN_Q29XHVmfV3mYX"
BASIC = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="
UA_TPL = "boluobao/5.0.36(android;32)/H5/{device_token}/H5"
DELAY = 0.6
OUT = paths.OUT_DIR / "form_calibration.jsonl"

CKW_BANDS = [(0.003, 3), (3, 8), (8, 13), (13, 20), (20, 40), (40, 1e9)]
WORD_BANDS = [(0, 50_000), (50_000, 150_000), (150_000, 10**9)]


def chapter_stats(nid: int) -> dict | None:
    device_token = hashlib.md5(str(uuid.uuid4()).encode()).hexdigest()
    headers = {
        "Authorization": BASIC,
        "Security": SALT,
        "User-Agent": UA_TPL.format(device_token=device_token),
    }
    r = requests.get(f"{API}/{nid}/chaps", headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json().get("data") or []
    if not isinstance(data, list) or not data:
        return None
    chars = [c.get("charCount") or 0 for c in data if isinstance(c, dict)]
    nz = [c for c in chars if c > 0]
    return {
        "chapters": len(chars),
        "chap_chars_median": statistics.median(nz) if nz else 0,
        "chap_chars_sum": sum(chars),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=6)
    args = ap.parse_args()

    df = SP.load_universe()
    df["form"] = FM.classify(df)
    w = df["words"].clip(lower=1)
    df["ckw"] = df["clicks"] / w
    fan = df["genre"].eq("同人") | df["tags"].fillna("").astype(str).str.contains("同人")

    # 校准域：当前判短/中/长 的书（对话/IP 已判定的不用再校准）
    base = df.form.isin(("short", "medium", "long"))
    picks: dict[int, str] = {}
    for (wlo, whi), wb in zip(WORD_BANDS, ("w<5w", "5-15w", ">15w")):
        for (clo, chi), cb in zip(CKW_BANDS, ("ckw<3", "3-8", "8-13", "13-20", "20-40", "40+")):
            for tag, tg in ((fan, "fan"), (~fan, "nonfan")):
                m = base & df.words.ge(wlo) & df.words.lt(whi) & df.ckw.ge(clo) & df.ckw.lt(chi) & tag
                sub = df[m]
                if len(sub) == 0:
                    continue
                # 分层内兼顾头部与中部：按 favs 排序取前半 + 中位段
                n = min(args.per_cell, len(sub))
                top = sub.sort_values("favs", ascending=False).head(max(1, n // 2))
                mid = sub.iloc[len(sub) // 2: len(sub) // 2 + n - len(top)]
                for _, r in pd.concat([top, mid]).iterrows():
                    picks.setdefault(int(r.id), f"{wb}|{cb}|{tg}")

    print(f"calibration n={len(picks)}")
    rows = []
    for i, (nid, cell) in enumerate(picks.items()):
        try:
            st = chapter_stats(nid)
        except Exception as e:  # noqa: BLE001
            st = {"error": str(e)[:120]}
        r = df[df.id == nid].iloc[0]
        rows.append({
            "nid": nid, "cell": cell, "title": str(r.title), "genre": r.genre,
            "price_type": r.price_type, "words": int(r.words), "favs": int(r.favs),
            "clicks": int(r.clicks), "ckw": round(r.ckw, 2), "est_year": int(r.est_year),
            "form": r.form,
            "chap_chars_median": (st or {}).get("chap_chars_median", 0),
            "chapters": (st or {}).get("chapters", 0),
            "words_per_chap": round(r.words / max((st or {}).get("chapters", 1), 1)),
            **(st or {}),
        })
        time.sleep(DELAY)
        if (i + 1) % 40 == 0:
            print(f"  {i+1}/{len(picks)}")

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    print(f"saved {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()

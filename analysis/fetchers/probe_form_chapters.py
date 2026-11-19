"""抽样验证「对话 vs 短篇」的判据：章节数真值 + 复合指标（点击/字数）区分度。

## 目的

E.12 后 `form=short` 混入了大量字数 2–5 万的对话小说（如 421290「成为符华圣痕的黑符」
favs 7,881 > 真短篇头部「听雨」5,478）。用户提出用 **点击/字数、收藏/字数** 复合指标区分：
对话每章约 500 字、同字数下章节数远超散文短篇 → 页面曝光与互动天然更高。

本探针用 `GET /novels/{id}/chaps`（每章带 `charCount` 正文口径）取**章节数真值**，
分层抽样对照，验证复合指标的区分度，为 `dialogue_form` 判据校准提供依据。

## 用法

    cd analysis && uv run python fetchers/probe_form_chapters.py

输出 `out/form_chapter_probe.jsonl`：每行 nid + 分组 + 章节数 + 章均/中位章字数。
"""

from __future__ import annotations

import json
import statistics
import sys
import time
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
OUT = paths.OUT_DIR / "form_chapter_probe.jsonl"


def chapter_stats(nid: int) -> dict | None:
    import hashlib
    import uuid
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
    chars = [c for c in chars if c >= 0]
    return {
        "chapters": len(chars),
        "chap_chars_median": statistics.median(chars) if chars else 0,
        "chap_chars_sum": sum(chars),
    }


def main() -> None:
    df = SP.load_universe()
    df["form"] = FM.classify(df)
    fan = df["genre"].eq("同人") | df["tags"].fillna("").astype(str).str.contains("同人")
    free = df["price_type"].eq("免费")

    def top(mask: pd.Series, n: int) -> list[dict]:
        sub = df[mask].sort_values("favs", ascending=False).head(n)
        return [{"nid": int(r.id), "group": g} for g, r in
                [(g, r) for g, (_, r) in zip([], sub.iterrows())]]

    groups: list[tuple[str, pd.Series, int]] = [
        ("A_dial_cand_2to5w",  fan & free & df.words.between(20000, 50000), 10),
        ("B_dial_5to15w",      fan & free & df.words.between(50000, 150000), 5),
        ("C_dial_gt15w",       fan & free & (df.words > 150000), 5),
        ("D_short_nonfan_free", ~fan & (df.words <= 50000) & free, 8),
        ("E_short_nonfan_sign", ~fan & (df.words <= 50000) & ~free, 4),
        ("F_fan_sign_2to5w",   fan & ~free & df.words.between(20000, 50000), 4),
        ("G_dial_known",       df.id.isin({570712, 641618, 296048}), 3),
    ]
    picks: dict[int, str] = {}
    for name, mask, n in groups:
        sub = df[mask].sort_values("favs", ascending=False).head(n)
        for nid in sub["id"]:
            picks[int(nid)] = name
    picks.setdefault(24132, "H_abandon_sample")   # 回到旧时光
    picks.setdefault(421290, "A_dial_cand_2to5w")  # 黑符
    picks.setdefault(95926, "E_short_nonfan_sign")  # 听雨

    rows: list[dict] = []
    for i, (nid, group) in enumerate(picks.items()):
        try:
            st = chapter_stats(nid)
        except Exception as e:  # noqa: BLE001
            st = {"error": str(e)[:120]}
        r = df[df.id == nid].iloc[0]
        row = {
            "nid": nid, "group": group, "title": str(r.title), "genre": r.genre,
            "price_type": r.price_type, "words": int(r.words), "favs": int(r.favs),
            "clicks": int(r.clicks), "clicks_per_kw": round(r.clicks / max(r.words, 1), 1),
            "favs_per_k": round(r.favs / max(r.words, 1), 2),
            "form": r.form, **(st or {}),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))
        time.sleep(DELAY)

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    print(f"\n saved {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()

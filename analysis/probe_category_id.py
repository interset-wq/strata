"""categoryId 语义校准：从全库每个 genre 分层抓 App API，定 categoryId 的真实含义。

结论（2026-11-20，7,227 本 DOM 真值 + 9 genre 各 8 本分层抽样）：
  categoryId 是产品线/形态标记，不是题材分类：
    0 = 常规（散文长篇为主，6,649 DOM 真值全为 prose）
    1 = 对话小说（533 DOM 真值全为 dialogue，零反例；征文清一色「对话小说组」）
    3 = 短篇（征文清一色「N征短篇」；字数 <2 万占 78%）
    4 = 沉浸式互动小说（5 本 DOM 真值全为 dialogue 且 info 均为「沉浸式互动小说…只能在APP观看」）

关键反证：categoryId 与 genre/typeId 不是同义词——cat=1 跨 9 个 genre 都出现，
且同 genre 内 cat=0/1/3/4 并存。用户原猜测「cate 和 genre 同义」经数据否证。

用法：uv run python probe_category_id.py          # 用已有 app_api 快照现算
      uv run python probe_category_id.py --fetch  # 重新抓每个 genre 的样本
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import paths  # noqa: E402

API_NOVELS = paths.OUT_DIR / "app_api_novels.jsonl"
NOVELS_CSV = paths.OUT_DIR / "novels.csv"
TRUTH = paths.ANCHORS_DIR / "web_dialogue.jsonl"
SAMPLE_OUT = paths.OUT_DIR / "category_probe.json"


def load_api() -> pd.DataFrame:
    return pd.DataFrame([json.loads(l) for l in API_NOVELS.open(encoding="utf-8")])


def load_csv() -> pd.DataFrame:
    return pd.read_csv(NOVELS_CSV, dtype={"id": int}, encoding="utf-8", low_memory=False)


def fetch_per_genre(csv: pd.DataFrame, per_genre: int = 8) -> pd.DataFrame:
    """每个 genre 按 nid 分位挑书（覆盖新老），抓 App API 拿 categoryId。"""
    import requests
    from fetchers.fetch_app_api_novels import make_headers

    rng = random.Random(7)
    headers = make_headers()
    rows = []
    for genre, grp in csv.groupby("genre"):
        ids = sorted(grp["id"].tolist())
        qs = [i / (per_genre - 1) for i in range(per_genre)]
        for q in qs:
            nid = ids[min(len(ids) - 1, int(q * (len(ids) - 1)))]
            try:
                r = requests.get(f"https://api.sfacg.com/novels/{nid}", headers=headers, timeout=20)
                d = r.json().get("data", {})
                rows.append(dict(nid=nid, genre_csv=genre, typeId=d.get("typeId"),
                                 categoryId=d.get("categoryId"), name=str(d.get("novelName"))[:30]))
            except Exception as e:  # noqa: BLE001
                print("ERR", nid, repr(e)[:60], file=sys.stderr)
            time.sleep(0.6)
    df = pd.DataFrame(rows)
    SAMPLE_OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="重新抓每个 genre 的分层样本")
    args = ap.parse_args()

    api, csv = load_api(), load_csv()
    if args.fetch:
        sample = fetch_per_genre(csv)
        print("=== 抽样：categoryId × genre(CSV) ===")
        print(pd.crosstab(sample.categoryId, sample.genre_csv, margins=True).to_string())
        print("\n=== 抽样：categoryId × typeId(API) ===")
        print(pd.crosstab(sample.categoryId, sample.typeId, margins=True).to_string())

    truth = pd.DataFrame([
        {"nid": d["nid"], "form": d["form"]}
        for d in (json.loads(l) for l in TRUTH.open(encoding="utf-8"))
        if d.get("form") in ("dialogue", "prose")
    ])
    merged = api.merge(truth, left_on="novelId", right_on="nid", how="inner")
    print("\n=== categoryId × DOM 对话真值（决定性证据）===")
    print(pd.crosstab(merged.categoryId, merged.form, margins=True).to_string())

    m = api.merge(csv, left_on="novelId", right_on="id", how="inner", suffixes=("_api", "_csv"))
    m["has_contest"] = m.contest.fillna("").str.strip().ne("")
    print("\n=== categoryId 按 addTime 年份（判断改版时点）===")
    api["yr"] = api.addTime.str[:4].astype(int)
    print(pd.crosstab(api.yr, api.categoryId, margins=True).to_string())

    print("\n=== 有征文书的 categoryId 征文名 Top5 ===")
    for cat in (1, 3):
        s = m[(m.categoryId == cat) & m.has_contest]
        print(f"  cat={cat} (n={len(s):,}): " + ", ".join(
            f"{k} {v}" for k, v in s.contest.value_counts().head(5).items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

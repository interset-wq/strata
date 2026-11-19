"""分档分类器的训练、自评与分级过滤清单（离线，零爬虫）。

    cd analysis && uv run python probe_form_triage.py            # 训练 + 自评
    cd analysis && uv run python probe_form_triage.py --export   # 另出中篇档待爬清单

产物：`out/form_clf_{band}.pkl`、`out/triage_{band}.csv`
（`triage_*.csv` 只含 nid / p / zone，供抓取器 `--csv` 直接消费）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from lib import form_clf, paths


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(paths.OUT_DIR / "novels.csv", low_memory=False)
    truth = form_clf.load_truth()
    print(f"DOM 真值 {len(truth)} 条（已按档归属）\n")
    print(f"{'档':8} {'真值':>5} {'对话':>5} {'AUC':>6} {'准确':>6} {'精确':>6} {'召回':>6} "
          f"{'不确定区':>8} {'自信区错误':>8}")
    print("-" * 62)
    for band in ("short", "medium", "long"):
        sub = truth[form_clf.in_band(truth, band)]
        if len(sub) < 80:
            print(f"{band:8} {len(sub):>5}  —— 真值不足 80 条，不训练")
            continue
        try:
            m = form_clf.train(band)
        except ValueError as e:
            print(f"{band:8} {len(sub):>5}  {e}")
            continue
        print(f"{band:8} {m['n']:>5} {m['n_dialogue']:>5} {m['auc']:>6.3f} {m['accuracy']:>6.3f} "
              f"{m['precision']:>6.3f} {m['recall']:>6.3f} {m['uncertain_share']:>7.1%} "
              f"{m['confident_error']:>7.1%}")

    if not args.export:
        return

    print("\n=== 中篇档分级过滤（universe）===")
    band_df = df[form_clf.in_band(df, "medium")]
    tri = form_clf.triage("medium", band_df)
    counts = tri["zone"].value_counts()
    print(f"  全档 {len(band_df):,} 本：" + "  ".join(f"{k} {v:,}" for k, v in counts.items()))
    unc = band_df.loc[tri["zone"] == "uncertain", ["id", "title", "author", "words", "clicks"]].copy()
    unc["p"] = tri.loc[tri["zone"] == "uncertain", "p"]
    out = paths.OUT_DIR / "triage_medium.csv"
    unc.rename(columns={"id": "nid"})[["nid", "p", "title", "words", "clicks"]].to_csv(
        out, index=False, encoding="utf-8")
    print(f"  待爬 {len(unc):,} 本 → {out}（6 并发约 {len(unc)*1.3/6/60:.0f} 分钟）")


if __name__ == "__main__":
    main()

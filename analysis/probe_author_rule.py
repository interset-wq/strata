"""作者先验与标题词表的精度—召回权衡（离线，零爬虫）。

问题：作者维度能否从「弱先验」收紧成「高精度规则」？标题 IP 词表漏词有多少？

方法：真值用 `anchors/web_dialogue.jsonl`（1,040 条 DOM 判定），作者级特征全部
来自快照（征文标记、书数、字数、ckw），不引入任何 DOM 结果，避免循环。评估集是
E.23 的 119 本分层抽样（作者有对话征文标记、自身无标记），逐本有 DOM 真值。

用法：`uv run python probe_author_rule.py`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from lib import dialogue_form as DF, forms as FM, paths


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    truth = pd.read_json(paths.ANCHORS_DIR / "web_dialogue.jsonl", lines=True)
    truth["nid"] = truth["nid"].astype("int64")
    df = pd.read_csv(paths.OUT_DIR / "novels.csv", low_memory=False)
    df["akey"] = df["author"].fillna("").astype(str).str.casefold()
    return truth, df


def author_stats(df: pd.DataFrame) -> pd.DataFrame:
    d = DF.mark(df.copy())
    d["is_marked"] = d["marked"].astype(bool)
    g = d.groupby("akey").agg(
        n_books=("id", "size"),
        n_marked=("is_marked", "sum"),
        words_med=("words", "median"),
        words_min=("words", "min"),
        ckw_med=("ckw", "median"),
        clicks_med=("clicks", "median"),
        n_short=("words", lambda s: int((s <= 50_000).sum())),
    )
    g["marked_ratio"] = g["n_marked"] / g["n_books"]
    g["short_ratio"] = g["n_short"] / g["n_books"]
    return g


def policies(g: pd.DataFrame) -> dict[str, pd.Series]:
    """作者级策略：True = 该作者名下未标征文的作品判 dialogue。"""
    return {
        "P1 任一作品有对话征文标记": g["n_marked"] >= 1,
        "P2 标记占比 ≥ 0.5": g["marked_ratio"] >= 0.5,
        "P3 标记占比 ≥ 0.8 且书数 ≥ 3": (g["marked_ratio"] >= 0.8) & (g["n_books"] >= 3),
        "P4 全部作品均有标记": g["marked_ratio"] >= 1.0,
        "P5 全部有标记 且 书数 ≥ 3": (g["marked_ratio"] >= 1.0) & (g["n_books"] >= 3),
        "P6 标记占比 ≥ 0.5 且短篇占比 ≥ 0.7": (g["marked_ratio"] >= 0.5) & (g["short_ratio"] >= 0.7),
    }


def eval_sample(truth: pd.DataFrame, df: pd.DataFrame, g: pd.DataFrame) -> None:
    samp = truth[truth["sample"].notna()].copy()
    base = samp.merge(df, left_on="nid", right_on="id")
    base = DF.mark(base)
    base = base.join(g, on="akey")
    pol = policies(g)
    print(f"评估集：{len(base)} 本跨档抽样（作者有对话征文标记、本书自身无标记）")
    print(f"  其中真为对话 {int((base.form == 'dialogue').sum())} / 散文 {int((base.form == 'prose').sum())}")
    print(f"  这些作者的书数分位：{base.n_books.describe([.5,.9]).round(0).to_dict()}")
    print(f"  标记占比分位：{base.marked_ratio.describe([.25,.5,.75]).round(2).to_dict()}\n")

    hdr = f"{'策略':38} {'命中':>5} {'真对话':>6} {'精确率':>7} {'覆盖真对话':>10} {'落空':>5}"
    print(hdr)
    print("-" * len(hdr))
    total_d = int((base.form == "dialogue").sum())
    rows = []
    for name, mask in pol.items():
        sel = base[mask.reindex(base.akey).fillna(False).to_numpy()]
        if sel.empty:
            print(f"{name:38} {0:>5}")
            continue
        tp = int((sel.form == "dialogue").sum())
        prec = tp / len(sel)
        rec = tp / max(total_d, 1)
        print(f"{name:38} {len(sel):>5} {tp:>6} {prec:>7.0%} {rec:>10.0%} {len(sel)-tp:>5}")
        rows.append((name, len(sel), tp, prec, rec))
    return rows


def eval_ip(truth: pd.DataFrame, df: pd.DataFrame) -> None:
    t = truth.merge(df[["id", "title"]], left_on="nid", right_on="id", how="inner")
    t["title"] = t["title"].fillna("").astype(str)
    print("\n=== 现有 IP_PATTERN 在 1,040 条真值上的表现 ===")
    hit = t["title"].str.contains(DF.IP_PATTERN)
    d = t[t.form == "dialogue"]
    p = t[t.form == "prose"]
    print(f"  命中 {int(hit.sum())} 本：对话 {int((hit & (t.form=='dialogue')).sum())} / 散文 {int((hit & (t.form=='prose')).sum())}")
    print(f"  召回 {int((d.title.str.contains(DF.IP_PATTERN)).sum())}/{len(d)} = "
          f"{(d.title.str.contains(DF.IP_PATTERN)).mean():.0%}   "
          f"精确 {(hit & (t.form=='dialogue')).sum()/max(hit.sum(),1):.0%}")

    # 从真值标题里挖候选词：对话侧高频、散文侧罕见
    def grams(s: str, ns=(3, 4)) -> set[str]:
        out = set()
        s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)
        for n in ns:
            out |= {s[i:i + n] for i in range(max(0, len(s) - n + 1))}
        return out

    from collections import Counter
    cd, cp = Counter(), Counter()
    for s in d["title"]:
        cd.update(grams(s))
    for s in p["title"]:
        cp.update(grams(s))
    cand = [(w, c, cp.get(w, 0)) for w, c in cd.items() if c >= 6]
    cand = [x for x in cand if x[2] <= 2]
    cand.sort(key=lambda x: (-x[1], x[2]))
    print("\n=== 对话侧高频、散文侧几乎不出现的 3–4 字片段（自动候选，需人工过筛）===")
    for w, c, pc in cand[:45]:
        mark = "" if DF.IP_PATTERN.search(w) else "  ← 词表漏"
        print(f"  {w:8} 对话 {c:>3} 散文 {pc:>2}{mark}")

    ROUND = ("提瓦特|英桀|泰拉|七国|升格者|明日方舟|罗德岛|博士|整合运动|源石|"
             "崩坏|星穹|原神|律者|女武神|舰长|琪亚娜|芽衣|布洛妮娅|希儿|姬子|"
             "雷电|钟离|温迪|纳西妲|芙宁娜|胡桃|甘雨|刻晴|魈|宵宫|万叶|绫华|"
             "卡芙卡|镜流|景元|流萤|花火|黄泉|死士|泰拉之王|古堡|傀影")
    pat = re.compile(ROUND)
    hit2 = t["title"].str.contains(pat)
    print(f"\n=== 扩充词表后（{len(set(ROUND.split('|')))} 个词）===")
    print(f"  命中 {int(hit2.sum())} 本：对话 {int((hit2&(t.form=='dialogue')).sum())} / 散文 {int((hit2&(t.form=='prose')).sum())}")
    tp = int((hit2 & (t.form == "dialogue")).sum())
    print(f"  精确 {tp/max(int(hit2.sum()),1):.0%}   召回 {tp/len(d):.0%}")


def main() -> None:
    truth, df = load()
    g = author_stats(df)
    eval_sample(truth, df, g)
    eval_ip(truth, df)


if __name__ == "__main__":
    main()

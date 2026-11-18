"""篇幅加权口碑分 `lqs`（2026-11-18 定案，权威口径 `docs/length-weighted-quality.md`）。

为什么需要它：`pr`（praises/favs）在长篇区与篇幅强负相关——中位 pr 从 15–30 万字的
0.52 掉到 100 万字以上的 0.22；`pr` 前 1% 的 177 本里 77% 是 15–30 万字、0 本超过
100 万字。读者行为相反：同代同一 pr 五分位内，100–200 万字作品收藏中位数是 15–30 万
字的 3.6–16.5 倍，全库收藏加权中位篇幅约 102 万字。推荐若直接按 `pr` 排序，会把
推荐池压到 20 万字量级。

定义（仅长篇区，`form = long`）：

    q        = 同一「世代 × 收藏档」内 pr 的分位（去掉收藏规模对 pr 的机械影响）
    len      = log(字数 / 15万) / log(100万 / 15万)，夹在 [0, 1]（≥100 万字不再加分）
    lqs      = q × (0.75 + 0.25 × len)          # 篇幅最多左右 25% 的分，且有下界
    lqs_pctl = lqs 在同世代已评分书内的分位（展示用）

为什么乘性而不是加性：加性混合允许"篇幅补偿质量"，低质长书能压过高质短书；
乘性保留下界 0.75，篇幅无法把垃圾书托起来。这也和报告 23 的「不连乘」约束不冲突——
那条约束针对的是「篇幅效率 × pr」（两个类质量信号叠加），这里篇幅项是显式先验、
权限封顶，不是质量证据。

校准：K = 0.25 使推荐池 top-1000 的中位篇幅 1.03M 字，与全库收藏加权中位篇幅
1.02M 对齐；同时 lqs 与收藏量秩相关 -0.01（不是热度榜）、与 pr 秩相关 0.62。

运行审计（只读，无网络）：``cd analysis && uv run python -m lib.lqs``
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lib import forms

ZONE_FORM = "long"          # 只作用于长篇区；中篇区（5–15 万）待定
ZONE_MIN_WORDS = 150_000    # 命名长篇但字数不足的不入池（"X征长篇" 中位仅 1.4 万字）
EVIDENCE_MIN_FAVS = 200     # 证据下限：低于此 pr 的抽样噪声压倒信号（覆盖长篇区 99.6% 收藏）
PR_CAP = 5.0                # pr 长尾截断（原文 max 23.5，来自 15 收藏级小样本）
LEN_LO, LEN_HI = 150_000, 1_000_000   # 篇幅系数 0 → 1 的锚点，再长不再加分
LEN_K = 0.25                # 篇幅权限：系数区间 [0.75, 1.00]，校准见下
FLOOR = 1.0 - LEN_K
BANDS = (200, 1_000, 5_000)  # 收藏档（pr 的分母规模，必须按档归一）
MIN_CELL = 40               # 世代 × 档 的最小样本量，不足退回全世代档位分位


def pr_of(df: pd.DataFrame) -> pd.Series:
    return (df["praises"] / df["favs"].replace(0, np.nan)).clip(upper=PR_CAP)


def _pct(frame: pd.DataFrame, col: str, keys) -> pd.Series:
    g = frame.groupby(keys, observed=True)[col]
    return g.rank(ascending=True, method="average") / g.transform("size")


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """追加 form / lz_band / lz_q / lz_len / lqs / lqs_pctl；不修改入参。

    需要列：`contest, words, genre, tags, price_type, favs, praises, est_year`。
    `lqs` 为空表示不在长篇区或证据不足（`favs < 200`），调用方须按 NULL 处理。
    """
    d = df.copy()
    if "est_year" not in d.columns:
        raise ValueError("lqs: needs est_year (run lib.eras first)")
    d["form"] = forms.classify(d)

    eligible = ((d["form"] == ZONE_FORM) & (d["words"] > ZONE_MIN_WORDS)
                & (d["favs"] >= EVIDENCE_MIN_FAVS))
    d["lz_band"] = pd.cut(d["favs"], BANDS + (np.inf,), right=False,
                          labels=["200-1k", "1k-5k", "5k+"]).astype(object)
    d.loc[~eligible, "lz_band"] = None

    lz = d[eligible].copy()
    lz["pr"] = pr_of(lz)
    # 质量项：同世代同收藏档分位，干掉「收藏越多 pr 越低」的机械关系
    lz["cell"] = lz.groupby(["est_year", "lz_band"], observed=True)["pr"].transform("size")
    within = _pct(lz[lz["cell"] >= MIN_CELL], "pr", ["est_year", "lz_band"])
    lz["lz_q"] = within.reindex(lz.index).fillna(_pct(lz, "pr", ["lz_band"]))

    # 篇幅项：对数插值，15 万 → 0，100 万 → 1，上限封顶
    words = lz["words"].to_numpy(dtype=float)
    lz["lz_len"] = (np.log(np.clip(words, LEN_LO, LEN_HI) / LEN_LO)
                    / np.log(LEN_HI / LEN_LO))
    lz["lqs"] = lz["lz_q"] * (FLOOR + LEN_K * lz["lz_len"])
    lz["lqs_pctl"] = _pct(lz, "lqs", ["est_year"])
    lz["lz_pr"] = lz["pr"]

    for col in ("lz_pr", "lz_q", "lz_len", "lqs", "lqs_pctl"):
        d[col] = np.nan
        d.loc[lz.index, col] = lz[col]
    return d


TIERS = ((150_000, 300_000, "15-30万"), (300_000, 500_000, "30-50万"),
         (500_000, 1_000_000, "50-100万"), (1_000_000, 2_000_000, "100-200万"),
         (2_000_000, np.inf, "200万+"))
TIER_LABELS = [t[2] for t in TIERS]


def tier_of(words: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=words.index, dtype=object)
    for lo, hi, name in TIERS:
        out[(words > lo) & (words <= hi)] = name
    return out


def _audit() -> int:
    from lib import eras, paths

    df = pd.read_csv(paths.OUT_DIR / "novels.csv")
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(est[["id", "est_date", "est_year"]], on="id", how="left")
    df = df[df["est_year"].between(2007, 2025)]
    d = compute(df)
    lz = d[d["lqs"].notna()].copy()
    lz["tier"] = tier_of(lz["words"])
    fav_tot = lz["favs"].sum()

    zone = d[(d.form == ZONE_FORM) & (d.words > ZONE_MIN_WORDS)]
    print(f"universe {len(df):,} | 长篇区 {len(zone):,} "
          f"| 评分池（favs>=200）{len(lz):,} "
          f"| 覆盖长篇区收藏 {fav_tot / zone.favs.sum():.1%}")

    print("\n== 1. pr 与篇幅（长篇区，favs>=10）==")
    z = d[(d["form"] == ZONE_FORM) & (d.words > ZONE_MIN_WORDS) & (d.favs >= 10)].copy()
    z["pr"] = (z.praises / z.favs).clip(upper=PR_CAP)
    z["tier"] = tier_of(z.words)
    tg = z.groupby("tier").agg(n=("id", "size"), med_pr=("pr", "median"),
                               med_favs=("favs", "median")).reindex(TIER_LABELS)
    zg = z.groupby("est_year")["pr"]
    z["pr_pctl"] = zg.rank(ascending=True, method="average") / zg.transform("size")
    for q in (0.99, 0.95):
        top = z[z.pr_pctl >= q]
        tiered = top[top.tier.notna()]
        mix = tiered.groupby("tier").size().reindex(TIER_LABELS).fillna(0) / len(tiered)
        tg[f"pr>{q:.2f} 占比"] = mix
        print(f"   pr 前 {(1 - q):.0%}（n={len(top)}，其中可切档 {len(tiered)}）长度构成已列")
    print(tg.round(3).to_string())

    print("\n== 2. 同代同一 pr 五分位下的收藏倍数（vs 15–30万，中位）==")
    z["pr_q"] = z.groupby("est_year")["pr"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop"))
    rows = {}
    for year in (2017, 2018, 2019, 2020, 2021):
        sub = z[z.est_year == year]
        piv = sub.pivot_table(index="pr_q", columns="tier", values="favs", aggfunc="median")
        rows[year] = {t: (piv[t] / piv["15-30万"]).median() for t in TIER_LABELS
                      if t in piv.columns and t != "15-30万"}
    print(pd.DataFrame(rows).T.round(1).to_string())

    print("\n== 3. 校准：推荐池的篇幅是否吻合收藏加权篇幅 ==")
    order = lz.sort_values("words")
    cum = order.favs.cumsum() / fav_tot
    print(f"收藏加权中位篇幅 {int(order.words.values[cum.searchsorted(0.5)]):,} 字")
    for k in (100, 1000):
        top = lz.nlargest(k, "lqs")
        ftop = lz.nlargest(k, "favs")
        print(f"top{k}: lqs 中位篇幅 {int(top.words.median()):,} 字 / 收藏覆盖 "
              f"{top.favs.sum() / fav_tot:.1%} | favs 榜中位篇幅 "
              f"{int(ftop.words.median()):,} 字 / 覆盖 {ftop.favs.sum() / fav_tot:.1%}")

    print(f"\n== 4. 篇幅系数敏感性（现口径 K={LEN_K}）==")
    print(f"{'K':>4} {'rho(words)':>10} {'top200_15-30':>13} {'top200>=50万':>13} "
          f"{'top1k_15-30':>12} {'top1k中位篇幅':>14}")
    for k in (0.20, 0.25, 0.30, 0.40, 0.50):
        score = lz["lz_q"] * (1 - k + k * lz["lz_len"])
        t2 = lz.assign(s=score).nlargest(200, "s")
        t1 = lz.assign(s=score).nlargest(1000, "s")
        print(f"{k:>4.2f} {score.corr(lz.words, method='spearman'):>10.3f} "
              f"{(t2.words <= 300_000).mean():>13.1%} {(t2.words >= 500_000).mean():>13.1%} "
              f"{(t1.words <= 300_000).mean():>12.1%} {int(t1.words.median()):>14,}")

    print("\n== 5. 与现有信号的关系 ==")
    print(f"rho(lqs, favs) {lz.lqs.corr(lz.favs, method='spearman'):+.3f} | "
          f"rho(lqs, pr) {lz.lqs.corr(lz.lz_pr, method='spearman'):+.3f} | "
          f"rho(lqs, words) {lz.lqs.corr(lz.words, method='spearman'):+.3f}")
    print(f"top1000 收藏中位 {int(lz.nlargest(1000, 'lqs').favs.median()):,} | "
          f"其中 favs<1k 占 {(lz.nlargest(1000, 'lqs').favs < 1000).mean():.1%}")

    print("\n== 6. 样例 ==")
    cols = ["id", "title", "words", "favs", "praises", "lz_q", "lqs"]
    print(lz.nlargest(8, "lqs")[cols].to_string(index=False, max_colwidth=20))
    print(f"\n最好的 15–30 万字书：rank "
          f"{int((lz.lqs > lz.loc[lz[lz.tier == '15-30万'].lqs.idxmax(), 'lqs']).sum()) + 1}"
          f" / {len(lz):,}")
    print(lz[lz.tier == "15-30万"].nlargest(3, "lqs")[cols]
          .to_string(index=False, max_colwidth=20))
    return 0


if __name__ == "__main__":
    raise SystemExit(_audit())

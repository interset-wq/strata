"""中篇口碑分 `mqs` 的校准探针（只读，无网络；权威口径 `docs/medium-quality-score.md`）。

## 为什么需要它

`lqs` 的篇幅锚点是 15 万–100 万字，中篇（5–15 万）的 `len` 恒为 0，所有中篇被压到
0.75 下界（`docs/length-weighted-quality.md` §5 明确「不要直接复用本指标」）。
中篇区因此没有排序信号，只能按 `favs` 排——而收藏是累积量、跨世代不可比。

## 三个事实（本脚本可复现）

1. **中篇内部 `pr` 与篇幅几乎无关**：rho = -0.10（长篇区是强负相关，`lqs` 因此存在）。
   但读者仍偏好长端：同代同 `pr` 五分位内，12.5–15 万收藏中位是 5–7.5 万的 1.3–1.8 倍。
2. **中篇的 `pr` 比长篇更被收藏规模支配**：收藏 10–50 档 `pr` 中位 1.33（p90 3.18），
   5k+ 档 0.16。证据下限必须高于长篇的 200，实测 300 是拐点（500 就退化成 `pr` 榜）。
3. **中篇池很小**：universe 已完结中篇 3,666 本，`favs ≥ 300` 的只有 420 本；种子层
   578 本已完结、其中 295 本达标。篇幅塌陷不是中篇的主要风险，冷门头部才是。

定义（`docs/medium-quality-score.md`）：

    mlen = log(字数 / 5万) / log(15万 / 5万)        # 夹在 [0, 1]
    mqs  = q × (0.75 + 0.25 × mlen)                 # 与 lqs 同构，只换锚点域
    q    = 同「世代 × 收藏档」内 pr 分位（档：300–1k / 1k–5k / 5k+）

运行：``cd analysis && uv run python probe_medium_signal.py``
"""

from __future__ import annotations

import gzip
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import eras, forms, paths  # noqa: E402

# ---- 判据常量（与 docs/medium-quality-score.md §2 一致）----
PR_CAP = 5.0
MED_LO, MED_HI = 50_000, 150_000      # mlen 锚点：5 万 → 0，15 万 → 1
MIN_WORDS_FOR_SCORE = 50_000          # 域下界（与 forms.MEDIUM_MAX_WORDS 互补）
EVIDENCE_MIN_FAVS = 300               # 证据下限：中篇 pr 在 300 以下被小样本支配
BANDS = (300, 1_000, 5_000)           # 收藏档（300 起，低于下限不给分）
MIN_CELL = 10                         # 世代 × 档最小样本（池小 30 倍；门槛越高回退越多、
                                      # 世代偏差越大：20→rho(year) -0.21，10→-0.05）
LEN_K = 0.25                          # 篇幅权限（与 lqs 同常数：短端书数量占优，
                                      # 中篇只差 3 倍仍需同等坡度才能对齐加权中位）
DONE = "已完结"
W = 100                               # Top-N 观察窗


def _pct(frame: pd.DataFrame, col: str, keys) -> pd.Series:
    g = frame.groupby(keys, observed=True)[col]
    return g.rank(ascending=True, method="average") / g.transform("size")


def _wmed(pool: pd.DataFrame) -> float:
    """收藏加权中位篇幅：『典型的一次收藏落在多长的书上』。"""
    order = pool.sort_values("words")
    cum = order["favs"].cumsum() / order["favs"].sum()
    return order["words"].to_numpy()[cum.searchsorted(0.5)]


def load(scope: str = "universe") -> pd.DataFrame:
    if scope == "seed":
        return _seed()
    df = pd.read_csv(paths.OUT_DIR / "novels.csv")
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(est[["id", "est_date", "est_year"]], on="id", how="left")
    df = df[df["est_year"].between(2007, 2025)].copy()
    df["form"] = forms.classify(df)
    return df


def _seed() -> pd.DataFrame:
    raw = gzip.open(paths.ROOT.parent / "app" / "assets" / "seed.db.gz", "rb").read()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        fh.write(raw)
        tmp = fh.name
    con = sqlite3.connect(tmp)
    df = pd.read_sql_query(
        "SELECT nid, title, words, favs, praises, form, status, lqs FROM books", con)
    con.close()
    Path(tmp).unlink(missing_ok=True)
    return df


def score(df: pd.DataFrame) -> pd.DataFrame:
    """追加 pr / band / q / mlen / mqs；域外或证据不足者 mqs 为空。"""
    d = df.copy()
    if "form" not in d.columns:
        d["form"] = forms.classify(d)
    d["pr"] = (d["praises"] / d["favs"].replace(0, np.nan)).clip(upper=PR_CAP)
    ok = ((d["form"] == "medium") & (d["status"] == DONE)
          & (d["words"] >= MIN_WORDS_FOR_SCORE)
          & (d["words"] <= MED_HI) & (d["favs"] >= EVIDENCE_MIN_FAVS))
    p = d[ok].copy()
    p["band"] = pd.cut(p["favs"], list(BANDS) + [np.inf], right=False,
                       labels=["300-1k", "1k-5k", "5k+"]).astype(object)
    p["cell"] = p.groupby(["est_year", "band"], observed=True)["pr"].transform("size")
    within = _pct(p[p["cell"] >= MIN_CELL], "pr", ["est_year", "band"])
    p["q"] = within.reindex(p.index).fillna(_pct(p, "pr", ["band"]))
    ln = np.clip(p["words"], MED_LO, MED_HI)
    p["mlen"] = np.log(ln / MED_LO) / np.log(MED_HI / MED_LO)
    p["mqs"] = p["q"] * (1 - LEN_K + LEN_K * p["mlen"])
    p["mqs_pctl"] = _pct(p, "mqs", ["est_year"])
    d["band"] = pd.Series(np.nan, index=d.index, dtype=object)
    d.loc[p.index, "band"] = p["band"].astype(object)
    for col in ("pr", "q", "mlen", "mqs", "mqs_pctl"):
        d[col] = np.nan
        d.loc[p.index, col] = p[col]
    return d


def main() -> int:
    d = load()
    med = d[d["form"] == "medium"]
    print(f"universe {len(d):,} | medium {len(med):,} | 已完结 "
          f"{(med['status'] == DONE).sum():,}")

    # ---- 1. 篇幅 × 口碑 ----
    print("\n== 1. 中篇（已完结）篇幅档 × pr ==")
    z = med[(med["status"] == DONE) & (med["favs"] >= 10)].copy()
    z["pr"] = (z["praises"] / z["favs"].replace(0, np.nan)).clip(upper=PR_CAP)
    z["tier"] = pd.cut(z["words"], [MED_LO, 75_000, 100_000, 125_000, MED_HI],
                       labels=["5-7.5万", "7.5-10万", "10-12.5万", "12.5-15万"])
    print(z.groupby("tier", observed=True).agg(
        n=("id", "size"), med_pr=("pr", "median"), med_favs=("favs", "median")).round(3)
        .to_string())
    print(f"rho(pr, words) = {z['pr'].corr(z['words'], method='spearman'):+.3f}")

    # ---- 2. pr 的小样本污染 ----
    print("\n== 2. 收藏档 × pr（已完结中篇）==")
    b = z.copy()
    b["band"] = pd.cut(b["favs"], [10, 50, 200, 1_000, 5_000, np.inf], right=False,
                       labels=["10-50", "50-200", "200-1k", "1k-5k", "5k+"])
    print(b.groupby("band", observed=True).agg(
        n=("id", "size"), med_pr=("pr", "median"),
        p90_pr=("pr", lambda s: s.quantile(.9))).round(3).to_string())

    # ---- 3. 候选信号对照 ----
    print(f"\n== 3. 候选信号 Top{W} 行为（池 = 已完结 & favs>={EVIDENCE_MIN_FAVS}）==")
    s = score(d)
    pool = s[s["mqs"].notna()].copy()
    pool["fav_pctl"] = _pct(pool, "favs", ["est_year"])
    wmed = _wmed(pool)
    print(f"评分池 {len(pool):,} 本 | 收藏加权中位篇幅 {int(wmed):,} | "
          f"池中位篇幅 {int(pool['words'].median()):,}")
    cands = {
        "favs DESC": pool["favs"],
        "fav_pctl(同代)": pool["fav_pctl"],
        "pr(硬比值)": pool["pr"],
        "lqs 原式(下界0.75)": pool["q"] * (0.75 + 0.25 * pool["mlen"]),
        "q(无篇幅)": pool["q"],
        f"mqs(K={LEN_K})": pool["mqs"],
    }
    print(f"\n{'信号':<22}{'中位字':>9}{'vs加权':>8}{'收藏中位':>10}"
          f"{'rho(pr)':>9}{'rho(favs)':>10}")
    for name, v in cands.items():
        top = pool.assign(_s=v).nlargest(W, "_s")
        print(f"{name:<22}{int(top['words'].median()):>9,}"
              f"{(top['words'].median()/wmed-1):>7.0%}"
              f"{int(top['favs'].median()):>10,}"
              f"{v.corr(pool['pr'], method='spearman'):>9.2f}"
              f"{v.corr(pool['favs'], method='spearman'):>10.2f}")

    # ---- 4. K 敏感性 ----
    print("\n== 4. 篇幅权限 K 敏感性（对齐目标 = 收藏加权中位篇幅）==")
    print(f"{'K':>5}{'top' + str(W) + '中位字':>12}{'vs加权':>8}"
          f"{'rho(favs)':>11}{'rho(pr)':>9}{'收藏中位':>10}")
    for k in (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25):
        v = pool["q"] * (1 - k + k * pool["mlen"])
        top = pool.assign(_s=v).nlargest(W, "_s")
        print(f"{k:>5.2f}{int(top['words'].median()):>12,}"
              f"{(top['words'].median()/wmed-1):>7.0%}"
              f"{v.corr(pool['favs'], method='spearman'):>11.2f}"
              f"{v.corr(pool['pr'], method='spearman'):>9.2f}"
              f"{int(top['favs'].median()):>10,}")

    # ---- 5. 种子层覆盖 ----
    sm = load("seed")
    sm = sm[(sm["form"] == "medium") & (sm["status"] == DONE)]
    print(f"\n== 5. 种子层（app 可见池）==")
    print(f"medium 已完结 {len(sm):,} 本 | favs 中位 {int(sm['favs'].median()):,}")
    for thr in (100, 200, 300, 500):
        print(f"  favs>={thr:<4}: {(sm['favs'] >= thr).sum():>3} 本"
              f"（{(sm['favs'] >= thr).mean():>4.0%}）")
    got = sm[sm["favs"] >= EVIDENCE_MIN_FAVS]
    print(f"  → mqs 可评分 {len(got)}/{len(sm)}（{len(got)/len(sm):.0%}），"
          f"收藏中位 {int(got['favs'].median()):,}，字数中位 {int(got['words'].median()):,}；"
          f"其余 {len(sm)-len(got)} 本 favs<{EVIDENCE_MIN_FAVS} 回退 fav_pctl")

    # ---- 6. K 的稳健性：bootstrap + 行为弹性 ----
    print("\n== 6. K 不是过拟合（两条独立检验）==")
    rng = np.random.default_rng(7)
    ks = []
    for _ in range(400):
        b = pool.sample(len(pool), replace=True, random_state=int(rng.integers(1e9)))
        target, best, bk = _wmed(b), 1e9, None
        for k in np.arange(0.0, 0.61, 0.02):
            t = b.assign(_s=b["q"] * (1 - k + k * b["mlen"])).nlargest(W, "_s")
            err = abs(t["words"].median() / target - 1)
            if err < best:
                best, bk = err, k
        if bk is not None:
            ks.append(bk)
    ks = pd.Series(ks)
    print(f"  bootstrap(400) K* 中位 {ks.median():.2f} | P25–P75 "
          f"{ks.quantile(.25):.2f}–{ks.quantile(.75):.2f} | P10–P90 "
          f"{ks.quantile(.1):.2f}–{ks.quantile(.9):.2f}")
    print(f"  K={LEN_K} 位于 K* 分布的 {100*(ks <= LEN_K).mean():.0f}% 分位"
          f"（接近 50% 即无偏）")

    # 行为弹性：同代 × pr 五分位格内 log(favs) ~ log(words)
    print("\n  行为弹性（同代 × pr 五分位格内，n>=20）：")
    allm = d[(d["form"] == "medium") & d["words"].between(MED_LO, MED_HI)
             & (d["favs"] >= 10)].copy()
    allm["pr"] = (allm["praises"] / allm["favs"]).clip(upper=PR_CAP)
    for label, sub in (("全部中篇", allm), (f"已完结", allm[allm["status"] == DONE]),
                       ("连载中", allm[allm["status"] != DONE])):
        x = sub.copy()
        x["pr_q"] = x.groupby("est_year")["pr"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop"))
        betas = []
        for _, g in x.groupby(["est_year", "pr_q"], observed=True):
            if len(g) < 20 or g["words"].nunique() < 8:
                continue
            betas.append(np.polyfit(np.log(g["words"].to_numpy(float)),
                                    np.log(g["favs"].to_numpy(float)), 1)[0])
        bta = float(np.median(betas))
        mult = np.exp(bta * np.log(MED_HI / MED_LO))
        print(f"    {label:<8}格子 {len(betas):>3} | β={bta:.3f} | 5→15 万收藏 "
              f"{mult:.2f}× | 若追平偏好 K={1-1/mult:.2f}")
    print(f"  → 追平偏好（K≈0.41）会让 Top100 篇幅过冲 +6%（用先验替代代表性），"
          f"故取对齐值 {LEN_K}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

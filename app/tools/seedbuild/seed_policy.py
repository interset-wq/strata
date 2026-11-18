"""Seed admission policy (V2) — executable spec + offline audit.

Rule set is decided in ``app/docs/09-seed-refresh-proposal.md`` appendix E
(2026-11-18). It is **not wired into build_seed.py yet**: the next seed rebuild
switches ``seed_set()`` over to :func:`admit` and updates the pinned counts.

Why the policy exists
--------------------
The 2026-05-03 seed admits books from two kinds of channels:

* quality-anchored — favs Top-20k, archived monthly ranks, banner (``featured``),
  short-form dual percentile. These are effectively clean (favs<5 ≈ 0-1%).
* time-anchored — ``est_date`` within 365 d, ``updated_at`` within 90 d. These
  carried 28% of the seed but 0.25% of its favourites; 53% of the books they
  alone admitted had favs<5, 18% had zero.

Cumulative favourites penalise new books by construction, so the time channels
are gated by **age-normalised velocity** (favs per day since ``est_date``)
percentile *within the launch quarter*, computed on the full statistical
universe. The percentile alone is not enough: the snapshot's median launch
quarter holds only 4-5 favourites, so "faster than half the cohort" still lands
inside the noise floor; the gate therefore also requires ``favs >= 5``, the same
floor the post-condition uses. Everything the gate removes is noise: max favs
15, zero books above the 90th click percentile of their generation.

Freed budget goes to the D2 deep-rank books, which are ranked Top-200 in their
generation but were absent from the pool — so the seed now contains every book
any offline board can display.

Run the audit (read-only, no writes, no network)::

    cd analysis && uv run python ../app/tools/seedbuild/seed_policy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
ANALYSIS = REPO / "analysis"
sys.path.insert(0, str(ANALYSIS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eras, paths  # noqa: E402
from deep_ranks import build_deep_ranks  # noqa: E402

# --- policy constants (pinned; changing one is a policy change, not a tunable)
VEL_PCTL_MIN = 0.5      # same-quarter velocity percentile gate for time channels
TIME_MIN_FAVS = 5       # absolute floor on top of the percentile (cohort median is 4-5)
RECENT_DAYS = 365       # est_date window that the gate applies to
ACTIVE_DAYS = 90        # updated_at window that the gate applies to
REC_N = 20_000          # favs Top-N anchor
SHORT_MAX_WORDS = 50_000
SHORT_TOP_N = 2_000
SHORT_BINS = [-1, 3_000, 6_000, 10_000, 20_000, 50_001]
SHORT_LABELS = ["<=3k", "3-6k", "6-10k", "10-20k", "20-50k"]
NOISE_FAVS = 5          # post-condition: favs below this and short words must be anchored
NOISE_WORDS = 10_000
GEN_MIN, GEN_MAX = 2007, 2025
LICENSED = 47           # appended by build_seed.py, outside the universe


def load_universe(csv: Path | None = None) -> pd.DataFrame:
    """Analysis universe: licensed Japanese LN dropped, est_year 2007..2025."""
    df = pd.read_csv(csv or paths.OUT_DIR / "novels.csv")
    df["upd"] = pd.to_datetime(df["updated_at"], errors="coerce")
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(est, on="id", how="left")
    df["est_date"] = pd.to_datetime(df["est_date"])
    df = df[df["est_year"].between(GEN_MIN, GEN_MAX)].copy()
    for src, dst in [("favs", "fav_pctl"), ("clicks", "click_pctl"),
                     ("praises", "praise_pctl")]:
        g = df.groupby("est_year")[src]
        df[dst] = g.rank(ascending=True, method="average") / g.transform("size")
    df["pr"] = (df["praises"] / df["favs"].replace(0, pd.NA)).where(df["favs"] >= 10)
    g = df.groupby("est_year")["pr"]
    df["pctl_pr"] = g.rank(ascending=True, method="average") / g.transform("size")
    return df


def add_velocity(df: pd.DataFrame, content_end: pd.Timestamp) -> pd.DataFrame:
    """favs / days-since-release, percentile inside the launch quarter."""
    df = df.copy()
    df["age_days"] = (content_end - df["est_date"]).dt.days.clip(lower=1)
    df["vel"] = df["favs"] / df["age_days"]
    df["quarter"] = (df["est_date"].dt.year.astype(str) + "Q"
                     + df["est_date"].dt.quarter.astype(str))
    g = df.groupby("quarter")["vel"]
    df["vel_pctl"] = g.rank(ascending=True, method="average") / g.transform("size")
    return df


def monthly_ids(df: pd.DataFrame) -> set[int]:
    ids: set[int] = set()
    with paths.MONTHLY_RANKS.open(encoding="utf-8") as fh:
        for line in fh:
            for item in json.loads(line)["items"]:
                if item.get("nid"):
                    ids.add(int(item["nid"]))
    return ids & set(df["id"])


def short_supplement(df: pd.DataFrame) -> set[int]:
    """Report 19: dual-percentile Top-2000 over (word bin x generation)."""
    short = df[(df["words"] <= SHORT_MAX_WORDS) & (df["status"] == "已完结")].copy()
    short["wb"] = pd.cut(short["words"], SHORT_BINS, labels=SHORT_LABELS, right=True)
    short["grp"] = short["wb"].astype(str) + "|" + short["est_year"].astype(str)
    g = short.groupby("grp", observed=True)["favs"]
    short["p_grp"] = g.rank(ascending=True, method="average") / g.transform("size")
    return set(short.sort_values("p_grp", ascending=False).head(SHORT_TOP_N)["id"])


def admit(df: pd.DataFrame, content_end: pd.Timestamp,
          deep: set[int] | None = None) -> dict:
    """Return the V2 seed id set plus the audit trail that explains each part."""
    base = set(df.nlargest(REC_N, "favs")["id"])
    monthly = monthly_ids(df)
    featured = set(df.loc[df["featured"] == 1, "id"])
    short = short_supplement(df)
    core = base | monthly | featured

    recent = set(df[df["est_date"] >= content_end - pd.Timedelta(days=RECENT_DAYS)]["id"])
    active = set(df[df["upd"] >= content_end - pd.Timedelta(days=ACTIVE_DAYS)]["id"])
    loose = (recent | active) - core - short
    gated = set(df[df["id"].isin(loose)
                   & (df["vel_pctl"] >= VEL_PCTL_MIN)
                   & (df["favs"] >= TIME_MIN_FAVS)]["id"])

    if deep is None:
        deep = set(build_deep_ranks(df, 200)["nid"])

    ids = core | gated | short | deep
    return {
        "ids": ids,
        "base": base,
        "monthly": monthly,
        "featured": featured,
        "short": short,
        "loose": loose,
        "gated": gated,
        "cut": loose - gated,
        "deep": deep,
        "baseline": core | recent | active | short,
    }


def postconditions(df: pd.DataFrame, res: dict) -> list[tuple[str, bool, str]]:
    """Checks the rebuild must assert before shipping (P1-P3)."""
    seed = df[df["id"].isin(res["ids"])]
    base_seed = df[df["id"].isin(res["baseline"])]
    anchored = res["monthly"] | res["featured"] | res["deep"]
    noise = seed[(seed["favs"] < NOISE_FAVS) & (seed["words"] < NOISE_WORDS)]
    unanchored = noise[~noise["id"].isin(anchored)]
    p1 = res["deep"] <= res["ids"]
    p2 = unanchored.empty
    cov_new = seed["favs"].sum() / df["favs"].sum()
    cov_old = base_seed["favs"].sum() / df["favs"].sum()
    p3 = cov_new >= cov_old - 1e-9
    return [
        ("P1 深榜书全部在种子内", p1,
         f"{len(res['deep'])} 本深榜书，缺 {len(res['deep'] - res['ids'])}"),
        ("P2 favs<5 且字数<1万必须有外部锚", p2,
         f"无锚噪声 {len(unanchored)} 本" + (f"：{unanchored['id'].tolist()[:5]}"
                                       if len(unanchored) else "")),
        ("P3 收藏覆盖不低于现基线", p3, f"新 {cov_new:.2%} vs 现 {cov_old:.2%}"),
    ]


def band(favs: int) -> str:
    for hi, name in [(0, "0"), (4, "1-4"), (9, "5-9"), (49, "10-49"),
                     (99, "50-99"), (499, "100-499"), (1_999, "500-1,999"),
                     (9_999, "2k-10k"), (10 ** 9, "10k+")]:
        if favs <= hi:
            return name
    return "10k+"


def main() -> int:
    sys.path.insert(0, str(REPO / "analysis"))
    from lib import config as C  # noqa: E402

    content_end = pd.Timestamp(C.CONTENT_END) if hasattr(C, "CONTENT_END") \
        else pd.Timestamp("2026-05-03")
    df = add_velocity(load_universe(), content_end)
    res = admit(df, content_end, deep=set(build_deep_ranks(df, 200)["nid"]))
    fav_tot = df["favs"].sum()

    print(f"universe {len(df):,}  favs {fav_tot:,}  content_end {content_end.date()}")
    print(f"licensed rows appended by build_seed: {LICENSED}")

    for label, ids in [("现基线 V0", res["baseline"]), ("新规则 V2", res["ids"])]:
        sub = df[df["id"].isin(ids)]
        print(f"\n== {label} ==")
        print(f"books {len(ids):,} (seed.db {len(ids) + LICENSED:,} incl. licensed)")
        print(f"favs coverage {sub['favs'].sum() / fav_tot:.2%}")
        print(f"favs<5 {(sub['favs'] < 5).mean():.2%} | favs<10 {(sub['favs'] < 10).mean():.2%}"
              f" | favs=0 {int((sub['favs'] == 0).sum()):,}")
        print(f"median favs {sub['favs'].median():.0f} | median words "
              f"{sub['words'].median():.0f} | words<10k {(sub['words'] < 10_000).mean():.1%}")

    cut = df[df["id"].isin(res["cut"])]
    print(f"\n== 时间渠道门 (vel_pctl >= {VEL_PCTL_MIN}, 同季度) ==")
    print(f"loose-only {len(res['loose']):,} -> keep {len(res['gated']):,} / cut {len(cut):,}")
    print(f"cut: favs<5 {(cut['favs'] < 5).mean():.1%} | max favs {cut['favs'].max()} "
          f"| favs=0 {int((cut['favs'] == 0).sum()):,}")
    print(f"cut: max clicks {cut['clicks'].max():,} | click_pctl>=0.9 "
          f"{int((cut['click_pctl'] >= 0.9).sum())} | deep-rank books in cut "
          f"{len(res['cut'] & res['deep'])}")

    print("\n== 深榜补入 ==")
    print(f"deep books {len(res['deep']):,} | missing from baseline "
          f"{len(res['deep'] - res['baseline']):,} | missing from V2 "
          f"{len(res['deep'] - res['ids']):,}")

    print("\n== 门槛敏感性 ==")
    for t in (0.5, 0.6, 0.7):
        ids = (res["base"] | res["monthly"] | res["featured"] | res["short"]
               | set(df[df["id"].isin(res["loose"])
                       & (df["vel_pctl"] >= t)
                       & (df["favs"] >= TIME_MIN_FAVS)]["id"])
               | res["deep"])
        sub = df[df["id"].isin(ids)]
        print(f"  t={t}: books {len(ids):,} | coverage "
              f"{sub['favs'].sum() / fav_tot:.2%} | favs<5 {(sub['favs'] < 5).mean():.2%}")

    print("\n== 后置断言 ==")
    for name, ok, detail in postconditions(df, res):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    sub = df[df["id"].isin(res["ids"])]
    print("\n== V2 收藏分档 ==")
    tbl = (sub.groupby(sub["favs"].map(band))
           .agg(n=("id", "size"), favs=("favs", "sum")))
    tbl["share"] = tbl["n"] / len(sub)
    print(tbl.reindex(["0", "1-4", "5-9", "10-49", "50-99", "100-499",
                       "500-1,999", "2k-10k", "10k+"]).fillna(0).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

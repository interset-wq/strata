"""年度年表：把定年结果聚合成可直接读的「站点变迁史」。

只有一张表 ``era_stats``，每行一年。设计原则：

- **每个指标旁边都要能看见口径**。``p99_view`` 是当年新书的累计人气分位，
  跨年不可比（累计值 = 当年用户规模 × 曝光时间），所以同时给 ``grant_per_1k``
  ——「每千本新书拿到 banner 的数量」，与规模无关。
- **删失必须显式标出**。banner 书创作跨度中位 2.5 年、P75 4.6 年，所以最近
  3 年的授予量是下界而非实况。``censored`` 列标出这批年份。
- **不猜下架率**。nid 区间填充率受「nid 是否被非小说对象占用」影响，未验证，
  不作为列输出，只在报告里记为待查。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import era

# banner 书创作跨度 P25=1.3 / 中位=2.5 / P75=4.6 / P90=7.1 年。
# 取 3 年为删失下界：少于 3 年的年份，授予量还没发生完。
CENSOR_YEARS = 3


def attach(novels: pd.DataFrame, anchors: pd.DataFrame) -> pd.DataFrame:
    """给每本书定年。返回 ``novels_era`` 表。

    ``after_last_update`` 标记「估计创建日晚于最后更新」的书。这不是逻辑错误，
    而是插值误差的直接测量：这本书在 ``last_update`` 那天已经存在，所以
    ``est_date`` 晚了多少天，误差就至少有多少天。违约集中在锚点稀疏年份。
    """
    est = era.estimate(novels[["id"]], anchors, mode="log")
    lu = novels[["id", "last_update"]].copy()
    lu["lu_date"] = pd.to_datetime(lu["last_update"], utc=True).dt.tz_localize(None).dt.normalize()
    est = est.merge(lu[["id", "lu_date"]], on="id", how="left")
    est["err_lower_bound"] = (
        pd.to_datetime(est["est_date"]) - est["lu_date"]
    ).dt.days.clip(lower=0).astype("int32")
    est["after_last_update"] = est["err_lower_bound"] > 1
    return est.drop(columns=["lu_date"])


def build_stats(
    novels_era: pd.DataFrame,
    novels: pd.DataFrame,
    censor_years: int = CENSOR_YEARS,
) -> pd.DataFrame:
    """按年聚合。返回 ``era_stats`` 表。"""
    cols = ["id", "author", "has_banner", "click_num", "word_num", "ptype"]
    df = novels_era[["id", "est_date", "est_year", "confidence", "mode"]].merge(
        novels[cols], on="id", how="left"
    )

    # 作者首次出现年份：区分「新人涌入」与「老作者多产」
    debut = df.groupby("author", dropna=False)["est_year"].min()
    df["debut_year"] = df["author"].map(debut)

    rows = []
    for year, g in df.groupby("est_year", sort=True):
        b = g[g["has_banner"] == 1]
        rows.append(
            {
                "year": int(year),
                "books_new": len(g),
                "authors_new": int((g["debut_year"] == year).sum()),
                "banners": int(g["has_banner"].sum()),
                "p50_view": g["click_num"].median(),
                "p90_view": g["click_num"].quantile(0.90),
                "p99_view": g["click_num"].quantile(0.99),
                "median_word": g["word_num"].median(),
                "vip_pct": (g["ptype"] == 4).mean() * 100,
                "banner_median_view": b["click_num"].median() if len(b) else np.nan,
                "banner_median_word": b["word_num"].median() if len(b) else np.nan,
            }
        )
    stats = pd.DataFrame(rows)

    stats["grant_per_1k"] = (stats["banners"] * 1000.0 / stats["books_new"]).round(3)
    for c in ("p50_view", "p90_view", "p99_view", "median_word",
              "banner_median_view", "banner_median_word"):
        stats[c] = stats[c].round(0)
    stats["vip_pct"] = stats["vip_pct"].round(1)

    snapshot_year = int(df["est_year"].max())
    stats["censored"] = stats["year"] > snapshot_year - censor_years

    order = [
        "year", "books_new", "authors_new", "banners", "grant_per_1k",
        "p50_view", "p90_view", "p99_view", "median_word", "vip_pct",
        "banner_median_view", "banner_median_word", "censored",
    ]
    stats = stats[order]
    stats["year"] = stats["year"].astype("int16")
    stats["books_new"] = stats["books_new"].astype("int32")
    stats["authors_new"] = stats["authors_new"].astype("int32")
    stats["banners"] = stats["banners"].astype("int32")
    return stats


def maturity(con) -> pd.Series:
    """banner 书的创作跨度（年）——删失窗口的依据。"""
    df = con.execute(
        """select n.last_update, e.est_date from novels n join novels_era e using (id)
           where n.has_banner = 1"""
    ).df()
    span = (
        df["last_update"].dt.tz_localize(None) - pd.to_datetime(df["est_date"])
    ) / pd.Timedelta(days=365.25)
    return span

"""年度年表：把定年结果聚合成可直接读的「站点变迁史」。

只有一张表 ``era_stats``，每行一年。设计原则：

- **每个指标旁边都要能看见口径**。``p99_view`` 是当年新书的累计人气分位，
  跨年不可比（累计值 = 当年用户规模 × 曝光时间），所以同时给 ``grant_per_1k``
  ——「每千本新书拿到 banner 的数量」，与规模无关。
- **删失必须显式标出**。banner 书创作跨度中位 2.5 年、P75 4.6 年，所以最近
  3 年的授予量是下界而非实况。``censored`` 列标出这批年份。
- **不猜下架率**。nid 空洞确实是被删的行，但空号混着早期盗版日轻清理、管理员
  测试书、违规下架、作者主动撤下，比例不可归因，所以不作为列输出。
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
    """按年聚合。返回 ``era_stats`` 表。

    **排除引进日轻**（``flg_import``）。理由：版权方账号上传的书，banner 由版权方
    提供，不代表 SFACG 对原创作品的当期认可。实测影响很大——2006-2009 年原创
    banner 从 12 个降到 0，早期「引进期」才第一次有了硬定义。

    排除的量不丢：落在 ``import_books`` / ``import_banners`` 两列里，
    所以 ``books_new + import_books`` 才是当年全量。
    """
    cols = ["id", "author", "has_banner", "click_num", "word_num", "ptype", "flg_import"]
    df = novels_era[["id", "est_date", "est_year", "confidence", "mode"]].merge(
        novels[cols], on="id", how="left"
    )

    import_df = df[df["flg_import"].fillna(False)]
    # 年份骨架取自**全量**：2006 年 3 本书全是引进，排除后该年为 0，
    # 但年份本身不能消失——否则 books_new + import_books 的合计对不上。
    all_years = sorted(df["est_year"].unique())
    df = df[~df["flg_import"].fillna(False)]

    # 作者首次出现年份：区分「新人涌入」与「老作者多产」
    debut = df.groupby("author", dropna=False)["est_year"].min()
    df["debut_year"] = df["author"].map(debut)

    imp = import_df.groupby("est_year").agg(
        import_books=("id", "size"), import_banners=("has_banner", "sum")
    )

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
    # 补回被整年排除掉的年份（如 2006 全为引进书）
    missing = [y for y in all_years if y not in set(stats["year"])]
    if missing:
        pad = pd.DataFrame(
            {
                "year": missing,
                "books_new": 0,
                "authors_new": 0,
                "banners": 0,
                "p50_view": np.nan,
                "p90_view": np.nan,
                "p99_view": np.nan,
                "median_word": np.nan,
                "vip_pct": np.nan,
                "banner_median_view": np.nan,
                "banner_median_word": np.nan,
            }
        )
        stats = pd.concat([stats, pad], ignore_index=True).sort_values("year")
    stats = stats.reset_index(drop=True)

    stats["import_books"] = (
        stats["year"].map(imp["import_books"]).fillna(0).astype("int32")
    )
    stats["import_banners"] = (
        stats["year"].map(imp["import_banners"]).fillna(0).astype("int32")
    )

    denom = stats["books_new"].replace(0, np.nan)
    stats["grant_per_1k"] = (stats["banners"] * 1000.0 / denom).round(3)
    for c in ("p50_view", "p90_view", "p99_view", "median_word",
              "banner_median_view", "banner_median_word"):
        stats[c] = stats[c].round(0)
    stats["vip_pct"] = stats["vip_pct"].round(1)

    snapshot_year = int(df["est_year"].max())
    stats["censored"] = stats["year"] > snapshot_year - censor_years

    order = [
        "year", "books_new", "authors_new", "banners", "grant_per_1k",
        "p50_view", "p90_view", "p99_view", "median_word", "vip_pct",
        "banner_median_view", "banner_median_word",
        "import_books", "import_banners", "censored",
    ]
    stats = stats[order]
    stats["year"] = stats["year"].astype("int16")
    for c in ("books_new", "authors_new", "banners"):
        stats[c] = stats[c].astype("int32")
    return stats


def maturity(con) -> pd.Series:
    """banner 书的创作跨度（年）——删失窗口的依据。

    排除引进日轻：那些书是版权方整批上架的，创作跨度由原版出版时间决定，
    与「原创作品多久能成熟到拿 banner」无关。
    """
    df = con.execute(
        """select n.last_update, e.est_date from novels n join novels_era e using (id)
           where n.has_banner = 1 and not n.flg_import"""
    ).df()
    span = (
        df["last_update"].dt.tz_localize(None) - pd.to_datetime(df["est_date"])
    ) / pd.Timedelta(days=365.25)
    return span

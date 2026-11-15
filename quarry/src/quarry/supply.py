"""供给崩塌归因：2022 见顶后三年 −61%，少的是谁？

``annual.py`` 只回答「每年多了几本书」。这里回答**机制**：把每年的新书拆成
「当年才出现的新人」与「往年已经出现过的人」，再看新人自己的留存。

三个必须先钉死的前提，否则结论会全错：

1. **2026-05 之后不能进供给曲线**。判据不是分片，是 **nid 密度**：nid 是站点的自增
   序列，与日历无关地单调推进，而「每千个 nid 里落成几本书」长期稳定在 410–490
   （2025-09 至 2026-04 连续 8 个月实测）。2026-05 起这个比值掉到 36、6 月 54，
   可同期 nid 仍以 ~72/天 推进（``nid_density``）。**nid 没停、书却不见了，
   只能是新书在快照里不可见**，不是站点断供。所以年度口径一律截止
   ``SUPPLY_END = 2025``，2026 只用 1–4 月做**同窗口**对比。
2. **作者名即作者身份**。平台禁止改名与重名，``author`` 可作稳定身份键：按名字统计的
   新人流入与留存等同于按作者统计。唯一需注意的是字符串比较大小写敏感。
3. **作者首次出现年份受定年精度限制**。2016 及以前 100% 是 ``low``（见
   ``annual.build_stats`` 与留一法），所以 cohort 曲线只从 2015 起读。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 年度口径截止年：2026 只有大半年，且 5 月起新书不可见，不能进年度序列。
SUPPLY_END = 2025
# 同窗口：每年 1–4 月的累计量。4 月是 nid 密度还正常的最后一个月。
PARTIAL_MONTHS = 4
# 留存观测的 cohort 起点：2015 是 banner 元年，也是定年可信度的分界下方一年。
COHORT_START = 2015

# 长书门槛（字）。只用 50 万：200 万字在 2024-2025 必然被删失（书还没长到那么长）。
LONG_WORDS = 500_000


def _sql_novels() -> str:
    """所有分析的统一底表：剔除引进日轻、剔除 2026、带定年。"""
    return f"""
        select n.id, n.author, n.has_banner, n.word_num, n.click_num,
               e.est_year as y, e.est_date
        from novels n join novels_era e using (id)
        where not n.flg_import and e.est_year <= {SUPPLY_END}
    """


def nid_density(con, freq: str = "month", since: str | None = None) -> pd.DataFrame:
    """每千个 nid 里落成几本书 —— 判断「采集是否还完整」的唯一硬指标。

    ``nid`` 是站点自增序列，与日历无关地单调推进；只要采集完整，单位 nid 的成书数
    就稳定（2025-09 至 2026-04 实测 411–492）。它断崖式下跌只有两种解释：

    * 站点真的没人写书了 —— 但那样 ``nid_per_day`` 必须同步塌；
    * 新书在快照里不可见 —— nid 照常推进，只有成书数掉。

    两者用同一张表就能分开，**不需要借助上游的分片**。上游把库拆成三个文件只是
    为了分批解压加快首屏，与数据内容无关，本数据集已不保留该列。
    """
    key = (
        "strftime(e.est_date, '%Y-%m')"
        if freq == "month"
        else "e.est_year::varchar"
    )
    where = f"and e.est_date >= DATE '{since}'" if since else ""
    df = con.execute(
        f"""
        select {key} as period,
               count(*) as books,
               min(n.id) as nid_lo,
               max(n.id) as nid_hi,
               max(n.id) - min(n.id) as nid_span,
               date_diff('day', min(e.est_date), max(e.est_date)) + 1 as days
        from novels n join novels_era e using (id)
        where not n.flg_import {where}
        group by 1 order by 1
        """
    ).df()
    df["per_1k"] = (df["books"] * 1000.0 / df["nid_span"]).round(0)
    df["nid_per_day"] = (df["nid_span"] / df["days"]).round(1)
    return df


def panel(con) -> pd.DataFrame:
    """作者 × 年 面板。每行表示「某作者在某年发了几本」。"""
    return con.execute(
        f"""
        with b as ({_sql_novels()})
        select author, y, count(*) as books from b group by 1, 2
        """
    ).df()


def by_year(con) -> pd.DataFrame:
    """按年拆新人/老人。``books_new`` 是当年首次出现的人写的书。

    ``per_new`` / ``per_old`` 是**人均产书**——把「人少了」与「人写得少了」分开，
    这是归因的关键一步：如果人均没掉，那塌的就是人数。
    """
    df = con.execute(
        f"""
        with b as ({_sql_novels()}),
        d as (select author, min(y) as debut from b group by 1)
        select b.y as year,
               count(*) as books,
               count(distinct b.author) as authors,
               count(*) filter (where d.debut =  b.y) as books_new,
               count(*) filter (where d.debut <  b.y) as books_old,
               count(distinct b.author) filter (where d.debut =  b.y) as authors_new,
               count(distinct b.author) filter (where d.debut <  b.y) as authors_old
        from b join d using (author)
        group by 1 order by 1
        """
    ).df()
    df["per_new"] = (df["books_new"] / df["authors_new"]).round(2)
    df["per_old"] = (df["books_old"] / df["authors_old"]).round(2)
    return df


def retention(con, ks: tuple[int, ...] = (1, 2, 3, 5)) -> pd.DataFrame:
    """cohort 留存：某年首次出现的人，第 k 年还在发书的比例。

    不可观测的格子给 ``NaN`` 而不是 0——2025 年的人没有「第 1 年」可言，
    填 0 会让曲线在右端假摔。这是本模块唯一容易画错的地方。
    """
    p = panel(con)
    debut = p.groupby("author")["y"].min()
    rows = []
    for y0 in range(COHORT_START, SUPPLY_END + 1):
        members = debut.index[debut == y0]
        if len(members) == 0:
            continue
        row = {"cohort": y0, "n": len(members)}
        active = p[p["author"].isin(members)]
        for k in ks:
            if y0 + k > SUPPLY_END:
                row[f"k{k}"] = np.nan
                continue
            seen = active.loc[active["y"] == y0 + k, "author"].nunique()
            row[f"k{k}"] = round(seen * 100.0 / len(members), 1)
        rows.append(row)
    return pd.DataFrame(rows)


def long_books(con, threshold: int = LONG_WORDS) -> pd.DataFrame:
    """每年新书里「字数已达门槛」的绝对量与密度。

    字数在快照日是现值，所以**新书天然吃亏**（还没长到 50 万字）。
    2024-2025 的绝对数是下界；``per_1k`` 是比值，比绝对数耐删失一点，但也不是无偏。
    """
    df = con.execute(
        f"""
        with b as ({_sql_novels()})
        select y as year, count(*) as books,
               count(*) filter (where word_num >= {threshold}) as long_books
        from b group by 1 order by 1
        """
    ).df()
    df["per_1k"] = (df["long_books"] * 1000.0 / df["books"]).round(2)
    return df


def banner_authors(con) -> pd.DataFrame:
    """「被认可过的人」还在不在写。

    banner 作者 = 名下至少一本 banner 书的账号（444 个，含 4 个版权方账号已剔除）。
    这是比总量更狠的一个指标：连拿到过站方资源的人都在退出。
    """
    total = con.execute(
        "select count(distinct author) from novels where has_banner = 1 and not flg_import"
    ).fetchone()[0]
    df = con.execute(
        f"""
        with b as ({_sql_novels()}),
        ba as (select distinct author from novels where has_banner = 1 and not flg_import)
        select b.y as year,
               count(distinct b.author) filter (where b.author in (select author from ba)) as active
        from b group by 1 order by 1
        """
    ).df()
    df["total"] = total
    df["pct"] = (df["active"] * 100.0 / total).round(1)
    return df


def newcomer_to_banner(con) -> pd.DataFrame:
    """每一届新人里，最终拿到 banner 的比例。

    分母是**该届全部新人**（不管后来还在不在写），分子是其中名下有 banner 书的人。
    这不是「当年授予率」，是「这一届人里有多少最终被站方认可过」。

    删失警告：banner 书创作跨度中位 2.5 年，所以 2024-2025 届远未结算完，
    只有 2015-2022 可比（2022 届已过 4 年，中位成熟度已跨过）。
    """
    return con.execute(
        f"""
        with b as ({_sql_novels()}),
        d as (select author, min(y) as debut from b group by 1),
        ba as (select distinct author from novels where has_banner = 1 and not flg_import)
        select d.debut as cohort,
               count(*) as n,
               count(*) filter (where d.author in (select author from ba)) as got_banner
        from d group by 1 order by 1
        """
    ).df().assign(pct=lambda x: (x["got_banner"] * 100.0 / x["n"]).round(2))


def jan_to_apr(con) -> pd.DataFrame:
    """同窗口（1–4 月）累计供给。2026 只能这样比。

    直接拿 2026 全年和 2025 全年比会把「少了大半年」当成「腰斩」，
    这是所有半年快照报告最常见的错。同窗口比不需要任何年化假设。
    """
    return con.execute(
        f"""
        with b as (
            select e.est_year as y, extract(month from e.est_date) as m
            from novels n join novels_era e using (id) where not n.flg_import
        )
        select y as year, count(*) as books from b
        where m <= {PARTIAL_MONTHS} group by 1 order by 1
        """
    ).df()


def decompose(con, y_from: int = 2022, y_to: int = SUPPLY_END) -> dict:
    """把两年的供给差拆成「新人少写」与「老人少写」两笔。

    只做加法拆解，不做因果。它回答的是「谁不见了」，不是「为什么不见」。
    """
    d = by_year(con).set_index("year")
    a, b = d.loc[y_from], d.loc[y_to]
    drop_total = int(a["books"] - b["books"])
    drop_new = int(a["books_new"] - b["books_new"])
    drop_old = int(a["books_old"] - b["books_old"])
    assert drop_new + drop_old == drop_total, "拆解不守恒"
    return {
        "from": y_from,
        "to": y_to,
        "books_from": int(a["books"]),
        "books_to": int(b["books"]),
        "drop_total": drop_total,
        "drop_new": drop_new,
        "drop_old": drop_old,
        "share_new": drop_new / drop_total * 100,
        "share_old": drop_old / drop_total * 100,
        "authors_from": int(a["authors"]),
        "authors_to": int(b["authors"]),
    }

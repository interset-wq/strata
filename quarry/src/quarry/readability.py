"""可读性结构：24.6 万本里，真正能「推荐给别人读完」的有多少。

``annual.py`` 数每年多了几本书，``supply.py`` 问少的是谁，这里问的是**这些书有多少
是能读的**。三个口径必须先钉死，否则整份报告会得出反的结论：

1. **``outcome`` 是唯一权威的结局字段**，只有三值 ``ongoing`` / ``done`` / ``dead``。
   上游那个看起来像「5 种状态」的 ``status`` 其实是两个正交维度压成一列：
   结局（2 完结 / 4 断更 / 3 连载中）＋ A 标（5 = 断更A、6 = 完结A）。
   A 标是 novel_hub 按「banner OR 人气≥1000万 OR 长评≥60 OR 收藏≥1万 OR 赞≥1万」
   派生的**成绩**标记，判定式在原 2/4/5/6 的 243,193 行上零反例，
   所以 5/6 相对 2/4 不携带任何结局信息。它在构建期已被拆掉（见 config）。
   **旧版这里写的是「2 与 6 是两个物种，必须分带看」——那是错的框架**：
   6 相对 2 多出来的只是「收藏≥1万」，而收藏达标的长篇自然更长，
   于是分带看会得出「6 是长篇、2 是短篇」的假象。真实情况是
   2,440 本完结长篇（含 640 本 ≥100 万字）落在未达标组里。
2. **``stats_precise`` 只关于数值精度，不关于结局**。它覆盖 5,320 本（原 status
   3/5/6），这些书的 click/like/praise 来自详情页精确通道；其余 240,725 本的
   数值是列表页显示值，``like`` 上限 9,999、``click`` 上限 382 万。
   做任何「成绩」类统计前必须用这一列过滤，否则是在拿截断值排序。
3. **「坑率」不能用全库当分母**。2025-2026 的书还没到能判定的年纪（2026 年只有
   42% 有结局），所以结局类指标一律截到 ``SETTLED_END = 2025``，增速类截到更早。
4. **字数在快照日是现值，不是终值**。连载中的书还在长，所以「≥30 万字」的
   分母里天然少了一批未来的长书；这条只影响连载中的 2,805 本（1.1%），可忽略，
   但对 2024-2025 的「完结长书」计数是下界。
"""
from __future__ import annotations

import pandas as pd

# 结局分组。三值互斥且穷尽，没有「A 组」这第二个维度。
DONE = "outcome = 'done'"
DEAD = "outcome = 'dead'"
ONGOING = "outcome = 'ongoing'"

# 结局判定的截止年：2026 只有 42% 的书有结局（其余还在更或刚发），不能当分母。
SETTLED_END = 2025

# 「可读」门槛：完结 + ≥30 万字。选 30 万不是拍脑袋：
# 完结书字数 P25 = 30 万上下，低于这个量的「完结」绝大多数是短篇/一次性发布。
READ_MIN_WORDS = 300_000

# 字数分带。上界用中文网文的习惯说法（万字）。
BANDS = [
    (0, 1_000, "0–0.1 万"),
    (1_000, 10_000, "0.1–1 万"),
    (10_000, 50_000, "1–5 万"),
    (50_000, 100_000, "5–10 万"),
    (100_000, 300_000, "10–30 万"),
    (300_000, 500_000, "30–50 万"),
    (500_000, 1_000_000, "50–100 万"),
    (1_000_000, 10**12, "≥100 万"),
]

_BASE = "from novels where not flg_import"


def _band_sql(col: str = "word_num") -> str:
    """把 word_num 映射到 BANDS 的序号，供 group by 用。"""
    whens = " ".join(
        f"when {col} >= {lo} and {col} < {hi} then {i}" for i, (lo, hi, _) in enumerate(BANDS)
    )
    return f"case {whens} else -1 end"


def ladder(con) -> pd.DataFrame:
    """可读性阶梯：从「上架」到「够长且完结」，每一步剩多少。

    **这必须是一条单调链**。单独把「完结」插进来会破坏单调性（完结 43,577 >
    ≥30 万字 9,613，因为 92% 的「完结」是 30 万字以下的短篇），那样的表看着
    像漏斗其实是错的。`pct_prev` 是相对上一级的留存，能看出是哪一级在掉人。
    """
    n = con.execute(f"select count(*) {_BASE}").fetchone()[0]
    rows = [
        ("上架", f"select count(*) {_BASE}"),
        ("≥1 万字", f"select count(*) {_BASE} and word_num >= 10000"),
        ("≥10 万字", f"select count(*) {_BASE} and word_num >= 100000"),
        ("≥30 万字", f"select count(*) {_BASE} and word_num >= 300000"),
        (
            f"≥{READ_MIN_WORDS // 10000} 万字且完结",
            f"select count(*) {_BASE} and word_num >= {READ_MIN_WORDS} and {DONE}",
        ),
    ]
    out = pd.DataFrame(
        [{"stage": s, "books": con.execute(q).fetchone()[0]} for s, q in rows]
    )
    out["pct_all"] = (out["books"] * 100.0 / n).round(2)
    out["pct_prev"] = (out["books"] * 100.0 / out["books"].shift(1)).round(1)
    out.loc[0, "pct_prev"] = 100.0
    return out


def word_bands(con) -> pd.DataFrame:
    """字数分带 × 结局。回答「哪一段是坑，哪一段是成品」。

    ``done_pct`` 是带内的完结率——**这是全篇最反直觉的一列**：字数越长，
    完结率反而越高（因为断更的书根本长不到那里去）。
    """
    df = con.execute(
        f"""
        select {_band_sql()} as band,
               count(*) as books,
               count(*) filter (where {DONE}) as done,
               count(*) filter (where {DEAD}) as dead,
               count(*) filter (where {ONGOING}) as ongoing,
               round(median(click_num))::BIGINT as click_p50
        {_BASE}
        group by 1 order by 1
        """
    ).df()
    df["label"] = df["band"].map({i: b[2] for i, b in enumerate(BANDS)})
    df["pct"] = (df["books"] * 100.0 / df["books"].sum()).round(1)
    df["done_pct"] = (df["done"] * 100.0 / df["books"]).round(1)
    df["dead_pct"] = (df["dead"] * 100.0 / df["books"]).round(1)
    cum = df["books"][::-1].cumsum()[::-1]
    df["reach_pct"] = (cum * 100.0 / df["books"].sum()).round(1)
    return df[["band", "label", "books", "pct", "reach_pct", "done", "done_pct",
               "dead", "dead_pct", "ongoing", "click_p50"]]


def outcome_by_year(con, since: int = 2010) -> pd.DataFrame:
    """按年看结局构成，以及「成品率」= 完结且够长的比例。

    成品率是比完结率更可信的指标：完结率受「短篇一次发完就标完结」污染，
    成品率要求真的写到 30 万字又收了尾，没法靠标签糊过去。
    """
    df = con.execute(
        f"""
        select e.est_year as year, count(*) as books,
               count(*) filter (where n.outcome = 'done') as done,
               count(*) filter (where n.outcome = 'dead') as dead,
               count(*) filter (where n.outcome = 'ongoing') as ongoing,
               count(*) filter (where n.outcome = 'done'
                                  and n.word_num >= {READ_MIN_WORDS}) as done_long
        from novels n join novels_era e using (id)
        where not n.flg_import and e.est_year >= {since}
        group by 1 order by 1
        """
    ).df()
    df["done_pct"] = (df["done"] * 100.0 / df["books"]).round(1)
    df["dead_pct"] = (df["dead"] * 100.0 / df["books"]).round(1)
    df["done_long_per_1k"] = (df["done_long"] * 1000.0 / df["books"]).round(2)
    return df


def dropoff(con) -> pd.DataFrame:
    """断更发生在哪里 —— 用字数当尺子，不用天数。

    天数会被「一天发十章然后消失」和「隔月更一章」搅在一起；字数才是读者
    真正投入的量。``death_share`` 是**死在这一段**的断更书占全部断更的比例，
    ``reach_pct`` 是有多少断更书活着越过了这一段的起点。
    """
    n = con.execute(f"select count(*) {_BASE} and {DEAD}").fetchone()[0]
    # 只取关心的一侧边界，最后一段用「≥100 万」收尾
    edges = [(0, 10_000), (10_000, 50_000), (50_000, 100_000),
             (100_000, 300_000), (300_000, 500_000), (500_000, 10**12)]
    labels = ["<1 万", "1–5 万", "5–10 万", "10–30 万", "30–50 万", "≥50 万"]
    rows = []
    for (lo, hi), lab in zip(edges, labels):
        r = con.execute(
            f"""select count(*),
                       count(*) filter (where word_num >= {hi})
                {_BASE} and {DEAD}
                  and word_num >= {lo} and word_num < {hi}"""
        ).fetchone()
        rows.append({"label": lab, "lo": lo, "books": r[0]})
    out = pd.DataFrame(rows)
    out["death_share"] = (out["books"] * 100.0 / n).round(1)
    # 越过本段上界的断更书数 / 断更总数
    out["reach_pct"] = (
        (out["books"][::-1].cumsum()[::-1] - out["books"]) * 100.0 / n
    ).round(1)
    return out[["label", "lo", "books", "death_share", "reach_pct"]]


def finished_profile(con) -> pd.DataFrame:
    """完结书的形状：多长、写了多久、多快。

    分三行看，但**这三行不是「三种书」，是同一批完结书的成绩分层**：

    - 全部完结（43,581）：字数中位 1.0 万、跨度 13 天 —— 这才是「完结书」的常态。
    - 其中精确通道（原 status 6，1,388 本）：中位 108.7 万字、561 天。
    - 其中未达标/被截断（原 status 2，42,193 本）：中位 9,502 字、12 天。

    **不要说「6 是长篇、2 是短篇」**。6 之所以长，是因为它按「收藏≥1万」筛出来的，
    成绩好的书自然更长；这是选择偏差，不是定义。反证：完结且 ≥30 万字的 3,766 本里，
    只有 1,326 本（35%）在精确通道，另外 2,440 本（含 640 本 ≥100 万字）都在未达标组。
    想描述「长篇的典型形态」，用全部完结那一行，不要用 6 那一行。

    ``wpm`` 只在跨度 ≥30 天的书上算：天数太小时 word_num/span 会炸出几万字/天
    的假值（整本搬运的书就是这种）。跨度用 0 截断，全库 12.5% 的 est_date
    晚于 last_update，负值不能直接丢，那是有偏的。
    """
    q = "[0.25, 0.5, 0.75, 0.9]"
    rows = []
    tiers = (
        ("完结·全部", DONE),
        ("完结·精确通道", f"{DONE} and stats_precise"),
        ("完结·未达标/截断", f"{DONE} and not stats_precise"),
    )
    for kind, cond in tiers:
        w = con.execute(f"select quantile_cont(word_num, {q}) {_BASE} and {cond}").fetchone()[0]
        s = con.execute(
            f"""select quantile_cont(greatest(date_diff('day', est_date, last_update), 0), {q})
                from novels n join novels_era e using (id)
                where not n.flg_import and n.{cond}"""
        ).fetchone()[0]
        wpm = con.execute(
            f"""select median(word_num / date_diff('day', est_date, last_update) * 30.0)
                from novels n join novels_era e using (id)
                where not n.flg_import and n.{cond}
                  and date_diff('day', est_date, last_update) >= 30"""
        ).fetchone()[0]
        rows.append(
            {
                "kind": kind,
                "n": con.execute(f"select count(*) {_BASE} and {cond}").fetchone()[0],
                "w25": int(w[0]), "w50": int(w[1]), "w75": int(w[2]), "w90": int(w[3]),
                "s25": int(s[0]), "s50": int(s[1]), "s75": int(s[2]), "s90": int(s[3]),
                "wpm": int(wpm) if wpm is not None else None,
                # 中文阅读约 500 字/分钟
                "hours": round(w[1] / 500 / 60, 1),
            }
        )
    return pd.DataFrame(rows)


def dead_in_long(con) -> pd.DataFrame:
    """长书里的断更率 —— 「≥30 万字」这个筛选器到底有多少坑。

    这是给 App 的直接结论：只想筛长书、不看结局，一半会踩坑。
    """
    rows = []
    for m in (100_000, 300_000, 500_000, 1_000_000):
        r = con.execute(
            f"""select count(*),
                       count(*) filter (where {DEAD}),
                       count(*) filter (where {DONE})
                {_BASE} and word_num >= {m}"""
        ).fetchone()
        rows.append(
            {
                "min_words": m,
                "books": r[0],
                "dead": r[1],
                "done": r[2],
                "dead_pct": round(r[1] * 100.0 / r[0], 1),
                "done_pct": round(r[2] * 100.0 / r[0], 1),
            }
        )
    return pd.DataFrame(rows)


def click_share(con) -> pd.DataFrame:
    """注意力份额：各字数带拿走多少点击。

    警告：``not stats_precise`` 的 240,725 本，``click_num`` 被列表页截断在 382 万，
    所以 ≥100 万那一带的份额是**下界**。这一列只能看「长书拿走的份额远高于其数量占比」
    这个方向，不能引用具体数值。
    """
    df = word_bands(con).copy()
    tot = con.execute(f"select sum(click_num) {_BASE}").fetchone()[0]
    got = con.execute(
        f"select {_band_sql()} as band, sum(click_num) {_BASE} group by 1 order by 1"
    ).df().set_index("band")["sum(click_num)"]
    df["click_share"] = (df["band"].map(got) * 100.0 / tot).round(1)
    return df[["label", "books", "pct", "click_share"]]


def summary(con) -> dict:
    """几个要写进结论、也要被 tests 钉住的数。"""
    n = con.execute(f"select count(*) {_BASE}").fetchone()[0]
    done = con.execute(f"select count(*) {_BASE} and {DONE}").fetchone()[0]
    read = con.execute(
        f"select count(*) {_BASE} and {DONE} and word_num >= {READ_MIN_WORDS}"
    ).fetchone()[0]
    dead = con.execute(f"select count(*) {_BASE} and {DEAD}").fetchone()[0]
    half = con.execute(
        f"select count(*) {_BASE} and word_num < 10000"
    ).fetchone()[0]
    return {
        "books": n,
        "done": done,
        "done_pct": round(done * 100.0 / n, 1),
        "readable": read,
        "readable_pct": round(read * 100.0 / n, 2),
        "dead": dead,
        "dead_pct": round(dead * 100.0 / n, 1),
        "under_1w": half,
        "under_1w_pct": round(half * 100.0 / n, 1),
    }


if __name__ == "__main__":  # pragma: no cover
    import duckdb

    from . import config

    c = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    pd.set_option("display.width", 240)
    print(ladder(c).to_string(index=False))
    print()
    print(word_bands(c).to_string(index=False))
    print()
    print(outcome_by_year(c).to_string(index=False))
    print()
    print(dropoff(c).to_string(index=False))
    print()
    print(dead_in_long(c).to_string(index=False))
    print()
    print(finished_profile(c))
    print(summary(c))
    c.close()

"""可读性结构的断言：报告里每个结论都要有一条守着。

这里守四件事：分母不能悄悄变大（否则「1.5%」是假的）、
「越长越安全」不能退化成「长 = 安全」、上游的 A 标不能被当成结局、
「精确通道的书更长」不能被读成「长篇都成绩好」。
"""
from __future__ import annotations

import duckdb
import pytest

from quarry import config, readability as R


@pytest.fixture(scope="module")
def con():
    if not config.DUCKDB_PATH.exists():
        pytest.skip("数据集不存在，先跑 uv run python -m quarry.build_dataset")
    c = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    yield c
    c.close()


def test_outcomes_conserve(con):
    """完结 + 断更 + 连载 必须严格等于全库，一个都不能漏。"""
    s = R.summary(con)
    assert s["done"] + s["dead"] + 2805 == s["books"]
    assert s["books"] == config.BASELINE["novels_total"] - config.BASELINE["import_books"]


def test_outcome_groups_match_baseline(con):
    s = R.summary(con)
    assert s["done"] == config.BASELINE["done_books"]
    assert s["dead"] == config.BASELINE["dead_books"]


def test_ladder_is_monotone(con):
    """漏斗必须单调递减。把「完结」单独插进来会让它变成 453%，那是错的。"""
    d = R.ladder(con)
    assert list(d["books"]) == sorted(d["books"], reverse=True), d["books"].tolist()
    assert d["books"].iloc[-1] == config.BASELINE["readable_books"]
    assert d["pct_all"].iloc[-1] < 2.0


def test_half_the_library_is_micro(con):
    """一半的书不到 1 万字——这是「24.6 万本」这个数字的最大幻觉。"""
    s = R.summary(con)
    assert s["under_1w"] == config.BASELINE["under_10k_books"]
    assert 45 < s["under_1w_pct"] < 55


def test_done_rate_rises_past_the_100k_step(con):
    """10 万字是一道坎：过坎之后完结率单调上升，坎下则几乎是平的。

    0–0.1 万那一档要排除：里面 4,496 本标着「完结」但中位只有 428 字，
    是空壳，插进来会让这条曲线假摔。
    """
    b = R.word_bands(con)
    b = b[b["band"] > 0].reset_index(drop=True)
    flat = list(b.loc[b["band"] <= 3, "done_pct"])      # 0.1–10 万
    rise = list(b.loc[b["band"] >= 3, "done_pct"])      # 5–10 万往上
    assert max(flat) - min(flat) < 2.5, f"坎下不该有明显趋势：{flat}"
    assert rise == sorted(rise), f"过坎后完结率不再单调上升：{rise}"
    assert b["done_pct"].iloc[-1] > 50


def test_long_does_not_mean_safe(con):
    """「长 = 安全」是错觉：≥100 万字里仍有三成断更。"""
    d = R.dead_in_long(con).set_index("min_words")
    assert d.loc[1_000_000, "dead_pct"] == pytest.approx(
        config.BASELINE["dead_pct_at_1m"], abs=0.1
    )
    assert d["dead_pct"].is_monotonic_decreasing
    # ≥30 万字这个常用筛选器有一半是坑
    assert d.loc[300_000, "dead_pct"] > 50


def test_dropoff_shares_sum_to_100(con):
    """断更分段的占比必须加总到 100，否则说明有段落没被分到。"""
    d = R.dropoff(con)
    assert abs(d["death_share"].sum() - 100) < 0.5, d["death_share"].sum()
    first = d.iloc[0]
    assert first["label"] == "<1 万" and 45 < first["death_share"] < 55


def test_finished_tiers_are_score_strata_not_species(con):
    """「完结书」只有一种常态，其余两档是**成绩分层**，不是两种书。

    这是本模块最容易写错的地方（旧版就写错了）：上游 status 6 = 完结 + A 标，
    而 A 的实质是「收藏≥1万」。所以 6 更长是因为成绩好的书通常更长，
    是选择偏差；不能说成「6 是长篇、2 是短篇」。
    硬反证：完结且 ≥30 万字的书里，6 成以上落在**未达标**那一档。
    """
    f = R.finished_profile(con).set_index("kind")
    all_ = f.loc["完结·全部"]
    precise = f.loc["完结·精确通道"]
    rest = f.loc["完结·未达标/截断"]

    # 完结书的常态是短：中位 1 万字上下，不是 108 万字
    assert 8_000 < all_["w50"] < 12_000
    assert precise["n"] + rest["n"] == all_["n"]
    assert precise["w50"] > 1_000_000 and rest["w50"] < 20_000
    # 跨度必须是 0 截断后的值，不能出现负数
    for k in ("s25", "s50", "s75", "s90"):
        for row in (all_, precise, rest):
            assert row[k] >= 0

    tier = dict(
        con.execute(
            """select stats_precise, count(*) from novels
               where not flg_import and outcome = 'done' and word_num >= 300000
               group by 1"""
        ).fetchall()
    )
    share = tier[True] / sum(tier.values())
    assert share < 0.4, (
        f"完结长篇里精确通道占 {share:.0%}，超过 4 成了——"
        "那说明「6 更长」不只是选择偏差，得回头重看 A 的判定式"
    )

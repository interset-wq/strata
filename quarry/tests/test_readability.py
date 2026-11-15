"""可读性结构的断言：报告里每个结论都要有一条守着。

这里守三件事：分母不能悄悄变大（否则「1.5%」是假的）、
「越长越安全」不能退化成「长 = 安全」、2 与 6 两种完结不能混回一起。
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


def test_status_groups_match_baseline(con):
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


def test_finished_two_kinds_are_different(con):
    """status 2 与 6 是两个物种，混在一起的「完结书中位数」没有意义。"""
    f = R.finished_profile(con).set_index("kind")
    short = f.loc["完结 2（短篇/常规）"]
    long_ = f.loc["完结 6（长篇）"]
    assert short["w50"] < 20_000
    assert long_["w50"] > 1_000_000
    assert long_["w50"] / short["w50"] > 50
    # 跨度必须是 0 截断后的值，不能出现负数
    for k in ("s25", "s50", "s75", "s90"):
        assert short[k] >= 0 and long_[k] >= 0

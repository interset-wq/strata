"""供给归因的断言：数字漂移时先在这里红。

这里守的不是「数据集没坏」，而是**报告的结论没被数据推翻**：
拆解必须守恒、留存必须随 k 单调下降、2026 不能混进年度序列。
"""
from __future__ import annotations

import duckdb
import pytest

from quarry import config, supply


@pytest.fixture(scope="module")
def con():
    if not config.DUCKDB_PATH.exists():
        pytest.skip("数据集不存在，先跑 uv run python -m quarry.build_dataset")
    c = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    yield c
    c.close()


def test_year_series_stops_at_2025(con):
    """2026 不进年度序列。它只有 5 个月采集，混进来会造出假断崖。"""
    d = supply.by_year(con)
    assert d["year"].max() == supply.SUPPLY_END == 2025
    assert d["year"].min() == 2007


def test_channel_cutoff_is_real(con):
    """2026-05 的断崖必须是采集边界，不是站点行为。

    证据是两片互补：cold 在 4 月塌、hot 同时抬；5 月两片一起断。
    若哪天 cold 又有了 5 月的新书，说明上游改了通道，§1 的结论要重写。
    """
    m = supply.channel_check(con, since=2026).set_index("month")
    assert m.loc[4, "total"] > 900, "2026-04 应仍接近月均 1,000"
    assert m.loc[4, "cold"] < 150, "cold 在 4 月应已塌"
    assert m.loc[4, "hot"] > 800, "hot 应在 4 月接过来了"
    assert m.loc[5, "total"] < 150, "2026-05 两片应同时断供"
    mx = con.execute(
        "select max(e.est_date) from novels n join novels_era e using (id) where n.chunk = 'cold'"
    ).fetchone()[0]
    assert str(mx)[:10] <= "2026-05-01", f"cold 分片已越过 2026-05-01：{mx}"


def test_decomposition_conserves(con):
    """新人 + 老人 必须严格等于总量，逐年。"""
    d = supply.by_year(con)
    assert ((d["books_new"] + d["books_old"]) == d["books"]).all()
    assert ((d["authors_new"] + d["authors_old"]) == d["authors"]).all()


def test_decline_is_mostly_newcomers(con):
    """2022 → 2025 的缺口里，新人贡献超过 2/3。这是全文的主结论。"""
    x = supply.decompose(con)
    assert x["books_from"] == config.BASELINE["supply_2022"]
    assert x["books_to"] == config.BASELINE["supply_2025"]
    assert x["drop_total"] == config.BASELINE["supply_drop"]
    assert x["share_new"] > 2 / 3, f"新人占比只有 {x['share_new']:.1f}%"


def test_retention_is_monotone(con):
    """留存率必须随 k 单调不增。上下文必须是同一届人，所以只能届内比。"""
    r = supply.retention(con)
    for _, row in r.iterrows():
        vals = [row[k] for k in ("k1", "k2", "k3", "k5") if row[k] == row[k]]
        assert vals == sorted(vals, reverse=True), f"{row['cohort']} 届留存不单调：{vals}"


def test_retention_unobservable_is_nan(con):
    """观测不到的格子必须是 NaN。填 0 会让 2025 届的曲线假摔到 0。"""
    r = supply.retention(con).set_index("cohort")
    assert r.loc[2025, "k1"] != r.loc[2025, "k1"]  # NaN
    assert r.loc[2024, "k2"] != r.loc[2024, "k2"]
    assert r.loc[2023, "k1"] == r.loc[2023, "k1"]


def test_output_per_author_did_not_collapse(con):
    """人均产量没塌——这是「人少了而不是写少了」的关键证据。

    若哪天 per_old 跌到 1.2 以下，说明产能也坏了，§4 的结论要重写。
    """
    d = supply.by_year(con).set_index("year")
    assert d.loc[2025, "per_old"] > 1.3
    assert d.loc[2025, "per_new"] > 1.15
    # 活跃人数才是塌的那一项
    assert d.loc[2025, "authors"] < d.loc[2022, "authors"] * 0.5


def test_banner_conversion_collapsed(con):
    """新生代到 banner 的转化率跌了一个量级，且 2021 届已结算完毕。"""
    c = supply.newcomer_to_banner(con).set_index("cohort")
    assert c.loc[2015, "pct"] > 3.0
    assert c.loc[2021, "pct"] < 0.2
    assert c.loc[2021, "pct"] > 0
    # 2015 届的转化率必须是 2021 届的 20 倍以上
    assert c.loc[2015, "pct"] / c.loc[2021, "pct"] > 20


def test_long_books_hold_up_better_than_total(con):
    """长书跌幅必须小于总量跌幅——「塌的是短书」这条结论的直接检验。"""
    d = supply.long_books(con).set_index("year")
    total_drop = d.loc[2025, "books"] / d.loc[2022, "books"]
    long_drop = d.loc[2025, "long_books"] / d.loc[2022, "long_books"]
    assert long_drop > total_drop, f"长书 {long_drop:.2f} 未好于总量 {total_drop:.2f}"
    # 密度回升
    assert d.loc[2025, "per_1k"] > d.loc[2022, "per_1k"]

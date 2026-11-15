"""数据集基线断言：数据一旦漂移，这里先红，而不是等 App 首页出错才发现。

跑法：cd quarry && uv run pytest -q
"""

from __future__ import annotations

import json

import duckdb
import pytest

from quarry import config


@pytest.fixture(scope="module")
def con():
    if not config.DUCKDB_PATH.exists():
        pytest.skip("数据集不存在，先跑 uv run python -m quarry.build_dataset")
    c = duckdb.connect(str(config.DUCKDB_PATH), read_only=True)
    yield c
    c.close()


def scalar(con, sql: str) -> int:
    return con.execute(sql).fetchone()[0]


# ───────── 规模 ─────────


def test_novels_total(con):
    assert scalar(con, "select count(*) from novels") == config.BASELINE["novels_total"]


def test_three_chunks_complete(con):
    rows = dict(con.execute("select chunk, count(*) from novels group by 1").fetchall())
    assert sum(rows.values()) == config.BASELINE["novels_total"]
    assert set(rows) == set(config.CHUNKS)


def test_banner_only_in_warm_and_hot(con):
    assert scalar(con, "select count(*) from novels where has_banner") == config.BASELINE["banner_total"]
    assert scalar(con, "select count(*) from novels where has_banner and chunk='cold'") == 0
    w = scalar(con, "select count(*) from novels where has_banner and chunk='warm'")
    h = scalar(con, "select count(*) from novels where has_banner and chunk='hot'")
    assert (w, h) == (config.BASELINE["banner_warm"], config.BASELINE["banner_hot"])


# ───────── 归一化 ─────────


def test_tag_name_is_unique_key(con):
    assert scalar(con, "select count(*)-count(distinct name) from tags") == 0
    assert scalar(con, "select count(*) from tags") == config.BASELINE["tag_total"]


def test_every_novel_tag_resolves(con):
    orphan = scalar(
        con,
        """select count(*) from novel_tags nt
           left join tags t on t.tag_id = nt.tag_gid
           where t.tag_id is null""",
    )
    assert orphan == 0


def test_novel_tag_pairs_unique(con):
    dup = scalar(
        con,
        "select count(*) from (select novel_id, tag_gid from novel_tags group by 1,2 having count(*)>1)",
    )
    assert dup == 0


def test_no_orphan_novel_reference(con):
    orphan = scalar(
        con,
        """select count(*) from novel_tags nt
           left join novels n on n.id = nt.novel_id where n.id is null""",
    )
    assert orphan == 0


# ───────── 去重 ─────────


def test_authors_deduped(con):
    assert scalar(con, "select count(*) from authors") == config.BASELINE["authors_clean"]
    assert scalar(con, "select count(*)-count(distinct name) from authors") == 0


def test_contests_deduped(con):
    assert scalar(con, "select count(*) from contests") == config.BASELINE["contests_clean"]
    assert scalar(con, "select count(*)-count(distinct name) from contests") == 0


def test_contest_reference_resolves(con):
    orphan = scalar(
        con,
        """select count(*) from novels n
           left join contests c on c.contest_id = n.contest_id
           where n.contest_id is not null and c.contest_id is null""",
    )
    assert orphan == 0


# ───────── 清洗 ─────────


def test_like_num_has_no_negative(con):
    assert scalar(con, "select count(*) from novels where like_num < 0") == 0
    # 原值为负的行必须被标记，且数量与来源一致
    assert scalar(con, "select count(*) from novels where flg_like_fixed") == config.BASELINE["like_negative"]
    assert scalar(con, "select count(*) from novels where flg_like_fixed and like_num is not null") == 0


def test_comment_null_is_not_zero(con):
    """comment_num 的 NULL 表示"未采集"，绝不能当成 0。"""
    missing = scalar(con, "select count(*) from novels where comment_num is null")
    zero = scalar(con, "select count(*) from novels where comment_num = 0")
    assert missing == scalar(con, "select count(*) from novels where flg_comment_missing")
    assert missing > 240_000 and zero > 0


def test_known_anomalies_are_flagged_not_deleted(con):
    """异常原样在库，只打标记——它们是待分析的病灶，不是脏数据。"""
    assert (
        scalar(con, "select count(*) from novels where flg_default_cover")
        == config.BASELINE["default_cover"]
    )
    assert scalar(con, "select count(*) from novels where click_num = 0") == config.BASELINE["zero_click"]
    dup = scalar(
        con,
        "select count(*) from (select title, author from novels group by 1,2 having count(*)>1)",
    )
    assert dup == config.BASELINE["dup_title_author_groups"]


def test_enum_values_legal(con):
    for col, ok in [("genre", range(1, 11)), ("status", range(1, 8)), ("ptype", range(1, 5))]:
        ok_list = ",".join(map(str, ok))
        bad = scalar(
            con, f"select count(*) from novels where {col} is null or {col} not in ({ok_list})"
        )
        assert bad == 0, f"{col} 存在非法值"


# ───────── 定年（era） ─────────


def test_anchors_monotonic():
    """nid 严格单调是定年模型成立的唯一前提。同刻锚点允许（批量导入）。"""
    from quarry import era

    a = era.load_anchors()
    assert len(a) >= 85, "锚点少于 85 个，定年精度不足"
    g = era.check_anchors(a)
    assert g.order_bad.iloc[0] == 0, "存在真逆序锚点（日期随 nid 递减）"
    # 锚点必须覆盖全库首尾，否则头尾 2.5% 会被外推
    nid_min, nid_max = scalar(
        duckdb.connect(str(config.DUCKDB_PATH), read_only=True),
        "select min(id) from novels",
    ), 777_879
    assert a.nid.min() <= nid_min + 1, "缺少最早锚点，头部会外推"
    assert a.nid.max() >= 777_000, "缺少最新锚点，尾部会外推"


def test_leave_one_out_accuracy():
    """留一法中位误差必须为 0 天、极值可控。

    留出单元是「同一时间戳的整组锚点」——采样时每个分位点抓 2 本相邻 nid，
    两者 addTime 常相同，只去掉一个会泄漏答案。
    """
    from quarry import era

    lo = era.leave_one_out(era.load_anchors(), mode="log")
    interp = lo[lo.kind == "interp"]
    err = interp.err_day.abs()
    assert err.median() <= 1.0, f"中位误差 {err.median()} 天过大"
    assert err.quantile(0.95) <= 30.0, f"P95 误差 {err.quantile(0.95)} 天过大"
    assert err.max() <= 365.0, f"最大误差 {err.max()} 天过大"


def test_est_date_error_is_measured_not_hidden(con):
    """创建日期应 ≤ 最后更新时间，但插值必然有误差。

    所以不要求零违约（那是在要求模型无错），而是用**违约率 + 违约幅度**
    监控模型质量。违约幅度本身是误差下界：书在 last_update 那天已存在，
    est_date 晚了几天，误差就至少几天。
    """
    total = scalar(con, "select count(*) from novels_era")
    bad = scalar(con, "select count(*) from novels_era where after_last_update")
    assert bad / total < 0.15, f"定年误差过大：{bad/total:.1%} 的书创建日晚于最后更新"

    med = scalar(
        con, "select median(err_lower_bound) from novels_era where after_last_update"
    )
    assert med < 90, f"违约幅度中位 {med} 天，超出可接受范围"


def test_after_last_update_concentrates_in_sparse_years(con):
    """违约应集中在锚点稀疏的早年，而不是均匀分布。

    如果哪天变成均匀分布，说明 nid 单调假设本身出问题了，不是精度问题。
    """
    rows = dict(
        con.execute(
            """select est_year, avg(after_last_update::int)
               from novels_era group by 1"""
        ).fetchall()
    )
    early = sum(rows[y] for y in range(2008, 2016)) / 8
    late = sum(rows[y] for y in range(2020, 2026)) / 6
    assert early > late, f"早年违约率 {early:.1%} 未高于近年 {late:.1%}，模型假设可疑"


def test_no_extrapolation(con):
    """锚点覆盖全库后，不应有任何书靠外推定年。"""
    assert scalar(con, "select count(*) from novels_era where mode <> 'interp'") == 0


def test_era_covers_every_novel(con):
    assert scalar(con, "select count(*) from novels_era") == config.BASELINE["novels_total"]
    assert scalar(
        con, "select count(*) from novels n left join novels_era e using (id) where e.id is null"
    ) == 0


def test_era_stats_conserves_totals(con):
    """年表必须与总表守恒：book 数、banner 数一个不差。"""
    assert scalar(con, "select sum(books_new) from era_stats") == config.BASELINE["novels_total"]
    assert scalar(con, "select sum(banners) from era_stats") == config.BASELINE["banner_total"]
    assert scalar(con, "select count(*) from era_stats") == 21  # 2006–2026


def test_dating_precision_splits_at_2017(con):
    """锚点按 2.5% 分位采样，所以书少的年份锚点稀、定年不可信。

    这是采样设计的性质，必须显式守住：2016 及以前 gap_days > 365（low），
    2017 起锚点密集（无 low）。若哪天变了，说明锚点集被改动过。
    """
    rows = dict(
        con.execute(
            """select est_year, avg((confidence = 'low')::int)
               from novels_era group by 1"""
        ).fetchall()
    )
    for y in range(2017, 2027):
        assert rows[y] < 0.01, f"{y} 年出现 low 置信度，锚点覆盖变差"
    for y in range(2011, 2016):
        assert rows[y] > 0.9, f"{y} 年置信度异常升高，锚点集被改动"


# ───────── 可复现 ─────────


def test_manifest_matches_tables(con):
    assert config.MANIFEST_PATH.exists(), "缺少 manifest.json"
    m = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert m["version"] == config.DATASET_VERSION
    assert m["schema_version"] == config.SCHEMA_VERSION
    for name in ("novels", "novels_era", "era_stats", "tags", "novel_tags", "authors", "contests"):
        assert m["tables"][name]["rows"] == scalar(con, f"select count(*) from {name}"), name
        assert (config.DATASET_DIR / m["tables"][name]["file"]).exists(), f"{name}.parquet 缺失"


def test_manifest_records_anchors():
    m = json.loads(config.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert m["anchors"]["count"] >= 85
    assert (config.ROOT / m["anchors"]["file"]).exists(), "锚点文件未入库"

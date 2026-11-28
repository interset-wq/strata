"""Validate a built seed.db before it is gzipped into app/assets/."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

SCHEMA_VERSION = 10
EXPECTED_TABLES = {"books", "book_tags", "seed_meta", "deep_ranks",
                   "calendar_universe", "contest_awards", "author_ranks",
                   "calib_fav_bounds", "calib_len_anchors",
                   "calib_cqs_median", "calib_cps_median", "eras_anchors"}
EXPECTED_INDEXES = {
    "idx_bt", "idx_updated", "idx_author", "idx_year_favs",
    "idx_genre_favs", "idx_favs", "idx_pr", "idx_shortfav",
    "idx_deep_lookup", "idx_awards_edition", "idx_form_cqs",
}


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def check_db(db_path: Path, seed: pd.DataFrame, meta: dict) -> None:
    errors: list[str] = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            _fail(errors, f"integrity_check: {integrity}")

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%'")}
        if tables != EXPECTED_TABLES:
            _fail(errors, f"tables {sorted(tables)} != {sorted(EXPECTED_TABLES)}")

        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")}
        if indexes != EXPECTED_INDEXES:
            _fail(errors, f"indexes {sorted(indexes)} != {sorted(EXPECTED_INDEXES)}")

        books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        licensed = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=1").fetchone()[0]
        if books != len(seed):
            _fail(errors, f"book_count {books} != DataFrame {len(seed)}")
        if books != meta["seed_rows"]:
            _fail(errors, f"book_count {books} != seed_rows {meta['seed_rows']}")
        if licensed != meta["licensed_rows"]:
            _fail(errors, f"licensed {licensed} != {meta['licensed_rows']}")

        tag_rows = conn.execute("SELECT COUNT(*) FROM book_tags").fetchone()[0]
        tag_count = conn.execute("SELECT COUNT(DISTINCT tag) FROM book_tags").fetchone()[0]
        empty_tags = conn.execute(
            "SELECT COUNT(*) FROM book_tags WHERE tag=''").fetchone()[0]
        orphan_tags = conn.execute(
            "SELECT COUNT(*) FROM book_tags t LEFT JOIN books b ON b.nid=t.nid"
            " WHERE b.nid IS NULL").fetchone()[0]
        if tag_rows == 0 or tag_count == 0:
            _fail(errors, "book_tags is empty")
        if empty_tags:
            _fail(errors, f"{empty_tags} empty tags")
        if orphan_tags:
            _fail(errors, f"{orphan_tags} tags reference missing nids")

        # D2 deep ranks: additive, full-universe, never a percentile denominator.
        deep_rows = conn.execute("SELECT COUNT(*) FROM deep_ranks").fetchone()[0]
        deep_expected = len(meta.get("deep_ranks", []))
        if deep_rows == 0 or (deep_expected and deep_rows != deep_expected):
            _fail(errors, f"deep_ranks {deep_rows} != expected {deep_expected}")
        dup_deep = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT est_year || '|' || metric || '|' || rank_no)"
            " FROM deep_ranks").fetchone()[0]
        if dup_deep:
            _fail(errors, f"{dup_deep} duplicate deep rank positions")
        deep_metrics = {r[0] for r in conn.execute("SELECT DISTINCT metric FROM deep_ranks")}
        if deep_metrics != {"favs", "clicks", "praises", "pr"}:
            _fail(errors, f"deep metrics {sorted(deep_metrics)} != expected four")
        bad_deep = conn.execute(
            "SELECT COUNT(*) FROM deep_ranks WHERE pctl IS NULL OR pctl <= 0 OR pctl > 1"
            " OR rank_no < 1 OR est_year NOT BETWEEN 2007 AND 2026").fetchone()[0]
        if bad_deep:
            _fail(errors, f"{bad_deep} deep rows have invalid rank/pctl/year")
        pr_gate = conn.execute(
            "SELECT COUNT(*) FROM deep_ranks d JOIN books b ON b.nid=d.nid"
            " WHERE d.metric='pr' AND b.favs < 10").fetchone()[0]
        if pr_gate:
            _fail(errors, f"{pr_gate} pr deep rows violate favs>=10 gate")
        deep_meta_row = conn.execute(
            "SELECT value FROM seed_meta WHERE key='deep_rank_rows'").fetchone()
        if deep_meta_row is None or int(deep_meta_row[0]) != deep_rows:
            _fail(errors, "seed_meta deep_rank_rows mismatch")

        # v5 contest awards: additive display facts (never admission/ordering,
        # docs/contest-display-in-app.md §6). Pinned total + clean fields.
        award_rows = conn.execute(
            "SELECT COUNT(*) FROM contest_awards").fetchone()[0]
        award_expected = len(meta.get("awards", []))
        if award_rows == 0 or (award_expected and award_rows != award_expected):
            _fail(errors, f"contest_awards {award_rows} != expected {award_expected}")
        bad_award = conn.execute(
            "SELECT COUNT(*) FROM contest_awards WHERE nid <= 0 OR edition IS NULL"
            " OR edition='' OR award IS NULL OR award='' OR source_nid IS NULL"
            " OR source_nid=''").fetchone()[0]
        if bad_award:
            _fail(errors, f"{bad_award} award rows with invalid fields")
        dup_award = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT nid || '|' || edition)"
            " FROM contest_awards").fetchone()[0]
        if dup_award:
            _fail(errors, f"{dup_award} duplicate (nid, edition) award rows")
        award_meta_row = conn.execute(
            "SELECT value FROM seed_meta WHERE key='award_rows'").fetchone()
        if award_meta_row is None or int(award_meta_row[0]) != award_rows:
            _fail(errors, "seed_meta award_rows mismatch")

        # v10 author ranks (docs/author-rank.md §9): additive display table,
        # zero runtime computation. Guards: expected row count, <= 500 total,
        # clean fields, rank_no contiguous from 1 per form, meta cross-check.
        ar_rows = conn.execute("SELECT COUNT(*) FROM author_ranks").fetchone()[0]
        ar_expected = len(meta.get("author_ranks", []))
        if ar_rows == 0 or (ar_expected and ar_rows != ar_expected):
            _fail(errors, f"author_ranks {ar_rows} != expected {ar_expected}")
        if ar_rows > 500:
            _fail(errors, f"author_ranks {ar_rows} > 500 (5 forms x 100)")
        bad_ar = conn.execute(
            "SELECT COUNT(*) FROM author_ranks WHERE author IS NULL OR author=''"
            " OR rep_title IS NULL OR rep_title='' OR rep_nid <= 0"
            " OR form NOT IN ('long','dialogue','medium','short','ip_collab')"
        ).fetchone()[0]
        if bad_ar:
            _fail(errors, f"{bad_ar} author_rank rows with invalid fields")
        ar_gap = conn.execute(
            "SELECT COUNT(*) FROM (SELECT form, MAX(rank_no) - MIN(rank_no) + 1"
            " - COUNT(*) AS missing FROM author_ranks GROUP BY form)"
            " WHERE missing > 0").fetchone()[0]
        if ar_gap:
            _fail(errors, f"{ar_gap} forms with non-contiguous author rank_no")
        ar_meta_row = conn.execute(
            "SELECT value FROM seed_meta WHERE key='author_rank_rows'").fetchone()
        if ar_meta_row is None or int(ar_meta_row[0]) != ar_rows:
            _fail(errors, "seed_meta author_rank_rows mismatch")

        required = {"schema_version", "seed_version", "content_end", "built_at",
                    "book_count", "tag_count", "gen_min", "gen_max", "licensed_count",
                    "deep_metrics", "deep_top_n", "deep_rank_rows", "deep_seed_hit",
                    "award_rows", "calibration_version", "cqs_scored",
                    "cqs_stable", "cps_scored", "cqs_mu0", "author_rank_rows"}
        meta_keys = {r["key"] for r in conn.execute("SELECT key FROM seed_meta")}
        if not required <= meta_keys:
            _fail(errors, f"seed_meta missing {sorted(required - meta_keys)}")
        schema_version = conn.execute(
            "SELECT value FROM seed_meta WHERE key='schema_version'").fetchone()[0]
        if int(schema_version) != SCHEMA_VERSION:
            _fail(errors, f"schema_version {schema_version} != {SCHEMA_VERSION}")
        meta_book_count = conn.execute(
            "SELECT value FROM seed_meta WHERE key='book_count'").fetchone()[0]
        if int(meta_book_count) != books:
            _fail(errors, f"seed_meta book_count {meta_book_count} != {books}")

        dating = conn.execute(
            "SELECT COUNT(*) FROM books WHERE est_year IS NULL OR est_date IS NULL"
            " OR est_conf IS NULL").fetchone()[0]
        if dating:
            _fail(errors, f"{dating} rows without dating")

        # v9 (E.30): universe percentile columns no longer ship; only pr
        # (device-recomputable) is a per-book score, and licensed rows carry
        # none.
        ln_pctl = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=1 AND pr IS NOT NULL"
        ).fetchone()[0]
        if ln_pctl:
            _fail(errors, f"{ln_pctl} licensed rows carry pr")

        bad_pr = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=0 AND ("
            " (favs >= 10 AND pr IS NULL) OR (favs < 10 AND pr IS NOT NULL))"
        ).fetchone()[0]
        if bad_pr:
            _fail(errors, f"{bad_pr} rows violate pr rule (favs<10 -> NULL)")

        # V3 quality columns: form is total; lqs/pctl are (0,1] or NULL.
        bad_form = conn.execute(
            "SELECT COUNT(*) FROM books WHERE form IS NULL OR form NOT IN"
            " ('invalid','short','medium','long','dialogue','ip_collab')").fetchone()[0]
        if bad_form:
            _fail(errors, f"{bad_form} rows have invalid form")
        # E.31: every non-licensed short/medium book must be 已完结 (the two
        # official categories merged in 2026); human-curated exemptions and
        # the E.39/E.40 forced whitelist may waive. Licensed LNs are a
        # display-only carve-out (user ruling).
        exempt = set(meta.get("manual_exempt", ()))
        forced_whitelist = set(meta.get("forced_whitelist", ()))
        serial_short = conn.execute(
            "SELECT nid FROM books WHERE is_licensed=0"
            " AND form IN ('short','medium')"
            " AND (status IS NULL OR status <> '已完结')").fetchall()
        serial_violations = [r["nid"] for r in serial_short
                             if r["nid"] not in exempt and r["nid"] not in forced_whitelist]
        if serial_violations:
            _fail(errors, f"serial short/medium in seed: {serial_violations[:10]}")
        # E.32: human blacklist is an unconditional seed veto (it outranks the
        # manual exemption list); the DB check spans the whole seed, while the
        # anchor loader validates nids against the non-licensed universe.
        blacklist = set(meta.get("manual_blacklist", ())) - forced_whitelist  # E.39/E.40 白名单优先
        blacklist_hits = seed.loc[seed["nid"].isin(blacklist), "nid"].tolist()
        if blacklist_hits:
            _fail(errors, f"blacklisted nids in seed: {blacklist_hits[:10]}")
        # v8: lqs/lqs_pctl/vel_pctl are no longer columns (archived,
        # report lineage only); licensed rows still carry no runtime scores.
        ln_quality = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=1 AND"
            " (cqs IS NOT NULL OR cps IS NOT NULL OR len_norm IS NOT NULL"
            "  OR cqs_state IS NOT NULL)"
        ).fetchone()[0]
        if ln_quality:
            _fail(errors, f"{ln_quality} licensed rows carry quality scores")

        # v6 runtime metrics (app/docs/18-runtime-metrics.md, report 24):
        # structural gates — form isolation, gates, state consistency.
        short_cqs = conn.execute(
            "SELECT COUNT(*) FROM books WHERE form IN ('short','ip_collab')"
            " AND (cqs IS NOT NULL OR len_norm IS NOT NULL)").fetchone()[0]
        if short_cqs:
            _fail(errors, f"{short_cqs} short/ip rows carry cqs/len_norm")
        cqs_gate = conn.execute(
            "SELECT COUNT(*) FROM books WHERE cqs IS NOT NULL AND favs < 1000"
        ).fetchone()[0]
        if cqs_gate:
            _fail(errors, f"{cqs_gate} cqs rows violate favs>=1000 gate")
        bad_state = conn.execute(
            "SELECT COUNT(*) FROM books WHERE (cqs IS NULL AND cqs_state IS NOT"
            " NULL) OR (cqs IS NOT NULL AND (cqs_state IS NULL OR cqs_state NOT"
            " IN ('stable','low')))").fetchone()[0]
        if bad_state:
            _fail(errors, f"{bad_state} rows have inconsistent cqs_state")
        bad_len = conn.execute(
            "SELECT COUNT(*) FROM books WHERE (cqs IS NULL AND len_norm IS NOT"
            " NULL) OR (len_norm IS NOT NULL AND (len_norm < 0 OR len_norm > 1))"
        ).fetchone()[0]
        if bad_len:
            _fail(errors, f"{bad_len} rows violate len_norm rule (cqs-coupled, [0,1])")
        for table in ("calib_fav_bounds", "calib_len_anchors",
                      "calib_cqs_median", "calib_cps_median"):
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if n == 0:
                _fail(errors, f"{table} is empty")
        bad_cell = conn.execute(
            "SELECT COUNT(*) FROM calib_cqs_median WHERE cell_n < 5"
            " OR med IS NULL").fetchone()[0]
        if bad_cell:
            _fail(errors, f"{bad_cell} calib_cqs_median rows below the cell floor")
        eras_rows = conn.execute("SELECT COUNT(*) FROM eras_anchors").fetchone()[0]
        if eras_rows < 280:
            _fail(errors, f"eras_anchors {eras_rows} < 280")
        eras_mono = conn.execute(
            "SELECT COUNT(*) FROM (SELECT nid - LAG(nid) OVER (ORDER BY nid)"
            " AS step FROM eras_anchors) WHERE step <= 0").fetchone()[0]
        if eras_mono:
            _fail(errors, f"{eras_mono} non-monotonic eras anchor nids")
        eras_meta_row = conn.execute(
            "SELECT value FROM seed_meta WHERE key='eras_anchor_rows'").fetchone()
        if eras_meta_row is None or int(eras_meta_row[0]) != eras_rows:
            _fail(errors, "seed_meta eras_anchor_rows mismatch")

        ln_range = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=0 AND"
            " (est_year < 2007 OR est_year > 2026)").fetchone()[0]
        if ln_range:
            _fail(errors, f"{ln_range} non-licensed rows outside 2007..2026")

        sample = conn.execute(
            "SELECT nid, is_licensed, pr FROM books WHERE nid=2242").fetchone()
        if sample is None or sample["is_licensed"] != 1 or sample["pr"] is not None:
            _fail(errors, "known licensed book nid=2242 is missing or not excluded")

        dup = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT nid) FROM books").fetchone()[0]
        if dup:
            _fail(errors, f"{dup} duplicate nids")

        # Titles are NOT globally unique: 24 duplicate titles in the analysis
        # universe (13 across different authors). Only an exact duplicate of
        # title + author + words + favs is a snapshot artifact; title reuse by
        # another author is legitimate and is printed as an audit note.
        title_reuse = []
        for title, nids in conn.execute(
                "SELECT title, GROUP_CONCAT(nid) FROM books"
                " GROUP BY title HAVING COUNT(*) > 1"):
            rows = conn.execute(
                "SELECT nid, author, words, favs FROM books WHERE title=?",
                (title,)).fetchall()
            signature = {(r["author"], r["words"], r["favs"]) for r in rows}
            if len(rows) > 1 and len(signature) == 1:
                _fail(errors, f"duplicate book record {title!r}: nids {nids}")
            else:
                title_reuse.append(f"{title!r}: {nids}")
        if title_reuse:
            print(f"validate: {len(title_reuse)} reused title(s) across distinct books"
                  f" (audit only): {'; '.join(title_reuse[:6])}")

        print(
            f"validate: books={books} licensed={licensed} tags={tag_rows}/{tag_count}"
            f" universe={meta['universe_rows']} admitted={meta.get('admitted', '?')}"
            f" v0={meta.get('baseline_v0', '?')} awards={award_rows}"
        )
    finally:
        conn.close()

    if errors:
        for err in errors:
            print("  -", err, file=sys.stderr)
        raise SystemExit(f"seed validation failed: {len(errors)} issue(s)")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("seed.db")
    if not path.exists():
        raise SystemExit(f"missing {path}")
    conn = sqlite3.connect(path)
    meta = {
        "seed_rows": conn.execute("SELECT COUNT(*) FROM books").fetchone()[0],
        "licensed_rows": conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=1").fetchone()[0],
        "universe_rows": 0, "admitted": 0, "baseline_v0": 0,
    }
    conn.close()
    seed = pd.read_sql_query("SELECT * FROM books", sqlite3.connect(path))
    check_db(path, seed, meta)

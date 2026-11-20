"""Validate a built seed.db before it is gzipped into app/assets/."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

SCHEMA_VERSION = 4
EXPECTED_TABLES = {"books", "book_tags", "seed_meta", "deep_ranks",
                   "calendar_universe"}
EXPECTED_INDEXES = {
    "idx_bt", "idx_updated", "idx_author", "idx_year_favpctl",
    "idx_year_clickpctl", "idx_genre_favs", "idx_favs", "idx_pr", "idx_shortfav",
    "idx_deep_lookup",
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
            " OR rank_no < 1 OR est_year NOT BETWEEN 2007 AND 2025").fetchone()[0]
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

        required = {"schema_version", "seed_version", "content_end", "built_at",
                    "book_count", "tag_count", "gen_min", "gen_max", "licensed_count",
                    "deep_metrics", "deep_top_n", "deep_rank_rows", "deep_seed_hit"}
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

        non_ln_missing = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=0 AND"
            " (fav_pctl IS NULL OR click_pctl IS NULL OR praise_pctl IS NULL)"
        ).fetchone()[0]
        if non_ln_missing:
            _fail(errors, f"{non_ln_missing} non-licensed rows missing percentiles")

        ln_pctl = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=1 AND"
            " (fav_pctl IS NOT NULL OR click_pctl IS NOT NULL"
            "  OR praise_pctl IS NOT NULL OR pr IS NOT NULL OR pctl_pr IS NOT NULL)"
        ).fetchone()[0]
        if ln_pctl:
            _fail(errors, f"{ln_pctl} licensed rows carry percentiles")

        bad_range = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=0 AND ("
            " fav_pctl <= 0 OR fav_pctl > 1 OR click_pctl <= 0 OR click_pctl > 1"
            " OR praise_pctl <= 0 OR praise_pctl > 1"
            " OR (pctl_pr IS NOT NULL AND (pctl_pr <= 0 OR pctl_pr > 1)))"
        ).fetchone()[0]
        if bad_range:
            _fail(errors, f"{bad_range} rows have percentiles outside (0,1]")

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
        bad_quality = conn.execute(
            "SELECT COUNT(*) FROM books WHERE"
            " (lqs IS NOT NULL AND (lqs <= 0 OR lqs > 1)) OR"
            " (lqs_pctl IS NOT NULL AND (lqs_pctl <= 0 OR lqs_pctl > 1)) OR"
            " (vel_pctl IS NOT NULL AND (vel_pctl <= 0 OR vel_pctl > 1))"
        ).fetchone()[0]
        if bad_quality:
            _fail(errors, f"{bad_quality} rows have invalid lqs/vel percentiles")
        ln_quality = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=1 AND"
            " (lqs IS NOT NULL OR lqs_pctl IS NOT NULL OR vel_pctl IS NOT NULL)"
        ).fetchone()[0]
        if ln_quality:
            _fail(errors, f"{ln_quality} licensed rows carry quality scores")

        ln_range = conn.execute(
            "SELECT COUNT(*) FROM books WHERE is_licensed=0 AND"
            " (est_year < 2007 OR est_year > 2025)").fetchone()[0]
        if ln_range:
            _fail(errors, f"{ln_range} non-licensed rows outside 2007..2025")

        sample = conn.execute(
            "SELECT nid, is_licensed, fav_pctl FROM books WHERE nid=2242").fetchone()
        if sample is None or sample["is_licensed"] != 1 or sample["fav_pctl"] is not None:
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
            f" v0={meta.get('baseline_v0', '?')}"
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

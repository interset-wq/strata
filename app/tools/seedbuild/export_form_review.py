"""Export the seed's short-form books for manual review.

Why this exists: short (`form='short'`) is the only bucket where we know the
platform head (听雨 114,482 clicks / 回到旧时光 215,723), so it is the only
bucket a reviewer can audit without guessing. Medium has no known head and is
therefore not exported.

Usage:
    python app/tools/seedbuild/export_form_review.py [--db path] [--out path]

The CSV is sorted by clicks descending: the top of the file is where
short-form misclassifications concentrate. `flags` repeats the review signals
so the file can be filtered in a spreadsheet:

    C>listen   clicks above 听雨 (114,482)
    F>=1000    favs at or above 1,000
    P>=1000    praises at or above 1,000
    serial     status is 连载中 (an unfinished book is not a short story)
    @ceil      clicks above the 回到旧时光 ceiling (215,723) -- should be empty
"""

from __future__ import annotations

import argparse
import gzip
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
DEFAULT_DB = REPO / "app" / "assets" / "seed.db.gz"
DEFAULT_OUT = REPO / "analysis" / "out" / "seed_form_short_review.csv"

LISTEN_CLICKS = 114_482   # 听雨, best-known short story by clicks
CEIL_CLICKS = 215_723     # 回到旧时光, hard ceiling for a ≤50k-word short

QUERY = """
select b.nid, b.title, b.author, b.genre, b.price_type, b.status, b.contest,
       b.words, b.clicks, b.favs, b.praises,
       b.est_year, b.est_date, b.est_conf, b.fav_pctl, b.click_pctl,
       b.tags,
       r.rank_no as click_rank
from books b
left join deep_ranks r
       on r.nid = b.nid and r.metric = 'clicks'
where b.form = 'short'
"""


def load(db_path: Path) -> pd.DataFrame:
    if db_path.suffix == ".gz":
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(gzip.decompress(db_path.read_bytes()))
            tmp_path = Path(tmp.name)
        try:
            return _read(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
    return _read(db_path)


def _read(path: Path) -> pd.DataFrame:
    # `with sqlite3.connect(...)` only manages the transaction, not the handle:
    # the file stays locked on Windows and the temp copy below cannot be removed.
    conn = sqlite3.connect(path)
    try:
        return pd.read_sql(QUERY, conn)
    finally:
        conn.close()


def build_flags(row: pd.Series) -> str:
    flags = []
    if row["clicks"] > CEIL_CLICKS:
        flags.append("@ceil")
    if row["clicks"] > LISTEN_CLICKS:
        flags.append("C>listen")
    if row["favs"] >= 1_000:
        flags.append("F>=1000")
    if row["praises"] >= 1_000:
        flags.append("P>=1000")
    if row["status"] == "连载中":
        flags.append("serial")
    return "|".join(flags)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--suspect-only", action="store_true",
                    help="keep only rows carrying at least one review flag")
    args = ap.parse_args()

    df = load(args.db)
    if df.empty:
        print("no short-form rows found", file=sys.stderr)
        return 1

    df["ckw"] = (df["clicks"] / df["words"].where(df["words"] > 0)).round(2)
    df["flags"] = df.apply(build_flags, axis=1)
    if args.suspect_only:
        df = df[df["flags"] != ""]
    df = df.sort_values(["clicks", "favs"], ascending=False).reset_index(drop=True)
    df.insert(0, "seq", range(1, len(df) + 1))

    cols = ["seq", "nid", "title", "author", "genre", "price_type", "status",
            "contest", "words", "clicks", "favs", "praises", "ckw", "click_rank",
            "est_year", "est_date", "est_conf", "fav_pctl", "click_pctl",
            "flags", "tags"]
    df = df[cols]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")

    over_listen = int((df["clicks"] > LISTEN_CLICKS).sum())
    over_ceil = int((df["clicks"] > CEIL_CLICKS).sum())
    print(f"rows            {len(df):,}")
    print(f"writing         {args.out}")
    print(f"clicks > {LISTEN_CLICKS:,}  {over_listen:,} ({over_listen / len(df):.1%})")
    print(f"clicks > {CEIL_CLICKS:,}  {over_ceil:,}")
    print(f"favs >= 1,000   {int((df['favs'] >= 1_000).sum()):,}")
    print(f"praises>=1,000  {int((df['praises'] >= 1_000).sum()):,}")
    print(f"serial          {int((df['status'] == '连载中').sum()):,}")
    print(f"words > 50,000  {int((df['words'] > 50_000).sum()):,}  (E.11 exempted)")
    print()
    print(df.head(20)[["seq", "nid", "title", "words", "clicks", "favs",
                       "status", "flags"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

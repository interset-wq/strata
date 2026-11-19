"""Export the seed's short- or medium-form books for manual review.

Why this exists: the reviewer can only audit a bucket against something known.
For `short` the platform head is known (听雨 114,482 clicks / 回到旧时光
215,723), so clicks alone exposes misclassifications. For `medium` there is no
known head yet, so the file instead carries the structural signals that separate
prose from dialogue (clicks/word, tag genre, serialisation) and the reviewer
draws the line from there.

Usage:
    python app/tools/seedbuild/export_form_review.py [--form short|medium]
        [--db path] [--out path] [--suspect-only]

The CSV is sorted by clicks descending: the top of the file is where
misclassifications concentrate. `flags` repeats the review signals so the file
can be filtered in a spreadsheet.

short:
    C>listen   clicks above 听雨 (114,482)
    @ceil      clicks above the 回到旧时光 ceiling (215,723) -- should be empty
    F>=1000    favs at or above 1,000
    P>=1000    praises at or above 1,000
    serial     status is 连载中 (an unfinished book is not a short story)

medium (no known head yet):
    prose-contest  carries a contest mark that is not a dialogue contest => the
               book is a 正文 entry, medium by construction (E.21). Rows with
               this flag are dropped from --suspect-only: no line to draw.
    ckw>=13    clicks/word at or above the short-dialogue threshold (v2-b)
    ckw>=10    softer dialogue signal
    C>1M       clicks above 1,000,000
    F>=5000    favs at or above 5,000
    P>=2000    praises at or above 2,000
    serial     status is 连载中
    near5w     words < 55,000 (sits on the 5万 short/medium boundary)
    tongue     tags contain 同人 but genre is not 同人 (E.17 only covers the
               `tong` set at <= 5万; these are the ones that escaped it)
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
DEFAULT_OUT = {
    "short": REPO / "analysis" / "out" / "seed_form_short_review.csv",
    "medium": REPO / "analysis" / "out" / "seed_form_medium_review.csv",
}

LISTEN_CLICKS = 114_482   # 听雨, best-known short story by clicks
CEIL_CLICKS = 215_723     # 回到旧时光, hard ceiling for a ≤50k-word short
# E.18: 对话体 2017-07 才存在 (dialogue monthly board opens). Books below this
# nid predate the product line, so their clicks are a decade of accumulation and
# are not comparable with a modern short story.
DIALOGUE_START_NID = 83_818
# Flags that question the *form* — the only ones worth a reviewer's time.
# For short there is a known head, so the click/reputation ceilings are the
# signals. For medium there is none: the signals are structural (clicks per
# word, escaped 同人 tags, the 5万 boundary), not quality.
SUSPECT_FLAGS = {
    "short": ("C>listen", "@ceil", "F>=1000", "P>=1000", "serial"),
    "medium": ("ckw>=13", "ckw>=10", "tongue", "near5w"),
}

QUERY = """
select b.nid, b.title, b.author, b.genre, b.price_type, b.status, b.contest,
       b.words, b.clicks, b.favs, b.praises,
       b.est_year, b.est_date, b.est_conf, b.fav_pctl, b.click_pctl,
       b.tags,
       r.rank_no as click_rank
from books b
left join deep_ranks r
       on r.nid = b.nid and r.metric = 'clicks'
where b.form = ?
"""


def load(db_path: Path, form: str) -> pd.DataFrame:
    if db_path.suffix == ".gz":
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp.write(gzip.decompress(db_path.read_bytes()))
            tmp_path = Path(tmp.name)
        try:
            return _read(tmp_path, form)
        finally:
            tmp_path.unlink(missing_ok=True)
    return _read(db_path, form)


def _read(path: Path, form: str) -> pd.DataFrame:
    # `with sqlite3.connect(...)` only manages the transaction, not the handle:
    # the file stays locked on Windows and the temp copy below cannot be removed.
    conn = sqlite3.connect(path)
    try:
        return pd.read_sql(QUERY, conn, params=(form,))
    finally:
        conn.close()


def build_flags(row: pd.Series, form: str) -> str:
    flags = []
    modern = row["nid"] >= DIALOGUE_START_NID
    if not modern:
        flags.append("pre-dialogue")
    if form == "short":
        if modern and row["clicks"] > CEIL_CLICKS:
            flags.append("@ceil")
        if modern and row["clicks"] > LISTEN_CLICKS:
            flags.append("C>listen")
    else:
        # E.21: a contest mark without 对话/点鸭 is a 正文 submission -> medium.
        if str(row["contest"]).strip():
            flags.append("prose-contest")
        if modern and row["ckw"] >= 13:
            flags.append("ckw>=13")
        elif modern and row["ckw"] >= 10:
            flags.append("ckw>=10")
        if row["clicks"] > 1_000_000:
            flags.append("C>1M")
        if row["favs"] >= 5_000:
            flags.append("F>=5000")
        if row["praises"] >= 2_000:
            flags.append("P>=2000")
        if row["words"] < 55_000:
            flags.append("near5w")
        if "同人" in str(row["tags"]) and row["genre"] != "同人":
            flags.append("tongue")
    if row["favs"] >= 1_000:
        flags.append("F>=1000")
    if row["praises"] >= 1_000:
        flags.append("P>=1000")
    if row["status"] == "连载中":
        flags.append("serial")
    return "|".join(flags)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--form", choices=("short", "medium"), default="short")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path,
                    help="defaults to analysis/out/seed_form_<form>_review.csv")
    ap.add_argument("--suspect-only", action="store_true",
                    help="keep only rows carrying at least one review flag")
    args = ap.parse_args()

    out = args.out or DEFAULT_OUT[args.form]
    df = load(args.db, args.form)
    if df.empty:
        print(f"no {args.form}-form rows found", file=sys.stderr)
        return 1

    df["ckw"] = (df["clicks"] / df["words"].where(df["words"] > 0)).round(2)
    df["flags"] = df.apply(lambda r: build_flags(r, args.form), axis=1)
    if args.suspect_only:
        # Only form signals count (`pre-dialogue` is informational, quality
        # flags are context). `prose-contest` is a verdict, not a suspicion
        # (E.21): those books are medium by construction and leave the set.
        parts = df["flags"].str.split("|")
        wanted = SUSPECT_FLAGS[args.form]
        form_signal = parts.apply(lambda t: any(f in wanted for f in t))
        confirmed = parts.apply(lambda t: "prose-contest" in t)
        df = df[form_signal & ~confirmed]
    df = df.sort_values(["clicks", "favs"], ascending=False).reset_index(drop=True)
    df.insert(0, "seq", range(1, len(df) + 1))

    cols = ["seq", "nid", "title", "author", "genre", "price_type", "status",
            "contest", "words", "clicks", "favs", "praises", "ckw", "click_rank",
            "est_year", "est_date", "est_conf", "fav_pctl", "click_pctl",
            "flags", "tags"]
    df = df[cols]

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"form            {args.form}")
    print(f"rows            {len(df):,}")
    print(f"writing         {out}")
    print(f"serial          {int((df['status'] == '连载中').sum()):,}")
    print(f"favs >= 1,000   {int((df['favs'] >= 1_000).sum()):,}")
    print(f"praises>=1,000  {int((df['praises'] >= 1_000).sum()):,}")
    print(f"ckw >= 13       {int((df['ckw'] >= 13).sum()):,}")
    print(f"ckw >= 10       {int((df['ckw'] >= 10).sum()):,}")
    print(f"clicks > 1M     {int((df['clicks'] > 1_000_000).sum()):,}")
    print(f"prose-contest   {int(df['flags'].str.contains('prose-contest').sum()):,}")
    print()
    print(df.head(20)[["seq", "nid", "title", "words", "clicks", "favs",
                       "ckw", "status", "flags"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

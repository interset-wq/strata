"""把上游三片原始快照构建成**我们自己的数据集**。

上游数据不随 Release 分发，所有分析与后续开发只依赖本脚本的产物：

    data/raw/chunks/*.sqlite  →  datasets/v1/{strata-v1.duckdb, parquet/*, manifest.json}

构建过程包含三件事：
1. **归一化**：三片 tags 各自编号（同 id 率 0%），必须按 name 重建全局 id。
2. **清洗**：只修物理不可能的值（like_num < 0），其余异常打 flg_ 标记不动。
3. **去重**：authors / contests 跨片重复，按 name 合并。

用法：
    uv run python -m quarry.build_dataset
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone

import duckdb
import pandas as pd
from rich.console import Console
from rich.table import Table

from . import annual, config, era

console = Console()


# ────────────────────────── 基础 IO ──────────────────────────


def read_table(path, table: str) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', con)
    finally:
        con.close()


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# ────────────────────────── 构建 ──────────────────────────


def load_raw() -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """读三片并纵向拼接；返回 (表名→DataFrame, 源文件清单)。"""
    missing = [c for c in config.CHUNKS if not config.chunk_path(c).exists()]
    if missing:
        raise SystemExit(f"缺少快照：{missing}（查找目录 {config.RAW_DIR}）")

    parts: dict[str, list[pd.DataFrame]] = {
        "novels": [], "tags": [], "novel_tags": [], "authors": [], "contests": []
    }
    sources = []

    for chunk in config.CHUNKS:
        path = config.chunk_path(chunk)
        t0 = time.time()
        for name in parts:
            df = read_table(path, name)
            df["chunk"] = chunk
            parts[name].append(df)
        parts["novels"][-1]["src_file"] = path.name
        sources.append(
            {
                "chunk": chunk,
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "rows": {"novels": len(parts["novels"][-1])},
                "read_seconds": round(time.time() - t0, 2),
            }
        )
        console.print(
            f"  [cyan]{chunk:>4}[/cyan] {len(parts['novels'][-1]):>7,} novels · "
            f"{len(parts['tags'][-1]):>3} tags · {len(parts['novel_tags'][-1]):>7,} 关联"
        )

    return {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}, sources


def normalize_tags(tags: pd.DataFrame, novel_tags: pd.DataFrame):
    """name 是唯一键。全局 id 按字典序分配，保证每次构建结果完全一致。"""
    names = sorted(str(n) for n in tags["name"].dropna().unique())
    mapping = {n: i + 1 for i, n in enumerate(names)}

    tags_global = pd.DataFrame({"tag_id": list(mapping.values()), "name": list(mapping.keys())})
    tags["tag_gid"] = tags["name"].map(mapping)

    merged = novel_tags.merge(
        tags[["chunk", "id", "name", "tag_gid"]].rename(columns={"id": "tag_id"}),
        on=["chunk", "tag_id"],
        how="left",
    )
    orphan = int(merged["tag_gid"].isna().sum())
    merged = merged.drop_duplicates(subset=["novel_id", "tag_gid"])
    return tags_global, merged[["novel_id", "tag_gid"]], orphan


def dedupe_contests(contests: pd.DataFrame, novels: pd.DataFrame):
    """contests 跨片重复（209 行 → 99 个名字），并重映射 novels.contest_id。"""
    names = sorted(contests["name"].dropna().unique())
    id_map = {n: i + 1 for i, n in enumerate(names)}
    clean = pd.DataFrame({"contest_id": list(id_map.values()), "name": names})

    lookup = contests.merge(
        novels[["id", "chunk", "contest_id"]].rename(columns={"id": "novel_id", "contest_id": "cid"}),
        left_on=["chunk", "id"],
        right_on=["chunk", "cid"],
        how="inner",
    )
    novels = novels.merge(
        lookup[["novel_id", "name"]].rename(columns={"name": "contest_name"}),
        left_on="id",
        right_on="novel_id",
        how="left",
    )
    novels["contest_id"] = novels["contest_name"].map(id_map)
    novels = novels.drop(columns=["novel_id", "contest_name"])
    return clean, novels


def dedupe_authors(authors: pd.DataFrame) -> pd.DataFrame:
    """一个作者只留一行，取人气最高的那本作为代表作。"""
    df = authors.sort_values("top_novel_clicks", ascending=False, kind="stable")
    df = df.drop_duplicates(subset=["name"], keep="first")
    return df[["name", "top_novel_id", "top_novel_title", "top_novel_clicks"]].reset_index(drop=True)


def clean_novels(novels: pd.DataFrame) -> pd.DataFrame:
    """修物理不可能的值，其余打标记。绝不动 NULL 语义。"""
    df = novels.copy()
    df["last_update"] = pd.to_datetime(df["last_update"], utc=True, errors="coerce")

    like_negative = df["like_num"] < 0
    df["flg_like_fixed"] = like_negative
    df["like_num"] = df["like_num"].where(~like_negative)  # 负数 → NULL

    df["flg_placeholder_title"] = df["title"].str.fullmatch(r"[0-9]+").fillna(False).astype(bool)
    df["flg_word_zero"] = (df["word_num"] == 0)
    df["flg_default_cover"] = df["cover"].str.contains("defaultnew", case=False, na=False)
    df["flg_praise_gt_click"] = df["praise_num"] > df["click_num"]
    df["flg_comment_missing"] = df["comment_num"].isna()

    # 引进日轻：版权方账号上传，banner 由版权方提供，不算 SFACG 的原创认可。
    # 只标记不删除——它们仍是站点历史的一部分，但所有认可类统计必须排除。
    # 见 config.IMPORT_PUBLISHERS 里的口径说明。
    df["flg_import"] = df["author"].isin(config.IMPORT_PUBLISHERS)

    order = [
        "id", "title", "author", "genre", "status", "ptype", "has_banner",
        "word_num", "click_num", "praise_num", "like_num",
        "comment_num", "review_num", "contest_id", "cover", "last_update", "chunk",
        "flg_placeholder_title", "flg_word_zero", "flg_default_cover",
        "flg_like_fixed", "flg_praise_gt_click", "flg_comment_missing", "flg_import",
    ]
    return df[order]


def build() -> dict:
    console.print(f"raw  → {config.RAW_DIR}")
    raw, sources = load_raw()

    tags, novel_tags, orphan_tags = normalize_tags(raw["tags"], raw["novel_tags"])
    contests, novels = dedupe_contests(raw["contests"], raw["novels"])
    authors = dedupe_authors(raw["authors"])
    novels = clean_novels(novels)

    # ── 定年：nid → 日期。锚点是入库资产（data/anchors），随数据集一起发布 ──
    anchors = era.load_anchors()
    console.print(f"  anchors {len(anchors)} · nid {anchors.nid.min():,} ~ {anchors.nid.max():,}")
    novels_era = annual.attach(novels, anchors)
    era_stats = annual.build_stats(novels_era, novels)
    console.print(
        f"  era    {novels_era.est_year.min()}–{novels_era.est_year.max()}"
        f" · {len(era_stats)} 年 · 外推 {int((novels_era['mode'] != 'interp').sum()):,} 本"
    )

    tables = {
        "novels": novels,
        "novels_era": novels_era,
        "era_stats": era_stats,
        "tags": tags,
        "novel_tags": novel_tags,
        "authors": authors,
        "contests": contests,
    }

    # ── 输出目录重建 ──
    if config.DATASET_DIR.exists():
        shutil.rmtree(config.DATASET_DIR)
    config.PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    artifacts = {}
    for name, df in tables.items():
        p = config.PARQUET_DIR / f"{name}.parquet"
        df.to_parquet(p, index=False, compression="zstd")
        artifacts[name] = {"rows": len(df), "file": str(p.relative_to(config.DATASET_DIR)),
                           "bytes": p.stat().st_size, "sha256": sha256(p)}

    # ── DuckDB 单文件 ──
    con = duckdb.connect(str(config.DUCKDB_PATH))
    try:
        for name, df in tables.items():
            con.register("_t", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _t")
            con.unregister("_t")
        con.execute("CHECKPOINT")
    finally:
        con.close()

    # 内容指纹：只由 parquet 的 sha256 决定。duckdb 单文件每次构建字节不同
    # （DuckDB 内部元数据非确定），不能作为校验基准。
    content_hash = hashlib.sha256(
        "".join(f"{k}:{v['sha256']}" for k, v in sorted(artifacts.items())).encode()
    ).hexdigest()

    manifest = {
        "dataset": "quarry-strata",
        "version": config.DATASET_VERSION,
        "schema_version": config.SCHEMA_VERSION,
        "content_hash": content_hash,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "quarry.build_dataset",
        "note": "由上游 Novel Hub 快照构建。上游原始文件不随本数据集分发，仅记录校验和以便溯源。",
        "source": sources,
        "anchors": {
            "file": str(config.ANCHORS_PATH.relative_to(config.ROOT)),
            "count": len(anchors),
            "sha256": sha256(config.ANCHORS_PATH),
            "method": "log-linear interpolation over nid; 91 points, 0 inversions",
        },
        "tables": artifacts,
        "duckdb": {
            "file": config.DUCKDB_PATH.name,
            "bytes": config.DUCKDB_PATH.stat().st_size,
            "sha256": sha256(config.DUCKDB_PATH),
            "deterministic": False,
        },
        "baseline": config.BASELINE,
    }
    config.MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "manifest": manifest,
        "rows": {k: len(v) for k, v in tables.items()},
        "orphan_tags": orphan_tags,
        "authors_raw": len(raw["authors"]),
        "contests_raw": len(raw["contests"]),
    }


def main() -> None:
    console.rule("[bold]quarry · build_dataset[/bold]")
    t0 = time.time()
    result = build()

    rows = result["rows"]
    if rows["novels"] != config.BASELINE["novels_total"]:
        console.print(
            f"[red]✗ novels {rows['novels']:,} ≠ 基线 {config.BASELINE['novels_total']:,}[/red]"
        )
        sys.exit(1)

    t = Table(title=f"数据集 {config.DATASET_VERSION}  ({config.DATASET_DIR})")
    t.add_column("表")
    t.add_column("行数", justify="right")
    t.add_column("parquet", justify="right")
    for name, info in result["manifest"]["tables"].items():
        t.add_row(name, f"{info['rows']:,}", f"{info['bytes'] / 1024 / 1024:.1f} MB")
    console.print(t)

    console.print(
        f"  authors 去重 {result['authors_raw']:,} → {rows['authors']:,}"
        f" · contests 去重 {result['contests_raw']:,} → {rows['contests']:,}"
        f" · 孤立标签 {result['orphan_tags']}"
    )
    size = config.DUCKDB_PATH.stat().st_size / 1024 / 1024
    total = sum(v["bytes"] for v in result["manifest"]["tables"].values())
    console.print(
        f"[green]✓ {config.DUCKDB_PATH.name} {size:.1f} MB ｜ "
        f"parquet 合计 {total / 1024 / 1024:.1f} MB ｜ "
        f"{time.time() - t0:.1f}s[/green]"
    )
    console.print(f"  manifest → {config.MANIFEST_PATH}")


if __name__ == "__main__":
    main()

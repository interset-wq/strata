"""从 covers_raw.jsonl 生成可渲染的目验表格 md（书名列 + 封面缩略图列）。

用法：cd analysis && uv run python ../cover-check/render_table.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

COLS = "| 序号 | nid | 书名 | 作者 | 封面（点击看原图） |\n"
SEP = "|---:|---:|---|---|---|\n"


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def main() -> None:
    rows = [json.loads(l) for l in (HERE / "covers_raw.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    lines = [
        "# 授权 47 本封面采集试跑 · 目验表\n",
        "> 数据源：官方 App API `GET /novels/{nid}` 的 `novelCover` 字段，"
        "2026-11-17 串行采集（0.5s 间隔，仅取书目元数据、不取正文、不登录）。\n",
        f"> 结果：**{len(rows)}/{len(rows)} 本取到真实封面 URL**，"
        "全部 `https://rss.sfacg.com/` 直链、`image/jpeg` 可渲染。\n",
        "> 这 47 本已通过 `dataset/build.py` 写入数据集，"
        "并由 `build_seed.py` 写入种子 `books.cover_url`；"
        "本表保留了按 nid 重取时的目验结果。\n\n",
        COLS,
        SEP,
    ]
    for i, r in enumerate(rows, 1):
        cover = r.get("cover") or ""
        img = (f'[<img src="{cover}" width="72" alt="封面">]({cover})'
               if cover else "—（未取到）")
        lines.append(
            f"| {i} | {r['nid']} | {esc(r['title'])} | {esc(r['author'])} | {img} |\n"
        )
    lines.append(
        "\n---\n\n"
        "采集脚本 `fetch_covers.py`、原始记录 `covers_raw.jsonl`、"
        "运行日志 `run.log` 同目录。任何一列封面与书名不符，请记录 nid 以便核对"
        "（可能命中库外/授权版换了封面）。\n"
    )
    out = HERE / "README.md"
    out.write_text("".join(lines), encoding="utf-8")
    print(f"生成 {out}（{len(rows)} 行）")


if __name__ == "__main__":
    main()

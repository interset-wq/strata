"""用授权 47 本 nid 试跑：从官方 App API 取 novelCover，产出可渲染对照表。

合规：只取书目元数据（novelCover），不取正文、不登录、不用用户 cookie；
串行 + 0.5s 间隔；失败单独记录，不中断整轮。目录与产物纳入 git。

用法：
    cd analysis && uv run python ../cover-check/fetch_covers.py
"""
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis" / "fetchers"))
import fetch_app_api_novels as F  # noqa: E402

HERE = Path(__file__).resolve().parent
LIST = HERE / "licensed47.json"
RAW = HERE / "covers_raw.jsonl"


def main() -> None:
    books = json.loads(LIST.read_text(encoding="utf-8"))
    done: dict[int, str] = {}
    if RAW.exists():
        for line in RAW.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("cover"):
                    done[r["nid"]] = r["cover"]

    session = requests.Session()
    session.headers.update(F.make_headers())
    out = RAW.open("a", encoding="utf-8")
    try:
        for i, b in enumerate(books, 1):
            nid = b["nid"]
            if nid in done:
                print(f"[{i:2}/47] nid={nid} 已有，跳过", flush=True)
                continue
            rec = {"nid": nid, "title": b["title"], "author": b["author"],
                   "cover": "", "http": 0, "error": ""}
            try:
                r = session.get(f"{F.API.rstrip('/')}/{nid}", timeout=25)
                rec["http"] = r.status_code
                payload = r.json()
                data = payload.get("data") or {}
                rec["cover"] = data.get("novelCover") or ""
                if not rec["cover"]:
                    rec["error"] = f"status={payload.get('status')} 无 novelCover"
            except Exception as exc:  # noqa: BLE001
                rec["error"] = str(exc)[:200]
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i:2}/47] nid={nid} {b['title'][:20]} "
                  f"http={rec['http']} cover={'OK' if rec['cover'] else 'MISS'} "
                  f"{rec['error']}", flush=True)
            time.sleep(0.5)
    finally:
        out.close()

    total = sum(1 for _ in RAW.read_text(encoding="utf-8").splitlines() if _.strip())
    print(f"\n完成，{total} 条 → {RAW}", flush=True)


if __name__ == "__main__":
    main()

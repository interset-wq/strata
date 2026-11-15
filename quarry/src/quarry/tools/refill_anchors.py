"""补锚点：在指定 nid 区间按等距采样，从 SFACG API 抓 ``addTime``。

为什么需要单独一个工具
----------------------
初始锚点按「全库 nid 的 2.5% 分位」采样，头尾各 2.5% 天然落在锚点之外。
头部靠 7 个手工早期锚点补齐；尾部（数据快照之后新增的书）会随快照更新
不断变长，所以需要一个可重跑的工具。

404 是正常情况——nid 有空洞（书被作者或站点下架），跳过即可。

认证
----
API 需要一行 App 内置的 Basic 认证头。**该值不入库**（仓库是 public 的，第三方凭据
不应出现在源码里），从环境变量读取：

    SFACG_AUTH='Basic ...' uv run python -m quarry.tools.refill_anchors --lo 761712 --hi 777879 --n 12

用法：
    uv run python -m quarry.tools.refill_anchors --lo 761712 --hi 777879 --n 12
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from .. import config

API = "https://api.sfacg.com/novels/{}"


def _auth() -> str:
    """从环境变量取认证头。不写死在源码里：仓库 public，凭据不该跟着走。"""
    v = os.environ.get("SFACG_AUTH", "").strip()
    if not v:
        sys.exit(
            "缺少 SFACG_AUTH 环境变量。\n"
            "  该值取自 App 内置的 Basic 头，出于凭据管理不写进仓库。\n"
            "  用法：SFACG_AUTH='Basic ...' uv run python -m quarry.tools.refill_anchors ..."
        )
    return v if v.lower().startswith("basic ") else f"Basic {v}"


def fetch(nid: int, auth: str) -> dict | None:
    req = urllib.request.Request(
        API.format(nid),
        headers={"Authorization": auth, "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())["data"]
        return {
            "nid": nid,
            "addTime": d["addTime"],
            "name": d.get("novelName", ""),
            "hasBannerApi": bool(d.get("bgBanner")),
            "source": "refill",
        }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, required=True)
    ap.add_argument("--hi", type=int, required=True)
    ap.add_argument("--n", type=int, default=12, help="采样点数")
    ap.add_argument("--sleep", type=float, default=0.4)
    args = ap.parse_args()

    path = config.ANCHORS_PATH
    auth = _auth()
    rows = {
        r["nid"]: r
        for r in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    print(f"现有锚点 {len(rows)}，nid {min(rows)} ~ {max(rows)}")

    step = max(1, (args.hi - args.lo) // (args.n + 1))
    targets = [args.lo + step * (i + 1) for i in range(args.n)]
    added = miss = 0
    for nid in targets:
        if nid in rows:
            continue
        rec = fetch(nid, auth)
        if rec is None:
            miss += 1
            print(f"  {nid} 404/失败，跳过")
        else:
            rows[rec["nid"]] = rec
            added += 1
            print(f"  {nid} {rec['addTime'][:19]} {rec['name'][:24]}")
        time.sleep(args.sleep)

    merged = sorted(rows.values(), key=lambda r: r["nid"])
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in merged) + "\n",
        encoding="utf-8",
    )
    print(f"\n新增 {added}，跳过 {miss}，合计 {len(merged)} → {path}")


if __name__ == "__main__":
    main()

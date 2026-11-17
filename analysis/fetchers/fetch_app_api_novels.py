"""用官方 App API 枚举书目，产出「nid + addTime」精确记录。

## 目的

本项目的定年体系（`lib/eras.py`）用 `log(nid) ↔ day` 分段线性反推，104 个锚点、
LOO P99 = 50 天，且**外推段（nid > 774,850）误差达 131–153 天**。
官方 App API 的 `GET /novels` 每条都带**精确到秒的 `addTime`**——用它枚举全库，
可以把定年从「反推」升级为「直接读官方建档时刻」。

同时这个接口还给出 `markCount`（收藏）、`viewTimes`（点击，精确整数）、`charCount`（字数）、
`point`（0–10 评分）、`signStatus`、`typeId`、`categoryId` —— 即书目元数据的**权威来源**。

## 已知实测结论（2026-11-17）

| 事实 | 数值 | 依据 |
| --- | --- | --- |
| `size` 上限 | 50 | 更大被截断 |
| 魔幻类（tid=21）可翻页深度 | page 0 ~ 1000+ 有内容，page 2000 为空 | 深翻页实测 |
| 采样质量 | 500 条零重复、`addTime` 零缺失 | `probe_sfacg_app_api.py` |
| 排序 | **大致按 `addTime` 降序，但页内不严格单调** | 同一次抽样首末差 8 个月 |
| 覆盖 | 比 PC 端目录（255,408 槽位）**更大** | 粗估九类约 54 万条，待全量确认 |

**因此翻页时不能假设「页内按 nid 或 addTime 有序」**，必须逐条按 nid 去重。

## 用法

    # 单类全量（断点续采：重复执行同一命令即可接着上次继续）
    uv run python analysis/fetchers/fetch_app_api_novels.py --tid 21

    # 全库九类
    uv run python analysis/fetchers/fetch_app_api_novels.py --all

    # 指定输出与节流
    uv run python analysis/fetchers/fetch_app_api_novels.py --all --path out/app_api_novels.jsonl --delay 0.6

输出 jsonl，每行：
```json
{"nid": 730611, "addTime": "2024-12-27T19:03:11", "markCount": 91050, "viewTimes": 33353509,
 "charCount": 2978118, "point": 5.0, "isFinish": false, "signStatus": "VIP",
 "typeId": 21, "categoryId": 0, "authorId": 43294, "authorName": "…",
 "novelName": "…", "lastUpdateTime": "2026-11-17T00:30:03", "tid": 21}
```

## 约束

- 只取**书目元数据**，不取正文（`/Chaps/{id}?expand=content` 实测无权限）。
- 不登录、不使用用户凭据；用 App 内置固定常量 + 每次请求自签。
- 串行 + 间隔 ≥0.5 s。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402

API = "https://api.sfacg.com/novels"
SALT = "FN_Q29XHVmfV3mYX"
BASIC = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="
UA_TPL = "boluobao/5.0.36(android;32)/H5/{device_token}/H5"
PAGE_SIZE = 50

# tid → 分类名（实测取值表，见 references/sfacg-app-api.md §2.1）
TIDS: dict[int, str] = {
    9: "爱情", 21: "魔幻", 22: "玄幻", 23: "古风", 24: "科幻",
    25: "校园", 26: "都市", 27: "游戏", 29: "悬疑",
}

KEEP = (
    "novelId", "novelName", "authorId", "authorName", "addTime", "lastUpdateTime",
    "markCount", "viewTimes", "charCount", "point", "isFinish", "signStatus",
    "typeId", "categoryId", "isSensitive", "allowDown", "novelCover", "bgBanner",
)


def make_headers() -> dict[str, str]:
    nonce = str(uuid.uuid4()).upper()
    timestamp = int(time.time() * 1000)
    device_token = str(uuid.uuid4()).upper()
    sign = hashlib.md5(
        f"{nonce}{timestamp}{device_token}{SALT}".encode("ascii")
    ).hexdigest().upper()
    return {
        "accept": "application/vnd.sfacg.api+json;version=1",
        "authorization": BASIC,
        "user-agent": UA_TPL.format(device_token=device_token),
        "sfsecurity": (
            f"nonce={nonce}&timestamp={timestamp}"
            f"&devicetoken={device_token}&sign={sign}"
        ),
        "accept-encoding": "gzip",
    }


def fetch_page(session: requests.Session, tid: int | None, page: int) -> list[dict]:
    params: dict[str, object] = {"size": PAGE_SIZE, "page": page}
    if tid is not None:
        params["tid"] = tid
    try:
        resp = session.get(API, params=params, timeout=25)
    except Exception as exc:  # noqa: BLE001 - 单页失败不中断整轮
        print(f"  page={page} 失败：{exc}")
        return []
    if resp.status_code != 200:
        print(f"  page={page} HTTP {resp.status_code}")
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    status = payload.get("status", {}) if isinstance(payload, dict) else {}
    if status.get("httpCode") not in (200, None):
        print(f"  page={page} httpCode={status.get('httpCode')} msg={status.get('msg')}")
        return []
    data = payload.get("data")
    return data if isinstance(data, list) else []


def crawl_tid(session: requests.Session, tid: int | None, label: str,
              out_path: Path, delay: float, max_pages: int) -> int:
    """翻页直到返回空页或达 max_pages，增量追加到 out_path。"""
    seen: set[int] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    seen.add(int(json.loads(line)["nid"]))
                except Exception:
                    continue
        print(f"[{label}] 已有 {len(seen)} 条，断点续采")

    page = 0
    new_count = 0
    with out_path.open("a", encoding="utf-8") as fh:
        while page < max_pages:
            items = fetch_page(session, tid, page)
            if not items:
                print(f"[{label}] page={page} 为空，翻页结束")
                break
            fresh = 0
            for it in items:
                nid = it.get("novelId")
                if nid is None or nid in seen:
                    continue
                seen.add(nid)
                rec = {k: it.get(k) for k in KEEP if k in it}
                rec["nid"] = nid
                rec["tid"] = tid if tid is not None else it.get("typeId")
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fresh += 1
            new_count += fresh
            fh.flush()
            if page % 50 == 0 or page == max_pages - 1:
                print(f"[{label}] page={page} +{fresh}（累计 {len(seen)}）")
            page += 1
            time.sleep(delay)
    return new_count


def main() -> None:
    ap = argparse.ArgumentParser(description="用官方 App API 枚举书目元数据")
    ap.add_argument("--tid", type=int, default=None, help="单个分类 id（如 21）")
    ap.add_argument("--all", action="store_true", help="九类全采")
    ap.add_argument("--path", default=str(paths.OUT_DIR / "app_api_novels.jsonl"))
    ap.add_argument("--delay", type=float, default=0.6, help="请求间隔秒（≥0.5）")
    ap.add_argument("--max-pages", type=int, default=2000, help="单类最大翻页数")
    args = ap.parse_args()

    out = Path(args.path)
    out.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(make_headers())

    if args.all:
        total = 0
        for tid, name in TIDS.items():
            print(f"\n===== {name}（tid={tid}）=====")
            total += crawl_tid(session, tid, f"{name}({tid})", out, args.delay, args.max_pages)
        print(f"\n全部完成，新增 {total} 条 → {out}")
    elif args.tid is not None:
        name = TIDS.get(args.tid, f"tid={args.tid}")
        n = crawl_tid(session, args.tid, name, out, args.delay, args.max_pages)
        print(f"\n完成，新增 {n} 条 → {out}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

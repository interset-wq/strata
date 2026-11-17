"""官方 SFACG 移动端 App API（api.sfacg.com）探针。

## 为什么需要这个探针

本项目原先只有 **PC 端 HTML** 通路（`m.sfacg.com/b/{nid}/`，15 KB/页）与
`op=novelbytype` 枚举，两个硬约束：

1. **没有上架时间（addTime）**——定年只能靠 `log(nid) ↔ day` 分段线性反推
   （104 个锚点，LOO P99 = 50 天）。
2. **点击数带「万」单位、量化步长 1,000（±500）**——PC 版人气显示为
   `11899.5万`，导致「点击变化」这种派生指标不可信（05 §3.4 曾据此取消
   点击变化观测）。

App API 两个问题都没有：`GET /novels/{id}` 单请求 700 B 直接给出
**精确到秒的 `addTime`** 与**精确整数的 `viewTimes`**。

## 认证机制（实测）

App 用**固定的内置凭据 + 每次请求自签**，不需要用户账号即可访问公开数据：

| 项 | 值 / 规则 |
| --- | --- |
| 认证头 `authorization` | `Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE=`（= `androiduser:1a1$51-yt697;*AJ7Bpxq4`） |
| `accept` | `application/vnd.sfacg.api+json;version=1` |
| `user-agent` | `boluobao/5.0.36(android;32)/H5/{device_token}/H5` |
| `sfsecurity` | `nonce={uuid4大写}&timestamp={unix毫秒}&devicetoken={uuid4大写}&sign={md5大写}` |
| `sign` | `md5(nonce + timestamp + devicetoken + SALT)`，`SALT = "FN_Q29XHVmfV3mYX"` |
| `nonce` | **客户端自造的 UUID**，不是服务器领取的 |
| `device_token` | **客户端自造的 UUID** |

`nonce` 与 `device_token` 每次请求重新生成即可；服务器只校验签名。
签名错误返回 `status.httpCode = 417`（HTTP 仍是 200）。

凭据来源：公开第三方实现（GitHub `fengyinxia/sfacg`、`duongden/sfacg_downloader`、
`Illustar0/SF_AutoCheckIn` 等）。它们是**App 客户端内置的固定常量**，
所有 App 用户共用同一套，不是任何用户的私密凭据。

## 合规边界（本探针严格遵守）

- **只取书目元数据**（nid / 标题 / 作者 / 收藏 / 点击 / 字数 / 状态 / 时间戳）。
- **不取正文**：`GET /Chaps/{id}?expand=content` 实测 401（errorCode 507，
  无接口权限），无需也无法绕过。
- **不登录、不使用任何用户 cookie**：需要身份的端点（`/user`、`/sessions`）
  一律只探测不调用。
- 串行 + 间隔 ≥0.5 s，不做高频抓取。

## 用法

    uv run python analysis/fetchers/probe_sfacg_app_api.py --endpoints   # 端点可达性总表
    uv run python analysis/fetchers/probe_sfacg_app_api.py --detail 730611
    uv run python analysis/fetchers/probe_sfacg_app_api.py --fields        # 字段字典
    uv run python analysis/fetchers/probe_sfacg_app_api.py --pushes       # 77 个推送位
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

API = "https://api.sfacg.com"

# App 客户端内置的固定常量（公开第三方实现一致，见模块 docstring）
SALT = "FN_Q29XHVmfV3mYX"
BASIC = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="
UA_TPL = "boluobao/5.0.36(android;32)/H5/{device_token}/H5"

# 公开数据端点总表：(说明, 路径, 是否需登录)
ENDPOINTS: list[tuple[str, str, bool]] = [
    ("小说详情（含 addTime/viewTimes）", "/novels/730611", False),
    ("分类枚举 魔幻 tid=21", "/novels?tid=21&size=50&page=0", False),
    ("全库列表", "/novels?size=50&page=0", False),
    ("首页推荐 filter=recom", "/novels?filter=recom&size=50", False),
    ("搜索小说", "/search/novels/result?q=%E8%8B%B1%E9%9B%84&size=20&page=0", False),
    ("搜索任意作品", "/search/any/result?q=%E8%8B%B1%E9%9B%84&size=20&page=0", False),
    ("特别推送列表", "/novels/specialpushs?pushNames=bigBrainPush&size=30", False),
    ("全部推送位（77 个）", "/specialpush", False),
    ("小说目录", "/novels/730611/dirs", False),
    ("小说分卷", "/novels/730611/volumes", False),
    ("小说章节列表", "/novels/730611/chaps", False),
    ("小说简评", "/novels/730611/cmts?page=0&size=10", False),
    ("小说书评", "/novels/730611/reviews?page=0&size=10", False),
    ("小说粉丝榜", "/novels/730611/fans", False),
    ("月票排名 周/月/总", "/novels/730611/ticket/rank?numMax=20&dateRange=1", False),
    ("打赏排名 月度", "/novels/730611/bonus/rank?numMax=20&dateRange=1", False),
    ("书内活动推送", "/novels/730611/actpushes?filter=android&pageType=0", False),
    ("章节正文（无权限，应 401）", "/Chaps/8436696?expand=content", True),
    ("当前用户（需登录，应 401）", "/user", True),
]


def make_headers() -> dict[str, str]:
    """构造一次请求头：nonce / device_token 自造，sign 为 md5(nonce+ts+dt+SALT)。"""
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


def get(path: str, **kw):
    """GET 一个 App API 路径，返回 (http_status, json_or_text)。"""
    try:
        resp = requests.get(f"{API}{path}", headers=make_headers(), timeout=18, **kw)
    except Exception as exc:  # noqa: BLE001 - 探针不因单点失败中断
        return None, {"exception": str(exc)}
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"text": resp.text[:200]}


def describe(payload) -> str:
    """把响应压成一行摘要。"""
    if not isinstance(payload, dict):
        return type(payload).__name__
    status = payload.get("status", {}) if isinstance(payload.get("status"), dict) else {}
    data = payload.get("data")
    head = f"httpCode={status.get('httpCode')}"
    if status.get("msg"):
        head += f" msg={status['msg']}"
    if isinstance(data, list):
        head += f" | data=list n={len(data)}"
        if data and isinstance(data[0], dict):
            head += f" | 首条字段={sorted(data[0].keys())}"
    elif isinstance(data, dict):
        head += f" | data=dict 键={list(data.keys())[:10]}"
    else:
        head += f" | data={type(data).__name__}"
    return head


def probe_endpoints() -> None:
    print("=== 官方 App API 端点可达性 ===\n")
    print(f"{'端点':<34} {'HTTP':>5}  {'需登录':<6} 摘要")
    print("-" * 118)
    for name, path, needs_login in ENDPOINTS:
        code, payload = get(path)
        tag = "是" if needs_login else ""
        print(f"{name:<34} {str(code):>5}  {tag:<6} {describe(payload)}")
        time.sleep(0.5)


def probe_detail(nid: int) -> None:
    code, payload = get(f"/novels/{nid}")
    print(f"=== GET /novels/{nid} → HTTP {code} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def probe_fields() -> None:
    """字段字典：以分类列表首条为准，核对与 PC 端字段的对应关系。"""
    code, payload = get("/novels?tid=21&size=50&page=0")
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        print("取不到样本")
        return
    sample = items[0]
    print(f"=== 分类列表首条字段（{len(sample)} 个）===\n")
    for k in sorted(sample):
        v = sample[k]
        print(f"  {k:<18} {type(v).__name__:<6} {json.dumps(v, ensure_ascii=False)[:70]}")
    print("\n=== 与 PC 端字段对应（analysis 侧列名 → App 字段）===")
    mapping = {
        "id": "novelId", "title": "novelName", "author": "authorName",
        "favs": "markCount", "clicks": "viewTimes", "words": "charCount",
        "pr": "point", "featured": "bgBanner", "cover_url": "novelCover",
        "status": "isFinish", "updated_at": "lastUpdateTime", "typeId": "typeId",
    }
    for local, app in mapping.items():
        print(f"  {local:<14} → {app:<16} {json.dumps(sample.get(app), ensure_ascii=False)[:56]}")
    print(f"  {'（定年）':<14} → {'addTime':<16} {sample.get('addTime')}")


def probe_pushes() -> None:
    code, payload = get("/specialpush")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        print("取不到推送位")
        return
    print(f"=== App 全部推送位（{len(data)} 个）===\n")
    for k in sorted(data):
        v = data[k]
        n = len(v) if isinstance(v, (list, dict)) else "-"
        print(f"  {k:<28} {type(v).__name__:<6} n={n}")


def main() -> None:
    ap = argparse.ArgumentParser(description="SFACG 官方 App API 探针")
    ap.add_argument("--endpoints", action="store_true", help="端点可达性总表")
    ap.add_argument("--detail", type=int, nargs="?", const=730611, help="单本详情全字段")
    ap.add_argument("--fields", action="store_true", help="字段字典与 PC 端对应")
    ap.add_argument("--pushes", action="store_true", help="全部推送位")
    args = ap.parse_args()

    if args.endpoints:
        probe_endpoints()
    if args.detail:
        probe_detail(args.detail)
    if args.fields:
        probe_fields()
    if args.pushes:
        probe_pushes()
    if not any([args.endpoints, args.detail, args.fields, args.pushes]):
        ap.print_help()


if __name__ == "__main__":
    main()

"""SFACG API 极简查看器：改 URL，运行，看返回。

运行：
    uv run --project analysis python tools/api_inspect.py

脚本从上往下直接执行，没有 main、没有命令行参数。
默认跑「小说详情」；想看别的，把下面注释里的例子取消注释（一次留一个），
或直接改 res = requests.get(...) 里的 URL。
认证封装在 auth()，输出封装在 dump()，你要自己写代码就照着改。

合规：只取书目元数据；不取正文；不登录、不用 cookie；串行、低频。
"""
import hashlib
import json
import time
import uuid

import requests

# App 客户端内置固定常量（非用户凭据，见 analysis/references/sfacg-app-api.md）
SALT = "FN_Q29XHVmfV3mYX"
BASIC = "Basic YW5kcm9pZHVzZXI6MWEjJDUxLXl0Njk7KkFjdkBxeHE="


def auth():
    """每次请求现造 nonce/device_token，sign=md5(nonce+ts+dt+SALT)。"""
    nonce = str(uuid.uuid4()).upper()
    ts = int(time.time() * 1000)
    dt = str(uuid.uuid4()).upper()
    sign = hashlib.md5(f"{nonce}{ts}{dt}{SALT}".encode("ascii")).hexdigest().upper()
    return {
        "accept": "application/vnd.sfacg.api+json;version=1",
        "authorization": BASIC,
        "user-agent": f"boluobao/5.0.36(android;32)/H5/{dt}/H5",
        "sfsecurity": f"nonce={nonce}&timestamp={ts}&devicetoken={dt}&sign={sign}",
        "accept-encoding": "gzip",
    }


def dump(res):
    """打印 HTTP 状态、业务码、data。大响应想只看结构可改 data -> data[0]。"""
    print("HTTP", res.status_code)
    try:
        j = res.json()
    except Exception:
        print(res.text[:1000])
        return
    print("status:", j.get("status"))
    print(json.dumps(j.get("data"), ensure_ascii=False, indent=2))


# ==================== 现成例子：一次留一个 ====================

# 1. 小说详情（19 字段，含 addTime / viewTimes / novelCover）
res = requests.get("https://api.sfacg.com/novels/730611", headers=auth(), timeout=20)
dump(res)

# 2. 逐章列表（745 章、227KB；只看首条结构可改 dump 里 data -> data[0]）
# res = requests.get("https://api.sfacg.com/novels/730611/chaps", headers=auth(), timeout=20)
# dump(res)

# 3. 目录 / 分卷
# res = requests.get("https://api.sfacg.com/novels/730611/dirs", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels/730611/volumes", headers=auth(), timeout=20)
# dump(res)

# 4. 列表 / 分类 / 推荐
# res = requests.get("https://api.sfacg.com/novels?size=5&page=0", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels?tid=21&size=5&page=0", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels?filter=recom&size=5", headers=auth(), timeout=20)
# dump(res)

# 5. 单本扩字段 tags / sysTags / intro
# res = requests.get("https://api.sfacg.com/novels/730611?expand=tags,sysTags,intro", headers=auth(), timeout=20)
# dump(res)

# 6. 搜索
# res = requests.get("https://api.sfacg.com/search/novels/result?q=英雄&size=5&page=0", headers=auth(), timeout=20)
# dump(res)

# 7. 推送位（77 个，其中 chatNovel* 是对话小说榜位）
# res = requests.get("https://api.sfacg.com/specialpush", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels/specialpushs?pushNames=bigBrainPush&size=10", headers=auth(), timeout=20)
# dump(res)

# 8. 简评 / 粉丝 / 月票榜 / 打赏榜
# res = requests.get("https://api.sfacg.com/novels/730611/cmts?page=0&size=5", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels/730611/fans", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels/730611/ticket/rank?numMax=5&dateRange=1", headers=auth(), timeout=20)
# dump(res)
# res = requests.get("https://api.sfacg.com/novels/730611/bonus/rank?numMax=5&dateRange=1", headers=auth(), timeout=20)
# dump(res)

# 9. PC 端页面（不用 App 认证）：HTML 文本，非 JSON
# res = requests.get("https://m.sfacg.com/b/730611/", timeout=20)
# print("HTTP", res.status_code, "长度", len(res.content))
# print(res.text[:1000])

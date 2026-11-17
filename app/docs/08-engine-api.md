# 08 · 引擎 HTTP 契约（Go ↔ Dart）

> v1.0 · 2026-11-17
> 本文档是 Go 引擎与 Flutter（dart:ffi 客户端）之间的**绑定契约**。双方都以本文为准；
> 改动任何端点必须先改本文。现状实现见 `app/engine/internal/api/api.go`。

## 总则

- 服务只绑定 `127.0.0.1`，端口由内核动态分配（`:0`）。启动方（CLI 或 FFI）负责把
  实际地址交给 UI。
- 所有响应为 UTF-8 JSON；HTTP 状态码语义常规。
- 错误响应统一为：

  ```json
  { "error": { "code": "invalid_argument", "message": "..." } }
  ``

  | code | HTTP | 含义 |
  | --- | --- | --- |
  | `invalid_argument` | 400 | 参数缺失/非法 |
  | `not_found` | 404 | nid 不在种子里 |
  | `internal` | 500 | 存储层/内部错误 |

- **分页**：统一用 `limit` 查询参数，1..200，缺省 50；越界返回 `invalid_argument`。
  v1 不做游标翻页（榜单一次最多 200 条已够）。
- 契约基线常量：`content_end`（种子数据截止日）、`gen_min`/`gen_max`（出生年份区间，
  当前 2007..2025）、`book_count=30878`、`licensed_count=47`。以 `/strata/healthz`
  实际返回为准，不要在 Dart 侧硬编码。

## 现有端点（已实现）

### GET /strata/healthz

200：

```json
{
  "status": "ok",
  "schema_version": 1,
  "seed_version": "…",
  "book_count": 30878,
  "licensed_count": 47,
  "content_end": "2026-05-03",
  "gen_min": 2007,
  "gen_max": 2025
}
```

UI 启动轮询即打这个端点（200ms 间隔、15s 超时），`status=="ok"` 即认为引擎就绪。

### GET /strata/meta

200：`{ "manifest": <Manifest>, "seed_meta": {key: value, …} }`。
`Manifest` 字段与 `app/assets/manifest.json` 一致（`schema_version`、`seed_version`、
`content_end`、`built_at`、`book_count`、`licensed_count`、`tag_count`、`tag_rows`、
`gen_min`、`gen_max`、`counts`、`files`）。

### GET /strata/books/:nid

- 400 `invalid_argument`：nid 不是正整数。
- 404 `not_found`：nid 不在种子（含 47 本授权书，均可见）。

200：

```json
{
  "source": "seed" | "local",
  "data_end": "2026-05-03",
  "book": { …24 列 Book… },
  "tags": ["…"],
  "local": <Observation|null>,
  "effective": { "clicks": …, "favs": …, "praises": …, "words": …,
                 "status": …, "updated_at": … }
}
```

`effective` = 种子值被 `local`（最新观测）覆盖后的展示值。Phase 4 之后
`local != null` 即 `source == "local"`。

### GET /strata/rankings/favs?year=&genre=&limit=

- `year` 必填，须在 `gen_min..gen_max` 内，否则 400。
- `genre` 可选，枚举：魔幻/玄幻/古风/科幻/校园/都市/游戏/同人/悬疑。

200：

```json
{
  "meta": { "kind": "favs", "pool": "seed", "ordering": "fav_pctl",
            "content_end": "…", "year": 2019, "genre": null|"魔幻",
            "limit": 50, "licensed_excluded": true },
  "items": [ { "nid": 123, "title": "…", "author": "…", "genre": "…",
               "est_year": 2019, "favs": 12345, "fav_pctl": 99.7 } ]
}
```

分位只按种子池（`is_licensed=0`）计算；`licensed_excluded` 恒为 true，榜单永不出现授权书。

### GET /strata/rankings/short?limit=

200：同上结构，`meta.kind="short"`、`ordering="favs"`、`short_max_words=50000`，
`items` 元素为 `{ nid, title, author, genre, est_year, favs, words }`（无分位字段）。

## 草案（Phase 3/4 实现，未落地前 UI 不得依赖）

### GET /strata/search?q=&limit=

L1 本地搜索：种子库内 `title`/`author` 的 LIKE 匹配（v1 无 FTS5）。响应结构复用
榜单：`meta.kind="search"` + `items`（Book 精简列）。空 `q` 返回 `invalid_argument`。
官方搜索 L2（30 条硬上限 + 静默限流识别）走 Phase 4，端点预留
`POST /strata/search/remote`，响应附 `rate_limited: bool`。

### POST /strata/books/:nid/refresh

触发一次移动版详情抓取（共用限速器，前台优先）。202 接受 → 轮询该 nid 详情直到
`source` 变化或 `meta` 报错；失败分类沿用 05 号文档三态判据
（`ok` / `not_found` / `transient`）。绝不写 `seed.db`。

### GET /strata/books/:nid/observations

按 `observed_at` 倒序返回该书的观测数组（`Observation[]`），供六指标折线。
分页预留 `before=`（早于某时间戳）。

### 书架 / watchlist（Phase 4/5）

| 端点 | 方法 | 语义 |
| --- | --- | --- |
| `/strata/shelf` | GET | 书架列表（本地收藏） |
| `/strata/shelf` | PUT/DELETE | 收藏/取消，body 只有 `nid` |
| `/strata/watchlist` | GET | 观测列表（含 `role: self\|peer`） |
| `/strata/watchlist` | POST/DELETE | 增删（`nid` + `role`） |

只写 `user.db`；与种子的关联**只用 `nid`**（rowid 每次种子发布都会重排）。

## FFI 启动契约（Phase 1）

`c-shared` 库导出三个符号：

- `char* strata_start(char* assets_dir, char* data_dir)` → JSON
  `{ok, addr?, seed_version?, book_count?, licensed_count?, content_end?, error?}`，
  `addr` 形如 `http://127.0.0.1:PORT`；
- `char* strata_stop()` → 同构 JSON；引擎未启动也返回 `{ok:true}`；
- `void strata_free(char*)` → 释放以上返回的 C 字符串（Dart 侧用完必调）。

启动失败（如种子缺失/校验不过）通过 `error` 字符串返回诊断信息，UI 据此显示
失败页，不做无限重试。

# APP 设计文档 01：技术栈

## 0. 选型

| 层 | 选型 |
| --- | --- |
| 平台 | Android + iOS |
| 包名 | `io.github.intersetwq.strata`（2026-11-21 定案；Android applicationId / iOS bundle id，上架后不可更改） |
| UI | Flutter 3.x / Dart 3，Riverpod + go_router，CustomPainter + fl_chart |
| 引擎 | 内嵌 Go 服务（in-process，C archive / shared lib 经 `dart:ffi` 挂载） |
| HTTP | Gin，仅监听 `127.0.0.1`，统一 RoutePrefix `/strata` |
| 存储 | SQLite（纯 Go 驱动 `modernc.org/sqlite`，禁 cgo） |
| 搜索 | 本地索引 + 官方双接口三层合并（口径见 04） |
| 模型 | Freezed（UI）+ Go struct（引擎），HTTP 为边界 |
| 测试 | `go test`（解析器纯函数 + golden test）+ flutter_test |
| 分发 | 种子随包只读；详情页进入即抓写回本地；Android APK / iOS 自签 IPA，不上架 |

## 1. 架构

```
App 进程
├── Flutter UI：只通过 HTTP 调 localhost 引擎，不直接碰 SQLite
└── 内嵌 Go 引擎
    ├── Gin HTTP 服务：127.0.0.1:<动态端口>
    ├── 爬虫层：限速、重试、解析器（纯函数）
    └── 存储层：SQLite（seed.db 只读 + user.db 读写）
```

- **in-process 而非子进程**：iOS 禁止 fork/exec 外部二进制，Go 引擎以库形式嵌入同一进程；
  Android 为双端一致同样走 in-process。
- **启动握手**：UI FFI 启动引擎 → 200ms 轮询 `/healthz`（15s 超时）→ 就绪进主界面；
  失败展示诊断页，不无限重载。端口动态分配（`127.0.0.1:0`），固定端口降级。
- 参照 [go-music-dl](https://github.com/guohuiyuan/go-music-dl)（AGPL-3.0，同许可）：
  限速器、启动握手、动态端口、数据目录解析等工具层可移植（保留原版权声明）；
  音乐业务与 Gio/WebView 壳不复用。

## 2. 数据约束（选型的依据）

| # | 约束 | 落地 |
| --- | --- | --- |
| 1 | 全库 245,887 行，88.3% 无唯一名次 | 不内置全库；种子只装精选 |
| 2 | 快照上界 2026-05-03，非实时 | `observed_at` 显式标注数据时间 |
| 3 | 累计指标跨世代不可比 | 排序默认同代分位，绝对数只作辅助；分位构建期算好 |
| 4 | 快照 status ≠ 当期状态 | 端上不重算生命状态 |
| 5 | 标签词表有版本（2014 上线、2022 清理）；萌神是荣誉 | 标签带词表版本；萌神不进题材统计 |
| 6 | `fireMoney` 是定价非营收 | 不计算营收 |
| 7 | 遗漏偏短、新、更新中（覆盖率 69.3%） | 未收录显式语义，首次进入即抓，不显示「不存在」 |
| 8 | banner 分下注/奖励两类、图上无书名 | banner 独立表带类型，UI 叠字 |
| 9 | 定年 = 281 锚点 + nid 插值（内插段 LOO p90 3 天） | 构建期完成，端上只读 |
| 10 | 覆盖安装整包替换种子 | 种子与用户数据分文件，跨库只认 `nid` |

## 3. 存储布局

| 文件 | 位置 | 权限 | 覆盖安装 |
| --- | --- | --- | --- |
| `seed.db.gz` | App bundle / assets | 只读 | 整包替换 |
| `seed.db` | 数据目录 `seed/seed-<version>.db`（解压副本） | 只读打开 | 按 `seed_version` 比对替换，整文件换名 |
| `user.db` | 应用数据目录 | 读写 | 保留 |

- `seed.db`：`books`（28 列）+ `book_tags` + `deep_ranks` + `calendar_universe`（发书日历）+ `seed_meta`，10 索引；
  `banner`/`rank_snapshots` 作为独立资产随包分发，不建表。构建期产出，运行时只 SELECT。
- `user.db`：`observations`（只追加，键 `nid + observed_at`）、`discovered`（搜索命中即收录，
  不参与统计）、`watchlist`（统一列表：激活 = 追踪，未激活 = 只存——原「书架」与「追踪列表」
  已合并，本 app 无阅读功能、书架语义不成立）、标注、搜索历史。
- 跨库 `ATTACH` join；同一字段取 `observed_at` 较新者。**跨库关联只能用 `nid`**，
  rowid 跨种子版本会重排。
- 不做 FTS5：种子规模小，内存索引足够；FTS5 中文 trigram 有已知失效。

## 4. 端上爬虫（数据新鲜度主通路）

| 维度 | v1 规则 |
| --- | --- |
| 触发 | 前台进入详情页即抓；观测列表订阅式定期爬取（07：用户显式开启、≤100 本、间隔 ≥6h）。不做全库后台批量 |
| 限速 | Go 侧全局限速器强制（每秒上限 + 单日上限）；详情页请求优先，队列设上限、溢出丢弃 |
| 去重 | 同书 30 秒窗口内只发一次 |
| 写入 | Go 侧单事务：更新最新值 + 追加观测；UI 不直接写库 |
| 失败 | 结构化错误；UI 回落本地值并标注数据时间 |

抓取通路三档：**移动版 HTML 为稳定基线（默认），App API 为可选增强（失效即降级）**，
PC 版按需；端点与字段见 05，接口事实见 `docs/sfacg-*.md`。

## 5. 搜索（概要）

三路合并：L0 联想（本地前缀索引 + 官方 searchreffer）/ L1 本地（seed+user 内存索引）/
L2 官方（HTML ≤30 条截断 + JSON 6–15 条，字段互补必须合并）。L2 命中而本地没有的书
写 `discovered`，不参与统计。合并去重按 `NovelID`。完整口径以 04 为准。

## 6. v1 不做

服务端 / 观测上报；全库后台爬虫（订阅式除外）；全库离线搜索；FTS5；同义词标签合并；
跨世代绝对数排名；用户系统与云同步；上传搜索词；App Store 上架适配。

## 7. 目录结构

```
app/
├── lib/                        # Flutter UI
│   ├── data/api/               # localhost HTTP 客户端
│   ├── domain/                 # Freezed 模型
│   ├── features/               # rankings / detail / search / watchlist（含统一兴趣列表）
│   └── core/ffi/               # FFI 桥：启动引擎、就绪探测
├── engine/                     # 内嵌 Go 引擎
│   ├── cmd/engine/main.go      # 库入口（非独立可执行）
│   └── internal/
│       ├── api/                # Gin 路由
│       ├── appshell/           # 启动握手
│       ├── crawler/  parser/  search/  store/
│       └── store/              # seed.db 只读 + user.db 读写
└── assets/seed.db.gz           # 随包种子
```

## 8. 待决问题

| # | 问题 | 建议 |
| --- | --- | --- |
| 1 | **FFI 可行性**：`dart:ffi` 调 Go C-archive 在双端真机的可用性、包体增量、调试方式 | 写代码第一步做 spike；失败回退 MethodChannel + 平台原生库 |

> 运行时 ATS：iOS 需开 `NSAllowsLocalNetworking`（回环明文 HTTP 要求，与审核无关），
> 列入集成测试。

## 9. 硬化实测（2026-11-23，v0.1.0-pre.11 release 构建实测）

**体积**：release APK 53,287,272 B ≈ 50.8 MB（arm64-only）。分解：

| 组件 | 大小 | 占比 |
| --- | --- | --- |
| `libstrata.so`（Go 引擎，`-s -w`） | 24.7 MB | 48.5% |
| `libflutter.so`（Flutter arm64） | 11.2 MB | 22.0% |
| `libapp.so`（Dart AOT） | 7.1 MB | 14.0% |
| `seed.db.gz`（捆绑种子 18,751 本） | 7.0 MB | 13.8% |
| `classes.dex` + 其余 | ~0.6 MB | ~1.1% |

> 最大单件是 `libstrata.so`：Go runtime + 纯 Go SQLite（modernc.org/sqlite，
> cgo 会破坏 iOS 交叉编译的既定裁定）。压缩空间有限（Go 深度裁剪/加壳不做，
> 兼容风险大于收益）；`libflutter.so` 由 Flutter SDK 决定。debug APK
> 220 MB（含 armeabi-v7a/x86_64 三份 `libflutter.so` + 未裁剪引擎），仅装机调试用。

**启动耗时**（真机 `am start -W` 冷启动 TotalTime，×3）：

- release：3536 / 3405 / 3356 ms（中位 ≈ 3.4 s）
- debug：4154 / 3372 / 3431 ms（对照组）

> release 与 debug 差距小：大头是引擎 FFI 初始化 + seed.db 解压挂载 +
> 首屏 HTTP，不是 AOT 编译差。iOS 无数据（无 Xcode）。

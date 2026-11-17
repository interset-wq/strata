# app/ —— 书层 Strata

手机端 App 本体。当前进度：Go 引擎已实现（`engine/`：localhost HTTP API + 双库挂载），
种子资产已生成（`assets/`，30,878 本）；Flutter UI 与 FFI 集成进行中。

早期设计稿与实测档案在 [`../archive/`](../archive/)，但方案已过时、数字口径已更新，
仅作沿革参考；产品重新设计时以分析报告为准。

正式设计文档在 [`docs/`](./docs/)：

| # | 文档 | 状态 |
| --- | --- | --- |
| 01 | [`技术栈`](./docs/01-tech-stack.md) | 已完成 v2.1：Flutter UI + 内嵌 Go 服务 + localhost API；Android/iOS；v1 做端上爬虫、无中心化服务端 |
| 02 | [`数据模型与种子构建`](./docs/02-data-model.md) | 已完成 v1.0：双库结构、`books` 24 列 + `book_tags` + `seed_meta`、9 个索引（含部分索引）、种子构建流水线与迁移策略 |
| 03 | [`榜单与分位排序`](./docs/03-rankings.md) | 已完成 v1.0：榜单矩阵（三类数据源）、分位以全库为参照系、展示红线；分位字段/候选池口径/短篇榜刻度已由报告 18-19 与 02 落定回填 |
| 04 | [`搜索与自动收录`](./docs/04-search.md) | 已完成 v1.0：官方搜索 30 条硬上限、本地不可替代（宽泛词多 4.7–80 倍）、静默限流识别、收录收益 9.2% |
| 05 | [`详情页抓取与写回`](./docs/05-detail-fetch.md) | 已完成 v1.0：只抓移动版（不抓 PC）、三态判据先于解析、只写 `user.db` 不写 `books`、共用限速器、点击变化观测因 ±500 量化精度取消 |
| 06 | [`更新机制`](./docs/06-update-mechanism.md) | 已完成 v1.0：五类"更新"分界、不叠全库调度（U5 订阅爬取除外）、种子换包原子替换 + 用户库事务迁移、三类保留期各自独立 |
| 07 | [`作者工作台与观测列表`](./docs/07-author-workbench.md) | 已完成 v1.0：**更新热力图（首屏，锚官方全勤阈值 3,000 字/500 元）+ 全勤达标看板**、`watchlist.role` 分本人/同期对照、六指标折线 + 复合指标（端上现算）、订阅式后台爬取——对标官方只给收藏变化的结构性缺口 |
| 08 | [`引擎 HTTP 契约`](./docs/08-engine-api.md) | v1.0：现有 5 个端点的响应模型/错误码/分页，search / detail 刷新 / observations / watchlist 草案；Go↔Dart 双方以此为准 |

## 引擎（`engine/`）

Go 实现的 localhost HTTP 服务，`internal/` 分四层：

- `appshell`：资产/数据目录解析、种子解压安装、user.db 初始化；
- `store`：SQLite 双库挂载（只读 `seed.db` ATTACH 进可写 `user.db`）与查询；
- `api`：gin 路由，现有 5 个端点（见 08 契约）；
- `engine`：进程内启动入口，供 CLI（`cmd/engine`）与 c-shared FFI（`cmd/ffi`）共用。

纯 Go SQLite 驱动 `modernc.org/sqlite`（禁 cgo 的驱动），端口动态分配，启动打印
`STRATA_ADDR` / `STRATA_SEED`。

外部接口的事实档案在 [`../analysis/references/sfacg-endpoints.md`](../analysis/references/sfacg-endpoints.md)
（端点、字段、边界、限流，全部实测于 2026-11-16）。

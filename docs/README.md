# 全局文档（`docs/`）

> 本目录存放**跨 analysis（数据分析）与 app（产品）共用的全局文档**：外部接口事实、
> 我们自定义指标的定义、小说形式的定义。
> analysis 目录只负责数据分析与报告；app/docs 只负责产品设计。
> 三者的边界：全局定义放这里，使用方在原位置留一行绝对路径指针。

## 文档清单

| 文档 | 类别 | 权威范围 |
| --- | --- | --- |
| [`sfacg-endpoints.md`](./sfacg-endpoints.md) | 接口事实 | SFACG **PC 端** HTML + `HTML5.ashx` 端点、参数、状态码、限流、存活判据 |
| [`sfacg-app-api.md`](./sfacg-app-api.md) | 接口事实 | SFACG **官方 App API**（`api.sfacg.com`）认证、19 字段、端点、77 推送位 |
| [`sfacg-live-ranks.md`](./sfacg-live-ranks.md) | 接口事实 | 现网榜单端点（`MonthlyBoy.ashx` 任意月、月票/新书/热销口径） |
| [`metrics-definitions.md`](./metrics-definitions.md) | **自定义指标** | 定年/universe/五分位/pr/覆盖率/断更/生命状态/推荐信号白名单的唯一权威定义 |
| [`13-form-definitions.md`](./13-form-definitions.md) | **小说形式** | `form` 五值（short/medium/long/dialogue/ip_collab）判定优先级、边界、优质短篇判定 |
| [`16-length-weighted-quality.md`](./16-length-weighted-quality.md) | **自定义指标** | 篇幅加权口碑分 `lqs`：长篇区排序信号，`pr` 的「世代 × 收藏档」分位 × 归一化篇幅系数（0.75–1.0）、校准与边界 |
| [`api-field-mapping.md`](./api-field-mapping.md) | **字段对应** | App API 18 字段 ↔ CSV/books 列的实测对应、一致率、值映射、写回约束（`point`/`bgBanner` 误映射纠正） |

## 使用约定

- **原位置的指针**：文档迁来后，`analysis/references/` 与 `app/docs/` 的同名文件
  只剩一行项目根绝对路径（如 `/docs/sfacg-app-api.md`），指向本目录。
  交叉引用无需修改——顺着指针即可找到正文。
- **路径是项目根绝对路径**：以 `/docs/...` 表示，不是操作系统绝对路径。
- **权威性**：接口事实以本目录三份为准；指标口径以 `metrics-definitions.md` 为准
  （`lqs` 的完整定义在其 [`16-length-weighted-quality.md`](./16-length-weighted-quality.md)）；
  形式以 `13-form-definitions.md` 为准；API 字段与本地列的对应关系以 `api-field-mapping.md`
  为准。报告里的数字是结论，不是定义。

## 边界提醒

- 本目录**不放**数据分析报告（在 `analysis/reports/`）与产品设计文档（在 `app/docs/`）。
- 动手抓数据前先读对应接口事实文档，不要猜参数、不要试探性请求。
- 所有接口文档遵守同一合规边界：只取书目元数据、不取正文、不登录、不用用户
  cookie、串行 ≥0.5s。

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
| [`quantitative-mode-metrics.md`](./quantitative-mode-metrics.md) | **设计定案** | 量化模式从零设计需要几个自定义指标：**2 个核心**——排序分（口碑发现分，`lqs`/`mqs` 为同指标的不同域实现、不可合并）+ 位置分（`fav_pctl`）；展示视角/`ref_pctl`/基础维度列为可选扩展；含三档施工范围与 6 条开发红线 |
| [`form-definitions.md`](./form-definitions.md) | **小说形式** | `form` 六值（invalid/short/medium/long/dialogue/ip_collab）判定优先级、边界、优质短篇判定 |
| [`length-weighted-quality.md`](./length-weighted-quality.md) | **自定义指标** | 篇幅加权口碑分 `lqs`：长篇区排序信号，`pr` 的「世代 × 收藏档」分位 × 归一化篇幅系数（0.75–1.0）、校准与边界 |
| [`lqs-ranking-integration.md`](./lqs-ranking-integration.md) | **实施规格** | 推荐层如何接入 `lqs`：现状排序基线、两级排序键、对话小配额、验收断言；指标定义仍在 `length-weighted-quality.md` |
| [`api-field-mapping.md`](./api-field-mapping.md) | **字段对应** | App API 18 字段 ↔ CSV/books 列的实测对应、一致率、值映射、写回约束（`point`/`bgBanner` 误映射纠正） |
| [`author-profile-on-demand.md`](./author-profile-on-demand.md) | **设计定案** | 作者资料不预采：App 打开作者页按需请求某本书详情页取头像/名字/作品集，intro 仅 PC 版 |
| [`fake-complete-short-medium.md`](./fake-complete-short-medium.md) | **分析待裁定** | 假完结短/中篇污染排名池：长篇征文即假、第二类僵尸、短篇覆盖缺口；含用户裁定与治理方案 |
| [`contest-roster-harvest.md`](./contest-roster-harvest.md) | 接口事实 + 研究 | 征文参赛清单两套端点、tagId 地图、补采短/中篇的覆盖实证与探针 |
| [`contest-roster-fields.md`](./contest-roster-fields.md) | 接口事实 | 征文清单两套接口逐字段说明 + 真实响应样例（6 字段、大小写差异、Cover 格式差异），供 App 核对 |
| [`contest-display-in-app.md`](./contest-display-in-app.md) | **设计定案** | 在 App 内展示征文信息：赛事档案页 + 参赛清单浏览页的三层数据来源、「我们的形式」筛选排序、降级与待裁定 |
| [`ref-percentile-for-discovered.md`](./ref-percentile-for-discovered.md) | **设计定案** | 库外自动收录书的分位：`ref_pctl` 断点表查表法（nid 定年分组 + favs 查 universe 分布），跨代可比、无需运行时全库；含收藏速率否证与边界降级 |
| [`anchor-density-strategy.md`](./anchor-density-strategy.md) | **分析定案** | 定年锚点按 id 区调整密度是否成立：早期误差大是锚点少非多、外推误差只由 max anchor 距离决定；策略=P0 常态化补最新锚点、早期保留、中段低优先 |
| [`award-winners-as-seed-source.md`](./award-winners-as-seed-source.md) | **分析定案** | 征文获奖书入种（用户已批准）：**剔除 602 本入围污染**→净获奖 **911 本** 规范化表 `contest_awards_normalized.csv`（11 届）+ 140 本库外补采清单；奖项名 44 本可靠/867 本待标定；获奖只作筛选徽标不打分；schema v5 `contest_awards` 表 + 断言 + 双产物的 app/ 交接规格（本 agent 不碰冻结的 app/） |
| [`contest-url-api-patterns.md`](./contest-url-api-patterns.md) | **统领研究** | 比赛 URL 与 API 规律总览：四代 URL 形态/四季节奏/tagId 分配/获奖四代形态四类规律，如何转化为种子质量（补书目+补优质+提定年），研究路线图（已验证 vs 待研究缺口）；细节走本文指针 |

## 使用约定

- **原位置的指针**：文档迁来后，`analysis/references/` 与 `app/docs/` 的原文件
  只剩一行项目根绝对路径（如 `/docs/sfacg-app-api.md`），指向本目录。
  交叉引用无需修改——顺着指针即可找到正文。
- **路径是项目根绝对路径**：以 `/docs/...` 表示，不是操作系统绝对路径。
- **权威性**：接口事实以本目录三份为准；指标口径以 `metrics-definitions.md` 为准
  （`lqs` 的完整定义在其 [`length-weighted-quality.md`](./length-weighted-quality.md)）；
  形式以 `form-definitions.md` 为准；API 字段与本地列的对应关系以 `api-field-mapping.md`
  为准。报告里的数字是结论，不是定义。

## 边界提醒

- 本目录**不放**数据分析报告（在 `analysis/reports/`）与产品设计文档（在 `app/docs/`）。
- 动手抓数据前先读对应接口事实文档，不要猜参数、不要试探性请求。
- 所有接口文档遵守同一合规边界：只取书目元数据、不取正文、不登录、不用用户
  cookie、串行 ≥0.5s。

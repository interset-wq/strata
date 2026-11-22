# 全局文档（`docs/`）

本目录只放**跨 `analysis/`（数据分析）与 `app/`（产品）共用的全局定义与接口事实**。
分析报告在 `analysis/reports/`，产品设计在 `app/docs/`；全局事实留这里，使用方在原位置只留指针。

## 先看哪里

| 要做的事 | 先读 |
| --- | --- |
| 抓 PC 端页面 / 搜索 / 榜单 / 判活 | `sfacg-endpoints.md` |
| 抓 App API（元数据、精确到秒的 `addTime`、`viewTimes`） | `sfacg-app-api.md` |
| 判断当前榜是否可用、展示裁定 | `sfacg-live-ranks.md` |
| 把 API 字段写回本地列 | `api-field-mapping.md`、`metrics-definitions.md` |
| 判断 `form` 或种子收录资格 | `form-definitions.md`、`fake-complete-short-medium.md` |
| 设计量化模式指标 | `quantitative-mode-metrics.md` → `metrics-definitions.md` → 域文档 |
| 征文发现、tagId、获奖入种、App 展示 | `contest-url-api-patterns.md` 导航，再按权威分工读对应文档 |
| 作者头像 / 简介 / 作品集 | `author-profile-on-demand.md` |

## 文档索引

### 接口事实

| 文档 | 权威范围 |
| --- | --- |
| [`sfacg-endpoints.md`](./sfacg-endpoints.md) | PC 端端点、参数、限流、状态码陷阱、判活三态 |
| [`sfacg-app-api.md`](./sfacg-app-api.md) | App API 认证、端点、18 字段字典、77 推送位、能力边界 |
| [`sfacg-live-ranks.md`](./sfacg-live-ranks.md) | 当期榜单端点、快照与展示裁定；历史月榜端点在 endpoints |
| [`api-field-mapping.md`](./api-field-mapping.md) | App API 字段 ↔ 本地列的实测映射与写回约束 |
| [`author-profile-on-demand.md`](./author-profile-on-demand.md) | 作者资料按需抓取：触发、DOM 选择器、返回契约、降级 |

### 指标与形态

| 文档 | 权威范围 |
| --- | --- |
| [`metrics-definitions.md`](./metrics-definitions.md) | 自定义指标总口径：定年、universe、分位、派生口径、推荐信号白名单 |
| [`quantitative-mode-metrics.md`](./quantitative-mode-metrics.md) | 量化模式定案：**只有 2 个核心指标**——排序分 + 位置分 |
| [`length-weighted-quality.md`](./length-weighted-quality.md) | 排序分的长篇域 `lqs`：公式、常量、校准、边界 |
| [`medium-quality-score.md`](./medium-quality-score.md) | 排序分的中篇域 `mqs`：已定参、归档未落地；与 `lqs` 不合并 |
| [`ref-percentile-for-discovered.md`](./ref-percentile-for-discovered.md) | 位置分 `fav_pctl` 的库外域 `ref_pctl`：断点表查表法 |
| [`lqs-ranking-integration.md`](./lqs-ranking-integration.md) | 推荐层接入 `lqs` 的排序键、候选门槛、验收断言 |
| [`form-definitions.md`](./form-definitions.md) | `form` 六值判定与种子收录资格的唯一真源 |
| [`fake-complete-short-medium.md`](./fake-complete-short-medium.md) | 假完结短/中篇与第二类僵尸裁定：已实施（种子 P10） |
| [`anchor-density-strategy.md`](./anchor-density-strategy.md) | 定年锚点密度策略：P0 常规补最新锚点，早期保留、中段低优先 |

### 征文

| 文档 | 权威范围 |
| --- | --- |
| [`contest-url-api-patterns.md`](./contest-url-api-patterns.md) | 规律总览与导航：URL 演进、四季节奏、API/tagId 规律 |
| [`contest-roster-harvest.md`](./contest-roster-harvest.md) | tagId 地图、活动页 URL 台账、补采覆盖与试号实证 |
| [`contest-roster-fields.md`](./contest-roster-fields.md) | 清单返回字段与获奖存储四代形态、提取正则 |
| [`award-winners-as-seed-source.md`](./award-winners-as-seed-source.md) | 获奖入种：净 911 / 剔除 602 / 补采 140、逐届明细与交接规格 |
| [`contest-display-in-app.md`](./contest-display-in-app.md) | App 展示设计：赛事档案页、参赛清单浏览页、请求与降级 |
| [`contest-api-integration-feasibility.md`](./contest-api-integration-feasibility.md) | 端内接入工程可行性：接入点映射、风险与工作量（路径 A/B 均已落地） |

## 权威分工

- **同一事实只在一处维护**，其余文档只写文件级指针；发现重复表或重复数字，优先删重复。
- 接口事实：PC 端看 `sfacg-endpoints.md`，App API 看 `sfacg-app-api.md`，字段映射看 `api-field-mapping.md`。
- 指标：`metrics-definitions.md` 管“是什么”，`quantitative-mode-metrics.md` 管“要几个”；`lqs`/`mqs` 是同指标不同域、不合并；`ref_pctl` 是位置分库外域，不是第 3 个指标。
- 征文：tagId/URL 看 `contest-roster-harvest.md`，字段/获奖形态看 `contest-roster-fields.md`，入种口径与逐届明细看 `award-winners-as-seed-source.md`，展示设计看 `contest-display-in-app.md`。
- `form` 判定看 `form-definitions.md`；假完结剔除是它的 P10 指针规则，规则正文在 `fake-complete-short-medium.md`。
- 数字是**某次快照的现算值**，随数据版本变化；禁止每次重算精确数字，禁止硬编码进代码。结构或语义矛盾照改，数值过期只标注。

## 工作约定

- 路径以项目根为基准；旧指针 `/docs/...` 等价于本目录的 `docs/...`。
- 动手抓数据前先读对应接口档案，不猜参数、不做试探性请求。
- 所有外部数据通路只取元数据、不取正文、不登录、不用用户 cookie，串行 ≥0.5s。
- `app/` 已解禁（v6 由开发 agent 施工）；本目录标注“工程侧 / 实施”的段落是交接规格、分析侧不执行。

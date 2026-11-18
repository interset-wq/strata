# 15 · Icon 语义表

> 产品文档。规则：**同一语义在任何页面必须使用同一个 icon**。
> 新增指标/动作时先查本表；语义已存在就复用，不存在就在此登记后再用。

## 指标展示（紧凑样式，一律 outlined 线性图标）

| 语义 | icon（Flutter） | 说明 |
| --- | --- | --- |
| 收藏 favs | `Icons.favorite_border` | 爱心。展示层用线性；**动作按钮**（收藏/取消收藏）用实心 `Icons.favorite` |
| 点赞/推荐 praises | `Icons.thumb_up_outlined` | 大拇指。展示层用线性；动作按钮用实心 `Icons.thumb_up` |
| 字数 words | `Icons.format_size` | 文字量级 |
| 点击/阅读 clicks | `Icons.visibility_outlined` | 浏览量=可见性 |

## 动作按钮（实心/强调样式）

| 语义 | icon（Flutter） | 使用处 |
| --- | --- | --- |
| 收藏（加入书架） | `Icons.favorite` | 详情页收藏按钮 |
| 追踪 watch | `Icons.visibility` | 详情页追踪按钮、书架页「追踪管理」入口 |
| 换一批/换一换 | `Icons.refresh` | 随机书架按钮、随机连载页「换一批」、下拉刷新手势 |
| 返回 | `Icons.arrow_back` | 二级页 AppBar |
| 回到顶部 | `Icons.arrow_upward` | 长页右下角 BackToTop（滚动 >500px 出现） |
| 换源切换 | `Icons.swap_vert` | 榜单页口径切换 |
| 观测时序 | `Icons.timeline` | 详情页「观测数据」入口 |
| 阅读记录入口 | `Icons.history` | 首页搜索行右侧 |
| 搜索 | `Icons.search` | 首页搜索框、榜单页 |

## 分类入口（首页宫格）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 分类找书 | `Icons.category` | 首页宫格 |
| 按状态浏览 | `Icons.update` | 首页宫格 |
| 征文比赛 | `Icons.emoji_events` | 首页宫格 |
| 短篇榜 | `Icons.article` | 首页宫格 |

## 分类入口（首页 curated 宽卡）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 授权作品（licensed） | `Icons.lock` | 首页宽卡入口（可点击用实心，与规则 4 一致） |
| 萌神获奖 | `Icons.emoji_events` | 首页宽卡入口（与宫格"征文比赛"同"获奖"语义，复用） |

## 状态占位

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 图片不可用 | `Icons.image_not_supported_outlined` | 大图精选卡片 / 全屏查看器：banner cut 图 404 时的占位容器（不做封面兜底——3:4 封面塞 16:9 容器会被裁成一条） |

## 使用规范

1. 指标展示统一走 `MetricBadge` 组件（`lib/widgets/metric_badge.dart`）：
   12px 线性 icon + 10px 文本，icon 与文本同色。禁止手写 `Icon + Text` 拼指标。
2. 图标尺寸：指标 12px、按钮 18–20px、宫格 22px、大空态 48–56px。
3. 颜色跟随文本色（`onSurfaceVariant`/`secondary`/`primary`），不单独设色。
4. outlined 用于"展示"，filled 用于"可点击/已激活"——这是唯一的填充语义。

## 当前覆盖页面

- 随机连载列表（字数/收藏/点击/点赞 MetricBadge 行）
- 分类/状态/比赛/短篇浏览页卡片（收藏 badge）
- 发现流行页卡片（点击 badge）
- 本地搜索结果（收藏 badge）
- 详情页观测历史（收藏/赞/字数）、观测数据 chips（收藏/推荐/字数）
- 榜单字数榜（字数 badge）

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
| 关注（加入列表） | `Icons.bookmark_add_outlined` | 详情页「关注此书」按钮 / 底部动作行；已关注态用实心 `Icons.bookmark` |
| 追踪（激活后台抓取） | `Icons.visibility` | 详情页追踪切换（未追踪时线性 `Icons.visibility_outlined`）、关注页追踪切换 |
| 换一批/换一换 | `Icons.refresh` | 随机池入口（首页）、随机连载页「换一批」、下拉刷新手势 |
| 返回 | `Icons.arrow_back` | 二级页 AppBar |
| 回到顶部 | `Icons.arrow_upward` | 长页右下角 BackToTop（滚动 >500px 出现） |
| 换源切换 | `Icons.swap_vert` | 榜单页口径切换 |
| 观测时序 | `Icons.timeline` | 详情页「观测数据」入口 |
| 阅读记录入口 | `Icons.history` | 首页搜索行右侧 |
| 搜索 | `Icons.search` | 首页搜索框、榜单页 |
| 形式推断说明 | `Icons.info` | 首页 form tab 行末按钮：弹出「关于小说形式」模态框（形式为推断，非官方分类；原右上角刷新按钮改造，刷新走下拉手势） |
| 打开官方页面 | `Icons.open_in_new` | 详情页 AppBar：系统浏览器打开移动版详情页（App 自身不加载官方内容） |
| 复制（标题/ID） | `Icons.copy_rounded` | 详情页：长按标题复制、元数据卡「书籍 ID」行复制（SnackBar 反馈「××已复制」） |

## 分类入口（首页宫格）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 分类找书 | `Icons.category` | 首页宫格 |
| 按状态浏览 | `Icons.update` | 首页宫格 |
| 征文比赛 | `Icons.emoji_events` | 首页宫格 |
| 短篇榜 | `Icons.article` | 首页宫格 |
| 经典榜单入口 | `Icons.leaderboard` | 短篇 tab 入口列表：点击/收藏/点赞/字数四榜（页内 SegmentedButton 切换） |

## 分类入口（首页 curated 宽卡）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 授权作品（licensed） | `Icons.lock` | 首页宽卡入口（可点击用实心，与规则 4 一致） |
| 萌神获奖 | `Icons.emoji_events` | 首页宽卡入口（与宫格"征文比赛"同"获奖"语义，复用） |
| 官方榜单 | `Icons.leaderboard_outlined` | 首页长篇宽卡（页内 Tab 切换月票/新书/热销/打赏）/ 对话 tab 宽卡（直达对话月票榜 m4）；文档不登记本数 |

## 分类入口（短篇 tab 入口列表 / 中篇/对话 tab 入口网格）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 分类总榜 | `Icons.format_list_numbered` | 中篇/对话 tab 入口网格（全部作品收藏序；年份榜默认"全部年份"也可达） |
| 短对话 | `Icons.short_text` | 对话 tab 入口网格（≤5 万字） |
| 中对话 | `Icons.menu_book` | 对话 tab 入口网格（5–15 万字） |
| 长对话 | `Icons.auto_stories` | 对话 tab 入口网格（>15 万字） |
| 年份榜 | `Icons.calendar_month` | 短篇 tab 入口列表 / 中篇/对话 tab 入口网格 |
| 比赛榜 | `Icons.emoji_events` | 短篇 tab 入口列表 / 中篇/对话 tab 入口网格（复用"征文比赛"语义） |
| 题材浏览 | `Icons.category` | 短篇 tab 入口列表 / 中篇/对话 tab 入口网格（复用"分类找书"语义） |
| 优质短篇/中篇/对话 | `Icons.star` | 短篇入口列表 / 中篇/对话入口网格（同代分位榜，docs/form-definitions §6） |
| 随机短篇/中篇/对话 | `Icons.shuffle` | 短篇入口列表 / 中篇/对话入口网格（/strata/random?status=short，form 区分） |

## 主导航（底部 Tab Bar）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 发书日历 | `Icons.event_available_outlined` | 底部 Tab Bar 第 3 位（2026-11-19 替换搜索——搜索入口在各 form tab 页内）；选中态用实心 `Icons.event_available`（规范 4：filled = 已激活） |
| 关注 | `Icons.bookmark_outline` | 底部 Tab Bar 第 4 位（2026-11-20 由「书架」改名——app 无阅读功能、书架语义不成立，书架并入 watchlist 为未激活条目；icon 与详情页关注按钮同语义同 icon）；选中态用实心 `Icons.bookmark`（规范 4） |

## 状态占位

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 图片不可用 | `Icons.image_not_supported_outlined` | 大图精选卡片 / 全屏查看器：banner cut 图 404 时的占位容器（不做封面兜底——3:4 封面塞 16:9 容器会被裁成一条） |
| 头像不可用 | `Icons.person` | 作者页头部 CircleAvatar：无网络头像或加载失败时的占位（outlined，onSurfaceVariant；展示层 outlined 规范 4） |

## 动作

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 切换排序方向 | `Icons.swap_vert` | 大图精选 gallery AppBar：收藏降序/升序切换（tooltip 显示目标方向） |
| 打开年月选择器 | `Icons.expand_more` | 日历标题行：标题尾小箭头，点标题打开二维年月选择器（BottomSheet） |
| 站内全搜 | `Icons.travel_explore` | 搜索页「搜全站」按钮（官方搜索手动触发，L1 结果段尾部；docs/08 §search-remote） |

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
- 作者页（头像占位 `Icons.person`；书目行为简单文本行，暂无 MetricBadge 语义）
- 搜索页（收藏 badge、`Icons.travel_explore` 全搜按钮、历史 chips 无 icon）

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
| 观测时序 | `Icons.timeline` | 数据页入口（`/book/:nid/data`）：关注页行尾快捷入口 / 详情页「观测历史」行尾「图表」按钮 |
| 阅读记录入口 | `Icons.history` | 首页搜索行右侧 |
| 搜索 | `Icons.search` | 首页搜索框、榜单页 |
| 形式推断说明 | `Icons.info` | 首页 form tab 行末按钮：弹出「关于小说形式」模态框（形式为推断，非官方分类；原右上角刷新按钮改造，刷新走下拉手势） |
| 打开官方页面 | `Icons.open_in_new` | 详情页 AppBar：系统浏览器打开移动版详情页（App 自身不加载官方内容）；单届赛事档案页 AppBar 同语义复用，仅 icon + tooltip「官方活动页」（2026-11-27 从正文动作行移入，URL 来自引擎台账，未验证则不显示） |
| 复制（标题/ID） | `Icons.copy_rounded` | 详情页：长按标题复制、元数据卡「书籍 ID」行复制（SnackBar 反馈「××已复制」） |
| 逆序切换 | `Icons.compare_arrows` | 经典榜单页指标行尾部：升/降序切换（升序态图标着色，tooltip 提示当前可切方向） |
| 筛选 | `Icons.filter_list` | 经典榜单页 AppBar：四维筛选面板（状态/价格/题材/标签 BottomSheet，有激活维度时带计数角标；年份走顶部独立年份条） |

## 分类入口（首页宫格）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 分类找书 | `Icons.category` | （原首页长篇宫格，2026-11-23 由「书单」格取代；本 icon 现见下方「题材浏览」） |
| 按状态浏览 | `Icons.update` | 首页宫格 |
| 征文比赛 | `Icons.emoji_events` | 首页宫格 |
| 短篇榜 | `Icons.article` | 首页宫格 |
| 经典榜单入口 | `Icons.leaderboard` | 短篇/中篇/对话 tab 入口行：点击/收藏/点赞/字数四榜（页内 SegmentedButton 切换；总榜=其中收藏段，故各 tab 不再单列总榜入口） |
| 官方书单 | `Icons.bookmarks` | 「书单推荐」区块更多按钮（2026-11-25 原长篇宫格入口被「日轻」取代）：官方书单浏览入口（顺序 id 探测，docs/booklist-in-app.md） |
| 日轻 | `Icons.local_library` | 首页长篇宫格（2026-11-25 用户裁定取代「官方书单」入口）：官方授权日本轻小说全量列表（/licensed，PoolListPage）；原「授权作品」宽卡入口退役；不用 `Icons.menu_book`（已被「中对话」占用） |
| 官方榜单 | `Icons.leaderboard_outlined` | 首页长篇宫格第 5 格（2026-11-25 用户裁定：宽卡降级为宫格单元、与作者榜同一行）：页内 Tab 切换月票/新书/热销/打赏；outlined 与「经典榜单」实心 `Icons.leaderboard` 同排区分（在线口径 vs 本地口径） |
| 作者榜 | `Icons.person_search` | 首页长篇宫格第 2 格 / 中篇·短篇·对话 tab 入口（2026-11-25 用户裁定：全 form 覆盖）：构建期预构建 top100 作者（/author-ranks?form=，引擎零运行时计算；docs/author-rank.md） |

## 分类入口（首页 curated 宽卡）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 获奖记录 | `Icons.emoji_events` | 单届赛事档案页 AppBar，仅 icon + tooltip「获奖记录」（2026-11-27 从正文获奖区块收口；无获奖数据时隐藏）；与首页宫格「征文比赛」同「获奖」语义，复用 |
| 官方榜单 | `Icons.leaderboard_outlined` | 对话 tab 入口行第 4 格「月票榜」（直达对话月票榜 m4）；首页长篇原宽卡 2026-11-25 降级为宫格单元（见「首页宫格」分节）；文档不登记本数 |
| 赛事归档 | `Icons.event_note` | 对话 tab 入口行第 5 格「对话线赛事」（`/contest-archive?lane=dialogue`；2026-11-26 用户裁定：原对话区内联归档列表退役，入口收进导航行）+ IP tab「IP 合集」标题行尾部「IP 线赛事 ›」（`?lane=ip`，同日补：lane 归档此前无入口）+ 短篇 tab 入口行「短篇征文」（`?lane=short`，2026-11-27 用户裁定：超新星杯短篇/2024主题短篇从「主题」tab 迁来）|

## 分类入口（原中篇/对话 tab 入口网格，2026-11-26 精简退役）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 短/中/长对话篇幅轴 | （无 icon） | 经典榜单页（对话 form）顶部篇幅 chip 行：全部/短 ≤5万/中 5–15万/长 >15万（2026-11-26 用户裁定：篇幅是筛选轴不是三个独立页面，首页短/中/长入口退役；`Icons.short_text`/`Icons.menu_book`/`Icons.auto_stories` 随入口退役） |
| 年份榜 | `Icons.calendar_month` | 官方榜单页月份按钮（原首页年份榜入口退役：年份在经典榜单页顶部年份条切换） |
| 比赛榜 | （无 icon） | 经典榜单页侧滑赛道面板（原首页比赛榜入口退役；`Icons.emoji_events` 现保留给单届赛事档案页 AppBar 获奖记录入口） |
| 题材浏览 | （无 icon） | 经典榜单页筛选面板（原首页题材榜入口退役；`Icons.category` 随入口退役） |
| 优质中篇/对话 | （无 icon） | 经典榜单页 order=pct 排序（原首页优质入口退役；`Icons.star` 随入口退役） |
| 随机短篇/中篇/对话 | （无 icon） | 各 tab 随机预览列表「更多」进随机池页（`Icons.shuffle` 随首页入口退役） |

## 主导航（底部 Tab Bar）

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 发书日历 | `Icons.event_available_outlined` | 底部 Tab Bar 第 3 位（2026-11-19 替换搜索——搜索入口在各 form tab 页内）；选中态用实心 `Icons.event_available`（规范 4：filled = 已激活） |
| 关注 | `Icons.bookmark_outline` | 底部 Tab Bar 第 4 位（2026-11-20 由「书架」改名——app 无阅读功能、书架语义不成立，书架并入 watchlist 为未激活条目；icon 与详情页关注按钮同语义同 icon）；选中态用实心 `Icons.bookmark`（规范 4） |

## 状态占位

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 图片不可用 | `Icons.image_not_supported_outlined` | 大图精选卡片 / 全屏查看器：banner cut 图 404 时的占位容器（不做封面兜底——3:4 封面塞 16:9 容器会被裁成一条） |
| 头像不可用 | （无 icon） | 作者页头部 / 作者榜行：无网络头像时占位为**作者名首字符**（用户 2026-11-25 裁定；原 `Icons.person` 占位退役——纯图标占位无辨识信息，首字符至少能对上名字） |

## 动作

| 语义 | icon | 使用处 |
| --- | --- | --- |
| 切换排序方向 | `Icons.swap_vert` | 大图精选 gallery AppBar：收藏降序/升序切换（tooltip 显示目标方向） |
| 打开年月选择器 | `Icons.expand_more` | 日历标题行：标题尾小箭头，点标题打开年月双列滚轮（BottomSheet CupertinoPicker，用户 2026-11-25 定） |
| 站内全搜 | `Icons.travel_explore` | 搜索页「搜全站」按钮（官方搜索手动触发，L1 结果段尾部；docs/08 §search-remote） |
| 加入对照作品 | `Icons.person_add_alt_1` | 数据页「同期对照」区块：本地搜索选书加入 watchlist（role=peer，docs/07 §1） |

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


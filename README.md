# 书层 Strata

![](https://img.shields.io/badge/release-v1.0.1-blue) ![](https://img.shields.io/badge/data-248%2C338%20novels-green)

基于 SF 轻小说（菠萝包轻小说）二十年书目数据的**离线优先找书 app**：
一个 APK 内置完整历史书目库（248,338 本），内嵌 Go 引擎本地查询，
在线能力（官方清单、详情刷新、作者追踪）按需补充——没有服务端，没有账号。

**核心判断**：官方榜单回答「现在什么火」，本项目回答「过去十年结构如何变化」。
一本 2015 年完结的作品不再给站方带来收入，因此不会进入任何当期榜；
但它的成绩作为书目事实并不随时间衰减。这个错位是产品的出发点，
也是全部数据工作的唯一红线。

---

## 产品（`app/`）

| 能力 | 说明 |
| --- | --- |
| 经典榜单 | 长篇/中篇/短篇/对话多维榜单，收藏/点击/点赞同代分位排序，题材/状态/标签/年份/价格联动筛选 |
| 量化榜单 | 口碑（cqs）与位置（cps）双榜，offset 翻页器定位长尾 |
| 比赛归档 | 官方征文赛事档案：赛程、覆盖率、代表作、参赛/获奖清单按需抓取（限速 + 缓存 + 三态判活） |
| 作者榜 | 全站作者按累计成绩排名，头像缓存 + 关注 |
| 日历 | VIP 上架周历（PreOrder 期次），内置库上架速览 |
| 关注与通知 | 关注作者定时刷新（引擎内置 cron），更新写入通知中心 |
| 收录 | 库外作品点击即自动收录，与内置书地位均等，指标端上补算 |

技术形态：Flutter UI + Go 引擎（`-buildmode=c-shared`，dart:ffi localhost HTTP）。
只读种子库 `seed.db` + 可写 `user.db` 两个 SQLite；iOS 侧仅差 Xcode 构建。
详见 [`app/README.md`](./app/README.md) 与设计文档 [`app/docs/01`–`16`](./app/docs/01-tech-stack.md)。

## 构建

```bash
# Flutter（Android debug）
cd app/ui && flutter build apk --debug

# 引擎（Android arm64 FFI）
cd app/engine
GOOS=android GOARCH=arm64 CGO_ENABLED=1 \
  CC=<ndk>/toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android24-clang.cmd \
  go build -buildmode=c-shared -o libstrata.so ./cmd/ffi

# 种子库（依赖 analysis 管线）
cd analysis && uv run python ../app/tools/seedbuild/build_seed.py
```

发布：打 `v*` tag 推送即触发 [.github/workflows/release.yml](.github/workflows/release.yml)
（NDK 编引擎 → release APK → GitHub Release），tag 与 `app/ui/pubspec.yaml` 的
versionName 保持一致。

---

## 数据层

| 目录 | 内容 |
| --- | --- |
| [`dataset/`](./dataset/) | 全量书籍目录唯一真源 248,338 本（只归并重复抓取行，不删书；15 字段），供种子使用，**不是分析口径** |
| [`analysis/`](./analysis/) | 可复现数据分析：22 份报告 + 88 张图，全部由生成器产出 |
| [`docs/`](./docs/) | 全局定义：SFACG 接口事实档案、自定义指标、体裁判定 |

**引用任何数字之前，先读 [`analysis/README.md`](./analysis/README.md) 的口径约束。**

### SFACG 接口事实档案（动手前必读）

任何涉及 SFACG 端点、参数、字段、状态码或抓取的工作，先读
[`docs/sfacg-endpoints.md`](./docs/sfacg-endpoints.md)（PC 端）与
[`docs/sfacg-app-api.md`](./docs/sfacg-app-api.md)（官方 App API），
不要凭印象猜 API——本项目已多次因猜测踩坑（搜索只认 `keyword`、
`novelbytype` 必须 POST + `Referer`、无效 nid 返回 200、HTML 搜索硬截 30 条等）。

### 快速开始（研究管线）

```bash
cd analysis
uv sync
uv run --extra archive python pipeline/prepare.py   # 首次：校验归档哈希并解压
uv run python pipeline/build_csv.py                 # 从 jsonl 重建 CSV / manifest
for f in generators/report_*.py; do uv run python "$f"; done   # 全部报告
```

---

## 核心发现（研究摘要）

以下六条出自 [报告 16：十年结构变迁](./analysis/reports/16_timeline.md)，
完整口径见 [`analysis/README.md`](./analysis/README.md)：

1. **供给是单峰，且「人」比「书」先见顶**：年供给 2022 年达峰 37,088 本，2025 年降至 14,552 本（−61%）；新作者数 2020 年已见顶。
2. **商业化是「门槛加深 + 天花板见顶」的剪刀差**：签约率中位 3.1% → 10.5%，月票总量 2020 年见顶后 −64%。
3. **注意力集中是结构常数，重心在迁移**：全书收藏 Gini ≈ 0.95，45% 的收藏落在 2020–2022 三个世代。
4. **口味转向是运营与自选择的合力**：魔幻份额下降、女性主角标签占比 9.1% → 36.1%，标签词表有断层，不能全读成需求侧变化。
5. **平台识别的是作者能力，不是单本爆款**：banner 授予、征文上榜优势、跟风书热度逐层对照后收敛到「筛选的是人」。
6. **图景有一面带盲区的镜子**：覆盖率约 69.3%，遗漏偏向「短、新、更新中」；全部绝对计数都是下界。

---

## 文档索引

| 文档 | 用途 |
| --- | --- |
| [`app/README.md`](./app/README.md) | 产品结构与文档索引（01–16） |
| [`app/docs/01-tech-stack.md`](./app/docs/01-tech-stack.md) | 技术栈与边界（无服务端/无账号/localhost only） |
| [`docs/README.md`](./docs/README.md) | 全局定义：接口事实、指标、体裁 |
| [`analysis/README.md`](./analysis/README.md) | 数据管线、报告清单、口径约束 |
| [`analysis/reports/`](./analysis/reports/) | 22 份报告正文与图表 |

`temp/` 下是参考项目的本地镜像（[sfacg_tools](https://github.com/light-nook-labs/sfacg_tools)、
[novly](https://github.com/light-nook-labs/novly)、[go-music-dl](https://github.com/guohuiyuan/go-music-dl)），
不进版本库；`archive/`（早期实测档案）已删除，其未失效结论已并入各当前文档。

---

## 数据来源与致谢

数据来自 SF 轻小说（菠萝包轻小说）的公开页面与 API，仅用于个人研究与书目分析，
不含任何正文内容。上游原始快照与凭据均不入库。

## 许可

本项目以 **GNU Affero 通用公共许可证第 3 版（AGPL-3.0）** 授权，
Copyright (C) 2026 interset-wq，许可证全文见 [`LICENSE`](./LICENSE)。
分析文字与图表版权归作者所有。

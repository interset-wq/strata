# 详情页 fixture

三态各一份真实服务端响应，原样保存、不加工。抓取方式与生产一致（移动版 HTML，
`User-Agent: Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Mobile Safari/537.36`），
串行间隔 ≥0.5 s。用 `detail_fixture_test.go` 校验。

| 文件 | URL | 抓取时间 | 期望状态 | 特征 |
|------|-----|----------|----------|------|
| `alive_48704.html` | `https://m.sfacg.com/b/48704/` | 2026-11-17 | alive | 有目录入口、收藏/赞/字数均为正 |
| `dead_73900.html` | `https://m.sfacg.com/b/73900/` | 2026-11-18 | dead | 3.6 KB，正文仅「出错啦」，无 `book_Catalog` |
| `zombie_4733.html` | `https://m.sfacg.com/b/4733/` | 2026-11-18 | zombie | 有书目详情与下架声明，`book_Catalog` 内无 `<a>`，无「点击阅读」入口 |

`detail_test.go` 另有两个内联最小 HTML 用例，验证判据本身（空目录容器、负收藏）；
本目录的真实页验证判据在真实结构上的表现。两者互补，改判据时同步改两处。

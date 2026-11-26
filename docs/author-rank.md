# 作者榜口径（稳定产出的优质作者）

> **定位**：作者榜的唯一权威口径。生成器、App 入口、预览页以本文为准。
> **状态**：2026-11-25 定案，2026-11-26 同步 E.34 赛事池正向准入与 E.32 黑名单（口径见 `analysis/generators/author_rank.py`，预览为 `analysis/out/author_rank_preview.html`）。
> **口径**：所有计数、收藏和、排名均为快照现算值，随数据版本变化，仅供参考；禁止硬编码进代码。
> **目标**：选出**稳定产出的优质作者**，作为「同一作者的其他作品」次级入口，不取代书榜主排序。

---

## 1. 三条判断链

1. **稳定产出**：某 form 的有效作品 ≥ 3 本，否则作者不进该 form 榜。只有稳定产出的作者，其粉丝群体才有意义。
2. **受欢迎程度**：只看绝对数值——该 form 收藏最高的 3 本（代表作）收藏和；cqs/AQS 等校准分不参与。
3. **值得信赖**：代表作完结率作为折扣。三者共同决定「信赖加权分」，按 form 隔离排名。

---

## 2. 有效作品（关键：form 之外还要套收录资格）

`lib/forms.py::classify` 只回答**作品形态**（纯字数/征文/DOM/API 证据），不随 `status` 变。作者榜**必须另套种子层的收录资格规则**，否则连载中的短/中篇会混进榜。以下规则只作用 `short`/`medium`，其他形态不受影响：

- **E.31 弃书**：`status != 已完结` 的 short/medium 不构成有效中短篇（连载中意味着没写完）。等价于 `seed_policy.abandoned_ids`；作者榜不读 `waive="complete"` 白名单。
- **P10 假完结**：short/medium 且 `contest` 含「长篇」视为假完结，剔除。等价于 `seed_policy.fake_complete_ids`，确定性裁定、无豁免，见 `docs/fake-complete-short-medium.md`。
- **E.34 赛事池正向准入**：short/medium 的 nid 必须在 26 个中短篇赛事 roster union 内（`analysis/anchors/contest_short_medium.json`），等价于 `seed_policy.short_medium_outside_contest_ids`；唯一豁免是人工 `waive="contest"`（作者榜读该白名单，但不读 `waive="complete"`）。union 只决定入池资格、不决定形态（见 §2 末《少女与龙》例）。
- **E.32 人工黑名单**：`seed_manual_blacklist.jsonl` 逐本剔除，当前为空；作者榜与种子共用同一锚点。
- 因此在 short/medium 榜内，作品必然全部已完结且在赛事池内，**完结率恒 100%**，完结率折扣对这两个形态无区分度。
- E.25 Web 死链（7 本）只在种子层；作者榜未接入，属已知边界。

`invalid`（words<2000 / 点击天花板越线）由 `r24.load()` 在 form 层已剔除。

---

## 3. 排名分数

对每位作者、每个 form 独立计算（不跨形态合并）：

```
候选     = 该作者该 form 的有效作品（§2）
入榜门槛 = |候选| >= 3
代表作   = 候选中按 favs 降序的前 3 本
收藏和   = sum(代表作.favs)                      # 绝对数值，受欢迎程度
完结率   = count(代表作.status == 已完结) / 3     # 信赖
信赖加权分 = 收藏和 × (BASE_KEEP + (1 - BASE_KEEP) × 完结率)
```

- `BASE_KEEP = 0.4`（用户 2026-11-25 定案）：完结率 0 时仍保留 40% 收藏信号，不做全盘否决；完结率 1 不打折。这个值目前无外部依据，是防止「高收藏但全连载」直接登顶的保守折扣。
- long/dialogue/ip_collab 的完结率有区分度；short/medium 恒 1（§2）。
- 收藏和取最高 3 本、不取全量，避免写得多的作者靠数量堆高；3 本门槛保证不是偶然一本。

---

## 4. form 隔离与跨榜

- 每张榜只用一个 form 的作品计算，形态之间**不合并分数**。
- 同一作者若在多个 form 都有 ≥3 本有效作品，**同时出现在多张榜**，各榜名次独立。这是设计意图，不是重复。
- form 是作品级属性：作者榜不得把作者主形态传播到每本书；同人独立建架；签约/VIP 不做品质标签。

---

## 5. 身份键与边界

- 身份键：作者名 `casefold()`，**保留空格**（`kola`/`KOLA` 同人，`First Order`/`firstorder` 不同人）。
- 分析口径不含 `authorId`（数据集仅覆盖约 49.8% 权威 id，已知 11 组改名），马甲/共用笔名无法合并；正式版若要消歧需走裁定表。
- **接入 App 的硬约束**：引擎 `store.AuthorBooks` 用 `author = ?` 精确字符串匹配（`app/engine/internal/store/store.go:1449`），`casefold` 键不能直接当查询参数。落库只写**原始显示名**（用于 `/author?author=` 跳转）；`casefold` 只在构建期去重，不进表。
- App 只展示**作者名 + 一本代表作**（`rep_nid` / `rep_title`）；分析预览仍保留作品数/收藏/完结率/三本代表作等核对列，两者不混用。

---

## 6. 已知限制（必读）

1. `favs` 混书龄/曝光分母，累计值跨时点不可比；这里只用于作者榜相对排序，**禁回流书榜打分**。
2. `status` 是快照状态（跨时点生命态另看 `updated_at`）；中短篇假完结按 P10 剔除，其余作者自报完结仍可能有噪声。
3. 本榜不覆盖全库作者（只有 ≥3 本有效作品者入榜），是「稳定作者榜」，不是全量作者目录。
4. 数据上界 2026-05-03，定年范围 2007–2025；2026 为右删失样本，不进榜。

---

## 7. 复现

```
uv run --project analysis python analysis/generators/author_rank.py
```

输出 `analysis/out/author_rank_preview.html`（五张 form 榜预览，带「只看代表作全完结」开关）。生成器复用 `analysis/generators/report_24_runtime_metrics.py::load()` 的定年与 form，守门断言见 §8。`analysis/out/gen_author_rank_preview.py` 是指向正式生成器的薄壳，不维护独立口径。

---

## 8. 守门断言

正式生成器必须保证：

- short/medium 榜内每本书 `status == 已完结` 且 `contest` 不含「长篇」（零连载、零假完结）；
- short/medium 榜内每本书 nid 在赛事 union 或人工 `waive="contest"` 白名单内，且零人工黑名单书；
- 每榜每位作者的有效作品数 ≥ 3；
- 每榜按信赖加权分降序、top100；
- 若上述任一断言失败，生成中止并报错，不产出 HTML。

---

## 9. App 预构建表（最小字段）

用户裁定：**展示只需要作者名 + 一本代表作**。排名证据（top3 收藏和、完结率、有效作品数，以及另外两本代表作）只在构建期参与计算，不落库。表是 additive 预构建产物，随 `seed.db.gz` 一起产出；运行时零计算、不 join `books`、不进任何分位分母、不回流书榜打分。

```sql
CREATE TABLE author_ranks(
  form      TEXT    NOT NULL,  -- long/dialogue/medium/short/ip_collab
  rank_no   INTEGER NOT NULL,  -- form 内名次 1..100
  author    TEXT    NOT NULL,  -- 原始显示名；/author?author= 精确匹配
  rep_nid   INTEGER NOT NULL,  -- 代表作 nid（top3 中 favs 最高的一本）
  rep_title TEXT    NOT NULL,  -- 代表作标题，供列表渲染
  PRIMARY KEY(form, rank_no)
);
```

- **不存**：`author_key`、`n_books`、`fav_sum`、`fav_top`、`finished`、`finish_rate`、`score`、`year`、三本 `reps` JSON。它们是构建期字段，不是展示字段。
- `rep_nid` / `rep_title` 取该 form 代表作的第 1 本（favs 最高）；排名仍按 top3 收藏和 + 完结率折扣计算，展示只露一本。
- 若该 nid 不在 seed 的 16,047 本里（E.35 form 配额准入后），列表仍可显示标题，但点详情可能无本地数据；若要求点击必达，需在构建期把代表作限定在 seed 内，或另加封面/在线兜底（本轮不加，保持最小字段）。
- `seed_meta` 只追加 `author_rank_rows` / `author_rank_forms` / `author_rank_snapshot`，不记录构建期权重明细。
- 守门：每张榜 `rank_no` 从 1 连续、`author` 与 `rep_title` 非空、`rep_nid > 0`、总行数 ≤ 500；两份 asset（`app/assets/`、`app/ui/assets/`）字节一致，`schema_version` 升为 10。

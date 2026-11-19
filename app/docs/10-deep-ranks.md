# APP 设计文档 10：全库世代内 Top200 深榜（D2）

> **文档状态**：D2 实施记录（2026-11-17）。上游决策见 `09-seed-refresh-proposal.md`
> 附录 A；分析依据见 `analysis/reports/21_deep_ranks.md`。
> **本文不修改 01–08**：种子书单仍 30,878 本、`books` 仍 24 列、分位分母仍是
> 241,758 行统计宇宙；报告 10 与 `lib/eras.py` 定年体系一字未动。
> **数据源**：`out/novels.csv` + 281 锚点定年的本地快照，内容上界 2026-05-03。
> 构建与查询全离线，无网络请求。

---

## 0. 为什么要新增这张表

引擎的 `/rankings/favs` 早已允许 `limit=200`，但它查的是**精选种子池**。
种子池在早期世代只有个位数到几十本，放宽 limit 不会补出书：

| 世代 | 种子内本数 | 深榜实际深度 | 命中率（收藏榜） |
| --- | --- | --- | --- |
| 2007 | 7 | 76 | 9.2% |
| 2008 | 6 | 200 | 3.0% |
| 2013 | 63 | 200 | 31.5% |
| 2015 | 189 | 200 | 94.5% |
| 2016–2025 | ≥200 | 200 | 100% |

四指标合计 14,626 个榜位，种子池只命中 7,534（51.5%）。因此深榜必须建在
**全库统计宇宙**上；但把 4,553 本补进种子会改变候选池、分位语义与既有文档，
代价远大于收益。D2 选择**追加一张只读表**：既不碰种子书单，也不碰分位分母。

---

## 1. 数据契约

### 1.1 `deep_ranks` 表（schema_version 2 新增）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| `est_year` | INTEGER | 世代分组键，`2007..2025` |
| `metric` | TEXT | `favs` / `clicks` / `praises` / `pr`，四选一 |
| `rank_no` | INTEGER | 组内名次，从 1 连续递增 |
| `nid` | INTEGER | SFACG 稳定 id；**可以不在 `books` 里**（这正是深榜的意义） |
| `title` / `author` / `genre` | TEXT | 展示字段，构建期冗余存储，避免必须 join `books` |
| `value` | REAL | 指标原值；`pr` 为 `praises/favs` |
| `pctl` | REAL | 该指标在全库同世代内的分位（构建期已算好） |
| `cover_url` | TEXT | 封面；允许 NULL |

主键 `(est_year, metric, rank_no)`，另加 `UNIQUE(est_year, metric, nid)`（同一本书在
同一榜单至多占一位），附加索引 `idx_deep_lookup(metric, est_year, rank_no)`。
**只读、追加、不参与任何分位计算、不作为搜索或详情的数据源。**

### 1.2 榜单口径

- 分组：`est_year` 逐年独立成榜，**不提供跨世代合并榜**。
- 深度：`min(200, 合格书目数)`。2007 世代全库仅 76 本；`pr` 另受 `favs ≥ 10` 限制
  （2007 世代只有 32 本合格）。**不补凑数条目**，端上必须显示真实深度 `M`。
- 排序：`value` 降序，同值按 `nid` 升序（可复现）。
- 参照系：全库统计宇宙（241,758 行，已剔除 47 本正版日轻），**不是种子池**。
- 规模：`14,626` 行 / 76 张榜；落库后 seed.db 16.02 → 17.99 MB，
  gzip 6.67 → **7.45 MB**（+0.78 MB）。

计算逻辑与报告 21 共用 `app/tools/seedbuild/deep_ranks.py`，避免两处口径漂移。

---

## 2. 查询接口

```
GET /strata/rankings/deep?year=<2007..2025>&metric=<favs|clicks|praises|pr>&limit=<1..200>
```

`year`、`metric` 必填；`limit` 省略时默认 50，上限 200（沿用 `parseLimit`）。

```json
{
  "meta": {
    "kind": "deep", "pool": "universe", "ordering": "favs",
    "content_end": "2026-05-03", "year": 2010, "metric": "favs",
    "limit": 5, "depth": 200, "licensed_excluded": true
  },
  "items": [
    {"rank": 1, "nid": 11383, "title": "妹妹大人魔女Sama",
     "author": "…", "genre": "…", "est_year": 2010,
     "value": 17677.0, "pctl": 1.0}
  ]
}
```

- `depth` 是**整张榜的实际长度**，不是本次返回条数；UI 应显示「第 1–N 名 / 共 M 名」。
- 命中 `nid` 不在 `books` 里时，走搜索/详情兜底（与 `discovered` 表同一路径），
  不得因为不在种子里就过滤掉。
- 错误：年份越界、未知 metric、limit 越界统一返回 `400 invalid_argument`。

---

## 3. 展示红线（继承 03 文档）

1. **分位不是排名**：同世代冠军分位均为 1.0，但绝对收藏可差一个量级；
   原值与分位必须同屏，禁止跨世代加总或平均。
2. **点击榜须标注累计口径**：受书龄与曝光分母混杂（报告 08），不等于曝光分档转化率；
   不做跨书点击涨幅。
3. **赞藏比门槛**：`favs < 10` 不入 `pr` 榜；短篇禁用比率类指标（报告 19），
   本榜不替代短篇榜。
4. **A/B/C 分区**：D2 属 A 类离线榜，与在线官方榜（B）、本机观测榜（C）分区展示。
5. **快照态**：`status` 是 2026-05-03 的快照，非当期状态；`updated_at` 只作时长。
6. **新鲜度**：内容上界之后的新书不在榜内；维持新鲜需按既定增强通路重采，
   本设计不引入任何自动抓取。

---

## 4. 构建与验证

```bash
# 重建种子资产（含 deep_ranks）
cd analysis
uv run python ../app/tools/seedbuild/build_seed.py

# 分析侧报告与配图
uv run python generators/report_21_deep_ranks.py

# 引擎测试
cd ../app/engine && go test ./...
```

`validate.py` 的断言：`books=30,878`、正版 47、`deep_ranks=14,626`、
四指标齐全、`rank_no` 连续、`pctl∈(0,1]`、`pr` 榜满足 `favs≥10`、
`seed_meta.deep_rank_rows` 一致。实测 `go test ./...` 全绿。

---

## 5. 明确不做

- **不改种子书单**：不把 4,553 本深榜书并入 `books`；那会改变候选池与既有分位语义。
- **不改报告 10 / 定年**：世代仍由 `log(nid)` 给出，`addTime` 不进定年。
- **不做全库绝对榜**：绝对数系统性屏蔽早期世代（03 §2）。
- **不做历史月榜扩展**：`MonthlyBoy.ashx` 数据源 ceiling 就是 top20（D3 做不到）。
- **不引入网络请求**：D2 是纯离线构建产物。

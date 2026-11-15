# 轻后端：收观测，不发内容（**P2 蓝图，v1 不实现**）

> **状态：不是第一期的工作。** 第一版是纯静态架构——种子走 GitHub Release，端上按需抓详情，
> 没有任何服务端。这份文件写的是**第三期**的样子，留着的原因是：
> 设计它的过程反过来约束了 v1 的数据结构（见 `architecture.md` §6.5「v1 就要埋的四个伏笔」）。
> 在 §7 的进入条件满足之前，不要写这个后端，也不要写上报模块。

一个 FastAPI 应用 + 一个 Postgres。只做两件事：**收端上的书籍观测**、**给构建流水线导出**。
没有用户系统、没有推送、没有内容分发——种子还是走 GitHub Release 静态文件。

---

## 1. 边界（先划清楚）

| 收 | 不收 |
| --- | --- |
| 书籍 id + 公开可爬的成绩字段（人气/收藏/赞/月票/评分/字数） | 用户 id、手机号、邮箱、任何登录态 |
| 观测时间 | 书架、阅读进度、搜索词 |
| 匿名 `client_id`（随机 UUID，首次启动生成） | 设备指纹、IMEI、IP 落库 |

**为什么可以不收用户数据**：要的东西本来就是公开网页上人人可见的数字，
匿名化上报只是"帮我少爬几次"，不是"拿用户画像换服务"。
`search_log` 和 `shelf` **永远留在设备上**——那才是真正有价值且真正敏感的东西。

---

## 2. 数据模型（Postgres）

只存**聚合结果**，不存流水。一本书一行。

```sql
CREATE TABLE book_obs (
  book_id     BIGINT PRIMARY KEY,
  payload     JSONB       NOT NULL,   -- {"view_num":1053211,"mark_num":196097,...}
  observed_at TIMESTAMPTZ NOT NULL,   -- 这个 payload 的观测时刻（端上报的）
  reports     INT         NOT NULL DEFAULT 1,  -- 累计上报次数
  clients     INT         NOT NULL DEFAULT 1,  -- 独立客户端数
  suspect     BOOLEAN     NOT NULL DEFAULT FALSE, -- 触发离群规则，不参与导出
  first_seen  TIMESTAMPTZ NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_obs_export ON book_obs(updated_at) WHERE NOT suspect;
```

容量：全站 24 万本上限 × ~300 B ≈ **72 MB**，加索引约 100 MB。
Neon 免费档 0.5 GB，留了 5 倍余量。

**为什么不留流水**：流水是无界的（100 个用户 × 每天 10 本 = 每天 1000 行 = 每月 9 MB，
一年 100 MB 且只增不减）。而我们要的只是"这本书现在多少"，一本书一个最新值就够。

---

## 3. 接口

### 3.1 上报

```http
POST /v1/observations
X-Client-Id: <uuid>          # 匿名，首次启动生成，存 local_meta
Content-Type: application/json

{
  "app_version": "0.1.0",
  "observations": [
    {"book_id": 121065, "payload": {"view_num":1053211,"mark_num":196097}, "observed_at": 1763200000},
    ...
  ]
}
```

- 批量上限 **200 条**，超出 413。
- 幂等：同一 `(book_id, X-Client-Id, client_seq)` 重复提交不重复计数。
  端上每次上报带一个单调递增的 `client_seq`，重试时复用。
- 返回：`{"accepted": 198, "rejected": 2, "reasons": {"outlier": 2}}`

### 3.2 导出（给 GitHub Actions）

```http
GET /v1/export?since=<iso8601>&token=<deploy_token>
→ NDJSON，一行一本书
{"book_id":121065,"payload":{...},"observed_at":"2026-11-15T09:12:00Z","clients":3}
```

- `since` 用 `updated_at` 过滤，增量拉取。
- `token` 是长期部署令牌（不是用户 token），只读，可轮换。
- `suspect = true` 的行不导出。

### 3.3 健康检查

`GET /healthz` → `{"ok":true,"rows":183204}`

---

## 4. 聚合策略（比接口更重要）

成绩字段绝大多数是**累计值**，只能增不能减。这条性质就是最便宜的质量校验。

收到一条观测时：

| 条件 | 动作 |
| --- | --- |
| 新 `observed_at` <= 已存的 | 丢弃（旧观测，可能是端上重放） |
| 差值在 `[0.9×, 10×]` 之间 | 覆盖 `payload`，`reports += 1` |
| 新值 < 0.9 × 旧值 | **拒绝**：累计值不该倒退（除非站方清数据），标记 `suspect` |
| 新值 > 10 × 旧值 | 先不覆盖，`suspect=true`；等 `clients >= 3` 再解除 |
| `point`（评分） | 例外：本来就是均值，允许双向小幅波动 |

**不做实时中位数**——那需要存多个样本，容量翻几十倍，收益只是抗单点脏数据，
而单点脏数据已经被上面的范围检查拦住了大半。

`suspect=true` 不导出、不进种子，但在后台保留，人工看一眼就能判断是真涨还是解析错。

---

## 5. 与种子构建的衔接

collector 生成 `seed.db` 时多一步：

```
① 采集闭包 19,791 本 → 基线 catalog（P0 是 stats_src='upstream'，P1 之后是 'own'）
② GET /v1/export?since=<上次构建时间>
③ 对每条观测：
     observed_at > 基线 stats_at  → 覆盖字段（stats_src 保持 'own'）
     否则                          → 跳过（采集的更新）
④ 导出 seed.sqlite.gz → GitHub Release
```

`stats_src` 只有 `own` / `upstream` 两值，含义是「这组数字是谁提供的」：
只要不是第三方快照就算 `own`——**爬虫采的和用户端报的都算 own**，
它们都是我们自己的来源，只是通道不同。想区分通道看 `user_patch.src`（detail / search），
不要给 `catalog` 再造第三、第四个枚举值：列一多，判定就开始漂。

效果：**新用户装上就带着"最近有人看过"的数据**，而不是一律躺在采集日那天。
对 6 月后上架、上游快照里压根没有的书，这一步是唯一的来源。

---

## 6. 部署

```bash
uv run fastapi deploy     # FastAPI Cloud，目前免费
```

FastAPI Cloud 本身不提供存储，数据库外接 **Neon（免费 0.5 GB）**，
连接串走环境变量。每日自动备份由 Neon 负责。

如果要换宿主（Render / Fly / Railway），代码不用改——只有一个 `DATABASE_URL` 和一个
`DEPLOY_TOKEN` 的差异。这是刻意的：后端要小到"一晚上能重写一遍"。

---

## 7. 什么时候才该开始写这个后端

原来是「什么时候该砍」，现在改成「什么时候才配写」——因为默认状态是**不写**。
下面四条**全部**成立才动手，任何一条不成立就继续用静态方案：

| # | 条件 | 依据 | 不满足时怎么替代 |
| --- | --- | --- | --- |
| 1 | 自己的爬虫已稳定 ≥ 4 周 | 后端收的观测要进种子构建才有用；爬虫不稳，构建流程本身就在变 | 先修爬虫 |
| 2 | 种子更新周期 > 2 周 | 若已经 ≤ 2 周，用户观测带来的新鲜度增益可以忽略 | 缩短构建周期 |
| 3 | 端上 `user_patch` 的**闭包外占比 > 5%** | 这是唯一能证明「用户看到了我采不到的书」的证据（SQL 见 `architecture.md` §6.5） | 扩大采集闭包 |
| 4 | 日活足以产生 ≥ 50 条/天的新观测 | 否则手动跑一次采集更省事，后端纯属运维负担 | 手动采集 |

第 3 条是关键：它把「要不要建后端」从一个**架构品味问题**变成**一个可以查的数**。
v1 不需要后端就能算出它——因为 `user_patch` 本来就在本地记着每一本被点开的书。

还有一条真风险要提前说清楚：**用户端抓详情 = 分布式爬虫**，请求量随用户数线性增长，
而站方看到的是同一个 App 的 Basic 认证串。所以端上抓取必须限速（每设备 1 次/秒、
每日上限 N 次），并且**详情缓存 TTL 14 天**内不重复抓——这不是性能优化，是生存问题。
**这条约束在 v1 就生效，与有没有后端无关**；后端上了之后只是多了个能远程调参的地方。

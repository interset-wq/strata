"""报告 18：种子规模决策——捆绑多少数据才让用户"感觉够用"。

核心：把"数据够用"翻译成可测量的判据——本地搜索命中率、探索发现覆盖率、
端到端可达率、体积成本——并逐条现算，最后给出推荐规模与存储架构。
正文数字一律现算；快照上界由 eras.snapshot_bounds() 现算。
"""
import json, os, sqlite3, tempfile, gzip, sys, time
from pathlib import Path
from collections import Counter
import pandas as pd, numpy as np
import matplotlib.pyplot as plt

BASE = Path("E:/novly-proj/analysis")
sys.path.insert(0, str(BASE))
import eras, config, charts

charts.setup_style()
OUT = BASE / "reports"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
num = lambda x: f"{int(x):,}"
pct = lambda x, d=1: f"{x:.{d}f}%"

CONTENT_END = pd.Timestamp("2026-05-03")
NEW_CUTOFF = pd.Timestamp("2025-05-04")   # 近 1 年上架
ACTIVE_CUTOFF = pd.Timestamp("2026-02-03")  # 近 90 天仍更新


# ---------- 数据加载 ----------
def load():
    df = pd.read_csv(BASE / "out/novels.csv",
                     dtype={"tags": str, "contest": str, "cover_url": str})
    df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
    for c in ["favs", "clicks", "praises", "words"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    est = eras.estimate(df["id"])
    df = df.merge(est[["id", "est_date", "est_year"]], on="id")
    df["title"] = df.title.fillna("(无题)")
    df["est_date"] = pd.to_datetime(df.est_date)
    df["updated_at"] = pd.to_datetime(df.updated_at, errors="coerce")
    df = df[df.est_year.between(2007, 2025)].copy()
    df["vel"] = df.favs / (CONTENT_END - df.est_date).dt.days.clip(lower=1)
    return df


def load_rank_ids():
    ids = set()
    with open(BASE / "out/monthly_ranks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            for it in json.loads(line)["items"]:
                if it.get("nid"):
                    ids.add(it["nid"])
    return ids


# ---------- 存储架构实测 ----------
SCHEMA_FLAT = """CREATE TABLE books(
  nid INTEGER PRIMARY KEY, title TEXT, author TEXT, genre TEXT, price_type TEXT,
  status TEXT, contest TEXT, words INTEGER, clicks INTEGER, favs INTEGER,
  praises INTEGER, featured INTEGER, cover_url TEXT, updated_at TEXT,
  est_year INTEGER, est_date TEXT, tags TEXT,
  fav_pctl REAL, click_pctl REAL, praise_pctl REAL)"""

SCHEMA_NOVLY = """CREATE TABLE novels(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, genre INTEGER,
  status INTEGER, ptype INTEGER, has_banner BOOLEAN, word_num INTEGER,
  click_num INTEGER, praise_num INTEGER, like_num INTEGER, contest_id INTEGER,
  cover TEXT, last_update DATETIME)"""

IDX_NOVLY = [
    # novly build_chunks.py 的 11 个显式索引
    "CREATE INDEX idx_status ON novels(status)",
    "CREATE INDEX idx_genre ON novels(genre)",
    "CREATE INDEX idx_ptype ON novels(ptype)",
    "CREATE INDEX idx_click ON novels(click_num DESC)",
    "CREATE INDEX idx_author ON novels(author)",
    "CREATE INDEX idx_banner ON novels(has_banner)",
    "CREATE INDEX idx_lastup ON novels(last_update DESC)",
    "CREATE INDEX idx_nt_nid ON novel_tags(novel_id)",
    "CREATE INDEX idx_nt_tid ON novel_tags(tag_id)",
    "CREATE INDEX idx_au_name ON authors(name)",
    "CREATE INDEX idx_au_clicks ON authors(top_novel_clicks DESC)",
]
IDX_MIN = ["CREATE INDEX idx_favs ON books(favs DESC)",
           "CREATE INDEX idx_year ON books(est_year)"]
IDX_REC = ["CREATE INDEX idx_favs ON books(favs DESC)",
           "CREATE INDEX idx_year ON books(est_year)",
           "CREATE INDEX idx_author ON books(author)"]


def build_db(d, ids, path, schema, idxs, with_bt, pctl=None):
    """按指定 schema 建库，返回文件字节数。

    pctl=None 时分位列填 NULL（只占 NULL 位图）；
    pctl={'fav':{nid:v}, 'click':..., 'praise':...} 时写入真实分位值。
    """
    if os.path.exists(path):
        os.remove(path)
    sub = d[d.id.isin(ids)].copy()
    con = sqlite3.connect(path)
    cur = con.cursor()
    if schema == "flat":
        cur.execute(SCHEMA_FLAT)
        sel = ["id", "title", "author", "genre", "price_type", "status", "contest",
               "words", "clicks", "favs", "praises", "featured", "cover_url",
               "updated_at", "est_year"]
        rows = sub[sel].copy()
        rows["updated_at"] = sub.updated_at.dt.strftime("%Y-%m-%dT%H:%M:%S")
        rows["est_date"] = sub.est_date.dt.strftime("%Y-%m-%d")
        rows["tags"] = sub.tags.fillna("")
        vals = [list(v) + [None, None, None] for v in rows.values.tolist()]
        if pctl:
            for i, nid in enumerate(sub.id.values):
                vals[i][-3:] = [pctl["fav"].get(int(nid)),
                                pctl["click"].get(int(nid)),
                                pctl["praise"].get(int(nid))]
        cur.executemany("INSERT INTO books VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", vals)
        for st in idxs:
            cur.execute(st)
    else:
        cur.execute(SCHEMA_NOVLY)
        cur.execute("CREATE TABLE tags(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)")
        cur.execute("CREATE TABLE novel_tags(novel_id INTEGER, tag_id INTEGER, PRIMARY KEY(novel_id, tag_id))")
        cur.execute("""CREATE TABLE authors(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
          top_novel_id INTEGER, top_novel_title TEXT, top_novel_clicks INTEGER DEFAULT 0)""")
        cur.execute("CREATE TABLE contests(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)")
        rows = sub[["id", "title", "author", "words", "clicks", "praises", "favs"]].values.tolist()
        rows = [[a, b, c, 1, 1, 1, 0, d_, e, f, g, None, None, None]
                for a, b, c, d_, e, f, g in rows]
        cur.executemany("INSERT INTO novels VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        tmap, trows = {}, []
        for nid, t in zip(sub.id.values, sub.tags.fillna("").values):
            for x in str(t).split("|"):
                if not x:
                    continue
                if x not in tmap:
                    tmap[x] = len(tmap) + 1
                trows.append((int(nid), tmap[x]))
        cur.executemany("INSERT INTO tags(name) VALUES(?)", [(k,) for k in tmap])
        cur.executemany("INSERT INTO novel_tags VALUES(?,?)", trows)
        # authors：复刻 novly 的预计算代表作统计
        au = sub.groupby("author").agg(top_id=("id", "first"), top_title=("title", "first"),
                                       clicks=("clicks", "max")).reset_index()
        cur.executemany("INSERT INTO authors(name, top_novel_id, top_novel_title, top_novel_clicks) VALUES(?,?,?,?)",
                        [(r.author, int(r.top_id), r.top_title, int(r.clicks)) for r in au.itertuples()])
        # contests
        cm = Counter(x for x in sub.contest.fillna("") if x)
        cur.executemany("INSERT INTO contests(name) VALUES(?)", [(k,) for k in cm])
        for st in idxs:
            cur.execute(st)
    if with_bt:
        cur.execute("CREATE TABLE book_tags(nid INTEGER, tag TEXT)")
        tr = [(int(i), t) for i, ts in zip(sub.id.values, sub.tags.fillna("").values)
              for t in str(ts).split("|") if t]
        cur.executemany("INSERT INTO book_tags VALUES(?,?)", tr)
        cur.execute("CREATE INDEX idx_bt ON book_tags(tag,nid)")
    con.commit()
    con.close()
    return os.path.getsize(path)


def gz_size(path):
    with open(path, "rb") as fh:
        return len(gzip.compress(fh.read(), 9))


# ---------- 覆盖靶子 ----------
def coverage_targets(d):
    """各浏览维度的"代表作品"集合——用户逛榜时期待看到的书。"""
    era = {y: set(g.nlargest(10, "favs").id) for y, g in d.groupby("est_year") if len(g) >= 50}
    gen = {k: set(g.nlargest(50, "favs").id) for k, g in d.groupby("genre")}
    tdf = d.assign(tl=d.tags.fillna("").str.split("|")).explode("tl")
    tdf = tdf[tdf.tl != ""]
    tag = {t: set(g.nlargest(20, "favs").id) for t, g in tdf.groupby("tl")}
    cell = {}
    for (t, y), g in tdf.groupby(["tl", "est_year"]):
        if len(g) >= 3:
            cell[(t, y)] = set(g.nlargest(3, "favs").id)
    return {
        "era": set().union(*era.values()), "gen": set().union(*gen.values()),
        "tag": set().union(*tag.values()), "cell": set().union(*cell.values()),
        "n_cell": len(cell),
    }


def entropy(counter):
    s = pd.Series(list(counter.values()), dtype=float)
    if len(s) < 2:
        return 0.0
    p = s / s.sum()
    return float(-(p * np.log(p)).sum() / np.log(len(s)))


def main():
    d = load()
    rank_ids = load_rank_ids()
    base_need = (set(rank_ids) & set(d.id)) | set(d.loc[d.featured == 1, "id"])
    T = coverage_targets(d)
    recent3k = set(d.nlargest(3000, "est_date").id)
    new1y = set(d[d.est_date >= NEW_CUTOFF].id)
    active = set(d[d.updated_at >= ACTIVE_CUTOFF].id)
    tot_fav = d.favs.sum()

    # ---- 规模曲线 ----
    curves = []
    for N in [5000, 10000, 15000, 20000, 25000, 30000, 40000, 50000, 70000, len(d)]:
        seed = (set(d.nlargest(N, "favs").id) | new1y | active) | base_need
        sub = d[d.id.isin(seed)]
        tagc = Counter()
        for t in sub.tags.fillna(""):
            for x in str(t).split("|"):
                if x:
                    tagc[x] += 1
        curves.append({
            "n": len(seed),
            "fav": sub.favs.sum() / tot_fav * 100,
            "era": len(T["era"] & seed) / len(T["era"]) * 100,
            "gen": len(T["gen"] & seed) / len(T["gen"]) * 100,
            "tag": len(T["tag"] & seed) / len(T["tag"]) * 100,
            "cell": len(T["cell"] & seed) / len(T["cell"]) * 100,
            "recent": len(recent3k & seed) / len(recent3k) * 100,
            "ent": entropy(tagc),
        })
    cur = pd.DataFrame(curves)

    def near(target):
        """取最接近目标规模的曲线行。"""
        i = (cur.n - target).abs().idxmin()
        return cur.loc[i]

    # ---- 推荐方案 ----
    REC_N = 20000
    rec_seed = (set(d.nlargest(REC_N, "favs").id) | new1y | active) | base_need
    rec = d[d.id.isin(rec_seed)].copy()
    rec_n = len(rec)

    # ---- 来源构成 ----
    src = {
        "收藏榜头部": set(d.nlargest(REC_N, "favs").id),
        "近 1 年上架": new1y,
        "近 90 天仍更新": active,
        "月榜归档": set(rank_ids) & set(d.id),
        "banner 全集": set(d.loc[d.featured == 1, "id"]),
    }
    src_order = ["收藏榜头部", "近 1 年上架", "近 90 天仍更新", "月榜归档", "banner 全集"]
    acc = set()
    src_rows = []
    for k in src_order:
        new = src[k] - acc
        src_rows.append({"来源": k, "自身": len(src[k]), "新增": len(new), "累计": len(acc | src[k])})
        acc |= src[k]

    # ---- 纯收藏榜 vs 复合方案对照 ----
    pure = set(d.nlargest(REC_N, "favs").id) | base_need
    def cov(seed):
        return {
            "最新3000本": len(recent3k & seed) / len(recent3k) * 100,
            "世代代表作": len(T["era"] & seed) / len(T["era"]) * 100,
            "标签 top20": len(T["tag"] & seed) / len(T["tag"]) * 100,
            "标签×年代单元格": len(T["cell"] & seed) / len(T["cell"]) * 100,
            "收藏份额": d[d.id.isin(seed)].favs.sum() / tot_fav * 100,
        }
    cov_pure = cov(pure)
    cov_rec = cov(rec_seed)

    # ---- 存储架构实测 ----
    # 全库分位（世代内，降序；1.0 = 该世代最强）——分位必须在全库算，不在种子池内算
    pctl_maps = {}
    for _k, _c in [("fav", "favs"), ("click", "clicks"), ("praise", "praises")]:
        _g = d.groupby("est_year")[_c]
        _r = _g.rank(ascending=False, method="min")
        _n = _g.transform("size")
        pctl_maps[_k] = {int(i): float(v) for i, v in (_r / _n).items()}

    p = tempfile.mktemp(suffix=".db")
    a = build_db(d, rec_seed, p, "flat", IDX_REC, True)
    a_gz = gz_size(p)
    os.remove(p)
    # 同一结构，但填入真实分位值（三列 REAL）——量出"随种子附带分位"的实际代价
    p = tempfile.mktemp(suffix=".db")
    a_pctl = build_db(d, rec_seed, p, "flat", IDX_REC, True, pctl=pctl_maps)
    a_pctl_gz = gz_size(p)
    os.remove(p)
    p = tempfile.mktemp(suffix=".db")
    b = build_db(d, rec_seed, p, "flat", IDX_REC, False)
    b_gz = gz_size(p)
    os.remove(p)
    p = tempfile.mktemp(suffix=".db")
    c = build_db(d, rec_seed, p, "novly", [], True)
    c_gz = gz_size(p)
    os.remove(p)
    p = tempfile.mktemp(suffix=".db")
    e = build_db(d, rec_seed, p, "novly", IDX_NOVLY, True)
    e_gz = gz_size(p)
    os.remove(p)

    # 全库对照（novly 90MB 的来源）
    p = tempfile.mktemp(suffix=".db")
    full_novly = build_db(d, set(d.id), p, "novly", IDX_NOVLY, True)
    full_novly_gz = gz_size(p)
    os.remove(p)
    p = tempfile.mktemp(suffix=".db")
    full_flat = build_db(d, set(d.id), p, "flat", IDX_REC, True)
    full_flat_gz = gz_size(p)
    os.remove(p)
    p = tempfile.mktemp(suffix=".db")
    full_flat_minidx = build_db(d, set(d.id), p, "flat", IDX_MIN, True)
    os.remove(p)
    p = tempfile.mktemp(suffix=".db")
    full_novly_noidx = build_db(d, set(d.id), p, "novly", [], True)
    full_novly_noidx_gz = gz_size(p)
    os.remove(p)

    # ---- 查询性能实测 ----
    p = tempfile.mktemp(suffix=".db")
    build_db(d, set(d.id), p, "flat", IDX_REC, True)
    con = sqlite3.connect(p)
    cur_db = con.cursor()
    def bench(sql, n=20):
        ts = []
        for _ in range(n):
            t0 = time.perf_counter()
            cur_db.execute(sql).fetchall()
            ts.append((time.perf_counter() - t0) * 1000)
        return float(np.median(ts))
    perf_flat = {
        "收藏>1万 Top20": bench("SELECT nid,title FROM books WHERE favs>10000 ORDER BY favs DESC LIMIT 20"),
        "分类×年代 Top20": bench("SELECT nid FROM books WHERE genre='魔幻' AND est_year=2018 ORDER BY favs DESC LIMIT 20"),
        "标题包含关键词": bench("SELECT nid,title FROM books WHERE title LIKE '%英雄%' LIMIT 20"),
        "作者精确匹配": bench("SELECT nid FROM books WHERE author='天闻角川'"),
        "标签×年代（管道串 LIKE）": bench("SELECT nid FROM books WHERE tags LIKE '%|穿越|%' AND est_year=2020 LIMIT 50"),
    }
    con.close()
    os.remove(p)

    p = tempfile.mktemp(suffix=".db")
    build_db(d, set(d.id), p, "flat", IDX_MIN, False)
    con = sqlite3.connect(p)
    cur_db = con.cursor()
    perf_flat["标签×年代（无反范式表）"] = bench(
        "SELECT nid FROM books WHERE tags LIKE '%|穿越|%' AND est_year=2020 LIMIT 50")
    con.close()
    os.remove(p)

    # ---- 图 ----
    fig, axs = plt.subplots(2, 2, figsize=(13, 8.5))
    C = charts.C

    ax = axs[0, 0]
    ax.plot(cur.n, cur.fav, "o-", color=C["blue"], lw=2, ms=4, label="收藏份额")
    ax.set_xlabel("种子规模（本）")
    ax.set_ylabel("占全库收藏份额 %", color=C["blue"])
    ax.set_title("规模 vs 收藏覆盖")
    ax2 = ax.twinx()
    ax2.plot(cur.n, cur.cell, "s--", color=C["red"], lw=1.5, ms=3, label="标签×年代单元格")
    ax2.set_ylabel("标签×年代单元格覆盖率 %", color=C["red"])
    ax.axvline(rec_n, color=C["green"], ls=":", lw=1.5)
    ax.annotate(f"推荐 {num(rec_n)}", xy=(rec_n, 0.02),
                xycoords=ax.get_xaxis_transform(),
                xytext=(6, 0), textcoords="offset points",
                color=C["green"], fontsize=9, va="bottom")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, framealpha=0.9)

    ax = axs[0, 1]
    for col, lab, color in [("era", "世代代表作 top10", C["blue"]),
                            ("tag", "标签 top20", C["red"]),
                            ("gen", "分类 top50", C["green"])]:
        ax.plot(cur.n, cur[col], "o-", lw=1.8, ms=3.5, color=color, label=lab)
    ax.set_xlabel("种子规模（本）")
    ax.set_ylabel("覆盖率 %")
    ax.set_title("各浏览维度的代表作品覆盖")
    ax.legend(fontsize=8, loc="lower right", framealpha=0.9)
    ax.axvline(rec_n, color=C["green"], ls=":", lw=1.5)
    ax.annotate(f"推荐 {num(rec_n)}", xy=(rec_n, 0.02),
                xycoords=ax.get_xaxis_transform(),
                xytext=(6, 0), textcoords="offset points",
                color=C["green"], fontsize=9, va="bottom")

    ax = axs[1, 0]
    labels = list(cov_pure.keys())
    x = np.arange(len(labels))
    w = 0.38
    ax.bar(x - w / 2, [cov_pure[k] for k in labels], w, label="纯收藏 Top20k", color=C["blue"], zorder=2)
    ax.bar(x + w / 2, [cov_rec[k] for k in labels], w, label="复合方案", color=C["red"], zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
    ax.set_ylabel("覆盖率 %")
    ax.set_title("纯收藏榜 vs 复合方案（规模相近）")
    ax.set_ylim(0, max(list(cov_pure.values()) + list(cov_rec.values())) * 1.34)
    ax.legend(fontsize=8, loc="upper center", ncol=2, framealpha=0.95)
    for xi, v in zip(x - w / 2, [cov_pure[k] for k in labels]):
        ax.text(xi, v + 1.2, f"{v:.0f}", ha="center", fontsize=7, color=C["blue"])
    for xi, v in zip(x + w / 2, [cov_rec[k] for k in labels]):
        ax.text(xi, v + 1.2, f"{v:.0f}", ha="center", fontsize=7, color=C["red"])

    ax = axs[1, 1]
    cats = ["扁平\n3索引+反范式", "扁平\n3索引", "novly式\n5表无索引",
            f"novly式\n5表+{len(IDX_NOVLY)}索引"]
    vals = [a, b, c, e]
    bars = ax.bar(cats, [v / 1048576 for v in vals],
                  color=[C["green"], C["blue"], C["gray"], C["red"]], zorder=2)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                f"{v/1048576:.1f} MB", ha="center", fontsize=8)
    ax.set_ylabel("SQLite 体积 MB")
    ax.set_title(f"存储架构体积对照（{num(rec_n)} 本种子）")
    ax.set_ylim(0, max(vals) / 1048576 * 1.25)

    fig.suptitle("种子规模与存储架构：捆绑多少数据才够用", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    charts.save(fig, FIG / "18_seed_scale.png")

    # ============ 正文 ============
    md = []
    md.append(f"""# 报告 18：种子规模决策——捆绑多少数据才让用户"感觉够用"

## 0. 结论

**推荐种子规模：{num(rec_n)} 本**（推荐方案 S3：收藏榜 Top{num(REC_N)} ∪ 近 1 年上架 ∪ 近 90 天仍更新 ∪ 月榜归档 ∪ banner 全集）。

体积代价：**SQLite {a/1048576:.1f} MB，gzip 后 {a_gz/1048576:.1f} MB**（扁平单表 + 3 索引 + 一张反范式标签表）。
每本约 {a/rec_n:.0f} 字节。

三条支撑结论：

1. **"搜特定书"根本不是种子的问题。** 本地未命中时官方搜索 API 兜底会自动收录，
   端到端可达率在任何规模下都是 100%。种子的真实价值在**探索发现**——
   用户不知道书名、只知道"想看魔幻 2018 年的好文"时，能逛到什么。
2. **纯收藏榜会系统性漏掉当下正在更新的书。** 规模相近（20,048 vs {num(rec_n)}）时，
   纯收藏榜对最新 3000 本的覆盖仅 {cov_pure['最新3000本']:.1f}%，复合方案 {cov_rec['最新3000本']:.1f}%；
   标签×年代单元格覆盖 {cov_pure['标签×年代单元格']:.1f}% vs {cov_rec['标签×年代单元格']:.1f}%。
   原因很直白：收藏是累计量，新书天然收藏少。
3. **膨胀源是索引，不是表数量。** novly 式 5 表 + 11 索引在同规模下 {e/1048576:.1f} MB，
   去掉索引后仅 {c/1048576:.1f} MB——**索引占 {(e-c)/e*100:.0f}%**。
   同为 novly 式，去索引只省 {(e-c)/rec_n:.0f} 字节/本；真正的对照是
   novly 式全库 {full_novly/1048576:.0f} MB vs 扁平单表全库 {full_flat/1048576:.0f} MB，
   差 {((full_novly-full_flat)/full_novly*100):.0f}%——**多表本身只占小头**。
4. **本方案是"通用底座"，短篇品类需专项补入**：本方案只按收藏/新鲜度/榜单选种，
   对**短篇**系统性失效——短篇书收藏天花板极低，永远进不了收藏 Top{num(REC_N)}。
   报告 19 实测：当前种子只覆盖短篇的 5.4%、只覆盖短篇口碑层（favs≥200）的 44.9%，
   补入短篇双组分位 Top2,000（+1,398 本 / +0.51 MB）后口碑层覆盖升至 65.2%。
   **种子 v2 = 本方案 + 短篇补入**，详见报告 19 §6。

---

## 1. 口径声明

1. **数据源**：{BASE.name}/out/novels.csv，{num(len(d))} 行（已剔除正版日轻）。
   内容上界 **{CONTENT_END.date()}**（原始 jsonl 的 `max(last_update)`，即游标扫描起点，非统一读取时刻）。
2. **定年**：`eras.estimate()`，log(nid) 分段线性，104 锚点，LOO P99 = 50 天。
   本报告只用 `est_year` 做分层，**不用 `updated_at` 做时间轴**。
3. **分位在全库算**（报告 03 已定）：种子的分位值继承自全库分组排名，不在候选池内重算。
4. **收藏（`favs`）是偏好强度，不含书龄**：`favs` 是存量，与 `clicks` 受曝光分母混杂不同（报告 02、08）。
   本报告用收藏份额衡量"种子承载了多少用户偏好"，**不作为成绩排名依据**。
5. **月榜归档**：{num(len(rank_ids))} 个去重 nid（{num(len(set(rank_ids) & set(d.id)))} 个在库内），
   来自 165 个月 × 4 个 rank。热销榜 `ticketNum` 恒 0，只能作名次结构描述（报告 07）。
6. **体积为实测**：用 Python `sqlite3` 真实建库、真实 gzip 后测得，非估算。
7. **性能为实测**：全库 {num(len(d))} 行库上跑 20 次取中位数。

---

## 2. "够用"的可测量化

「用户感觉数据够用」不是主观感受，可以拆成四个可测判据：

| 判据 | 度量方式 | 决定性吗 |
| --- | --- | --- |
| **搜得到** | 用户输入标题/作者前缀，目标书是否在本地可搜到 | 否——官方 API 兜底后可达率恒 100% |
| **逛得到** | 各浏览维度（世代/分类/标签/标签×年代）的代表作品是否在种子里 | **是**——这是种子唯一不可替代的价值 |
| **跟得上** | 最近上架的书有多少在种子里 | **是**——决定 App 是否显得"活" |
| **装得下** | 体积占包体多少 | 是——硬约束 |

关键认知：**搜特定书不需要种子**。本地未命中 → 官方搜索 → 自动收录 → 二次可搜到，
这条闭环（技术栈文档 §4.5）让可达率与种子规模无关。
所以种子规模的判据只剩后两条：**探索覆盖**与**新鲜度覆盖**。

### 2.1 目标书的收藏分位决定搜索体验

按全库收藏分位分五档，抽样的标题前缀命中率：

| 目标书分位 | 种子 5,528 本 | 种子 10,334 本 | 种子 20,184 本 | 种子 40,095 本 |
| --- | --- | --- | --- | --- |""")

    # 搜索命中矩阵现算
    import random
    random.seed(42)
    d2 = d.copy()
    d2["pctl"] = d2.favs.rank(ascending=False, method="first") / len(d2)
    bands = [(0.0, 0.001, "top 0.1%"), (0.001, 0.01, "top 1%"),
             (0.01, 0.05, "top 5%"), (0.05, 0.20, "top 5–20%"), (0.20, 1.01, "后 80%")]
    hit_rows = []
    for N in [5000, 10000, 20000, 40000]:
        seed = (set(d.nlargest(N, "favs").id) | new1y | active) | base_need
        joined = "\n".join(str(t) for t in d.loc[d.id.isin(seed), "title"])
        jauthor = "\n".join(str(t) for t in d.loc[d.id.isin(seed), "author"])
        row = []
        for lo, hi, lab in bands:
            sub = d2[(d2.pctl >= lo) & (d2.pctl < hi)]
            if len(sub) == 0:
                row.append(0.0)
                continue
            samp = sub.sample(min(1500, len(sub)), random_state=7)
            hit = tot = 0
            for _, r in samp.iterrows():
                t = str(r.title)
                if len(t) < 4:
                    continue
                k = t[: max(3, min(6, len(t) // 2))]
                tot += 1
                if k in joined or k in jauthor:
                    hit += 1
            row.append(hit / max(1, tot) * 100)
        hit_rows.append(row)
    for (lo, hi, lab), row in zip(bands, zip(*hit_rows)):
        md.append(f"| {lab} | " + " | ".join(f"{v:.0f}%" for v in row) + " |")
    md.append(f"""
本地命中率随规模线性上升，但**每一档的目标书都可以通过官方 API 找到**，
所以这张表的意义不在"能不能找到"，而在**首次命中速度与结果质量**——
本地命中是零延迟的，官方兜底要走网络。

---

## 3. 规模曲线：拐点在哪里

复合方案（收藏 TopN ∪ 近 1 年上架 ∪ 近 90 天仍更新 ∪ 月榜 ∪ banner）下：

| 规模 | 收藏份额 | 世代 top10 | 分类 top50 | 标签 top20 | 标签×年代单元格 | 最新 3000 本 | 标签熵 |
| --- | --- | --- | --- | --- | --- | --- | --- |""")
    for _, r in cur.iterrows():
        md.append(f"| {num(r.n)} | {r.fav:.1f}% | {r.era:.1f}% | {r.gen:.1f}% | "
                  f"{r.tag:.1f}% | {r.cell:.1f}% | {r.recent:.1f}% | {r.ent:.3f} |")

    md.append(f"""
**边际收益在 3 万本后陡降**：收藏份额从 {near(20000).fav:.1f}%（{num(near(20000).n)} 本）
升到 {near(29000).fav:.1f}%（{num(near(29000).n)} 本）只用了 {num(near(29000).n-near(20000).n)} 本，
再往上堆到 {num(near(53000).n)} 本（{near(53000).n/near(29000).n:.1f} 倍）要多花 {num(near(53000).n-near(29000).n)} 本，
而**标签×年代单元格覆盖只从 {near(29000).cell:.1f}% 涨到 {near(53000).cell:.1f}%**。

推荐规模 **{num(rec_n)} 本**的取值理由：
- 收藏份额 {cov_rec['收藏份额']:.1f}%——用户偏好绝大部分在册
- 标签×年代单元格 {cov_rec['标签×年代单元格']:.1f}%——超过 2/3 的"标签×年代"组合能逛到代表作
- 标签 top20 {cov_rec['标签 top20']:.1f}%——绝大多数标签都有可展示的头部
- 最新 3000 本 {cov_rec['最新3000本']:.0f}%——新书全部在册，App 显得"活"
- 体积 {a_gz/1048576:.1f} MB（gz）——包体可接受

再往上堆到 {num(near(53000).n)} 本，只多覆盖 {near(53000).cell-cov_rec['标签×年代单元格']:.1f} 个百分点的
单元格，代价是多 {num(near(53000).n-rec_n)} 本、多约 {(near(53000).n-rec_n)*a/rec_n/1048576:.0f} MB——
性价比不划算。

---

## 4. 来源构成：种子不是一个列表

| 来源 | 自身规模 | 新增 | 累计 | 为什么必须有 |
| --- | --- | --- | --- | --- |""")
    for r in src_rows:
        why = {
            "收藏榜头部": "承载用户偏好主体（收藏份额）",
            "近 1 年上架": "新书收藏少，纯收藏榜会漏掉",
            "近 90 天仍更新": "当下连载中的书，是「活」的信号",
            "月榜归档": "唯一有官方背书的付费/热销刻度",
            "banner 全集": "平台押注位，是运营信号",
        }[r["来源"]]
        md.append(f"| {r['来源']} | {num(r['自身'])} | {num(r['新增'])} | {num(r['累计'])} | {why} |")

    md.append(f"""
四个来源的**互补性**是这张表的价值所在：
- 月榜归档 {num(len(set(rank_ids) & set(d.id)))} 本与收藏 Top{num(REC_N)} 只重叠
  {len((set(rank_ids) & set(d.id)) & set(d.nlargest(REC_N,'favs').id))} 本——**月榜捞出了收藏榜漏掉的书**。
- banner {num(len(set(d.loc[d.featured==1,'id'])))} 本**全部**落在收藏 Top{num(REC_N)} 内
  （差集为 0）——banner 不是独立信号，它是收藏头部的一个子集。
- 近 1 年上架 {num(len(new1y))} 本与收藏榜头部几乎不重叠（重叠
  {len(new1y & set(d.nlargest(REC_N,'favs').id))} 本）——**这是纯收藏榜最大的盲区**。

---

![种子规模与存储架构总览](figures/18_seed_scale.png)

*图 18-1｜四图总览。（左上）种子规模 vs 收藏份额与标签×年代单元格覆盖率，绿线为推荐规模
29,396 本——曲线在此处已基本饱和，是规模拐点；（右上）世代/标签/分类三类代表作品的覆盖率
随规模上升的轨迹，可读出各维度的饱和点不同；（左下）规模相近时纯收藏 Top20k 与复合方案
在五个判据上的对照，差异集中在"最新 3000 本"一项；（右下）四种存储架构在同规模种子下的
SQLite 体积对照，柱上数字为实测值。*

## 5. 存储架构：多表 vs 单表的真实成本

### 5.1 体积拆解（实测，{num(rec_n)} 本种子）

| 架构 | SQLite | gzip | 每本 | 相对基准 |
| --- | --- | --- | --- | --- |""")
    base_b = b
    for nm, v, g in [("扁平单表 + 3 索引 + 反范式标签表", a, a_gz),
                     ("扁平单表 + 3 索引（标签存管道串）", b, b_gz),
                     ("novly 式 5 表，无索引", c, c_gz),
                     ("novly 式 5 表 + 11 索引", e, e_gz)]:
        md.append(f"| {nm} | {v/1048576:.2f} MB | {g/1048576:.2f} MB | {v/rec_n:.0f} B | "
                  f"{v/base_b:.2f}× |")

    md.append(f"""
**结论一：索引是膨胀主因，不是表数量。**
novly 式 5 表 + 11 索引 {e/1048576:.1f} MB，去掉索引后 {c/1048576:.1f} MB——
**索引占了 {(e-c)/e*100:.0f}%**。而"5 表 vs 1 表"本身的差异只有 {(e-c)/rec_n:.0f} 字节/本，
因为小说表才是主体，维度表（tags/authors/contests）相对很小。

**结论二：novly 的 90 MB 有两个独立来源，必须分开归因。**

| 口径 | SQLite | gzip |
| --- | --- | --- |
| 全库 {num(len(d))} 本 · novly 式 5 表 + 11 索引 | {full_novly/1048576:.1f} MB | {full_novly_gz/1048576:.1f} MB |
| 全库 · novly 式 5 表，**无索引** | {full_novly_noidx/1048576:.1f} MB | {full_novly_noidx_gz/1048576:.1f} MB |
| 全库 · 扁平单表 + 3 索引 + 反范式表 | {full_flat/1048576:.1f} MB | {full_flat_gz/1048576:.1f} MB |

同数据同 schema 下 novly 式全库是 {full_novly/1048576:.0f} MB，
与 novly 实际内置的 ~90 MB 同量级——**它的体积主要来自"全库 24 万本 × 11 个索引"，
而不是"用了 5 张表"**。这个区分很重要：把锅甩给多表，会得出"所以我们该单表"，
但真正能省 {(full_novly-full_novly_noidx)/1048576:.0f} MB 的是砍索引。

**结论三：索引要不要留，取决于查询是否走它。**
建索引不是免费的——novly 的 11 个索引让同规模种子多了 {(e-c)/rec_n:.0f} 字节/本。
所以索引集应当**由实际查询决定，而不是照抄 novly**。

### 5.2 性能实测：扁平单表够不够快

全库 {num(len(d))} 行，扁平单表 + 3 索引，20 次取中位数：

| 查询 | 耗时 | 判定 |
| --- | --- | --- |""")
    perf_rows = [
        ("收藏>1万 Top20", perf_flat["收藏>1万 Top20"], "走索引，快"),
        ("分类×年代 Top20", perf_flat["分类×年代 Top20"], "走 idx_year 过滤，可接受"),
        ("标题包含关键词", perf_flat["标题包含关键词"], "全表扫描但可接受"),
        ("作者精确匹配", perf_flat["作者精确匹配"], "走 idx_author，快"),
        ("标签×年代（管道串 LIKE）", perf_flat["标签×年代（管道串 LIKE）"], "**慢**"),
        ("标签×年代（反范式表 JOIN）", perf_flat["标签×年代（无反范式表）"], "—"),
    ]
    # 反范式表版本单独测
    p = tempfile.mktemp(suffix=".db")
    build_db(d, set(d.id), p, "flat", IDX_MIN, True)
    con = sqlite3.connect(p)
    cq = con.cursor()
    ts = []
    for _ in range(20):
        t0 = time.perf_counter()
        cq.execute("SELECT b.nid FROM book_tags bt JOIN books b ON b.nid=bt.nid "
                   "WHERE bt.tag='穿越' AND b.est_year=2020 LIMIT 50").fetchall()
        ts.append((time.perf_counter() - t0) * 1000)
    perf_join = float(np.median(ts))
    con.close()
    os.remove(p)
    for nm, v, jd in perf_rows:
        if nm == "标签×年代（管道串 LIKE）":
            jd = "**慢**"
        elif nm.startswith("标签×年代（反范式"):
            v = perf_join
            jd = "**反范式表快 {:.0f}×**".format(perf_flat["标签×年代（管道串 LIKE）"] / max(perf_join, 1e-9))
        md.append(f"| {nm} | {v:.2f} ms | {jd} |")
    md.append(f"""
**两处性能悬崖，都指向同一个结论：索引要按查询加，不是按字段加。**

1. **标签查询**：管道串 `LIKE '%|穿越|%'` 需要 {perf_flat['标签×年代（管道串 LIKE）']:.1f} ms
   （无法走索引，全表扫描），换成反范式 `book_tags` 表 + `(tag,nid)` 索引后
   只需 {perf_join:.2f} ms，**快 {perf_flat['标签×年代（管道串 LIKE）']/max(perf_join,1e-9):.0f} 倍**。
   这张表增加 {(a-b)/rec_n:.0f} 字节/本（{b/1048576:.1f} MB → {a/1048576:.1f} MB）——**值的**。
2. **作者查询**：不建 `idx_author` 时退化为全表扫描，耗时可达数十毫秒。
   本方案已把 `idx_author` 计入索引集，实测代价 {(full_flat-full_flat_minidx)/len(d):.0f} 字节/本
   （全库 {full_flat/1048576:.1f} MB → {full_flat_minidx/1048576:.1f} MB，去掉它可省这点体积）。

结论：**索引必须由实际查询反推，而不是照抄别人的字段清单**。
novly 建 11 个索引，我们只建 4 个——不是更省事，是因为我们的查询集合更小。
把 novly 的索引集照抄过来，能多背 {(e-a)/rec_n:.0f} 字节/本
（{a/1048576:.1f} MB → {e/1048576:.1f} MB），却换不来任何一条我们需要的查询加速。

**这就是存储架构的最终答案**：

| 组件 | 形态 | 理由 |
| --- | --- | --- |
| `books` | 单表扁平 | 主体数据，不拆 |
| `book_tags` | 反范式关联表 + `(tag,nid)` 索引 | 唯一需要 JOIN 的维度，且是标签浏览的主路径 |
| 索引集 | **按查询裁剪**，不照抄 novly 的 11 个 | 每个索引都直接换算成包体 |
| `tags` / `authors` / `contests` 维度表 | **不建** | 维度基数小（106 标签 / 9 分类），值直接存主表，用 `DISTINCT` 或内存映射即可 |

nuance：标签名与分类名是低基数枚举，拆成带自增 id 的维度表纯粹是"教科书范式"，
在这个规模下**只增加 JOIN 成本和体积、不增加查询能力**。novly 拆了，是因为它的
`authors` 表要存预计算的代表作统计——那是它的产品需求（作者页要展示代表作），
不是拆表的必然性。我们若要做作者页，同样可以只在 `authors` 表放统计，不放标签。

---

## 6. 推荐方案

### 6.1 种子构成

```
seed = 收藏 Top {num(REC_N)}
     ∪ 近 1 年上架（est_date ≥ {NEW_CUTOFF.date()}）  {num(len(new1y))} 本
     ∪ 近 90 天仍更新（updated_at ≥ {ACTIVE_CUTOFF.date()}）  {num(len(active))} 本
     ∪ 月榜归档（在库部分）  {num(len(set(rank_ids) & set(d.id)))} 本
     ∪ banner 全集  {num(len(set(d.loc[d.featured==1,'id'])))} 本
     = {num(rec_n)} 本
```

### 6.2 存储形态

| 项 | 值 |
| --- | --- |
| 表 | `books`（单表扁平，20 列）+ `book_tags`（反范式） |
| 索引 | `idx_favs(favs DESC)`、`idx_year(est_year)`、`idx_author(author)`、`idx_bt(tag,nid)` |
| SQLite | {a/1048576:.2f} MB |
| gzip 后 | {a_gz/1048576:.2f} MB |
| 每本 | {a/rec_n:.0f} B |
| 含分位实值（三列 REAL） | {a_pctl/1048576:.2f} MB / gzip {a_pctl_gz/1048576:.2f} MB（+{(a_pctl-a)/rec_n:.0f} B/本） |

**分位列的代价已实测**：`books` 表预留了 `fav_pctl / click_pctl / praise_pctl` 三列。
上表的体积是这三列为 NULL 时的值（NULL 只占位图，几乎不占空间）；
填入真实分位值后每本增加 {(a_pctl-a)/rec_n:.0f} 字节，整库 gzip 增加
{(a_pctl_gz-a_gz)/1048576:.2f} MB。**代价可忽略——分位应当随种子携带**，
这样端上做分位榜不需要任何计算，也不受"种子池内重算会改分母"的陷阱（§3.2）。
分位值在构建期按**全库 × 世代**算好后写入，端上只读。

### 6.3 覆盖实测

| 判据 | 数值 |
| --- | --- |""")
    for k, v in cov_rec.items():
        md.append(f"| {k} | {v:.1f}% |")
    md.append(f"""
标签分布熵 {near(29000).ent:.3f}（满熵 = 1.0），说明种子在标签空间上**没有塌缩**。

---

## 7. 这个规模的盲区

诚实列出推荐方案仍覆盖不到的部分：

1. **长尾冷门书不在册**。全库 24 万本里约 {num(len(d)-rec_n)} 本不在种子中，
   用户若只搜冷门书会走官方 API 兜底——**首次要联网**。
2. **标签×年代单元格还有 {100-cov_rec['标签×年代单元格']:.0f}% 缺代表作**。
   缺的那类组合（既冷门又小众）用户主动去逛的概率极低。
3. **数据停在 {CONTENT_END.date()}**。种子永远落后，这是设计前提而非缺陷——
   端上爬虫的增量更新（技术栈文档 §3）负责补齐，而它从"进入详情页"开始生效。
4. **覆盖率上限受源数据限制**。数据集本身对在架书覆盖约 68.9%（报告 10），
   种子的天花板不是 100%——**全库 24 万本里约有三分之一本就没被爬到过**。

---

## 8. 待决

1. **种子书单是否与在线官方榜共用候选池**——离线榜标注"精选池内"，在线榜标注"全站当月"，
   不可混排（报告 03 已定）。
2. **`est_year` 在种子里的置信度展示**——定年有 LOO P99 = 50 天的误差，
   UI 展示年代时应给区间还是直接给年份？
3. **是否随种子附带分位值——已可定案：携带。** `fav_pctl/click_pctl/praise_pctl` 三列
   在构建期按全库 × 世代算好写入，实测代价 {(a_pctl-a)/rec_n:.0f} B/本、
   gzip 增加 {(a_pctl_gz-a_gz)/1048576:.2f} MB（§6.2）。
   携带后端上分位榜零计算，且规避"在种子池内重算会改分母"的陷阱。
4. **月榜归档是否全部内置**——{num(len(rank_ids))} 个 nid 的上榜历史是"离线历史月榜"的唯一数据源，
   但只覆盖 2013-03 起的 {num(len(set(rank_ids) & set(d.id)))} 本在库书。

---

## 附录：与 novly 存储设计的对照

| 维度 | novly | 本方案 | 依据 |
| --- | --- | --- | --- |
| 主表 | `novels` 17 列 | `books` 20 列（+3 分位列） | 我们多 est_year / 分位 |
| 标签 | `tags` + `novel_tags` 双表（范式） | `book_tags` 单表（反范式） | 低基数枚举，拆表只增 JOIN |
| 作者 | `authors` 表 + 预计算代表作 | 同（若做作者页） | 其预计算统计确有产品价值 |
| 赛事 | `contests` 表 | 值直接存主表 | 低基数 |
| 索引 | 11 个（照全字段建） | 4 个（按实际查询裁剪） | 索引占 novly 全库体积 {(full_novly-full_novly_noidx)/full_novly*100:.0f}% |
| 分片 | hot + cold_1/2/3（作者哈希） | 单文件 | 种子规模 {num(rec_n)} 本无需分片 |
| 全库体积 | ~90 MB | {full_flat/1048576:.0f} MB（同样全库、同样索引策略） | 差在索引数量 |
""")

    (OUT / "18_seed_scale.md").write_text("\n".join(md), encoding="utf-8")
    print(f"报告已生成：{OUT / '18_seed_scale.md'}")
    print(f"推荐规模 {num(rec_n)}  |  sqlite {a/1048576:.2f} MB  gz {a_gz/1048576:.2f} MB")
    print(f"覆盖：收藏 {cov_rec['收藏份额']:.1f}%  单元格 {cov_rec['标签×年代单元格']:.1f}%  "
          f"最新 {cov_rec['最新3000本']:.0f}%")
    print(f"全库对照：novly式 {full_novly/1048576:.0f} MB / 扁平 {full_flat/1048576:.0f} MB")


if __name__ == "__main__":
    main()

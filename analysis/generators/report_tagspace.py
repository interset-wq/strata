"""生成 analysis/reports/09_tagspace.md：标签共现网络与题材语义空间。

报告 04 统计了单标签频次，本报告转向**标签之间的关系**：106 个受控标签
（87 个出现 ≥100 次）构成的是一个连续语义空间，还是少数几个「套路包」？

口径要点（详见 §7）：

- 标签字段是**受控词表**，每本 1-5 个，且每本标签数随世代从 0 升到 5
  （2010-14 有 50-60% 的书完全无标签）。标签数直接决定共现机会，因此
  共现分析**只用 2017 年及以后**（标签体系稳定期），且以「同标签数分层的
  随机配对期望」为基准，用 O/E 而非原始共现计数。
- `20XX萌神` 7 个标签是运营荣誉而非题材（报告 04 §3），逐一从标签集合中剔除。
- 聚类分组只为统计方便；标签空间的轮廓系数仅约 0.04，即**边界模糊、没有
  离散的题材类**，这一点本身是本报告的结论之一，不是方法缺陷。

用法：uv run python analysis/report_tagspace.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from scipy import sparse  # noqa: E402
from scipy.cluster.hierarchy import dendrogram, linkage  # noqa: E402
from scipy.sparse import csr_matrix  # noqa: E402
from scipy.sparse.csgraph import laplacian  # noqa: E402
from scipy.sparse.linalg import eigsh  # noqa: E402
from sklearn.cluster import SpectralClustering  # noqa: E402
from sklearn.manifold import MDS  # noqa: E402
from sklearn.metrics import silhouette_score  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import paths

from lib import charts  # noqa: E402
from lib import eras  # noqa: E402

BASE = paths.ROOT
OUT = paths.REPORTS_DIR / "09_tagspace.md"
MIN_FREQ = 100
SINCE = 2017
HUB_MIN = 30  # 计算「平均 O/E」时的最小共现数（低频标签也能定义）
K = 8

# 簇名按签名标签判定（谱聚类编号不稳定，不能按下标硬编码）
SIGNATURES = [
    ("女武神", "崩坏同人（单 IP）"),
    ("同人", "同人 IP 群"),
    ("女性主角", "女性向变身"),
    ("倒追", "乙女追妻"),
    ("脑洞", "悬疑脑洞"),
    ("硬核", "暗黑硬核"),
    ("日常", "情感氛围"),
]


# ---------- 格式化 ----------


def pct(x: float, nd: int = 1) -> str:
    return f"{x:.{nd}f}"


def thousands(x: float) -> str:
    if pd.isna(x):
        return "—"
    if abs(x) >= 1e8:
        return f"{x / 1e8:.1f} 亿"
    if abs(x) >= 1e4:
        return f"{x / 1e4:,.1f} 万"
    return f"{x:,.0f}"


def md_table(rows: list[list], header: list[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


# ---------- 载入与矩阵 ----------


def load_books() -> pd.DataFrame:
    df = pd.read_csv(paths.OUT_DIR / "novels.csv", dtype={"tags": str, "contest": str})
    est = eras.estimate(df["id"])
    d = df.merge(est[["id", "est_date", "est_year"]], on="id")
    d["tl"] = d["tags"].fillna("").map(
        lambda s: [t.strip() for t in s.split("|") if t.strip() and "萌神" not in t]
    )
    d["ntag"] = d["tl"].map(len)
    d["updated"] = pd.to_datetime(d["updated_at"], errors="coerce")
    return d


def tag_matrix(d: pd.DataFrame, since: int = SINCE, min_freq: int = MIN_FREQ):
    """返回 (标签名, 稀疏指示矩阵, 频次数组, 对应子集)。"""
    sub = d[(d["est_year"] >= since) & (d["ntag"] > 0)].reset_index(drop=True)
    cnt: dict[str, int] = {}
    for L in sub["tl"]:
        for t in L:
            cnt[t] = cnt.get(t, 0) + 1
    tags = [t for t, v in sorted(cnt.items(), key=lambda kv: -kv[1]) if v >= min_freq]
    idx = {t: i for i, t in enumerate(tags)}
    rows, cols = [], []
    for r, L in enumerate(sub["tl"]):
        for t in L:
            if t in idx:
                rows.append(r)
                cols.append(idx[t])
    X = sparse.csr_matrix(
        (np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(sub), len(tags))
    )
    X.data[:] = 1.0
    return tags, X, np.asarray(X.sum(0)).ravel(), sub


def cooc(X: sparse.csr_matrix):
    """共现矩阵、分层随机期望、O/E 比。"""
    CO = np.asarray((X.T @ X).todense(), dtype=float)
    k = np.asarray(X.sum(1)).ravel()
    E = np.zeros_like(CO)
    for kk in np.unique(k):
        if kk < 2:
            continue
        sel = k == kk
        Nk = int(sel.sum())
        if Nk < 2:
            continue
        nk = np.asarray(X[sel].sum(0)).ravel().astype(float)
        E += (kk - 1) * np.outer(nk, nk) / (Nk * kk - 1)
    OE = np.divide(CO, E, out=np.full_like(CO, np.nan), where=E > 0)
    np.fill_diagonal(OE, np.nan)
    return CO, E, OE


def weighted_oe(CO: np.ndarray, OE: np.ndarray, cap: float = 50.0) -> np.ndarray:
    """以共现量为权重的平均 O/E：该标签的共现「平均落在随机期望的多少倍」。

    低频标签可能与任何标签都达不到阈值共现，简单取平均会得到空集；加权平均对
    每个标签都有定义，权重正好是「这段关联占该词共现总量的多少」。
    """
    W = np.nan_to_num(CO, nan=0.0).copy()
    np.fill_diagonal(W, 0)
    O = np.clip(np.nan_to_num(OE, nan=0.0), 0, cap)
    den = W.sum(1)
    return np.divide((W * O).sum(1), den, out=np.full(len(den), np.nan), where=den > 0)


def similarity(CO: np.ndarray, n: np.ndarray) -> np.ndarray:
    """对称化条件概率 0.5*(P(j|i)+P(i|j))，作为标签间关联强度。"""
    P = CO / np.maximum(n[:, None], 1)
    S = 0.5 * (P + P.T)
    np.fill_diagonal(S, 0)
    return S


def cluster_tags(S: np.ndarray, tags: list[str], k: int = K):
    sc = SpectralClustering(
        n_clusters=k, affinity="precomputed", random_state=0, assign_labels="kmeans"
    )
    lb = sc.fit_predict(S)
    # 按签名标签给簇命名；未命中的簇由「剩余」补名
    names: dict[int, str] = {}
    for sig, nm in SIGNATURES:
        if sig not in tags:
            continue
        c = int(lb[tags.index(sig)])
        names.setdefault(c, nm)
    n_left = len(set(lb.tolist()) - set(names))
    for c in sorted(set(lb.tolist()) - set(names)):
        names[c] = "男性向冒险" if n_left == 1 else f"簇 {c}"
        n_left -= 1
    return lb, names


def assign_books(sub: pd.DataFrame, tags: list[str], lb: np.ndarray):
    """把每本书分配给标签票数最多的簇，并记录跨簇标签数。"""
    t2c = dict(zip(tags, lb))
    cl, ncl = [], []
    for L in sub["tl"]:
        cs = [t2c[t] for t in L if t in t2c]
        if not cs:
            cl.append(-1)
            ncl.append(0)
            continue
        v = pd.Series(cs).value_counts()
        cl.append(int(v.index[0]))
        ncl.append(int(v.size))
    sub = sub.copy()
    sub["cluster"] = cl
    sub["ncl"] = ncl
    return sub


# ---------- 图表 ----------


def fig_vocab(d: pd.DataFrame, tags: list[str], sub: pd.DataFrame) -> str:
    """左：标签字段三代（无标签占比与每本标签数）；右：词表的启用与停用。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.6, 3.1), width_ratios=[1, 1])

    g = d[d["est_year"].between(2007, 2026)].groupby("est_year").agg(
        zero=("ntag", lambda s: (s == 0).mean() * 100),
        med=("ntag", "median"),
        mean=("ntag", "mean"),
    )
    yrs = g.index.to_numpy()
    ax0.bar(yrs, g["zero"], color="#CCCCCC", width=0.72, label="无标签书占比 %")
    ax0.set_ylabel("无标签书占比 %（灰柱）", color="#777777")
    ax0.set_ylim(0, 100)
    ax1b = ax0.twinx()
    ax1b.plot(yrs, g["mean"], lw=1.6, color=charts.C["blue"], marker="o", ms=2.6,
              label="每本标签数（均值，蓝线）")
    ax1b.set_ylabel("每本标签数（蓝线）", color=charts.C["blue"])
    ax1b.set_ylim(0, 5.2)
    ax1b.grid(False)
    ax0.set_title("标签字段的三代：空窗期 → 受控多标签", fontsize=9, loc="left")
    for lo, hi, nm, _ in [(2010, 2014, "空窗期", ""), (2017, 2026, "受控多标签", "")]:
        ax0.annotate(nm, xy=((lo + hi) / 2, 92), ha="center", fontsize=7.5, color="#666666")
    ax0.set_xlabel("上架年份")

    # 右：每个标签的启用年与退场年（全库口径，年 ≥20 次才算活跃）
    rows = []
    for t in tags:
        s = d[d["tl"].map(lambda L: t in L)]
        if len(s) < 50:
            continue
        cy = s.groupby("est_year").size()
        cy = cy[cy >= 20]
        if len(cy) == 0:
            continue
        rows.append((t, int(cy.index.min()), int(cy.index.max()), len(s)))
    act = pd.DataFrame(rows, columns=["tag", "start", "end", "n"]).sort_values(
        ["start", "n"], ascending=[True, False]
    )
    top = act.sort_values("n", ascending=False).head(30)
    y = np.arange(len(top))
    ax1.hlines(y, top["start"], top["end"], color="#DDDDDD", lw=3.2, zorder=1)
    sc = ax1.scatter(top["start"], y, s=12, color=charts.C["green"], zorder=3, label="启用年")
    ax1.scatter(top["end"], y, s=12, color=charts.C["red"], zorder=3, label="最后活跃年")
    ax1.set_yticks(y)
    ax1.set_yticklabels(top["tag"].tolist(), fontsize=6.4)
    ax1.invert_yaxis()
    ax1.set_xlim(2007, 2027)
    ax1.legend(frameon=False, fontsize=7, loc="upper left")
    ax1.set_title("使用频次前 30 的标签：启用与退场", fontsize=9, loc="left")
    ax1.set_xlabel("上架年份（按定年）")
    fig.tight_layout()
    return charts.save(fig, "09_vocab.png")


def fig_cooccur(tags: list[str], lb: np.ndarray, names: dict[int, str],
                CO: np.ndarray, OE: np.ndarray, n: np.ndarray) -> str:
    """按簇排序的 87×87 log2(O/E) 热力图。"""
    order = sorted(range(len(tags)), key=lambda i: (lb[i], -n[i]))
    M = OE[np.ix_(order, order)].copy()
    M = np.where(M > 0, np.log2(np.maximum(M, 1e-6)), np.nan)
    fig, ax = plt.subplots(figsize=(7.2, 7.0))
    norm = TwoSlopeNorm(vmin=-3, vcenter=0, vmax=5)
    im = ax.imshow(M, cmap="RdBu_r", norm=norm, interpolation="nearest")
    ax.set_yticks([])
    ax.set_xticks([])
    ax.grid(False)
    # 簇分隔线与块标签
    bounds = []
    prev = None
    for pos, i in enumerate(order):
        if lb[i] != prev:
            bounds.append(pos)
            prev = lb[i]
    bounds.append(len(order))
    for b in bounds[1:-1]:
        ax.axhline(b - 0.5, color="#333333", lw=0.7)
        ax.axvline(b - 0.5, color="#333333", lw=0.7)
    palette = ["#4477AA", "#CC3311", "#009988", "#EE7733", "#EE3377", "#33BBEE",
               "#AA3377", "#777777"]
    from matplotlib.patches import Patch
    handles = []
    for j in range(len(bounds) - 1):
        a, b = bounds[j], bounds[j + 1]
        c = lb[order[a]]
        col = palette[c % len(palette)]
        ax.add_patch(plt.Rectangle((-0.05, a), 0.04, b - a, transform=ax.get_yaxis_transform(),
                                   color=col, clip_on=False, zorder=5))
        handles.append(Patch(color=col, label=names[c]))
    ax.legend(handles=handles, fontsize=6.8, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, -0.01), ncol=4, handlelength=1.0, handleheight=0.9,
              columnspacing=1.0)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01)
    cb.set_label("log2(共现 / 随机期望)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    ax.set_title("共现强度矩阵（对称）：块内红、块间蓝，白 = 中性", fontsize=9, loc="left")
    fig.tight_layout()
    return charts.save(fig, "09_cooccur.png")


def fig_space(tags: list[str], S: np.ndarray, lb: np.ndarray, n: np.ndarray,
              names: dict[int, str], hub: np.ndarray) -> str:
    """谱嵌入语义空间（与聚类同一几何）：点大小 ∝ 频次，颜色 = 簇。"""
    L = laplacian(sparse.csr_matrix(S), normed=True)
    # eigsh（ARPACK）用随机初始向量，不设 v0 则每次重跑得到略有不同的特征向量，
    # 图不可复现。固定 v0 即可。
    v0 = np.ones(L.shape[0], dtype=float)
    _, vec = eigsh(L.astype(float), k=3, which="SM", v0=v0)
    XY = vec[:, 1:3]
    fig, ax = plt.subplots(figsize=(7.0, 5.4))
    palette = ["#4477AA", "#CC3311", "#009988", "#EE7733", "#EE3377", "#33BBEE",
               "#AA3377", "#777777"]
    for c in sorted(set(lb.tolist())):
        m = lb == c
        ax.scatter(XY[m, 0], XY[m, 1], s=np.sqrt(n[m]) * 1.6, alpha=0.65,
                   color=palette[c % len(palette)], edgecolor="white", lw=0.4,
                   label=f"{names[c]}（{int(m.sum())}）")
    # 标注：高频标签 + 高关联专用件；贪心避让，只保留互不重叠的
    cand = [i for i in range(len(tags)) if n[i] > 25000 or hub[i] > 5]
    for c in sorted(set(lb.tolist())):  # 每簇的最高频标签必标
        idx = [i for i in range(len(tags)) if lb[i] == c]
        m = max(idx, key=lambda i: n[i])
        if m not in cand:
            cand.append(m)
    cand.sort(key=lambda i: -(hub[i] + n[i] / 10000))
    placed: list[tuple[float, float]] = []
    span_x = np.ptp(XY[:, 0]) or 1.0
    span_y = np.ptp(XY[:, 1]) or 1.0
    for i in cand:
        x, y = XY[i, 0] / span_x, XY[i, 1] / span_y
        if any((x - px) ** 2 + (y - py) ** 2 < 0.004 for px, py in placed):
            continue
        placed.append((x, y))
        ax.annotate(tags[i], (XY[i, 0], XY[i, 1]), fontsize=6.8, ha="center",
                    va="bottom", color="#222222",
                    xytext=(0, 4), textcoords="offset points")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=True, framealpha=0.95, edgecolor="none", fontsize=7,
              loc="lower right", ncol=2, markerscale=0.8)
    ax.set_title("标签的二维语义空间（谱嵌入，与聚类同一几何）", fontsize=9, loc="left")
    fig.tight_layout()
    return charts.save(fig, "09_space.png")


def fig_mismatch(st: pd.DataFrame, names: dict[int, str]) -> str:
    """左：供给份额 vs 收藏份额；右：上榜率与转化率。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.8, 3.4), width_ratios=[1, 1.1])
    x = st["supply"] * 100
    y = st["fav_share"] * 100
    ax0.plot([0, x.max() * 1.1], [0, x.max() * 1.1], ls="--", lw=0.8, color="#999999")
    pal = ["#4477AA", "#CC3311", "#009988", "#EE7733", "#EE3377", "#33BBEE",
           "#AA3377", "#777777"]
    # 手工错位：原点附近的小簇标签互相避让（ha: h=水平对齐）
    OFF = {
        "男性向冒险": (-8, 8, "right"),
        "情感氛围": (10, 4, "left"),
        "女性向变身": (6, 10, "left"),
        "乙女追妻": (-8, 12, "right"),
        "悬疑脑洞": (9, 6, "left"),
        "同人 IP 群": (9, -9, "left"),
        "崩坏同人（单 IP）": (9, -1, "left"),
        "暗黑硬核": (-7, 0, "right"),
    }
    for i, (_, r) in enumerate(st.iterrows()):
        ax0.scatter(r["supply"] * 100, r["fav_share"] * 100, s=np.sqrt(r["n"]) * 1.4,
                    color=pal[i % len(pal)], edgecolor="white", lw=0.5, zorder=3)
        dx, dy, ha = OFF.get(names[r["cluster"]], (4, 3, "left"))
        ax0.annotate(names[r["cluster"]], (r["supply"] * 100, r["fav_share"] * 100),
                     fontsize=6.6, xytext=(dx, dy), textcoords="offset points", ha=ha)
    ax0.set_xlabel("供给份额 %（书数占比）")
    ax0.set_ylabel("收藏份额 %")
    ax0.set_title("供给与注意力：对角线以上＝以少占多", fontsize=9, loc="left")

    st2 = st.sort_values("mp_rate")
    y2 = np.arange(len(st2))
    ax1.barh(y2 - 0.2, st2["mp_n"], height=0.38, color="#4477AA", label="月票榜上榜书数")
    ax1.barh(y2 + 0.2, st2["hot_n"], height=0.38, color="#CC3311", label="热销榜上榜书数")
    for yy, (v1, v2, mp, ht) in zip(y2, zip(st2["mp_n"], st2["hot_n"],
                                            st2["mp_rate"], st2["hot_rate"])):
        ax1.text(v1, yy - 0.2, f" {v1}（{mp:.2f}%）", va="center", fontsize=6.2,
                 color="#4477AA")
        ax1.text(v2, yy + 0.2, f" {v2}（{ht:.2f}%）", va="center", fontsize=6.2,
                 color="#CC3311")
    ax1.set_yticks(y2)
    ax1.set_yticklabels([names[c] for c in st2["cluster"]], fontsize=7)
    ax1.legend(frameon=False, fontsize=7, loc="lower right")
    ax1.set_xlabel("2013-2026 累计上过榜的书数（括号内为区内比例）")
    ax1.set_title("商业化门槛：谁付得起", fontsize=9, loc="left")
    ax1.set_xlim(0, max(st2["mp_n"].max(), st2["hot_n"].max()) * 1.35)
    fig.tight_layout()
    return charts.save(fig, "09_mismatch.png")


def fig_hub(tags: list[str], OE: np.ndarray, CO: np.ndarray, n: np.ndarray,
            lb: np.ndarray, names: dict[int, str]) -> str:
    """左：枢纽—专属二维；右：O/E 分布。"""
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(8.6, 3.4), width_ratios=[1.15, 1])
    hub = weighted_oe(CO, OE)
    valid = CO >= HUB_MIN
    np.fill_diagonal(valid, False)
    ax0.scatter(np.log2(hub), np.log10(n), s=16, color=charts.C["blue"], alpha=0.6,
                edgecolor="white", lw=0.3)
    # 贪心避让标注
    cand = list(range(len(tags)))
    cand.sort(key=lambda i: -(hub[i] * 3 + n[i] / 10000))
    xs, ys = np.log2(hub), np.log10(n)
    span_x = np.ptp(xs) or 1.0
    span_y = np.ptp(ys) or 1.0
    placed = []
    for i in cand:
        x, y = xs[i] / span_x, ys[i] / span_y
        if any((x - px) ** 2 + (y - py) ** 2 < 0.0035 for px, py in placed):
            continue
        placed.append((x, y))
        ax0.annotate(tags[i], (xs[i], ys[i]), fontsize=6.2,
                     xytext=(3, 2), textcoords="offset points", color="#333333")
    ax0.set_xlabel("加权平均 O/E（以共现量为权重）→ 右侧＝与特定伙伴强绑定")
    ax0.set_ylabel("log10 频次")
    ax0.axvline(1.0, ls=":", lw=0.8, color=charts.C["red"])
    ax0.set_title("通用配料（左）与专用件（右）", fontsize=9, loc="left")

    pair200 = CO >= 200
    np.fill_diagonal(pair200, False)
    v = np.log2(np.maximum(OE[pair200], 1e-6))
    ax1.hist(v, bins=60, color="#BBBBBB", edgecolor="white", lw=0.3)
    ax1.axvline(0, color=charts.C["red"], lw=1.0)
    ax1.set_xlabel("log2(O/E)")
    ax1.set_ylabel("标签对数量")
    ax1.set_title(f"≥200 次共现的 {int(pair200.sum() / 2):,} 对：随机基准两侧都很多", fontsize=9,
                  loc="left")
    ax1.text(0.02, 0.9, f"O/E>2 占 {(v > 1).mean() * 100:.0f}%　O/E<0.5 占 {(v < -1).mean() * 100:.0f}%",
             transform=ax1.transAxes, fontsize=7, color="#333333")
    fig.tight_layout()
    return charts.save(fig, "09_hub.png")


# ---------- 章节 ----------


def main() -> None:
    charts.setup_style()
    d = load_books()
    tags, X, n, sub = tag_matrix(d)
    CO, E, OE = cooc(X)
    S = similarity(CO, n)
    lb, names = cluster_tags(S, tags)
    sub = assign_books(sub, tags, lb)
    sb = eras.snapshot_bounds(d)
    n_anchor = len(eras.load_anchors()) if hasattr(eras, "load_anchors") else 104

    Dm = 1 - S
    np.fill_diagonal(Dm, 0)
    sil = silhouette_score(Dm, lb, metric="precomputed")
    # n_jobs=1：MDS 的 SMACOF 迭代在多线程下有浮点求和顺序差异，
    # 导致同一份输入每次重跑得到略有不同的坐标，图不可复现。串行即可。
    mds = MDS(n_components=2, metric="precomputed", init="random", random_state=0,
              normalized_stress="auto", n_jobs=1)
    XY = mds.fit_transform(Dm)

    # 词表基本量
    all_tags = sorted({t for L in d["tl"] for t in L})
    cnt_all = pd.Series([t for L in d["tl"] for t in L]).value_counts()

    # 簇画像
    mp = d.set_index("id")
    ranks = [json.loads(x) for x in (paths.OUT_DIR / "monthly_ranks.jsonl").open(encoding="utf-8")]
    mt = {it["nid"] for r in ranks if r["rank"] == 0 for it in r["items"]}
    ht = {it["nid"] for r in ranks if r["rank"] == 3 for it in r["items"]}
    conv = sub[(sub["clicks"] >= 400) & (sub["clicks"] < 1500) & (sub["favs"] > 0)]
    conv_rate = conv.assign(r=conv["favs"] / conv["clicks"]).groupby("cluster")["r"].median() * 100
    cut = pd.Timestamp(sb["content_end"]) - pd.Timedelta(days=365)
    rows = []
    for c in sorted(set(lb.tolist())):
        s = sub[sub["cluster"] == c]
        on = set(s["id"]) & set(mp.index)
        rows.append({
            "cluster": c, "n": len(s),
            "supply": len(s) / len(sub),
            "fav_share": s["favs"].sum() / sub["favs"].sum(),
            "favs_med": s["favs"].median(),
            "words_med": s["words"].median(),
            "conv": conv_rate.get(c, np.nan),
            "mp_rate": len(on & mt) / len(on) * 100 if on else np.nan,
            "hot_rate": len(on & ht) / len(on) * 100 if on else np.nan,
            "mp_n": len(on & mt),
            "hot_n": len(on & ht),
            "vip": (s["price_type"] == "VIP").mean() * 100,
            "done": (s["status"] == "已完结").mean() * 100,
            "stale": (s["updated"] < cut).mean() * 100,
            "contest": (s["contest"].fillna("") != "").mean() * 100,
            "mixed": (s["ncl"] >= 2).mean() * 100,
        })
    st = pd.DataFrame(rows)
    st["ratio"] = st["fav_share"] / st["supply"]
    st = st.sort_values("ratio", ascending=False)
    hub = weighted_oe(CO, OE)

    figs = {
        "vocab": fig_vocab(d, tags, sub),
        "cooccur": fig_cooccur(tags, lb, names, CO, OE, n),
        "space": fig_space(tags, S, lb, n, names, hub),
        "mismatch": fig_mismatch(st, names),
        "hub": fig_hub(tags, OE, CO, n, lb, names),
    }

    # ---- 数值 ----
    g_zero = d[d["est_year"].between(2010, 2014)]["ntag"].eq(0).mean() * 100
    g_all = d[d["est_year"] >= 2019]
    n_tag_rows = int((d["ntag"] == 0).sum())
    n_used = len(tags)
    gini_tag = gini(n)
    valid = CO >= 200
    np.fill_diagonal(valid, False)
    iu = np.triu_indices(len(tags), 1)
    pair_ok = valid[iu]
    OE_flat = np.log2(OE[iu][pair_ok])
    pairs = [
        (float(OE[i, j]), int(CO[i, j]), tags[i], tags[j])
        for i in range(len(tags)) for j in range(i + 1, len(tags)) if CO[i, j] >= 200
    ]
    pairs.sort(reverse=True)
    top_pairs, low_pairs = pairs[:12], pairs[-8:]

    # 同人 IP 子标签：与「同人」O/E 最高的标签
    ti = tags.index("同人")
    ip = sorted(
        [(float(OE[ti, j]), int(CO[ti, j]), tags[j]) for j in range(len(tags))
         if j != ti and CO[ti, j] >= 100], reverse=True
    )[:10]

    hub_df = pd.DataFrame({"tag": tags, "n": n, "hub": hub}).sort_values("hub", ascending=False)

    mix = sub.groupby("ncl").agg(n=("id", "size"), favs=("favs", "median"))
    ctl = sub[(sub["clicks"] >= 400) & (sub["clicks"] < 1500)
              & (sub["words"].between(5e4, 2e5))]
    mix["favs_ctl"] = ctl.groupby("ncl")["favs"].median()
    mix_r = (sub[(sub["clicks"] >= 400) & (sub["clicks"] < 1500) & (sub["favs"] > 0)]
             .assign(r=lambda x: x["favs"] / x["clicks"]).groupby("ncl")["r"].median() * 100)

    # ---- 报告 ----
    body = f"""# 09 · 题材语义空间：{n_used} 个标签的共现结构

> 口径声明：
> 1. 数据 `analysis/out/novels.csv`（{len(d):,} 行，内容上界 {sb['date']}，
>    上架年份由 nid 定年，{n_anchor} 锚点，LOO P99 = 50 天，报告 01 §1）。
> 2. `tags` 是**平台受控词表**而非作者自由填写：全库共 {len(all_tags)} 个不同标签，
>    {n_used} 个出现 ≥100 次，构成本报告的标签集。每本 1-5 个标签。
> 3. **`20XX萌神` 7 个标签已剔除**（运营荣誉而非题材，报告 04 §3），不参与共现。
> 4. **共现只用 {SINCE} 年及以后的书**（{len(sub):,} 本）：2010-2014 有 {g_zero:.0f}%
>    的书完全没有标签，2017 年前标签数中位仅 1，跨世代共现不可比。
> 5. 共现基准不是「独立随机」，而是**同标签数分层的随机配对期望**：把标签在同一
>    标签数（1-5 个）的书之间随机重排、保留每个标签的总量。O/E 因此不受「近年
>    标签越选越多」的规则变化影响。
> 6. 聚类仅作统计分组。{n_used} 个标签的轮廓系数约 {sil:.2f}——标签空间是连续谱，
>    没有离散的题材类，簇边界是人为切分。
> 7. 上榜率用 `out/monthly_ranks.jsonl`（月票榜 rank 0、热销榜 rank 3，
>    2013-03 至 2026-11），只统计在库书。

{sec_conclusion(tags, n, st, names, top_pairs, low_pairs, ip, g_zero, len(sub), mix_r, mix, sil, gini_tag, len(all_tags), (sub['ncl'] == 1).mean() * 100)}

---

{sec_vocab(d, all_tags, cnt_all, tags, n, gini_tag, figs["vocab"], n_tag_rows)}

---

{sec_cooccur(figs, top_pairs, low_pairs, ip, n_used, OE_flat, hub_df)}

---

{sec_space(figs, tags, lb, names, n, st, sil)}

---

{sec_mismatch(figs, st, names, sub)}

---

{sec_mix(mix, mix_r, sub)}

---

{sec_bounds()}
"""
    OUT.write_text(body, encoding="utf-8")
    print(f"written {OUT} ({len(body):,} chars)")


def sec_conclusion(tags, n, st, names, top_pairs, low_pairs, ip, g_zero, n_book,
                   mix_r, mix, sil, gini_tag, n_all, single) -> str:
    top = st.iloc[0]
    bottom = st.iloc[-1]
    best_mp = st.sort_values("mp_n", ascending=False).iloc[0]
    worst_mp = st.sort_values("mp_n").iloc[0]
    n_ip = int((n[tags.index("同人")]))
    m2 = mix_r.get(2, float("nan"))
    m1 = mix_r.get(1, float("nan"))
    return f"""## 0. 结论

1. **标签不是自由词汇，是一份 {n_all} 词的小词表**：全库合计 {n_all} 个在用标签，
   其中 {len(tags)} 个出现 ≥100 次、构成本报告的标签集。频次最高的「{tags[0]}」覆盖
   2017 年后新书的 {pct(n[0] / n_book * 100)}%，词表集中度（基尼）{gini_tag:.2f}
   ——高度头部化，长尾是只服务几十本书的细分词。
2. **标签字段分三代，跨代比较只有 2017 之后成立**：2007-09 是单标签时代，
   2010-14 反而有 {g_zero:.0f}% 的书完全无标签（空窗期），2015-16 过渡，
   2017 起进入受控多标签（中位 3 个，2025 年 5 个）。而且词表本身不稳定：
   **2022 年 23 个 IP 与亚文化标签被清理**（含这些标签的书 1,665 → 23 本），
   2023-24 一批女性向标签（变身、追夫、橘味、穿越）爆发进场。任何「标签占比
   随年份变化」的结论都必须先问：这是题材在变，还是标签规则在变。
3. **共现结构是「通用配料 + IP 专用件」**：最强关联全部来自同人子标签——
   {'、'.join(f'{a}×{b}（O/E {v:.0f}）' for v, c, a, b in top_pairs[:4])}。
   「同人」不是题材，而是**一个挂载 IP 的命名空间**，其下 {n_ip:,} 本书共享
   同一套写作范式却各自绑定一个作品。
4. **互斥关系同样清晰**：「同人」与原创向标签系统性互斥——
   {'、'.join(f'{a}×{b}（O/E {v:.2f}）' for v, c, a, b in low_pairs[-4:])}。
   这不是巧合，是**供给模式的分野**：同人书的读者来自已有 IP，不需要（也不该）
   用原创向标签自我介绍。
5. **8 个语义区存在，但边界模糊**（轮廓系数 {sil:.2f}）：{names.get(0, '')}、
   {'、'.join(sorted(set(names.values()) - {names.get(0, '')}))} 等块的内部关联强、块间几乎为零；
   但全库只有 {single:.1f}% 的书全部标签落在同一区——题材在**标签层是分立的**，
   在**书层是混合的**，聚类切分只是统计方便。
6. **供给与注意力错配是结构性的**：「{names[top['cluster']]}」用 {top['supply'] * 100:.1f}%
   的供给拿到 {top['fav_share'] * 100:.1f}% 的收藏（{top['ratio']:.1f} 倍）；
   「{names[bottom['cluster']]}」用 {bottom['supply'] * 100:.1f}% 的供给只拿到
   {bottom['fav_share'] * 100:.1f}%（{bottom['ratio']:.2f} 倍）。付费端的分化更陡：
   「{names[best_mp['cluster']]}」累计 {int(best_mp['mp_n'])} 本上过月票榜
   （区内 {best_mp['mp_rate']:.2f}%），「{names[worst_mp['cluster']]}」仅
   {int(worst_mp['mp_n'])} 本（{worst_mp['mp_rate']:.2f}%）——月票榜十六年只有 694 本书，
   头部题材拿走了几乎全部席位。控制曝光与字数后，混合度对收藏与转化率几乎没有
   影响（同档转化率 {m1:.2f}% vs {m2:.2f}%）——**再多标签也不制造读者**。"""


def sec_vocab(d, all_tags, cnt_all, tags, n, gini_tag, fig, n_zero) -> str:
    # 词表断层：2022 活跃但 2023-24 均沉寂的标签；2022 沉寂但 2024 活跃的标签
    died, born = [], []
    for t in tags:
        cy = d[d["tl"].map(lambda L: t in L)].groupby("est_year").size()
        if cy.get(2022, 0) >= 20 and cy.get(2023, 0) < 20 and cy.get(2024, 0) < 20:
            died.append(t)
        elif cy.get(2022, 0) < 20 and cy.get(2024, 0) >= 20:
            born.append(t)
    died_str = "、".join(f"「{t}」" for t in sorted(died))
    born_str = "、".join(f"「{t}」" for t in sorted(born))
    top = cnt_all.head(20)
    rows = [[t, f"{v:,}", f"{v / len(d) * 100:.1f}"] for t, v in top.items()]
    t1 = md_table(rows, ["标签", "书数", "占全库 %"])
    yr = d.groupby("est_year").agg(n=("id", "size"), zero=("ntag", lambda s: (s == 0).mean() * 100),
                                   mean=("ntag", "mean"))
    yr = yr.loc[2007:2026]
    rows2 = [[str(int(y)), f"{int(r['n']):,}", f"{r['zero']:.0f}", f"{r['mean']:.2f}"]
             for y, r in yr.iterrows()]
    t2 = md_table(rows2, ["上架年", "书数", "无标签 %", "每本标签数（均值）"])
    return f"""## 1. 词表：{len(all_tags)} 个词，三代口径

![](figures/09_vocab.png)

{len(all_tags)} 个不同标签里，{len(tags)} 个出现 ≥100 次、{int((cnt_all >= 1000).sum())} 个
≥1,000 次、最少用的一个只出现过 {cnt_all.min():.0f} 次——**这是一份封闭的受控词表**，不是用户自由标注。
频次前 20：

{t1}

集中度（基尼系数）{gini_tag:.2f}。标签数分布的偏斜意味着：共现分析若直接用原始
计数，结果会被头部标签主导；因此 §2 起全部改用 O/E。

标签字段本身经历了三代（图 1 左）：

{t2}

三代的分界很清楚：**2007-09 单标签**（无标签率 <16%、中位 1 个）→ **2010-14 空窗**
（无标签率 {yr.loc[2010:2014, 'zero'].mean():.0f}%）→ **2015-16 过渡**（
{yr.loc[2015, 'zero']:.0f}% → {yr.loc[2016, 'zero']:.0f}%）→ **2017 起受控多标签**
（无标签率 <3%，中位 3 个，2025 年升至 5 个）。全库合计 {n_zero:,} 行零标签，
几乎全部落在空窗期。

这解释了一件容易误读的事：**「标签覆盖率上升」不是作者变勤快，而是平台把标签
从可选变成必填**。报告 04 记「标签体系约 2014 上线」，从本表看更准确的说法是
**2015-16 逐步强制、2017 完全强制**。

### 1.1 词表不是稳定的：2022 年断层与 2023-24 换血

图 1 右给出每个标签的活跃区间（年使用 ≥20 次算活跃），其中藏着两个事件：

**其一，2022 年断层**。{len(died)} 个标签在 2022 年及以前每年使用 ≥20 次、
2023 与 2024 两年同时沉寂：{died_str}。几乎全部是**同人 IP 专属词**（型月、舰娘、
火影、约战、幻想乡、神奇宝贝、海贼、假面骑士、女武神、舰长、刀客塔）与
**亚文化口味词**（爽文、轻松、玩梗、多女主、单女主、黑化、克苏鲁、暗黑、末日、
硬核）——其中「末日」的退场与报告 04 §4「末日标签 2023 年起疑似退出使用」
相互印证。含这些标签的书从 2022 年的 1,665 本骤降到 2023 年的 23 本——
**这不是读者口味消失，而是词表被清理**：同期「同人」本身不降反升（2023 年
3,595 本创峰值），说明同人书还在投，只是不再挂 IP 词。最可能的解释是平台对
词表收紧管理（IP 词的版权风险或词表去重）；2026 年含「死亡」标签的书回升到
523 本，提示部分恢复或批量回填，需要另行核实。

**其二，2023-24 换血**。{len(born)} 个标签在 2022 年沉寂、2024 年重新活跃：
{born_str}。同期橘味（2022 年 89 本 → 2024 年 2,894 本）、变身（73 → 2,663）、
追夫（5 → 372）爆发式增长。**退场的几乎全是男性向亚文化词，进场与爆发的
几乎全是女性向词**——报告 04 §2 记录的「女性向转向」，在词表层面是一次
明确的、由运营主导的编辑行为，而非作者自发的渐变。"""


def sec_cooccur(fig, top_pairs, low_pairs, ip, n_used, OE_flat, hub_df) -> str:
    rows = [[a, b, f"{v:.1f}", f"{c:,}"] for v, c, a, b in top_pairs]
    t1 = md_table(rows, ["标签 A", "标签 B", "O/E", "共现书数"])
    rows2 = [[a, b, f"{v:.2f}", f"{c:,}"] for v, c, a, b in low_pairs]
    t2 = md_table(rows2, ["标签 A", "标签 B", "O/E", "共现书数"])
    ip_rows = [[t, f"{v:.1f}", f"{c:,}"] for v, c, t in ip]
    t3 = md_table(ip_rows, ["与「同人」共现的标签", "O/E", "共现书数"])
    def H(t: str) -> float:
        return float(hub_df.loc[hub_df["tag"] == t, "hub"].iloc[0])

    hub_top = hub_df.head(6)
    hub_low = hub_df.tail(6).iloc[::-1]
    t4 = md_table([[r.tag, f"{r.hub:.2f}", f"{int(r.n):,}"] for r in hub_top.itertuples()],
                  ["专用件", "加权平均 O/E", "频次"])
    t5 = md_table([[r.tag, f"{r.hub:.2f}", f"{int(r.n):,}"] for r in hub_low.itertuples()],
                  ["通用配料", "加权平均 O/E", "频次"])
    return f"""## 2. 共现：IP 微标签、互斥与通用配料

![](figures/09_cooccur.png)

把 {n_used} 个标签按簇排序后，O/E 矩阵沿对角线出现 8 个强红的块：**块内共现远超
随机期望，块间明显偏蓝（低于期望）**。标签之间的关联是块状的、且互斥的，不是
弥散的；接近白色的「中性对」反而占少数。左侧色条与图例标出 8 个簇（成员名单见 §3 表）。

### 2.1 最强关联全部是同人 IP

{t1}

`女武神 × 舰长` 的 O/E 高达 {top_pairs[0][0]:.0f}（{top_pairs[0][1]} 本）——这两个词
在词表里唯一的作用就是标记「崩坏3 同人」。与之同类的还有型月、舰娘、火影、
幻想乡、约战、刀客塔、假面骑士、神奇宝贝、海贼：**它们不是题材，是 IP**。

（注意：这些 IP 标签已于 2022 年从词表退场（§1.1），因此本表与图 2 中同人块的
共现结构描述的是 **2017-2022 年的词表制度**。）

「同人」与各 IP 标签的关联（O/E）：

{t3}

这构成一个两层结构：**`同人` 是命名空间，IP 名是其中的键**。同人小说的读者不是
按题材找书，而是按作品找书——这解释了为什么同人书的收藏中位最高（报告 05）、
活跃率最低（一次性投稿货架）：它的需求端是 IP 流量，供给端是一次性消费。

### 2.2 互斥：同人是另一套供给

{t2}

最弱的 8 对里有 5 对涉及「同人」：`同人 × 现实` O/E 仅 {low_pairs[-1][0]:.2f}
（{low_pairs[-1][1]} 本），`同人 × 纯爱` {[v for v, c, a, b in low_pairs if a == '同人' and b == '纯爱'][0]:.2f}，
`同人 × 致郁`、`同人 × 橘味`、`同人 × 变身` 同样低。另 3 对
（`日常 × 战争`、`搞笑 × 战争`、`热血 × 倒追`）是**语义的自然排斥**，与同人那组
不同类。

两类互斥要分开读：语义排斥（战争 vs 日常）证明标签体系是自洽的；供给模式排斥
（同人 vs 原创向）证明**同人是一条独立的产品线**，而非「魔幻类的一个子类」。

### 2.3 通用配料与专用件

![](figures/09_hub.png)

每个标签的「加权平均 O/E」（以共现量为权重）衡量它的共现平均落在随机期望的
多少倍：远大于 1 说明它只在特定组合里出现，接近 1 说明与谁搭配都正常。

{t4}

{t5}

**通用配料**是高频、低关联的一组（日常 {H('日常'):.2f}、搞笑 {H('搞笑'):.2f}、无敌
{H('无敌'):.2f}）：它们与任何标签搭配都在期望附近，因此**不能作为题材信号**——
一本书挂了「日常」，你仍然不知道它是什么书。

**专用件**是低频、高关联的一组（暗黑 {H('暗黑'):.2f}、克苏鲁 {H('克苏鲁'):.2f}、
硬核 {H('硬核'):.2f}）：它们几乎只与固定的少数标签同现，是**口味标记**。这类标签
数量少，却是检索时信息量最大的一批——用它们筛选比用「战斗」「日常」有效得多。

图 3 右的分布：O/E>2 的标签对占 {pct((OE_flat > 1).mean() * 100, 0)}%、O/E<0.5 的占
{pct((OE_flat < -1).mean() * 100, 0)}%——共现既不随机也不均匀，而是
**「强关联少数 + 互斥少数 + 大量中性」的三段式**。"""


def sec_space(fig, tags, lb, names, n, st, sil) -> str:
    rows = []
    for c in sorted(set(lb.tolist())):
        mem = sorted([tags[i] for i in range(len(tags)) if lb[i] == c],
                     key=lambda t: -int(n[tags.index(t)]))
        rows.append([names[c], str(len(mem)), f"{int(n[[tags.index(t) for t in mem]].sum()):,}",
                     "、".join(mem[:8]) + ("…" if len(mem) > 8 else "")])
    t1 = md_table(rows, ["语义区", "标签数", "覆盖书数（累计）", "主要标签"])
    best = st.sort_values("conv", ascending=False)
    return f"""## 3. 八个语义区：空间是连续的，切分是人造的

![](figures/09_space.png)

把对称条件概率当作相似度做谱嵌入，得到图 4。点的大小是频次，颜色是谱聚类的结果。
轮廓系数只有 **{sil:.2f}**——这不是聚类失败，而是数据在说：**题材空间是连续谱**。
读者能感到「战斗」和「日常」是两种书，但词表里没有一条清晰的边界。

八个区及其成员：

{t1}

几点观察：

- **「男性向冒险」区最大**（{int((lb == lb[tags.index('战斗')]).sum())} 个标签），
  战斗、异世界、冒险、无敌、系统、升级彼此高度关联，是平台的**默认类型**；
- **「同人 IP 群」独立成区**，与其余各区几乎不共现（§2.2）；
- **「女性向变身」与「乙女追妻」是两个不同的区**：前者是女性主角+橘味+魔法少女
  的**视角**聚类，后者是倒追+追夫+女尊+师尊的**关系**聚类。女性向内部已经分化出
  「谁在看」和「看什么关系」两条轴，这是 2023 年后最明显的结构变化（报告 04 §2）；
- **「悬疑脑洞」「暗黑硬核」是两个小但紧密的区**，成员少、块内 O/E 高，
  是典型的**口味社区**（而非人口学细分）。

按同曝光档（400-1.5k 点击）的转化率排序：最高 {names[best.iloc[0]['cluster']]}
（{best.iloc[0]['conv']:.2f}%），最低 {names[best.iloc[-1]['cluster']]}
（{best.iloc[-1]['conv']:.2f}%）。差距仍在 1.5 倍量级——与报告 08 §4 的结论一致：
**题材解释的方差远小于曝光**。"""


def sec_mismatch(fig, st, names, sub) -> str:
    rows = []
    for r in st.itertuples():
        rows.append([names[r.cluster], f"{int(r.n):,}", f"{r.supply * 100:.1f}",
                     f"{r.fav_share * 100:.1f}", f"{r.ratio:.2f}",
                     f"{r.favs_med:,.0f}", f"{r.words_med / 1e4:.1f}", f"{r.conv:.2f}",
                     f"{r.mp_n}（{r.mp_rate:.2f}）", f"{r.hot_n}（{r.hot_rate:.2f}）"])
    t1 = md_table(rows, ["语义区", "书数", "供给 %", "收藏份额 %", "收藏/供给", "收藏中位",
                         "字数中位（万）", "转化率 %", "月票榜（率 %）", "热销榜（率 %）"])
    rows2 = [[names[r.cluster], f"{r.vip:.0f}", f"{r.done:.0f}", f"{r.stale:.0f}",
              f"{r.contest:.0f}"] for r in st.itertuples()]
    t2 = md_table(rows2, ["语义区", "VIP %", "完结率 %", "断更 >1 年 %", "征文参与 %"])
    top, bottom = st.iloc[0], st.iloc[-1]
    n_hi = int(st[st["ratio"] > 1]["n"].sum())
    by_name = {names[r.cluster]: r for r in st.itertuples()}
    nv, nz, nr = by_name["女性向变身"], by_name["乙女追妻"], by_name["同人 IP 群"]
    return f"""## 4. 供需错配：谁以少占多，谁供过于求

![](figures/09_mismatch.png)

把每个语义区的书按「标签票数最多」归入一区（跨区书归入标签更多的那个区），
再与收藏、榜单、生命周期交叉：

{t1}

{t2}

读法：

- **「收藏/供给」比值是本节的中心量**：比值 {top['ratio']:.2f} 的
  「{names[top['cluster']]}」用 {top['supply'] * 100:.1f}% 的供给拿到
  {top['fav_share'] * 100:.1f}% 的收藏；比值仅 {bottom['ratio']:.2f} 的
  「{names[bottom['cluster']]}」用 {bottom['supply'] * 100:.1f}% 的供给只拿到
  {bottom['fav_share'] * 100:.1f}%。**收藏/供给 > 1 的区合计只提供
  {n_hi:,} 本书（{n_hi / len(sub) * 100:.1f}% 的供给），却拿走
  {st[st['ratio'] > 1]['fav_share'].sum() * 100:.1f}% 的收藏。**
- **注意力错配与付费错配同向，但付费错配更陡**：图 5 右的月票榜与热销榜上榜书数
  在「{names[top['cluster']]}」（{top['mp_rate']:.2f}% / {top['hot_rate']:.2f}%）与
  「{names[bottom['cluster']]}」（{bottom['mp_rate']:.2f}% / {bottom['hot_rate']:.2f}%）
  之间相差一个数量级。月票榜总共只有 694 本书上过（报告 07 §1），所以每个区的
  上榜书都是两位数以内的个例——**这不是「题材决定付费」，而是「少数书撑起一个区」**。
- **两个女性向区是同一种错配的两面**：「女性向变身」字数中位
  {nv.words_med / 1e4:.1f} 万字、收藏中位 {nv.favs_med:,.0f}、断更率
  {nv.stale:.0f}%（全表最低）、征文参与率 {nv.contest:.0f}%；「乙女追妻」VIP 率
  {nz.vip:.0f}%（全表最高）、征文参与率 {nz.contest:.0f}%（全表最高）。
  前者是**长线连载**，后者是**赛事驱动**——同一个读者群的两条供给路径。
- **同人区的形态完全相反**：{nr.n:,} 本、断更率 {nr.stale:.0f}%、
  征文参与率 {nr.contest:.0f}%（全表最低）、十六年只有 {int(nr.mp_n)} 本上过月票榜。
  它不参与任何运营机制，也不追求完结，是**纯粹的 IP 消费**。

一个必须写明的限制：每个区都是混合体。区的上榜率高可能是区内极少数书撑起来的，
不能读作「这个题材更容易付费」。本报告只做结构描述。"""


def sec_mix(mix, mix_r, sub) -> str:
    rows = []
    for k in sorted(mix.index):
        if k == 0 or mix.loc[k, "n"] < 100:
            continue
        rows.append([f"{int(k)} 个", f"{int(mix.loc[k, 'n']):,}",
                     f"{mix.loc[k, 'n'] / len(sub) * 100:.1f}",
                     f"{mix.loc[k, 'favs']:,.0f}", f"{mix.loc[k, 'favs_ctl']:,.0f}",
                     f"{mix_r.get(k, float('nan')):.2f}"])
    t1 = md_table(rows, ["标签跨的区数", "书数", "占比 %", "收藏中位（全体）",
                         "收藏中位（同档同字数）", "同档转化率 %"])
    r1 = mix_r.get(1, float("nan"))
    r3 = mix_r.get(3, float("nan"))
    return f"""## 5. 混合度：多贴几个标签不制造读者

每本书的标签可能落在不同语义区。按「标签跨几个区」分组：

{t1}

只看「收藏中位（全体）」会得出「跨区越多越受欢迎」（5 → 22），但这是**混杂**：
跨区书几乎都是 2022 年后的多标签书，字数更长、曝光更大。把样本限制在
「同曝光档（400-1.5k 点击）+ 同字数档（5-20 万字）」后，差异收敛到
{mix.loc[1, 'favs_ctl']:,.0f} → {mix.loc[3, 'favs_ctl']:,.0f}；转化率则几乎不动
（{r1:.2f}% → {r3:.2f}%）。

结论与报告 08 §4 一致：**标签的组合方式对互动几乎没有解释力**。标签的价值在
「检索与匹配」（读者按标签找书），不在「质量信号」。"""


def sec_bounds() -> str:
    return """## 6. 口径边界

1. **标签是运营词表，不是作者意图**：同一本书的标签可能由编辑补填或批量调整，
   本报告无法区分「作者选」与「平台配」。
2. **共现 ≠ 因果**：O/E 高只表示两词常被同时使用，不表示其中一个导致另一个。
   IP 微标签与「同人」的关系是**定义性的**（同人书必须挂作品名），不是发现。
3. **2017 年之前不可比**：空窗期的书多数无标签，把它们纳入会系统性低估早期题材
   的多样性；本报告已排除，代价是无法回答「2010-14 的题材结构与现在差别多大」。
   同时 2017-2026 也并非同一制度：2022 年词表断层（§1.1）意味着同人 IP 块的
   共现结构由 2017-22 年贡献，2023 年之后的同人书不再挂 IP 词——若只看
   2023+ 的数据，图 2 的同人块会大面积消失。
4. **定年误差**：low 段（nid < 61,157）月级误差可达 ±50 天，跨年边界处会影响
   年度归属，但不影响共现结构（共现不依赖时间）。
5. **聚类切分是人为的**：k=8 依据可解释性选定，轮廓系数极低意味着任何 k 都不比
   其他 k 更「正确」；换 k 会改变各区的份额，但不改变块状结构本身。
6. **下架删失**：数据集是 2026-05-03 的在册快照，历年下架的书（月票榜侧 2013-14
   占 28-31%，报告 07 §1）不在样本内，早期题材结构因此偏向「活下来的书」。
"""


if __name__ == "__main__":
    main()

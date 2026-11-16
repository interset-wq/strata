"""报告 19 数据预演：5 万字口径全链重算。"""
import sys, json, re
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import config, eras

df = pd.read_csv(BASE / "out/novels.csv")
df = df[~df.author.isin(config.LICENSED_LN_AUTHORS)].copy()
df["contest"] = df.contest.fillna("")
df["updated_at"] = pd.to_datetime(df.updated_at, errors="coerce")
df["done"] = df.status == "已完结"
df["tier"] = np.where(df.contest.str.contains("短篇"), "短篇",
              np.where(df.contest.str.contains("中篇"), "中篇",
              np.where(df.contest.str.contains("长篇"), "长篇",
              np.where(df.contest.str.contains("对话"), "对话", ""))))
df = df.merge(eras.estimate(df["id"].values)[["id", "est_date", "est_year"]],
              on="id", how="left")
df["finish_days"] = (df.updated_at - pd.to_datetime(df.est_date)).dt.days
df["fast"] = df.done & df.finish_days.between(0, 7)
df["pr"] = df.praises / df.favs.replace(0, np.nan)
df["cvr"] = df.favs / df.clicks.replace(0, np.nan)

THR = 50000
SHORT = (df.words <= THR) & df.done
s = df[SHORT].copy()
WB = [0, 3000, 6000, 10000, 20000, 50001]
WL = ["≤3k", "3-6k", "6-10k", "10-20k", "20-50k"]
s["wb"] = pd.cut(s.words, WB, labels=WL, right=True)

print(f"=== 5 万字口径 ===")
print(f"  短篇（≤{THR//10000}万字 且 已完结）: {len(s):,} 本，占全库 {len(s)/len(df)*100:.1f}%")
print(f"  速更占比: {s.fast.mean()*100:.1f}%")
print(f"  官方短篇赛项落在区间内: {(df[(df.tier=='短篇')&df.done].words<=THR).mean()*100:.1f}%")
for t in ["中篇", "长篇", "对话"]:
    g = df[(df.tier == t) & df.done]
    if len(g): print(f"  官方{t}赛项落在区间内: {(g.words<=THR).mean()*100:.1f}%（n={len(g):,}）")
g = df[(df.tier == "短篇") & df.done]
print(f"  区间内含官方短篇赛项书: {int((s.tier=='短篇').sum()):,} 本 ({(s.tier=='短篇').mean()*100:.1f}%)")
print(f"  区间内含官方中篇赛项书: {int((s.tier=='中篇').sum()):,} 本 ({(s.tier=='中篇').mean()*100:.1f}%)")
print(f"  区间内含官方长篇赛项书: {int((s.tier=='长篇').sum()):,} 本 ({(s.tier=='长篇').mean()*100:.1f}%)")

print("\n=== 字数档结构 ===")
t = s.groupby("wb", observed=True).agg(n=("id", "size"), fast=("fast", "mean"),
                                       fav=("favs", "median"), clk=("clicks", "median"),
                                       pr=("pr", "median"))
print(t.to_string())

print("\n=== 收藏天花板（5 万字口径）===")
for k in ["favs", "clicks", "praises"]:
    v = s[k]
    print(f"  {k:<8} 非零={ (v>0).mean()*100:5.1f}%  p50={v.median():>8,.0f}  p95={v.quantile(.95):>10,.0f}  max={v.max():>10,.0f}")
for th in [50, 100, 200, 500, 1000]:
    print(f"  favs ≥ {th:>4}: {int((s.favs>=th).sum()):>6,} 本 ({(s.favs>=th).mean()*100:5.2f}%)")
L = df[(df.words > THR) & df.done]
print(f"  对照长篇: favs p50={L.favs.median():,.0f} p95={L.favs.quantile(.95):,.0f} max={L.favs.max():,.0f}")
print(f"  收藏 ≥1万 的短篇: {int((s.favs>=10000).sum())} 本；长篇 {int((L.favs>=10000).sum())} 本")

print("\n=== 排序刻度：favs 绝对值 vs 双组分位 ===")
s["grp"] = s.wb.astype(str) + "|" + s.est_year.astype(str)
def pctl(frame, key):
    r = frame.groupby(key, observed=True)["favs"].rank(ascending=True, method="average")
    n = frame.groupby(key, observed=True)["favs"].transform("size")
    return r / n
s["p_wb"] = pctl(s, "wb")
s["p_grp"] = pctl(s, "grp")
for k, lab in [("favs", "favs 绝对值"), ("p_wb", "字数档内分位"), ("p_grp", "字数档×世代 双组")]:
    t = s.sort_values(k, ascending=False).head(30)
    print(f"  {lab:<18} favs中位={t.favs.median():>7.0f} words中位={t.words.median():>8,.0f} "
          f"年份={t.est_year.min()}-{t.est_year.max()} 速更={t.fast.mean()*100:.0f}% 官方短篇赛项={(t.tier=='短篇').mean()*100:.0f}%")

print("\n=== 否定结论重算（5 万字口径）===")
s["fb"] = pd.cut(s.finish_days, [-1, 7, 30, 90, 365, 10**9],
                 labels=["0-7", "8-30", "31-90", "91-365", ">365"])
s["cell"] = s.wb.astype(str) + "|" + s.fb.astype(str)
agg = []
for cell, g in s.groupby("cell", observed=True):
    g = g.dropna(subset=["pr"])
    if len(g) < 150: continue
    agg.append({"cell": cell, "n": len(g),
                "hi_f": g[g.pr >= g.pr.quantile(.95)].favs.median(),
                "lo_f": g[g.pr <= g.pr.quantile(.05)].favs.median(),
                "hi_c": g[g.pr >= g.pr.quantile(.95)].clicks.median(),
                "lo_c": g[g.pr <= g.pr.quantile(.05)].clicks.median()})
a = pd.DataFrame(agg)
print(f"  赞藏比 pr: top5% favs中位 {a.hi_f.mean():.1f} vs bot5% {a.lo_f.mean():.1f} "
      f"| clicks {a.hi_c.mean():.0f} vs {a.lo_c.mean():.0f}  （n_cell={len(a)}）")
agg2 = []
for cell, g in s.groupby("cell", observed=True):
    g = g.dropna(subset=["cvr"])
    if len(g) < 150: continue
    agg2.append({"hi_f": g[g.cvr >= g.cvr.quantile(.95)].favs.median(),
                 "lo_f": g[g.cvr <= g.cvr.quantile(.05)].favs.median(),
                 "hi_c": g[g.cvr >= g.cvr.quantile(.95)].clicks.median(),
                 "lo_c": g[g.cvr <= g.cvr.quantile(.05)].clicks.median()})
a2 = pd.DataFrame(agg2)
print(f"  转化率 cvr: top5% favs中位 {a2.hi_f.mean():.1f} vs bot5% {a2.lo_f.mean():.1f} "
      f"| clicks {a2.hi_c.mean():.0f} vs {a2.lo_c.mean():.0f}  （n_cell={len(a2)}）")

print("\n=== 口碑层画像（favs≥200）===")
hi = s[s.favs >= 200]
print(f"  n={len(hi):,}  字数中位={hi.words.median():,.0f}  速更={hi.fast.mean()*100:.1f}%  "
      f"官方短篇赛项={(hi.tier=='短篇').mean()*100:.1f}%  pr中位={hi.pr.median():.2f}  年份跨度={hi.est_year.min()}-{hi.est_year.max()}")
print("  题材分布:", hi.genre.value_counts().head(8).to_dict())
print("  完结时长档:", hi.fb.value_counts(normalize=True).round(3).to_dict())
print(hi.sort_values("favs", ascending=False)[["id", "title", "author", "words", "favs", "clicks", "est_year"]].head(8).to_string(index=False))

print("\n=== 种子覆盖（5 万字口径）===")
CONTENT_END = pd.Timestamp("2026-05-03")
d = df[df.est_year.between(2007, 2025)].copy()
seed = set(d.nlargest(20000, "favs").id)
seed |= set(d[d.est_date >= CONTENT_END - pd.Timedelta(days=365)].id)
seed |= set(d[d.updated_at >= CONTENT_END - pd.Timedelta(days=90)].id)
ranks = set()
with open(BASE / "out/monthly_ranks.jsonl", encoding="utf-8") as fh:
    for line in fh:
        for it in json.loads(line)["items"]:
            if it.get("nid"): ranks.add(it["nid"])
seed |= (ranks & set(d.id)) | set(d.loc[d.featured == 1, "id"])
print(f"  种子 n={len(seed):,}（报告 18 为 29,396）")
sd = d[d.id.isin(seed)]
ss = sd[(sd.words <= THR) & sd.done]
allshort = df[SHORT]
print(f"  种子里短篇: {len(ss):,} 本 ({len(ss)/len(seed)*100:.1f}%)，覆盖全部短篇 {len(ss)/len(allshort)*100:.1f}%")
for th in [100, 200]:
    a1 = int((allshort.favs >= th).sum()); a2_ = int((ss.favs >= th).sum())
    print(f"  口碑层 favs≥{th}: 全库 {a1:,}，种子 {a2_:,} → 覆盖 {a2_/a1*100:.1f}%")

print("\n=== 补短篇双组分位 Top N ===")
for N in [1000, 2000, 3000]:
    top = s.sort_values("p_grp", ascending=False).head(N)
    need = (~top.id.isin(seed)).sum()
    add = top[~top.id.isin(seed)]
    newcov = int((ss.favs >= 200).sum() + (add.favs >= 200).sum())
    print(f"  Top{N:<5} 已在种子 {N-need:>5}  需补 {need:>5} 体积+{need*381/1048576:.2f}MB  "
          f"补后 favs≥200 覆盖 {newcov}/{int((allshort.favs>=200).sum())} = {newcov/(allshort.favs>=200).sum()*100:.1f}%")

print("\n=== 短篇的世代趋势 ===")
g = s.groupby("est_year").agg(n=("id", "size"), fav=("favs", "median"), fast=("fast", "mean"))
print(g.to_string())

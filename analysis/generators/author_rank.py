"""作者榜正式生成器：按 form 隔离、绝对收藏 + 代表作完结率，≥3 本有效作品。

权威口径：docs/author-rank.md。修改口径须同步改文档与本文，不改预览产物。

口径（用户定）：
- 作者榜用于选「稳定产出的优质作者」；某 form 作品 <3 本视为不能稳定
  产出，不进该 form 榜。只有稳定产出的作者，其粉丝群体才有意义。
- **有效中短篇（E.31 + P10 + E.32 + E.34）**：short/medium 必须 status=已完结、
  征文不含「长篇」，且 nid 落在中短篇赛事 roster union 内（唯一豁免 =
  `seed_manual_exempt.jsonl` 中 `waive="contest"`）；人工黑名单逐本剔除。
  任一不满足即从所有形态榜剔除。`lib/forms.py` 的 form 是纯作品属性、不随
  status/赛事变，作者榜必须另套这套收录资格规则，否则连载中或假中短篇会
  混进榜。因此 short/medium 榜里的作品必然全完结且在赛事池内，完结率恒 100%。
- 只看绝对数值判断受欢迎程度：用该 form 收藏最高的 3 本的收藏和。
- 完结率判断「值得信赖」：代表作（这 3 本）中已完结的比例作为折扣。
  信赖加权分 = top3 收藏和 × (BASE_KEEP + (1-BASE_KEEP) × 完结率)；
  完结率 1 不打折，0 只保留 BASE_KEEP，连载代表作直接拉低排名。
  （对 long/dialogue/ip_collab 有区分度；short/medium 因上述门槛恒 1）
- form 隔离：每张榜只用该 form 的作品；同一作者可在多张 form 榜出现。
- 身份用作者名 casefold 保空格（分析口径无 authorId，改名/马甲未合并）。

已知限制：favs 混书龄/曝光、累计跨时点不可比；status 是快照状态（跨时点
生命态要另看 updated_at）。这里只用于作者榜相对排序（用户裁定口径），
禁回流书榜打分。数字为快照现算、随版本变化。不改数据集/种子/正式文档。

用法：uv run --project analysis python analysis/generators/author_rank.py
输出：analysis/out/author_rank_preview.html（含守门断言，失败即中止）
"""
from __future__ import annotations

import html
import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "out"))

from lib import contest_scope as CS  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "r24", ROOT / "generators" / "report_24_runtime_metrics.py")
r24 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r24)

# CSS/JS 壳（analysis/out/gen_report24_top200.py）仅预览 HTML 需要，在
# main() 里惰性加载：seed builder（app/tools/seedbuild/build_seed.py）从
# 本模块 import build_author_frame / app_seed_rows，不得依赖 out/ 产物存在。
FORM_CN = r24.FORM_CN
FORM_ORDER = r24.FORMS
MIN_BOOKS = 3       # 该 form 至少 3 本才算稳定产出
TOP_N = 3           # 取该 form 收藏最高的 3 本
BASE_KEEP = 0.4     # 完结率为 0 时保留的收藏权重（不全盘否决）


def num(x) -> str:
    return f"{int(x):,}"


def _reps(x) -> str:
    return "<br>".join(
        f"{html.escape(str(r.title))} <span class='rid'>{int(r.id)} · 收藏 {num(r.favs)}"
        f" · <span class='{'fin' if r.finished else 'ongoing'}'>"
        f"{'完结' if r.finished else '连载'}</span></span>"
        for r in x.sort_values("favs", ascending=False).itertuples()
    )


def _effective_mask(d: pd.DataFrame) -> pd.Series:
    """E.31 + P10 + E.32 + E.34：有效中短篇的四条硬门槛。

    与 `app/tools/seedbuild/seed_policy.py` 的 `abandoned_ids` /
    `fake_complete_ids` / `manual_blacklist_ids` /
    `short_medium_outside_contest_ids` 同一套确定性规则，
    只作用 short/medium；long/dialogue/ip_collab 不剔除。赛事 union 只决定
    能否进池，不决定 short 还是 medium（《少女与龙》挂短篇赛道却是 medium）。
    """
    length = d["form"].isin(("short", "medium")).to_numpy()
    serial = d["status"].ne("已完结").to_numpy()
    fake = d["contest"].fillna("").astype(str).str.contains("长篇", regex=False).to_numpy()
    in_pool = d["id"].isin(CS.short_medium_nids()).to_numpy()
    waived = d["id"].isin(CS.contest_waived_nids()).to_numpy()
    outside = length & ~in_pool & ~waived
    blacklisted = d["id"].isin(CS.manual_blacklist_nids()).to_numpy()
    return ~((length & (serial | fake)) | outside | blacklisted)


def build_author_frame():
    d, _ = r24.load()
    d = d[_effective_mask(d)].copy()
    d["akey"] = d["author"].astype(str).str.casefold()
    d["finished"] = (d["status"] == "已完结").astype(int)
    d = d.sort_values(["akey", "form", "favs", "id"],
                      ascending=[True, True, False, True])
    d["rk"] = d.groupby(["akey", "form"]).cumcount() + 1

    counts = d.groupby(["akey", "form"]).size().rename("n_books").reset_index()
    year = d.groupby(["akey", "form"])["est_year"].max().rename("year").reset_index()
    top = d[d["rk"] <= TOP_N].copy()
    stat = top.groupby(["akey", "form"]).agg(
        fav_sum=("favs", "sum"),
        fav_top=("favs", "max"),
        finished=("finished", "sum"),
    ).reset_index()
    reps = (top.groupby(["akey", "form"])
            .apply(_reps, include_groups=False).rename("reps").reset_index())

    pv = (stat.merge(counts, on=["akey", "form"])
          .merge(year, on=["akey", "form"])
          .merge(reps, on=["akey", "form"]))
    pv = pv[pv["n_books"] >= MIN_BOOKS].copy()
    pv["finish_rate"] = pv["finished"] / TOP_N
    pv["score"] = pv["fav_sum"] * (BASE_KEEP + (1 - BASE_KEEP) * pv["finish_rate"])

    # 各形态作品数（含未达门槛的形态），用于看跨形态产出分布
    order = {f: i for i, f in enumerate(FORM_ORDER)}
    cross = {}
    for a, sub in counts.groupby("akey"):
        sub = sub.sort_values("form", key=lambda s: s.map(order))
        cross[a] = " ".join(
            f"{FORM_CN.get(f, f)[:1]}{int(n)}" for f, n in zip(sub["form"], sub["n_books"])
        )
    pv["display"] = pv["akey"].map(d.groupby("akey")["author"].first())
    pv["cross"] = pv["akey"].map(cross)
    scoreable = [f for f in FORM_ORDER if not pv[pv["form"] == f].empty]
    _assert_guards(d, pv)
    return pv, scoreable


def _assert_guards(d: pd.DataFrame, pv: pd.DataFrame) -> None:
    """docs/author-rank.md §8 守门断言：失败即中止，不产出榜单。"""
    # 1. 中短篇有效作品零连载、零假完结
    short_medium = d[d["form"].isin(("short", "medium"))]
    assert (short_medium["status"] == "已完结").all(), (
        f"有效中短篇混入连载书 {int((short_medium['status'] != '已完结').sum())} 本")
    assert not short_medium["contest"].fillna("").astype(str).str.contains(
        "长篇", regex=False).any(), "有效中短篇混入征文含「长篇」的假完结书"
    allowed = CS.short_medium_nids() | CS.contest_waived_nids()
    outside = short_medium[~short_medium["id"].isin(allowed)]
    assert outside.empty, f"有效中短篇不在赛事 union: {len(outside)} 本"
    assert d["id"].isin(CS.manual_blacklist_nids()).sum() == 0, "人工黑名单书混入作者榜"
    # 2. 每榜每位作者有效作品数 >= MIN_BOOKS
    assert (pv["n_books"] >= MIN_BOOKS).all(), (
        f"入榜作者作品数 < {MIN_BOOKS}: {int((pv['n_books'] < MIN_BOOKS).sum())} 行")
    # 3. 收藏和 >= 最高单本（top3 聚合的基本一致性）
    assert (pv["fav_sum"] >= pv["fav_top"]).all(), "top3 收藏和小于最高单本收藏"
    # 4. 完结率 ∈ [0,1]，short/medium 恒 1
    assert pv["finish_rate"].between(0, 1).all(), "完结率越界"
    for fm in ("short", "medium"):
        z = pv[pv["form"] == fm]
        if len(z):
            assert (z["finish_rate"] == 1).all(), f"{fm} 榜完结率非恒 1"
    # 5. 表名与分数非空
    assert pv["display"].notna().all() and pv["score"].notna().all(), "作者名或分数缺失"


def table(z: pd.DataFrame, tid: str) -> str:
    head = ["#", "作者", "本形态作品数", "信赖加权分", f"top{TOP_N} 收藏和",
            "代表作完结率", "最高单本收藏", "各形态作品数", "近作年",
            f"代表作（本形态 top{TOP_N}）"]
    th = "".join(f"<th>{html.escape(c)}</th>" for c in head)
    body = []
    for rank, (_, r) in enumerate(z.nlargest(100, "score").iterrows(), 1):
        cells = [str(rank), html.escape(str(r["display"])), num(r["n_books"]),
                 f"<b class='score'>{num(r['score'])}</b>", num(r["fav_sum"]),
                 f"{int(r['finished'])}/{TOP_N} ({r['finish_rate']:.0%})",
                 num(r["fav_top"]), html.escape(str(r["cross"])),
                 str(int(r["year"])), r["reps"]]
        body.append(f'<tr data-rate="{r["finish_rate"]:.2f}">'
                    + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    return (f'<table id="{tid}"><thead><tr>{th}</tr></thead><tbody>'
            + "".join(body) + "</tbody></table>")


def _load_css_js():
    g200_path = ROOT / "out" / "gen_report24_top200.py"
    if not g200_path.exists():
        raise SystemExit(f"preview needs {g200_path} (CSS/JS shell); missing")
    spec2 = importlib.util.spec_from_file_location("g200", g200_path)
    g200 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(g200)
    return g200.CSS, g200.JS


def app_seed_rows() -> list[tuple[str, int, str, int, str]]:
    """App 预构建表（docs/author-rank.md §9）：只落最小展示字段。

    返回 (form, rank_no, author, rep_nid, rep_title)。author 是原始显示名
    （/author?author= 精确匹配查询参数）；casefold 键只用于构建期去重，
    不进表。展示只露一本代表作（该 form 有效作品中 favs 第 1 本）；
    排名仍按 top3 收藏和 + 完结率折扣计算，证据列不落库。
    """
    pv, scoreable = build_author_frame()
    d, _ = r24.load()
    d = d[_effective_mask(d)].copy()
    d["akey"] = d["author"].astype(str).str.casefold()
    rows: list[tuple[str, int, str, int, str]] = []
    for fm in scoreable:
        z = (pv[pv["form"] == fm]
             .sort_values(["score", "akey"], ascending=[False, True])
             .head(100))
        for rank_no, r in enumerate(z.itertuples(index=False), 1):
            sub = d[(d["akey"] == r.akey) & (d["form"] == fm)]
            rep = sub.sort_values(["favs", "id"],
                                  ascending=[False, True]).iloc[0]
            rows.append((fm, rank_no, str(r.display),
                         int(rep["id"]), str(rep["title"])))
    # §9 守门：rank_no 每榜从 1 连续、字段非空、rep_nid > 0、总行数 ≤ 500。
    assert len(rows) <= 500, f"author rank rows {len(rows)} > 500"
    for fm, rank_no, author, rep_nid, rep_title in rows:
        assert author and rep_title and rep_nid > 0, (
            f"invalid author rank row ({fm}, {rank_no})")
    for fm in scoreable:
        nos = [rn for (f, rn, *_rest) in rows if f == fm]
        assert nos == list(range(1, len(nos) + 1)), (
            f"{fm} rank_no not contiguous from 1")
    return rows


def main() -> None:
    pv, scoreable = build_author_frame()
    css, js = _load_css_js()

    tabs = "".join(
        f'<button class="tab{" on" if i == 0 else ""}" data-t="{fm}">'
        f'{FORM_CN.get(fm, fm)} <span class="cnt">{num(len(pv[pv["form"] == fm]))}</span></button>'
        for i, fm in enumerate(scoreable)
    )
    panels = []
    for i, fm in enumerate(scoreable):
        z = pv[pv["form"] == fm]
        n_full = int((z["finish_rate"] >= 1).sum())
        pid = "t-" + fm
        extra = (" · 有效中短篇必须已完结，连载 / 假完结已剔除，完结率恒 100%"
                 if fm in ("short", "medium") else "")
        panels.append(
            f'<div class="panel{" on" if i == 0 else ""}" id="{fm}">'
            f'<div class="stat">本形态 ≥{MIN_BOOKS} 本作品的作者 {num(len(z))} 名 · '
            f'代表作全完结 {num(n_full)} 名 · '
            f'信赖加权分 = top{TOP_N} 收藏和 × ({BASE_KEEP}+{1 - BASE_KEEP:.1f}×完结率) · '
            f'只按本形态作品计算，同一作者可同时出现在其他形态榜{extra}</div>'
            f'<label class="strictbox"><input type="checkbox" class="full" '
            f'onchange="applyFilter(\'{pid}\')"> 只看代表作全完结</label>'
            f'<input class="search" placeholder="筛选作者 / 代表作" '
            f'oninput="applyFilter(\'{pid}\')">'
            + (table(z, pid) if len(z) else "<p>无数据</p>")
            + "</div>"
        )

    multi_authors = int((pv.groupby("akey")["form"].nunique() >= 2).sum())
    full_authors = int((pv["finish_rate"] >= 1).groupby(pv["akey"]).any().sum())
    total = " · ".join(
        f"{FORM_CN.get(f, f)} {num(len(pv[pv['form'] == f]))}" for f in scoreable
    )
    page_js = js + """
function applyFilter(pid){
  const root=document.getElementById(pid.replace(/^t-/,''));
  if(!root) return;
  const q=(root.querySelector('.search')?.value||'').trim().toLowerCase();
  const full=root.querySelector('.full')?.checked;
  root.querySelectorAll('tbody tr').forEach(tr=>{
    const okq=!q || tr.innerText.toLowerCase().includes(q);
    const okf=!full || Number(tr.dataset.rate||0)>=1;
    tr.style.display=okq&&okf?'':'none';
  });
}
"""
    page_css = (css + "\n.rid{color:var(--mut);font-size:11px;margin-left:5px}"
           ".fin{color:#067647}.ongoing{color:#b54708}"
           ".strictbox{display:inline-flex;align-items:center;gap:5px;margin:0 10px 10px 0;font-size:12px;color:var(--mut)}"
           "td:last-child{white-space:normal;min-width:340px}")
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>作者榜预览 · 绝对收藏 + 完结率</title>
<style>{page_css}</style></head><body><div class="wrap">
<h1>作者榜预览 · 按 form 隔离的信赖加权收藏榜</h1>
<div class="sub">复用报告24 定年 / form 现算 · 快照 2026-05-03 · 定年 2007–2025 · 数字随数据版本变化</div>
<div class="verify">目的：选<b>稳定产出的优质作者</b>。某 form 作品 <b>≥{MIN_BOOKS} 本</b>才进该 form 榜；只有稳定产出的作者，粉丝群体才有作用。<br>
<b>有效中短篇（E.31 + P10）</b>：short / medium 必须已完结；连载中或征文含「长篇」（假完结）的短 / 中篇不构成有效中短篇，已从所有榜剔除。`forms.py` 的 form 是纯作品属性、不随 status 变，作者榜另套这条收录资格规则。故 short / medium 榜内作品必然全完结、完结率恒 100%。<br>
受欢迎程度<b>只看绝对数值</b>：该 form 收藏最高的 {TOP_N} 本收藏和；<b>是否值得信赖</b>看代表作完结率——信赖加权分 = 收藏和 × ({BASE_KEEP}+{1 - BASE_KEEP:.1f}×完结率)，完结率 1 不打折、0 只保留 {BASE_KEEP:.0%}，连载代表作直接拉低排名。可切「只看代表作全完结」。<br>
form 隔离：同一作者在多形态都有成绩时会<b>同时出现在多张榜</b>，名次独立。合格作者：{total}；{num(multi_authors)} 名跨 ≥2 榜，{num(full_authors)} 名至少有一张榜代表作全完结。</div>
<div class="tabs">{tabs}</div>
{''.join(panels)}
<div class="note">
<b>为何用 top{TOP_N} 收藏和 × 完结率</b>：只看成绩最好的 {TOP_N} 本反映读者规模，不被写得多的作者靠数量堆高；{MIN_BOOKS} 本门槛保证不是偶然一本；完结率把「敢不敢把作品写完」计入信赖，避免高收藏但长期烂尾的作者靠粉丝爬到前面。<br>
<b>为什么不是硬门槛</b>：完结率 0 只打 {BASE_KEEP:.0%} 折而非直接剔除，连载中的头部作品仍有读者规模信号；需要严格信赖口径时勾选「只看代表作全完结」。<br>
<b>已知限制</b>：favs 混书龄 / 曝光、累计跨时点不可比；status 是快照状态（跨时点生命态另看 updated_at）。中短篇的假完结按 P10（征文含「长篇」）确定性剔除，其余作者自报完结仍可能有噪声。这里只用于作者榜相对排序（用户裁定口径），禁回流书榜打分。<br>
<b>身份边界</b>：身份键用作者名 casefold（保留空格），分析口径不含 authorId —— 覆盖 49.8% 的权威 id 与 11 组改名尚未接入，马甲 / 共用笔名无法合并，正式版需走裁定表。<br>
<b>展示约束</b>：作者榜只作「同一作者的其他作品」次级入口，不取代书榜主排序；form 是作品级属性，禁把作者主形态传播到每本书；同人独立建架；签约 / VIP 不做品质标签。
</div></div>
<script>{page_js}</script></body></html>"""

    out = ROOT / "out" / "author_rank_preview.html"
    out.write_text(page, encoding="utf-8")
    print(f"written: {out} ({len(page):,} chars)")
    for fm in scoreable:
        z = pv[pv["form"] == fm]
        print(f"{fm}: authors(>={MIN_BOOKS} books)={len(z)} "
              f"full-finish={int((z['finish_rate'] >= 1).sum())}")
        print("  top5:", [(r["display"], int(r["fav_sum"]),
                           f"{r['finish_rate']:.0%}", int(r["score"]))
                          for _, r in z.nlargest(5, "score").iterrows()])


if __name__ == "__main__":
    main()

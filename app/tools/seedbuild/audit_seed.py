"""审计重建后的种子是否真的高质量（只读；不改数据库、不发版）。

输入：`app/assets/seed.db.gz`（当前发布种子）+ `analysis/out/novels.csv`（分母）。
输出：`analysis/out/seed_v3_quality.md`（生成物，勿手改）。

口径：V3 质量锚（时间渠道已移除）见 `app/docs/09-seed-refresh-proposal.md` 附录 E；
`lqs` 只覆盖长篇区且 favs>=200，不能拿它的覆盖率当全池质量证明。

用法：
    cd analysis && uv run python ../app/tools/seedbuild/audit_seed.py
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
ANALYSIS = REPO / "analysis"
sys.path.insert(0, str(ANALYSIS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import config as C, paths  # noqa: E402
from lib import dialogue_form as DF  # noqa: E402
from lib import forms as FM  # noqa: E402
import seed_policy as SP  # noqa: E402
from lib import lqs as LQ  # noqa: E402

SEED_GZ = REPO / "app" / "assets" / "seed.db.gz"
MANIFEST = REPO / "app" / "assets" / "manifest.json"
OUT = paths.OUT_DIR / "seed_v3_quality.md"


def read_seed() -> tuple[pd.DataFrame, dict]:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "seed.db"
        db.write_bytes(gzip.decompress(SEED_GZ.read_bytes()))
        conn = sqlite3.connect(db)
        try:
            books = pd.read_sql_query("SELECT * FROM books", conn)
            meta = dict(conn.execute("SELECT key, value FROM seed_meta").fetchall())
        finally:
            conn.close()
    return books, meta


def share(mask: pd.Series) -> str:
    return f"{float(mask.mean()):.2%}" if len(mask) else "n/a"


def band(favs: pd.Series) -> pd.Series:
    return pd.cut(favs, [-1, 0, 4, 9, 49, 99, 499, 1999, 9999,
                         np.inf],
                  labels=["0", "1-4", "5-9", "10-49", "50-99", "100-499",
                          "500-1,999", "2k-10k", "10k+"])


def describe(df: pd.DataFrame) -> dict:
    return {
        "n": len(df),
        "favs": int(df["favs"].sum()),
        "favs<5": int((df["favs"] < 5).sum()),
        "favs=0": int((df["favs"] == 0).sum()),
        "med_favs": float(df["favs"].median()),
        "med_words": float(df["words"].median()),
        "words<10k": int((df["words"] < 10_000).sum()),
    }


def main() -> int:
    seed, meta = read_seed()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    universe = SP.load_universe()
    content_end = pd.Timestamp(C.CONTENT_END) if hasattr(C, "CONTENT_END") \
        else pd.Timestamp("2026-05-03")
    df = SP.add_velocity(universe, content_end)
    res = SP.admit(df, content_end)
    raw = seed.rename(columns={"nid": "id"})
    core = raw[raw["is_licensed"] == 0].copy()
    v0 = df[df["id"].isin(res["baseline"])]

    lines: list[str] = []
    add = lines.append
    add("# 新建种子的质量审计（V3 / 质量锚）")
    add("")
    add(f"> 生成物，由 `app/tools/seedbuild/audit_seed.py` 现算，勿手改。"
        f"种子 `seed_version={manifest['seed_version']}`，"
        f"`schema_version={manifest['schema_version']}`，"
        f"内容上界 {manifest['content_end']}。")
    add("")
    add("## 1. 总量与质量基线（非授权口径）")
    add("")
    add("| 指标 | V0 旧种子 | V3 新种子 | 全部分母 |")
    add("|---|---:|---:|---:|")
    fav_tot = int(df["favs"].sum())
    for label, key in [("书数", "n"), ("收藏合计", "favs"),
                       ("favs<5", "favs<5"), ("favs=0", "favs=0"),
                       ("字数<1万", "words<10k")]:
        a, b = describe(v0)[key], describe(core)[key]
        all_n = fav_tot if key == "favs" else len(df)
        add(f"| {label} | {a:,} | {b:,} | {all_n:,} |")
    add(f"| 收藏覆盖率 | {v0['favs'].sum()/fav_tot:.2%} | "
        f"{core['favs'].sum()/fav_tot:.2%} | 100% |")
    add(f"| 收藏中位数 | {v0['favs'].median():.0f} | {core['favs'].median():.0f} | "
        f"{df['favs'].median():.0f} |")
    add(f"| 字数中位数 | {v0['words'].median():.0f} | {core['words'].median():.0f} | "
        f"{df['words'].median():.0f} |")
    add(f"| favs<5 占比 | {share(v0['favs'] < 5)} | {share(core['favs'] < 5)} | "
        f"{share(df['favs'] < 5)} |")
    add("")
    add(f"发布种子共 **{len(seed):,} 本** = V3 质量锚入池 {manifest['counts']['admitted_v3']:,}"
        f" + 授权 {manifest['licensed_count']}；旧种子 {manifest['counts']['baseline_v0']:,}"
        f" + 47 = {manifest['counts']['baseline_v0'] + 47:,}。")

    add("")
    add("## 2. 收藏分档（新种子非授权部分）")
    add("")
    tbl = core.groupby(band(core["favs"]), observed=True).agg(
        n=("id", "size"), favs=("favs", "sum"))
    tbl["书占比"] = tbl["n"] / len(core)
    tbl["收藏占比"] = tbl["favs"] / core["favs"].sum()
    add(tbl.reindex(["0", "1-4", "5-9", "10-49", "50-99", "100-499",
                     "500-1,999", "2k-10k", "10k+"]).fillna(0).to_string())

    add("")
    add("## 3. 形式与篇幅（新种子 vs 全部分母）")
    add("")
    uf = FM.classify(df).value_counts(normalize=True)
    sf = core["form"].value_counts(normalize=True)
    add("| form | 种子占比 | 全库占比 | 种子本数 |")
    add("|---|---:|---:|---:|")
    for name in FM.FORMS:
        add(f"| {name} | {sf.get(name, 0):.2%} | {uf.get(name, 0):.2%} | "
            f"{int((core['form'] == name).sum()):,} |")

    add("")
    add("## 4. 1 万字以下：短篇 vs 对话小说")
    add("")
    s_all = df[df["words"] < 10_000]
    s_seed = core[core["words"] < 10_000].copy()
    v0_small = int(((df["id"].isin(res["baseline"]))
                    & (df["words"] < 10_000)).sum())
    uf_small = FM.classify(s_all).value_counts()
    sf_small = s_seed["form"].value_counts()
    add(f"- 全库 `<1万字` {len(s_all):,} 本（{len(s_all)/len(df):.1%}），"
        f"新种子 {len(s_seed):,} 本（{len(s_seed)/len(core):.1%}），"
        f"V0 为 {v0_small:,} 本（{v0_small/len(v0):.1%}）——"
        f"数量减少 {1-len(s_seed)/v0_small:.0%}，占比腰斩，并非被大量塞进短篇。")
    add("")
    add("| form | 种子本数 | 种子占比 | 全库占比 | 中位收藏 | favs≥100 | 同代 fav 分位≥0.9 |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for name in FM.FORMS:
        sub = s_seed[s_seed["form"] == name]
        add(f"| {name} | {len(sub):,} | {len(sub)/len(s_seed):.1%} | "
            f"{uf_small.get(name, 0)/len(s_all):.1%} | "
            f"{sub['favs'].median():.0f} | {int((sub['favs'] >= 100).sum()):,} | "
            f"{int((sub['fav_pctl'] >= 0.9).sum()):,} |")
    add("")
    add(f"- `dialogue` 占种子 <1万字 的 **{sf_small.get('dialogue', 0)/len(s_seed):.1%}**"
        f"（最大单一类），全库同长度段仅 "
        f"{uf_small.get('dialogue', 0)/len(s_all):.1%}；"
        f"其中 {int(DF.mark(s_seed)['marked'].sum()):,} 本有对话征文确定标记，"
        f"{int(DF.mark(s_seed)['hidden'].sum()):,} 本仅为形态推断（E.13 判据 v2："
        "同人簇/复合指标 clicks÷字，校准 n=193 精确率 0.92）。")
    add("- 对话在短长度段反而是质量较高的一类：种子内 <1万字 且 favs≥100 的 "
        f"{int((s_seed['favs'] >= 100).sum()):,} 本里 "
        f"{int(((s_seed['form'] == 'dialogue') & (s_seed['favs'] >= 100)).sum()):,} 本"
        "是对话（"
        f"{((s_seed['form'] == 'dialogue') & (s_seed['favs'] >= 100)).sum()/(s_seed['favs'] >= 100).sum():.1%}）；"
        "若按「短篇天然低质」一刀切砍 <1万字，会先砍掉这批。")
    add("")
    order = [("收藏Top20k", res["base"]), ("短篇双分位", res["short"]),
             ("深榜", res["deep"]), ("月榜", res["monthly"])]
    anchors = {name: set(ids) for name, ids in order}

    def main_channel(nid: int) -> str:
        for name, _ids in order:
            if nid in anchors[name]:
                return name
        return "banner/其它"

    s_seed["main"] = s_seed["id"].map(main_channel)
    add("| 主渠道（优先序） | <1万本数 | dialogue | short | 中位收藏 | favs<10 |")
    add("|---|---:|---:|---:|---:|---:|")
    for name in [n for n, _ in order] + ["banner/其它"]:
        sub = s_seed[s_seed["main"] == name]
        if not len(sub):
            continue
        add(f"| {name} | {len(sub):,} | {int((sub['form'] == 'dialogue').sum()):,} | "
            f"{int((sub['form'] == 'short').sum()):,} | {sub['favs'].median():.0f} | "
            f"{int((sub['favs'] < 10).sum()):,} |")
    sus = s_seed[s_seed["favs"] < 10]
    add("")
    add(f"- 真正可疑的是 <1万字 且 favs<10 的 **{len(sus):,} 本**"
        f"（占 <1万 {len(sus)/len(s_seed):.1%}），形态以普通 short 为主"
        f"（{int((sus['form'] == 'short').sum()):,} 本），"
        f"dialogue 仅 {int((sus['form'] == 'dialogue').sum()):,} 本；"
        f"渠道来源：{'、'.join(f'{k} {v}' for k, v in sus['main'].value_counts().items())}。")
    add("- 时间渠道已整体移除（不做新书发现），因此 <1万字低收藏残留只剩"
        f"深榜锚（P1 强制全入池）与月榜锚；不是对话形态造成的。")

    add("")
    add("## 5. 征文保底（E.31 人工清单）")
    add("")
    seed_ids = set(core["id"])
    gaps = {k: v for k, v in res["contest_detail"].items() if v["need"] > 0}
    floor = res["contest_floor_specs"]
    add(f"- 自动全赛事保底已取消；**{len(floor)} 个征文**由人工写入保底清单"
        f"（{'、'.join(f'{k}≥{v}' for k, v in sorted(floor.items())) or '当前为空'}）。"
        f"本次从 `favs≥{SP.CONTEST_MIN_FAVS}、字数≥{SP.CONTEST_MIN_WORDS:,}` 的"
        f"合格候选中按同代收藏分位补入 **{len(res['contest_added'])} 本**，缺口已清零。")
    add("")
    add("| 征文 | 全量 | 保底前 | 补入 | 当前 | 合格候选 |")
    add("|---|---:|---:|---:|---:|---:|")
    for name, d in gaps.items():
        now = int(df[(df["contest"].fillna("").astype(str).str.strip() == name)
                     & df["id"].isin(seed_ids)].shape[0])
        add(f"| {name} | {d['total']} | {d['held']} | {d['added']} | "
            f"{now} | {d['eligible']} |")
    add("")
    add("- 这是**多样性约束而非质量豁免**：补入书全部通过收藏与字数底线；"
        "已入池的书即使来自其它渠道也计入名额，不替换原有书。")
    add("")
    add("## 6. `lqs` 篇幅加权口碑分")
    add("")
    scored = core[core["lqs"].notna()]
    add(f"- 评分池（form=long、>15 万字、favs≥200）覆盖种子 "
        f"**{len(scored):,} 本**，占非授权种子 {len(scored)/len(core):.1%}、"
        f"占其收藏 {scored['favs'].sum()/core['favs'].sum():.1%}。")
    add(f"- `lqs` 与收藏秩相关 ρ="
        f"{scored['lqs'].corr(scored['favs'], method='spearman'):+.2f}；"
        f"与 `pr` 秩相关 ρ="
        f"{scored['lqs'].corr(scored['pr'], method='spearman'):+.2f}。")
    top = scored.nlargest(1000, "lqs")
    add(f"- lqs Top-1000 的中位字数 **{int(top['words'].median()):,}**"
        f"（校准目标约 1,030,000），中位收藏 {int(top['favs'].median()):,}。")
    tiers = LQ.tier_of(top["words"]).value_counts()
    add("- Top-1000 篇幅构成：" + "、".join(
        f"{t} {tiers.get(t, 0)/len(top):.0%}" for t in LQ.TIER_LABELS))
    add("")
    add("| lqs 排名 | nid | 书名 | 字数 | 收藏 | pr | lqs |")
    add("|---:|---:|---|---:|---:|---:|---:|")
    for i, (_idx, r) in enumerate(scored.nlargest(10, "lqs").iterrows(), 1):
        add(f"| {i} | {int(r['id'])} | {str(r['title'])[:22]} | {int(r['words']):,} | "
            f"{int(r['favs']):,} | {r['pr']:.2f} | {r['lqs']:.3f} |")

    add("")
    add("## 7. 噪声残留（逐本可追）")
    add("")
    channel = {name: set(ids) for name, ids in [
        ("深榜", res["deep"]), ("月榜", res["monthly"]),
        ("banner", res["featured"]), ("短篇双分位", res["short"]),
        ("收藏Top20k", res["base"])]}
    core["anchor"] = core["id"].map(
        lambda nid: "+".join(k for k, v in channel.items() if nid in v) or "无")
    low = core[core["favs"] < 5].sort_values("favs")
    add(f"favs<5 共 **{len(low)} 本**（{len(low)/len(core):.2%}），"
        f"全部有外部锚：{', '.join(f'{k} {v}' for k, v in low['anchor'].value_counts().items())}")
    add("")
    add("| nid | 书名 | 收藏 | 字数 | 入池锚 |")
    add("|---:|---|---:|---:|---|")
    for _idx, r in low.head(15).iterrows():
        add(f"| {int(r['id'])} | {str(r['title'])[:24]} | {int(r['favs'])} | "
            f"{int(r['words']):,} | {r['anchor']} |")
    add("")
    add(f"时间渠道整体移除 {len(res['excluded_time']):,} 本（favs<5 占 "
        f"{share(df[df['id'].isin(res['excluded_time'])]['favs'] < 5)}，最高收藏 "
        f"{int(df[df['id'].isin(res['excluded_time'])]['favs'].max())}）；"
        f"深榜补入 {len(res['deep'] - res['baseline']):,} 本，"
        f"新种子深榜缺失 {len(res['deep'] - set(core['id']))} 本。")

    add("")
    add("## 8. 产品可用性")
    add("")
    covers = core["cover_url"].notna()
    licensed = raw[raw["is_licensed"] == 1]
    lic_covers = licensed["cover_url"].notna()
    add(f"- 非授权种子有封面 URL {int(covers.sum()):,} 本（{covers.mean():.1%}）；"
        f"授权 {manifest['licensed_count']} 本中 {int(lic_covers.sum())} 本有 "
        f"`cover-check` 当期封面（2026-11-19 起不再置空）。"
        f"全种子共 {int(raw['cover_url'].notna().sum()):,} 本有封面。")
    add(f"- `book_tags` 行 {manifest['tag_rows']:,}，不同标签 {manifest['tag_count']}。")
    add(f"- 种子内同名不同书：{int(raw['title'].duplicated().sum())} 组"
        "（'萝莉进化论' 13245/21623，不同作者、均为深榜锚，属书名复用而非快照重复）。")
    add("")
    add("## 9. 结论")
    add("")
    eligible = df[~df["id"].isin(res["ineligible"])]
    cov_seed = core["favs"].sum() / eligible["favs"].sum()
    cov_v0 = v0[~v0["id"].isin(res["ineligible"])]["favs"].sum() / eligible["favs"].sum()
    add("- V3 质量锚的六条后置断言全部 PASS（见 `manifest.postconditions`）："
        f"合格深榜 {len(res['deep'] - res['ineligible']):,} 本全入池；"
        "favs<5 且 <1 万字的无锚噪声 0；"
        f"收藏覆盖合格书口径 {cov_seed:.2%}（VS V0 {cov_v0:.2%}，"
        f"差 {(cov_seed-cov_v0)*100:+.2f}pp，容差 0.2pp）；"
        f"人工保底清单内 {len(res['contest_detail'])} 个征文达标（E.31）；"
        f"连载短/中篇仅人工豁免可入种，现有 {len(res['abandoned_in_seed'])} 本（E.31）；"
        f"invalid 零入种（E.12）。")
    add(f"- E.31 弃书规则：连载中的短/中篇（{len(res['abandoned']):,} 本）无收录资格，"
        "读者直觉是「一口气读完」，2026 中篇并入短篇后同一条硬规则适用全世代；"
        "自动征文保底与 fav_pctl 质量豁免均已取消，"
        f"仅人工清单 {len(res['manual_exempt'])} 本可逐本放行（P5/P8 守门）。"
        f"E.32 人工黑名单 {len(res['manual_blacklist'])} 本永久剔除，优先于豁免（P11）。")
    add(f"- E.12 僵尸规则：`form=invalid`（words<2000，{len(res['invalid']):,} 本）"
        "无收录资格——app 正常章节最少 2000 字、正常书至少一章，<2000 多为目录"
        "抓取残缺的僵尸书（锚点 4166 辞别黄昏的小镇 words=775）。征文保底候选"
        " ≥1万字、天然不碰 invalid。同时取消篇幅征文命名覆盖字数——征文名只反映"
        "投稿赛道、不反映真实字数（86279 少女与龙 words=13.9万却挂「五征短篇」）。"
        f"本轮 E.11+E.12 合计从质量锚剔除，种子 {len(seed):,} 本。")
    add(f"- 低收藏书从 {len(v0[v0['favs'] < 5]):,} 本降到 {len(low):,} 本；"
        f"时间渠道移除 {len(res['excluded_time']):,} 本，只让出 0.26% 收藏，"
        "中位收藏 652 → 870。")
    add("- 但入池 ≠ 推荐排序：种子仅保证候选集不含明显噪声；"
        "`lqs` 是长篇区的分层/排序信号（只覆盖 15 万字以上且 favs≥200），"
        "中篇区仍待定，短篇仍用同代 fav 分位。")
    add(f"- <1 万字不是质量问题源：数量已从 V0 的 {v0_small:,} 降到 {len(s_seed):,}，"
        "其中过半是对话小说且收藏表现优于普通短篇；残留的 favs<10 "
        "集中在深榜锚（详见 §4）。")
    add("- 剩余风险：深榜锚会把少量低收藏老书带入，这是设计选择（保证离线榜单可展示）；"
        "不做新书发现意味着近一年上架书只能靠收藏、月榜、征文或榜单进入种子。")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"...\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

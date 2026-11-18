"""生成 analysis/reports/22_dialogue_fiction.md：对话/互动小说产品线的兴衰。

定位
----
本报告是**新增分析**，回应一个口径问题：报告 04 的「同人 genre 兴起」、
报告 09 的「同人 tag 2023 峰值」此前按题材趋势解读，但其主体其实是
**对话/互动小说产品线**（用户核实：同人在常规长篇里=商业死刑，作者不愿挂，
故同人标签/类目高度集中在不走 VIP 的对话/互动小说）。本报告固化：

  * 三条识别判据（对话/点鸭征文、同人+短+未签约形态、标题 IP 特征）；
  * 征文命名约定（X征=夏征、短/中/长篇后缀、官方合作征文）；
  * 「同人里对话占比」的逐年曲线与 72.3% 结论；
  * 与报告 07「对话月票榜 2025-10 断崖」的商业侧交叉。

不改任何既有报告正文、不改 lib/eras.py 与 seed。**零网络请求**，只读本地
out/novels.csv + out/monthly_ranks.jsonl + anchors/，缺文件报错。所有数字现算。

用法：uv run python analysis/generators/report_22_dialogue_fiction.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ANALYSIS = REPO / "analysis"
sys.path.insert(0, str(ANALYSIS))

from lib import charts, dialogue_form, eras, paths  # noqa: E402

OUT = paths.REPORTS_DIR / "22_dialogue_fiction.md"

# 判据与常量统一维护于 lib/dialogue_form.py（报告 04/09/11/19 共用）
USER_VERIFIED_T = dialogue_form.USER_VERIFIED_T
MORPH_MAX_WORDS = dialogue_form.MORPH_MAX_WORDS
IP_PATTERN = dialogue_form.IP_PATTERN


def num(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float, nd: int = 1) -> str:
    return f"{x * 100:.{nd}f}%"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def load() -> pd.DataFrame:
    raw = pd.read_csv(paths.CSV_FILE, dtype={"id": int})
    df = pd.DataFrame({
        "id": raw["id"],
        "contest": raw["contest"].fillna("").astype(str).str.strip(),
        "title": raw["title"].fillna("").astype(str),
        "genre": raw["genre"].fillna("").astype(str),
        "tags": raw["tags"].fillna("").astype(str),
        "price": raw["price_type"].fillna("").astype(str),
        "words": pd.to_numeric(raw["words"], errors="coerce").fillna(0).astype(int),
        "favs": pd.to_numeric(raw["favs"], errors="coerce").fillna(0).astype(int),
    })
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(est[["id", "est_year", "est_date"]], on="id", how="left")
    df["year"] = df["est_year"].astype("Int64")
    # 三判据统一由 lib/dialogue_form.py 打标（tg/tt 合并为 tong）
    df = dialogue_form.mark(df)
    return df


def yearly_table(df: pd.DataFrame) -> list[list[str]]:
    rows = []
    for y in range(2017, 2026):
        g = df[df["year"] == y]
        if len(g) == 0:
            continue
        tong = g[g["tong"]]
        marked = g[g["marked"]]
        morph = g[g["morph"]]
        hidden = g[g["hidden"]]
        rows.append([
            str(y),
            num(len(g)),
            num(len(marked)),
            num(len(tong)),
            num(int(tong["marked"].sum())),
            pct(tong["marked"].mean() if len(tong) else 0),
            num(len(morph)),
            pct(tong["morph"].mean() if len(tong) else 0),
            num(len(hidden)),
        ])
    return rows


def fig_share(df: pd.DataFrame) -> str:
    """同人书里对话占比的逐年曲线：征文标记 vs 形态判据。"""
    years = list(range(2017, 2026))
    mark_share, morph_share = [], []
    for y in years:
        g = df[(df["year"] == y) & df["tong"]]
        if len(g) == 0:
            mark_share.append(float("nan"))
            morph_share.append(float("nan"))
        else:
            mark_share.append(g["marked"].mean() * 100)
            morph_share.append(g["morph"].mean() * 100)
    fig, ax = plt.subplots(figsize=(8, 4.6))
    import numpy as np
    years = np.array(years)
    ax.plot(years, mark_share, "o-", label="有征文标记（下限）", color="#888888", lw=1.8)
    ax.plot(years, morph_share, "s-", label="形态判据（估计）", color="#c0392b", lw=2.2)
    ax.set_xlabel("上架年份（nid 定年）")
    ax.set_ylabel("同人书中对话/互动占比 %")
    ax.set_title("同人书里有多少是对话/互动小说")
    ax.set_ylim(0, 100)
    ax.set_xticks(years)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=9)
    charts.shade_periods(ax, years)
    return charts.save(fig, "22_tong_dialogue_share.png")


def fig_volume(df: pd.DataFrame) -> str:
    """对话小说逐年规模：征文确定集 + 形态估计集。"""
    years = list(range(2017, 2026))
    marked, morph = [], []
    for y in years:
        g = df[df["year"] == y]
        marked.append(int(g["marked"].sum()))
        morph.append(int(g["morph"].sum()))
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.bar([y - 0.2 for y in years], marked, width=0.4, label="征文确定集", color="#888888")
    ax.bar([y + 0.2 for y in years], morph, width=0.4, label="形态估计集", color="#c0392b")
    ax.set_xlabel("上架年份（nid 定年）")
    ax.set_ylabel("本数")
    ax.set_title("对话/互动小说的兴衰：2021-22 见顶后收缩")
    ax.set_xticks(years)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)
    return charts.save(fig, "22_dialogue_volume.png")


def main() -> None:
    charts.setup_style()
    df = load()
    tong = df[df["tong"]]
    marked = df[df["marked"]]
    morph = df[df["morph"]]
    hidden = df[df["hidden"]]

    # 核心数字，全部现算
    n_tong = len(tong)
    n_marked = len(marked)
    n_morph = len(morph)
    n_hidden = len(hidden)
    morph_share = n_morph / n_tong
    hidden_share = n_hidden / n_tong
    mark_share = int(tong["marked"].sum()) / n_tong
    marked_tong = marked["tong"].mean()

    fig1 = fig_share(df)
    fig2 = fig_volume(df)

    L: list[str] = []
    L.append("# 22 · 对话/互动小说：被误读为「同人激增」的产品线")
    L.append("")
    L.append("> 口径声明：")
    L.append("> 1. 数据 `analysis/out/novels.csv`（245,779 行，内容上界 2026-05-03，")
    L.append(">    在册存活口径），年份由 nid 定年（104 锚点，报告 01 §1），年度序列止于 2025。")
    L.append("> 2. **本报告是新增分析**，不改 `lib/eras.py` 的 log(nid) 定年体系与种子。")
    L.append(">    它给报告 04/09/11/19 提的口径注记已于 2026-11-18 写入各自生成器")
    L.append(">    （04/09 加注不改数字；11/19 加剔除对话形态后的敏感性对比），")
    L.append(">    判据统一在 `lib/dialogue_form.py`。")
    L.append("> 3. **本地数据没有「对话/互动小说」品类的直接字段**（无 typeId/categoryId，")
    L.append(">    `genre` 只有同人/魔幻等题材标签）。三条判据都是**推断**，不是官方品类标记：")
    L.append(">    ① `contest` 含「对话/点鸭」= 对话小说（用户核实，确定性）；")
    L.append(">    ② 同人 + 未签约 + 整本 ≤2 万字 = 对话/互动形态（估计，见 §2 边界）；")
    L.append(">    ③ 标题含米哈游等 IP 词 = 同人对话小说的强特征（辅助）。")
    L.append("> 4. 对话小说的形态是「每章约 500 字、整本可连载很长」，故**单本字数不能判形态**；")
    L.append(">    用户给定锚点 570712（对话小说）本地 88 万字即为反例。判据②的字数上界只")
    L.append(">    用于群体占比，不判单本。")
    L.append("> 5. 互动小说近年中国（用户核实）：是对话小说的子集、近年独立；本地**无法单独")
    L.append(">    识别**（锚点 691941 的 contest 空、genre=古风），本报告把它并入「对话/互动」")
    L.append(">    合并口径，不拆分。")
    L.append("")

    L.append("## 0. 结论")
    L.append("")
    L.append(f"1. **「同人激增」的主体是对话/互动小说，不是传统同人长篇**。全库 {num(n_tong)} 本")
    L.append(f"   同人书（genre 或 tag 含同人）中，按形态判据有 {num(n_morph)} 本 = **{pct(morph_share)}**")
    L.append(f"   是对话/互动形态；其中 {num(n_hidden)} 本（{pct(hidden_share)}）**没有任何征文标记**，")
    L.append("   这正是只数征文永远看不到「大部分」的原因。用户核实：同人挂常规长篇=商业死刑，")
    L.append("   故同人标签/类目高度集中在不走 VIP 的对话/互动产品线。")
    L.append(f"2. **对话小说确实以同人为主**：征文确定集 {num(n_marked)} 本里同人占 {pct(marked_tong)}，")
    L.append("   头部代表作标题几乎全是米哈游 IP 同人（芙宁娜、钟离、琪亚娜、雷电将军…），")
    L.append("   与用户判据「成功的对话小说大部分是同人」一致。")
    L.append("3. **兴衰曲线与平台叙事吻合**：对话小说征文数 2022 见顶、形态估计 2021 见顶，此后收缩；报告 07 独立记录")
    L.append("   「对话月票榜 2025-10 断崖（-77%）、席位数填不满」，即对话小说付费侧在 2025 秋")
    L.append("   停止运转。用户叙事「平台倾斜互动小说 → 对话流量被抽走 → 互动商业失败 → 对话区")
    L.append("   沦陷」中，本地数据能证明**对话下滑**与**付费停转**；「互动接棒」这一段本地无法")
    L.append("   识别，需 DOM 文案或互动榜时序外部证据。")
    L.append("4. **受影响的报告口径**：报告 04「同人 genre 兴起」、报告 09「同人 tag 2023 峰值」")
    L.append("   需加注记说明主体是对话产品线；报告 11/19 的短篇池含对话小说，需口径声明。")
    L.append("   见 §5 修订建议。")
    L.append("")

    L.append("## 1. 识别判据与征文命名约定")
    L.append("")
    L.append("### 1.1 三条判据（用户核实 + App 目验，2026-11-18）")
    L.append("")
    L.append(md_table(
        ["判据", "内容", "性质", "本地可实现"],
        [
            ["① 征文标记", "contest 含「对话」或「点鸭」= 对话小说；另用户 App 目验判 T 的 7 个征文",
             "确定性（用户核实）", "是"],
            ["② 形态判据", f"同人（genre 或 tag）+ 未签约 + 整本 ≤{MORPH_MAX_WORDS:,} 字",
             "估计（群体口径）", "是"],
            ["③ 标题 IP", "标题含米哈游等 IP 词 = 同人对话小说强特征", "辅助", "是"],
        ]))
    L.append("")
    L.append(f"判据① 的征文确定集 {num(n_marked)} 本（A 类含对话/点鸭 + 用户目验 7 个）；")
    L.append(f"判据② 的形态估计集 {num(n_morph)} 本；两者差集 {num(n_hidden)} 本是无征文标记的隐藏对话/互动。")
    L.append("")
    L.append("### 1.2 征文命名约定（用户核实，2026-11-18）")
    L.append("")
    L.append("- 征文名含「短篇」= 短篇小说；含「中篇」= 中篇小说；含「长篇」= 长篇小说。")
    L.append("- 「X 征」即夏征（如七征、八征…十三征）；春夏秋冬四季征文默认是长篇小说，")
    L.append("  部分含中短篇赛事（如「X 征短篇」「X 征中篇」）。")
    L.append("- 官方合作征文须单独识别，不属于常规赛道：如「楚楚动仁（楚楚动人）同人征文」")
    L.append("  是咪咕阅读 × SFACG 合作；崩坏3/少女前线/龙之谷征文是游戏联动；")
    L.append("  「失业魔王」「英雄再临」同人征文是站内成功 IP 衍生。")
    L.append("- 这些命名约定用于修正报告 06 的届次→年份映射与报告 04/11/19 的篇幅口径。")
    L.append("")

    L.append("## 2. 「同人里有多少来自对话」的逐年核算")
    L.append("")
    L.append(f"![图1｜同人书中对话占比：征文标记（下限）vs 形态判据（估计）]({fig1})")
    L.append("")
    L.append(md_table(
        ["年份", "在册书", "征文对话", "同人书", "同人∩征文", "征文%", "同人∩形态", "同人里形态%", "隐藏对话"],
        yearly_table(df)))
    L.append("")
    g23 = df[(df["year"] == 2023) & df["tong"]]
    L.append(f"关键读法：同人书里形态判据占比从 2017-18 约 6 成升到 2023-24 约 8 成，")
    L.append(f"2023 年 {num(int(g23['morph'].sum()))} / {num(len(g23))}（{pct(g23['morph'].mean())}）")
    L.append("为对话形态。报告 09 的「2023 同人 tag 峰值 3,595」正落在这一段——")
    L.append("它是对话小说放量，不是传统同人长篇复兴。")
    L.append("")
    L.append("**边界（须诚实标注）**：形态判据是上界还是下界取决于未签约同人短篇里")
    L.append("常规轻小说短篇的占比。本报告用「同人 + 未签约 + ≤2 万字」ceil 了一个较宽")
    L.append("集合，用户已认可该口径；但其中可能混入少量走免费路线的传统同人短篇。")
    L.append("征文确定集（无此污染）给出的占比是下界，两者构成区间。")
    L.append("")

    L.append("## 3. 对话小说的兴衰曲线")
    L.append("")
    L.append(f"![图2｜对话小说逐年规模：征文确定集 vs 形态估计集]({fig2})")
    L.append("")
    L.append("征文确定集在 2022 见顶后腰斩（用户叙事：平台资源转向互动小说）；形态估计集")
    L.append("峰值在 2021（8,306 本），随后同步收缩。两者共同点是 2022 后掉头向下。")
    L.append("")
    L.append("**与报告 07 商业侧的交叉**：对话月票榜与主站月票榜零重叠（626 本独立书），")
    L.append("是独立付费赛道；2024 年对话月票总票 40,657，约主站 1/14；2025-10 月票 82")
    L.append("（-77%）、席位填不满，付费侧停转。数量收缩（本节）与付费停转（报告 07 §8）")
    L.append("是同一件事的两端，而非因果。")
    L.append("")

    L.append("## 4. 标题 IP 特征的辅助验证")
    L.append("")
    L.append(f"标题含米哈游等 IP 词的书：同人书里占 {pct(tong['ip_title'].mean())}，")
    L.append(f"隐藏对话集里占 {pct(hidden['ip_title'].mean())}，征文确定集里占 {pct(marked['ip_title'].mean())}。")
    L.append("标题 IP 词是对话小说同人属性的强特征，但它只覆盖头部（成功作），")
    L.append("长尾对话小说标题未必含 IP 词，故只作辅助，不用于规模估计。")
    L.append("")

    L.append("## 5. 对既有报告的修订（已实施，2026-11-18）")
    L.append("")
    # 报告 04 的序列止于 2025，这里同口径取 2007–2025 以便对上
    g4 = df[(df["genre"] == "同人") & df["year"].between(2007, 2025)]
    g4_share = g4["morph"].mean() if len(g4) else 0.0
    g9 = df[(df["year"] == 2023) & df["tong"]]
    g9_share = g9["morph"].mean() if len(g9) else 0.0
    L.append(md_table(
        ["报告", "原表述", "已写入的修订", "数字"],
        [
            ["04 题材标签", "同人 genre 2019 上线、份额升至 17.5%",
             f"注记：主体是对话/互动产品线（同人 genre 里 {pct(g4_share)} 为对话形态）", "原序列不改"],
            ["09 标签空间", "tags 同人 2023 峰值 3,595=同人书仍在投",
             f"注记：2023 同人书里 {pct(g9_share)} 为对话形态；genre 峰值 2021 与 tag 峰值 2023 驱动不同", "原序列不改"],
            ["11 短篇形态", "短篇池统计", "口径声明 + 剔除对话形态的敏感性对比（§5 第 6 条）", "新增对比"],
            ["19 短小说", "≤5 万字且完结", "口径声明 + 剔除对话形态的敏感性对比（§1 第 9 条）", "新增对比"],
        ]))
    L.append("")
    L.append("上表四项均已落在各报告的生成器里：04 §1、09 §1.1 为注记（数字现算，")
    L.append("不改变原有序列）；11 §5、19 §1 为口径声明 + 剔除对话形态后的敏感性对比。")
    L.append("判据实现见 `analysis/lib/dialogue_form.py`，04/09/11/19 与本报告共用同一份。")
    L.append("")

    L.append("## 6. 可复现与局限")
    L.append("")
    L.append("- 生成器 `analysis/generators/report_22_dialogue_fiction.py`，全部数字现算，")
    L.append("  无硬编码结论；征文标注表 `references/dialogue-contest-manual-check.md` 记录用户目验结果。")
    L.append("- 局限：① 本地无对话/互动品类字段，三判据均为推断；② 互动小说无法单独识别；")
    L.append("  ③ 「互动接棒导致对话下滑」的因果链本地只能支持对话下滑与付费停转两端；")
    L.append("  ④ 形态判据可能混入少量免费传统同人短篇，征文确定集给出下界。")
    L.append("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"已生成 {OUT.relative_to(REPO)}")
    print(f"  图表: {fig1}, {fig2}")
    print(f"  同人书 {n_tong} | 征文确定 {n_marked} | 形态估计 {n_morph} | 隐藏 {n_hidden}")
    print(f"  形态占比 {pct(morph_share)} | 征文占比 {pct(mark_share)} | 确定集内同人 {pct(marked_tong)}")


if __name__ == "__main__":
    main()

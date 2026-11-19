"""`form` 形式分类（`docs/form-definitions.md` §4 伪代码的可执行版）。

六值互斥：`invalid / short / medium / long / dialogue / ip_collab`，逐级覆盖：
字数兜底（含 invalid 下界）→ 对话形态 → 对话征文 → IP 合作。

2026-11-19 用户裁定两项修正（见 `docs/form-definitions.md` §0/§3）：
1. **取消篇幅征文命名覆盖字数**：征文名（「X征短篇/中篇/长篇」）只反映投稿赛道，
   不反映真实字数（实测「中篇征文」有 129 万字、「短篇征文」有 13.9 万字）。
   篇幅 form 现在**纯按字数**切档。对话征文标记与 IP 封闭名单仍覆盖（确定性身份）。
2. **新增 `invalid`（第六值）**：words < 2000 的书不构成有效篇幅——app 正常章节
   最少 2000 字、正常书至少一章，故 <2000 几乎都是目录抓取残缺的僵尸书
   （锚点 4166 辞别黄昏的小镇 words=775）。`invalid` 无收录资格，种子层剔除；
   但对话/IP 的确定性证据仍优先把它救回对应形态（字数不判形态，§3.4）。

本模块只回答「是不是短篇/长篇」，不回答「好不好」——质量判定见 `lqs.py` 与
`docs/form-definitions.md` §6.1。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lib import dialogue_form as DF

INVALID_MAX_WORDS = 2_000   # 用户 2026-11-19 定：<2000 不是有效篇幅（app 章节下限）
SHORT_MAX_WORDS = 50_000
MEDIUM_MAX_WORDS = 150_000

# §3.5 封闭名单：SFACG 近年无新增 IP 合作征文
IP_COLLAB_NAMES = ("楚楚动仁", "崩坏3", "少女前线", "龙之谷", "失业魔王", "英雄再临")

FORMS = ("invalid", "short", "medium", "long", "dialogue", "ip_collab")
# 仍具篇幅语义、受完结/僵尸资格约束的值（E.11 + invalid）
LENGTH_FORMS = ("short", "medium")


def classify(df: pd.DataFrame) -> pd.Series:
    """返回 form 列。需要 `contest/words/genre/tags/price_type`（或 `price`）。"""
    if "title" not in df.columns:      # DF.mark 需要 title 做 IP 词判据
        df = df.assign(title="")
    d = DF.mark(df)
    words = pd.to_numeric(d["words"], errors="coerce").fillna(0).astype(int)
    contest = d["contest"].fillna("").astype(str)

    # 级 0：字数兜底（纯字数，取消篇幅征文命名覆盖；<2000 → invalid）
    form = np.where(words < INVALID_MAX_WORDS, "invalid",
                    np.where(words <= SHORT_MAX_WORDS, "short",
                             np.where(words <= MEDIUM_MAX_WORDS, "medium", "long")))
    # 级 2：对话形态（估计）——覆盖篇幅标签，但**不得救回 invalid**：
    #       僵尸书章节数极少、clicks/字 天文高（4166 775 字 ckw=13.2；181214
    #       23 章 × 11 字 ckw=291），ckw 判据会把僵尸误判成对话（校准后实测
    #       2,405 本 invalid 被误翻）。只有确定性证据（级 3/4）能救回 invalid。
    form = np.where((d["morph"].to_numpy()) & (form != "invalid"), "dialogue", form)
    # 级 2.5：短篇点击天花板（E.19，用户 App 目验）。真 short 的点击上界是
    #       「回到旧时光」215,723；越过此线却仍在短篇档（≤5 万字）的书不是真
    #       短篇——是内容被替换为无意义文本的僵尸（When It Sucks，34,297 字
    #       162 万点击，阅读按钮仍在）或作者恶意标注完结的长篇（字数只统计到
    #       前段）。两者字数、状态、点击数都不可信，归 invalid 而非 long：
    #       没有可靠字数可判它是长篇。级 2 命中的对话不受影响（当代越线书多是
    #       对话，v2-d 已判 dialogue）。
    if "clicks" in d.columns:
        clicks = pd.to_numeric(d["clicks"], errors="coerce").fillna(0).to_numpy()
        form = np.where((form == "short") & (words <= SHORT_MAX_WORDS)
                        & (clicks > DF.DIAL_CLICKS_CEIL), "invalid", form)
    # 级 3：对话征文（确定性）——可救回 invalid
    form = np.where(d["marked"].to_numpy(), "dialogue", form)
    # 级 4：IP 合作（最高）
    ip = contest.map(lambda x: any(name in x for name in IP_COLLAB_NAMES))
    form = np.where(ip.to_numpy(), "ip_collab", form)
    return pd.Series(form, index=df.index, name="form")


def form_stats(df: pd.DataFrame) -> pd.Series:
    """直接对原始表返回五值分布。"""
    return classify(df).value_counts().reindex(FORMS).fillna(0).astype(int)

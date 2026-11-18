"""`form` 形式分类（`docs/form-definitions.md` §4 伪代码的可执行版）。

五值互斥：`short / medium / long / dialogue / ip_collab`，逐级覆盖：
字数兜底 → 篇幅征文命名 → 对话形态 → 对话征文 → IP 合作。

本模块只回答「是不是短篇/长篇」，不回答「好不好」——质量判定见 `lqs.py` 与
`docs/form-definitions.md` §6.1。

已知缺口（与上游文档一致）：§3.3 提到「X 征」默认长篇，但 §4 的权威伪代码未实现该规则，
此处同样不实现；它只影响字数落在中篇区间的四季征文，随 `form` 列正式落地时一并定。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lib import dialogue_form as DF

SHORT_MAX_WORDS = 50_000
MEDIUM_MAX_WORDS = 150_000

# §3.5 封闭名单：SFACG 近年无新增 IP 合作征文
IP_COLLAB_NAMES = ("楚楚动仁", "崩坏3", "少女前线", "龙之谷", "失业魔王", "英雄再临")

FORMS = ("short", "medium", "long", "dialogue", "ip_collab")


def classify(df: pd.DataFrame) -> pd.Series:
    """返回 form 列。需要 `contest/words/genre/tags/price_type`（或 `price`）。"""
    if "title" not in df.columns:      # DF.mark 需要 title 做 IP 词判据
        df = df.assign(title="")
    d = DF.mark(df)
    words = pd.to_numeric(d["words"], errors="coerce").fillna(0).astype(int)
    contest = d["contest"].fillna("").astype(str)

    # 级 0：字数兜底
    form = np.where(words <= SHORT_MAX_WORDS, "short",
                    np.where(words <= MEDIUM_MAX_WORDS, "medium", "long"))
    # 级 1：篇幅征文命名（确定性，覆盖字数）
    form = np.where(contest.str.contains("长篇", na=False), "long", form)
    form = np.where(contest.str.contains("中篇", na=False), "medium", form)
    form = np.where(contest.str.contains("短篇", na=False), "short", form)
    # 级 2：对话形态（估计）
    form = np.where(d["morph"].to_numpy(), "dialogue", form)
    # 级 3：对话征文（确定性）
    form = np.where(d["marked"].to_numpy(), "dialogue", form)
    # 级 4：IP 合作（最高）
    ip = contest.map(lambda x: any(name in x for name in IP_COLLAB_NAMES))
    form = np.where(ip.to_numpy(), "ip_collab", form)
    return pd.Series(form, index=df.index, name="form")


def form_stats(df: pd.DataFrame) -> pd.Series:
    """直接对原始表返回五值分布。"""
    return classify(df).value_counts().reindex(FORMS).fillna(0).astype(int)

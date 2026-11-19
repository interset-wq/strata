"""`form` 形式分类（`docs/form-definitions.md` §4 伪代码的可执行版）。

六值互斥：`invalid / short / medium / long / dialogue / ip_collab`，逐级覆盖：
字数兜底（含 invalid 下界）→ 对话形态估计 → 详情页 DOM 的散文证据（撤销估计）→
短篇点击天花板 → 对话征文 → 详情页 DOM 的对话证据 → IP 合作。

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

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from lib import dialogue_form as DF
from lib import paths
from lib import web_dialogue as WD

# 用户直接裁定的形态（最高优先，覆盖下面所有级）。用户 2026-11-19：
# 「不需要 DOM 判决，很多你可以直接问我，因为对话数据非常出众的作品非常少」——
# 数据量大的书判错代价最大，逐本问人比再爬一遍便宜。
USER_FORM_FILE = paths.ANCHORS_DIR / "form_user_verified.jsonl"


@lru_cache(maxsize=1)
def user_forms() -> dict[int, str]:
    """`nid -> form`，来自 `analysis/anchors/form_user_verified.jsonl`。

    行格式：`{"nid": 172004, "form": "long", "reason": "…", "verified_on": "2026-11-19"}`。
    文件不存在即空表（默认不干预）。
    """
    if not USER_FORM_FILE.exists():
        return {}
    out: dict[int, str] = {}
    for line in USER_FORM_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        row = json.loads(line)
        form = str(row["form"])
        if form not in FORMS:
            raise ValueError(f"form_user_verified: 非法形态 {form!r}（nid={row.get('nid')}）")
        out[int(row["nid"])] = form
    return out

INVALID_MAX_WORDS = 2_000   # 用户 2026-11-19 定：<2000 不是有效篇幅（app 章节下限）
SHORT_MAX_WORDS = 50_000
MEDIUM_MAX_WORDS = 150_000
# E.21 的正文征文保护档必须与本模块的中篇档一致，否则两条规则会互相错位。
assert DF.PROSE_CONTEST_MIN_WORDS == SHORT_MAX_WORDS + 1
assert DF.PROSE_CONTEST_MAX_WORDS == MEDIUM_MAX_WORDS

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
    #       `morph` 本身已排除 E.21 的正文征文（中篇档）：有征文标记而无对话
    #       关键词的书属正文组，形态由字数决定，ckw 灰带不得推翻征文标记。
    # 级 1.2：详情页 DOM 的**散文**证据（E.22）——撤销形态估计的假阳性。
    #       DOM 预读章节区渲染出正文 = 该书是散文产品线，ckw 高企只是病毒式传播
    #       （264982「转生成蝴蝶的我来到了斗罗大陆」ckw=12.1、40325 ckw=11.8，
    #       章节为「第一章」，形态估计会把它们划进对话）。
    wd = WD.apply(d).to_numpy()
    morph = d["morph"].to_numpy() & (wd != "prose")
    form = np.where(morph & (form != "invalid"), "dialogue", form)
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
    # 级 3.5：详情页 DOM 的**对话**证据（E.22，最高确定性）。
    #       产品线声明优先于征文组别：3 本带正文征文标记的书被 DOM 判为对话
    #       （448045 玄幻征文、683752 冬季恋曲征文、607079 冬季征文）——作者用
    #       对话编辑器写作但投了正文组，E.21 的「正文征文否决形态估计」在此让位。
    #       也覆盖 4 本「第一章」命名的沉浸式互动小说（745405 / 746269 / 729181 /
    #       758261），章节命名判据对它们全部失效。
    form = np.where(wd == "dialogue", "dialogue", form)
    # 级 4：IP 合作（最高）
    ip = contest.map(lambda x: any(name in x for name in IP_COLLAB_NAMES))
    form = np.where(ip.to_numpy(), "ip_collab", form)
    # 级 -1：用户直接裁定（真正的最高——覆盖 DOM、征文与 IP 名单）。
    #       数据出众的书判错代价最大，而这类书很少，逐本问人比再爬一遍便宜。
    uv = user_forms()
    if uv:
        nid = pd.to_numeric(
            d["id"] if "id" in d.columns else d.get("nid"), errors="coerce"
        )
        decided = nid.map(lambda x: uv.get(int(x)) if pd.notna(x) else None)
        form = np.where(decided.notna().to_numpy(), decided.to_numpy(), form)
    return pd.Series(form, index=df.index, name="form")


def form_stats(df: pd.DataFrame) -> pd.Series:
    """直接对原始表返回五值分布。"""
    return classify(df).value_counts().reindex(FORMS).fillna(0).astype(int)

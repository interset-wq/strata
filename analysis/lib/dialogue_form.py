"""对话/互动小说形态判据（报告 22 固化，供其它报告加注记与敏感性对比）。

本地数据没有「对话/互动小说」品类字段（无 typeId/categoryId），判据都是**推断**：

  * ① 征文标记：`contest` 含「对话/点鸭」= 对话小说（用户核实，确定性），
    另加用户 App 目验的 7 个征文（无关键字，属隐藏标记）；
  * ② 形态判据 v2（2026-11-19，用户裁定 R18，章节真值校准）：
      - (同人特征 & clicks/字 ≥ 6)；
      - (非同人 & words ≤ 5 万 & clicks/字 ≥ 13)；
      - (非同人 & 5–15 万字 & clicks/字 ≥ 30)；
      - (words ≤ 5 万 & clicks > 真短篇点击天花板)：天花板 = 「回到旧时光」
        clicks 215,723——用户 App 目验确认其为真短篇点击上限（36 本误判短篇
        全部 >226k；真短篇章节少、曝光低，clicks 上不去）。此条款**不限
        同人/签约**，专收 ckw 6–13 灰带的高曝光对话文（E.16）；
      - **同人 & words ≤ 5 万（E.17，2026-11-19 用户裁定）**：种子 short 层
        170 本同人经逐一目验全为误判（头部 20 万点击的崩坏/综漫系）。同人区
        是对话/互动产品线的主场（§18），同人而字数压不进长篇档（>5 万）者
        按形态判对话。同人长篇（>5 万）不适用——那是正常散文连载；
      - 保留原条款 (同人 + 未签约 + ≤ 2 万字)。
  * ③ 标题 IP 特征：含米哈游等 IP 词 = 同人对话小说的强特征（辅助）。

短篇上限（用户目验，E.17 固化）：点击 215,723（回到旧时光）、favs 5,478 与
praises 2,389（听雨）。这三条是 P7 断言的来源——short 层若有书越过 favs/赞
天花板，说明还有形态误判。**断言只对 `nid ≥ 83,818`（对话体时代）生效**：
早期书的 clicks 是十余年累积，与当代不可比（回到旧时光本身 2012 建档）。

时间下界（E.18，2026-11-19 用户裁定）：对话体出现之前的 nid 不可能是对话。
证据链——历史月榜 `MonthlyBoy.ashx` 的 rank=4（对话月票榜）首月为 2017-07
（2016-10 至 2017-06 全空），同月出现首批「五征对话小说」投稿，最小 nid
83,818 / 2017-07-03；此前十年无任何对话征文标记。故形态判据全部加
`nid ≥ 83,818` 下界，早期同人短篇按散文计（回退 1,709 本）。

标题 IP 条款（E.18）：`ip_title & words ≤ 5 万` → 对话。用户判定「有崩坏等
米哈游特征的都是对话」；早期书里的「崩坏」是普通词汇（崩坏の迷宫 2010），
被时间下界自然挡掉。报告 22 §4 早已把标题 IP 词列为对话同人的强特征，但只覆盖
头部，故仍不算确定性。

对话小说每章约 500 字、整本可连载很长，**单本字数不能判形态**（锚点 570712 为
88 万字对话）。v2 动机：E.11/E.12 后 `form=short` 仍混入大量 2–5 万字对话小说
（421290「成为符华圣痕的黑符」favs 7,881 > 真短篇头部「听雨」5,478），对话同字数
下章节数远超散文 → 点击/字天然更高。校准（`out/form_calibration.jsonl`，n=193，
真值 = App API `GET /novels/{id}/chaps` 章节中位字数 ≤1100）：R18 精确率 0.92、
召回 0.85；`clicks/字 < 3` 的书 0 对话（纯散文），`ckw<3` 层全部正确为散文。
残差：章均 1100–1250 字的边界书两可；病毒式传播的真散文短篇（ckw ≥ 50）可能误判。
互动小说是对话小说的子集，本地无法单独识别，并入合并口径。

口径权威说明见 `docs/form-definitions.md`、`analysis/references/moebattle-tags.md`
与报告 22。
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# 用户通过 App 逐条目验判为对话小说的 7 个征文（无「对话/点鸭」字样）
USER_VERIFIED_T = [
    "怪谈异闻主题征文长篇", "春节征文长篇", "穿越主题征文", "星穹小说家征文",
    "春节征文短篇", "战斗主题征文", "怪谈异闻主题征文短篇",
]
# 形态判据①的字数上界（同人+未签约）
MORPH_MAX_WORDS = 20_000
# 形态判据 v2 阈值（clicks/字，快照口径；2026-11-19 章节真值校准）
DIAL_CKW_FAN = 6.0      # 同人特征（genre/tags 含同人）
DIAL_CKW_SHORT = 13.0   # 非同人 & words ≤ 5 万
DIAL_CKW_MEDIUM = 30.0  # 非同人 & 5–15 万字
# 真短篇点击天花板（E.16，2026-11-19 用户裁定）：回到旧时光 clicks=215,723 为
# 真 short 点击上限；words ≤ 5 万且越过此线者判对话（不限同人/签约）。
DIAL_CLICKS_CEIL = 215_723
# 对话体时间下界（E.18，2026-11-19 用户裁定）：「对话体出现之前的 id 一定
# 不可能是对话」。硬证据 = 历史月榜 rank=4（对话月票榜）首月 2017-07
# （2016-10…2017-06 全部为空），同月出现首批「五征对话小说」投稿，最小 nid
# 83,818（2017-07-03）。此前 10 年没有任何对话征文标记，早期同人短篇是散文。
# 形态判据全部只在此后生效；征文标记（确定性）不受此限。
DIALOGUE_START = "2017-07"
DIALOGUE_START_NID = 83_818
# 真短篇收藏/点赞天花板（E.17，听雨 5,478 / 2,389）：仅用于 P7 断言，
# 不参与形态判定——越过者说明该书的 short 身份另有问题，须人工复核。
SHORT_MAX_FAVS = 5_478
SHORT_MAX_PRAISES = 2_389
# 同人短字数上界（E.17）：>5 万字的同人是正常散文连载，不判对话。
FAN_MAX_WORDS = 50_000
# 米哈游 IP 标题词的对话判定字数上界（E.18）：只吃短篇档，medium/long 另议。
IP_MAX_WORDS = 50_000
# 标题 IP 特征词（米哈游系为主，对话小说同人集中区）
IP_PATTERN = re.compile(
    "原神|崩坏|星穹|星铁|芙宁娜|钟离|纳西妲|琪亚娜|芽衣|姬子|雷电|梅比乌斯|"
    "奥托|布洛妮娅|希儿|舰长|女武神|米忽悠|胡桃|甘雨|刻晴|迪卢克|温迪|魈|"
    "宵宫|万叶|绫华|心海|雷真|死士|律者|卡芙卡|镜流|景元|流萤|花火|黄泉"
)


def mark(df: pd.DataFrame) -> pd.DataFrame:
    """返回副本，追加判据列。

    需要列：`contest` / `title` / `genre` / `tags` / `words`，以及
    `price_type`（或 `price`）；`clicks` 可选（缺失时 v2 的 ckw 条款不生效，
    仅判据①与原同人条款生效）。
    追加列：`mA` / `mT` / `marked`（判据①）、`tong` / `unsigned` /
    `ckw` / `morph`（判据②）、`hidden`（形态命中但无征文标记）、
    `ip_title`（判据③）。
    """
    d = df.copy()
    contest = d["contest"].fillna("").astype(str).str.strip()
    genre = d["genre"].fillna("").astype(str)
    tags = d["tags"].fillna("").astype(str)
    title = d["title"].fillna("").astype(str)
    price = (
        d["price_type"].fillna("").astype(str)
        if "price_type" in d.columns
        else d["price"].fillna("").astype(str)
    )
    words = pd.to_numeric(d["words"], errors="coerce").fillna(0).astype(int)

    d["mA"] = contest.str.contains("对话|点鸭", na=False)
    d["mT"] = contest.isin(USER_VERIFIED_T)
    d["marked"] = d["mA"] | d["mT"]
    d["tong"] = (genre == "同人") | tags.str.contains("同人", na=False)
    d["unsigned"] = ~price.isin(["VIP", "签约"])
    # 形态判据 v2：clicks/字（快照值）。缺失 clicks 时 ckw=0，v2 条款不生效。
    clicks_num = None
    if "clicks" in d.columns:
        w = words.clip(lower=1).to_numpy()
        clicks_num = pd.to_numeric(d["clicks"], errors="coerce").fillna(0)
        d["ckw"] = clicks_num.to_numpy() / w
    else:
        d["ckw"] = np.zeros(len(d))
    d["ip_title"] = title.str.contains(IP_PATTERN, na=False)
    # E.18 时间下界：对话体 2017-07 才存在，之前的 nid 一律不判形态。
    nid_col = "id" if "id" in d.columns else ("nid" if "nid" in d.columns else None)
    if nid_col is None:
        after_start = pd.Series(True, index=d.index)
    else:
        after_start = (pd.to_numeric(d[nid_col], errors="coerce").fillna(0)
                       >= DIALOGUE_START_NID)
    d["dialogue_era"] = after_start
    d["morph"] = after_start & (
        (d["tong"] & d["unsigned"] & (words <= MORPH_MAX_WORDS))          # 原条款
        | (d["tong"] & d["ckw"].ge(DIAL_CKW_FAN))                          # v2-a
        | (~d["tong"] & (words <= 50_000) & d["ckw"].ge(DIAL_CKW_SHORT))   # v2-b
        | (~d["tong"] & words.between(50_001, 150_000)
           & d["ckw"].ge(DIAL_CKW_MEDIUM))                                 # v2-c
        | (d["tong"] & (words <= FAN_MAX_WORDS))                           # v2-e（E.17）
        | (d["ip_title"] & (words <= IP_MAX_WORDS))                        # v2-f（E.18）
    )
    if clicks_num is not None:                                             # v2-d 天花板
        d["morph"] = d["morph"] | (after_start & (words <= 50_000)
                                   & clicks_num.gt(DIAL_CLICKS_CEIL))
    d["hidden"] = d["morph"] & ~d["marked"]
    return d


def dialogue_set(df: pd.DataFrame) -> pd.Series:
    """要剔除的「对话/互动形态」掩码（形态判据 ∪ 征文确定集）。"""
    d = mark(df) if "morph" not in df.columns else df
    return d["morph"] | d["marked"]

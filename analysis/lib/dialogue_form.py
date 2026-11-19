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
      - 保留原条款 (同人 + 未签约 + ≤ 2 万字)。
  * ③ 标题 IP 特征：含米哈游等 IP 词 = 同人对话小说的强特征（辅助）。

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
    d["morph"] = (
        (d["tong"] & d["unsigned"] & (words <= MORPH_MAX_WORDS))          # 原条款
        | (d["tong"] & d["ckw"].ge(DIAL_CKW_FAN))                          # v2-a
        | (~d["tong"] & (words <= 50_000) & d["ckw"].ge(DIAL_CKW_SHORT))   # v2-b
        | (~d["tong"] & words.between(50_001, 150_000)
           & d["ckw"].ge(DIAL_CKW_MEDIUM))                                 # v2-c
    )
    if clicks_num is not None:                                             # v2-d 天花板
        d["morph"] = d["morph"] | ((words <= 50_000)
                                   & clicks_num.gt(DIAL_CLICKS_CEIL))
    d["hidden"] = d["morph"] & ~d["marked"]
    d["ip_title"] = title.str.contains(IP_PATTERN, na=False)
    return d


def dialogue_set(df: pd.DataFrame) -> pd.Series:
    """要剔除的「对话/互动形态」掩码（形态判据 ∪ 征文确定集）。"""
    d = mark(df) if "morph" not in df.columns else df
    return d["morph"] | d["marked"]

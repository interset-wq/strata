"""对话/互动小说形态判据（报告 22 固化，供其它报告加注记与敏感性对比）。

本地数据没有「对话/互动小说」品类字段（无 typeId/categoryId），以下三条判据
都是**推断**，不是官方标记：

  * ① 征文标记：`contest` 含「对话/点鸭」= 对话小说（用户核实，确定性），
    另加用户 App 目验的 7 个征文（无关键字，属隐藏标记）；
  * ② 形态判据：同人 + 未签约 + 整本 ≤ 2 万字 = 对话/互动形态（估计）；
  * ③ 标题 IP 特征：含米哈游等 IP 词 = 同人对话小说的强特征（辅助）。

对话小说每章约 500 字、整本可连载很长，**单本字数不能判形态**（用户给定锚点
570712 为 88 万字对话小说），故判据②的字数上界只用于群体占比。
互动小说是对话小说的子集，本地无法单独识别，并入合并口径。

口径权威说明见 `docs/13-form-definitions.md`、`analysis/references/moebattle-tags.md`
与报告 22。
"""

from __future__ import annotations

import re

import pandas as pd

# 用户通过 App 逐条目验判为对话小说的 7 个征文（无「对话/点鸭」字样）
USER_VERIFIED_T = [
    "怪谈异闻主题征文长篇", "春节征文长篇", "穿越主题征文", "星穹小说家征文",
    "春节征文短篇", "战斗主题征文", "怪谈异闻主题征文短篇",
]
# 形态判据的字数上界
MORPH_MAX_WORDS = 20_000
# 标题 IP 特征词（米哈游系为主，对话小说同人集中区）
IP_PATTERN = re.compile(
    "原神|崩坏|星穹|星铁|芙宁娜|钟离|纳西妲|琪亚娜|芽衣|姬子|雷电|梅比乌斯|"
    "奥托|布洛妮娅|希儿|舰长|女武神|米忽悠|胡桃|甘雨|刻晴|迪卢克|温迪|魈|"
    "宵宫|万叶|绫华|心海|雷真|死士|律者|卡芙卡|镜流|景元|流萤|花火|黄泉"
)


def mark(df: pd.DataFrame) -> pd.DataFrame:
    """返回副本，追加判据列。

    需要列：`contest` / `title` / `genre` / `tags` / `words`，以及
    `price_type`（或 `price`）。
    追加列：`mA` / `mT` / `marked`（判据①）、`tong` / `unsigned` /
    `morph`（判据②）、`hidden`（形态命中但无征文标记）、`ip_title`（判据③）。
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
    d["morph"] = d["tong"] & d["unsigned"] & (words <= MORPH_MAX_WORDS)
    d["hidden"] = d["morph"] & ~d["marked"]
    d["ip_title"] = title.str.contains(IP_PATTERN, na=False)
    return d


def dialogue_set(df: pd.DataFrame) -> pd.Series:
    """要剔除的「对话/互动形态」掩码（形态判据 ∪ 征文确定集）。"""
    d = mark(df) if "morph" not in df.columns else df
    return d["morph"] | d["marked"]

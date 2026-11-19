"""`form` 的**确定性**判据：PC 详情页 DOM 的对话产品线声明（E.22）。

## 判据来源

对话小说/互动小说**不支持 Web 阅读**：详情页「预读章节」区不渲染正文，只放一行固定提示。

- 对话小说：`全新的对话小说版本,给你最棒的阅读体验!只能在APP上观看哦,扫码下载APP观看吧……`
- 互动小说（点鸭）：`全新的沉浸式互动小说,给你最棒的阅读体验!只能在APP上观看哦,……`（nid 72–76 万）
- 散文：同位置是**正文首段**（`圣堂内，清音和学姐一起……`／`巫马权背手而立……`）

DOM 位置：`.chapter-info .chapter-content`（`<p class="chapter-content chapter-normal">`）。
真值表 `anchors/web_dialogue.jsonl` 由 `fetchers/probe_web_dialogue.py` 抓取，
2026-11-19 覆盖中篇种子 944 本（363 对话 / 558 散文 / 22 无正文 / 1 死亡）。

## 为什么它是最高优先级的形态证据

* 产品线声明 > 征文组别：`contest` 只反映投稿赛道，3 本带正文征文标记的书被 DOM 判为对话
  （448045 玄幻征文、683752 冬季恋曲征文、607079 冬季征文），作者按对话编辑器写作但投了正文组。
* 产品线声明 > 点击/字估计：对话书 `ckw` 中位仅 2.71（最低 0.02），ckw 阈值（6/13/30）
  对中篇档近乎失效——363 本对话里 335 本 ckw < 6，用 ckw 判只能抓到 8%。
* 反向价值：4 本**沉浸式互动小说**的章节名是「第一章」（不是「话」），章节命名判据全部漏判，
  只有 DOM 抓到（745405 / 746269 / 729181 / 758261，nid 72–76 万）。

## 替代品与残余

章节标题计数单位（App `GET /novels/{id}/chaps`：对话书「第 N 话」、散文「第 N 章/序章」）
是强代理但**非确定性**：中篇 944 本里 3 本章节叫「话」而 DOM 有正文（550853 / 576854 / 16668），
故只作交叉校验列（`unit_evidence`），不参与判定。

`verdict=unknown`（详情页预读区为「暂无内容……」或空，22 本）时本模块返回空，由
`forms` 的其他级决定；其中章节单位为「话」者按对话兜底（1 本：607079）。

自洽性校验（写入报告）：363 本 DOM 判对话**全部** `nid ≥ 83,818`（对话体时代下界 E.18），
零例外——两条独立证据链互相印证。
"""

from __future__ import annotations

import json
import functools

import pandas as pd

from lib import paths

TRUTH_FILE = paths.ANCHORS_DIR / "web_dialogue.jsonl"
FALLBACK_DIALOGUE_NIDS = (607_079,)   # unknown 但章节单位=「话」（29/30 话）


@functools.lru_cache(maxsize=1)
def load() -> dict[int, str]:
    """nid → `dialogue` / `prose`。文件缺失时返回空表（判据静默降级）。"""
    if not TRUTH_FILE.exists():
        return {}
    out: dict[int, str] = {}
    for line in TRUTH_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out[int(rec["nid"])] = str(rec["form"])
    return out


def apply(df: pd.DataFrame) -> pd.Series:
    """返回与 `df` 同索引的证据列：`dialogue` / `prose` / `''`（无真值）。"""
    truth = load()
    if not truth or df.empty:
        return pd.Series("", index=df.index, dtype=object)
    col = "id" if "id" in df.columns else ("nid" if "nid" in df.columns else None)
    if col is None:
        return pd.Series("", index=df.index, dtype=object)
    nids = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    out = nids.map(truth).fillna("")
    out[nids.isin(FALLBACK_DIALOGUE_NIDS)] = "dialogue"
    return out.astype(object).set_axis(df.index)


def coverage() -> dict[str, int]:
    """真值表覆盖统计（供审计脚本与文档引用）。"""
    truth = load()
    from collections import Counter
    return dict(Counter(truth.values()))

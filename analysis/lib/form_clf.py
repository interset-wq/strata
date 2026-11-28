"""分档形态分类器（中篇档已校准；供**分级过滤**用，不作最终判据）。

## 为什么必须分档

E.23 的负结果证明：跨档迁移会失败——同一个标题词在不同字数档方向相反
（`原神` 在中篇档偏散文、长篇档 4/4 全对话）。根因是真值分布：1,040 条
DOM 真值 90% 落在 5–15 万字。**档内插值有效，跨档外推无效**，因此每个
字数档各自训练、各自评估、各自使用。

## 角色：分级过滤（triage），不是判定

DOM 一次请求 1 秒、确定性、可复算；分类器只用来**决定哪些书不必爬**：

1. 用档内真值训练（按作者分组交叉验证，防泄漏）；
2. 给全档打分，把 `p < LO` 判散文、`p > HI` 判对话，其余进「不确定区」；
3. 只爬不确定区，结果写回 `anchors/web_dialogue.jsonl`（DOM 仍为唯一权威）。

中篇档实测：OOF 准确率 0.957、不确定区 9%、自信区残留错误 0.9%
（详见 `probe_form_triage.py`）。分级后爬取量 28,167 → 3,665 本（13 分钟）。

## 用法

    from lib import form_clf
    form_clf.train("medium")              # 写 out/form_clf_medium.pkl
    p = form_clf.predict("medium", df)    # Series[0,1]
    tri = form_clf.triage("medium", df)   # DataFrame: p / zone

**禁止**把 p 直接写成 `books.form`：种子只接受 DOM 真值，概率标签会污染
形态分布本身（冷门对话书恰恰最容易被判低分，会带上热度偏置）。
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold

from lib import dialogue_form as DF, paths

# 分档边界，与 forms.SHORT_MAX_WORDS / MEDIUM_MAX_WORDS 一致
# 2026-11-27：短/中篇分界从 5 万改回 3 万口径（SHORT_MAX_WORDS=34_999）。
BANDS = {
    "short": (0, 34_999),
    "medium": (34_999, 150_000),
    "long": (150_000, 10**9),
}
ZONE_LO, ZONE_HI = 0.1, 0.9
MODEL_DIR = paths.OUT_DIR


def model_path(band: str) -> Path:
    return MODEL_DIR / f"form_clf_{band}.pkl"


def features(d: pd.DataFrame) -> pd.DataFrame:
    """纯快照特征。`d` 需先经 `dialogue_form.mark`。"""
    X = pd.DataFrame(index=d.index)
    w = pd.to_numeric(d["words"], errors="coerce").clip(lower=1)
    X["log_words"] = np.log10(w)
    X["log_clicks"] = np.log10(d["clicks"] + 1)
    X["log_favs"] = np.log10(d["favs"] + 1)
    X["log_praises"] = np.log10(d["praises"] + 1)
    X["log_ckw"] = np.log10(d["ckw"] + 1e-3)
    X["log_favs_w"] = np.log10(d["favs"] / w + 1e-4)
    X["log_praises_w"] = np.log10(d["praises"] / w + 1e-4)
    X["log_nid"] = np.log10(d["id"])
    X["tong"] = d["tong"].astype(int)
    X["ip"] = d["ip_title"].astype(int)
    X["marked"] = d["marked"].astype(int)
    X["prose_contest"] = d["prose_contest"].astype(int)
    X["n_tags"] = d["tags"].fillna("").astype(str).str.count(",") + 1
    X["title_len"] = d["title"].fillna("").astype(str).str.len()
    X["author_n"] = d.groupby("author")["id"].transform("size")
    return X


def in_band(d: pd.DataFrame, band: str) -> pd.Series:
    lo, hi = BANDS[band]
    w = pd.to_numeric(d["words"], errors="coerce").fillna(0)
    return (w > lo) & (w <= hi)


def load_truth() -> pd.DataFrame:
    t = pd.read_json(paths.ANCHORS_DIR / "web_dialogue.jsonl", lines=True)
    t["nid"] = t["nid"].astype("int64")
    t = t[t["form"].isin(["dialogue", "prose"])]
    df = pd.read_csv(paths.OUT_DIR / "novels.csv", low_memory=False)
    m = t.merge(df, left_on="nid", right_on="id")
    m["y"] = (m["form"] == "dialogue").astype(int)
    return DF.mark(m)


def _new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=3, max_iter=200, learning_rate=0.08,
        min_samples_leaf=20, l2_regularization=1.0, random_state=19,
    )


def train(band: str, save: bool = True) -> dict:
    """档内训练 + 按作者分组 5 折自评。返回评估指标。"""
    t = load_truth()
    t = t[in_band(t, band)]
    if len(t) < 80:
        raise ValueError(f"{band} 档真值仅 {len(t)} 条，不足以训练")
    X, y, g = features(t), t["y"].to_numpy(), t["author"].fillna("").astype(str).to_numpy()

    oof = np.zeros(len(y))
    for trn, te in GroupKFold(n_splits=5).split(X, y, g):
        m = _new_model().fit(X.iloc[trn], y[trn])
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    pred = oof >= 0.5
    conf = (oof < ZONE_LO) | (oof > ZONE_HI)
    metrics = {
        "band": band,
        "n": len(t),
        "n_dialogue": int(y.sum()),
        "auc": round(float(roc_auc_score(y, oof)), 3),
        "precision": round(float(precision_score(y, pred)), 3),
        "recall": round(float(recall_score(y, pred)), 3),
        "accuracy": round(float((pred == y).mean()), 3),
        "uncertain_share": round(float((~conf).mean()), 3),
        "confident_error": round(float((pred[conf] != y[conf]).mean()) if conf.any() else 0.0, 4),
    }

    final = _new_model().fit(X, y)
    if save:
        with model_path(band).open("wb") as f:
            pickle.dump({"model": final, "features": list(X.columns),
                         "zone": (ZONE_LO, ZONE_HI), "metrics": metrics}, f)
    return metrics


def predict(band: str, df: pd.DataFrame) -> pd.Series:
    p = model_path(band)
    if not p.exists():
        raise FileNotFoundError(f"缺模型 {p}，先跑 form_clf.train('{band}')")
    with p.open("rb") as f:
        obj = pickle.load(f)
    d = DF.mark(df.copy())
    X = features(d)[obj["features"]]
    return pd.Series(obj["model"].predict_proba(X)[:, 1], index=df.index)


def triage(band: str, df: pd.DataFrame) -> pd.DataFrame:
    """给整档打分并标注 zone：`prose` / `dialogue` / `uncertain`。"""
    p = predict(band, df)
    zone = np.where(p < ZONE_LO, "prose", np.where(p > ZONE_HI, "dialogue", "uncertain"))
    return pd.DataFrame({"nid": df["id"].to_numpy(), "p": p.round(4), "zone": zone},
                        index=df.index)

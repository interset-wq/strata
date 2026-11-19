"""形态分类器 baseline：能不能用可用特征复现 DOM 真值。

真值 = `anchors/web_dialogue.jsonl`（921 条详情页 DOM 判定，363 对话 / 558 散文）。
对照 = 关闭 DOM 两级的 `forms.classify`（即纯规则链）。
只在本地跑，不发起任何网络请求。

用法：`uv run python probe_form_classifier.py`
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, ".")
from lib import dialogue_form as DF  # noqa: E402
from lib import eras, forms as FM, paths  # noqa: E402


def truth() -> pd.DataFrame:
    rows = pd.read_json(paths.ANCHORS_DIR / "web_dialogue.jsonl", lines=True)
    rows["nid"] = rows["nid"].astype("int64")
    return rows[["nid", "form", "unit_evidence"]]


def features(df: pd.DataFrame) -> pd.DataFrame:
    """只用快照里拿得到的字段，不依赖任何 API。"""
    d = df.copy() if "ckw" in df.columns else DF.mark(df)
    words = pd.to_numeric(d["words"], errors="coerce").fillna(0).clip(lower=1)
    clicks = pd.to_numeric(d["clicks"], errors="coerce").fillna(0)
    favs = pd.to_numeric(d["favs"], errors="coerce").fillna(0)
    praises = pd.to_numeric(d["praises"], errors="coerce").fillna(0)
    est = eras.estimate(d["id"].tolist()).set_index("id")
    title = d["title"].fillna("").astype(str)
    tags = d["tags"].fillna("").astype(str)

    out = pd.DataFrame(index=d.index)
    out["log_words"] = np.log10(words)
    out["log_clicks"] = np.log10(clicks + 1)
    out["log_favs"] = np.log10(favs + 1)
    out["log_praises"] = np.log10(praises + 1)
    out["log_ckw"] = np.log10(clicks / words + 1e-3)
    out["log_fkw"] = np.log10(favs / words + 1e-4)
    out["log_pkw"] = np.log10(praises / words + 1e-4)
    out["log_nid"] = np.log10(pd.to_numeric(d["id"], errors="coerce").clip(lower=1))
    out["est_year"] = est["est_year"].reindex(d["id"]).to_numpy()
    out["est_gap"] = est["gap_days"].reindex(d["id"]).to_numpy()
    out["tong"] = d["tong"].astype(int)
    out["ip_title"] = d["ip_title"].astype(int)
    out["marked"] = d["marked"].astype(int)
    out["prose_contest"] = d["prose_contest"].astype(int)
    out["vip"] = d["price_type"].fillna("").astype(str).isin(["VIP", "签约"]).astype(int)
    out["finished"] = d["status"].fillna("").astype(str).str.contains("完结").astype(int)
    out["title_len"] = title.str.len()
    out["title_quote"] = title.str.contains("[「」『』“”\"]", regex=True).astype(int)
    out["title_ip"] = title.str.contains(DF.IP_PATTERN, regex=True).astype(int)
    out["n_tags"] = tags.ne("").astype(int) * tags.str.count(",").add(1)
    out["dialogue_era"] = d["dialogue_era"].astype(int)
    # 作者维度：该作者名下书的数量（对话小说作者往往只写对话）
    au = d["author"].fillna("").astype(str).str.casefold()
    out["author_n"] = au.map(au.value_counts()).astype(float)
    return out


def rule_score(df: pd.DataFrame) -> np.ndarray:
    """纯规则链（关掉 DOM 两级）给出的概率型分数：命中=1，否则 0。"""
    saved = FM.WD if hasattr(FM, "WD") else None
    import lib.web_dialogue as WD

    orig_file = WD.TRUTH_FILE
    WD.TRUTH_FILE = paths.ANCHORS_DIR / "__disabled__.jsonl"
    WD.load.cache_clear()
    try:
        form = FM.classify(df)
    finally:
        WD.TRUTH_FILE = orig_file
        WD.load.cache_clear()
    return form.eq("dialogue").astype(int).to_numpy(), saved


def report(name: str, y: np.ndarray, s: np.ndarray, thr: float = 0.5) -> dict:
    pred = s >= thr
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    auc = roc_auc_score(y, s)
    ap = average_precision_score(y, s)
    print(f"{name:22} AUC={auc:.4f} PR-AUC={ap:.4f} P={prec:.3f} R={rec:.3f} F1={f1:.3f} "
          f"(tp={tp} fp={fp} fn={fn})")
    return dict(name=name, auc=auc, ap=ap, prec=prec, rec=rec, f1=f1)


def main() -> None:
    t = truth()
    df = pd.read_csv(paths.OUT_DIR / "novels.csv", low_memory=False)
    d = t.merge(df, left_on="nid", right_on="id", how="inner")
    print(f"真值 {len(t)} 条，特征表匹配 {len(d)} 条；"
          f"dialogue {int((d.form == 'dialogue').sum())} / prose {int((d.form == 'prose').sum())}")
    y = (d["form"] == "dialogue").astype(int).to_numpy()
    d = DF.mark(d)

    X = features(d)
    print(f"特征 {X.shape[1]} 个，缺失率最高："
          f"{X.isna().mean().sort_values(ascending=False).head(3).round(3).to_dict()}")

    # 对照：现有规则链（不含 DOM）
    s_rule, _ = rule_score(d)
    report("规则链（无 DOM）", y, s_rule)

    groups = d["author"].fillna("").astype(str).str.casefold().to_numpy()
    oof = np.zeros(len(d))
    gkf = GroupKFold(n_splits=5)
    for tr, te in gkf.split(X, y, groups):
        m = HistGradientBoostingClassifier(max_depth=4, max_iter=300, learning_rate=0.06,
                                           min_samples_leaf=15, l2_regularization=1.0,
                                           random_state=19)
        m.fit(X.iloc[tr], y[tr])
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    report("分类器 @0.5", y, oof)

    # 阈值扫描
    print("\n阈值扫描：")
    best = None
    for thr in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        pred = oof >= thr
        tp = int((pred & (y == 1)).sum())
        fp = int((pred & (y == 0)).sum())
        fn = int((~pred & (y == 1)).sum())
        p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
        print(f"  thr={thr:.1f}  P={p:.3f} R={r:.3f} F1={2*p*r/max(p+r,1e-9):.3f} "
              f"(tp={tp} fp={fp} fn={fn})")
        if best is None or 2 * p * r / max(p + r, 1e-9) > best[1]:
            best = (thr, 2 * p * r / max(p + r, 1e-9))

    # 消融：看模型到底靠什么
    print("\n消融（单变量 AUC / PR-AUC）：")
    for c in X.columns:
        v = X[c].fillna(X[c].median()).to_numpy()
        try:
            print(f"  {c:16} AUC={roc_auc_score(y, v):.4f} AP={average_precision_score(y, v):.4f}")
        except ValueError:
            pass

    print("\n时代外推检查（只用 nid+est_year 训练，看全样本 AUC）：")
    Xi = X[["log_nid", "est_year", "dialogue_era"]].fillna(0)
    oof2 = np.zeros(len(d))
    for tr, te in gkf.split(Xi, y, groups):
        m = HistGradientBoostingClassifier(max_depth=3, max_iter=200, random_state=19)
        m.fit(Xi.iloc[tr], y[tr])
        oof2[te] = m.predict_proba(Xi.iloc[te])[:, 1]
    report("仅时代特征", y, oof2)

    # 错分明细
    pred = oof >= 0.5
    err = d[~(pred == y.astype(bool))].copy()
    err["p"] = oof[~(pred == y.astype(bool))]
    print(f"\n@0.5 错分 {len(err)} 本：")
    for _, r in err.sort_values("p").iterrows():
        print(f"  {r['nid']:7} true={r['form']:8} p={r['p']:.3f} w={r['words']:>7} "
              f"ckw={r['ckw']:>6.2f} tong={int(r['tong'])} "
              f"{str(r['title'])[:26]}")


if __name__ == "__main__":
    main()

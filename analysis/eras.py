"""nid → 日期定年。

方法
----
91 个锚点是 API 实测的作品创建时间（``addTime``），``nid`` 为站点全局自增
主键、严格单调，故可在锚点之间插值出任意 nid 的创建日期。

插值在 log(nid) 空间进行：nid 增速 20 年间从约 2 涨到约 330 本/天（180 倍），
log 空间更接近匀速。两端用边界段斜率外推，标记 ``extrap``；锚点采样按
分位点各抓 2 本相邻 nid，末段锚点常共享同一秒级时间戳，外推斜率必须跳过
同刻点，否则超界 nid 会被压到同一天。

置信度按两侧锚点的**日期跨度**分档（不是 nid 跨度）：隔一季内 high，
隔一年内 mid，更远 low；外推区一律 low。

误差
----
留一法（leave-one-out）实测。留出单元是「同一秒时间戳的整组锚点」——
相邻双胞胎锚点若只留出一个，另一个会泄漏答案，误差恒为 0。

迁移说明：引擎与锚点自 quarry/era.py 与 quarry/data/anchors 迁入（quarry
将退役），锚点为 API 实测，不可由 dataset.7z 重建，故入库存放于
``analysis/anchors/``。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
ANCHORS_PATH = ROOT / "anchors" / "nid_anchors.jsonl"

_EPOCH = np.datetime64("1970-01-01", "D")


def load_anchors(path: Path | str | None = None) -> pd.DataFrame:
    rows = [
        json.loads(line)
        for line in Path(path or ANCHORS_PATH).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    df = pd.DataFrame(rows)
    df["addTime"] = pd.to_datetime(df["addTime"])
    df = df.sort_values("nid").reset_index(drop=True)
    df["day"] = (df["addTime"].to_numpy(dtype="datetime64[D]") - _EPOCH).astype("float64")
    return df


class _Model:
    """log(nid) ↔ day 的分段线性映射。"""

    def __init__(self, anchors: pd.DataFrame) -> None:
        self.nid = anchors["nid"].to_numpy(dtype="float64")
        self.day = anchors["day"].to_numpy(dtype="float64")
        self.lnid = np.log(np.maximum(self.nid, 1.0))

    def _edge_slopes(self) -> tuple[float, float]:
        n = len(self.day)
        j = n - 1
        while j > 0 and (self.day[j] == self.day[j - 1] or self.lnid[j] == self.lnid[j - 1]):
            j -= 1
        lo_slope = (self.day[j] - self.day[j - 1]) / (self.lnid[j] - self.lnid[j - 1])
        i = 0
        while i < n - 1 and (self.day[i] == self.day[i + 1] or self.lnid[i] == self.lnid[i + 1]):
            i += 1
        hi_slope = (self.day[i + 1] - self.day[i]) / (self.lnid[i + 1] - self.lnid[i])
        return lo_slope, hi_slope

    def predict(self, ids: np.ndarray) -> np.ndarray:
        x = np.log(np.maximum(np.asarray(ids, dtype="float64"), 1.0))
        day = np.interp(x, self.lnid, self.day)
        lo, hi = x < self.lnid[0], x > self.lnid[-1]
        if lo.any() or hi.any():
            lo_slope, hi_slope = self._edge_slopes()
            if lo.any():
                day[lo] = self.day[0] + (x[lo] - self.lnid[0]) * lo_slope
            if hi.any():
                day[hi] = self.day[-1] + (x[hi] - self.lnid[-1]) * hi_slope
        return _EPOCH + np.round(day).astype("int64").astype("timedelta64[D]")


def estimate(ids) -> pd.DataFrame:
    """给一组 nid 定年。返回 id / est_date / est_year / confidence / mode。"""
    anchors = load_anchors()
    model = _Model(anchors)
    ids = np.asarray(ids, dtype="float64")

    est = model.predict(ids)
    idx = np.searchsorted(model.nid, ids)
    lo_i = np.clip(idx - 1, 0, len(model.nid) - 1)
    hi_i = np.clip(idx, 0, len(model.nid) - 1)
    gap_day = np.abs(model.day[hi_i] - model.day[lo_i])

    mode = np.where(
        ids < model.nid[0], "extrap_low",
        np.where(ids > model.nid[-1], "extrap_high", "interp"),
    )
    conf = np.where(gap_day <= 90, "high", np.where(gap_day <= 365, "mid", "low"))
    conf = np.where(mode == "interp", conf, "low")

    return pd.DataFrame(
        {
            "id": ids.astype("int64"),
            "est_date": est,
            "est_year": est.astype("datetime64[Y]").astype(int) + 1970,
            "gap_days": gap_day.astype("int32"),
            "mode": mode,
            "confidence": conf,
        }
    )


def cover_timestamp(cover_url) -> pd.Series:
    """从封面相对路径提取上传时间（月粒度）。

    路径形如 ``YYYY/MM/uuid.jpg``，时间戳是封面文件的**上传时间**：
    更换封面会换新文件，时间戳随之前移，因此它记录「最后一次封面上传」，
    一般不早于作品创建时间，可用作 nid 定年的独立交叉验证。

    两种情形必须区分（实测）：

    - 唯一封面（该文件只被一本书使用）：时间戳即该书自己的上传。
      与 nid 定年估计的偏差中位约 −11 天、最大提前 47 天——封面常在
      正式上架前随草稿上传。
    - 共用封面（同一文件出现在多本书的 cover_url 上）：novel_hub 爬虫
      在详情页抓到了 id 更大的书的封面（选择器缺陷）。**组内 id 最大者
      是封面属主**，其余成员的时间戳晚于自身创建（中位 +348 天）。
      验证：属主的时间戳与定年吻合率 89.8%、分布与唯一封面逐分位一致；
      其余成员 19.5%。build_csv 已按此规则清洗——共用组保留 id 最大者、
      其余置空——清洗后数据集内封面文件全库唯一。

    空值（无封面 / 占位封面 / 爬虫错值已清洗）返回 NaT。
    """
    c = pd.Series(cover_url).fillna("")
    m = c.str.extract(r"^(\d{4})/(\d{2})/")
    return pd.to_datetime(
        m[0].fillna("") + m[1].fillna(""), format="%Y%m", errors="coerce"
    )


def leave_one_out() -> pd.DataFrame:
    """留一法误差。留出单元 = 同一秒时间戳的整组锚点。"""
    a = load_anchors()
    recs = []
    for _, grp in a.groupby(a["addTime"].dt.floor("s"), sort=False):
        rest = a.drop(index=grp.index)
        if len(rest) < 3:
            continue
        model = _Model(rest)
        for _, row in grp.iterrows():
            pred = model.predict([row["nid"]])[0]
            true = np.datetime64(row["addTime"].date(), "D")
            kind = (
                "extrap_low" if row["nid"] < rest["nid"].min()
                else "extrap_high" if row["nid"] > rest["nid"].max()
                else "interp"
            )
            recs.append(
                {
                    "nid": int(row["nid"]),
                    "err_day": float((pred - true) / np.timedelta64(1, "D")),
                    "kind": kind,
                }
            )
    return pd.DataFrame(recs)

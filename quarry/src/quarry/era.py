"""nid → 日期定年。

依据
----
``novels.id`` 就是站点全局自增主键 ``nid``，严格单调：先创建的书 nid 更小。
这是唯一能覆盖全库 24.6 万本的时间轴——``last_update`` 是"最后更新"，
对老书来说是十年后的一次编辑，不能当创作时间。

方法
----
85 个锚点（API 实测的 ``addTime``），在 nid 空间做**分段线性插值**。
两端用边界段的斜率外推，并显式标记为 ``extrap``（锚点按 2.5% 分位采样，
所以头尾各 2.5% 的书天然落在锚点之外）。

验证
----
留一法（leave-one-out）：每次拿掉 1 个锚点，用其余 84 个预测它，看误差。
这比"最大误差 4 天"这类单点结论可靠——它给出的是整个区间的误差分布。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

_EPOCH = np.datetime64("1970-01-01", "D")


def _to_day(ts: pd.Series) -> np.ndarray:
    """datetime64 序列 → 距 1970-01-01 的天数（float，便于插值）。"""
    return (ts.to_numpy(dtype="datetime64[D]") - _EPOCH).astype("float64")


def _from_day(days: np.ndarray) -> np.ndarray:
    return _EPOCH + np.round(days).astype("int64").astype("timedelta64[D]")


def load_anchors(path: Path | None = None) -> pd.DataFrame:
    """读锚点，返回按 nid 升序、带 ``day`` 列的表。"""
    path = Path(path or config.ANCHORS_PATH)
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    df = pd.DataFrame(rows)
    df["addTime"] = pd.to_datetime(df["addTime"])
    df = df.sort_values("nid").reset_index(drop=True)
    df["day"] = _to_day(df["addTime"])
    return df


def check_anchors(df: pd.DataFrame) -> pd.DataFrame:
    """质量体检：真逆序、重复时间戳、间隙分布。

    返回间隙表，供报告与断言使用。``addTime`` 相等不算逆序（引进书批量导入
    会共享同一时间戳，如 2242/2243 同为 2006-08-26T02:46:36）。
    """
    d = df.reset_index(drop=True)
    nid = d["nid"].to_numpy(dtype="float64")
    day = d["day"].to_numpy()
    order_bad = int((np.diff(day) < 0).sum())   # 严格递减才算错
    ties = int((np.diff(day) == 0).sum())       # 同一时刻：允许，但记录
    gap_nid = np.diff(nid)
    gap_day = np.diff(day)
    return pd.DataFrame(
        {
            "i": np.arange(len(nid) - 1),
            "nid_from": nid[:-1].astype("int64"),
            "nid_to": nid[1:].astype("int64"),
            "gap_nid": gap_nid.astype("int64"),
            "gap_day": gap_day,
            "rate": gap_nid / np.maximum(gap_day, 0.5),  # 每天新增多少 nid
            "order_bad": order_bad,
            "ties": ties,
        }
    )


@dataclass
class NidEra:
    """nid ↔ 日期的分段映射。

    ``mode``:
        ``linear``  nid 空间线性插值
        ``log``     log(nid) 空间线性插值——nid 增长近似幂律（rate 从 1.8 涨到
                    328 nid/天，180 倍），log 空间更接近匀速
    """

    nid: np.ndarray
    day: np.ndarray
    mode: str = "linear"

    @classmethod
    def fit(cls, anchors: pd.DataFrame, mode: str = "linear") -> "NidEra":
        a = anchors.sort_values("nid")
        return cls(
            nid=a["nid"].to_numpy(dtype="float64"),
            day=a["day"].to_numpy(dtype="float64"),
            mode=mode,
        )

    def _x(self, nids) -> np.ndarray:
        x = np.asarray(nids, dtype="float64")
        return np.log(np.maximum(x, 1.0)) if self.mode == "log" else x

    def _edge_slopes(self) -> tuple[float, float]:
        """取首尾**斜率非零**的段。

        锚点采样是「每个分位点抓 2 本相邻 nid」，末两个锚点常在同一天
        （如 761711/761712 都是 2025-10-30）。若直接用最后两点算斜率，
        得到 0，所有超出末锚点的 nid 会被压到同一天。必须跳过同刻点。
        """
        ax = self._x(self.nid)
        day = self.day
        n = len(day)

        j = n - 1
        while j > 0 and (day[j] == day[j - 1] or ax[j] == ax[j - 1]):
            j -= 1
        lo_slope = (day[j] - day[j - 1]) / (ax[j] - ax[j - 1])

        i = 0
        while i < n - 1 and (day[i] == day[i + 1] or ax[i] == ax[i + 1]):
            i += 1
        hi_slope = (day[i + 1] - day[i]) / (ax[i + 1] - ax[i])

        return lo_slope, hi_slope

    def predict_day(self, nids) -> np.ndarray:
        x = self._x(nids)
        ax = self._x(self.nid)
        out = np.interp(x, ax, self.day)

        lo = x < ax[0]
        hi = x > ax[-1]
        if lo.any() or hi.any():
            lo_slope, hi_slope = self._edge_slopes()
            if lo.any():
                out[lo] = self.day[0] + (x[lo] - ax[0]) * lo_slope
            if hi.any():
                out[hi] = self.day[-1] + (x[hi] - ax[-1]) * hi_slope

        return out

    def predict(self, nids) -> np.ndarray:
        """返回日期（datetime64[D]）。超范围点用边界段斜率外推。"""
        return _from_day(self.predict_day(nids))


def _twin_groups(anchors: pd.DataFrame) -> list[np.ndarray]:
    """按秒级时间戳分组。

    采样时每个分位点抓了 2 本相邻 nid，两者 ``addTime`` 常完全相同（批量导入）。
    留一法若只去掉一个，另一个就成了"答案泄漏"，误差恒为 0。
    所以留出单元必须是整组时间戳。
    """
    a = anchors.reset_index(drop=True)
    key = a["addTime"].dt.floor("s")
    return [np.asarray(v) for v in a.groupby(key).indices.values()]


def leave_one_out(
    anchors: pd.DataFrame, mode: str = "linear"
) -> pd.DataFrame:
    """留一法误差。留出单元 = 同一时间戳的整组锚点。

    区分「内部插值」与「边界外推」两种情形——后者只有首尾才会出现。
    """
    a = anchors.reset_index(drop=True)
    recs = []
    for idxs in _twin_groups(a):
        rest = a.drop(index=idxs)
        if len(rest) < 3:
            continue
        model = NidEra.fit(rest, mode=mode)
        for i in idxs:
            nid_i = a.loc[i, "nid"]
            pred = model.predict([nid_i])[0]
            true = np.datetime64(a.loc[i, "addTime"].date(), "D")
            if nid_i < rest["nid"].min():
                kind = "extrap_low"
            elif nid_i > rest["nid"].max():
                kind = "extrap_high"
            else:
                kind = "interp"
            recs.append(
                {
                    "nid": int(nid_i),
                    "name": a.loc[i].get("name", ""),
                    "true": true,
                    "pred": pred,
                    "err_day": float((pred - true) / np.timedelta64(1, "D")),
                    "kind": kind,
                    "n_twins": len(idxs),
                }
            )
    return pd.DataFrame(recs)


def estimate(
    novels: pd.DataFrame, anchors: pd.DataFrame, mode: str = "log"
) -> pd.DataFrame:
    """给每本书定年，附置信度。

    置信度按「两侧锚点间隙」分档——间隙越大，插值的假设（nid 匀速增长）
    越不可靠。外推区一律标 low。
    """
    model = NidEra.fit(anchors, mode=mode)
    a_nid = model.nid
    a_day = model.day
    ids = novels["id"].to_numpy(dtype="float64")
    idx = np.searchsorted(a_nid, ids)
    lo = np.clip(idx - 1, 0, len(a_nid) - 1)
    hi = np.clip(idx, 0, len(a_nid) - 1)
    gap_nid = np.abs(a_nid[hi] - a_nid[lo])
    # 置信度看**日期跨度**，不是 nid 跨度：插值误差取决于两侧锚点隔了多久，
    # 而 nid 间隔能从 1 跳到 53,021，直接分档会让 99% 的书挤在同一档。
    gap_day = np.abs(a_day[hi] - a_day[lo])

    est = model.predict(ids)
    mode_arr = np.where(ids < a_nid[0], "extrap_low",
                        np.where(ids > a_nid[-1], "extrap_high", "interp"))

    # 固定阈值，物理含义明确：两侧锚点隔一个季度内 → 高可信；隔一年以上 → 低。
    # gap_days 中位 84 天、P90 211 天，所以多数书会落在 high/mid。
    conf = np.where(gap_day <= 90, "high",
                    np.where(gap_day <= 365, "mid", "low"))
    conf = np.where(mode_arr == "interp", conf, "low")

    out = pd.DataFrame(
        {
            "id": novels["id"].to_numpy(),
            "est_date": est,
            "nid_gap": gap_nid.astype("int64"),
            "gap_days": gap_day.astype("int32"),
            "mode": mode_arr,
            "confidence": conf,
        }
    )
    out["est_year"] = out["est_date"].dt.year.astype("int16")
    return out

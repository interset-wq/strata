"""nid → 日期定年。

方法
----
281 个锚点是作品创建时间实测：91 个来自 API（``addTime``），12 条为用户
核实创建时间（2026-11-16 并入，``source=user_verified``，见
``references/verified-dates.md``），177 条为 E.15 月榜遗漏书（2026-11-19
并入，``source=app_api``，App API 逐本 ``addTime``；高 nid 段由此外推转
内插）。``nid`` 为站点全局自增
主键、严格单调，故可在锚点之间插值出任意 nid 的创建日期。

插值在 log(nid) 空间进行：nid 增速 20 年间从约 2 涨到约 330 本/天（180 倍），
log 空间更接近匀速。两端用边界段斜率外推，标记 ``extrap``；锚点采样按
分位点各抓 2 本相邻 nid，末段锚点常共享同一秒级时间戳，外推斜率必须跳过
同刻点，否则超界 nid 会被压到同一天。

置信度按两侧锚点的**日期跨度**分档（不是 nid 跨度）：锚点书自身（App API
``addTime`` 直接核实）为 ``exact``；隔一季内 high，隔一年内 mid，更远 low；
外推区一律 low。

误差
----
留一法（leave-one-out）实测。留出单元是「同一秒时间戳的整组锚点」——
相邻双胞胎锚点若只留出一个，另一个会泄漏答案，误差恒为 0。

迁移说明：引擎与锚点自 quarry/era.py 与 quarry/data/anchors 迁入（quarry
将退役），锚点为 API 实测，不可由 dataset.7z 重建，故入库存放于
``analysis/anchors/``。

与正版日轻的关系（边界澄清）：最低端的 3 个锚点（nid 2242 / 2243 / 2347，
2006-08 至 2006-09）对应的书在数据集内已被整行剔除——站点早期上架的是
盗版日轻，后来正版授权版复用了同标题的旧 id。锚点的 ``addTime`` 记录的是
**该 nid 本身**的创建时刻（盗版条目时代），对 id 序列的日期映射依然成立；
被污染的是数据集里那 47 行的「书与其 id 不同时出生」，而不是锚点。故锚点
保留，剔除判据见 ``config.LICENSED_LN_AUTHORS``。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from lib import paths

ROOT = paths.ROOT
# 插值输入：91 个 API 实测锚点 + 12 条用户核实锚点（source=user_verified，
# 2026-11-16 经用户批准从 verified_dates.jsonl 并入，low 段系统性偏差修正）
ANCHORS_PATH = paths.NID_ANCHORS
# 用户核实创建时间的证据档案（12 条 exact）：已并入 ANCHORS_PATH 插值，
# 本文件保留原始记录、配对依据与溯源（source 均为 user_verified）
VERIFIED_PATH = paths.VERIFIED_DATES
# 粗略日期（「附近」）：现已清空；文件保留，备后续粗略日期
APPROXIMATE_PATH = paths.APPROXIMATE_DATES

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


def load_verified() -> pd.DataFrame:
    """用户核实创建时间的证据档案（12 条 ``bound_type=exact``）。

    2026-11-16 起已并入 ``ANCHORS_PATH`` 参与插值（用户批准的 low 段
    重标定），故现行 ``estimate()`` 对这 12 个 nid 的定年即 ``created_at``、
    ``delta_days`` 恒为 0。本函数保留用于：溯源（source / note）、
    以及用 91 个纯 API 锚点重算**并入前**偏差（见报告 01 §1）。

    返回列：nid / title / created_at / bound_type / source / verified_on /
    contest / note / est_date / confidence / gap_days / delta_days。
    ``delta_days`` = 精确创建时间 − nid 定年。
    """
    rows = [
        json.loads(line)
        for line in VERIFIED_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    v = pd.DataFrame(rows)
    v["created_at"] = pd.to_datetime(v["created_at"])
    est = estimate(v["nid"]).set_index("id")
    v["est_date"] = pd.to_datetime(v["nid"].map(est["est_date"]))
    v["confidence"] = v["nid"].map(est["confidence"])
    v["gap_days"] = v["nid"].map(est["gap_days"])
    v["delta_days"] = (v["created_at"] - v["est_date"]).dt.days
    return v.sort_values("nid").reset_index(drop=True)


def load_approximate() -> pd.DataFrame:
    """外部给出的**粗略**日期：误差 <7 天，约 80% 即为准确创建日。

    用户说明「粗略时间的误差小于 7，甚至 80% 的概率就是准确时间」，
    故它不是月级软约束，而是可回测定年误差的**强约束**（残差主要来自
    曲线而非参考日）。因仍有约 20% 概率存在 ≤7 天偏差，不并入插值锚点。
    返回列含 approx_date / est_date / delta_days / confidence / gap_days；
    ``delta_days`` = 参考日 − nid 定年。
    """
    rows = [
        json.loads(line)
        for line in APPROXIMATE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    v = pd.DataFrame(rows)
    v["approx_date"] = pd.to_datetime(v["approx_date"])
    est = estimate(v["nid"]).set_index("id")
    v["est_date"] = pd.to_datetime(v["nid"].map(est["est_date"]))
    v["confidence"] = v["nid"].map(est["confidence"])
    v["gap_days"] = v["nid"].map(est["gap_days"])
    v["delta_days"] = (v["approx_date"] - v["est_date"]).dt.days
    return v.sort_values("nid").reset_index(drop=True)


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
    """给一组 nid 定年。返回 id / est_date / est_year / confidence / mode。

    confidence 四档：``exact``（锚点书，est_date 即官方 addTime，非估计）、
    ``high``/``mid``/``low``（内插，按两侧锚点日期跨度）、外推一律 ``low``。
    """
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
    # Anchor nids carry the official App API addTime; np.interp reproduces
    # their exact day, so est_date is already the official value — only the
    # tier needs overriding (docs/metrics-definitions.md §1.1).
    conf = np.where(np.isin(ids, model.nid), "exact", conf)

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

    **运营位书例外（用户口述机制，2026-11-16）**：``featured=1`` 的非日轻
    由平台在 banner 更新后一段时间同步更换封面，操作方是平台而非作者，
    故其时间戳记录的是运营操作、不是作品创建。实测 71 本有封面的运营位书
    偏差中位 +338 天、±47 天窗口内 0 本（非运营位为 −11 天 / 88.9%），
    因此定年交叉验证必须剔除 ``featured=1``。撤下 banner 后 ``featured=0``
    但封面未回退的书仍可能保留运营期封面，是右侧长尾的来源之一；
    封面时间戳一般只能给出创建的弱下界，不可逐本反推上架日。

    空值（无封面 / 占位封面 / 爬虫错值已清洗）返回 NaT。
    """
    c = pd.Series(cover_url).fillna("")
    m = c.str.extract(r"^(\d{4})/(\d{2})/")
    return pd.to_datetime(
        m[0].fillna("") + m[1].fillna(""), format="%Y%m", errors="coerce"
    )


def snapshot_bounds(df: pd.DataFrame) -> dict:
    """数据内容上界——由数据集自身推导，不引用任何外部爬取日期。

    ``max(last_update)`` 是**书的内容更新时间上界**（不是快照时间/爬取时间：
    后者是 novel_hub release 2026-05-27 与各补爬批次 `observed_at`，见
    `dataset/README.md`）。此后上架的新书不在库内，因此它同时是「新书可见性」
    的截止线与「末次更新距今」的计时基准。数据集内最新 nid 的定年日给出
    可见作品的创建日上界。

    返回:
        content_end: 最新章节更新时间（内容上界）
        newest_created: 库内最新作品的创建日（nid 定年）
        date: 内容上界的日期字符串
        year_frac: 内容上界的十进年份，供「暴露年数」口径使用
        days_after: 内容上界之后仍出现在库中的作品数（应为 0）
    """
    upd = pd.to_datetime(df["updated_at"], errors="coerce")
    content_end = upd.max()
    est = df["est_date"] if "est_date" in df.columns else None
    newest = est.max() if est is not None else pd.NaT
    doy = int(content_end.dayofyear)
    return {
        "content_end": content_end,
        "newest_created": newest,
        "date": content_end.strftime("%Y-%m-%d"),
        "year_frac": content_end.year + (doy - 1) / 365,
        "days_after": int((est > content_end).sum()) if est is not None else 0,
    }


def staleness_days(df: pd.DataFrame, content_end: pd.Timestamp) -> pd.Series:
    """末次更新距内容上界的天数（断更时长），负值不存在。"""
    upd = pd.to_datetime(df["updated_at"], errors="coerce")
    return (content_end - upd).dt.days


def leave_one_out(anchors: pd.DataFrame | None = None) -> pd.DataFrame:
    """留一法误差。留出单元 = 同一秒时间戳的整组锚点。

    ``anchors`` 缺省用全部锚点（281 = 91 API 实测 + 12 条用户核实 + 177 条
    E.15 app_api）；传入过滤后的锚点可对比并入前后的误差口径。
    E.15 并入前后（interp 段）：p90 10d→3d、均值 13.8d→5.1d。
    """
    a = anchors if anchors is not None else load_anchors()
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

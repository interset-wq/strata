"""从第三方 SFACG 观测站采集精确上架时间，交叉校验本项目的定年体系。

背景：`analysis/references/sfacg-endpoints.md` 记录了 SFACG 的 15 个公开端点，
但**没有一个提供上架时间（addTime）**——上游 jsonl 也没有该字段，因此本项目
的定年只能靠 `log(nid) ↔ day` 的分段线性反推（104 锚点，LOO P99 = 50 天）。

第三方观测站 `book.l66526652.top`（菠萝包情报屋）的公开接口会返回精确到秒的
`published_at`，其 `publication_basis` 字段自述为 `sfacg_app.addTime`，
即来自 SFACG 移动端 App API 的建档时间。本脚本用它做**外部交叉校验**：
本项目的定年是自建体系，外部精确日期能独立暴露系统性偏差。

用法：
    uv run python analysis/fetchers/probe_external_dates.py --collect --days 40
    uv run python analysis/fetchers/probe_external_dates.py --collect --from 2024-04-12 --to 2026-05-01
    uv run python analysis/fetchers/probe_external_dates.py --compare

采集走该站的 `/api/publication-calendar?date=`（按日新书，每条含 published_at）。
该站观测史始于 2024-04-12（更早日期 total=0），因此 2024-04 之前无历史可查。
分页：`page_size` 硬上限 50，`page` 参数有效，`offset` 无效。
间隔 ≥0.5 s、总量受 --days/--from/--to 控制，不做高频抓取。输出 out/external_dates.jsonl。

注意：本脚本只取**书目元数据**（nid + 上架时间），不取正文、不取评论。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import eras, paths

BASE = "https://book.l66526652.top"
CALENDAR = f"{BASE}/api/publication-calendar"
UA = "Mozilla/5.0 (compatible; strata-research/1.0; +metadata-validation)"
PAGE_SIZE = 50  # 实测硬上限：page_size 设 100/200/500/1000 均被截断到 50


def _fetch_day(session: requests.Session, d: str) -> list[dict]:
    """取某一天的全部新书（翻页至不足一页为止）。"""
    rows: list[dict] = []
    page = 1
    while True:
        resp = session.get(
            CALENDAR,
            params={"date": d, "page_size": PAGE_SIZE, "page": page},
            timeout=25,
        )
        if resp.status_code != 200:
            print(f"  {d} page={page} HTTP {resp.status_code}")
            break
        chunk = resp.json().get("rows", [])
        rows.extend(chunk)
        # 不足一页 = 最后一页；page 越界时该站会回退到末页，故以长度判定
        if len(chunk) < PAGE_SIZE:
            break
        page += 1
        if page > 40:  # 安全上限，防止该站异常时死循环
            break
    return rows


def collect(days: int, out_path: Path, from_date: str | None = None,
            to_date: str | None = None) -> int:
    """按日期采集新书的上架时间，写 jsonl。"""
    today = date.today()
    if from_date:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date) if to_date else today
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur.isoformat())
            cur += timedelta(days=1)
    else:
        # 从今天往前均匀取 days 天
        span = min(days * 3, 900)
        dates = [(today - timedelta(days=offset)).isoformat() for offset in range(0, span, 3)][:days]

    seen: dict[str, str] = {}
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})

    for i, d in enumerate(dates, 1):
        try:
            rows = _fetch_day(session, d)
        except Exception as exc:  # noqa: BLE001 - 探针不因单点失败中断
            print(f"[{i}/{len(dates)}] {d} 失败：{exc}")
            time.sleep(1.0)
            continue

        for row in rows:
            nid = str(row.get("novel_id", ""))
            pub = row.get("published_at")
            if nid and pub:
                seen.setdefault(nid, pub)
        if i % 20 == 0 or i == len(dates):
            print(f"[{i}/{len(dates)}] {d} +{len(rows)} 条（累计 {len(seen)}）")
        time.sleep(0.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for nid, pub in sorted(seen.items(), key=lambda kv: int(kv[0])):
            fh.write(json.dumps({
                "nid": int(nid),
                "published_at": pub,
                "source": "book.l66526652.top/api/publication-calendar",
                "basis": "sfacg_app.addTime",
            }, ensure_ascii=False) + "\n")
    print(f"写出 {len(seen)} 条 → {out_path}")
    return len(seen)


def compare(in_path: Path) -> None:
    """用采集到的精确上架时间校验本项目定年。"""
    import pandas as pd

    rows = []
    for line in in_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        print("无样本，先跑 --collect")
        return

    df = pd.DataFrame(rows)
    df["published_at"] = pd.to_datetime(df["published_at"])
    df["nid"] = df["nid"].astype("int64")

    est = eras.estimate(df["nid"].to_numpy())
    df = df.merge(est, left_on="nid", right_on="id", how="left")
    df["est_date"] = pd.to_datetime(df["est_date"])
    df["err_days"] = (df["est_date"] - df["published_at"]).dt.days.astype("int64")
    df["abs_err"] = df["err_days"].abs()

    print(f"\n样本 {len(df)} 条，nid 范围 {df['nid'].min()}–{df['nid'].max()}")
    print(f"真实上架区间：{df['published_at'].min()} → {df['published_at'].max()}")
    print("\n=== 整体误差（天）===")
    for q in (0.5, 0.75, 0.9, 0.95, 0.99):
        print(f"  P{int(q*100):02d} = {df['abs_err'].quantile(q):.0f}")
    print(f"  max = {df['abs_err'].max()}  mean = {df['abs_err'].mean():.1f}  "
          f"有符号均值 = {df['err_days'].mean():+.1f}")
    print(f"  完全一致（±1 天内）占比：{(df['abs_err'] <= 1).mean()*100:.1f}%")
    print(f"  误差 ≤30 天：{(df['abs_err'] <= 30).mean()*100:.1f}%   "
          f"≤90 天：{(df['abs_err'] <= 90).mean()*100:.1f}%")

    print("\n=== 按定年置信度分组 ===")
    for conf, grp in df.groupby("confidence"):
        print(f"  {conf:>5}  n={len(grp):4d}  中位 |err|={grp['abs_err'].median():6.0f}  "
              f"P90={grp['abs_err'].quantile(0.9):6.0f}  max={grp['abs_err'].max():5d}")

    print("\n=== 按外推/内插模式分组 ===")
    for mode, grp in df.groupby("mode"):
        print(f"  {mode:>12}  n={len(grp):4d}  中位 |err|={grp['abs_err'].median():6.0f}  "
              f"P90={grp['abs_err'].quantile(0.9):6.0f}")

    print("\n=== 误差最大的 10 条 ===")
    worst = df.reindex(df["abs_err"].sort_values(ascending=False).index).head(10)
    for _, r in worst.iterrows():
        print(f"  nid={int(r['nid']):>7}  真实={r['published_at']:%Y-%m-%d}  "
              f"估计={r['est_date']:%Y-%m-%d}  err={r['err_days']:+5d}  "
              f"({r['mode']}/{r['confidence']})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true", help="采集上架时间样本")
    ap.add_argument("--compare", action="store_true", help="与本项目定年对比")
    ap.add_argument("--days", type=int, default=40, help="采集天数（默认 40，近端均匀取样）")
    ap.add_argument("--from", dest="from_date", default=None,
                    help="起始日期 YYYY-MM-DD（逐日全量采集；该站观测史始于 2024-04-12）")
    ap.add_argument("--to", dest="to_date", default=None, help="结束日期 YYYY-MM-DD")
    ap.add_argument("--path", default=str(paths.OUT_DIR / "external_dates.jsonl"))
    args = ap.parse_args()

    out = Path(args.path)
    if args.collect:
        collect(args.days, out, args.from_date, args.to_date)
    if args.compare:
        compare(out)
    if not (args.collect or args.compare):
        ap.print_help()

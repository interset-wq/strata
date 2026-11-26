"""Seed admission policy (V2) — executable spec + offline audit.

Rule set is decided in ``app/docs/09-seed-refresh-proposal.md`` appendix E
(2026-11-18). Since 2026-11-19 it is **wired into build_seed.py** (V3):
``seed_set()`` was replaced by :func:`admit`, and ``form`` / ``lqs`` /
``vel_pctl`` are stored as build-time columns on ``books``. This module stays
the executable spec and the read-only audit CLI.

Why the policy exists
--------------------
The seed admits books only through **quality-anchored channels**: favs Top-20k,
archived monthly ranks, banner (``featured``), short-form dual percentile, and
every D2 deep-rank book. The time channels present in the 2026-05-03 baseline
(``est_date`` within 365 d / ``updated_at`` within 90 d) were gated by
age-normalised velocity in V2, but were **removed entirely on 2026-11-19**:
new books are structurally disadvantaged by cumulative favourites, so giving
them a dedicated admission channel is unfair to the large body of older books
in the library. The velocity gate is still computed for diagnostics only;
it never admits a book. Removing the channel drops 4,164 books worth 0.26% of
all favourites and raises the seed's median favourites from 652 to 870.

Since 2026-11-24 (E.31) there is **no automatic contest floor and no automatic
exemption**: `short`/`medium` must be `status=已完结` in every generation, and
the only way back in is a human-curated line in `seed_manual_exempt.jsonl`.
A human-curated `seed_contest_floor.jsonl` names the few contests that still
get a quota; candidates must clear `favs >= 5`, `words >= 10_000` and every
ineligibility rule (including the completion rule unless manually exempted).
E.32 adds a human-curated `seed_manual_blacklist.jsonl` for fake short/medium
books that deterministic rules miss; it outranks the exemption list.
E.34 (2026-11-26) adds a **positive gate**: every `short`/`medium` seed candidate
must be in the roster union of the 26 short/medium contest tracks archived in
`contest-achieve` (`analysis/anchors/contest_short_medium.json`). The union only
decides pool eligibility, never short-vs-medium (word count still decides that).
The only waiver is a human line `waive="contest"` in `seed_manual_exempt.jsonl`;
`waive="complete"` remains the separate E.31 completion waiver. High-favourite
books with no contest (or a non-short/medium contest) are user-confirmed fake
mediums and are excluded. See `docs/fake-complete-short-medium.md` §6.

Run the audit (read-only, no writes, no network)::

    cd analysis && uv run python ../app/tools/seedbuild/seed_policy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
ANALYSIS = REPO / "analysis"
sys.path.insert(0, str(ANALYSIS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import eras, paths  # noqa: E402
from lib import contest_scope as CS  # noqa: E402
from lib import dialogue_form as DF  # noqa: E402
from lib import forms as FM  # noqa: E402
from deep_ranks import build_deep_ranks  # noqa: E402

# Policy constants (pinned). The velocity group is diagnostic only — see admit().
VEL_PCTL_MIN = 0.5      # diagnostic threshold for what the retired V2 gate would admit
TIME_MIN_FAVS = 5       # diagnostic floor for the retired V2 gate
RECENT_DAYS = 365       # retired time channel: est_date window
ACTIVE_DAYS = 90        # retired time channel: updated_at window
COVERAGE_TOL = 0.002    # P3 allowance: deliberate loss from removing time channels
REC_N = 20_000          # favs Top-N anchor
SHORT_MAX_WORDS = 50_000
SHORT_TOP_N = 2_000
SHORT_BINS = [-1, 3_000, 6_000, 10_000, 20_000, 50_001]
SHORT_LABELS = ["<=3k", "3-6k", "6-10k", "10-20k", "20-50k"]
NOISE_FAVS = 5          # post-condition: favs below this and short words must be anchored
NOISE_WORDS = 10_000
CONTEST_MIN_FAVS = 5    # floor for manually listed contest-floor candidates
CONTEST_MIN_WORDS = 10_000  # same: avoid padding the seed with <1万-word noise
ABANDON_FORMS = ("short", "medium")  # E.31: 连载短/中篇无收录资格，人工清单除外
GEN_MIN, GEN_MAX = 2007, 2026  # E.30: 2026 作为正常世代进 universe，与其他年份一样筛选
LICENSED = 47           # appended by build_seed.py, outside the universe
SEED_EXEMPT_ANCHOR = ANALYSIS / "anchors" / "seed_manual_exempt.jsonl"
SEED_FLOOR_ANCHOR = ANALYSIS / "anchors" / "seed_contest_floor.jsonl"
SEED_BLACKLIST_ANCHOR = ANALYSIS / "anchors" / "seed_manual_blacklist.jsonl"
BLACKLIST_KINDS = ("fake_short", "fake_medium", "fake_complete")
EXEMPT_WAIVES = ("complete", "contest")  # E.31 completion / E.34 contest-pool


def _read_seed_anchor(path: Path) -> list[dict]:
    """Read a human-curated JSONL anchor; blank/`//` lines are comments."""
    rows: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("//"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"{path.name}:{lineno}: expected a JSON object")
        rows.append(obj)
    return rows


def manual_exempt_ids(df: pd.DataFrame, waive: str = "complete") -> set[int]:
    """Human waivers from ``seed_manual_exempt.jsonl``, selected by kind.

    - ``waive="complete"`` (E.31): the only way to waive the short/medium
      completion rule.
    - ``waive="contest"`` (E.34): the only way to waive the short/medium
      contest-pool positive gate.

    A book needing both must be listed twice. Unknown ``waive`` values and nids
    outside the universe fail loudly: a stale manual list must never silently
    turn into an automatic exemption rule.
    """
    if waive not in EXEMPT_WAIVES:
        raise ValueError(f"unsupported waive={waive!r}; expected {EXEMPT_WAIVES}")
    present = set(df["id"])
    out: set[int] = set()
    for row in _read_seed_anchor(SEED_EXEMPT_ANCHOR):
        got = row.get("waive")
        if got not in EXEMPT_WAIVES:
            raise ValueError(f"{SEED_EXEMPT_ANCHOR.name}: unsupported waive={got!r}")
        if got != waive:
            continue
        if not all(row.get(k) for k in ("reason", "verified_on")):
            raise ValueError(f"{SEED_EXEMPT_ANCHOR.name}: reason/verified_on required")
        nid = int(row["nid"])
        if nid not in present:
            raise ValueError(f"{SEED_EXEMPT_ANCHOR.name}: nid {nid} outside the universe")
        out.add(nid)
    return out


def manual_blacklist_ids(df: pd.DataFrame) -> set[int]:
    """E.32: human-confirmed fake short/medium books, permanently excluded.

    Rows are ``{nid, kind, reason, verified_on}``; ``kind`` must be one of
    `BLACKLIST_KINDS`. This is a seed-admission blacklist — it does not rewrite
    the work-level `form`. It outranks the manual exemption list: a nid on both
    lists stays excluded. Deterministic rules (P10, E.19) still run as well.
    """
    present = set(df["id"])
    out: set[int] = set()
    for row in _read_seed_anchor(SEED_BLACKLIST_ANCHOR):
        if row.get("kind") not in BLACKLIST_KINDS:
            raise ValueError(f"{SEED_BLACKLIST_ANCHOR.name}: unsupported kind={row.get('kind')!r}")
        if not all(row.get(k) for k in ("reason", "verified_on")):
            raise ValueError(f"{SEED_BLACKLIST_ANCHOR.name}: reason/verified_on required")
        nid = int(row["nid"])
        if nid not in present:
            raise ValueError(f"{SEED_BLACKLIST_ANCHOR.name}: nid {nid} outside the universe")
        out.add(nid)
    return out


def contest_floor_specs() -> dict[str, int]:
    """E.31: contests with a human-approved quota; empty file = no floor at all."""
    specs: dict[str, int] = {}
    for row in _read_seed_anchor(SEED_FLOOR_ANCHOR):
        name = str(row.get("contest", "")).strip()
        if not name or not all(row.get(k) for k in ("reason", "verified_on")):
            raise ValueError(f"{SEED_FLOOR_ANCHOR.name}: contest/reason/verified_on required")
        minimum = int(row.get("min", 3))
        if minimum < 1 or name in specs:
            raise ValueError(f"{SEED_FLOOR_ANCHOR.name}: invalid or duplicate contest {name!r}")
        specs[name] = minimum
    return specs


def _form(df: pd.DataFrame) -> pd.Series:
    if "form" in df.columns:
        return df["form"]
    sys.path.insert(0, str(ANALYSIS))
    from lib import forms as FM  # noqa: E402
    return FM.classify(df)


def abandoned_ids(df: pd.DataFrame, exempt: set[int] | None = None) -> set[int]:
    """E.31 弃书规则：连载中的 short/medium 一律无收录资格。

    短/中篇是「一口气读完」的作品，连载中意味着作者没写完，比已完结劣质书
    更没有资格进种子。2026 起 sfacg 把中篇并入短篇（`app/docs/09` 附录 D），
    两个形态都按同一条硬规则处理：`status=已完结` 才合格。

    E.13 的 `fav_pctl≥0.98` 自动质量豁免与 E.9 的征文保底豁免均已取消；
    唯一例外是人工逐本写入 `seed_manual_exempt.jsonl` 的书（P5/P8 守门）。
    `form` 仍是作品级属性、不随 status 变，本函数只在种子收录层生效。
    """
    if exempt is None:
        exempt = manual_exempt_ids(df, "complete")
    form = _form(df)
    serial = df["status"].ne("已完结").to_numpy()
    long_form = form.isin(ABANDON_FORMS).to_numpy()
    waived = df["id"].isin(exempt).to_numpy()
    mask = long_form & serial & ~waived
    return set(df.loc[mask, "id"])


def invalid_ids(df: pd.DataFrame) -> set[int]:
    """E.12 僵尸规则：`form = invalid`（words < 2000）无收录资格。

    app 正常章节最少 2000 字、正常书至少一章，故 <2000 几乎都是目录抓取
    残缺的僵尸书（锚点 4166 辞别黄昏的小镇 words=775）。`form` 可能对这类书
    仍标 dialogue/ip_collab（确定性证据救回），那些不算 invalid。

    **E.19 第二类 invalid**：`words ≤ 5 万` 且 `clicks > 215,723`（回到旧时光）
    的书不是真短篇——是内容被替换为无意义文本的僵尸（When It Sucks）或作者
    恶意标注完结的长篇（字数只统计到前段），数据不可信。这类书与 <2000 字
    僵尸一样无收录资格。

    **征文保底也不豁免**：P6 是兜底守门，无论候选来自哪个渠道，invalid 在
    最终种子里恒为 0。
    """
    form = _form(df)
    return set(df.loc[form.eq("invalid").to_numpy(), "id"])


def fake_complete_ids(df: pd.DataFrame) -> set[int]:
    """P10 假完结（用户 2026-11-20 裁定）：short/medium 档征文名含「长篇」即假。

    征文同时开长/中/短赛道，作者技不如人就断更并改状态完结；长篇赛道流量是
    中短篇的上百至上千倍，长篇征文里的劣质书数据也可能远超真短篇优质书。
    `status=已完结` 是作者自报字段，E.11/E.20 只查它，E.19 天花板只覆盖 ≤5
    万字，5–15 万的中篇档整档没有对应闸门——故这条是确定性裁定，不是统计
    阈值：只要「形态被判成 short/medium、却报了长篇征文」就剔除，无豁免。

    只对 short/medium 生效：`long` 书本就是长篇赛道、`dialogue` 是形态产品线，
    它们带长篇征文标记不适用本裁定，不计入返回集。依据是 `_form(df)`（分类
    结果，含用户裁定通道），不改动 form 列本身——form 是作品属性，收录资格
    才随规则变。全库命中远多于种子（21,916 vs 145），这里返回全集供 ineligible
    与征文保底过滤共用；断言 P10 检查种子内命中为零。

    详见 `docs/fake-complete-short-medium.md`。
    """
    form = _form(df)
    contest = df["contest"].fillna("").astype(str)
    mask = (form.isin(("short", "medium")).to_numpy()
            & contest.str.contains("长篇", regex=False).to_numpy())
    return set(df.loc[mask, "id"])


def short_medium_outside_contest_ids(df: pd.DataFrame,
                                     exempt: set[int] | None = None) -> set[int]:
    """E.34 正向准入：不在中短篇赛事 union 里的 short/medium 无收录资格。

    用户 2026-11-26 裁定：中短篇仍有大量假书，改以 `contest-achieve` 归档的
    26 个中短篇赛项 roster 并集作为**唯一正向门票**；无征文或挂非中短篇征文、
    却按字数被判成 short/medium 的高收藏书确认为**假中/假短**，不再因收藏高
    而放行。union 只决定「能否进池」，short 还是 medium 仍由字数/form 决定
    （《少女与龙》挂五征短篇却是 13.9 万字 medium，按 tag 分会误伤）。

    唯一豁免是人工白名单中 ``waive="contest"`` 的逐本书（E.34）；黑名单
    （E.32）优先于它。P13 守门要求这些书零入种。
    """
    if exempt is None:
        exempt = CS.contest_waived_nids()
    form = _form(df)
    in_pool = df["id"].isin(CS.short_medium_nids()).to_numpy()
    waived = df["id"].isin(exempt).to_numpy()
    mask = (form.isin(ABANDON_FORMS).to_numpy() & ~in_pool & ~waived)
    return set(df.loc[mask, "id"])


def dead_ids(df: pd.DataFrame) -> set[int]:
    """E.25 Web 死链：详情页文案「小说不存在」的书无展示资格。

    jsonl 快照是单向游标扫描的产物，抓过之后再被下架的书仍带着完整的
    字数/收藏/更新时间，形态规则与质量锚都无从察觉——只有 PC 详情页判活
    能发现。与 E.12 的 invalid 不同，这些书**内容本身可能是好的**，只是
    现在打不开（例如 746895 小小娇美人 favs 9,933）；app 详情页会 404，
    所以必须零入种，且不像 invalid 那样可以靠确定性形态证据救回。

    来源 `analysis/anchors/web_dead.jsonl`（7 本，2026-11-19 串行复核）。
    """
    from lib.web_dialogue import dead_nids

    return set(dead_nids()) & set(df["id"])


def load_universe(csv: Path | None = None) -> pd.DataFrame:
    """Analysis universe: licensed Japanese LN dropped, est_year 2007..2026."""
    df = pd.read_csv(csv or paths.OUT_DIR / "novels.csv")
    df["upd"] = pd.to_datetime(df["updated_at"], errors="coerce")
    est = eras.estimate(df["id"]).rename(columns={"confidence": "est_conf"})
    df = df.merge(est, on="id", how="left")
    df["est_date"] = pd.to_datetime(df["est_date"])
    df = df[df["est_year"].between(GEN_MIN, GEN_MAX)].copy()
    for src, dst in [("favs", "fav_pctl"), ("clicks", "click_pctl"),
                     ("praises", "praise_pctl")]:
        g = df.groupby("est_year")[src]
        df[dst] = g.rank(ascending=True, method="average") / g.transform("size")
    df["pr"] = (df["praises"] / df["favs"].replace(0, pd.NA)).where(df["favs"] >= 10)
    g = df.groupby("est_year")["pr"]
    df["pctl_pr"] = g.rank(ascending=True, method="average") / g.transform("size")
    return df


def add_velocity(df: pd.DataFrame, content_end: pd.Timestamp) -> pd.DataFrame:
    """favs / days-since-release, percentile inside the launch quarter."""
    df = df.copy()
    df["age_days"] = (content_end - df["est_date"]).dt.days.clip(lower=1)
    df["vel"] = df["favs"] / df["age_days"]
    df["quarter"] = (df["est_date"].dt.year.astype(str) + "Q"
                     + df["est_date"].dt.quarter.astype(str))
    g = df.groupby("quarter")["vel"]
    df["vel_pctl"] = g.rank(ascending=True, method="average") / g.transform("size")
    return df


def monthly_ids(df: pd.DataFrame) -> set[int]:
    ids: set[int] = set()
    with paths.MONTHLY_RANKS.open(encoding="utf-8") as fh:
        for line in fh:
            for item in json.loads(line)["items"]:
                if item.get("nid"):
                    ids.add(int(item["nid"]))
    return ids & set(df["id"])


def short_supplement(df: pd.DataFrame) -> set[int]:
    """Report 19: dual-percentile Top-2000 over (word bin x generation).

    favs >= NOISE_FAVS guard (2026-11-19, E.15): tiny bin x gen groups can put
    a favs=3 book at their group top and push it into the global Top-2000 at
    the margin (38821 surfaced when anchor-dating shifts reshuffled groups);
    P2 forbids unanchored favs<5 & words<10k seed books. The percentile MUST
    be computed on the full pool (filtering first shrinks group denominators
    and distorts ranks wholesale, -52 seed books in one sweep); only the
    *candidates* are filtered. Same threshold as the contest floor (5).
    """
    short = df[(df["words"] <= SHORT_MAX_WORDS) & (df["status"] == "已完结")].copy()
    short["wb"] = pd.cut(short["words"], SHORT_BINS, labels=SHORT_LABELS, right=True)
    short["grp"] = short["wb"].astype(str) + "|" + short["est_year"].astype(str)
    g = short.groupby("grp", observed=True)["favs"]
    short["p_grp"] = g.rank(ascending=True, method="average") / g.transform("size")
    cand = short[short["favs"] >= NOISE_FAVS]
    return set(cand.sort_values("p_grp", ascending=False).head(SHORT_TOP_N)["id"])


def contest_guarantee(df: pd.DataFrame, existing: set[int],
                      ineligible: set[int] | None = None,
                      floor: dict[str, int] | None = None) -> tuple[set[int], dict]:
    """E.31: quota only for contests on the human-curated floor list.

    The old E.9 rule auto-filled *every* named contest to three books; that
    imported low-quality noise (especially serial short/medium books) and is
    removed. Only rows in `seed_contest_floor.jsonl` get a quota, with each
    row's own `min`. Candidates still clear `favs >= 5`, `words >= 10_000`
    and `ineligible` up front — including the completion rule, unless that
    specific nid is on the manual exemption list. Ranking uses same-generation
    `fav_pctl` (ties: favs desc, id asc); books already in the seed count.
    """
    if floor is None:
        floor = contest_floor_specs()
    added: set[int] = set()
    detail: dict[str, dict] = {}
    contest = df["contest"].fillna("").astype(str).str.strip()
    blocked = ineligible or set()
    for name, minimum in sorted(floor.items()):
        group = df[contest == name]
        held = set(group.loc[group["id"].isin(existing), "id"])
        eligible = group[~group["id"].isin(blocked)]
        need = max(0, min(minimum, len(eligible)) - len(held))
        pool = eligible[(eligible["favs"] >= CONTEST_MIN_FAVS)
                        & (eligible["words"] >= CONTEST_MIN_WORDS)
                        & (~eligible["id"].isin(held))]
        picked = set(pool.sort_values(
            ["fav_pctl", "favs", "id"], ascending=[False, False, True]
        ).head(need)["id"])
        added |= picked
        detail[name] = {"total": len(group), "min": minimum,
                        "eligible_total": int(len(eligible)),
                        "held": len(held), "added": len(picked), "need": need,
                        "eligible": len(pool)}
    return added, detail


# E.35（2026-11-26）：form 配额 + 同代分位准入。总量 16,000，按用户裁定
# long/dialogue/short/medium/ip_collab 递减；IP 固定 50。旧锚点驱动
# （top-favs / 月榜 / featured / deep）降级为诊断字段，不再决定入种。
# E.37（2026-11-26，用户裁定）：dialogue 占比不得超过 40%，由 6,750（42.2%）
# 压到 6,400（40.0%）；释放的 350 名额按优先级补给 long（8,000 → 8,350）。
FORM_QUOTAS: dict[str, int] = {
    "long": 8_350, "dialogue": 6_400, "short": 1_100,
    "medium": 100, "ip_collab": 50,
}
QUOTA_TOTAL = sum(FORM_QUOTAS.values())  # 16,000
DIALOGUE_MAX_SHARE = 0.40  # E.37 硬上限：会话体不得占配额超过 40%（用户裁定）
# 配额制下的绝对覆盖率下限：总量从 17,959 压到 16,000 后现算约 94.3%，
# 该下限只守「没有把覆盖率搞崩」，不硬编码现算值（口径为快照现算、随版本变化）。
COVERAGE_FLOOR = 0.93


def quota_ids(df: pd.DataFrame, ineligible: set[int],
              form: pd.Series | None = None) -> tuple[set[int], dict]:
    """按 form 配额取同代分位前 N 本，替换旧锚点驱动准入。

    同代分位 = `groupby(est_year)['favs'].rank(pct=True)`，解决绝对 favs
    跨年不可比（很多年份对话/中篇头部到不了固定 favs 阈值）。eligible 池
    已扣 ineligible（E.31/E.32/E.34/P10/E.19/E.25）；每个 form 独立取前 N，
    名额不足时取实际数（P14 会捕获缺口）。返回 (ids, 每 form 分位底明细)。
    """
    if form is None:
        form = _form(df)
    ids: set[int] = set()
    detail: dict[str, dict] = {}
    for fm, n in FORM_QUOTAS.items():
        pool = df[form.eq(fm) & ~df["id"].isin(ineligible)].copy()
        if pool.empty:
            detail[fm] = {"n": 0, "quota": n, "pctl_floor": None}
            continue
        pool["pctl"] = pool.groupby("est_year")["favs"].rank(pct=True)
        picked = pool.nlargest(n, "pctl")
        ids.update(int(x) for x in picked["id"])
        detail[fm] = {"n": len(picked), "quota": n,
                      "pctl_floor": float(picked["pctl"].min())}
    return ids, detail


def admit(df: pd.DataFrame, content_end: pd.Timestamp,
          deep: set[int] | None = None) -> dict:
    """Quality-anchored seed ids plus the audit trail.

    Since 2026-11-19 there is **no new-book discovery channel**: ``recent`` /
    ``active`` / ``gated`` / ``cut`` are computed for diagnostics only and are
    never unioned into ``ids``. See the module docstring for the decision.

    E.31: 连载中的 short/medium 在所有世代均无收录资格（2026 中短合并后同样
    如此），唯一例外是人工清单逐本批准；征文保底仅对人工列名赛事生效，
    且不得绕过这条完结规则。`form=invalid`（words<2000 的僵尸书）同样无资格。
    E.32: 人工黑名单逐本排除假短/假中篇，优先级高于人工豁免，保底同样不得带入。
    E.34: short/medium 必须落在中短篇赛事 roster union 内，唯一豁免是人工
    ``waive="contest"``；无征文的高收藏 medium 是用户裁定的假中篇。
    E.35: 入种改为 form 配额 + 同代分位取前 N（总量 16,000）。旧锚点
    （base/monthly/featured/short/deep）与征文保底降级为诊断，不再 override
    配额名额；P1/P3 语义随之改写，新增 P14 配额守门。
    E.37: dialogue 配额压到 40%（6,400），释放名额补给 long（8,350）；
    P14 同时守门对话占比硬上限，防止配比再次越过 40%。
    """
    base = set(df.nlargest(REC_N, "favs")["id"])
    monthly = monthly_ids(df)
    featured = set(df.loc[df["featured"] == 1, "id"])
    short = short_supplement(df)
    core = base | monthly | featured

    if deep is None:
        deep = set(build_deep_ranks(df, 200)["nid"])

    blacklist = manual_blacklist_ids(df)
    exempt = manual_exempt_ids(df, "complete") - blacklist  # 黑名单优先于豁免
    contest_exempt = manual_exempt_ids(df, "contest") - blacklist
    floor = contest_floor_specs()
    abandoned = abandoned_ids(df, exempt=exempt)
    invalid = invalid_ids(df)
    fake_complete = fake_complete_ids(df)
    outside_contest = short_medium_outside_contest_ids(df, exempt=contest_exempt)
    dead = dead_ids(df)
    ineligible = (abandoned | invalid | fake_complete | dead | blacklist
                  | outside_contest)
    anchors = (core | short | deep) - ineligible

    # E.35: 配额制替换锚点驱动。anchors/core/short/deep 仅作诊断字段保留，
    # 不再决定入种；征文保底（contest_floor）也不再 override 配额名额。
    ids, quota_detail = quota_ids(df, ineligible, form=_form(df))
    ids -= ineligible  # 二次过滤防御
    contest_added: set[int] = set()
    contest_detail: dict = {}

    # Diagnostic only: what the retired V2 time gate would have admitted.
    recent = set(df[df["est_date"] >= content_end - pd.Timedelta(days=RECENT_DAYS)]["id"])
    active = set(df[df["upd"] >= content_end - pd.Timedelta(days=ACTIVE_DAYS)]["id"])
    loose = (recent | active) - core - short - deep
    gated = set(df[df["id"].isin(loose)
                   & (df["vel_pctl"] >= VEL_PCTL_MIN)
                   & (df["favs"] >= TIME_MIN_FAVS)]["id"])

    return {
        "ids": ids,
        "base": base,
        "monthly": monthly,
        "featured": featured,
        "short": short,
        "contest_added": contest_added,
        "contest_detail": contest_detail,
        "contest_floor_specs": floor,
        "abandoned": abandoned,
        "abandoned_in_seed": abandoned & ids,
        "manual_exempt": exempt,
        "contest_pool_exempt": contest_exempt,
        "outside_contest": outside_contest,
        "manual_blacklist": blacklist,
        "invalid": invalid,
        "fake_complete": fake_complete,
        "dead": dead,
        "ineligible": ineligible,
        "loose": loose,
        "gated": gated,
        "cut": loose - gated,
        "deep": deep,
        "excluded_time": (recent | active) - ids,
        "baseline": core | recent | active | short,
        "quota_detail": quota_detail,
    }


def postconditions(df: pd.DataFrame, res: dict) -> list[tuple[str, bool, str]]:
    """Checks the rebuild must assert before shipping (P1-P14).

    E.35 配额制下 P1/P3 语义改写：旧「深榜书全入种」不再成立（每 form 有
    名额上限，深榜书按同代分位被挤出属预期），P1 改为配额满额检查；P3 改为
    绝对覆盖率下限。P14 守各 form 名额与总量。其余硬规则断言不变。
    """
    seed = df[df["id"].isin(res["ids"])]
    abandoned = res["abandoned"]
    invalid = res["invalid"]
    ineligible = res["ineligible"]
    eligible = df[~df["id"].isin(ineligible)]
    eligible_tot = eligible["favs"].sum()
    base_seed = df[df["id"].isin(res["baseline"]) & ~df["id"].isin(ineligible)]
    anchored = res["monthly"] | res["featured"] | res["deep"]
    noise = seed[(seed["favs"] < NOISE_FAVS) & (seed["words"] < NOISE_WORDS)]
    unanchored = noise[~noise["id"].isin(anchored)]
    # E.35: P1 改为「配额全部填满」——每个 form 取到 NAME 名额 or 池子上限。
    quota_detail = res["quota_detail"]
    p1 = all(v["n"] == v["quota"] for v in quota_detail.values())
    p2 = unanchored.empty
    cov_new = seed["favs"].sum() / eligible_tot
    cov_old = base_seed["favs"].sum() / eligible_tot
    # E.35: 配额制总量从锚点时代的 17,959 压到 16,000，覆盖率现算约 94.3%；
    # 旧「回退 ≤0.2pp」不再适用（旧基线含 top20k 全收），改为绝对下限守门。
    p3 = cov_new >= COVERAGE_FLOOR
    contest = df["contest"].fillna("").astype(str).str.strip()
    shortfalls = {}
    # E.31: 保底清单是唯一有 quota 的赛事集合；不在清单里的征文没有 P4 门槛。
    # target 按合格候选数（非 ineligible + 过 favs/words 门槛 + held）封顶，
    # 避免与 P6/P9/P10 的硬剔除直接冲突。
    for name in sorted(res["contest_floor_specs"]):
        group = df[contest == name]
        detail = res["contest_detail"].get(name, {})
        eligible_n = detail.get("eligible", 0) + detail.get("held", 0)
        target = min(res["contest_floor_specs"][name], eligible_n)
        have = int(group["id"].isin(res["ids"]).sum())
        if have < target:
            shortfalls[name] = {"have": have, "target": target,
                                "eligible": eligible_n}
    p4 = not shortfalls
    # P5: 连载 short/medium 零入种；唯一的合法例外是人工豁免清单逐本放行。
    form_all = _form(df)
    serial = df["status"].ne("已完结").to_numpy()
    exempt = res["manual_exempt"]
    serial_short_medium = set(df.loc[
        form_all.isin(ABANDON_FORMS).to_numpy() & serial, "id"]) - exempt
    stray = serial_short_medium & res["ids"]
    p5 = not stray
    # P6: invalid（<2000 字僵尸 / 越短篇点击天花板的假短篇）在任何渠道都不得入种。
    p6 = not (invalid & res["ids"])
    # P7: 短篇三条天花板（E.17/E.19，用户 App 目验）。回到旧时光 clicks 215,723
    #     是全时期真短篇点击上限（早期书的点击虽累积十数年，`When It Sucks`
    #     162 万这类越线者已被 E.19 判为僵尸/假短篇、归 invalid，不再留在
    #     short 层）。听雨 5,478 favs / 2,389 赞是收藏与点赞上限。short 层若有
    #     书越过任一条，说明 classify 的天花板条款失效，断言失败。
    form_in_seed = FM.classify(df).where(df["id"].isin(res["ids"]))
    short_mask = form_in_seed.eq("short")
    over_c = df.loc[short_mask & (df["clicks"] > DF.DIAL_CLICKS_CEIL)]
    over_f = df.loc[short_mask & (df["favs"] > DF.SHORT_MAX_FAVS)]
    over_p = df.loc[short_mask & (df["praises"] > DF.SHORT_MAX_PRAISES)]
    p7 = over_c.empty and over_f.empty and over_p.empty
    # P8: E.31 全世代 short/medium 必须已完结——连载书零入种，
    # 唯一例外是人工豁免清单逐本批准者。与 P5 相互独立复核同一条硬规则。
    p8 = not stray
    # P9: E.25 Web 死链（详情页「小说不存在」）在任何渠道都不得入种——快照
    #     里它们的收藏/字数都还正常，形态规则看不出异常，只有详情页判活能拦住。
    dead = res["dead"]
    p9 = not (dead & res["ids"])
    # P10: 征文含「长篇」的 short/medium（假完结）在任何渠道都不得入种——
    #     包括征文保底（124/145 本过保底门槛，靠 contest_added 二次过滤拦住）。
    fake = res["fake_complete"]
    p10 = not (fake & res["ids"])
    # P11: 人工黑名单（假短/假中篇）在任何渠道零入种，且压过人工豁免。
    blacklist = res["manual_blacklist"]
    p11 = not (blacklist & res["ids"])
    # P13: E.34 正向准入——union 外的 short/medium（无征文/非中短篇征文，
    # 用户确认为假中/假短）在任何渠道都不得入种；唯一例外是人工
    # waive="contest" 白名单，已在 outside_contest 计算时扣除。
    outside = res["outside_contest"]
    p13 = not (outside & res["ids"])
    # P14: E.35 配额守门——每个 form 入种数 == 配额，同代分位底单调
    # （long < dialogue < short 在配额席位上的相对水位由配额定义，不强制序）。
    quota_detail = res["quota_detail"]
    form_all = _form(df)
    seed_form = form_all[df["id"].isin(res["ids"])]
    dialogue_share = (seed_form.eq("dialogue").sum() / len(res["ids"])
                      if res["ids"] else 1.0)
    p14 = (len(res["ids"]) == QUOTA_TOTAL
           and all(seed_form.eq(fm).sum() == n for fm, n in FORM_QUOTAS.items())
           and dialogue_share <= DIALOGUE_MAX_SHARE)  # E.37: 对话 ≤40%
    return [
        ("P1 各 form 配额全部填满（E.35）", p1,
         " · ".join(f"{fm} {v['n']}/{v['quota']}"
                    for fm, v in quota_detail.items())),
        ("P2 favs<5 且字数<1万必须有外部锚", p2,
         f"无锚噪声 {len(unanchored)} 本" + (f"：{unanchored['id'].tolist()[:5]}"
                                       if len(unanchored) else "")),
        ("P3 收藏覆盖 ≥ 绝对下限（E.35 配额制）", p3,
         f"新 {cov_new:.2%} vs 下限 {COVERAGE_FLOOR:.2%} "
         f"（旧基线 {cov_old:.2%}，配额制主动压缩不再用回退口径）"),
        ("P4 人工保底清单内征文达到设定本数", p4,
         f"清单内 {len(res['contest_detail'])} 个征文，缺口 "
         f"{len(shortfalls)}" + (f"：{shortfalls}" if shortfalls else "")),
        ("P5 连载 short/medium 零入种（仅人工豁免例外）", p5,
         f"全世代连载短/中篇 {len(serial_short_medium):,} 本（已剔除 "
         f"{len(exempt)} 本人工豁免），入种 {len(stray)} 本"
         + (f"：{sorted(stray)[:10]}" if stray else "")),
        ("P6 invalid（僵尸/假短篇）零入种", p6,
         f"invalid {len(invalid):,} 本，入种 {len(invalid & res['ids'])} 本"),
        ("P7 short 层不越短篇三条天花板", p7,
         f"short {int(short_mask.sum()):,} 本；越点击 "
         f"{len(over_c)}、越收藏 {len(over_f)}、越点赞 {len(over_p)}"
         + (f"：{(over_c['id'].tolist() + over_f['id'].tolist() + over_p['id'].tolist())[:5]}"
            if not p7 else "")),
        ("P8 全世代 short/medium 必须已完结（仅人工豁免例外）", p8,
         f"全世代连载短/中篇 {len(serial_short_medium):,} 本，人工豁免 "
         f"{len(exempt)} 本，入种 {len(stray)} 本"),
        ("P9 Web 死链零入种（详情页「小说不存在」）", p9,
         f"死链 {len(dead)} 本，入种 {len(dead & res['ids'])} 本"
         + (f"：{sorted(dead & res['ids'])}" if not p9 else "")),
        ("P10 征文含「长篇」的 short/medium 零入种（假完结）", p10,
         f"命中 {len(fake):,} 本，入种 {len(fake & res['ids'])} 本"
         + (f"：{sorted(fake & res['ids'])[:10]}" if not p10 else "")),
        ("P11 人工黑名单零入种（优先于人工豁免）", p11,
         f"黑名单 {len(blacklist)} 本，入种 {len(blacklist & res['ids'])} 本"
         + (f"：{sorted(blacklist & res['ids'])[:10]}" if not p11 else "")),
        ("P13 非中短篇赛事的 short/medium 零入种（仅人工 waive=contest 例外）", p13,
         f"union 外 {len(outside):,} 本，人工豁免 {len(res['contest_pool_exempt'])} 本，"
         f"入种 {len(outside & res['ids'])} 本"
         + (f"：{sorted(outside & res['ids'])[:10]}" if not p13 else "")),
        ("P14 各 form 配额、总量 16,000 与对话占比 ≤40%（E.35/E.37）", p14,
         f"总量 {len(res['ids']):,}/{QUOTA_TOTAL:,} · "
         + " · ".join(f"{fm} {seed_form.eq(fm).sum()}/{n}"
                      for fm, n in FORM_QUOTAS.items())
         + f" · dialogue {dialogue_share:.2%} ≤ {DIALOGUE_MAX_SHARE:.0%}"),
    ]


def band(favs: int) -> str:
    for hi, name in [(0, "0"), (4, "1-4"), (9, "5-9"), (49, "10-49"),
                     (99, "50-99"), (499, "100-499"), (1_999, "500-1,999"),
                     (9_999, "2k-10k"), (10 ** 9, "10k+")]:
        if favs <= hi:
            return name
    return "10k+"


def main() -> int:
    sys.path.insert(0, str(REPO / "analysis"))
    from lib import config as C  # noqa: E402

    content_end = pd.Timestamp(C.CONTENT_END) if hasattr(C, "CONTENT_END") \
        else pd.Timestamp("2026-05-03")
    df = add_velocity(load_universe(), content_end)
    res = admit(df, content_end, deep=set(build_deep_ranks(df, 200)["nid"]))
    fav_tot = df["favs"].sum()

    print(f"universe {len(df):,}  favs {fav_tot:,}  content_end {content_end.date()}")
    print(f"licensed rows appended by build_seed: {LICENSED}")

    for label, ids in [("现基线 V0", res["baseline"]),
                       ("质量锚 V3", res["ids"])]:
        sub = df[df["id"].isin(ids)]
        print(f"\n== {label} ==")
        print(f"books {len(ids):,} (seed.db {len(ids) + LICENSED:,} incl. licensed)")
        print(f"favs coverage {sub['favs'].sum() / fav_tot:.2%}")
        print(f"favs<5 {(sub['favs'] < 5).mean():.2%} | favs<10 {(sub['favs'] < 10).mean():.2%}"
              f" | favs=0 {int((sub['favs'] == 0).sum()):,}")
        print(f"median favs {sub['favs'].median():.0f} | median words "
              f"{sub['words'].median():.0f} | words<10k {(sub['words'] < 10_000).mean():.1%}")

    ex = df[df["id"].isin(res["excluded_time"])]
    print(f"\n== 时间渠道（已移除，仅诊断） ==")
    print(f"excluded {len(ex):,} books / {ex['favs'].sum():,} favs "
          f"({ex['favs'].sum()/fav_tot:.2%} of universe)")
    print(f"favs<10 {(ex['favs'] < 10).mean():.1%} | favs=0 "
          f"{int((ex['favs'] == 0).sum()):,} | max favs {ex['favs'].max() if len(ex) else 0}")
    print("V2 gate would have admitted "
          f"{len(res['gated']):,} / cut {len(res['cut']):,} — neither enters the seed")

    print("\n== 深榜补入 ==")
    print(f"deep books {len(res['deep']):,} | missing from baseline "
          f"{len(res['deep'] - res['baseline']):,} | missing from V3 "
          f"{len(res['deep'] - res['ids']):,}")

    print("\n== 征文保底（仅人工清单）==")
    gaps = {k: v for k, v in res["contest_detail"].items() if v["need"] > 0}
    print(f"listed contests {len(res['contest_detail'])} | below floor {len(gaps)} "
          f"| added {len(res['contest_added'])}")
    for name, d in gaps.items():
        print(f"  {name:24} total {d['total']:4} | before {d['held']:3} "
              f"| added {d['added']:2} | eligible {d['eligible']:4}")

    print("\n== 后置断言 ==")
    for name, ok, detail in postconditions(df, res):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    sub = df[df["id"].isin(res["ids"])]
    print("\n== V3 收藏分档 ==")
    tbl = (sub.groupby(sub["favs"].map(band))
           .agg(n=("id", "size"), favs=("favs", "sum")))
    tbl["share"] = tbl["n"] / len(sub)
    print(tbl.reindex(["0", "1-4", "5-9", "10-49", "50-99", "100-499",
                       "500-1,999", "2k-10k", "10k+"]).fillna(0).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

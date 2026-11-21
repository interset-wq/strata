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

Since 2026-11-19 a separate **contest floor** (E.9) keeps every named contest
— the six closed IP collabs and the other 90 competitions alike — represented
by at least three books. It is a diversity constraint, not a quality exception:
candidates must still clear `favs >= 5` and `words >= 10_000`, and are chosen by
same-generation `fav_pctl`.

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
CONTEST_MIN_PER = 3     # E.9: every named contest keeps >= 3 books (incl. IP collabs)
CONTEST_MIN_FAVS = 5    # floor for contest-floor candidates (no quality exception)
CONTEST_MIN_WORDS = 10_000  # same: avoid padding the seed with <1万-word noise
ABANDON_FORMS = ("short", "medium")  # E.11: 连载中的短/中篇 = 作者弃书，无收录资格
ABANDON_PCTL_EXEMPT = 0.98  # E.13: 同代 fav_pctl ≥ 0.98 的连载短/中篇 豁免弃书规则
GEN_MIN, GEN_MAX = 2007, 2025
LICENSED = 47           # appended by build_seed.py, outside the universe


def _form(df: pd.DataFrame) -> pd.Series:
    if "form" in df.columns:
        return df["form"]
    sys.path.insert(0, str(ANALYSIS))
    from lib import forms as FM  # noqa: E402
    return FM.classify(df)


def abandoned_ids(df: pd.DataFrame) -> set[int]:
    """E.11+13 弃书规则：连载中的 short/medium 不具收录资格（质量豁免见下）。

    理由是产品直觉——短/中篇是「一口气读完」的作品，连载中意味着作者
    没写完（弃书），比已完结劣质书更没有资格进种子。`form` 仍是纯篇幅
    标签、不随 status 变；本函数只在种子收录层生效。

    **E.13 质量豁免（2026-11-19，用户定，仅 short）**：同代 `fav_pctl ≥ 0.98`
    的连载短篇不算弃书——status 字段不可靠（24132「回到旧时光」同代前 0.85%
    的短篇，作者只是忘了点完结）。豁免不是直接入库：这些书仍须有质量锚
    （Top20k/月榜/banner/短篇补/深榜）才能进种子。

    **E.20（2026-11-19，用户定）：中篇无豁免**。`form=medium` 且连载中的书
    一律弃书，不看 fav_pctl——5–15 万字仍在连载的中篇，绝大多数是作者弃掉的
    长篇（字数还会涨、结构是长篇），给它们开口子等于让大量太监长篇进种子。
    中篇必须 `status=已完结` 才有收录资格，征文保底也不例外（P8 守门）。
    """
    form = _form(df)
    serial = df["status"].ne("已完结").to_numpy()
    is_short = form.eq("short").to_numpy()
    is_medium = form.eq("medium").to_numpy()
    low = df["fav_pctl"].lt(ABANDON_PCTL_EXEMPT).to_numpy()
    mask = (is_medium & serial) | (is_short & serial & low)
    return set(df.loc[mask, "id"])


def exempt_from_abandon(df: pd.DataFrame) -> set[int]:
    """E.13 豁免集：连载中的 **short** 且同代 fav_pctl ≥ 0.98。

    E.20 起中篇不再豁免——连载中篇一律弃书（见 `abandoned_ids`）。
    这些书不进 ineligible；若原本有质量锚则照常经锚入种（P3/P1 的合格
    分母包含它们）。
    """
    form = _form(df)
    mask = (form.eq("short").to_numpy()
            & df["status"].ne("已完结").to_numpy()
            & df["fav_pctl"].ge(ABANDON_PCTL_EXEMPT).to_numpy())
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
    """Analysis universe: licensed Japanese LN dropped, est_year 2007..2025."""
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


def contest_guarantee(df: pd.DataFrame, existing: set[int]) -> tuple[set[int], dict]:
    """E.9: every named contest keeps at least three seed books.

    Covers all contests (IP collabs included), not only the closed IP list.
    Adds only from `favs >= 5` and `words >= 10_000`, ranked by same-generation
    `fav_pctl` (ties: favs desc, id asc). Books already in the seed count even
    if they entered through another channel. Contests with fewer than three
    total books can only contribute however many exist.
    """
    added: set[int] = set()
    detail: dict[str, dict] = {}
    contest = df["contest"].fillna("").astype(str).str.strip()
    # E.20: a serialising medium book is never eligible, contest floor included.
    serial_medium = _form(df).eq("medium") & df["status"].ne("已完结")
    for name in sorted(contest[contest != ""].unique()):
        group = df[contest == name]
        held = set(group.loc[group["id"].isin(existing), "id"])
        need = max(0, min(CONTEST_MIN_PER, len(group)) - len(held))
        pool = group[(group["favs"] >= CONTEST_MIN_FAVS)
                     & (group["words"] >= CONTEST_MIN_WORDS)
                     & (~group["id"].isin(held))
                     & (~serial_medium.loc[group.index])]
        picked = set(pool.sort_values(
            ["fav_pctl", "favs", "id"], ascending=[False, False, True]
        ).head(need)["id"])
        added |= picked
        detail[name] = {"total": len(group), "held": len(held),
                        "added": len(picked), "need": need,
                        "eligible": len(pool)}
    return added, detail


def admit(df: pd.DataFrame, content_end: pd.Timestamp,
          deep: set[int] | None = None) -> dict:
    """Quality-anchored seed ids plus the audit trail.

    Since 2026-11-19 there is **no new-book discovery channel**: ``recent`` /
    ``active`` / ``gated`` / ``cut`` are computed for diagnostics only and are
    never unioned into ``ids``. See the module docstring for the decision.

    E.11+13: 连载中的 short/medium（弃书，short 同代 pctl≥0.98 豁免）从质量锚
    剔除；E.20 起中篇无任何豁免（连载中篇一律出局，保底也不例外）。
    征文保底（E.9）对 short 豁免该规则、仍从全池选书，以保住低完结率比赛的代表性。
    E.12: `form=invalid`（words<2000 的僵尸书）无收录资格，从质量锚剔除；
    征文保底候选 words>=1万、天然不碰 invalid，故保底也不带入。
    """
    base = set(df.nlargest(REC_N, "favs")["id"])
    monthly = monthly_ids(df)
    featured = set(df.loc[df["featured"] == 1, "id"])
    short = short_supplement(df)
    core = base | monthly | featured

    if deep is None:
        deep = set(build_deep_ranks(df, 200)["nid"])

    abandoned = abandoned_ids(df)
    invalid = invalid_ids(df)
    fake_complete = fake_complete_ids(df)
    dead = dead_ids(df)
    exempt = exempt_from_abandon(df)
    ineligible = abandoned | invalid | fake_complete | dead
    anchors = (core | short | deep) - ineligible

    ids = set(anchors)
    contest_added, contest_detail = contest_guarantee(df, ids)  # 豁免弃书：全池
    # 但不豁免 invalid/P10 假完结/死链（这三类 145 本里有 124 本过保底门槛，
    # 不二次过滤会被征文保底重新加回）。
    contest_added -= invalid | fake_complete | dead
    ids |= contest_added

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
        "abandoned": abandoned,
        "abandoned_in_seed": abandoned & ids,
        "abandon_exempt": exempt,
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
    }


def postconditions(df: pd.DataFrame, res: dict) -> list[tuple[str, bool, str]]:
    """Checks the rebuild must assert before shipping (P1-P10).

    P1/P3 use the **eligible** denominator (连载 short/medium + invalid excluded):
    those books voluntarily lost coverage under E.11/E.12, so counting them as a
    regression would make the assertion fail by design.
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
    p1 = (res["deep"] - ineligible) <= res["ids"]
    p2 = unanchored.empty
    cov_new = seed["favs"].sum() / eligible_tot
    cov_old = base_seed["favs"].sum() / eligible_tot
    # V0's time channels contributed ~0.2pp of coverage. Removing them is the
    # decision, not a regression, so P3 now bounds the *deliberate* loss.
    p3 = cov_new >= cov_old - COVERAGE_TOL
    contest = df["contest"].fillna("").astype(str).str.strip()
    named = contest != ""
    shortfalls = {}
    for name, group in df[named].groupby(contest[named]):
        target = min(CONTEST_MIN_PER, len(group))
        have = int(group["id"].isin(res["ids"]).sum())
        if have < target:
            shortfalls[name] = {"have": have, "target": target}
    p4 = not shortfalls
    # P5: 弃书只能通过征文保底豁免回到种子；其他渠道一律不得带入。
    stray = abandoned - res["contest_added"]
    p5 = not (stray & res["ids"])
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
    # P8: E.20 中篇必须已完结——连载中篇零入种，征文保底也不例外。
    form_all = FM.classify(df)
    serial_medium = set(df.loc[(form_all == "medium").to_numpy()
                               & df["status"].ne("已完结").to_numpy(), "id"])
    p8 = not (serial_medium & res["ids"])
    # P9: E.25 Web 死链（详情页「小说不存在」）在任何渠道都不得入种——快照
    #     里它们的收藏/字数都还正常，形态规则看不出异常，只有详情页判活能拦住。
    dead = res["dead"]
    p9 = not (dead & res["ids"])
    # P10: 征文含「长篇」的 short/medium（假完结）在任何渠道都不得入种——
    #     包括征文保底（124/145 本过保底门槛，靠 contest_added 二次过滤拦住）。
    fake = res["fake_complete"]
    p10 = not (fake & res["ids"])
    return [
        ("P1 合格深榜书全部在种子内", p1,
         f"{len(res['deep'] - ineligible):,} 本合格深榜书，"
         f"缺 {len((res['deep'] - ineligible) - res['ids'])}"),
        ("P2 favs<5 且字数<1万必须有外部锚", p2,
         f"无锚噪声 {len(unanchored)} 本" + (f"：{unanchored['id'].tolist()[:5]}"
                                       if len(unanchored) else "")),
        ("P3 收藏覆盖回退 ≤ 时间渠道放弃量（合格书口径）", p3,
         f"新 {cov_new:.2%} vs V0 {cov_old:.2%}，差 "
         f"{(cov_new - cov_old)*100:+.2f}pp（容差 {COVERAGE_TOL*100:.1f}pp）"),
        ("P4 每个征文至少 3 本", p4,
         f"{len(res['contest_detail'])} 个征文，缺口 "
         f"{len(shortfalls)}" + (f"：{shortfalls}" if shortfalls else "")),
        ("P5 弃书仅经征文保底豁免入种", p5,
         f"弃书 {len(abandoned):,} 本（另有同代 pctl≥{ABANDON_PCTL_EXEMPT} 豁免 "
         f"{len(res['abandon_exempt'])} 本经质量锚入种），种子内 "
         f"{len(res['abandoned_in_seed'])} 本（均须来自征文保底），"
         f"越界 {len(stray & res['ids'])} 本"),
        ("P6 invalid（僵尸/假短篇）零入种", p6,
         f"invalid {len(invalid):,} 本，入种 {len(invalid & res['ids'])} 本"),
        ("P7 short 层不越短篇三条天花板", p7,
         f"short {int(short_mask.sum()):,} 本；越点击 "
         f"{len(over_c)}、越收藏 {len(over_f)}、越点赞 {len(over_p)}"
         + (f"：{(over_c['id'].tolist() + over_f['id'].tolist() + over_p['id'].tolist())[:5]}"
            if not p7 else "")),
        ("P8 连载中篇零入种（中篇必须已完结）", p8,
         f"连载中篇 {len(serial_medium):,} 本，入种 "
         f"{len(serial_medium & res['ids'])} 本"),
        ("P9 Web 死链零入种（详情页「小说不存在」）", p9,
         f"死链 {len(dead)} 本，入种 {len(dead & res['ids'])} 本"
         + (f"：{sorted(dead & res['ids'])}" if not p9 else "")),
        ("P10 征文含「长篇」的 short/medium 零入种（假完结）", p10,
         f"命中 {len(fake):,} 本，入种 {len(fake & res['ids'])} 本"
         + (f"：{sorted(fake & res['ids'])[:10]}" if not p10 else "")),
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

    print(f"\n== 征文保底（每个 >= {CONTEST_MIN_PER} 本）==")
    gaps = {k: v for k, v in res["contest_detail"].items() if v["need"] > 0}
    print(f"named contests {len(res['contest_detail'])} | below floor {len(gaps)} "
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

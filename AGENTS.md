# AGENTS.md

Strata (书层): reproducible research on 20 years of SFACG (菠萝包轻小说) bibliographic data, plus the
product (`app/`: seed builder + Go engine + Flutter UI implemented). AGPL-3.0.
Windows + PowerShell environment.

## Read first (do not scan the whole repo)

- `docs/README.md` — **global definitions**: SFACG endpoint facts (`sfacg-endpoints.md` PC, `sfacg-app-api.md` App, `sfacg-live-ranks.md`), custom metric definitions (`metrics-definitions.md`), and novel `form` definitions (`form-definitions.md`). Authoritative for interfaces and our own metrics/definitions. Old paths in `analysis/references/` and `app/docs/` are one-line absolute-path pointers to `/docs/...`.
- `analysis/README.md` — data pipeline, 22 reports (19 baseline + 3 supplements), and the 12 caliber constraints. Authoritative for any number.
- `app/README.md` + `app/docs/01-12` — product design (Chinese). `01-tech-stack.md` and `02-data-model.md` are the binding ones.
- `archive/` is intentionally stale (old dataset, old `quarry/` pipeline). Never cite its numbers or APIs.

## Layout

| Path | Role |
| --- | --- |
| `docs/` | **Global definitions shared by analysis + app**: interface facts, custom metrics, novel `form`. Not reports, not product design. |
| `analysis/` | Python research. `lib/` shared code, `generators/` report producers, `pipeline/` data build, `fetchers/` live probes, `references/` evidence (global docs moved to `docs/`, one-line pointers remain). |
| `analysis/data/`, `analysis/out/` | Gitignored, rebuildable. Raw jsonl comes from `dataset.7z`; `novels.csv` is derived. Never edit or commit. |
| `app/docs/` | Product design docs, numbered 01-07. Keep in Chinese. |
| `app/tools/seedbuild/` | Seed builder: `schema.sql`, `build_seed.py`, `validate.py`. Writes `app/assets/`. |
| `app/assets/` | Generated `manifest.json` + `seed.db.gz` (bundled read-only seed). |
| `app/engine/` | Go engine: `cmd/engine`, `internal/{appshell,store,api,testseed}`; localhost HTTP API. |
| `temp/` | Gitignored local mirrors of reference projects: [sfacg_tools](https://github.com/light-nook-labs/sfacg_tools), [novly](https://github.com/light-nook-labs/novly), [go-music-dl](https://github.com/guohuiyuan/go-music-dl). Never import from or ship it; cite upstream repos in docs. |
| `.workbuddy/` | Gitignored session memory. Not a source of truth. |

## Commands (run from repo root unless noted)

Analysis (Python >= 3.11, `uv`):

```powershell
cd analysis
uv sync
uv run --extra archive python pipeline/prepare.py   # first run only: verify + unpack dataset.7z
uv run python pipeline/build_csv.py                 # jsonl -> out/novels.csv + out/manifest.json
uv run python generators/report_market.py           # one report
Get-ChildItem generators/report_*.py | ForEach-Object { uv run python $_.FullName }  # all 22
```

- Reports and figures are generated: edit `generators/report_*.py`, never `reports/*.md` or `figures/*.png`.
- All scripts derive paths from `lib/paths.py`. New scripts must use `paths.*`, not hand-built paths.

Seed build (run after `build_csv.py`; reuses analysis code, writes `app/assets/`):

```powershell
cd analysis
uv run python ../app/tools/seedbuild/build_seed.py   # rebuild seed.db.gz + manifest.json
```

Go engine (`app/engine/`):

```powershell
cd app/engine
$env:GOPROXY = "https://goproxy.cn,direct"   # proxy.golang.org is unreachable from this network
go test ./...
go run ./cmd/engine --data-dir ../../temp/engine-data
```

- The engine prints `STRATA_ADDR=http://127.0.0.1:PORT` and `STRATA_SEED=...` on startup.
- It must use a pure-Go SQLite driver (`modernc.org/sqlite` v1.62.0, which bundles SQLite 3.54.1); never `mattn/go-sqlite3` (cgo breaks iOS cross-compilation).

Flutter (`app/ui/`): build **debug** APKs by default for device testing (user preference,
2026-11-19). Release builds are only for final packaging.

```powershell
cd app/ui
flutter build apk --debug      # app-debug.apk: debuggable via adb/logcat/run-as
flutter analyze
flutter test
```

Python on Windows: always pass `encoding="utf-8"` when reading files (`sys.stdout` is not UTF-8). Use `uv run` so the analysis venv/deps are used. Do not use bash/WSL unless the user asks.

## Data facts that change code

- `analysis/out/novels.csv` is **245,887 rows and intentionally excludes 47 licensed Japanese light novels** (authors in `config.LICENSED_LN_AUTHORS`; includes the 108 E.14 monthly-rank supplements). Analysis must keep excluding them: reused nids corrupt dating and generation stats.
- The app seed must re-add those 47 as `is_licensed=1` with NULL percentiles; they are searchable/detail-visible but excluded from A-class rankings and statistics.
- **Seed recipe (V3, rebuilt 2026-11-19; E.24 current = E.23 + per-band classifiers (kept as triage, never as a verdict) and a full DOM audit of every seed book (supersedes E.23 counts))**: book source = `dataset/out/books.jsonl` v20260503.7 (248,338 books = 248,230 + 108 E.14 monthly-rank supplements; raw jsonl only for the analysis table). Stats universe is still `is_licensed=0`, `est_year in 2007..2025` (241,864 rows), percentiles computed there by `est_year`. Admission = `seed_policy.admit()`: favs Top-20k ∪ monthly-rank nids ∪ banner ∪ short dual-percentile Top-2000 ∪ every D2 deep-rank book, **minus ineligible** = E.11 abandon (serializing short/medium with same-generation `fav_pctl < 0.98` have no admission right; E.13 quality exemption rescues top serializing shorts like 24132 whose authors forgot to mark complete — they still need a quality anchor; contest floor exempt) ∪ E.12/E.19 invalid (`words<2000` zombies, or `words ≤ 5万 & clicks > 215,723` fake-shorts; no exemption). `form` is **six-valued** (`invalid/short/medium/long/dialogue/ip_collab`); E.13 dialogue-morph v2 uses composite engagement (clicks/word: 同人 ≥6, non-fan ≤5万字 ≥13, non-fan 5–15万字 ≥30, calibrated on n=193 App-API chapter ground truth, precision 0.92 / recall 0.85) because 2–5万字 dialogue novels were flooding `short` (421290 favs 7,881 > top prose short 听雨 5,478); morph estimates never rescue `invalid` (zombies have absurd clicks/word). **No new-book discovery channel** — the two time channels were retired 2026-11-19; `vel_pctl` is diagnostic only. E.14 folds in 108 monthly-rank books missing from the May snapshot (rank-listed ⇒ alive; counters are 2026-11 App-API values, `dataset/rank_missing.jsonl`); 87/108 admitted, 19 excluded as serializing short/medium, 2 born 2026 (outside gen cap). E.15 appends 177 dating anchors from that fetch (`anchors/nid_anchors.jsonl`, 104→281; LOO interp p90 10d→3d, mean 13.8d→5.1d; est_year flips affect only 759/245,887 books, universe size unchanged) and adds a favs≥5 noise floor to the short-supplement candidates — percentile still computed on the full pool (filtering first distorts group denominators wholesale). **E.17 (2026-11-19, user)**: `genre=同人` (or tags containing 同人) with `words ≤ 50,000` is always `dialogue` — the user inspected all 170 fan books in the seed's `short` layer and every one was a misclassification (the v2-a arm `同人 & ckw≥6` matched **0** seed books, i.e. it was dead weight). Short-form ceilings confirmed by App inspection and asserted in **P7**: `clicks ≤ 215,723` (回到旧时光), `favs ≤ 5,478` and `praises ≤ 2,389` (听雨). **E.18 (2026-11-19, user)**: dialogue only exists from `nid ≥ 83,818` (2017-07) — the archived monthly board rank=4 (dialogue monthly tickets) is empty for 2016-10…2017-06 and starts 2017-07 with the first 「五征对话小说」 entries, so every morph clause is gated on that nid and 1,709 early books fall back to their length class (回到旧时光 itself is 2012, `When It Sucks` 2010 with 1.63M accumulated clicks). Title-IP clause added: 米哈游 IP words in the title with `words ≤ 5万` → dialogue (1,745 shorts); it deliberately stops at 5万 because medium/long IP books have `ckw` 1.33/0.95 — ordinary prose fanfiction. **E.19 (2026-11-19, user)**: the click ceiling is now a *verdict*, not only a guard — a `words ≤ 5万` book with `clicks > 215,723` that is still `short` is `invalid`, because the user inspected all of them and each is either a zombie whose text was replaced with gibberish (`When It Sucks`, reading button intact) or a long novel falsely marked complete (its word count only covers the front). They are not `long`: no reliable word count exists to classify them, and `status` is worthless. P7 now asserts the ceilings for **all eras**; the shorts cross none — their maxima are the ceilings themselves. **E.20 (2026-11-19, user)**: `medium` must be complete — a serialising medium book is out regardless of `fav_pctl`, and the contest floor cannot rescue it either, because most 5–15万字 serialising mediums are abandoned long novels (the word count will keep growing). E.13's quality exemption now applies to `short` only; P8 asserts zero serialising mediums in the seed. **E.21 (2026-11-19, user)**: a contest mark without 对话/点鸭 is a 正文 submission — contests are entered by group and every dialogue group carries the keyword. In the 5–15万字 band such a book therefore keeps its length class: `ckw` is an estimate, the contest mark is deterministic evidence, and an estimate may not overrule it. Eight serialising fan books (五征/七征/九征长篇组, 玄幻征文, 冬季恋曲征文活动 — 伊卡洛斯在约战, 变身卡莲的小日常, 开局有识律力量的我来到崩坏 …) move dialogue→medium and then leave the seed under E.20. **E.22 (2026-11-19, user)**: the dialogue product line is now identified from the **PC detail-page DOM**, not from estimates — dialogue/interactive novels are not readable on the web, so `book.sfacg.com/Novel/{nid}/` renders only the product notice in `.chapter-info .chapter-content` (`全新的对话小说版本…只能在APP上观看` / `全新的沉浸式互动小说…`) while prose renders its opening paragraph. Truth table `analysis/anchors/web_dialogue.jsonl` (944 medium seed books → 363 dialogue / 558 prose / 22 empty / 1 delisted; `fetchers/probe_web_dialogue.py`). Two new rungs in `forms.classify`: 1.2 (DOM says prose → revoke the morph estimate; kills the 264982/40325 ckw 12 false positives) and 3.5 (DOM says dialogue → `dialogue`, overruling the E.21 contest-group veto on 3 books written in the dialogue editor but entered in prose groups). Product-line fact outranks both the contest group and clicks/word — 335 of the 363 DOM-dialogue books sit below the 同人 ckw threshold of 6 (median 2.71), and 4 沉浸式互动小说 (745405/746269/729181/758261) name their chapters 「第一章」, so a chapter-title heuristic missed them entirely. Self-consistency: all 363 DOM-dialogue books have `nid ≥ 83,818`, zero exceptions (E.18). Consequence: seed medium 944→**580**, dialogue 5,302→**5,666**, total unchanged; universe medium 26,163→**25,799**, dialogue 42,288→**42,652**. **E.23 (2026-11-19, user)**: the author dimension is a priors source, never a propagation rule, and the form label cannot be learned across length bands. Measured on 120 books sampled by layer and inspected page by page: among books by authors who *do* carry a dialogue-contest mark, only 28% of their `short`, 60% of their `medium` and 32% of their `long` are actually dialogue (baseline 7% for authors without the mark) — a 4–8x lift, but propagating it would mislabel 4,000+ prose books, exactly as 秋米拉 shows (7 books = long 3 / short 3 / dialogue 1). The rule's own `dialogue` verdicts are 93% correct, so its weakness is recall, not precision. Two classifiers were tried and rejected: 22 snapshot features score F1 0.960 inside the 918-book medium-only truth set (where the rule recalls **0**), but drop to 85% accuracy / one-third recall on the cross-band holdout with a 1.000 training AUROC; a title char-ngram model reaches the same 85% with single-character fragments as its top features and puts `原神` on the **prose** side, although in the long band 4/4 IP-titled books are dialogue. The feature flips direction between length bands because the truth set is 100% 5–15万字 and 100% complete, so no estimator transfers to the 81% of the universe that is `short`. Adopting DOM directly (1s/book, deterministic) beats any estimator. The 119 cross-band verdicts are kept as facts (`anchors/web_dialogue.jsonl` 921→**1,040**) and correct 35 labels; **7 serialising dialogue books** previously blocked by E.11/E.20 now enter, because a dialogue novel serialises by 话 and a serial is not an abandonment. Adds 47 licensed = **18,757 books** (was 30,878 / 26,348 / 18,477 / 17,335 / 18,105 / 18,124 / 18,125 / 18,231 / 18,877 / 18,870 / 18,758 / 18,750). **E.24 (2026-11-19, user)**: the user pushed back that a bigger crawl is poor value and asked whether a stronger classifier could do it, plus two intuitions — dialogue authors are nearly always dialogue authors, and miHoYo-style titles are usually dialogue. Both were measured rather than assumed. (1) **Author dimension, leave-one-out on 1,040 DOM truths**: 65 authors have >= 2 verified books; only **3 are mixed (5%)**, and predicting a book from that author's other verified books scores **97% precision / 96% recall**. The intuition is right — but only once one book has been *determined*; when the observation is a contest mark the same propagation gives 28–60% (E.23), because a mark means “entered a dialogue contest”, not “this work is dialogue”. Observation quality, not the author feature, was the limiting factor. (2) **Per-band classifiers, not cross-band**: E.23's failure was transfer across length bands; trained per band, `short` reaches AUC 0.988 / accuracy 0.952 and `medium` AUC 0.993 / accuracy 0.960, with **0.2% and 0.9% error inside the confident zone** (split at 0.1/0.9). The short-band model repairs both of the rule's big errors: 131/132 dialogue books sitting in `invalid` are recovered, and 61 false positives in the rule's `dialogue` stratum fall to 6. Implementation `analysis/lib/form_clf.py` + `analysis/probe_form_triage.py`. **It still must not write `books.form`**: it under-scores cold dialogue books, so a probabilistic label would put a popularity bias into the form distribution itself. Its role is triage (19.9万 short books → 28,800 to crawl instead of 199k = 12h) and population estimation. (3) **The rule recalls 0% in the short band**: of the seed's 801 shorts, **216 (27%) are dialogue and not one was caught** — their median `ckw` is 3.3, and fan / title-IP / contest marks are all 0%. That, not judgement difficulty, is why the review lists were unreadable. (4) **So every seed book was audited by DOM** (16,960 + 1,750 = 18,710 requests, 8 workers, ~25 min, zero failures): `dialogue` was 97.3% correct (144 prose), `long` 3.7% dialogue (428), `short` 27% dialogue, `medium` 38% dialogue. Truth 1,040 → **19,190** (6,470 dialogue / 12,720 prose). **Seed 18,757 → 18,663 → 18,656 after E.25** (18,609 + 47): the 144 false dialogues fall back to their length class and most are serialising, so E.11/E.20 removes them (net -94). Seed forms: `dialogue` **6,189**, `long` **11,172**, `short` **609**, `medium` 577, `ip_collab` 62 — **seed form now contains no estimates at all**. (5) **Universe error is now quantified** from a 600-book stratified random sample (200 per rule stratum): the rule's `dialogue` stratum is only **69.2%** right [62.4%, 75.2%], its `short` stratum contains 8.6% dialogue (11,464 missed), and its `invalid` stratum is **74.6% dialogue** (17,946 books wrongly written off as zombies). Weighted, the short band holds ≈ **58,700 dialogue books (29%)** — the rule is short by 17,510 — and the per-band classifier independently estimates 54,579, so the two chains agree within ±7%. Universe `dialogue` 43,277 is therefore a *rule verdict*; the true figure is ≈ **59,000**. Every form-grouped statistic must carry that caveat. `books` has 28 columns, `schema_version=3`, `seed_version=20260503.23`; non-licensed cover coverage **17,850/18,609 (95.9%)**; favourite coverage **96.63% on the eligible denominator** (E.17 turns 5,853 fan books from short to dialogue, which removes them from E.11 abandon and adds 0.87% of favourites to the denominator, so the absolute floor moved 97.0%→96.5%; the same-denominator P3 delta is -0.01pp) — nine postconditions P1–P9 all pass. Deep ranks unchanged (14,621 rows). Every named contest keeps >= 3 books (E.9, P4); abandon books only re-enter via contest floor (P5); invalid never enters (P6) — neither `words<2000` zombies nor E.19 fake-shorts; no seed `short` book crosses a short-form ceiling (P7); no serialising medium enters at all, contest floor included (P8). Rebuild: `cd analysis && uv run python ../app/tools/seedbuild/build_seed.py`; audit with `audit_seed.py` → `analysis/out/seed_v3_quality.md`; short-layer review CSV via `export_form_review.py --suspect-only`. **E.25 (2026-11-19, user)**: 7 books whose PC detail page says 「小说不存在」 were still in the seed (746895 小小娇美人 favs 9,933, 704626 你管这叫约会 5,315 …). The jsonl snapshot is a one-way cursor scan, so a book delisted after the crawl keeps a complete word count, favourite count and update timestamp — neither `classify` nor the quality anchors can see it, only per-book liveness can. All 18,710 DOM probes returned exactly these 7 error pages (1.5–1.6 KB, HTTP 200) and serial re-probes reproduced them at 2.5 s intervals, ruling out concurrency throttling. List pinned in `analysis/anchors/web_dead.jsonl` → `lib/web_dialogue.dead_nids()` → `seed_policy.dead_ids()`, folded into `ineligible` (the contest floor cannot rescue them) and guarded by **P9**. Seed **18,663 → 18,656** (18,609 + 47), P1–P9 all pass, favourite coverage 96.63% unchanged (22,103 favourites = 0.02% of the denominator); non-licensed forms `long` 11,178→11,172, `medium` 578→577. Same session, the user declined any further precision work: the 2-hour short/medium triage crawl (which would have taken universe coverage to 99.8%) is cancelled and the E.24 error bars stay attached to every form-grouped statistic; the title-IP list stays closed (提瓦特/英桀/泰拉/七国/升格者 were candidates) because seed books are 100% DOM-verified, so extra keywords would only move the universe estimate. History: `app/docs/09` appendix E (E.24 supersedes E.14–E.23 on counts).
- Percentiles are build-time only; never recompute them on device. `pr = praises/favs` with `favs < 10` set to NULL.
- Two physical DBs: bundled read-only `seed.db`, writable `user.db` in app data. Join only by `nid` (never rowid, which reseeds on every seed release).
- Cumulative metrics (`clicks`/`favs`/`praises`) are not comparable across generations; always rank by same-generation percentile.

## SFACG crawling: do not guess APIs

- Search accepts only `keyword`; `novelbytype` requires POST + `Referer`; invalid nids return HTTP 200 with Chinese negative copy; HTML search hard-caps at 30 results and silently rate-limits (HTTP 200 + "请输入关键字" + 0 results); liveness needs the three-state check, not status codes.
- The global rate limiter is a survival constraint, shared by search and detail fetches; foreground detail requests get priority and queue overflow is dropped.

## Product constraints (v1)

- Flutter UI + embedded Go engine via `dart:ffi`, localhost HTTP only. No server, login, cloud sync, full-library crawl, or FTS5.
- iOS is self-signed (not App Store), but ATS `NSAllowsLocalNetworking` is still required.
- iOS cannot be built or tested on this Windows machine (no Xcode); Android can.

## Conventions

- Product/design docs are Chinese; agent-facing docs (this file, build READMEs) are English.
- Do not use SDD/TDD workflows unless the user explicitly asks.
- Cite current generators/reports, never `archive/` or stale memory files. Keep numbers reproducible; recompute rather than copy.
- License is AGPL-3.0. Porting tooling from [go-music-dl](https://github.com/guohuiyuan/go-music-dl) is allowed with attribution; do not copy its music business code.
- Never commit raw data, derived CSVs, `*.db`, runtime `user.db`, `temp/`, or credentials. The bundled seed asset is generated by the seed builder.

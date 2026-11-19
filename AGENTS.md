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
- **Seed recipe (V3, rebuilt 2026-11-19; E.19 current = E.18 + short clicks ceiling as a verdict, supersedes E.13 counts)**: book source = `dataset/out/books.jsonl` v20260503.7 (248,338 books = 248,230 + 108 E.14 monthly-rank supplements; raw jsonl only for the analysis table). Stats universe is still `is_licensed=0`, `est_year in 2007..2025` (241,864 rows), percentiles computed there by `est_year`. Admission = `seed_policy.admit()`: favs Top-20k ∪ monthly-rank nids ∪ banner ∪ short dual-percentile Top-2000 ∪ every D2 deep-rank book, **minus ineligible** = E.11 abandon (serializing short/medium with same-generation `fav_pctl < 0.98` have no admission right; E.13 quality exemption rescues top serializing shorts like 24132 whose authors forgot to mark complete — they still need a quality anchor; contest floor exempt) ∪ E.12/E.19 invalid (`words<2000` zombies, or `words ≤ 5万 & clicks > 215,723` fake-shorts; no exemption). `form` is **six-valued** (`invalid/short/medium/long/dialogue/ip_collab`); E.13 dialogue-morph v2 uses composite engagement (clicks/word: 同人 ≥6, non-fan ≤5万字 ≥13, non-fan 5–15万字 ≥30, calibrated on n=193 App-API chapter ground truth, precision 0.92 / recall 0.85) because 2–5万字 dialogue novels were flooding `short` (421290 favs 7,881 > top prose short 听雨 5,478); morph estimates never rescue `invalid` (zombies have absurd clicks/word). **No new-book discovery channel** — the two time channels were retired 2026-11-19; `vel_pctl` is diagnostic only. E.14 folds in 108 monthly-rank books missing from the May snapshot (rank-listed ⇒ alive; counters are 2026-11 App-API values, `dataset/rank_missing.jsonl`); 87/108 admitted, 19 excluded as serializing short/medium, 2 born 2026 (outside gen cap). E.15 appends 177 dating anchors from that fetch (`anchors/nid_anchors.jsonl`, 104→281; LOO interp p90 10d→3d, mean 13.8d→5.1d; est_year flips affect only 759/245,887 books, universe size unchanged) and adds a favs≥5 noise floor to the short-supplement candidates — percentile still computed on the full pool (filtering first distorts group denominators wholesale). **E.17 (2026-11-19, user)**: `genre=同人` (or tags containing 同人) with `words ≤ 50,000` is always `dialogue` — the user inspected all 170 fan books in the seed's `short` layer and every one was a misclassification (the v2-a arm `同人 & ckw≥6` matched **0** seed books, i.e. it was dead weight). Short-form ceilings confirmed by App inspection and asserted in **P7**: `clicks ≤ 215,723` (回到旧时光), `favs ≤ 5,478` and `praises ≤ 2,389` (听雨). **E.18 (2026-11-19, user)**: dialogue only exists from `nid ≥ 83,818` (2017-07) — the archived monthly board rank=4 (dialogue monthly tickets) is empty for 2016-10…2017-06 and starts 2017-07 with the first 「五征对话小说」 entries, so every morph clause is gated on that nid and 1,709 early books fall back to their length class (回到旧时光 itself is 2012, `When It Sucks` 2010 with 1.63M accumulated clicks). Title-IP clause added: 米哈游 IP words in the title with `words ≤ 5万` → dialogue (1,745 shorts); it deliberately stops at 5万 because medium/long IP books have `ckw` 1.33/0.95 — ordinary prose fanfiction. **E.19 (2026-11-19, user)**: the click ceiling is now a *verdict*, not only a guard — a `words ≤ 5万` book with `clicks > 215,723` that is still `short` is `invalid`, because the user inspected all of them and each is either a zombie whose text was replaced with gibberish (`When It Sucks`, reading button intact) or a long novel falsely marked complete (its word count only covers the front). They are not `long`: no reliable word count exists to classify them, and `status` is worthless. P7 now asserts the ceilings for **all eras**; the 800 remaining shorts cross none — their maxima are the ceilings themselves. Adds 47 licensed = **18,870 books** (was 30,878 / 26,348 / 18,477 / 17,335 / 18,105 / 18,124 / 18,125 / 18,231 / 18,877). `books` has 28 columns, `schema_version=3`, `seed_version=20260503.17`; non-licensed cover coverage **18,042/18,823 (95.8%)**; favourite coverage **96.65% on the eligible denominator** (E.17 turns 5,853 fan books from short to dialogue, which removes them from E.11 abandon and adds 0.87% of favourites to the denominator, so the absolute floor moved 97.0%→96.5%; the same-denominator P3 delta is -0.01pp) — seven postconditions P1–P7 all pass. Deep ranks unchanged (14,621 rows). Every named contest keeps >= 3 books (E.9, P4); abandon books only re-enter via contest floor (P5); invalid never enters (P6) — neither `words<2000` zombies nor E.19 fake-shorts; no seed `short` book crosses a short-form ceiling (P7). Rebuild: `cd analysis && uv run python ../app/tools/seedbuild/build_seed.py`; audit with `audit_seed.py` → `analysis/out/seed_v3_quality.md`; short-layer review CSV via `export_form_review.py --suspect-only`. History: `app/docs/09` appendix E (E.19 supersedes E.14–E.18 on counts).
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

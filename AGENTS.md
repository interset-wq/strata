# AGENTS.md

Strata (书层): reproducible research on 20 years of SFACG (菠萝包轻小说) bibliographic data, plus the
product (`app/`: seed builder + Go engine + Flutter UI implemented). AGPL-3.0.
Windows + PowerShell environment.

## Read first (do not scan the whole repo)

- `docs/README.md` — **global definitions**: SFACG endpoint facts (`sfacg-endpoints.md` PC, `sfacg-app-api.md` App, `sfacg-live-ranks.md`), custom metric definitions (`metrics-definitions.md`), and novel `form` definitions (`form-definitions.md`). Authoritative for interfaces and our own metrics/definitions. Old paths in `analysis/references/` and `app/docs/` are one-line absolute-path pointers to `/docs/...`.
- `analysis/README.md` — data pipeline, 24 reports (19 baseline + 5 supplements/special), and the 12 caliber constraints. Authoritative for any number.
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
Get-ChildItem generators/report_*.py | ForEach-Object { uv run python $_.FullName }  # all 24
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
- Android cross-compile (FFI `.so`): CC must be the **target-prefixed** clang `D:/androidSDK/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android24-clang.cmd` — plain `clang(.exe)` lacks the target triple and breaks cgo.

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
- The app seed must re-add those 47 as `is_licensed=1` with NULL `pr`; they are searchable/detail-visible but excluded from A-class rankings and statistics.
- **Seed recipe (current = V3 + E.14–E.32; full history: `app/docs/09` appendix E)**: book source = `dataset/out/books.jsonl` (252,336 books; raw jsonl feeds the analysis table only). Stats universe = `is_licensed=0 × est_year 2007..gen_max` (gen_max currently 2026; 249,885 rows); universe percentiles are build-time only (admission, deep-ranks `pctl` column, quality verdicts) — never written to seed columns (E.30). Admission = `seed_policy.admit()`: favs Top-20k ∪ monthly-rank nids ∪ banner ∪ short dual-percentile Top-2000 ∪ every D2 deep-rank book, **minus ineligible** = abandoned serializing short/medium (E.31: every short/medium in the seed must be complete; manual exemption list) ∪ invalid (`words<2000` zombies or `words ≤ 5万 & clicks > 215,723` fake-shorts) ∪ web-dead (`analysis/anchors/web_dead.jsonl`, P9) ∪ manual blacklist (`analysis/anchors/seed_manual_blacklist.jsonl`, P11, outranks manual exemption); contest floor / quality exemption run on manual lists only (E.31, initially empty). No new-book discovery channel (E.8). `form` is **six-valued** (`invalid/short/medium/long/dialogue/ip_collab`) and seed `form` carries **no estimates** — verdict precedence: user verdict (`analysis/anchors/form_user_verified.jsonl`, level -1, E.27: **ask, don't guess**) > PC detail-page DOM (`analysis/anchors/web_dialogue.jsonl`, 3.5, E.22) > App `categoryId` (3.6, E.28) > deterministic clauses (E.17 fan ≤50k → dialogue; E.18 dialogue `nid ≥ 83,818` + miHoYo title-IP ≤50k; E.19 over-ceiling fake-short → invalid; E.21 prose-contest veto). **Any seed rebuild must sync BOTH artifacts** (`app/assets/` + `app/ui/assets/`, E.26). Current seed = `manifest.json` (schema **v9**, E.30: four universe percentile columns dropped, `pr` kept; P1–P11 gated at build time — do not pin book counts here, they move every rebuild). Rebuild: `cd analysis && uv run python ../app/tools/seedbuild/build_seed.py`; audit: `audit_seed.py` → `analysis/out/seed_v3_quality.md`.
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

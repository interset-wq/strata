# AGENTS.md

Strata (书层): reproducible research on 20 years of SFACG (菠萝包轻小说) bibliographic data, plus the
product (`app/`: seed builder + Go engine implemented; Flutter UI not started). AGPL-3.0.
Windows + PowerShell environment.

## Read first (do not scan the whole repo)

- `analysis/README.md` — data pipeline, 20 reports (19 baseline + 1 supplement), and the 12 caliber constraints. Authoritative for any number.
- `app/README.md` + `app/docs/01-07` — product design (Chinese). `01-tech-stack.md` and `02-data-model.md` are the binding ones.
- `analysis/references/sfacg-endpoints.md` — the only authoritative SFACG endpoint fact file. Read before any fetching work.
- `archive/` is intentionally stale (old dataset, old `quarry/` pipeline). Never cite its numbers or APIs.

## Layout

| Path | Role |
| --- | --- |
| `analysis/` | Python research. `lib/` shared code, `generators/` report producers, `pipeline/` data build, `fetchers/` live probes, `references/` evidence. |
| `analysis/data/`, `analysis/out/` | Gitignored, rebuildable. Raw jsonl comes from `dataset.7z`; `novels.csv` is derived. Never edit or commit. |
| `app/docs/` | Product design docs, numbered 01-07. Keep in Chinese. |
| `app/tools/seedbuild/` | Seed builder: `schema.sql`, `build_seed.py`, `validate.py`. Writes `app/assets/`. |
| `app/assets/` | Generated `manifest.json` + `seed.db.gz` (bundled read-only seed). |
| `app/engine/` | Go engine: `cmd/engine`, `internal/{appshell,store,api,testseed}`; localhost HTTP API. |
| `temp/` | Gitignored reference projects (`go-music-dl`, old prototypes). Never import from or ship it. |
| `.workbuddy/` | Gitignored session memory. Not a source of truth. |

## Commands (run from repo root unless noted)

Analysis (Python >= 3.11, `uv`):

```powershell
cd analysis
uv sync
uv run --extra archive python pipeline/prepare.py   # first run only: verify + unpack dataset.7z
uv run python pipeline/build_csv.py                 # jsonl -> out/novels.csv + out/manifest.json
uv run python generators/report_market.py           # one report
Get-ChildItem generators/report_*.py | ForEach-Object { uv run python $_.FullName }  # all 20
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

Python on Windows: always pass `encoding="utf-8"` when reading files (`sys.stdout` is not UTF-8). Use `uv run` so the analysis venv/deps are used. Do not use bash/WSL unless the user asks.

## Data facts that change code

- `analysis/out/novels.csv` is **245,779 rows and intentionally excludes 47 licensed Japanese light novels** (authors in `config.LICENSED_LN_AUTHORS`). Analysis must keep excluding them: reused nids corrupt dating and generation stats.
- The app seed must re-add those 47 as `is_licensed=1` with NULL percentiles; they are searchable/detail-visible but excluded from A-class rankings and statistics.
- Reproducible seed recipe: stats universe = `is_licensed=0` and `est_year in 2007..2025` (241,758 rows); percentiles are computed there, grouped by `est_year`. Seed pool = top 20k favs ∪ `est_date >= 2026-05-03 - 365d` ∪ `updated_at >= 2026-05-03 - 90d` ∪ archived monthly-rank nids ∪ banner = 29,433; short dual-percentile Top 2000 adds 1,398; plus 47 licensed = **30,878**. Use these exact relative cutoffs (report 18's one-day-later constants yield 29,396 and are not the canonical build).
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
- License is AGPL-3.0. Porting tooling from `temp/go-music-dl` is allowed with attribution; do not copy its music business code.
- Never commit raw data, derived CSVs, `*.db`, runtime `user.db`, `temp/`, or credentials. The bundled seed asset is generated by the seed builder.

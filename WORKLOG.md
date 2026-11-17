# Worklog — agent operation log

Shared, append-only log of agent work sessions, so other agents can pick up
where the last one left off. Append at the END of the file. English only.
Never delete or rewrite other agents' entries.

| Field | Meaning |
| --- | --- |
| Date | ISO date of the session |
| Agent | which agent/session did the work |
| Did | what was actually done (files touched, commands run) |
| Verified | evidence: test/build commands and their results |
| Next | what the next agent should pick up |

---

## 2026-11-17 — AtomCode (glm5.3-flash)

- **Did** (Phase 0 of the FFI-first plan, per `app/docs/` + AGENTS.md):
  - Inventoried existing uncommitted FFI refactor: `app/engine/internal/engine/engine.go`
    (new library entry `Start`/`StartPaths`/`StartWithFlags`, shared by CLI and FFI),
    `app/engine/cmd/ffi/main.go` (c-shared exports `strata_start`/`strata_stop`/`strata_free`),
    and the slimmed `app/engine/cmd/engine/main.go` (now delegates to `internal/engine`).
    These were NOT written this session; they were found in the working tree.
  - Updated `app/README.md`: removed "尚未开工" status, added engine layout section
    and pointer to the new contract doc (docs/08).
- **Verified**: inventory only; no tests run yet this session.
- **Next** (in progress at handoff):
  1. Write `app/docs/08-engine-api.md`: HTTP contract for the existing 5 endpoints
     (`/strata/healthz`, `/strata/meta`, `/strata/books/:nid`, `/strata/rankings/favs`,
     `/strata/rankings/short`) — response models, error codes
     (`invalid_argument|not_found|internal`), pagination (`limit` 1..200, default 50) —
     plus drafts for search / detail refresh / observations / watchlist.
  2. Run `go test ./...` in `app/engine` to verify the refactor (set
     `GOPROXY=https://goproxy.cn,direct`).
  3. Phase 1: `go build -buildmode=c-shared` Android arm64 `.so`; Flutter FFI spike
     with `/healthz` polling (200ms interval, 15s timeout); acceptance = APK shows
     `book_count=30878`.
- **Notes**:
  - Seed facts: 30,878 books total incl. 47 licensed (`is_licensed=1`, NULL percentiles).
  - Working tree also had prior changes; do not clean/restore them.
  - Per plan, Phase 0 + Phase 1 are the current scope; Phases 2-6 deferred.

---

## 2026-11-17 — AtomCode (glm5.3-flash), session 3 (Phase 2)

- **Did** (Phase 2 COMPLETE, verified on device):
  - `app/ui/lib/data/api/strata_api.dart` (new): typed HTTP client for the contract —
    `healthz`/`meta`/`books/:nid`/`rankings/favs`/`rankings/short`, unified
    `StrataApiException` (status + code + message).
  - `app/ui/lib/core/providers.dart` (new): `bootProvider` (FutureProvider: extract
    bundled assets → FFI start → healthz poll → ready `StrataApi`; failure carries the
    diagnostic message; `ref.invalidate` = retry, no loop) and `metaProvider`.
  - `app/ui/lib/app/` (new): go_router (`/boot`, `/home`) + M3 theme (light/dark).
  - `app/ui/lib/pages/` (new): BootPage (progress/failure+retry, routes to /home on ok),
    HomePage (renders /strata/meta). `main.dart` now ProviderScope + MaterialApp.router.
  - Deps: flutter_riverpod 3.5.0, go_router 18.1.4.
- **Verified**: `flutter analyze` clean; debug APK on device shows
  `/strata/meta` data (seed 20260503.1, book_count=30878, licensed_count=47,
  tags 105/111828). Screenshot: `temp/ffi-build/phase2_home.png`.
- **Next** (Phase 3, reader MVP): Go store/API for 分位榜/题材榜/短篇榜/新书榜/详情/L1
  search if missing; Flutter ranking list + book detail + local search pages; keep
  `is_licensed=1` excluded from percentile rankings.
- **Notes**: commits 6aba8ac (docs), 72bb027 (engine), 21696f4 (ui spike),
  85d4b3d (ui shell). Nothing pushed.

---

## 2026-11-17 — AtomCode (glm5.3-flash), session 4 (Phase 3)

- **Did** (Phase 3 COMPLETE, verified on device):
  - Go: `GET /strata/search?q=` (L1 local LIKE search over seed, licensed included)
    and `GET /strata/rankings/new` (est_year >= gen_max-1 by fav_pctl, licensed
    excluded) in `internal/store` + `internal/api`; testseed gained a 2025-gen book
    (book_count 5→6 in fixtures); docs/08 contract updated to "已实现".
  - `cmd/ffi/main.go`: `strata_start` is now IDEMPOTENT — activity recreation without
    process death returns the live engine info instead of "engine already running"
    (bug found during device acceptance).
  - Flutter: RankingsPage (4 tabs: 分位榜 year selector / 题材榜 year+genre /
    短篇榜 / 新书榜), SearchPage, BookDetailPage; home page got leaderboard/search
    entries; Dart models gained `rank` + `SearchItem`.
- **Verified**: `go test ./...` all ok; `flutter analyze` clean; device acceptance:
  rankings tabs render (same-generation pctl ordering), detail page shows seed +
  effective values + licensed badge, search "JK" returns favs-ordered results.
  Screenshots: `temp/ffi-build/phase3_*.png`.
- **Next** (Phase 4 per plan): rate limiter, mobile detail fetch, three-state check,
  parser golden tests, observations write-back, official search L2, shelf + retention.
  BUT another agent is evaluating a higher-quality external API and may rewrite
  `analysis/references/sfacg-app-api.md`, docs/05 and related design — coordinate
  before starting Phase 4 crawler work; do not duplicate API research.
- **Notes**: commits 0bf141f (engine), 059f1af (ui). The other agent's uncommitted
  doc edits (sfacg-app-api.md, 05-detail-fetch.md) were left untouched.


---

## 2026-11-17 — AtomCode (glm5.3-flash), session 2

- **Did** (Phase 0 + Phase 1 COMPLETE, FFI spike validated on a real device):
  - `app/docs/08-engine-api.md` (new): binding Go↔Dart HTTP contract — the 5 live
    endpoints with exact response shapes/error codes/limit rules, plus drafts for
    L1 search, POST refresh, observations, shelf/watchlist, and the FFI start/stop
    JSON contract. Change endpoints via this doc first.
  - `app/README.md`: engine status updated (no longer "尚未开工"), engine layout section added.
  - `app/engine/internal/engine/engine_test.go` (new): library-entry test —
    `Start` serves `/healthz` on a dynamic loopback port, clean `Shutdown`, empty-path rejection.
  - `app/ui/` (new Flutter project, Android only): `lib/core/ffi/engine_ffi.dart`
    (dart:ffi bindings for `strata_start`/`strata_stop`/`strata_free`, healthz polling
    200ms interval / 15s timeout), `lib/main.dart` (boot page: running → ok/failure
    with diagnostics + retry, extracts bundled seed assets to files before Start).
  - Build chain that works on this machine: NDK `D:/androidSDK/ndk/28.2.13676358`,
    `GOOS=android GOARCH=arm64 CGO_ENABLED=1 CC=<ndk>/aarch64-linux-android24-clang.cmd
    go build -buildmode=c-shared` → `temp/ffi-build/libstrata.so` (25.9MB) → copied to
    `app/ui/android/app/src/main/jniLibs/arm64-v8a/`; seed assets copied to `app/ui/assets/`
    and bundled in APK.
- **Verified**:
  - `go test ./...` in `app/engine`: all ok (incl. new internal/engine test).
  - `flutter analyze`: no issues.
  - Device acceptance (USB device ADAD6R2805004487): `flutter build apk --debug
    --target-platform android-arm64` installed and launched; screen shows
    `engine ok @ http://127.0.0.1:45851, seed_version=20260503.1, book_count=30878`.
    Screenshot: `temp/ffi-build/acceptance.png` (temp/, not committed).
- **Next** (Phase 2 per plan): Flutter shell — `lib/core/ffi` (exists, move to final shape),
  `lib/data/api` client, Riverpod, go_router, startup-failure/retry page hardening,
  theme; main UI calls `/strata/meta`. iOS verification deferred (no Mac).
- **Notes**:
  - pub.dev here resolves `ffi: ^2.2.0` (2.3.0 unavailable in this network/mirror).
  - `test/widget_test.dart` was reduced to a placeholder (default test referenced MyApp).
  - Nothing committed yet; all changes are in the working tree.


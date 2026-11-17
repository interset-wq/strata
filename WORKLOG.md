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
---

## 2026-11-17 — AtomCode (glm5.3-flash), session 4 (Phase 3)

- **Next** (Phase 3, reader MVP): Go store/API for 分位榜/题材榜/短篇榜/新书榜/详情/L1
  search if missing; Flutter ranking list + book detail + local search pages; keep
  `is_licensed=1` excluded from percentile rankings.
- **Notes**: commits 6aba8ac (docs), 72bb027 (engine), 21696f4 (ui spike),
  85d4b3d (ui shell). Nothing pushed.

---

## 2026-11-17 — AtomCode (glm5.3-flash), session 5 (Phase 4)

- **Did** (Phase 4 core COMPLETE, verified on device):
  - `internal/crawl` (new): global limiter (foreground priority, queue-overflow
    dropped), mobile detail fetcher, pure three-state parser (dead/zombie/alive
    per docs/05 §4.3) with golden test on `temp/_page_48704.html` (skip if absent).
  - API (new endpoints): POST `/books/:nid/refresh` (synchronous, classified
    verdict, alive → observation appended), GET `/books/:nid/observations`,
    shelf GET/PUT/DELETE. Contract docs/08 updated to "已实现".
  - `cmd/ffi`: `GODEBUG=netdns=cgo` at init (Go pure resolver can't read
    /etc/resolv.conf on Android → DNS hang); HostsDialer pins verified SFACG IPs
    (device DNS poisoned: wrong IP answered TLS). DoH dialer kept in crawl/ as
    an alternative but not wired.
  - Flutter: detail page refresh button with verdict message, observation
    history, shelf add/remove, effective-value display (local observation
    overrides seed).
- **Verified**: go test all ok; flutter analyze clean; device: refresh wrote
  observations (favs/praises/words updated, source=local), seed.db sha256
  unchanged across refreshes (0aab13e3…), user.db grew. Note: the phone had NO
  internet during first attempts — 3 "failures" were environmental.
- **Next** (Phase 4 leftovers → Phase 5): watchlist + subscription-style
  background fetch, update heatmap/six-metric charts, retention cleanup (180d),
  official search L2 — pending the other agent's experimental App API results.
- **Notes**: commits 7869fdf (engine), 7c78d46 (ui). soundisle reference clone
  in temp/soundisle (uses gomobile AAR + plain Go net; no DNS workaround needed
  on their network — our netdns=cgo + HostsDialer stays). Another agent owns
  API-doc rewrites: sfacg-app-api.md, 05, 07 were left untouched by us.

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

---

## 2026-11-17 — WorkBuddy (session handoff, offline validation only)

- **Did**: Located the previous agent's interrupted background job: `analysis/fetchers/fetch_app_api_novels.py --all --delay 0.6`,
  whose output `analysis/out/app_api_novels.jsonl` stopped at 18:05 when that session ended. Briefly resumed it, then
  STOPPED all crawling on user instruction and reverted the temporary script edits (`--start-page`, flushed prints);
  the fetcher is back to its committed state. No network requests from this point on.
- **Validated (offline, no requests)**: Used the complete magic-category enumeration (tid=21, 88,528 books) to test
  report 10's "U-shaped in-register density" claim *within one category*, with the report's own nid bands.
  Within nid 2,657–774,850 there are 85,852 catalog books; 85,537 (99.6%) are in `out/novels.csv`.
  Band-wise in-register rates are 98.8–99.9% — **no U shape**; the lowest band is 650–774k (196 out-of-library books),
  all other bands have 9–33. Interpretation: the report's U shape describes nid-slot occupancy (denominator includes
  never-existing ids), not crawl completeness inside the live catalog. Consistent with report 10's revised conclusion
  that the real re-crawl target is ~1k books, not 111k.
- **Verified**: offline Python only; 111,331 unique nids in the enumeration file, zero duplicates.
- **Next**: validate other report 10 inferences from existing data only (e.g. missing-books skew toward short/recent,
  month-rank books not systematically delisted). Do NOT resume enumeration or hit external sites without explicit approval.
- **Notes**: `app_api_coverage.json` (17:36: 43,901 / 262 true missing) is stale because it used a partial enumeration;
  do not cite it as final.


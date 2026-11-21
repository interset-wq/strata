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

---

## 2026-11-17 — WorkBuddy (report 20, supplement only)

- **Did**: Created `analysis/generators/report_20_app_api_crosscheck.py` → `analysis/reports/20_app_api_crosscheck.md`
  plus two figures. Added `APP_API_NOVELS` / `EXTERNAL_DATES` path constants to `analysis/lib/paths.py`.
  Updated report counts in root README, `analysis/README.md`, AGENTS.md and project memory to
  19 baseline + 1 supplement / 84 figures.
- **Hard constraint honored**: report 10 (`10_survival.md`), `lib/eras.py` and every `app/docs/*` file were NOT touched.
  Report 20 is explicitly a supplement: no new coverage number, no change to the U/inverted-U conclusion,
  no App field emitted, and no network requests at generation time (missing inputs cause a hard error).
- **Verified**: generator runs clean; slot occupancy 44.3→24.0→40.1% (U shape confirmed with report 10's own bands),
  in-catalog hit rate 98.79–99.88% (flat, 99.63% overall), 315/85,852 pre-bound out-of-library books in tid=21,
  external addTime cross-check n=31,229, median 2 d, P99 10 d, max 11 d, 100% ≤30 d.
- **Next**: none required. If more validation is wanted, keep it offline under report 20 or a new supplement;
  do not edit report 10 or the dating model.

---

## 2026-11-17 — AtomCode (glm5.3-flash), session 6 (Phase 4 wrap-up)

- **Did**: observation retention prune at startup (180d, docs 02 §3.1); refresh
  debounce (same nid <60s replays verdict with cached:true); shelf page
  (/shelf route + home entry + shelfList in Dart client); contract docs/08
  updated with both semantics.
- **Verified**: go test + flutter analyze clean; device: shelf list shows
  favorited book (731325 神女大人…), second refresh returns cached:true,
  prune ran at startup without touching recent observations.
- **Pitfall**: testseed nid 1005 is NOT in the real bundled seed — "book not
  in seed" on device; use a real ranking nid for device-side shelf/refresh
  checks. Also: UI favorite taps kept missing — verify shelf via adb forward
  + curl against the engine port (find it via /proc/net/tcp on device).
- **Next**: experimental App API pipeline (JSON parse + own three-state,
  default off, fallback to HTML baseline) or Phase 5 watchlist/background
  fetch. Push still pending user approval.

---

## 2026-11-17 — D2 implementation (full-universe generation Top200)

- **Did**: user chose D2 over D1. Added `app/tools/seedbuild/deep_ranks.py` (shared, full-universe
  generation Top200 for favs/clicks/praises/pr), `analysis/generators/report_21_deep_ranks.py`
  → `reports/21_deep_ranks.md` + 2 figures. Extended seed schema to v2 with an additive
  `deep_ranks` table, rebuilt `app/assets/seed.db.gz` / `manifest.json`, and added
  `GET /strata/rankings/deep` with store method, testseed fixture and Go tests.
  Documented in `app/docs/10-deep-ranks.md`; 09 proposal appendix B records execution.
- **Verified**: 241,758-row universe → 76 boards / 14,626 rows; seed pool covers only
  7,534/14,626 (51.5%), 2007 generation 7/76 — proving `limit=200` on the seed-pool
  endpoint was not a deep board. `books` unchanged at 30,878 / 24 columns; gz 6.67 → 7.45 MB.
  `go test ./...` all green; real-asset query returns depth 200 (2010 favs) and 32 (2007 pr).
- **Hard constraint honored**: report 10, `lib/eras.py`, and app docs 01–08 untouched;
  no network requests; 4,553 deep-rank books were NOT merged into the seed book list.
- **Next**: D1 (near-30-day new-book Top200) remains unstarted and needs the enumeration gap closed;
  depth 500 rejected for now (new-book top200 threshold only 8 favs).

---

## 2026-11-17 — Cover refresh proposal (offline planning only)

- **Did**: user paused front-end deep-board integration (UI still being designed) and asked to plan a
  high-quality-seed crawler for covers. Added `app/docs/11-cover-refresh-proposal.md` (proposal, not
  executed). All figures recomputed offline from novels.csv / seed.db.gz / raw jsonl / local App sample.
- **Key finding**: seed pool 30,831 non-licensed books, 18,724 (60.7%) have empty `cover_url`, BUT
  16,976 (90.7%) of those had a real URL in raw jsonl that `dedup_covers` nulled as a known
  novel_hub selector bug (same cover on many books; owner match 89.8% vs non-owner 19.5%). Those URLs
  are WRONG and cannot be backfilled. Only 1,748 are true default placeholders. So the real target is
  16,976 books, not 18,724 and not the 131,814 empty in the full universe.
- **App API**: `novelCover` full https URL present in 114,381/114,381 local samples. 6,457 of the
  16,976 are already in the local sample (zero requests); 10,519 need fetching.
- **Cost**: plan A (store URL only) = 10,519 detail requests (~88 min @0.5s); list deep-scan = 5,108
  pages (not worth it). Downloading images = 829 MB for 16,976 / 1.4 GB for all seeds — infeasible.
  Recommended: additive `covers` table, URL only, default-image fallback for the 1,748.
- **Blockers for execution**: UI currently renders NO covers at all (no Image.network in app/ui/lib),
  so "seed must have covers" is a data-quality goal, not a UI blocker. 5 decision points listed in §5;
  suggested first step is a 30-book validation of URL correctness before any full crawl.
- **Hard constraint**: no requests made; report 10, eras.py, app docs 01–10 untouched. Front-end
  deep-board work remains paused; engine `in_seed` change (store/api/test) is done and go tests green.
---

## 2026-11-17 — AtomCode (glm5.3-flash), session 7 (UI design system)

- **Did**: app-wide UI design per user review round-trips (mockups at
  temp/ui-design/mockups.html, v5): "文房纸墨" dual theme (paper #F6F2E9 /
  night #181511, cinnabar accent, serif display), bottom NavigationBar with
  4 top-level tabs, home rebuilt as a book-finding surface (featured banner
  carousel with novly-style 1.45x offset for 4.47:1 images, entry grid,
  genre chips, continue-browsing from shelf), detail page data-dense
  (metric grid, percentile bars, PR badge, full metadata).
- **User decisions**: no seed-stats exposure on home (find-books app, not a
  database dashboard); no fabricated "hot this week" — seed is static, only
  honest sources (editor picks / local footprint / random); tab count 4 with
  novly-style entry-grid distribution for secondary pages; detail page
  maximizes data display; intro text comes from mobile HTML
  (.book_bk_qs1) — parser support still TODO.
- **Verified**: go test + flutter analyze clean; device screenshots
  (home carousel live images, rankings, shelf, detail) all good; commits
  1add3da (engine featured endpoint) + 0a22fb4 (ui landing).
- **Next**: rankings/search/shelf pages only re-themed, still need layout
  polish; detail intro section awaits engine parser support; author
  workbench (Phase 5) untouched. Push still pending user approval.

---

## 2026-11-18 - Detail refresh uses every returned field

- **Did**: completed the detail-refresh gap. `crawl.Detail` now parses title,
  author, genre, price type, cover, summary, favs, praises, words, status and
  updated_at from the single mobile HTML response. `AppNovel` now carries all
  20 App API fields (authorId/typeId/categoryId/isSensitive/allowDown/etc.).
  Added `user.db.book_meta` (schema v3) as the writable metadata overlay, and
  unified `bookRefresh` + `watcher.pollOne` on `writeHTML`/`writeApp`.
  `GET /strata/books/:nid` now returns `meta`, an enriched `effective` map,
  and a local cover fallback; the Flutter detail page renders the local cover,
  overlays title/author/status/genre, and shows summary/add_time/point/category.
- **Verified**: `go test ./...` green (new parser and write-path tests),
  `flutter analyze` + `flutter test` clean, fixture `temp/_page_48704.html`
  now actually runs instead of skipping (fixed relative path). Rebuilt
  `libstrata.so` with NDK 28.2 and release APK; APK contains the new
  25,441,576-byte `.so`, `assets/seed.db.gz`, and INTERNET permission.
- **Note**: seed remains read-only; observed values continue to live in
  `observations`, while all book attributes live in `book_meta`. App API still
  has no praises/summary and HTML still has no clicks, so each pathway keeps
  the other's previous values instead of overwriting them with NULL.

---

## 2026-11-19 - Classic mode completion (data-only path)

- **Did**:
  - Engine: added `Store.ClassicBooks` and `GET /strata/rankings/classic`
    (absolute `favs DESC, nid ASC`, optional genre/status/contest/form).
    Added `form` to `RankItem`, `BoardBooks`, `Discover`, `RandomBooks`, and
    the shared scan; added `parseForm` validation
    (`short|medium|long|dialogue|ip_collab`).
  - Random pools now honour `form`; the `browse` mega-book gate applies only
    to the default long-form tab so short/medium/dialogue/IP tabs are not
    empty.
  - Flutter: `rankingClassic` API; browse page uses absolute favs (no year or
    percentile); home form tabs now drive all three random showcases; browse
    card shows cumulative clicks instead of `fav_pctl`; removed disabled
    quant placeholder tabs and stale `30,878` / `12,107` copy.
  - Docs: updated `08` with `/rankings/classic`, `form`, and new seed counts;
    `03`/`04` counts; `12` endpoint/column/count references.
- **Verified**:
  - `go test ./...` in `app/engine`: all packages pass (new classic/form tests).
  - `flutter analyze` and `flutter test`: clean/pass.
  - Smoke-tested real seed `20260503.4`: healthz reports schema 3, 26,339 books;
    classic returns 155640 / 48704 / 666497 in favs order; serial+short form
    returns short books.
  - Rebuilt `libstrata.so` (36,407,864 bytes, NDK 28.2) and release APK
    (84.0 MB) with the new seed asset.
- **Next**: device smoke test the new APK (debug build for tap debugging), then
  verify home form tabs, browse absolute favs, and detail percentile display.

---

## 2026-11-19 - E.14: fold 108 monthly-rank missing books into dataset and seed

- **Did**: fetched App-API metadata for the 193 rank-listed books absent from
  the library (report 10 group A; e.g. 5976 S.M.S-舍子花, 2009-06-02, 23,306
  favs, best rank 2). 182 fetched, 11 deleted (404). Calibre: addTime ≤
  2026-05-03 bound (74 post-bound births and 11 dead excluded) → 108 books in
  `dataset/rank_missing.jsonl` (15-field schema + addTime/authorId/rank provenance);
  counters are 2026-11 App-API values (observed_at per book; excluded from
  dataset content_upper_bound); praises scraped from mobile HTML (App API lacks
  the field), favs cross-checked mobile-vs-API (0 mismatches >5%).
- **Pipelines**: dataset v20260503.7 (248,338 books); analysis corpus via
  `build_csv.py` supplement merge (novels.csv 245,887 rows; cover paths
  normalised relative); seed v20260503.12 = 18,077 + 47 = 18,124. Universe
  241,758 → 241,864. 87/108 admitted via monthly anchor; 19 excluded as
  serializing short/medium (E.11), 2 born 2026 outside the gen cap; P1-P6 all
  PASS, coverage 97.05% (eligible), non-licensed covers 17,265/18,077 (95.5%).
  New fetchers: `fetch_rank_missing.py`, `build_rank_missing_supplement.py`.
- **Verified**: `build.py` assertions pass; `validate.py` seed checks pass;
  `audit_seed.py` rebuilt against the new denominator (`seed_v3_quality.md`);
  seed.db.gz synced to `app/ui/assets/`.
- **Note**: 2026-born rankers (772261 凤傲天后悔 13,030 favs) remain outside the
  stats universe by the est_year ≤ 2025 cap — a pre-existing calibre decision,
  revisit only if the gen cap itself changes.

---

## 2026-11-20 - Medium tab portal + fixed carousel

- **Did**: replaced the medium home tab's chips + infinite `BookRowTile` list
  with a fixed featured carousel + 2×3 entry grid (总榜/年份/比赛/题材/优质/随机).
  Added `/medium-random` (`status=short&form=medium`); `RandomPoolPage`
  now accepts an optional form. Home carousel is per form: medium/IP use a fixed
  favs-order featured pool, short falls back to the IP pool, long/dialogue keep
  the date-seeded shuffle. `/featured` and `/banner` accept `form`.
  Updated docs/15, docs/16, and the Flutter carousel tests.
- **Verified**: `go test ./...`, `flutter analyze`, `flutter test` pass;
  debug APK built and installed; device smoke saw the 3-book fixed medium
  carousel, 中篇总榜 and 随机中篇 routes, and the short tab's IP fallback.
- **Next**: user acceptance on the device. Do not drive the phone via adb
  unless the user explicitly asks; the user will operate it.

---

## 2026-11-20 - Dialogue tab length-aware portal

- **Did**: replaced the dialogue tab's genre chips + infinite list with a
  cover-composed carousel + 3x3 entry grid. The grid puts length bands first
  (short <=50k, medium 50k-150k, long >150k) before total/year/contest/genre/
  quality/random, because the dialogue pool spans 3k-1.77M words and a single
  favs list is dominated by long works. Added `words-band` to
  `/strata/rankings/classic` (short|medium|long), plumbed it through
  `ClassicListPage`, and added `/dialogue-random`.
- **Verified**: `go test ./...`, `flutter analyze`, `flutter test` pass;
  rebuilt `libstrata.so` and the debug APK. No adb install/tap was performed.
- **Next**: device acceptance by the user; check the 3-column card readability
  and each length-band route.

---

## 2026-11-21 - Official ranks scope split (long / dialogue)

- **Did**: reused the committed official-ranks Go API and demo; added `scope`
  to `OfficialRanksPage`. The long tab shows monthly ticket/new/hot + PC
  current boards; the dialogue tab shows only the dialogue monthly-ticket
  board. Added home wide-card entries in both tabs, removed the duplicate entry
  from the local rankings page, and passed `scope` through `/official-ranks`.
- **Verified**: `flutter analyze` and `flutter test` pass; the Go API is
  unchanged. Official board requests still go through the engine TTL cache.
- **Next**: device acceptance of both entry cards; do not drive the phone via
  adb unless the user explicitly asks.

---

## 2026-11-21 - Official dialogue direct + month picker

- **Did**: changed the dialogue tab's official card to open `/official-ranks/m4`
  directly (no intermediate board grid). Replaced the official detail page's
  month `DropdownButtonFormField` with a `‹ 2026-11 ›` strip plus a year/month
  BottomSheet, because the dropdown was buggy and felt like an old web form
  (user feedback). Added previous/next month limits and disabled months outside
  2013-03..current.
- **Verified**: `flutter analyze` and `flutter test` pass; debug APK rebuilt and
  installed immediately (user preference: always install after build).
- **Next**: device acceptance of the dialogue direct entry and month picker.

---

## 2026-11-21 - Drop duplicate PC current boards

- **Did**: removed PC current 月度月票榜 and 月度热销榜 from the official-ranks
  grid. Their current-month values are the same boards as the historical
  monthly library's current `rank=0` and `rank=3`. Only PC 月度打赏榜 remains
  (the monthly library has no 打赏 board). Go endpoint unchanged.
- **Verified**: `flutter analyze` and `flutter test` pass; debug APK rebuilt and
  installed immediately. No phone operation.
- **Next**: user acceptance.

---

## 2026-11-21 - Official rankings: remove grid, switch boards with tabs

- **Did**: deleted the intermediate official board grid. The long tab's official
  card now opens the ranking page directly with a TabBar for 月票/新书/热销/
  打赏. Extracted the month switcher + list into `_OfficialBoardView`, shared by
  the tab page and the dialogue direct page (`/official-ranks/m4`). Removed the
  now-unused `scope` query plumbing.
- **Verified**: `flutter analyze` and `flutter test` pass; debug APK rebuilt and
  installed immediately. No phone operation.
- **Next**: user acceptance of tab switching and the shared month picker.

---

## 2026-11-21 - Fill PC rank covers from seed

- **Did**: PC Rank rows carry no `<img>` at all, so every PC board entry had an
  empty `cover_url` and fell back to the default cover. Added
  `Store.CoverURLs` (local `covers` wins, then `seed.books.cover_url`) and used
  it in `officialRanksPc` to enrich every nid before caching/serving. Verified
  against the live page: the 打赏 rows have no image markup.
- **Verified**: `go test ./...` passes; rebuilt `libstrata.so` with NDK 28.2
  and rebuilt/installed the debug APK. No phone operation.
- **Also**: bumped the PC cache key to `pc:current:v2` so a v1 body cached
  before cover enrichment is not reused.
- **Next**: user acceptance of the 打赏 tab covers.

---

## 2026-11-21 - Dialogue monthly picker starts 2017-07

- **Did**: user verified the dialogue monthly-ticket board's first data month is
  **2017-07** (continuous from 2018-07, with a few empty slots in between). The
  month picker's lower bound is now board-specific: `m4` starts at 2017-07,
  every other historical board stays at 2013-03. Empty months remain selectable
  and render 无数据 rather than being hidden.
- **Verified**: `flutter analyze` and `flutter test` pass; rebuilt/installed the
  debug APK. No phone operation.
- **Next**: user acceptance of the dialogue month range.

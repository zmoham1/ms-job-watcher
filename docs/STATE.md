# ms-job-watcher — Session Handoff

## Current status

**As of 2026-07-12: external triggering via cron-job.org is DEAD and has been for 5+ weeks.** A health check found the last `workflow_dispatch` run was 2026-06-04 — every run since (76 of the last 100) has been `event=schedule`. The Jun 2 "verified in production" note below was accurate at the time but went stale silently; cron-job.org's own dashboard needs to be checked directly (this can't be diagnosed or fixed from the repo — it needs the account holder to log into cron-job.org and check job status/PAT rejection there). Worse, the GitHub-native fallback had *also* drifted from the documented `13 */3 * * *` sparse cadence down to a flat once-daily cron in both workflow files (`0 12 * * *` / `0 22 * * *`) — undocumented, cause unknown. Both workflow files have been restored to the `*/3h` fallback cadence (watcher `13 */3 * * *`, boards `43 */3 * * *`, offset to avoid both landing in the same slot) as of this commit. Real cadence until cron-job.org is fixed: every 3 hours, not every 10/30 min.

Pipeline 1 (`--mode main`) polls Microsoft, NVIDIA, Amazon, Goldman Sachs, IBM, and Oracle. Pipeline 2 (`--mode boards`) sweeps ~1,200 ATS boards in batches of 200. `seen.json` holds 6,357 deduplicated job IDs; `seen_boards.json` holds 41,881.

## Open bugs / issues

- [ ] **cron-job.org external dispatch is dead (since ~2026-06-04) — needs account-holder action.** Not fixable from the repo. Log into cron-job.org, check whether the watcher/boards jobs are paused, deleted, or erroring (likely PAT rejection or an account-side issue — the PAT itself doesn't expire until 2026-08-31, so that's not yet the cause). Until fixed, real cadence is the GitHub `schedule:` fallback (every 3h, just restored — see Current status).
- [x] **Oracle facets too narrow (0 fetched in production).** `_ORACLE_URL_SUFFIX` carried stale `selectedCategoriesFacet`/`selectedFlexFieldsFacets` params that silently zeroed out results without appearing in any visible filter UI. Removed 2026-07-12.
- [x] **Goldman Sachs under-fetch + loc_ok=0.** `GS_PAYLOAD` had a narrow `EXPERIENCE_LEVEL` filter (Support/Seasonal/Associate only) and 5-city `LOCATION` subfilters excluding valid US roles elsewhere. Also `normalize_goldman_item()` read `locations[0].primary` as a location string when it's actually a boolean flag. Both fixed 2026-07-12.
- [x] **IBM loc_ok=0 always.** `normalize_ibm_hit()` was reading `field_keyword_17` (IBM's work-arrangement field: "Hybrid"/"Remote"/empty) as the location, which never matched `is_us_location()`. The real city field is `field_keyword_19` (e.g. "Cambridge, US", sometimes the placeholder "Multiple Cities"); `field_keyword_05` is the country, guaranteed "United States" by the post_filter itself and used as fallback. Fixed 2026-07-12 — verified against live API samples.
- [ ] **Dead-board single-strike permanent marking — no resurrection.** One 404/410 = dead forever. 16 boards in current CSV are marked dead; some may be transient failures. Implement N-strikes (3 consecutive) or monthly TTL re-probe.
- [ ] **`boards_dead.json` has 921 orphaned entries (stale, not wasting throughput but misleading).** Only 16 of 937 entries overlap with the current CSV. Prune to match live CSV.
- [ ] **Large untapped board pool.** `greenhouse_us_verified.csv` (4,659 rows), `lever_us_verified.csv` (1,806 rows), `workday_us_verified.csv` (4,770 rows) — none ingested. Verify first, add in tranches.
- [ ] **Gmail account mismatch.** Connected Gmail is the wrong account; the alerts inbox hasn't been analyzed. Reconnect the correct inbox before doing Gmail-based funnel analysis.
- [ ] **IBM "Entry Level" facet (`field_keyword_18`) narrows results 13→3.** Flagged 2026-07-11, not yet changed — decide whether to broaden.

## Next steps

1. **After ~1 day of live dispatch runs, check `run_log.json` funnel data** — look at per-source `title_ok` and `loc_ok` counts to confirm the title classifier isn't over-dropping. If a source's "kept" count drops sharply after a filter tweak, that's the signal. Recall-first: err toward alerting.
2. **Reconnect the correct Gmail inbox**, then analyze which boards actually produce relevant alerts.
3. **Selectively ingest from the ~10k curated lists** (greenhouse/lever/workday_us_verified) — verify first, add in tranches; do NOT bulk-add (cycle staleness wrecks latency).
4. **[low] Dead-board resurrection + prune orphaned entries** — implement N-strikes (3 consecutive 404s) or monthly TTL re-probe instead of single-strike permanent marking; prune `boards_dead.json` down to the 16 entries that actually overlap the current CSV (921 are stale orphans).
5. **[optional, deferred by choice] Automated test harness** — pytest on `classify_title` / `is_us_location` was considered and deliberately deferred. `run_log.json` is the lightweight safety net for regressions. Not urgent unless the classifier is changed.

## Key facts & gotchas

- **Single file:** all logic lives in `watcher.py` (~2,160 lines after pagination additions). No external modules beyond `requests`.
- **State is committed to git** by the `github-actions` bot after every run. Push conflicts handled by a 5-retry loop with `git merge -X ours`. Remote state is always source of truth; pull before editing state files locally.
- **Scheduling was supposed to be EXTERNAL** — cron-job.org was meant to call the `workflow_dispatch` API (watcher every 10 min, boards every 30 min), but as of 2026-07-12 it's been silently dead since ~2026-06-04 (last real `workflow_dispatch` run). The GitHub `schedule:` cron in both files is the only thing actually running right now, restored to `13 */3 * * *` / `43 */3 * * *` (was found flattened to a once-daily cron in both files, cause unknown). Auth = a fine-grained PAT (this repo, Actions:write) stored in cron-job.org that **EXPIRES 2026-08-31** (not yet expired, so not the cause of the current outage — check cron-job.org's dashboard directly for paused/deleted jobs).
- **Dead boards: single-strike permanent.** One 404/410 → `boards_dead.add(board_id)` → skipped forever. No retry logic.
- **Dead boards: 921 of 937 are orphaned stale entries.** Only **16 boards** in the current 1,200-row CSV are actually dead. The other 921 are from boards removed in earlier CSV versions — they don't slow down batches.
- **Oracle was broken since day one.** `fetch_oracle` was returning the search container (`items` list, each a dict with `SearchId`, `Keyword`, etc.) instead of `items[0].get("requisitionList")`. This produced `oracle:url:` junk keys and 0 Oracle jobs ever entering `seen.json`. Fixed in commit `804f627b`.
- **GS/IBM/Oracle now paginate.** GS uses `pageNumber` increment; IBM uses `from` offset (Elasticsearch); Oracle uses `limit=50,offset=N` embedded in the finder query string. All three short-circuit when a full page is already in `seen_keys`.
- **New board bootstrap suppresses first-run alerts.** When a board is seen for the first time, all current jobs are added to `seen` silently — no email. Alert lag until second sweep.
- **Cursor persists in `state/boards_cursor.json`.** Wraps to 0 after reaching end of CSV. Full cycle = `ceil(n_boards / batch_size)` runs.
- **Workday URL normalization is complex.** `workday_normalize_external_job_url` handles 5 path shapes. Bugs here produce unclickable links in emails.
- **US location filtering** uses state abbreviation regex + ISO 3166 country-code blocklist. International cities with US-state-like abbreviations were fixed Apr 1 2026.
- **Concurrency:** ThreadPoolExecutor with per-platform semaphores (GH=8, Lever=8, SR=6, WD=4, Ashby=6). Workday is most restrictive.
- **Email:** Gmail SMTP SSL on port 465. Secrets: `EMAIL_USER`, `EMAIL_APP_PASSWORD`, `ALERT_TO_EMAIL`.
- **Recall-first philosophy:** a missed job (false negative) is expensive; a junk alert (false positive) is cheap. When in doubt, err toward alerting.
- **Security:** Full git-history scan was clean (no secrets ever committed). `.gitleaks.toml` added with `[extend] useDefault = true` + allowlist for `state/*.json`. The local-only `data/boards/workday_debug/` directory contains HAR files with expired AWS STS credentials — never committed, optional cleanup: `rm -rf data/boards/workday_debug/`.
- **Full architecture reference:** see `docs/ARCHITECTURE.md` — repo map, full function index, runtime traces, external API surface, and ranked risk findings.

## Backlog (later — not urgent)

Evidence gathered 2026-06-02 from ~10 hrs of live dispatch runs (29 main runs, 14 boards runs).
The boards lane is healthy (~250 emails over the window). All items below are main-mode curated-lane gaps.
Note: 100% location pass on Microsoft/Amazon/NVIDIA is expected — those queries are US-filtered upstream, not a bug.

- **Oracle — 0 fetched in every run despite the `804f627b` fix.** Zero Oracle coverage in production. Diagnosis when revisited: run `fetch_oracle` in isolation, inspect the raw API response + extraction key, confirm the fix actually landed in the deployed function.

- **Goldman Sachs — under-fetch + loc_ok=0 always.** Only ~2 jobs fetched per run (single page — pagination likely still broken), and the 1 title-passing job fails `is_us_location` every run. GS is a US company (NYC HQ); suspected location-string format the regex doesn't match. Also threw 403 errors in 2 of 29 runs. Fix plan: fix pagination first, then eyeball real location strings on the larger corpus to diagnose the regex miss.

- **NVIDIA fetches exactly 20, Amazon exactly 300 every run.** Round, stable counts that smell like un-paginated single-page results or hard caps silently truncating the full listing. Confirm both sources paginate to completion (or document why the count is correct).

- **[low] Boards recall spot-check.** Title pass rates (23–37%) and location drop-offs after title (Ashby 24%, Workday 26%) look like normal filtering of all-department global boards, but that's unverified. Someday: eyeball a sample of title-rejected and location-rejected jobs on one high-volume source to confirm the filters aren't dropping real US engineering roles.

## Future roadmap — board expansion (designed 2026-06-02, NOT started)

### Architecture decision: multi-pipeline sharding
Keep the existing 1,200-board pipeline **untouched** as the fast lane. Add coverage as **separate parallel pipelines** (`boards2.yml`, `boards3.yml` …), each ~2,000 boards, each with its own disjoint CSV + cursor + seen-file + cron-job.org trigger; stagger schedules so shards don't hit the same ATS concurrently. Target ~6,200 total (1,200 + ~2k + ~2k).

Separate pipelines chosen over appending to the 1,200 CSV because appending changes how often existing boards get swept (bigger cursor = slower revisit); separate shards keep the 1,200 truly untouched and fault-isolated.

### First move: Greenhouse + Lever (agreed next step, NOT built)
Lead with GH + Lever: cheapest platforms (1 GET/board, ~18 boards/sec on no-WD batches) and the only two with easy 304 change-detection. A single GH/Lever shard could sweep ~5k boards in ~5 min → cycles in 10–30 min, faster than the current pipeline.

Plan: extract net-new GH/Lever (verified lists minus current 1,200, deduped by slug) → async liveness-verify each → deploy as a separate pipeline. Zero risk to the working pipeline.

Workday = cost driver (4–26 API calls/board, no cheap change-detection): defer to its own shard with small batch + app-level count caching; slower cycle acceptable.

### Measurement findings (2026-06-02, from run_log.json + watcher.py inspection)
- **Huge headroom:** 200-board runs finish ~95s avg / 126s max of the 900s timeout (~14% used). Batch 200 is very conservative — adding boards need not hurt per-run latency if batch size scales up.
- **Per-board API cost:** GH = 1 GET; Lever = 1 GET; Ashby = 1 POST; SmartRecruiters = 1–5 GETs; Workday = 1 GET (boot) + 4–25 POSTs. Workday is "the clock."
- **Observed throughput:** ~2.1 boards/sec average; ~18 boards/sec on no-Workday batches (cursor 1000–1200 slice, 0 WD boards, ran in 11.2s).
- **Rate limits:** No throttling evidence from any boards platform at current load; 429s auto-retried transparently; only Goldman Sachs (main mode) threw 403s.
- **Change-detection:** GH & Lever = easy (ETag/304 conditional GET); SmartRecruiters = read `totalFound` on first page and bail early; Ashby & Workday = no HTTP path (both POST), would need app-level count/ID caching.

### Inventory — IN PROGRESS, BLOCKED (resume here next session)
Verified lists carry **only `company`, `platform`, `board_url`** — no industry, size, or location metadata. Sector/size targeting is NOT possible from these lists alone; needs external enrichment or job-text-level filtering.

Net-new-by-platform count **not yet computed**: dedup vs. live 1,200 returned zero overlap (wrong) due to a URL-format mismatch between verified lists and the live CSV. **Next session:** normalize URLs to per-platform slug before comparing. Known verified-list sizes (confirm on resume): Ashby ~49, Greenhouse ~4,659, Lever ~1,806, SmartRecruiters ~210, Workday ~4,770.

### Open questions for next session
- Real net-new GH/Lever count after URL-format fix.
- Job-text eligibility filter across ALL pipelines: drop roles requiring security clearance / "US citizen or PR required" / ITAR (ineligible on OPT); optionally flag "no sponsorship" (H-1B needed later). High value, situation-specific.

## Recent changes

- **2026-07-12** — Health check found cron-job.org external dispatch dead since ~2026-06-04 (silently fell back to GitHub `schedule:`, which had also drifted to a flat once-daily cron in both workflow files, cause unknown). Restored `*/3h` fallback cadence in both. Also fixed 3 verified bugs: Oracle facet over-narrowing (0 fetched), Goldman Sachs narrow filters + boolean/string field bug, and IBM location field bug (`field_keyword_17` is work-arrangement, not location — real city field is `field_keyword_19`, country fallback `field_keyword_05`). cron-job.org itself still needs the account holder to check its dashboard directly — not fixable from this repo.
- **2026-06-04** - `feat: add --hours-fresh posted-date filter`. `watcher.py` now supports `--hours-fresh N` in both `main` and `boards` mode and filters jobs by parsed `posted` timestamps before test emails and alerts are built. Current behavior is strict: jobs without a parseable posted timestamp are excluded when freshness filtering is enabled.
- **2026-06-04** - `feat: add local watcher config for email + title filters`. `watcher.py` now reads optional `watcher.local.json` (or `WATCHER_LOCAL_CONFIG`) for local email credentials and configurable title filters. Env vars still win for GitHub Actions. Added `watcher.local.example.json` and ignored `watcher.local.json` so local secrets and role tweaks do not get committed.
- **2026-06-04** - `feat: add always-send summary mode + local Windows automation scripts`. Added `--always-send-summary` so morning/evening runs can email a short "no matching jobs" digest instead of staying silent. Added `run_morning_digest.bat` and `run_evening_digest.bat`; local Windows Task Scheduler tasks were created at `8:00 AM` and `6:00 PM` using those scripts.

- **2026-06-02** — Expansion plan designed + budget measured. Multi-pipeline shard architecture decided; GH/Lever first move agreed. Verified-list inventory started (URL-format mismatch blocked net-new count — resume next session). See "Future roadmap" section above.
- **2026-06-02** — External triggering verified in production. `gh run list` confirms `event=workflow_dispatch` runs at 20:40 and 20:50 UTC (exactly 10 min apart, all success); boards dispatch also confirmed. Multi-hour latency fully resolved.
- **2026-06-02** — `ci: switch to external dispatch trigger — downgrade schedule to sparse fallback`. cron-job.org now drives both workflows (watcher 10 min, boards 30 min) via `workflow_dispatch` API (HTTP 204 verified). GitHub `schedule:` downgraded to `13 */3 * * *` (sparse fallback). PAT expires 2026-08-31.
- **2026-06-02** — Cadence audit: measured 10 watcher + 9 boards gaps post-Jun-1 cron change. Watcher median 268 min (target 10 min), boards median 273 min (target 30 min) — both worse than pre-change baseline. GitHub cron deprioritization confirmed; must move off Actions cron entirely.
- **2026-06-02** — `feat: add per-run funnel observability to state/run_log.json` (`d0d51894`). Both modes now record `{ts, mode, per_source: {src: {fetched, title_ok, loc_ok, new, emailed, error/errors}}, duration_s, cursor}` to `state/run_log.json` (bounded 1,000 records, picked up by existing `git add state/*.json`). Also prints a one-line summary to Actions log each run.
- **2026-06-01** — `fix: paginate Goldman Sachs, IBM, Oracle — fix Oracle requisitionList extraction` (`804f627b`). Oracle was broken since day one; now fixed. All three sources paginate fully.
- **2026-06-01** — `ci: improve cron cadence — watcher 10min offset, boards 30min offset` (`f7a5c236`). Moved off congested `:00/:15/:30/:45` slots.
- **2026-06-01** — `config: add .gitleaks.toml` (`1e06172d`). Suppresses `state/*.json` false positives while keeping default secret detectors active.
- **2026-06-01** — Full architecture audit: created `docs/ARCHITECTURE.md`; corrected dead-board count (16 active, 921 orphaned); confirmed Actions throttling as primary latency risk; identified GS/IBM/Oracle pagination gaps (now fixed).
- **2026-06-01** — Added `CLAUDE.md` and `docs/STATE.md` for persistent project memory. Repo made **public** (unlimited Actions minutes).

# Large-Download Production Stress-Test Plan

> A **plan** (not an automated benchmark) for validating the download pipeline
> under large-file and concurrent load on the real deployment. Per the brief:
> **no synthetic benchmarks** — you drive real downloads through the bot and
> **observe** the system with [`monitor-resources.sh`](monitor-resources.sh) and
> direct DB/Redis inspection. Companion: [`RAILWAY_DEPLOYMENT.md`](RAILWAY_DEPLOYMENT.md),
> [`PRODUCTION_VALIDATION.md`](PRODUCTION_VALIDATION.md).

---

## 0. Read this first — the real file-size ceiling

The brief mentions files "up to ~50 GB". **The Telegram Bot API cannot upload 50 GB.**
Actual, code-backed limits:

| Path | Max upload | Where |
|---|---|---|
| Public `api.telegram.org` | **50 MB** | default |
| Self-hosted Bot API server (D-040, [`LOCAL_BOT_API.md`](LOCAL_BOT_API.md)) | **2 GB** | set `BOT_API_BASE_URL` |
| App guard `max_file_size` | **2 GiB default** | `services/download_service.py` → files over it raise `FileTooLargeError` (permanent; user gets "file too large") |

So the **maximum deliverable single file is ~2 GB** with the self-hosted bot-api,
50 MB without it. This plan targets **up to 2 GB**. (50 GB would require a different
delivery channel entirely — out of scope for the Telegram Bot API and V1.)

**Second ceiling — time, not size.** The yt-dlp download step has a **300 s timeout**
(`_DEFAULT_DOWNLOAD_TIMEOUT`; confirm your worker wiring doesn't override it). A
download that takes longer than 300 s raises `DownloadTimeoutError` (retryable) →
re-queued at LOW priority → up to `WORKER_MAX_RETRIES` (default 3) → `permanently_failed`.
**300 s for 2 GB ≈ 55 Mbit/s sustained from the source.** For large/slow sources this
timeout — not the size cap — is the practical limit. Treat "does the timeout need
raising for large files?" as an explicit output of test **T7** (a config/tuning
decision for the Owner; do not change it as part of this plan).

---

## 1. Preconditions & tooling

- [ ] Deploy validated via [`PRODUCTION_VALIDATION.md`](PRODUCTION_VALIDATION.md).
- [ ] For >50 MB files: the **self-hosted bot-api** service is up and
      `BOT_API_BASE_URL` is set; `max_file_size` is at the intended cap (≤ 2 GiB).
- [ ] Enough **worker disk** for `DOWNLOAD_TEMP_DIR` (Railway: a Volume at
      `/tmp/downloads`), sized ≥ `largest_file × WORKER_COUNT × ~2` (download + mux headroom).
- [ ] Note the tunables in play: `WORKER_COUNT`, `WORKER_JOB_TIMEOUT` (300),
      `WORKER_MAX_RETRIES` (3), `WORKER_HEARTBEAT_INTERVAL` (30), `max_file_size`.
- [ ] Start the sampler in a side terminal for each test window:
      `deploy/monitor-resources.sh https://<api-domain> /tmp/downloads 5 stress-<test>.csv`
- [ ] Have `psql` and `redis-cli` access to the production data services (read-only is fine).
- [ ] A set of **real** source URLs of increasing size: small (~50–200 MB), medium
      (~500 MB–1 GB), large (~1.5–2 GB), and one deliberately **oversized** (>`max_file_size`)
      and one deliberately **slow/huge** (to exceed 300 s).

> Everything below uses real downloads through the real bot. No load generator.

---

## 2. Test matrix

Each test: **objective → method → observe → pass criteria.** Record results in §4.

### T1 — Single large download
- **Objective:** one near-cap file (~2 GB) completes and delivers.
- **Method:** from a test account, request one large URL; wait for delivery.
- **Observe:** `monitor` CSV (`tempdir_bytes` rises to ~file size then drops to 0 on
  cleanup; `active_workers`=1; `queue_depth`=0); `jobs.status` → `completed`.
- **Pass:** file delivered intact; job `completed`; temp dir returns to empty.

### T2 — Multiple concurrent downloads
- **Objective:** `WORKER_COUNT` downloads run in parallel without interference.
- **Method:** submit `WORKER_COUNT` medium files near-simultaneously (multiple accounts,
  or the per-user single-active rule permits one active per user — use several accounts).
- **Observe:** `active_workers` reaches `WORKER_COUNT`; each job independent; `tempdir_bytes`
  ≈ sum of in-flight files; RAM/disk stay within plan (T4/T5).
- **Pass:** all complete; none corrupt; no cross-job leakage; workers not starved.

### T3 — Queue behavior
- **Objective:** a backlog larger than `WORKER_COUNT` drains in order, none stuck.
- **Method:** submit `2–3 × WORKER_COUNT` downloads quickly.
- **Observe:** `queue_depth` rises above 0, then monotonically drains to 0; FIFO-by-priority
  (retries come back at LOW and go behind fresh jobs); `redis-cli -n 1 LLEN <queue key>`
  mirrors `queue_depth`.
- **Pass:** every job eventually `completed`/terminal; `queue_depth` ends at 0; no orphan
  `active_downloads` left (cleanup sweeps within ~`2 × WORKER_HEARTBEAT_INTERVAL`).

### T4 — RAM usage
- **Objective:** memory stays bounded across large + concurrent downloads (no whole-file-in-RAM).
- **Method:** run T1 and T2 with the sampler active.
- **Observe:** `mem_used_mb` over the window; expect it to track transcode/mux buffers,
  **not** total bytes downloaded (files stream to disk).
- **Pass:** peak RAM well under the worker plan's limit; no OOM kill / restart in worker logs.

### T5 — Disk usage
- **Objective:** temp disk never exhausts under peak concurrency.
- **Method:** run T2/T3 with the largest files the cap allows.
- **Observe:** `disk_used_pct` and `tempdir_bytes` peaks vs the volume size.
- **Pass:** `disk_used_pct` stays with headroom (e.g. < 85%); no `ENOSPC` in logs.

### T6 — Temporary-file cleanup
- **Objective:** every job's scratch dir is removed; no leak over time.
- **Method:** after T1–T3, and again after a failed/timed-out job (T7/T8).
- **Observe:** `tempdir_files`/`tempdir_bytes` return to ~0 between waves;
  `ls $DOWNLOAD_TEMP_DIR` empty; cleanup-worker logs show `cleanup_swept` /
  `cleanup_orphans_swept`.
- **Pass:** no residual `<job_id>` dirs after completion **or** failure; orphans from a
  killed worker are swept by the cleanup loop.

### T7 — Timeout behavior
- **Objective:** a download exceeding the 300 s step timeout fails cleanly and is handled.
- **Method:** request the deliberately **slow/huge** source (or throttle) so the download
  step exceeds 300 s.
- **Observe:** `DownloadTimeoutError` in worker logs; job goes to `retry_queued` (LOW), not
  a crash; the yt-dlp subprocess is killed (no zombie); temp dir cleaned (T6).
- **Pass:** timeout is caught, job re-queued (retryable), process reaped, user eventually
  gets success (if a retry fits the window) or a clear failure. **Record whether 300 s is
  adequate for your largest intended file** — tuning input for the Owner.

### T8 — Retry behavior
- **Objective:** transient failures retry up to the budget, then permanently fail; permanent
  errors (oversized) do **not** retry.
- **Method:** (a) induce a transient failure (e.g. interrupt the source mid-download);
  (b) request the **oversized** (>`max_file_size`) file.
- **Observe (a):** `retry_count` increments; re-queued at LOW; after `WORKER_MAX_RETRIES`
  → `permanently_failed`. **Observe (b):** `FileTooLargeError` → immediate
  `permanently_failed`, user told "file too large", **no** retry, **no** double-delivery.
- **Pass:** retry budget honored; permanent errors terminal on first try; a retry after a
  partial delivery never re-sends the file or re-shows an ad (idempotent fan-out).

### T9 — Worker utilization
- **Objective:** all workers are used; heartbeats stay live under load.
- **Method:** T2/T3 with the sampler.
- **Observe:** `active_workers` reaches `WORKER_COUNT` under backlog; heartbeats don't lapse
  (no false orphan sweeps mid-job); no single worker hogging.
- **Pass:** utilization scales to `WORKER_COUNT`; no heartbeat expiry during healthy jobs;
  adding load past `WORKER_COUNT` grows `queue_depth`, not failures.

### T10 — Redis load
- **Objective:** Redis stays healthy as queue/cache/locks/heartbeats/progress churn.
- **Method:** during T2/T3, watch Redis.
- **Observe:** `redis-cli INFO` — `used_memory`, `connected_clients`, `instantaneous_ops_per_sec`,
  `evicted_keys` (should be 0); `redis_connected` gauge stays 1; queue key length tracks
  `queue_depth`; progress/lock keys expire after jobs.
- **Pass:** no evictions, no connection saturation, memory bounded, `/v1/ready` Redis check
  stays `ok`.

### T11 — PostgreSQL load
- **Objective:** DB keeps up; the connection pool isn't exhausted.
- **Method:** during T2/T3, watch Postgres.
- **Observe:** `SELECT count(*) FROM pg_stat_activity WHERE datname=current_database();`
  vs the plan's connection limit; `db_pool_in_use` gauge; slowest statements
  (`pg_stat_statements` if available); `jobs`/`downloads`/`active_downloads` rows advance
  correctly; `downloads` partition for the current month exists.
- **Pass:** active connections stay under the limit (tune `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`
  and `WORKER_COUNT` if near it); no pool-timeout errors; row states consistent; no lock pileups.

---

## 3. Data collection

- One `stress-<test>.csv` per test window (the sampler), charted afterwards
  (queue_depth / active_workers / mem / disk / tempdir over time).
- DB snapshots: `jobs` status counts, `downloads` count, `pg_stat_activity` count.
- Redis snapshots: `INFO memory`, `INFO clients`, `INFO stats`, queue `LLEN`.
- Worker/api logs for the window (errors, timeouts, retries, cleanup lines, any OOM/restart).

---

## 4. Results & sign-off

| Test | Result | Peak RAM | Peak disk % | Notes (timeouts / retries / tuning) |
|---|---|---|---|---|
| T1 Single large | ☐ | | | |
| T2 Concurrent | ☐ | | | |
| T3 Queue | ☐ | | | |
| T4 RAM | ☐ | | | |
| T5 Disk | ☐ | | | |
| T6 Temp cleanup | ☐ | | | |
| T7 Timeout | ☐ | | | 300 s adequate? |
| T8 Retry | ☐ | | | |
| T9 Worker util | ☐ | | | |
| T10 Redis | ☐ | | | |
| T11 Postgres | ☐ | | | |

**Capacity conclusions (fill in):** max reliable single-file size `____`, max useful
concurrency `____` at `WORKER_COUNT=____`, recommended worker disk/RAM `____`, and any
tuning the Owner should apply (`max_file_size`, the 300 s download timeout,
`WORKER_COUNT`, DB pool). Feed these into `PERFORMANCE_REPORT.md`.

**Run by:** `__________`  **date:** `__________`  **overall:** **PASS / FAIL**

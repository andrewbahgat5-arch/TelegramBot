# Performance Report

> **Document Status:** LIVE · Append-only performance & load-test SSOT
> **Companion Documents:** `MASTER_PLAN.md` (Sections 2.5, 25.10, 25.15), `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`, `SECURITY_REPORT.md`
> **Last Updated:** 2026-06-23
>
> Append a new entry on every load run, every micro-benchmark series, every stress scenario, every capacity report. Never edit past entries.

---

## How to use this file

Three event types are recorded here:

1. **Load runs** — outcomes of a Simulation Framework execution at a given level (L1 through L6).
2. **Stress scenario runs** — outcomes of ST-1 through ST-6.
3. **Capacity reports** — auto-generated after L4 / L5 / L6 runs.
4. **Micro-benchmarks** — repeatable `pytest-benchmark` runs.

Entries are append-only. A correction adds a new entry; never edit the original.

---

## V1 Service Level Objectives (LOCKED — Section 2.5)

| Dimension | Target |
|---|---|
| URL → first user-visible response | p95 ≤ 2 s |
| Cached resend → delivered | p95 ≤ 1 s |
| Job queue → worker pickup (idle worker present) | p95 ≤ 1 s |
| End-to-end download → delivery (non-cached, 50 MB MP4) | p95 ≤ 90 s |
| Bot availability | 99.5% |
| Cache hit ratio after 30 days post-launch | ≥ 40% |
| Sustained users at L5 (1000) | meet all of the above |

A load run that violates any SLO produces a **regression**: the corresponding sprint cannot exit until the regression is resolved or formally accepted.

---

## Status Summary

| Level | Last Run | Last p95 (URL→keyboard) | Last p95 (download→delivery) | Last Cache Hit Ratio | Last Error Rate | Capacity Verdict |
|---|---|---|---|---|---|---|
| L1 (10) | — | — | — | — | — | — |
| L2 (50) | — | — | — | — | — | — |
| L3 (100) | — | — | — | — | — | — |
| L4 (500) | — | — | — | — | — | — |
| L5 (1000) | — | — | — | — | — | — |
| L6 (5000) | — | — | — | — | — | — |
| Stress: ST-1..ST-6 | — | — | — | — | — | — |

This summary is the only mutable region. Update its rows after each new entry.

---

## Load Run Template

```
### <Date YYYY-MM-DD HH:MM UTC> — Load Run L<level>

| Field | Value |
|---|---|
| Git SHA | <hash> |
| Environment | local | test | staging |
| Sprint | <number> |
| Triggered by | <PR # / sprint exit / pre-release / scheduled> |
| Level | L<number> (<users> simulated users) |
| Profile mix | Casual: X%, Active: Y%, Heavy: Z%, Abuse: W% |
| Traffic generator | RandomTraffic | ScheduledSpike | PeakHour | Viral | PlatformPattern |
| Duration | <hh:mm:ss> |
| Seed | <integer or "stochastic"> |
| Hardware profile | CPU: <model>, RAM: <GB>, Disk: <type>, Network: <gbps> |

**Application metrics**
| Metric | Value |
|---|---|
| Total requests | <N> |
| Successful responses | <N> |
| Error rate | <%> |
| Response time p50 / p95 / p99 | <ms> / <ms> / <ms> |
| Throughput (req/s) | <N> |

**Queue metrics**
| Metric | Value |
|---|---|
| Avg queue depth | <N> |
| Max queue depth | <N> |
| Avg processing time | <s> |
| Retry rate | <%> |
| Max fan-out cohort size | <N> |

**Worker metrics**
| Metric | Value |
|---|---|
| Worker count | <N> |
| Utilization (avg / max) | <%> / <%> |
| Avg processing speed | <jobs/min> |
| Failure rate | <%> |
| Heartbeat misses | <N> |

**Redis metrics**
| Metric | Value |
|---|---|
| Memory peak | <MB> |
| Ops/s peak | <N> |
| Cache hit ratio (file_id) | <%> |
| Cache hit ratio (metadata) | <%> |
| Lock acquire p95 | <ms> |

**Database metrics**
| Metric | Value |
|---|---|
| Query p50 / p95 | <ms> / <ms> |
| Pool used (max) | <N> |
| Write throughput | <writes/s> |
| Partition I/O hotspots | <list or "none"> |

**Provider metrics**
| Provider | Success | Failure | Fallback Activated | Health Transitions |
|---|---|---|---|---|
| ytdlp | <N> | <N> | <N> | <list> |

**SLO compliance**
- URL→keyboard p95 ≤ 2s: <pass/fail>
- Cached resend p95 ≤ 1s: <pass/fail>
- Queue pickup p95 ≤ 1s: <pass/fail>
- Download→delivery p95 ≤ 90s: <pass/fail>
- Error rate < 1%: <pass/fail>

**Notes / observations**
<anything operationally relevant>

**Linked PR / report files**
<urls>
```

---

## Stress Scenario Template

```
### <Date YYYY-MM-DD HH:MM UTC> — Stress Scenario ST-<id>

| Field | Value |
|---|---|
| Scenario | ST-<id> (<name from Section 25.15.6>) |
| Git SHA | <hash> |
| Environment | local | test | staging |
| Sprint | <number> |
| Duration | <hh:mm:ss> |

**Expected behavior** (from Section 25.15.6)
<copy of the LOCKED expected behavior>

**Observed behavior**
<what actually happened>

**Verdict**
<pass / fail / partial — with explanation>

**Metrics during scenario**
<key values; lean on Load Run Template structure where relevant>

**Action items (if any)**
- <ticket numbers, follow-up tasks>
```

---

## Capacity Report Template

Generated automatically after L4 / L5 / L6 runs.

```
### <Date YYYY-MM-DD HH:MM UTC> — Capacity Report

| Field | Value |
|---|---|
| Source run | <reference to a Load Run entry above> |
| Git SHA | <hash> |
| Hardware profile | <copy from source run> |

**Current sustainable capacity**
- Max supported simultaneous users (steady state): <N>
- Max downloads / hour: <N>
- Max queue throughput: <jobs/min>
- Bottleneck: <which subsystem hits the wall first>

**Projection at +50% load**
- Expected user count: <N>
- Estimated additional CPU / RAM / DB / Redis: <numbers>
- Estimated new hardware tier (if any): <description>

**Scaling recommendations**
- Vertical (next single-host upgrade): <description>
- Horizontal (next process / read replica / worker pool): <description>
- Earliest sprint / version that would need it: <Sprint or Version>
```

---

## Micro-Benchmark Template

For `pytest-benchmark` runs under `tests/performance/`.

```
### <Date YYYY-MM-DD HH:MM UTC> — Micro-benchmarks

| Field | Value |
|---|---|
| Git SHA | <hash> |
| Sprint | <number> |

| Benchmark | Median | Min | Max | StdDev | Trend vs. previous |
|---|---|---|---|---|---|
| <bench_name> | <ms> | <ms> | <ms> | <ms> | <±%> |
...

**Regressions** (>10% slower than previous)
- <bench_name> — <delta>; root cause: <…>; action: <…>.
```

---

## Standing Entries

### 2026-07-17 18:23 UTC — Isolated concurrency load run (queue + worker pool, stub download) — NOT an SLO/capacity measurement

> **Scope & honesty:** this exercises the **real** `QueueService` + Redis reliable
> queue (atomic Lua dequeue) + the **real** `DownloadWorker` pool at N-way concurrency,
> with a **stub** `DownloadService` (per-job work simulated as `asyncio.sleep`). It
> validates the coordination layer — queue integrity, worker concurrency, failure/ack
> handling, memory stability — and deliberately does **not** touch the residential
> proxy, YouTube, ffmpeg, disk, or Telegram. It is therefore **not** an SLO or capacity
> result (download→delivery, URL→keyboard, cache-hit are unmeasurable here); the LOCKED
> Status-Summary rows stay empty pending the real Phase-B L4 run. External bottlenecks
> (proxy bandwidth/ban, ffmpeg CPU on 4 cores, disk for concurrent temp files, Telegram
> upload flood limits) are the real ceiling for 500 *real* downloads and are untested here.

| Field | Value |
|---|---|
| Git SHA | `8f5fafe` (worktree `happy-bose-71ed46`) |
| Environment | throwaway Redis (`redis:7`) on its own Docker network on the prod VPS host; harness in an ephemeral `telegram-bot/worker:v1` container. Fully isolated from the live stack; torn down after. |
| Hardware | prod VPS: 4 vCPU, 7.8 GB RAM (shared host; live bot running) |
| Harness | `loadtest.py` — real `QueueService`/`RedisQueue`/`DownloadWorker`, stub `DownloadService` (sleep = simulated download+transcode+upload) |
| Prod reference | live `WORKER_COUNT=8`, 1 worker container, `DB_POOL_SIZE=10` |

**Scenarios**

| Scenario | Config | Drain | Throughput | Peak concurrency | Integrity | Peak RSS | Verdict |
|---|---|---|---|---|---|---|---|
| A baseline | 500 jobs / 8 workers, sim 0.05–0.20 s | 8.73 s | 57.3 jobs/s | 8/8 | 500 ok · 0 lost · 0 dup | 68 MB | PASS |
| B headroom | 500 jobs / 64 workers, sim 0.05–0.20 s | 1.56 s | 321.5 jobs/s | 64/64 | 500 ok · 0 lost · 0 dup | 69 MB | PASS |
| C failure/ack | 200 jobs / 8 workers, 20% fail | 1.55 s | 109.5 jobs/s | 8/8 | 170 ok + 30 failed = 200 · 0 lost · 0 dup | 68 MB | PASS |
| D realistic | 120 jobs / 8 workers, sim 4–14 s | 138.75 s | 0.9 jobs/s | 8/8 | 120 ok · 0 lost · 0 dup | 68 MB | PASS |

**Observations**
- **Enqueue burst:** 500 jobs enqueue in ~0.3 s (~1,700/s) — a simultaneous 500-user hit is trivial for the queue.
- **Integrity:** every job processed exactly once in all runs (atomic dequeue → no double-delivery; failed jobs ack without wedging). 0 lost, 0 duplicate throughout.
- **Concurrency:** workers saturate fully (8/8, and 64/64 in B); the queue scales cleanly to 8× `WORKER_COUNT` with no loss.
- **Memory:** flat ~68 MB across every run — no leak under 500-job load.
- **Throughput is worker-bound:** drain ≈ `N_JOBS ÷ WORKER_COUNT × avg_job_time`. Scenario D (~9 s/job, 8 workers) → **~500 jobs would drain in ~9–10 min**; with real 4K per-download times (~20–40 s incl. transcode+upload) the 500th user waits **~20–45 min**, first 8 start immediately.

**Action items**
- Real bounded end-to-end sample (24–40 real downloads) to measure true per-download cost + CPU/proxy headroom, then right-size `WORKER_COUNT` vs. 4 vCPU + single proxy.
- Phase-B real L4 (500) via the simulation framework for the LOCKED SLO/capacity rows.

### 2026-06-27 — Sprint 11 (11.10 partial) — FRAMEWORK DRY-RUN (stub transport, NOT a capacity measurement)

> **Important:** these numbers come from the deterministic in-memory `StubBotClient`,
> **not** the real bot. They validate that the simulation framework runs each load
> level to completion and writes a reproducible report entry (the §25.15.9 / 11.10
> validation-checklist item), and that the **Abuse profile is fully blocked at scale**.
> They are **not** SLO/capacity results — the LOCKED Status-Summary rows above stay
> empty until the Phase-B sandbox + isolated test infra are provisioned and the real
> L1–L4 runs execute. The V1 SLOs (p95 URL→keyboard ≤ 2 s, download→delivery ≤ 90 s,
> cache hit ratio) require the live bot and cannot be measured here.

| Field | Value |
|---|---|
| Git SHA | this commit (Sprint 11 Phase-A); worktree `happy-bose-71ed46` |
| Transport | `StubBotClient` (deterministic, network-free) |
| Seed | 42 |
| Profiles | Casual,Active,Heavy (mixed) |
| Command | `python -m tests.simulation.runner --level=<L> --profile=Casual,Active,Heavy --seed=42` |

| Level | Users | Actions | Succeeded | Blocked | Successful downloads | Stub action-latency p95 (ms) |
|---|---|---|---|---|---|---|
| L1 | 10 | 439 | 212 | 227 | 64 | 67.9 |
| L2 | 50 | 2225 | 1082 | 1143 | 326 | 67.5 |
| L3 | 100 | 4354 | 2145 | 2209 | 647 | 67.6 |
| L4 | 500 | 22988 | 10789 | 12199 | 3243 | 67.5 |

**Abuse profile (L2, seed 42):** 9050 actions → **0 successful downloads**, 6000 download attempts blocked (M-22 invariant holds at scale).

**Notes:** the ~0.51 mixed-profile block rate is a **stub artifact** — `StubBotClient` enforces the default free daily-limit (10) and rate ceiling, so Heavy users (20–40 downloads/session) are correctly throttled; this is the modeled abuse defense, not a system bottleneck. The stub latency is synthetic. Determinism confirmed (fixed seed → identical per-action outcomes; throughput excluded as wall-clock dependent). Real L1–L4 capacity + SLO verdicts are **pending Phase B**.

### 2026-06-27 — Capacity Report (Sprint 11, 11.13) — PENDING PHASE-B DATA

The capacity-planning report (§25.15.7: max steady-state users, max downloads/hour,
max queue throughput, +50% hardware estimate, scaling recommendation) requires the
real L4/L5/L6 runs against the provisioned sandbox + test infra. The framework,
metrics catalog (§25.15.5), and report writer are in place; this section will be
filled from the Phase-B `--level=L4/L5/L6` runs. No capacity numbers are asserted
until then (no fabricated data).

### Pre-Sprint 0 — 2026-06-23

| Field | Value |
|---|---|
| State | No code, no simulation framework, no measurements. |
| Notes | This file is initialized empty. First real entry expected at the end of Sprint 6 (single-user end-to-end timing). Simulation framework arrives in Sprint 11. |

---

## Disaster Recovery — Backup/Restore Drills (Section 14.8, Task 10.7)

Append one entry per drill. Full procedure + report: [`deploy/restore-drill-report.md`](deploy/restore-drill-report.md).

### 2026-06-25 — Restore drill #1 (Sprint 10, dev stack)

| Field | Value |
|---|---|
| Source DB | `telegram_bot` @ `tgbot_postgres` (postgres:15) |
| Method | `pg_dump -Fc` → `createdb` throwaway → `pg_restore` → integrity compare → drop throwaway |
| Dump size | 251 KB (custom format) |
| Migration head (source = restore) | `202606240001` ✅ |
| Row-count parity (source = restore) | settings 31=31, users 4=4, advertisements 8=8, media_metadata 38=38, cached_files 60=60 ✅ |
| Partitions restored | 260 = 260 (`pg_inherits`) ✅ |
| Sample query on restore | `settings` read OK (`ads_enabled=true`, `free_daily_limit=10`) ✅ |
| Result | **PASS** — restore produces a byte-faithful, queryable database. |
| Notes | Drill run against the dev stack. Production drill (real volumes, PITR/WAL) is scheduled 30 days post-launch (Task 12.6). |

---

## Release Snapshots

```
### Release V<X.Y> — <Date>

| Field | Value |
|---|---|
| Git tag | v<X.Y>.<Z> |
| L4 result | <pass / fail with numbers> |
| L5 result | <pass / fail with numbers> |
| L6 result (if run) | <pass / fail with numbers> |
| Open performance regressions at release | <list, must be 0 for V1 launch> |
| Sign-off (Owner) | <name + date>; capacity report reviewed |
```

---

> **End of `PERFORMANCE_REPORT.md`.** Append-only. Update on every load run, stress scenario, capacity snapshot, or benchmark series.

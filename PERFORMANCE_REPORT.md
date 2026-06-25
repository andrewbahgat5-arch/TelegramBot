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

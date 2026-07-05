# Telegram SaaS Download Bot — Master Implementation Plan

> **Document Status:** CANONICAL · Single Source of Truth · Supersedes all prior reference documents
> **Version:** 2.0
> **Last Updated:** 2026-06-23
> **Owner:** Project Architect
> **Audience:** Every AI agent and human contributor working on this project
> **Target Scale (V1):** 20,000 daily users · 300,000 monthly users
> **Lifetime Roadmap:** V1 through V6 and beyond
>
> This document overrides any conflict found in:
> - `project_reference.md` (v1.2, 2026-06-22) — historical, retained for context
> - `database_reference.md` (v1.0, 2026-06-22) — historical, retained for context
>
> Where this document disagrees with either of the above, this document wins. Both prior documents are now reference-only. They must not be used to resolve schema, naming, or architecture questions.

---

## Reading Order for AI Agents

Read in this order on every cold start. Do not skip steps.

1. **Section 1 — AI Agent Execution Rules.** The constitution. Non-negotiable. Read fully.
2. **Section 2 — Project Charter.** Scope and what is explicitly out of scope.
3. **Section 3 — Version Roadmap.** What ships when. Required to avoid violating future-proofing.
4. **Section 4 — Architecture Governance.** Locked decisions vs. configurable knobs.
5. **Section 9 — Component Catalog.** Mapping from concern → owning module.
6. **Section 10 — Locked Database Schema.** The only valid schema. Quote it; do not rederive it.
7. **The sprint you are working on** (Section 23–24). Do not read sprints other than the active one unless explicitly tasked.

If any required document referenced by this plan is missing, **stop and ask** — do not infer.

---

## Table of Contents

### Part I — Governance
1. [AI Agent Execution Rules](#1-ai-agent-execution-rules)
2. [Project Charter](#2-project-charter)
3. [Version Roadmap (V1 – V6+)](#3-version-roadmap-v1--v6)
4. [Architecture Governance Rules](#4-architecture-governance-rules)
5. [Decision Log](#5-decision-log)

### Part II — Architecture Reference (Locked)
6. [Technology Stack](#6-technology-stack)
7. [Repository Layout](#7-repository-layout)
8. [Architecture Layers and Dependency Rules](#8-architecture-layers-and-dependency-rules)
9. [Component Catalog](#9-component-catalog)
10. [Locked Database Schema](#10-locked-database-schema)
11. [Cache Architecture](#11-cache-architecture)
12. [Queue Architecture](#12-queue-architecture)
13. [Configuration Management](#13-configuration-management)
14. [Security Principles](#14-security-principles)
15. [Observability](#15-observability)

### Part III — Data Flows (Canonical)
16. [Canonical Data Flows](#16-canonical-data-flows)

### Part IV — Future Versions Readiness
17. [Future Versions Readiness Review](#17-future-versions-readiness-review)
18. [Extension Points Catalog](#18-extension-points-catalog)
19. [Database Evolution Strategy](#19-database-evolution-strategy)
20. [API Evolution Strategy](#20-api-evolution-strategy)
21. [Queue and Worker Scalability](#21-queue-and-worker-scalability)

### Part V — Execution
22. [Master Execution Plan](#22-master-execution-plan)
23. [Sprint Plan](#23-sprint-plan)
24. [Task Decomposition Standard](#24-task-decomposition-standard)
25. [Testing Strategy](#25-testing-strategy)
26. [Progress Tracking](#26-progress-tracking)

### Part VI — Appendices
27. [Open Questions](#27-open-questions)
28. [Glossary](#28-glossary)
29. [Supersession Notes (vs. prior docs)](#29-supersession-notes-vs-prior-docs)

---

# Part I — Governance

## 1. AI Agent Execution Rules

These rules apply to every AI agent and every human contributor. Violations are project-level defects, even if the code compiles.

### 1.1 Sources of Truth (Order of Precedence)

When two sources disagree, the higher-numbered source wins.

1. **Code merged on `main`** — actual behavior, last resort.
2. **This document (`MASTER_PLAN.md`)** — architectural truth.
3. **`PROJECT_PROGRESS.md`** — implementation-status truth (what is built, what is not, what is blocked, what was tested). Must be kept in sync with `main` at all times.
4. **Active sprint definition (Section 23)** — current scope.
5. **`project_reference.md`, `database_reference.md`** — informational only. Superseded.
6. **Any other document, chat message, screenshot** — informational only.

If you find a contradiction between `main` and this document, **stop and report it**. Do not "fix" the code to match the doc without explicit approval, and do not silently update the doc to match the code.

### 1.2 Authoritative Files

| Concern | Authoritative File |
|---|---|
| Architecture, scope, sprint plan | `MASTER_PLAN.md` (this file) |
| Implementation status, completion, session handoffs | `PROJECT_PROGRESS.md` |
| Database schema | Section 10 of this file |
| Configuration keys | Section 13 of this file + `core/config.py` once written |
| Public API contracts | Section 20 + OpenAPI generated from FastAPI |
| Domain entities & enums | `domain/` directory once written |
| Download provider inventory | Section 12.6 of this file |

### 1.3 Hard Rules — Never Violate

1. **Never change architecture layers** (Section 8). Do not add cross-layer imports. Do not import infrastructure from domain. Do not import from a sibling service.
2. **Never modify the schema in Section 10** without an approved migration entry in Section 19 and an updated decision-log entry in Section 5.
3. **Never add a new dependency** to `pyproject.toml` without an entry in Section 6.4 and a decision-log entry. Pin versions exactly.
4. **Never invent a database column, table, index, or constraint** that is not in Section 10. If you need one, propose it first.
5. **Never invent a configuration key.** All keys live in Section 13. If a new one is needed, propose it first.
6. **Never store secrets** (bot token, DB password, API keys, Sentry DSN) in code, logs, error messages, comments, commit messages, test fixtures, or example files.
7. **Never use `--no-verify`, `--force`, `--no-edit`, or `--no-gpg-sign`** on git operations unless the human owner explicitly asks.
8. **Never delete or rewrite migrations once merged.** New schema changes require a new migration.
9. **Never call yt-dlp, FFmpeg, or Telegram APIs from the bot or service layer.** All external I/O lives in `infrastructure/`.
10. **Never assume the operator will fix it.** Every code path that can fail in production must have a logged, observable, and (where possible) recoverable failure mode.
11. **Never reference a specific download provider** (yt-dlp, gallery-dl, direct HTTP, anything else) from `bot/`, `services/`, `workers/`, or `api/`. All provider calls traverse `DownloaderRegistry` via `DownloaderProtocol`. Importing `yt_dlp` outside `infrastructure/downloader/providers/ytdlp_provider.py` is forbidden. No layer above infrastructure may branch on a provider's identity (e.g., `if provider.name == "ytdlp": ...`).
12. **Never complete a task without updating `PROJECT_PROGRESS.md`.** Marking a task done in code without updating the progress file is a process defect. See Section 26 and `PROJECT_PROGRESS.md` itself for the procedure.

### 1.4 Pre-Flight Checklist (Before Editing Any File)

For every task, before writing code:

1. Confirm you are working in the **active sprint**.
2. Confirm the task is **listed in the sprint** (Section 23).
3. Read the **component card** for every component you will touch (Section 9). Identify:
   - What the component can modify.
   - What the component must never modify.
   - Its dependencies.
4. Read the **schema rows** for every table you will touch (Section 10).
5. Read the **data flow** for the feature you are implementing (Section 16).
6. If any of the above is unclear, **stop and ask**. Do not guess.

### 1.5 Implementation Rules

1. **No business logic in handlers.** Handlers parse, delegate, format. That is all.
2. **No infrastructure imports in services.** Services depend on `domain/protocols/`. Concretes are injected at the entry point.
3. **No silent fallbacks.** Every fallback must log a structured warning that includes the correlation ID.
4. **No swallowed exceptions.** Catch only what you can handle. Re-raise the rest.
5. **No commented-out code.** Delete it. Git remembers.
6. **No "future-proofing" code that does nothing today.** Extension points are listed in Section 18 — implement them only when the corresponding sprint arrives.
7. **No new abstractions without a second use case** present or imminent within the same sprint.
8. **No premature optimization.** Measure first. Section 22 lists the only performance targets you must meet for V1.
9. **No global state.** Services hold injected dependencies; modules hold pure functions.

### 1.6 Forbidden Patterns

| Pattern | Why Forbidden |
|---|---|
| `from infrastructure.* import *` inside `services/` or `domain/` | Breaks the dependency rule (Section 8). |
| Raw SQL strings outside `infrastructure/database/repositories/` | Bypasses repository layer; hides queries from review. |
| Hard-coded user IDs, role names, or settings values inside services | Use config or domain enums. |
| Catching `Exception` without re-raise or domain-exception translation | Hides failures. |
| `print()`, `logging.info()` direct calls | Use the structured logger from `core/logging.py`. |
| Synchronous network or disk I/O inside `async def` handlers | Will block the event loop. Use async clients. |
| New top-level directories | Layout is locked in Section 7. |

### 1.7 When You Must Stop and Ask

Stop and ask the human owner — do not infer — when any of the following is true:

- You believe the schema in Section 10 is wrong for the task.
- The task requires a configuration key not in Section 13.
- The task requires a dependency not in Section 6.4.
- The task requires touching a component the task description did not authorize.
- A test failure cannot be explained by the change you made.
- The acceptance criteria in the sprint section are ambiguous.
- You believe the active sprint is not the right sprint for this work.

### 1.8 Definition of Done (Per Task)

A task is "done" only when **all** of these are true:

1. The task's stated acceptance criteria (Section 23) are met.
2. **Unit tests** cover the new code; existing tests pass.
3. **Integration tests** pass for any touched data flow.
4. **Security tests** pass for any touched authn/authz/input/secret path (Section 25.9).
5. **End-to-end (E2E) tests** pass for any user-visible flow, including Telegram bot behavior (Section 25.7, 25.8).
6. **Manual verification recorded** for any item in the Manual Test Catalog (Section 25.16) reached by this task.
7. **Regression tests** added for any bug closed by this task (Section 25.11).
8. The change introduces no new lint or type-check failures (`ruff`, `mypy --strict`, `import-linter`).
9. `pip-audit` and `bandit` report no new high-severity findings.
10. New configuration keys (if any) appear in `.env.example` and Section 13.
11. New schema changes (if any) ship with an Alembic migration and a Section-19 entry.
12. New components (if any) have a Component Card added to Section 9.
13. Logs emitted by the new code use the structured logger with correlation IDs.
14. New download providers (if any) are registered through `DownloaderRegistry` and listed in Section 12.6.5.
15. **`PROJECT_PROGRESS.md` updated in the same PR** — task status flipped to `[x]`, completion date, validation results, files affected, implementation notes. The PR description must link the progress-file diff.
16. **`TEST_RESULTS.md` updated** with the new test-run outcomes.
17. If the task touched security: **`SECURITY_REPORT.md` updated** with findings.
18. If the task touched performance: **`PERFORMANCE_REPORT.md` updated** with benchmarks.
19. If the task triggers a Human Verification Gate (Section 25.13): **Owner sign-off recorded** in the PR (`Gate <ID> approved`).

Marking a task done without all applicable items is a process defect, not just sloppiness. A future agent reading `PROJECT_PROGRESS.md` will trust it to reflect reality. Drift defeats the file's purpose.

### 1.9 Definition of Done (Per Sprint)

A sprint is "done" only when **all** of these are true:

1. Every task's Definition of Done passes.
2. The sprint's Exit Criteria (Section 23) pass.
3. Human verification items (Section 23) are signed off by the human owner.
4. The agent has produced a sprint summary in `PROJECT_PROGRESS.md` listing what changed (see "Sprint Closeout" template in that file).
5. A Session Handoff section is appended to `PROJECT_PROGRESS.md` with: current state, completed work, remaining work, known issues, recommended next task, files modified, validation status.
6. The agent has stopped and waited for explicit "proceed" before starting the next sprint.

### 1.10 Future-Proofing Rules

Before implementing any feature:

1. Read the matching Future Versions Readiness entry (Section 17).
2. Confirm your design does not block a documented future requirement.
3. If the simplest V1 solution blocks a planned V2–V6 feature, choose the next-simplest solution that does not block it. Document the choice in Section 5.
4. Never close an extension point (Section 18) without explicit approval.

### 1.11 Conflict Resolution Protocol

When you discover a conflict:

1. Stop the current task.
2. Locate the conflict precisely: file, line numbers, both versions.
3. Determine which source has higher precedence (Section 1.1).
4. Propose a resolution. Do not implement it.
5. Wait for the human owner's decision.
6. Record the decision in Section 5.

---

## 2. Project Charter

### 2.1 Vision

Build a production-grade Telegram SaaS download platform capable of scaling from hundreds of users per day to tens of thousands of users per day while maintaining high performance, reliability, and future extensibility through V2–V6.

### 2.2 Core User Flow (V1)

1. User sends a supported social media URL.
2. Bot analyzes the URL and presents available formats and qualities.
3. User selects format and quality.
4. System checks the global file cache first.
5. If cached: file is sent instantly via Telegram `file_id`.
6. If not cached: a job enters the queue; a worker downloads, transcodes if needed, uploads, and caches the resulting `file_id`.
7. User receives progress updates until completion.
8. The action is recorded in the user's download history for future instant access.

### 2.3 In Scope (V1)

| Capability | Notes |
|---|---|
| Video downloads | Via yt-dlp. |
| Audio downloads | Via yt-dlp + FFmpeg. |
| Format selection | From yt-dlp metadata. |
| Quality selection | From yt-dlp metadata. |
| Queue system | Redis-backed, priority-aware, adjustable worker count. |
| Telegram `file_id` cache | Global, user-independent. |
| Download history | Per-user, paginated, with instant resend. |
| Admin panel | In-bot. Owner + Moderator roles. |
| Statistics | Real-time, system-wide. |
| Broadcast system | Owner-only. With language/role filters. |
| Error tracking | Sentry + internal `error_logs`. |
| Monitoring | Health checks, uptime probes, metrics endpoints. |
| Smart ad system | Admin-managed, frequency-controlled. |
| Ban system | With audit trail. |
| Rate limiting | Per user, per role, configurable. |
| Multi-user fan-out | Two users requesting the same content while one download is in flight both receive the result. |

### 2.4 Out of Scope (V1 — Reserved for Later Versions)

| Capability | Reserved For |
|---|---|
| Premium subscription enforcement | V2 |
| Multi-language interface | ~~V2~~ **Shipped in V1, Sprint 11.5** (D-061–D-063) — see §23 Sprint 11.5. |
| Multiple links in one request | V2 |
| Web dashboard | V3 |
| Payment integration (Stripe, YooKassa, crypto, Telegram Stars) | V4 |
| Referral system | ~~V5~~ **Shipped in V1, Sprint 13** (D-066) — see §23 Sprint 13. |
| Multi-engine downloads with fallback (gallery-dl, etc.) | V6 |
| Group chat support | Post-V6 |
| Push notifications outside Telegram | Out of scope indefinitely |

V1 must include the **schema hooks and extension points** for everything reserved for V2–V6 (Section 17, 18). V1 must **not include implementations** of any reserved capability.

### 2.5 Non-Functional Requirements (V1)

| Dimension | Target |
|---|---|
| Daily active users | 20,000 (steady state) |
| Monthly active users | 300,000 |
| Cache hit ratio (`file_id`) | ≥ 40% within 30 days of launch |
| URL → first user-visible response | p95 ≤ 2 s |
| Cached resend (file_id) → delivered | p95 ≤ 1 s |
| Job queue → worker pick-up (idle worker present) | p95 ≤ 1 s |
| End-to-end download → delivery (non-cached, 50 MB MP4) | p95 ≤ 90 s |
| Bot availability | 99.5% |
| RPO (data loss tolerance) | ≤ 15 minutes |
| RTO (recovery time) | ≤ 60 minutes |

### 2.6 Stakeholders

| Role | Responsibility |
|---|---|
| **Owner** (human) | Architectural decisions, scope changes, sprint approval, conflict resolution. The only person authorized to override Section 1. |
| **AI Agents** | Implementation, testing, documentation upkeep. Bound by Section 1. |
| **Moderators** (runtime) | User management. No code access. |
| **End Users** (runtime) | Use the bot. No code access. |

---

## 3. Version Roadmap (V1 – V6+)

The version sequence is defined by the project brief and is binding on architecture.

| Version | Theme | Headline Features |
|---|---|---|
| **V1** | Production foundation | Core download flow, queue, cache, history, admin panel, statistics, broadcasts, error tracking, monitoring. |
| **V2** | Monetization base + global reach | Premium subscription tier (priority queue, larger limits, ad-free), ~~multi-language UI~~ (shipped early — see below), multiple links per single request. |
| **V3** | Operator UX | Full web dashboard (admin and analytics) over the FastAPI layer. |
| **V4** | Revenue | Payment integration: Stripe (international), YooKassa (RU/CIS), crypto (TON/USDT), Telegram Stars. |
| **V5** | Growth | ~~Referral system with codes, bonuses, tracking.~~ (shipped early — see below) |
| **V6** | Resilience | Multi-engine download architecture with automatic fallback (yt-dlp primary, gallery-dl secondary, direct HTTP tertiary). |
| **Post-V6** | TBD | Group support, advanced analytics, possibly federation. |

Each version is a separate release. No version may begin until the previous version's sprints are accepted by the Owner.

**V2 footnote (2026-07-01):** the multi-language UI line item shipped ahead of schedule, in V1 Sprint 11.5, at the Owner's explicit direction (English + Arabic, unlimited future languages via catalog files — D-061–D-063). V2 may still add further languages or a self-serve translation workflow; the localization *architecture* itself is not V2 scope any more.

**V5 footnote (2026-07-05):** the referral system line item also shipped ahead of schedule, in V1 Sprint 13, at Owner direction (unique per-user codes, permanent stacking bonus downloads to both referrer and referred, admin analytics dashboard + leaderboard — D-066). This realizes EP-1 (`users.referred_by`, sketched for V5) with a richer design than originally scoped: a dedicated `referrals` table (not just a counter column) so invite history and per-referral reward status are queryable, not just a running total. V5 may still add payment-linked referral tiers or multi-level referral chains once V4 payments exist; the referral *tracking and reward architecture* itself is not V5 scope any more.

The Owner reserves the right to publish a dedicated Version Roadmap document at any time. When that document arrives, this section is updated to reference it, and the new document takes precedence over this section. Architecture decisions made before the new roadmap arrives must hold up against it; if they do not, they are revisited per Section 1.11.

---

## 4. Architecture Governance Rules

### 4.1 Locked vs. Configurable

Decisions in this document fall into three buckets:

| Bucket | Meaning | How to Change |
|---|---|---|
| **LOCKED** | Cannot be changed without Owner approval and a Section-5 decision-log entry. | Open an issue, propose, wait for approval. |
| **CONFIGURABLE** | Designed to vary by environment. Driven by `settings` table or env vars. | Edit the value, no architecture change. |
| **DEFERRED** | Not decided yet. Owner will decide before the relevant sprint. | Listed in Section 27. |

The default state is LOCKED unless explicitly marked otherwise.

### 4.2 Architecture Governance Principles

1. **V1 speed never beats long-term maintainability.** A V1 solution that blocks V2 is a defect, not a shortcut.
2. **Every cross-cutting concern has exactly one home.** Logging is in `core/logging.py`. Configuration is in `core/config.py`. Sentry is in `core/sentry.py`. No alternatives.
3. **Every external dependency is wrapped.** yt-dlp, FFmpeg, Telegram API, Postgres, Redis — all behind an adapter in `infrastructure/`. Services see protocols, not vendors.
4. **Every persistent state mutation is observable.** Insert, update, delete: each emits a structured log entry.
5. **Every async operation has a timeout.** No unbounded `await`.
6. **Every queue job is idempotent.** Re-processing a job must not double-charge the counters, duplicate the upload, or send the user the file twice.
7. **Every horizontal-scale prerequisite is enforced from day one.** No in-process state holds authoritative data. Even on single-server V1, state is in Postgres or Redis.
8. **Backwards compatibility within a major version.** Schema migrations within V1 sprints must be additive whenever feasible. Destructive changes require Owner approval and a documented rollout plan.

### 4.3 Three Inviolable Architectural Rules

These are the topmost constraints. They are tested by the architecture review on every PR.

1. **Dependency direction is inward.** `bot → services → domain` and `infrastructure → domain`. Nothing imports outward.
2. **Telegram, yt-dlp, FFmpeg, Postgres, Redis are vendors, not architecture.** Replacing any one of them must be a localized infrastructure change.
3. **The user-visible bot can be killed and restarted without data loss.** All in-flight state is recoverable from Postgres + Redis.

---

## 5. Decision Log

Every non-obvious decision is recorded here with date, rationale, and (if applicable) alternatives rejected. Every change to a LOCKED item adds a new row.

| # | Date | Decision | Rationale | Alternatives Rejected |
|---|---|---|---|---|
| D-001 | 2026-06-23 | `users.premium_expires_at` (plural, `-s`). | Consistent with PostgreSQL norm for timestamp columns (`expires_at`, `started_at`). Matches Stripe webhook convention used by likely V4 integration. | `premium_expire_at`. |
| D-002 | 2026-06-23 | `user_preferences` has surrogate `id BIGINT PK` + `user_id BIGINT UNIQUE NOT NULL FK`. Created lazily on first preference write. | Surrogate PK supports future cross-references and audit triggers without rewriting FKs. Lazy creation avoids 20k useless rows from `/start`. | Composite/natural PK on `user_id`. |
| D-003 | 2026-06-23 | `advertisements` keeps the rich schema: media types, button URL, role targeting, persisted impressions and clicks. | Brief lists ads in admin features. CTR analytics needed in V2 monetization decisions. JSON in a tiny table is fine. | Text-only ads, Redis-only analytics. |
| D-004 | 2026-06-23 | Ad targeting uses `target_role` enum (`null`, `user`, `premium`), not `free_users_only` boolean. | Enum extends to V2 premium tiers without schema change. Boolean would require a migration in V2. | `free_users_only` boolean. |
| D-005 | 2026-06-23 | Settings keys use `role_axis` pattern: `free_max_file_size`, `premium_max_file_size`. | Matches the `free_*`, `premium_*` symmetry already used for `*_daily_limit` and `*_download_cooldown_seconds`. | `max_free_file_size`, `max_premium_file_size`. |
| D-006 | 2026-06-23 | `cached_files.usage_count BIGINT`. | A single very popular media at 20k DAU can exceed INT32 in <2 years. | INTEGER. |
| D-007 | 2026-06-23 | `cached_files.last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. | A row only exists after a successful upload; the timestamp is always meaningful. | NULLABLE. |
| D-008 | 2026-06-23 | `downloads.cached_file_id` is **NULLABLE** with `ON DELETE SET NULL`. | Allows cache eviction without destroying history. History row degrades to "view-only"; resend falls back to a new job. Matches the documented stale-resend flow. | NOT NULL with RESTRICT (impossible to nullify, contradicts the eviction story). |
| D-009 | 2026-06-23 | A `job_waiters` table tracks multi-user fan-out durably. | Redis-only fan-out loses State on restart, silently failing late waiters. A 2-column table costs nothing and is consistent with Principle 4.2.7. | Redis-only pub-sub. |
| D-010 | 2026-06-23 | Ad delivery uses **post-increment** modulo. `if (total_downloads_after_increment % show_every_n_downloads == 0) show_ad`. | Means: every Nth completed download triggers an ad. Avoids the "first download always shows an ad" surprise. | Pre-increment. |
| D-011 | 2026-06-23 | `media_metadata.metadata_json` is updated via `COALESCE` merge, not blind overwrite. | A cheaper extraction must never clobber a richer prior one. | Blind overwrite. |
| D-012 | 2026-06-23 | `users.daily_download_count` is reset **lazily** at request time, keyed by `daily_download_count_reset_date`. | Avoids a 300k-row UPDATE batch at midnight UTC. Hot path is unchanged. | Nightly batch UPDATE. |
| D-013 | 2026-06-23 | `jobs.id` is **UUIDv7** (time-ordered). Generated in application code; PG `gen_random_uuid()` is UUIDv4 and unsuitable for the write rate. | Sequential UUIDs prevent B-tree page splits and index bloat at 18M rows/year. External-visibility property is preserved. | UUIDv4. |
| D-014 | 2026-06-23 | A Redis read-through cache fronts `users` lookups, TTL 30 s, keyed by `telegram_id`. Invalidated on user write. | Hot path runs on every incoming update. Without this, Postgres carries millions of reads/day pointlessly. | Direct PG read on every update. |
| D-015 | 2026-06-23 | `downloads` is created as a **monthly RANGE-partitioned** table from day one, with the next 12 partitions pre-created. | Retrofitting partitioning at 50M rows is painful. Up-front cost is one migration. | Plain table, partition later. |
| D-016 | 2026-06-23 | `jobs` and `error_logs` are also monthly RANGE-partitioned from day one. | Same reasoning as D-015. | Plain table, partition later. |
| D-017 | 2026-06-23 | Add `error_log_retention_days` to `settings` seed (default `90`). | The schema claimed retention was configurable; without a seed key, it wasn't. | Hard-code retention. |
| D-018 | 2026-06-23 | Add composite index `ix_ads_active_priority_role (is_active, priority DESC, target_role)`. | Matches the V1 ad-selection query exactly. | No composite. |
| D-019 | 2026-06-23 | API is versioned via URL prefix from V1: `/v1/health`, `/v1/admin/*`. | Cheapest possible V3+ migration story. | Header-based versioning, no version. |
| D-020 | 2026-06-23 | PgBouncer is part of the standard deployment, not deferred to Phase 2. | At three processes × pool 10 + overflow 20, PG default `max_connections=100` is already at risk. Better cheap and present than absent. | Defer to scale issue. |
| D-021 | 2026-06-23 | All worker types share one `queue:jobs` priority queue, distinguished by a `worker_kind` column on `jobs`. | Single queue keeps fan-out and dead-letter logic simple. `worker_kind` allows specialized workers (V6 multi-engine) without forking the queue. | One queue per worker kind. |
| D-022 | 2026-06-23 | Domain-level locale identifiers use IETF BCP-47 (`en`, `ar`, `ru`, `pt-BR`). | Standard, Telegram-compatible, extends to regional variants in V2 without re-parsing. | ISO 639-1 only. |
| D-023 | 2026-06-23 | UUIDv7 generation lives in `core/uuid7.py` as a pure helper. No external lib in V1. | Avoids a dependency for a 40-line function. | Add `uuid7` PyPI package. |
| D-024 | 2026-06-23 | `notifications_enabled` lives in `user_preferences`, not `users`. | Keeps `users` row narrow on the hot path. Preferences are written rarely; reading them is not on the hot path. | Put it on `users`. |
| D-025 | 2026-06-23 | Per-task timeouts are enforced at the layer that owns the work: handler (5 s response), service (15 s), worker (configurable, default 300 s). | Defense in depth. The handler returns a clean error even if a service hangs. | Single global timeout. |
| D-026 | 2026-06-23 | `DownloaderRegistry` + `DownloaderProtocol` are LOCKED V1 architectural components. V1 ships with one registered provider (`YtdlpProvider`); the abstraction is present from day one. | Owner directive: the system must never be tightly coupled to a single download library. Building the registry now is ~200 LOC; retrofitting it in V6 would touch every service. | Single-provider direct-call until V6. |
| D-027 | 2026-06-23 | Provider failover is opt-in via `provider_failover_enabled` (default `true`). When enabled, the registry tries providers in `priority DESC` order, marking failures as DEGRADED for `provider_cooldown_seconds` and trying the next on retryable failure. | Failover is the only behavior that justifies multiple providers. Without it, a registry is empty ceremony. One toggle gives the operator control. | Always-on failover; no toggle. |
| D-028 | 2026-06-23 | Provider health is tracked in Redis under `provider:health:{name}` plus an in-memory mirror, refreshed by a periodic background task every `provider_health_check_interval_seconds`. | Persistent health survives process restart. In-memory mirror avoids hot-path Redis read. | In-memory only; PG-backed. |
| D-029 | 2026-06-23 | Adding a new provider must require **zero** changes to `services/`, `bot/`, `api/`, `workers/`. Any required change there means the abstraction is wrong and must be fixed first. | This is the contract that gives the abstraction value. Without it the abstraction is a fig leaf. | Permit ad-hoc coupling. |
| D-030 | 2026-06-23 | `PROJECT_PROGRESS.md` is the live implementation-status SSOT. `MASTER_PLAN.md` is the architecture/sprint SSOT. The two are not redundant: the plan is stable, the progress file is mutable. | Splitting "what we are building" from "where we are" keeps the plan from churning. | One combined file. |
| D-031 | 2026-06-23 | Test-first: no task is `[x] Completed` without unit + integration + security + manual + Telegram-bot E2E verification in the categories that apply. Section 25 enumerates the per-category gates; Section 1.8 enforces them. | Validation gates are how the architecture stays sound at scale. A missing test is paid for years later. | "Tests in a follow-up" pattern. |
| D-032 | 2026-06-23 | Production environments are forbidden for testing. Separate test bot token, test PG, test Redis, test queue, test storage are mandatory. `DEPLOY_ENV=test` selects them. A startup assertion refuses to boot if `DEPLOY_ENV=test` is paired with a known-production token fingerprint. | A leaked test broadcast or test ban in production is a public incident. Hard isolation is the only safe rule. | Shared infra with namespacing. |
| D-033 | 2026-06-23 | Six test categories live under `tests/`: `unit`, `integration`, `security`, `performance`, `e2e`, `regression`. Each is a separate pytest collection root with its own CI job. | Reproducible, separately runnable suites. CI can run subsets. | Single tests/ namespace. |
| D-034 | 2026-06-23 | The user simulation framework lives under `tests/simulation/` (not a new top-level directory). It is test infrastructure, but first-class: versioned, reviewed, maintained with production-grade rigor. | The simulator is the only way to validate production readiness without real users. Treating it as throwaway gives weak signal. | New top-level `simulation/` directory. |
| D-035 | 2026-06-23 | Six load levels are LOCKED: L1=10, L2=50, L3=100, L4=500, L5=1000, L6=5000 simulated users. Each produces a versioned, append-only report in `PERFORMANCE_REPORT.md`. | Standardized levels make cross-version reports comparable. | Ad-hoc load tests. |
| D-036 | 2026-06-23 | `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md` are mandatory living documents. Append-only; updated on every PR that runs the matching suite. | Without persistent reports we re-discover the same issues. | Per-PR ephemeral artifacts. |
| D-037 | 2026-06-23 | Human Verification Gates (G-1 through G-8 in Section 25.13) require explicit Owner sign-off in the PR (`Gate <ID> approved`) before merge. The agent stops at the gate. | These are the spots where wrong code is most expensive. | Auto-merge for "low risk." |
| D-038 | 2026-06-23 | Telegram E2E tests use a dedicated sandbox bot (created via @BotFather, separate from production) and a fixed pool of test accounts. The Telegram API is wrapped in `tests/e2e/harness.py`. | Real Telegram API behavior cannot be fully mocked; sandbox bot is the cheapest realism. | Pure mocks. |
| D-039 | 2026-06-23 | Security testing is structured by category (Section 25.9.1 through 25.9.5). Categories may be added but never removed. Every release runs every category. | Locking the category set prevents quiet regressions in security coverage. | Ad-hoc security testing. |
| D-040 | 2026-06-24 | V1 delivers files through a **self-hosted Telegram Bot API server** (2 GB upload cap), selected by a new `BOT_API_BASE_URL` env var (empty = public api.telegram.org, 50 MB). The bot and worker Telegram clients point at it; `max_file_size` (Section 13.4) stays the 2 GiB hard cap. | Owner directive (OQ-11) at Sprint 6 start: large media (HD video, lossless audio) routinely exceeds 50 MB, so the public API cap would make the core flow useless for most content. Base URL is a single env var; the public API remains the fallback. | Public Bot API only (50 MB); chunked/segmented delivery; external file hosts. |
| D-041 | 2026-06-24 | **Per-codec audio** is modeled by extending the `Quality` enum with audio-codec members (`mp3`, `m4a`, `aac`, `ogg`, `opus`, `wav`, `flac`) and adding a descriptive `codec` field to `MediaFormatOption`. The chosen codec is the `quality` value, so the LOCKED `cached_files`/`active_downloads` unique key `(media_id, format, quality)` distinguishes codecs with no schema change. Audio targets are a fixed catalog offered whenever the media has any audio stream; native containers are remuxed, the rest are FFmpeg transcodes. | Owner carry-in: users want explicit MP3/M4A/Opus/etc. Encoding the codec in `quality` reuses the locked cache key (one cached file per codec) and keeps the enum additive (Section 9.4). | A parallel `audio_codec` column (schema change to the locked unique key); a separate `AudioCodec` enum carried out-of-band from the cache key (risks collisions). |
| D-042 | 2026-06-24 | **(Sprint 9.5)** Ads v2 delivers content in two modes behind `AdSenderProtocol`: `fields` (Sprint 9, programmatic type+text+`file_id`+buttons) and `copy` (store `(storage_chat_id, storage_message_id)` in a bot-owned storage channel; deliver via `bot.copy_message`). Buttons are first-class in a new `ad_buttons` table (copyMessage drops inline keyboards, so they are re-attached on send and stay click-trackable in both modes). | Lets the Owner reuse a complete rich Telegram message (any media/album, caption, formatting, multiple buttons) with no re-upload and no raw-byte storage — the Owner's recommended architecture. A new sender method + table, not a refactor of the Sprint 9 selection core. No new Python dependency (`copy_message` is on the aiogram `Bot`). | Rebuilding every Telegram message variant field-by-field (brittle); storing raw media bytes (storage/upload cost). |
| D-043 | 2026-06-24 | **(Sprint 9.5)** Audience targeting becomes first-class via `advertisements.audience_mode` (`all`/`include`/`exclude`) + an `ad_audience_rules` table (`effect`, `dimension` ∈ role/plan/language/user_id/segment/country, `value`) + reusable `audience_segments`/`audience_segment_members`. Within a dimension values OR, across dimensions AND. The Sprint 9 `target_role` (D-004) is retained as a denormalized fast pre-filter for one deprecation window and backfilled into an equivalent `include role=…` rule. | The Sprint 9 single `target_role` cannot express "Arabic users only", "user IDs [..]", "all except premium", or reusable segments. A rule table makes targeting (and future monetization segmentation) first-class and additive; the Owner/premium exemptions (16.7) are preserved and become overridable by an explicit include rule. | Boolean flags per audience (combinatorial explosion); a single JSON blob (not queryable/indexable for segment membership). Supersedes D-004 additively. |
| D-044 | 2026-06-24 | **(Sprint 9.5)** Persistent ads are positioned by an `advertisements.placement` enum (`post_download` [compat], `video_delivery`, `audio_delivery`, `quality_select`, `home`, `history`, `broadcast`) plus one `settings` toggle per placement (Section 13.6). New-placement toggles default **OFF** (opt-in); the compat placement keeps Sprint 9 behavior. Selection narrows by an additive `ix_ads_placement_active_priority(placement, is_active, priority DESC)` index. | Placement is just another filter dimension on the existing `AdService` selection; per-placement toggles prevent surprise/spammy ads and let placements ship incrementally and be measured. The LOCKED `ix_ads_active_priority_role` is retained (additive index, no drop). | A single global "show persistent ads" flag (no per-surface control); hard-coding placements in handlers (business logic in handlers, forbidden by 1.5.1). |
| D-046 | 2026-06-25 | **(#28/#29)** The download selects the **exact `format_id`** that was offered for the chosen tier (looked up from `media.formats` at download time), instead of re-deriving via a height cap. The height-capped selector is the fallback only, and its final branch is now also height-capped (the uncapped `/best` is removed) so a download can never exceed the selected tier. | Guarantees the delivered resolution **and** size match the displayed option: the same format whose size was shown is the one downloaded. The previous `bestvideo[height<=H]…/best` could resolve to a different (or, via the uncapped fallback, higher) format than displayed, causing 480p→720p mismatches and wrong size estimates. `analyze_by_media_id` serves `formats` (with `provider_format_id`) from the metadata cache, so the id is available at download time. | Threading the format_id through the signed callback (exceeds 64-byte limit); a stricter height-range filter (still mismatches nearest-tier display snapping). |
| D-047 | 2026-06-25 | **(#31)** Ad buttons render as Telegram **URL buttons** (open the destination directly), not callback buttons. | Owner UX directive: pressing Open must launch the link immediately with no copy/paste step. Trade-off: a URL button fires no callback, so per-button click counts are not incremented for direct-open buttons (impressions still are). `AdButtonSpec` retains an optional `callback_data` so a future **redirect-based tracked** button (which both opens and counts) can be added without a refactor — the natural home for click analytics and the #32 quota-unlock flow. | Callback buttons (track clicks, but require an extra tap / message — rejected by the Owner); `answerCallbackQuery(url=…)` (Telegram restricts it to game/`t.me` links). |
| D-048 | 2026-06-25 | **(#30)** The post-download ad is sent as a **reply to the delivered media message** (`reply_to_message_id`), so it sits visually attached directly under the file. `FileSenderProtocol.upload`/`send_cached` now return the delivered message id. | Owner UX directive: the ad must feel attached to the media, not a standalone message elsewhere. Threading the delivered message id is additive (optional param, defaults preserve prior behavior). | Sending the ad as an independent message (the prior behavior — appears below but not threaded). |
| D-045 | 2026-06-24 | **(Sprint 9.5)** Ad broadcasts reuse the Sprint 8 `broadcasts` plumbing via a nullable `broadcasts.advertisement_id` FK (→`advertisements` ON DELETE SET NULL); `BroadcastWorker` gains one branch that delivers a stored ad via `copy_message` instead of plain text, reusing the chunked fan-out and `total_sent`/`total_failed` counters as the broadcast delivery-count analytic. Richer per-event/time-series analytics are an additive, monthly-partitioned `ad_events` table (last/optional task) that never touches the counter hot path. Scheduling (`scheduled_at` + due-poller) is specified but deferred to a later sprint. | Avoids forking a second broadcast subsystem; counters already exist. `ad_events` keeps the hot-path increments cheap while leaving room for analytics. | A separate ad-broadcast pipeline (duplicate logic); event rows on the hot path (write amplification); building scheduling before the core ad system is proven. |
| D-049 | 2026-06-25 | **(Sprint 10)** The `api/` HTTP process is realized with **FastAPI 0.115.6 + uvicorn 0.34.0** (the LOCKED Section 6.1 choice, EP-8), serving **only** the three public endpoints `/v1/health`, `/v1/ready`, `/v1/metrics` this sprint. The admin API surface (Task 8.3) and `ADMIN_API_KEY` reconciliation (§13.2 vs §20.3) remain deferred. Infrastructure imports stay confined to `api/main.py` (the composition root); `api/app.py` and `api/readiness.py` depend only on `core`/stdlib and receive probes as injected callables. | Sprint 10 requires the metrics/health/readiness endpoints, which need an HTTP server; FastAPI/uvicorn is the architecturally-locked layer. The three endpoints are public (auth `none`/network ACL), so standing them up does **not** require resolving the deferred `ADMIN_API_KEY` question. Owner-approved 2026-06-25. | aiohttp-only server (deviates from the locked FastAPI row); deferring the HTTP tasks with 8.3 (blocks observability). |
| D-050 | 2026-06-25 | **(Sprint 10)** `/v1/metrics` uses **prometheus-client 0.21.1** (Section 15.3 metric set in `core/metrics.py`). V1 metric model: counters/histograms are incremented in-process; the api process serves the single LOCKED `/v1/metrics`, exposing its own registry (default process/python collectors + histograms) plus four **live gauges** (`queue_depth`, `active_workers`, `db_pool_in_use`, `redis_connected`) refreshed from Redis/DB at scrape time, so they are accurate regardless of which process did the work. Cross-process **counter** aggregation uses prometheus-client's standard `PROMETHEUS_MULTIPROC_DIR` multiprocess mode when that env var is present (shared volume on the V1 single host); when unset (dev/tests) the default registry is rendered. | A proper registry beats hand-rolling exposition text. Live gauges give honest queue/worker/DB/Redis signal at the locked single endpoint; multiprocess mode is the canonical prometheus-client answer for several processes on one host, and degrades cleanly to single-process for dev. `PROMETHEUS_MULTIPROC_DIR` is prometheus-client's own mechanism, not a new app config key (Section 13). | Hand-rolled exposition (more code, no ecosystem tooling); per-process scrape endpoints (violates the single LOCKED `/v1/metrics` in §20.2); ignoring cross-process aggregation (counters always read ~0 at the endpoint). |
| D-054 | 2026-06-26 | **(Owner feedback)** `/unban` (and `POST /v1/admin/users/{id}/unban`) now **clears** the ban fields — `is_banned=false`, `banned_at=NULL`, `ban_reason=NULL` — rather than retaining `banned_at`/`ban_reason` as an audit trail (the Sprint 8 behavior). | Owner directive 2026-06-26: a non-banned user must never display a stale ban reason (`/userinfo` and the admin API surfaced `ban_reason` after an unban). Durable ban history is the job of the V3 audit log (§19.3 `add_admin_audit_log`), not a live column on `users`. Supersedes the "preserve audit fields" note in `UserService.unban`. | Keeping `ban_reason` after unban (the prior behavior — rejected by the Owner as confusing); moving the reason to `error_logs` on unban (overloads a diagnostics table). |
| D-055 | 2026-06-27 | **(Sprint 9.6, F-2 — Owner-approved + signed off 2026-06-27; D-055–D-059 final.)** A **unified audience engine** shared by ads + broadcasts: new `audience_expressions` (`mode`) + `audience_rules` (`effect`/`dimension`/`value`) tables, referenced by a nullable `audience_expression_id` FK on `advertisements` and `broadcasts` (migration `202606270001`, additive). Premium is the `plan` dimension (an attribute, never a role). The Sprint-9.5 per-viewer **Python matcher** (`AudienceService.evaluate_audience`) is joined by a new **set-based SQL compiler** (`infrastructure.database.audience_query.compile_audience_predicate`) for broadcast count/paging; the two share one semantics, pinned by a shared truth-table test (invariant #17). Broadcast default guards (exclude banned always; staff unless explicitly included) live in `broadcast_audience_predicate`, keeping the core identical to the matcher. `ad_audience_rules` + broadcast `target_role`/`target_language` are retained + dual-read for one window; existing ad rules are backfilled into equivalent expressions. | The single `target_role` (and broadcasts' role+language) cannot express premium/segment/"all except X"; one rule model serves ads, broadcasts, and future messaging features (Owner directive 2026-06-27). Two evaluators (one Python, one SQL) are required because ad delivery judges one viewer while broadcasts must count/page thousands; a shared truth table prevents drift. | Per-feature audience tables (duplication); a JSON blob (not queryable for segments); per-user Python eval for broadcasts (does not scale); premium as a role (rejected by the Owner). |
| D-056 | 2026-06-27 | **(Sprint 9.6, F-2)** **Multi-placement** ads: a one-to-many `ad_placements(advertisement_id, placement)` join table (migration `202606270002`) lets an ad occupy several placements at once. `AdRepository.list_active_for_placement` dual-reads — a placement row wins; legacy ads with no rows fall back to the scalar `advertisements.placement` column (retained one window, backfilled one row per ad). Per-placement §13.6 toggles are unchanged. | Owner #12: one ad should serve several surfaces without duplicate rows. A join table is queryable/indexable and additive; dual-read keeps the LOCKED Sprint-9.5 selection working through the deprecation window (the D-043/D-044 pattern). | A comma-list/array column (not indexable/FK-clean); keeping single placement (rejected by the Owner). |
| D-057 | 2026-06-27 | **(Sprint 9.6, F-2+F-3)** One Owner-only aiogram FSM **compose wizard** drives both Ad and Broadcast creation: config-first (Type → Audience → Placement[ads] → Settings) then content-last → Preview → Save. Two co-equal content methods (Wizard-composed text and Copy-mode forward/send), both retained. The **Preview is an edit hub** (Edit ▸ jumps to a section and returns, never restarts). State is a JSON-serializable `WizardState` (future draft-resume is additive, Owner #15). Signed ≤64-byte `w` callbacks; drives existing services + the D-055/D-056/D-058 surfaces only (no business logic in handlers). Realizes the reserved EP-22 (panel) and EP-23 (rich builder) as one flow. | A single wizard avoids forking Ad/Broadcast flows; config-first/content-last + the edit hub match the Owner's spec (#4/#10); copy-mode preserves native Telegram content. | Separate wizards (duplication); restart-on-edit (rejected, Owner #10); `key=value` commands as the only builder (rejected). |
| D-058 | 2026-06-27 | **(Sprint 9.6, F-2)** **Internal ad metadata**: nullable `advertisements.internal_name` (VARCHAR 120) + `internal_notes` (TEXT) (migration `202606270002`), admin-only and **never on any delivery path**. Settable in the wizard + `/ad_create`/`/ad_edit`. | Owner #11: managing hundreds of campaigns needs admin-facing labels/notes that users never see. Two nullable columns are the minimal additive change; the title stays the user-visible field. | A separate metadata table (overkill); reusing `title` (conflates user-visible title with an internal label — rejected). |
| D-059 | 2026-06-27 | **(Sprint 9.6, F-2)** The compose wizard is a **registry-driven engine** over a tuple of step objects (`bot/panel/wizard.py`: `step_id`/`title`/`applies_to`/validators) — the engine computes the applicable next/prev step (Broadcast auto-skips Placement), runs §4.9 validation that names the offending step (for the edit-hub jump), and never hardcodes transitions. Audience **dimensions** and **placements** are likewise registries (`AUDIENCE_OPTIONS`/`PLACEMENT_OPTIONS`). | Owner #10/#11/#13: future steps (Scheduling, Country, A/B, Expiration) and new audience dimensions/placements must register without rewriting the wizard. A step/option registry mirrors the existing panel `SECTIONS`/`SUBMENUS` pattern. | Hardcoded linear FSM transitions (every feature edits the flow — rejected); per-wizard bespoke flows (duplication). |
| D-053 | 2026-06-25 | **(Task 9.5.10)** Scheduling is a nullable `scheduled_at` timestamp on **both** `broadcasts` and `advertisements` (migration `202606250002`, `down_revision=202606250001`). **Broadcasts** are scheduled via a **due-poller**: `BroadcastRepository.get_next_pending(now)` returns the oldest pending row whose `scheduled_at` is NULL or `<= now`, so the existing `BroadcastWorker` poll loop (already running on an idle interval) *is* the poller — no new worker. A partial index `ix_broadcasts_scheduled` covers the pending+scheduled scan. **Ads** use `scheduled_at` as a "starts showing at" gate, checked in `AdService.maybe_show` (Python, over the small per-placement candidate list) — a future-scheduled ad is skipped until due. NULL on either column = prior behavior (immediate / always-eligible). Command surface: `--at <ISO-8601>` on `/broadcast` and `/ad_broadcast`; `scheduled_at=<ISO>` (or `none` to clear) on `/ad_create` / `/ad_edit`. A shared `core.timeparse.parse_iso_datetime` parses the input (UTC, trailing `Z` and offsets accepted). | "Add scheduled_at + a due-poller so ads/broadcasts can be scheduled" with minimal new surface: reusing the BroadcastWorker's existing poll loop avoids a second worker/process; a gate in `maybe_show` avoids changing the ad selection SQL/protocol (and its fakes). Both columns nullable + additive keeps it back-compatible. The partial index keeps the due scan cheap as pending volume grows. | A dedicated scheduler worker/process (more infrastructure than a scaffold needs); a Redis ZSET of due times (duplicates the durable table's ordering); pushing scheduled broadcasts onto the job queue (the queue has no `worker_kind` dispatch — would corrupt the download path, per the §16.8 deviation note); gating ads via a `now` predicate in the repo (ripples through the protocol + every fake). |
| D-052 | 2026-06-25 | **(Task 9.5.9)** The `ad_events` per-event analytics table (impressions/clicks, monthly RANGE-partitioned like `error_logs`) is written **off the delivery hot path** by an injected `AdEventRecorderProtocol`. The port's `record_impression`/`record_click` are **synchronous, non-blocking** (they schedule a background write and return), so an `ad_events` INSERT never adds latency to ad delivery; the `advertisements`/`ad_buttons` counters stay the source of truth (D-045). The concrete `AdEventRecorder` (infrastructure) is a process singleton owning its **own** session factory — it writes on a fresh session in a fire-and-forget `asyncio` task, swallowing+logging failures (analytics is best-effort). `ad_events` is created by migration `202606250001` (`down_revision=202606240001`) with **no FKs** (cheap writes; a deleted ad's rows age out with their partition). It is added to `RUNTIME_PARTITIONED_TABLES` (not the baseline-migration `PARTITIONED_TABLES`, which must stay frozen) so the cleanup worker keeps its partitions rolling; it has no retention settings key, so partitions are not auto-dropped (acceptable for V1 analytics; a key can be added later). | "Must not slow delivery": a synchronous same-session INSERT per impression would be a hot-path change (D-045 forbids it). A sync-signature port + fire-and-forget adapter enforces non-blocking at the type level and keeps the recorder out of the request session's unit of work. No FKs avoids write contention with ad CRUD. The frozen baseline `PARTITIONED_TABLES` keeps the already-merged `202606230001` migration correct on fresh databases. | Same-session synchronous INSERT (slows delivery, hot-path change); a Redis-buffered queue + a new drain worker (more infrastructure for a scaffold); FK to `advertisements` (write contention + blocks ad delete); adding `ad_events` to `PARTITIONED_TABLES` (breaks the baseline migration's seed on a fresh DB). |
| D-060 | 2026-06-27 | **(Sprint 11, Task 11.1)** Add `DEPLOY_ENV` (`development`/`test`/`production`, default `development`) and `PROD_BOT_TOKEN_FINGERPRINT` (SHA-256 hex of the production bot token) to the LOCKED §13.2 set. A self-enforcing `Settings` model-validator (`_enforce_environment_safety`) runs an **extensible registry** of environment safety rules (`core/environment.py::ENVIRONMENT_SAFETY_RULES`); the first rule refuses to boot when `DEPLOY_ENV=test` and `sha256(BOT_TOKEN)==PROD_BOT_TOKEN_FINGERPRINT`, realizing D-032's isolation guarantee. Violations raise `EnvironmentMisconfiguredError` (a non-`ValueError` so it propagates out of `Settings()` unchanged). `token_fingerprint` lives in `core/security.py`. | D-032 mandated `DEPLOY_ENV=test` + a production-fingerprint boot assertion but neither key was ever added to §13.2. A one-way hash lets a test deployment detect the production token without storing a secret (Hard Rule 6). The registry (not a hardcoded check) lets future isolation rules — test must not use a production DB/Redis/storage/webhook — drop in without changing the startup architecture (Owner directive). The model-validator makes the guard self-enforcing across all current and future entry points. | Comparing raw tokens (stores a secret); comparing bot-id prefixes only (weaker); an explicit call in each `main()` (forgettable); a single hardcoded fingerprint check (not extensible). |
| D-051 | 2026-06-25 | **(Task 8.3)** The deferred `/v1/admin/*` HTTP API is implemented on the existing Sprint-10 FastAPI process, gated by a new `ADMIN_API_KEY` env var **added to the LOCKED §13.2 set** — resolving the conflict where §20.3 named the key but §13.2 omitted it (Owner-approved 2026-06-25). All 11 §20.2 endpoints are exposed. The key travels in the `X-API-Key` header (constant-time compare). When the key is **unset** the admin router is not mounted (paths 404 — "silently ignored", mirroring the bot's owner-only-commands behavior); when set, a missing/wrong key → 401. With a single shared key there is no per-request HTTP identity in V1, so §20.2's "(owner only)" markers collapse to "valid-key-only" (the key is the owner's; JWT identity is V3). Routes carry no business logic: they delegate to `UserService` (stats/users/ban/unban), `SettingsService` (settings list/update), `QueueService` (queue summary), and a new lightweight `AdminService` (jobs listing + error-log browse — the two reads no existing service owned). `AdminService` depends on narrow read protocols (`JobReadRepository`/`ErrorReadRepository`), so it avoids the heavy `JobService` transport deps; new repo reads `JobRepository.list_recent` + `ErrorLogRepository.list_recent`. `api/routes/admin.py` imports services/domain/core only (import-linter clean); the composition root `api/main.py` wires the concretes. | The Owner approved the env var + the full surface (the three §13.2-vs-§20.3 reconciliation questions). Reusing the Sprint-10 api process avoids a second HTTP server; delegating to existing services keeps the routes thin and honors "no business logic in handlers" (§1.5.1). `AdminService` is justified by the two reads with no owner; narrow protocols avoid a new abstraction's blast radius. 404-when-disabled keeps the surface invisible until configured. | A whole new admin process (duplicate HTTP stack); putting jobs/error queries in `JobService` (drags in file-sender/notifier deps); adding the read methods to the broad shared repo protocols (forces every fake to implement them); enforcing per-role HTTP auth in V1 (no identity model until V3 JWT). |
| D-061 | 2026-07-01 | **(Sprint 11.5)** Multi-language UI is pulled forward from V2 into V1 at explicit Owner direction. The user's UI locale reuses the existing `users.language` column (BCP-47, D-022) exclusively; `user_preferences.preferred_language` (EP-3) stays reserved/unused. `AuthMiddleware` no longer seeds `users.language` from Telegram's auto-detected `language_code` — a new user's row is created with a new `Settings.default_locale` (env `DEFAULT_LOCALE`, default `"en"`) instead, and the field is thereafter only ever written by an explicit in-bot language pick (`UserService.set_language`). `DEFAULT_LOCALE` is a deploy-time rendering knob, the same category as the existing `BOT_PARSE_MODE` — not a per-user runtime tunable — so it lives in `core/config.py`/§13.2, not the `settings` table. No migration: `users.language` already exists and is nullable. | Telegram's auto-detected `language_code` is not restricted to the languages this bot actually catalogs, so treating it as a trustworthy UI locale would silently mis-set the field for most non-English clients. `user_preferences.preferred_language` was reserved for "V2 i18n" under a design that assumed a `user_preferences`-based settings model; the simpler path the Owner approved reuses a column that already existed and was already read by ad audience targeting (`dimension='language'`), so no schema change was needed at all. | Seeding from `tg_user.language_code` (untrustworthy); using `user_preferences.preferred_language` per the original EP-3 sketch (would need a preferences-row-on-first-write dance for a value needed on literally every update); a hardcoded `"en"` literal instead of an env var (fails the "no hardcoded default" requirement). |
| D-062 | 2026-07-01 | **(Sprint 11.5)** Supported languages are **discovered from `core/locales/*.json` at startup** (`core/i18n.py::configure`), never stored in the `settings` table — adding a language is "drop in one file with `_meta.enabled: true`," no DB/code change. Every catalog carries a standardized `_meta` block (`code`/`native_name`/`direction` ∈ `{ltr, rtl}`/`enabled`/`version`); `_` is reserved for metadata only, and any other underscore-prefixed top-level key fails validation. The configured default locale (`DEFAULT_LOCALE`, D-061) is the **reference catalog**: every other discovered locale's keys must be a subset of the default's (an orphaned/typo'd key fails startup, naming the offending key), while the default itself must contain every key the codebase uses. `translate(key, locale, **kwargs)` falls back non-default → default → the raw key string on a miss (each fallback logged), and catches a bad `.format()` placeholder rather than raising (Hard Rule 10) — no caller-facing crash path exists. Flat, dot-named keys (`"errors.file_too_large"`) in plain JSON, loaded via `pathlib`/`json`, no new Python dependency. | Filesystem discovery (rather than a `settings`-table list) means the Owner's explicit ask — "adding a language is only a translation file" — is literally true, with zero coupling to a DB write. The default-locale-as-reference-catalog invariant catches a typo'd key in a non-default catalog at deploy time instead of a silent runtime fallback discovered by a user report. Flat JSON over gettext/Babel/`.po` files matches D-023's precedent (no new dependency where a stdlib-only solution suffices) and keeps lookup a single dict access. | Storing the supported-language list in `settings` (couples a filesystem asset to a DB row, needs a migration to seed); nested/namespaced JSON objects (lookup requires a path-walk, no benefit over flat keys); gettext/Babel (new dependency, `.po`/`.mo` tooling this project doesn't otherwise need); silently ignoring orphaned keys (masks a typo until a user hits it in the non-default locale). |
| D-063 | 2026-07-01 | **(Sprint 11.5)** Language is changed via a **permanent button only** — no first-contact picker gate (a new user starts in `DEFAULT_LOCALE` immediately) and no `/language` command (two rounds of Owner simplification superseding the original plan). Regular users get a "🌐 Change Language" inline button attached to the `/start` screen (this bot has no persistent reply-keyboard menu; this is the closest existing equivalent — flagged as an interpretation call); Owner/Moderator get a new "🌐 Language" section in the existing admin-panel `SECTIONS` registry. Both entry points render the same picker and share one pick-persistence path (`UserService.set_language` + a new signed callback action `l`, parsed by `bot/callbacks/factory.py::CallbackSigner`); an empty-string sentinel payload means "open the picker," a real code means "apply this pick." A pick takes effect immediately (confirmation renders in the newly-picked locale, not the pre-pick one) with no restart, and `LocaleMiddleware` (new; runs after `AuthMiddleware`, before `ThrottleMiddleware`) re-resolves `data["locale"]` fresh on every update — a stored locale that becomes disabled silently falls back to the default and **recovers automatically**, with no data migration, the moment the locale is re-enabled. Because one in-flight download can have several waiters (`job_waiters`) with different languages, `DownloadService._notify_waiters`/`JobService._try_deliver_cached` each resolve the **recipient's own** locale fresh per delivery rather than reusing one "job locale." This realizes EP-3 and EP-11 (both reserved for V2) ahead of schedule — though EP-3's literal `user_preferences.preferred_language` column is still untouched (D-061); the mechanism took the simpler `users.language` path instead, so EP-3 is superseded rather than literally implemented. | Owner directive, delivered in two explicit simplification passes during this sprint's design review: first replacing a first-contact gate with an always-English default, then dropping the `/language` command in favor of a button-only surface. Sharing one signed action + one apply path across both entry points avoids duplicating the picker or the persistence logic. Per-recipient fan-out locale resolution is required correctness, not an enhancement — a job's waiters are not guaranteed to share a language. | A first-run forced picker (rejected — Owner #1/#2); a `/language` command (initially approved, then explicitly dropped — Owner simplification #2); writing a fallback locale back to `users.language` on read (would prevent automatic recovery when a locale is re-enabled); reusing one job-level locale for every waiter in a fan-out (wrong whenever waiters differ in language). |
| D-064 | 2026-07-01 | **(Sprint 11.5)** `UserFacingError` gains a `translation_key` property (`f"errors.{self.error_type.value}"`) instead of a generic `params: dict[str, Any]` on `AppError`. Every `ErrorType` member maps 1:1 to a catalog key; the one `except UserFacingError` catch site (`bot/handlers/download.py`) calls `translate(exc.translation_key, locale)` with no dynamic interpolation. | Traced every `UserFacingError` raise site before deciding: none of the four subclasses reachable from that catch site (`PermissionDeniedError`, `MaintenanceModeError`, `DailyLimitExceededError`, `CooldownActiveError`) ever needed a dynamic value in their user-facing message. Adding a `params` dict "for future use" with no current caller would be dead code the moment it shipped (Hard Rule 1.5.6 — no unused future-proofing). | A generic `params: dict[str, Any] | None` on `AppError` (would ship unused); a `to_translation_kwargs()` method per subclass (same problem, more surface). |
| D-065 | 2026-07-03 | Security bump: `fastapi` 0.115.6 → **0.139.0**; `starlette` pinned explicitly at **1.3.1** (previously transitive-only at 0.41.3). Owner-approved same day. | A Sprint-11 security re-run's `pip-audit` gate found **7 known vulnerabilities** in starlette 0.41.3 (PYSEC-2026-161/248/249, GHSA-2c2j-9gv5-cj73, GHSA-7f5h-v6xp-fcq8, GHSA-wqp7-x3pw-xc5r, GHSA-x746-7m8f-x49c); full remediation requires starlette 1.3.1, which requires a newer FastAPI. The API is the one internet-facing HTTP surface (prod compose publishes only the api port), so launching on a known-vulnerable parser was unacceptable. Explicit starlette pin = durable security floor instead of re-inheriting whatever FastAPI resolves. Gates after bump: unit+security suites green, `pip check` clean, `pip-audit` clean, mypy --strict clean (164 app files), import-linter 7/7, bandit 0. | Staying on 0.115.6 (ships known CVEs at launch); bumping starlette alone to 0.49.x (fixes only 2 of 7); leaving starlette transitive (pin drifts with future FastAPI changes). |
| D-066 | 2026-07-05 | **(Sprint 13)** Referral system pulled forward from V5 into V1 at Owner direction, realizing EP-1. `users.referred_by_id` (self-FK, `ON DELETE SET NULL`) + `referral_code` (unique) + `referral_bonus_downloads`; a new `referrals` table (`referrer_id`, `referred_id` unique, `reward_granted`, `created_at`). Reward model: a successful referral grants `referral_reward_downloads` (a `settings` key, default 5) as a **permanent, stacking** bonus to **both** the referrer and the new user — added on top of `free_daily_limit`/`premium_daily_limit`, never expiring, never reset by the daily-counter lazy-reset (D-012). `ReferralService` is framework-free (depends on repository protocols + a narrow `SettingsReader` protocol only); `/start` parses a `?start=ref_<CODE>` deep link, applies the referral, and best-effort-notifies the referrer (a `TelegramAPIError`, e.g. the referrer blocked the bot, is swallowed and logged — never surfaces to the new user). | Owner directive to ship growth features in V1 rather than wait for V5. A dedicated `referrals` table (not just a counter column, as EP-1 originally sketched) makes invite history and per-referral reward status queryable — needed for the admin leaderboard, which a running total alone cannot support. Stacking (not one-time or percentage) bonuses keep the reward rule trivial to reason about and audit. Best-effort referrer notification matches the existing pattern for any Telegram send that can legitimately fail (a blocked bot is not an application error). | A single `users.referral_count` column (can't support a leaderboard or per-invite reward audit); one-time (non-stacking) bonuses (weaker growth incentive, and Owner asked for permanent stacking); crashing `/start` if the referrer notification fails (would break onboarding for an unrelated Telegram-side condition). |
| D-067 | 2026-07-05 | **(Sprint 13)** Admin panel visual overhaul via `bot/panel/ui.py`, a pure-presentation primitives module (`header`/`metric`/`progress_bar`/`sparkline`/`card`/`table`/`badge`/`footer`/etc., no I/O, no service calls). Every icon is a semantic code routed through a single `emoji(code)` function backed by an empty `CUSTOM_EMOJI_IDS: dict[str, str]` map; today every code resolves to its plain-Unicode fallback, but filling that map (once the bot has a **Fragment-purchased username**, a Telegram Bot-API precondition for `<tg-emoji>` custom-emoji entities that cannot be met from a coding session) switches the **entire panel** to animated custom emoji with zero screen-level changes. | The Owner asked for animated panel emoji. Telegram's Bot API restricts animated inline custom emoji to bots with a paid Fragment username — an account-level purchase, not obtainable programmatically. Presented three options (ship Unicode only; build animation-ready and ship Unicode; wait for the Fragment username first); Owner chose the animation-ready path so no rework is needed later. Routing every icon through one function (rather than inlining emoji literals across ~15 screens) is what makes the later flip a one-line data change instead of a re-touch of every screen. | Hardcoding Unicode emoji per-screen (the later Fragment-username flip would require re-touching every screen); blocking the whole sprint on the Owner first obtaining a Fragment username (unnecessary — the UI/UX and every other feature don't depend on it); a runtime feature-flag config key instead of a plain code map (over-engineered for a mapping that changes rarely and only at deploy time). |
| D-068 | 2026-07-05 | **(Sprint 13)** Admin-editable message templates (9 keys: welcome, help, download started/complete/failed, daily-limit-reached, banned, cooldown, maintenance) are stored in a new `message_templates` table (PK `key`+`locale`) and served through a **transparent override hook** added to `core/i18n.py::translate()` — it now consults an in-memory `(locale, key) → content` override map *before* falling through to the on-disk catalog. `TemplateService` (loads the override map once at startup via `.load()`, re-syncs it on every edit/reset) is wired as a **process singleton** — the one deliberate exception to this sprint's otherwise-per-request-session service pattern — via a new session-owning `MessageTemplateStore` adapter (mirrors `AdEventRecorder`'s D-052 pattern: each operation opens its own short-lived, committed session). | A transparent hook means every existing and future `translate(key, locale, **kwargs)` call site gets template-override support for free — no caller ever needs to know whether a given key is customized. A process singleton is correct here (unlike the sprint's other new services) because the override map is read on every single `translate()` call across every request; re-querying the DB per call would add a query to the hottest code path in the entire bot. `catalog_template()` (a second, override-blind lookup) lets the admin edit screen preview the shipped default even while a custom override is active. | A per-request DB lookup inside `translate()` (adds a query to literally every user-facing message send — unacceptable on the hottest path in the bot); a separate `translate_with_override()` function (callers would have to remember to use it; defeats the "transparent" goal); storing overrides only in `settings` (that table is a flat key/value store; templates need locale-scoping and a reset-to-default operation, better modeled by a dedicated table). |
| D-069 | 2026-07-05 | **(Sprint 13)** Two Sprint-13 features need to run **outside** the request-bound session (a multi-minute Telegram-API health sweep over every user; a template cache read on every `translate()` call) without breaking the "services never import aiogram" / "infrastructure is a leaf" import-linter contracts (§8). Both are solved the same way: the aiogram-specific piece lives in a small **bot-layer adapter** (`bot/chat_prober.py::AiogramChatProber`, mapping `TelegramForbiddenError`→blocked and a "not found" `TelegramBadRequest`→deleted onto the framework-free `ProbeOutcome` enum that `services/user_health.py::UserHealthChecker` actually depends on), while the **session-owning** piece lives in `infrastructure` (`user_health_store.py::UserHealthStoreAdapter`, `message_template_store.py::MessageTemplateStore`), satisfying the service-layer's `UserHealthStore`/`MessageTemplateStore` protocols **structurally** — `infrastructure` never imports `services`, it just happens to implement the same method shapes. | `services/user_health.py` needed to run a long, chunked, delayed sweep with a progress callback, which cannot share the request's single transaction; but the only thing that knows how to talk to Telegram (`Bot.get_chat`, and which aiogram exception means what) is aiogram, which `services/` may never import (§8). Splitting the adapter across the two layers — aiogram mapping in `bot/`, session ownership in `infrastructure/` — satisfies both constraints simultaneously without weakening either import-linter contract, verified green (7/7 contracts kept) at every commit this sprint. | Importing aiogram into `services/user_health.py` directly (violates §8, would have failed import-linter); running the health sweep inside the request's session (holds one Postgres transaction open for a multi-minute Telegram-API sweep — unacceptable); a single combined adapter in `infrastructure/` doing both the Telegram call and the session (would require `infrastructure` to import aiogram, which the layer has never done and §8 forbids). |

---

# Part II — Architecture Reference (Locked)

## 6. Technology Stack

**LOCKED.** Changing any row requires Owner approval and a decision-log entry.

### 6.1 Runtime

| Layer | Technology | Version Pin | Notes |
|---|---|---|---|
| Language | Python | 3.13.x | Newest stable when V1 begins. |
| Telegram framework | Aiogram | 3.x (latest stable on sprint-0 start) | Async-first, FSM. |
| HTTP layer (admin / health / metrics) | FastAPI | 0.139.0 (D-049, bumped D-065) | Mounted as a separate process (`api/`). Sprint 10 shipped health/ready/metrics; the `/v1/admin/*` surface (Task 8.3) was added 2026-06-25, gated by `ADMIN_API_KEY` (D-051). Bumped from 0.115.6 on 2026-07-03 for the starlette CVE fix (D-065). |
| ASGI framework under FastAPI | starlette | 1.3.1 (D-065) | Pinned explicitly as a security floor — 0.41.3 carried 7 known CVEs. |
| ASGI server | uvicorn | 0.34.0 (D-049) | Used by the FastAPI process. |
| Database | PostgreSQL | 15.x (minimum 15) | Required for UUIDv7-compatible storage, JSONB, partitioning, partial indexes. |
| ORM | SQLAlchemy | 2.0.x | Async sessions only. |
| Migrations | Alembic | latest stable | Versioned, additive-first. |
| Cache + Queue | Redis | 7.x | Persistence on (AOF + RDB). |
| DB connection pooler | PgBouncer | latest stable | Transaction pooling. |
| Downloader | yt-dlp | latest stable, pinned monthly | Cron-bumped after smoke tests. |
| Media transcoder | FFmpeg | system package, pinned major version | Vendored if distro version is too old. |
| Error tracking | Sentry SDK | latest stable | Self-hosted or SaaS — Owner decides per-environment. |
| Uptime monitoring | Uptime Kuma | latest stable | Probes `/v1/health`, `/v1/ready`. |

### 6.2 Python Libraries

| Library | Purpose | Notes |
|---|---|---|
| `pydantic` v2 | Validation, schemas | |
| `pydantic-settings` | Config | |
| `structlog` | Structured logging | JSON in prod, console in dev. |
| `asyncpg` | Postgres driver | Via SQLAlchemy. |
| `redis` (with `hiredis`) | Async Redis client | |
| `tenacity` | Retry policies | |
| `orjson` | Fast JSON | |
| `aiohttp` | Aiogram transport | Already required. |
| `prometheus-client` | `/v1/metrics` registry + exposition | 0.21.1 (D-050). Sprint 10. |

### 6.3 Tooling

| Tool | Purpose |
|---|---|
| `ruff` | Lint + format. |
| `mypy` (strict mode) | Type checking. |
| `pytest`, `pytest-asyncio` | Tests. |
| `pip-audit` | Dependency vulnerability scan, CI step. |
| `bandit` | Static security scan. |
| Pre-commit hooks | Run lint, type-check, fast tests on staged files. |

### 6.4 Adding a New Dependency

Any new dependency requires:

1. A row added to Section 6.1, 6.2, or 6.3 with version pin and purpose.
2. A decision-log entry citing why the existing stack cannot meet the need.
3. Owner approval.

Dependencies are pinned to exact versions in `pyproject.toml`. `pip-audit` runs in CI on every PR.

---

## 7. Repository Layout

**LOCKED.** New top-level directories require Owner approval.

```
project_root/
│
├── bot/                         # Telegram Bot Layer (thin)
│   ├── main.py                  # Bot entry point
│   ├── handlers/                # Aiogram handlers
│   ├── middlewares/             # Auth, throttle, logging, db_session
│   ├── keyboards/               # Inline + reply keyboards
│   ├── filters/                 # URL filter, role filter
│   └── callbacks/               # Callback data factories
│
├── services/                    # Business logic (framework-agnostic)
│   ├── url_analyzer.py
│   ├── job_service.py
│   ├── download_service.py
│   ├── history_service.py
│   ├── cache_service.py
│   ├── user_service.py
│   ├── queue_service.py
│   ├── notification_service.py
│   ├── ad_service.py
│   ├── broadcast_service.py
│   ├── settings_service.py
│   └── rate_limit_service.py
│
├── workers/                     # Queue consumers
│   ├── main.py
│   ├── download_worker.py
│   ├── cleanup_worker.py
│   └── broadcast_worker.py
│
├── domain/                      # Pure domain (no framework imports)
│   ├── entities/
│   ├── enums/
│   ├── exceptions.py
│   └── protocols/               # Protocols implemented by infrastructure
│       ├── repositories.py
│       ├── cache.py
│       ├── queue.py
│       ├── downloader.py
│       ├── transcoder.py
│       └── file_sender.py
│
├── infrastructure/              # Adapters to external systems
│   ├── database/
│   │   ├── engine.py
│   │   ├── session.py
│   │   ├── models/              # SQLAlchemy ORM models
│   │   └── repositories/        # Protocol implementations
│   ├── redis/
│   │   ├── client.py
│   │   ├── cache.py
│   │   ├── queue.py
│   │   └── locks.py
│   ├── downloader/
│   │   ├── registry.py              # DownloaderRegistry — provider abstraction
│   │   ├── providers/               # one file per provider
│   │   │   ├── __init__.py
│   │   │   └── ytdlp_provider.py    # V1: sole registered provider
│   │   └── ffmpeg_client.py         # transcoder (not a provider)
│   └── telegram/
│       └── file_sender.py
│
├── api/                         # FastAPI (admin, health, metrics)
│   ├── main.py
│   ├── routes/
│   │   ├── v1_health.py
│   │   ├── v1_admin.py
│   │   └── v1_metrics.py
│   └── dependencies.py
│
├── core/                        # Cross-cutting concerns
│   ├── config.py                # pydantic-settings
│   ├── logging.py               # structlog setup
│   ├── sentry.py                # Sentry init
│   ├── uuid7.py                 # UUIDv7 helper (D-023)
│   └── constants.py
│
├── migrations/                  # Alembic
│   ├── env.py
│   └── versions/
│
├── tests/                       # See Section 25.2 for the canonical layout
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── performance/
│   ├── e2e/
│   ├── regression/
│   └── simulation/              # User Simulation Framework (Section 25.15)
│
├── deploy/                      # Dockerfiles, compose files, configs
│   ├── Dockerfile.bot
│   ├── Dockerfile.worker
│   ├── Dockerfile.api
│   ├── docker-compose.yml
│   ├── pgbouncer.ini
│   └── README.md
│
├── alembic.ini
├── pyproject.toml
├── .env.example
├── MASTER_PLAN.md               # THIS FILE
├── project_reference.md         # Superseded (historical)
└── database_reference.md        # Superseded (historical)
```

### 7.1 File-Placement Rules

| If you are writing… | It belongs in… |
|---|---|
| Code that imports Aiogram types | `bot/` |
| Code that imports FastAPI types | `api/` |
| Code that subprocesses yt-dlp or any provider library | `infrastructure/downloader/providers/<name>_provider.py` (one provider per file) |
| Code that selects / orchestrates between providers | `infrastructure/downloader/registry.py` |
| Code that subprocesses FFmpeg (transcoder, not provider) | `infrastructure/downloader/ffmpeg_client.py` |
| Code that sends a Telegram message or file | `infrastructure/telegram/` (the send) and `bot/` or a service (the decision to send) |
| A SQLAlchemy ORM model | `infrastructure/database/models/` |
| A SQL query | `infrastructure/database/repositories/` |
| A Redis call | `infrastructure/redis/` |
| A reusable protocol or ABC | `domain/protocols/` |
| A business rule | A service in `services/` |
| A pure dataclass (no framework) | `domain/entities/` |
| A configuration key | `core/config.py` + Section 13 |
| A cross-cutting helper used by 3+ layers | `core/` |

If your code doesn't fit any rule above, **stop and ask**.

---

## 8. Architecture Layers and Dependency Rules

```
   ┌──────────────────────────────────────────────────────┐
   │                       core/                          │  ← leaf, no project imports
   └──────────────────────────────────────────────────────┘
                              ▲
                              │
   ┌──────────────────────────┴───────────────────────────┐
   │                       domain/                        │  ← may import core only
   └──────────────────────────────────────────────────────┘
                              ▲                ▲
                  ┌───────────┘                └───────────┐
                  │                                        │
   ┌──────────────┴─────────────┐         ┌──────────────┴──────────────┐
   │     services/              │         │      infrastructure/        │
   │   (may import: domain,     │         │  (may import: domain, core) │
   │    core)                   │         │                             │
   └────────────────────────────┘         └─────────────────────────────┘
                  ▲                                        ▲
                  │                                        │
   ┌──────────────┴────────┐  ┌──────────┴────────┐  ┌────┴───────────┐
   │   bot/                │  │   api/            │  │   workers/     │
   │ (services, domain,    │  │ (services, domain,│  │ (services,     │
   │  core)                │  │  core)            │  │  domain, core) │
   └───────────────────────┘  └───────────────────┘  └────────────────┘
```

### 8.1 Allowed Imports

| Layer | May Import From |
|---|---|
| `core/` | (no project imports) |
| `domain/` | `core/` |
| `services/` | `domain/`, `core/` |
| `infrastructure/` | `domain/`, `core/` |
| `workers/` | `services/`, `domain/`, `core/` |
| `bot/` | `services/`, `domain/`, `core/` |
| `api/` | `services/`, `domain/`, `core/` |

Notably:
- `bot/`, `api/`, and `workers/` **must not** import from `infrastructure/`. They receive concrete infrastructure objects only at the entry point and only via dependency injection.
- `services/` **must not** import from `infrastructure/`. They depend on `domain/protocols/`.
- `infrastructure/` **must not** import from `services/`, `bot/`, `api/`, or `workers/`. It is a leaf in dependency direction (alongside `core/` and `domain/`).

A CI lint rule (`import-linter` or equivalent) enforces this.

### 8.2 Composition Root

Each process has exactly one composition root that wires concretes to protocols and injects them into the service layer:

| Process | Composition Root |
|---|---|
| Bot | `bot/main.py` |
| Worker pool | `workers/main.py` |
| API | `api/main.py` |

The composition root is the only place that may import from both `services/` and `infrastructure/` in the same file.

---

## 9. Component Catalog

Every component listed here has a **Component Card** with seven fixed sections: **Purpose · Responsibilities · Dependencies · Files/Folders · Related Services · Can Modify · Must Never Modify**.

If a component is not listed here, it does not exist yet. Adding a component requires adding its card before merging.

### 9.1 Bot Layer

#### Component: `BotApp` (entry point)
- **Purpose:** Bring the bot online, wire dependencies, register handlers, run the dispatcher.
- **Responsibilities:** Read config; init logging, Sentry, DB session factory, Redis client; build service objects; mount `/health` endpoints; start polling or webhook listener.
- **Dependencies:** `core/config.py`, `core/logging.py`, `core/sentry.py`, every service, every infrastructure concrete.
- **Files/Folders:** `bot/main.py`
- **Related Services:** All.
- **Can Modify:** Aiogram dispatcher configuration, handler registration order.
- **Must Never Modify:** Any service internals; any DB schema; the queue protocol.

#### Component: `DownloadHandlers`
- **Purpose:** Receive URL messages and callback queries for format/quality selection; delegate to services.
- **Responsibilities:** Parse messages, validate inbound data via Aiogram filters, call `URLAnalyzerService`, `JobService`, `HistoryService`, build keyboards, format responses.
- **Dependencies:** `URLAnalyzerService`, `JobService`, `HistoryService`, `NotificationService`, keyboards.
- **Files/Folders:** `bot/handlers/download.py`, `bot/keyboards/format_select.py`, `bot/keyboards/quality_select.py`, `bot/callbacks/factory.py`
- **Related Services:** All download-related services.
- **Can Modify:** Catalog copy in `core/locales/*.json` (Sprint 11.5 — never a hardcoded string in the handler itself), keyboard layouts.
- **Must Never Modify:** Business rules; database access; Telegram file uploads (those are in `infrastructure/telegram/file_sender.py`).

#### Component: `HistoryHandlers`
- **Purpose:** Show history; respond to resend taps.
- **Responsibilities:** Render paginated history with inline buttons; call `HistoryService.resend()`.
- **Dependencies:** `HistoryService`.
- **Files/Folders:** `bot/handlers/history.py`, `bot/keyboards/history.py`
- **Related Services:** `HistoryService`, `NotificationService`.
- **Can Modify:** Pagination size (within configurable bounds), keyboard layout.
- **Must Never Modify:** Cache; `cached_files` table; `downloads` table writes.

#### Component: `AdminHandlers`
- **Purpose:** In-bot administrative commands for Owner and Moderator.
- **Responsibilities:** `/stats`, `/ban`, `/unban`, `/userinfo`, `/users`, `/broadcast`, `/settings`, `/setting_set`. Authorization gating via `RoleFilter` (non-staff are silently ignored). The ad commands (`/ad_*`) live in `AdHandlers`.
- **Dependencies:** `UserService`, `BroadcastService`, `SettingsService`.
- **Files/Folders:** `bot/handlers/admin.py`
- **Related Services:** All admin-facing services.
- **Can Modify:** Command surface (subject to versioning).
- **Must Never Modify:** Authorization rules — those live in `RoleFilter` and `UserService`.

#### Component: `AdHandlers`
- **Purpose:** The ad admin surface (Owner-only) plus the public ad-click callback.
- **Responsibilities:** `/ad_create`, `/ad_list`, `/ad_edit`, `/ad_toggle`, `/ad_delete`, `/ad_stats`, `/ad_global` gated by `OwnerFilter` (non-owners silently ignored); the signed `a|<ad_id>` ad-click callback (any user) → record the click + deliver the link (flow 16.7 W6). Parse/delegate/format only.
- **Dependencies:** `AdService` (via `ad_service_factory`), `CallbackSigner`.
- **Files/Folders:** `bot/handlers/ads.py`
- **Related Services:** `AdService`.
- **Can Modify:** Command + callback surface (subject to versioning).
- **Must Never Modify:** Authorization rules (`OwnerFilter`); selection/click logic (lives in `AdService`).

#### Component: `AuthMiddleware`
- **Purpose:** Resolve the Telegram user to a `users` row on every update; populate context; reject banned users.
- **Responsibilities:** Look up user (via cached path), upsert if first time, check `is_banned`, attach user object to handler context.
- **Dependencies:** `UserService`.
- **Files/Folders:** `bot/middlewares/auth.py`
- **Related Services:** `UserService`, `CacheService` indirectly.
- **Can Modify:** Cache hit/miss telemetry.
- **Must Never Modify:** Ban message text as a hardcoded literal (must go through `core.i18n.translate`, Sprint 11.5); the user-resolution rules; must seed a new user's `users.language` from `Settings.default_locale`, never from Telegram's auto-detected `language_code` (D-061).

#### Component: `LocaleMiddleware` (Sprint 11.5)
- **Purpose:** Resolve the effective UI locale for the current update and inject it into handler context.
- **Responsibilities:** Read `data["user"].language` (populated upstream by `AuthMiddleware`) and call `core.i18n.resolve_locale()`, injecting the result as `data["locale"]`. Recomputed fresh on every update — never caches or writes back to the DB, so a since-disabled locale automatically recovers the moment it is re-enabled (D-063).
- **Dependencies:** `core/i18n.py`.
- **Files/Folders:** `bot/middlewares/i18n.py`
- **Related Services:** None directly; every handler downstream consumes `data["locale"]`.
- **Can Modify:** Nothing configurable here by design.
- **Must Never Modify:** Must run after `AuthMiddleware` (needs `data["user"]`) and before `ThrottleMiddleware` (its own message needs a resolved locale); must never write to `users.language`.

#### Component: `ThrottleMiddleware`
- **Purpose:** Enforce per-user message rate limits.
- **Responsibilities:** Increment a Redis counter; reject above threshold; return a localized friendly message.
- **Dependencies:** `RateLimitService`.
- **Files/Folders:** `bot/middlewares/throttle.py`
- **Related Services:** `RateLimitService`.
- **Can Modify:** Specific limits via `settings`.
- **Must Never Modify:** The Redis key scheme (Section 11.4).

#### Component: `LoggingMiddleware`
- **Purpose:** Bind a correlation ID to the structlog context for the duration of one Telegram update.
- **Responsibilities:** Generate UUIDv7, bind, unbind on completion.
- **Dependencies:** `core/logging.py`.
- **Files/Folders:** `bot/middlewares/logging.py`
- **Related Services:** None.
- **Can Modify:** Logged fields.
- **Must Never Modify:** Correlation ID generation algorithm (must remain UUIDv7).

#### Component: `DbSessionMiddleware`
- **Purpose:** Open an async session per update; commit on success; rollback on failure.
- **Responsibilities:** Provide a session into the handler context.
- **Dependencies:** `infrastructure/database/session.py`.
- **Files/Folders:** `bot/middlewares/db_session.py`
- **Related Services:** None directly.
- **Can Modify:** Session scope semantics within the documented rules.
- **Must Never Modify:** Transaction isolation level.

### 9.2 Services Layer

#### Component: `URLAnalyzerService`
- **Purpose:** Turn a user URL into a `MediaInfo` value object with available formats and qualities.
- **Responsibilities:** URL syntactic validation; URL normalization; `(platform, video_id)` extraction; metadata cache check; yt-dlp invocation (via protocol); UPSERT into `media_metadata`; metadata cache write.
- **Dependencies:** `CacheService`, `domain/protocols/downloader.py`, `MediaRepository`.
- **Files/Folders:** `services/url_analyzer.py`
- **Related Services:** `JobService`.
- **Can Modify:** Cache TTLs (via settings), supported-platform allowlist.
- **Must Never Modify:** The `media_metadata` schema; the metadata cache key scheme.

#### Component: `JobService`
- **Purpose:** Decide whether to serve from cache, attach to a running download, or create a new job.
- **Responsibilities:** Check `cached_files`; on hit, deliver the cached `file_id` instantly and record it (downloads row + counters + cache-hit progress edit, flow 16.2); on miss, claim `active_downloads`; on conflict, attach the user to the existing job via `job_waiters`; on success, create a `jobs` row, stash the worker's progress context + lock token in Redis (`job:{id}`), and enqueue.
- **Dependencies:** `JobRepository`, `CachedFileRepository`, `ActiveDownloadRepository`, `JobWaiterRepository`, `DownloadRepository`, `UserRepository`, `QueueService`, `CacheService`, `FileSenderProtocol`, `NotificationService`. (The cache-hit path delivers + records directly, so it owns delivery for that path — flow 16.2.)
- **Files/Folders:** `services/job_service.py`
- **Related Services:** `DownloadService`, `NotificationService`.
- **Can Modify:** Job priority assignment within documented bands.
- **Must Never Modify:** The `jobs`, `active_downloads`, or `job_waiters` schemas.

#### Component: `DownloadService`
- **Purpose:** Execute a queued job end-to-end.
- **Responsibilities:** Read job; call yt-dlp (download); call FFmpeg if needed; call Telegram file sender; UPSERT `cached_files`; INSERT into `downloads` for every waiter (primary + fan-out); update counters atomically; remove `active_downloads` row; mark job complete; trigger `NotificationService`.
- **Dependencies:** `domain/protocols/downloader.py`, `domain/protocols/transcoder.py`, `domain/protocols/file_sender.py`, `JobRepository`, `CachedFileRepository`, `DownloadRepository`, `ActiveDownloadRepository`, `JobWaiterRepository`, `UserRepository`, `NotificationService`.
- **Files/Folders:** `services/download_service.py`
- **Related Services:** `JobService`, `NotificationService`, `AdService`.
- **Can Modify:** Temp file paths, working directory, internal step ordering.
- **Must Never Modify:** Schema of `cached_files`, `downloads`, `jobs`, `active_downloads`, `job_waiters`.

#### Component: `HistoryService`
- **Purpose:** Read user history; provide instant resend.
- **Responsibilities:** Paginated SELECT on `downloads`; on resend, JOIN to `cached_files`; on cache miss, fall back to a new `JobService.create_job`.
- **Dependencies:** `DownloadRepository`, `CachedFileRepository`, `JobService`, `domain/protocols/file_sender.py`.
- **Files/Folders:** `services/history_service.py`
- **Related Services:** `JobService`, `NotificationService`.
- **Can Modify:** Pagination window (within settings).
- **Must Never Modify:** Writes to `downloads` from this path (resend never inserts a duplicate history row by itself; it returns the existing row).

#### Component: `CacheService`
- **Purpose:** Single, audited entry point for Redis cache operations.
- **Responsibilities:** `file_id` cache, metadata cache, user cache (D-014), download lock acquire/release.
- **Dependencies:** `domain/protocols/cache.py` (implemented by `infrastructure/redis/cache.py`).
- **Files/Folders:** `services/cache_service.py`
- **Related Services:** Most.
- **Can Modify:** TTLs via settings.
- **Must Never Modify:** The Redis key scheme (Section 11.4).

#### Component: `UserService`
- **Purpose:** User registration, role management, ban administration, lookups.
- **Responsibilities:** `UPSERT` on first contact; role assignment; ban / unban (preserving audit fields); update `last_activity_at` with debounce; manage user cache.
- **Dependencies:** `UserRepository`, `CacheService`.
- **Files/Folders:** `services/user_service.py`
- **Related Services:** `AuthMiddleware`.
- **Can Modify:** Cache TTLs (via settings); debounce window (constant).
- **Must Never Modify:** Role enum; `users` schema; the Owner ID source (config only).

#### Component: `QueueService`
- **Purpose:** Encapsulate enqueue, dequeue (worker side), depth, ack/nack.
- **Responsibilities:** Wrap the Redis sorted-set + active-set protocol. Provide priority semantics. Provide blocking dequeue for workers.
- **Dependencies:** `domain/protocols/queue.py` (implemented by `infrastructure/redis/queue.py`).
- **Files/Folders:** `services/queue_service.py`
- **Related Services:** `JobService`, `DownloadWorker`.
- **Can Modify:** Priority weights (within documented bands).
- **Must Never Modify:** Redis key scheme; priority band ranges.

#### Component: `NotificationService`
- **Purpose:** Send user-facing messages tied to jobs (progress, completion, failure).
- **Responsibilities:** Localized messages — every send method takes a required `locale: str` and routes copy through `core.i18n.translate` (Sprint 11.5; en/ar shipped, extensible to more); routing via the Telegram client.
- **Dependencies:** `domain/protocols/file_sender.py` for files; raw Telegram message API via an injected `MessageSender` protocol; `core/i18n.py`.
- **Files/Folders:** `services/notification_service.py`
- **Related Services:** `DownloadService`, `JobService`.
- **Can Modify:** Catalog copy in `core/locales/*.json`.
- **Must Never Modify:** Notification delivery transport; must resolve each fan-out recipient's own locale rather than reusing one job-level locale (D-063).

#### Component: `AdService`
- **Purpose:** Decide whether to show an ad after a download; pick the ad; record the impression.
- **Responsibilities:** Selection algorithm (Section 16.7); impression increment; click tracking via callback.
- **Dependencies:** `AdRepository`, `SettingsService`, `UserRepository`.
- **Files/Folders:** `services/ad_service.py`
- **Related Services:** `DownloadService` (calls it after delivery), `AdminHandlers`.
- **Can Modify:** Algorithm tuning constants in settings.
- **Must Never Modify:** Schema of `advertisements`; the `ads_enabled` master switch semantics.

#### Component: `BroadcastService`
- **Purpose:** Queue and execute broadcast deliveries with filtering.
- **Responsibilities:** Create a `broadcasts` row; spawn a `broadcast_worker` job; update `total_sent` / `total_failed`.
- **Dependencies:** `BroadcastRepository`, `UserRepository`, `QueueService`.
- **Files/Folders:** `services/broadcast_service.py`
- **Related Services:** `BroadcastWorker`, `AdminHandlers`.
- **Can Modify:** Per-batch chunk size (configurable).
- **Must Never Modify:** Schema of `broadcasts`.

#### Component: `SettingsService`
- **Purpose:** Read and write the `settings` key/value store, with caching.
- **Responsibilities:** Type-cast values (parse `value TEXT` to the expected Python type); read-through Redis cache; invalidate on write; provide a typed getter API per documented key.
- **Dependencies:** `SettingsRepository`, `CacheService`.
- **Files/Folders:** `services/settings_service.py`
- **Related Services:** Many.
- **Can Modify:** Cache TTL.
- **Must Never Modify:** The set of keys (Section 13.4). New keys require Section 5 approval.

#### Component: `RateLimitService`
- **Purpose:** Centralize all rate-limit decisions.
- **Responsibilities:** Read `settings` (free vs. premium limits); check `users.daily_download_count` (lazy reset, D-012); check Redis cooldown counter; check per-minute message throttle.
- **Dependencies:** `SettingsService`, `CacheService`, `UserRepository`.
- **Files/Folders:** `services/rate_limit_service.py`
- **Related Services:** `JobService`, `ThrottleMiddleware`.
- **Can Modify:** Limit values (via settings only).
- **Must Never Modify:** The lazy-reset algorithm without Section 5.

### 9.3 Workers Layer

#### Component: `DownloadWorker`
- **Purpose:** Pull jobs from the queue, invoke `DownloadService`, manage retry/failure, send heartbeats.
- **Responsibilities:** Acquire job (`BZPOPMIN`); call `DownloadService.process`; on retryable failure increment retry count and re-enqueue; on permanent failure mark job; release `active_downloads` row; clear temp files; heartbeat every N seconds.
- **Dependencies:** `QueueService`, `DownloadService`, `JobRepository`.
- **Files/Folders:** `workers/download_worker.py`, `workers/main.py`
- **Related Services:** `DownloadService`.
- **Can Modify:** Heartbeat interval (configurable), retry-window backoff (within tenacity policy).
- **Must Never Modify:** The job state machine (Section 12.3).

#### Component: `CleanupWorker`
- **Purpose:** Periodic maintenance.
- **Responsibilities:** Delete temp files older than N minutes; sweep `active_downloads` rows whose job is terminal; reconcile stale `job_waiters`; run `error_logs` retention; run `downloads` retention (per D-015 partitioned drop).
- **Dependencies:** Repositories for the touched tables; filesystem access.
- **Files/Folders:** `workers/cleanup_worker.py`
- **Related Services:** All cleanup-related repositories.
- **Can Modify:** Schedule (cron-style, configurable).
- **Must Never Modify:** Retention periods without an updated `settings` value.

#### Component: `BroadcastWorker`
- **Purpose:** Execute pending broadcasts in chunks.
- **Responsibilities:** Read a `broadcasts` row; iterate target users in batches; send via the Telegram client; update counters; respect Telegram rate limits (handled by Aiogram).
- **Dependencies:** `BroadcastRepository`, `UserRepository`, Telegram client via an injected sender protocol.
- **Files/Folders:** `workers/broadcast_worker.py`
- **Related Services:** `BroadcastService`.
- **Can Modify:** Batch size; inter-batch sleep (configurable).
- **Must Never Modify:** The schema of `broadcasts`; the broadcast filter semantics.

### 9.4 Domain Layer

#### Component: Entities
- **Purpose:** Immutable in-memory representations of business objects.
- **Responsibilities:** No I/O. Defaults + validation only.
- **Files/Folders:** `domain/entities/`
- **Can Modify:** Adding new entities per sprint scope.
- **Must Never Modify:** Add framework imports.

#### Component: Enums
- **Purpose:** Strongly typed enumerations: `JobStatus`, `UserRole`, `MediaFormat`, `Quality`, `ErrorType`, `AdType`.
- **Files/Folders:** `domain/enums/`
- **Can Modify:** Add values (additive) within the sprint scope.
- **Must Never Modify:** Remove values (would break stored records).

#### Component: Protocols
- **Purpose:** Define the interfaces the service layer depends on.
- **Files/Folders:** `domain/protocols/`
- **Can Modify:** Add new protocols when introducing a new infrastructure surface.
- **Must Never Modify:** Existing protocols' methods (breaking change).

#### Component: Exceptions
- **Purpose:** Domain-specific exception hierarchy (Section 15.4).
- **Files/Folders:** `domain/exceptions.py`
- **Can Modify:** Add new types per sprint.
- **Must Never Modify:** Reorder or rename existing types.

### 9.5 Infrastructure Layer

#### Component: `SqlAlchemyRepositories`
- **Purpose:** Implement repository protocols using SQLAlchemy 2.0 async sessions.
- **Files/Folders:** `infrastructure/database/repositories/*.py`
- **Can Modify:** SQL formulations to improve performance, as long as semantics and query plans don't regress.
- **Must Never Modify:** Repository protocol method signatures.

#### Component: `RedisCache`
- **Purpose:** Implement `CacheProtocol`.
- **Files/Folders:** `infrastructure/redis/cache.py`
- **Can Modify:** Serialization format (must be backward-compatible).
- **Must Never Modify:** Key scheme (Section 11.4).

#### Component: `RedisQueue`
- **Purpose:** Implement `QueueProtocol`.
- **Files/Folders:** `infrastructure/redis/queue.py`
- **Can Modify:** Sorted-set scoring within priority bands.
- **Must Never Modify:** Active-set protocol; key scheme.

#### Component: `DownloaderRegistry`
- **Purpose:** Single entry point through which all download and metadata calls flow. Owns provider selection, failover, and health.
- **Responsibilities:** Implements `DownloaderProtocol`. Holds a registered list of provider instances. Per-call: detect platform, build candidate list, try in priority order, manage failover and health updates per Section 12.6.3.
- **Dependencies:** `domain/protocols/downloader.py`; `CacheService` (for provider health state); `SettingsService` (for `providers_enabled`, failover toggles).
- **Files/Folders:** `infrastructure/downloader/registry.py`
- **Related Services:** `URLAnalyzerService`, `DownloadService`.
- **Can Modify:** Selection algorithm tuning, health-update internals, retry sequencing.
- **Must Never Modify:** The protocol surface visible to services (services see only `DownloaderProtocol`); the rule that no service code references a provider by name.

#### Component: `YtdlpProvider`
- **Purpose:** Concrete `DownloaderProtocol` implementation that wraps yt-dlp. The sole V1 provider.
- **Responsibilities:** Subprocess yt-dlp; parse JSON output; translate vendor errors to domain exceptions; expose capabilities and supported platforms; implement `health_check`.
- **Dependencies:** `yt_dlp` (vendor) — imported here and **nowhere else**.
- **Files/Folders:** `infrastructure/downloader/providers/ytdlp_provider.py`
- **Related Services:** Reached only through `DownloaderRegistry`. No service may import this file.
- **Can Modify:** Subprocess args, parsing logic, retry policy local to yt-dlp.
- **Must Never Modify:** The `DownloaderProtocol` signature; the registration interface; any code outside its file.

#### Component: `FfmpegClient`
- **Purpose:** Wrap FFmpeg.
- **Files/Folders:** `infrastructure/downloader/ffmpeg_client.py`
- **Can Modify:** Encoding presets.
- **Must Never Modify:** `TranscoderProtocol`.

#### Component: `TelegramFileSender`
- **Purpose:** Upload a file once to the storage chat to mint a reusable `file_id`/`unique_file_id`, and deliver cached files by `file_id`. Co-located `TelegramMessageSender` is the `MessageSenderProtocol` transport for `NotificationService` progress edits. The aiogram `Bot` is built by `build_bot` (`infrastructure/telegram/client.py`), which targets the self-hosted Bot API server when `BOT_API_BASE_URL` is set (D-040).
- **Files/Folders:** `infrastructure/telegram/file_sender.py`, `infrastructure/telegram/client.py`
- **Can Modify:** Chunking thresholds; storage-chat target.
- **Must Never Modify:** `FileSenderProtocol`, `MessageSenderProtocol`.

#### Component: `TelegramAdSender`
- **Purpose:** The only place that sends an advertisement message for the ad pipeline (`AdSenderProtocol`). The ad `type` selects the send method (text / photo / video / animation, re-using the admin-uploaded `content_media_file_id`); a button ad attaches one inline callback button carrying the signed ad-click `callback_data` (flow 16.7 W6).
- **Files/Folders:** `infrastructure/telegram/ad_sender.py`
- **Can Modify:** Send-method mapping per ad type; keyboard layout.
- **Must Never Modify:** `AdSenderProtocol`; the ad selection/click logic (lives in `AdService`).

### 9.6 API Layer

#### Component: `HealthRoutes`
- **Purpose:** Liveness and readiness checks.
- **Files/Folders:** `api/routes/v1_health.py`
- **Can Modify:** Probe internals.
- **Must Never Modify:** URL paths within V1.

#### Component: `AdminRoutes`
- **Purpose:** V3 web-dashboard precursor. V1 exposes read-only admin endpoints used by Moderators-via-tooling, not by end users.
- **Files/Folders:** `api/routes/v1_admin.py`
- **Can Modify:** Pagination, filters.
- **Must Never Modify:** URL paths within V1 (Section 20.2).

#### Component: `MetricsRoutes`
- **Purpose:** Operational metrics for scraping.
- **Files/Folders:** `api/routes/v1_metrics.py`
- **Can Modify:** Metric labels.
- **Must Never Modify:** Existing metric names within V1.

### 9.7 Core

#### Component: `Config`
- **Purpose:** Single, typed config object loaded at startup.
- **Files/Folders:** `core/config.py`
- **Can Modify:** Add new fields (must update Section 13).
- **Must Never Modify:** Reorder secrets; expose secrets via `__repr__`.

#### Component: `Logging`
- **Purpose:** Structlog setup; sensitive-data scrubbing.
- **Files/Folders:** `core/logging.py`
- **Can Modify:** Output formatting.
- **Must Never Modify:** Scrubbing rules without Section 14 update.

#### Component: `Sentry`
- **Purpose:** Sentry SDK init.
- **Files/Folders:** `core/sentry.py`
- **Can Modify:** Integration list (additive).
- **Must Never Modify:** DSN handling (env only).

#### Component: `Uuid7`
- **Purpose:** Generate time-ordered UUIDs (D-013).
- **Files/Folders:** `core/uuid7.py`
- **Can Modify:** Tweak random bits if a hot collision is observed.
- **Must Never Modify:** The time component (must be monotonic-millisecond).

#### Component: `Constants`
- **Purpose:** Framework-free primitive constants shared across layers (priority bands, secret-redaction key list, standard log fields, layered timeouts).
- **Files/Folders:** `core/constants.py`
- **Related Services:** `QueueService` (priority bands), `Logging`/`Sentry` (secret keys), `RateLimitService`/`UserService` (timeouts, debounce).
- **Can Modify:** Add new primitives; tune timeout/debounce constants.
- **Must Never Modify:** Priority band base scores without a Section 12.2 update; the secret-key list without a Section 14.3 update. No enums here — those live in `domain/enums/`.

#### Component: `I18n` (Sprint 11.5)
- **Purpose:** Load, validate, and look up localized UI strings for every discovered locale.
- **Responsibilities:** Discover `core/locales/*.json` at `configure()` time (called once from each composition root); validate every catalog's `_meta` block and enforce the default-locale-is-reference-catalog invariant (D-062); expose `translate(key, locale, **kwargs)` (never raises — falls back and logs on any miss); expose `resolve_locale(stored)` (read-only, never writes back to the DB) and `list_enabled_locales()` for the picker keyboard.
- **Dependencies:** `core/logging.py` only (framework-free, no `Settings` import — mirrors `core/logging.py`'s explicit `configure()` pattern).
- **Files/Folders:** `core/i18n.py`, `core/locales/*.json`
- **Related Services:** Every handler/keyboard/service that renders user-facing text; `LocaleMiddleware`.
- **Can Modify:** Add catalog keys; add a new locale file.
- **Must Never Modify:** The `_meta` contract (D-062); the default-locale-as-reference-catalog invariant; must never raise out of `translate()` (Hard Rule 10).

---

## 10. Locked Database Schema

**LOCKED.** This is the only valid V1 schema. Any change requires a new migration referenced in Section 19 and a decision-log entry.

### 10.1 Tables (V1) — Twelve Tables

| # | Table | Purpose |
|---|---|---|
| 1 | `users` | User registry (hot-path). |
| 2 | `media_metadata` | Normalized per-content metadata. |
| 3 | `cached_files` | Global `file_id` cache. |
| 4 | `downloads` | User history (partitioned monthly). |
| 5 | `jobs` | Job queue persistence (partitioned monthly). |
| 6 | `active_downloads` | In-flight dedup record. |
| 7 | `job_waiters` | Multi-user fan-out registry (D-009). |
| 8 | `broadcasts` | Broadcast log. |
| 9 | `advertisements` | Ad catalog. |
| 10 | `settings` | Runtime configuration key/value. |
| 11 | `error_logs` | Persistent error log (partitioned monthly). |
| 12 | `user_preferences` | Per-user preferences. |

### 10.2 Table: `users`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | Surrogate. |
| `telegram_id` | BIGINT | NOT NULL, UNIQUE | — | External identity. |
| `username` | VARCHAR(255) | NULLABLE | NULL | |
| `first_name` | VARCHAR(255) | NULLABLE | NULL | |
| `language` | VARCHAR(10) | NULLABLE | NULL | BCP-47 (D-022). **The user's UI locale (Sprint 11.5, D-061)** — set to `Settings.default_locale` at creation, thereafter only by an explicit in-bot language pick. Also read by ad audience targeting (`dimension='language'`). |
| `role` | VARCHAR(20) | NOT NULL | `'user'` | `owner` / `moderator` / `user`. |
| `is_premium` | BOOLEAN | NOT NULL | `false` | |
| `premium_expires_at` | TIMESTAMPTZ | NULLABLE | NULL | D-001. |
| `is_banned` | BOOLEAN | NOT NULL | `false` | |
| `banned_at` | TIMESTAMPTZ | NULLABLE | NULL | Audit retained on unban. |
| `ban_reason` | VARCHAR(500) | NULLABLE | NULL | Audit retained on unban. |
| `daily_download_count` | INTEGER | NOT NULL | `0` | Lazy-reset (D-012). |
| `daily_download_count_reset_date` | DATE | NOT NULL | `CURRENT_DATE` | Lazy-reset key (D-012). |
| `total_downloads` | BIGINT | NOT NULL | `0` | Lifetime counter. |
| `last_activity_at` | TIMESTAMPTZ | NULLABLE | NULL | Debounced write. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Indexes:** `users_pkey(id)`, `uq_users_telegram_id(telegram_id)`, `ix_users_role(role)`, `ix_users_is_premium(is_premium)`, `ix_users_is_banned(is_banned)`, `ix_users_last_activity(last_activity_at)`, `ix_users_created_at(created_at)`.

**Reserved extension points:** `referred_by BIGINT NULL FK → users.id` (V5); `stripe_customer_id VARCHAR(255) NULL` (V4). ~~`default_locale_override` already covered by `user_preferences.preferred_language` (V2)~~ — superseded: UI locale is `users.language` itself (D-061); `user_preferences.preferred_language` remains reserved/unused.

### 10.3 Table: `media_metadata`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | |
| `platform` | VARCHAR(50) | NOT NULL | — | `youtube`, `tiktok`, `instagram`, `twitter`, ... |
| `video_id` | VARCHAR(255) | NOT NULL | — | Platform-specific content ID. |
| `title` | TEXT | NOT NULL | — | TEXT (no length cap) — Postgres cost is identical to VARCHAR. |
| `duration` | INTEGER | NULLABLE | NULL | Seconds. |
| `thumbnail_url` | TEXT | NULLABLE | NULL | |
| `source_url` | TEXT | NOT NULL | — | First-seen canonical form. |
| `metadata_json` | JSONB | NULLABLE | NULL | Merged with COALESCE (D-011). |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Unique:** `uq_media_platform_video(platform, video_id)`.

**Indexes:** `media_metadata_pkey(id)`, `ix_media_platform(platform)`, `ix_media_created_at(created_at)`.

**Reserved extension points:** Future GIN trigram index on `title` for V3 search; `engine_used VARCHAR(20) NULL` (V6).

### 10.4 Table: `cached_files`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | |
| `media_id` | BIGINT | NOT NULL, FK → `media_metadata.id` ON DELETE CASCADE | — | |
| `format` | VARCHAR(50) | NOT NULL | — | |
| `quality` | VARCHAR(20) | NOT NULL | — | |
| `telegram_file_id` | VARCHAR(255) | NOT NULL | — | |
| `telegram_unique_file_id` | VARCHAR(255) | NOT NULL | — | |
| `file_size` | BIGINT | NULLABLE | NULL | Bytes. |
| `usage_count` | BIGINT | NOT NULL | `0` | D-006. |
| `last_used_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | D-007. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Unique:** `uq_cached_media_format_quality(media_id, format, quality)`.

**Indexes:** `cached_files_pkey(id)`, `ix_cached_media_id(media_id)`, `ix_cached_last_used(last_used_at)`, `ix_cached_usage_count(usage_count)`.

### 10.5 Table: `downloads` (monthly RANGE partitioned)

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK component, GENERATED ALWAYS AS IDENTITY | — | PK is `(id, created_at)` to satisfy partition constraint. |
| `user_id` | BIGINT | NOT NULL, FK → `users.id` ON DELETE CASCADE | — | |
| `cached_file_id` | BIGINT | NULLABLE, FK → `cached_files.id` ON DELETE SET NULL | — | D-008. |
| `platform` | VARCHAR(50) | NOT NULL | — | Denormalized for fast history display. |
| `format` | VARCHAR(50) | NOT NULL | — | Denormalized. |
| `quality` | VARCHAR(20) | NOT NULL | — | Denormalized. |
| `file_size` | BIGINT | NULLABLE | NULL | Denormalized. |
| `status` | VARCHAR(20) | NOT NULL | `'completed'` | `completed` / `failed` / `cancelled`. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Partition key. |

**Primary key:** `(id, created_at)`. **Partitioned by:** `RANGE (created_at)`. **Pre-create partitions** for the rolling 12 months at every cleanup-worker run. **Indexes** apply per-partition.

**Indexes:** `ix_downloads_user_id(user_id)`, `ix_downloads_user_created(user_id, created_at DESC)`, `ix_downloads_platform(platform)`, `ix_downloads_created_at(created_at)`.

### 10.6 Table: `jobs` (monthly RANGE partitioned)

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | UUID | PK component | App-generated UUIDv7 (D-013). | |
| `user_id` | BIGINT | NOT NULL, FK → `users.id` ON DELETE CASCADE | — | |
| `media_id` | BIGINT | NOT NULL, FK → `media_metadata.id` ON DELETE RESTRICT | — | |
| `format` | VARCHAR(50) | NOT NULL | — | |
| `quality` | VARCHAR(20) | NOT NULL | — | |
| `worker_kind` | VARCHAR(30) | NOT NULL | `'download'` | D-021. |
| `priority` | INTEGER | NOT NULL | `1000` | Lower = sooner. |
| `retry_count` | INTEGER | NOT NULL | `0` | |
| `status` | VARCHAR(30) | NOT NULL | `'created'` | See Section 12.3. |
| `error_message` | TEXT | NULLABLE | NULL | |
| `correlation_id` | UUID | NULLABLE | NULL | Bound to the originating request's correlation. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Partition key. |
| `started_at` | TIMESTAMPTZ | NULLABLE | NULL | |
| `finished_at` | TIMESTAMPTZ | NULLABLE | NULL | |

**Primary key:** `(id, created_at)`. **Partitioned by:** `RANGE (created_at)`.

**Indexes:** `ix_jobs_user_id(user_id)`, `ix_jobs_status(status)`, `ix_jobs_media_id(media_id)`, `ix_jobs_status_priority(status, priority, created_at)`, `ix_jobs_correlation_id(correlation_id)`.

### 10.7 Table: `active_downloads`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | |
| `media_id` | BIGINT | NOT NULL, FK → `media_metadata.id` ON DELETE CASCADE | — | |
| `format` | VARCHAR(50) | NOT NULL | — | |
| `quality` | VARCHAR(20) | NOT NULL | — | |
| `job_id` | UUID | NOT NULL, FK → `jobs.id` (no FK action, jobs partitioned; integrity by application + cleanup) | — | |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Unique:** `uq_active_media_format_quality(media_id, format, quality)`.

**Indexes:** `active_downloads_pkey(id)`, `ix_active_job_id(job_id)`.

### 10.8 Table: `job_waiters` (NEW — D-009)

Records every user waiting on a given job's completion. The primary user who created the job is also a waiter (so the fan-out flow is uniform).

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | |
| `job_id` | UUID | NOT NULL | — | Logical FK to `jobs.id`. |
| `user_id` | BIGINT | NOT NULL, FK → `users.id` ON DELETE CASCADE | — | |
| `correlation_id` | UUID | NULLABLE | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Unique:** `uq_job_waiter(job_id, user_id)` — a user appears at most once per job.

**Indexes:** `ix_job_waiters_job(job_id)`, `ix_job_waiters_user(user_id)`.

On job completion, `DownloadService` reads all waiters for the job, inserts one `downloads` row per waiter, delivers the file to each, then deletes all waiter rows in one statement.

### 10.9 Table: `broadcasts`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | |
| `created_by` | BIGINT | NOT NULL, FK → `users.id` ON DELETE RESTRICT | — | Audit. |
| `target_language` | VARCHAR(10) | NULLABLE | NULL | NULL = all. |
| `target_role` | VARCHAR(20) | NULLABLE | NULL | NULL = all. |
| `message_text` | TEXT | NOT NULL | — | |
| `expected_total` | INTEGER | NOT NULL | `0` | Snapshot of audience size at queue time (B-broadcasts progress fix). |
| `total_sent` | INTEGER | NOT NULL | `0` | |
| `total_failed` | INTEGER | NOT NULL | `0` | |
| `status` | VARCHAR(20) | NOT NULL | `'pending'` | `pending` / `in_progress` / `completed` / `cancelled`. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `completed_at` | TIMESTAMPTZ | NULLABLE | NULL | |

**Indexes:** `broadcasts_pkey(id)`, `ix_broadcasts_created_at(created_at)`, `ix_broadcasts_status(status)`.

### 10.10 Table: `advertisements`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | |
| `title` | VARCHAR(255) | NOT NULL | — | Admin-facing label. |
| `type` | VARCHAR(20) | NOT NULL | `'text'` | `text` / `photo` / `video` / `animation`. |
| `content_text` | TEXT | NULLABLE | NULL | |
| `content_media_file_id` | VARCHAR(255) | NULLABLE | NULL | Telegram `file_id` (admin uploads once). |
| `button_text` | VARCHAR(100) | NULLABLE | NULL | |
| `button_url` | TEXT | NULLABLE | NULL | |
| `target_role` | VARCHAR(20) | NULLABLE | NULL | D-004: `null` / `user` / `premium`. |
| `show_every_n_downloads` | INTEGER | NOT NULL | `1` | |
| `is_active` | BOOLEAN | NOT NULL | `true` | |
| `priority` | INTEGER | NOT NULL | `0` | Higher wins. |
| `impressions` | BIGINT | NOT NULL | `0` | |
| `clicks` | BIGINT | NOT NULL | `0` | |
| `created_by` | BIGINT | NOT NULL, FK → `users.id` ON DELETE RESTRICT | — | Audit. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Indexes:** `advertisements_pkey(id)`, `ix_ads_active_priority_role(is_active, priority DESC, target_role)` (D-018), `ix_ads_target_role(target_role)`.

### 10.11 Table: `settings`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(100) | PK | — | |
| `value` | TEXT | NOT NULL | — | Parsed by `SettingsService`. |
| `value_type` | VARCHAR(20) | NOT NULL | `'string'` | `string` / `int` / `bool` / `float` / `json`. Enables typed read. |
| `description` | TEXT | NULLABLE | NULL | Human description (shown in admin UI). |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_by` | BIGINT | NULLABLE, FK → `users.id` ON DELETE SET NULL | NULL | Audit. |

(See Section 13.4 for the seeded key set.)

### 10.12 Table: `error_logs` (monthly RANGE partitioned)

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK component, GENERATED ALWAYS AS IDENTITY | — | PK `(id, created_at)`. |
| `user_id` | BIGINT | NULLABLE, FK → `users.id` ON DELETE SET NULL | NULL | |
| `job_id` | UUID | NULLABLE | NULL | Logical link (jobs partitioned). |
| `correlation_id` | UUID | NULLABLE | NULL | |
| `error_type` | VARCHAR(30) | NOT NULL | — | See enum (Section 15.4). |
| `message` | TEXT | NOT NULL | — | |
| `traceback` | TEXT | NULLABLE | NULL | Sanitized of secrets before insert. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Partition key. |

**Partitioned by:** `RANGE (created_at)`.

**Indexes:** `ix_errors_user_id(user_id)`, `ix_errors_job_id(job_id)`, `ix_errors_type(error_type)`, `ix_errors_created_at(created_at)`, `ix_errors_correlation_id(correlation_id)`.

### 10.13 Table: `user_preferences`

| Column | Type | Constraints | Default | Notes |
|---|---|---|---|---|
| `id` | BIGINT | PK, GENERATED ALWAYS AS IDENTITY | — | D-002. |
| `user_id` | BIGINT | NOT NULL, UNIQUE, FK → `users.id` ON DELETE CASCADE | — | One-to-one. |
| `notifications_enabled` | BOOLEAN | NOT NULL | `true` | D-024. |
| `preferred_language` | VARCHAR(10) | NULLABLE | NULL | BCP-47. **Reserved/unused** — the UI locale lives in `users.language` instead (Sprint 11.5, D-061). Left here for a possible future distinct purpose (e.g., a content-language preference separate from UI language), not touched by i18n. |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | |

**Reserved extension points:** `default_format`, `default_quality`, `auto_download`, `theme` (added per V2+ sprint).

### 10.14 Foreign Keys (summary)

| # | Source | Column | Target | Target Col | ON DELETE | Rationale |
|---|---|---|---|---|---|---|
| 1 | `downloads` | `user_id` | `users` | `id` | CASCADE | User owns history. |
| 2 | `downloads` | `cached_file_id` | `cached_files` | `id` | SET NULL | D-008. |
| 3 | `jobs` | `user_id` | `users` | `id` | CASCADE | |
| 4 | `jobs` | `media_id` | `media_metadata` | `id` | RESTRICT | Cannot delete media with jobs. |
| 5 | `cached_files` | `media_id` | `media_metadata` | `id` | CASCADE | |
| 6 | `active_downloads` | `media_id` | `media_metadata` | `id` | CASCADE | |
| 7 | `active_downloads` | `job_id` | `jobs.id` | — | (logical only) | jobs partitioned; cleanup-worker reconciles. |
| 8 | `broadcasts` | `created_by` | `users` | `id` | RESTRICT | Audit. |
| 9 | `advertisements` | `created_by` | `users` | `id` | RESTRICT | Audit. |
| 10 | `error_logs` | `user_id` | `users` | `id` | SET NULL | Diagnostics survive user deletion. |
| 11 | `user_preferences` | `user_id` | `users` | `id` | CASCADE | |
| 12 | `job_waiters` | `user_id` | `users` | `id` | CASCADE | |
| 13 | `settings` | `updated_by` | `users` | `id` | SET NULL | Audit. |

### 10.15 Schema Diagram (canonical)

```
                      ┌────────────────┐
                      │   settings     │ (standalone)
                      └────────────────┘

  ┌──────────────────────────┐    1 ─── N    ┌─────────────────────────┐
  │          users           │ ───────────► │    user_preferences      │
  │ (hot path, cached)       │               │      (lazy)              │
  └──────────────────────────┘               └─────────────────────────┘
       │  1 ── N (creates)
       ├──────────────► broadcasts, advertisements (audit)
       │  1 ── N
       ├──────────────► downloads (partitioned, history)
       │  1 ── N
       ├──────────────► jobs (partitioned)
       │  1 ── N
       ├──────────────► job_waiters
       │  1 ── N
       └──────────────► error_logs (partitioned, optional)

  ┌──────────────────────────┐  1 ── N   ┌─────────────────────────┐
  │      media_metadata      │ ────────► │      cached_files       │
  └──────────────────────────┘           └─────────────────────────┘
       │  1 ── N                              │  1 ── N
       ├──────────────► jobs                  └────► downloads (SET NULL)
       │  1 ── N
       └──────────────► active_downloads ── jobs (logical link)
```

---

## 11. Cache Architecture

### 11.1 Cache Layers

| # | Cache | Backing | TTL (default) | Why |
|---|---|---|---|---|
| 1 | `file_id` cache | Redis (string) | 30 days | Avoid re-upload to Telegram. |
| 2 | Metadata cache | Redis (string, JSON) | 1 hour | Avoid yt-dlp re-extraction for hot URLs. |
| 3 | User cache | Redis (string, JSON) | 30 seconds | Hot-path user-by-`telegram_id` lookups (D-014). |
| 4 | Download lock | Redis (string, SETNX) | 10 minutes | Belt-and-suspenders dedup. The DB is the suspenders. |
| 5 | Rate-limit counters | Redis (counter + TTL) | window-dependent | Per-user throttling. |
| 6 | Settings cache | Redis (string, JSON) | 60 seconds | Avoid PG hit on every read. |

### 11.2 Cache Authority

- **`file_id` cache:** `cached_files` table is authoritative; Redis is a read-through accelerator.
- **Metadata cache:** `media_metadata` is authoritative.
- **User cache:** `users` is authoritative; Redis is a TTL-bounded snapshot.
- **Download lock:** Redis is the fast path; `active_downloads.uq_active_media_format_quality` is the durable enforcement.
- **Rate-limit counters:** Redis only (acceptable for the use case).
- **Settings cache:** `settings` is authoritative.

### 11.3 Invalidation

- **User cache:** invalidate on every successful write to `users` for that user.
- **Settings cache:** invalidate the specific key on every `SettingsService.set`.
- **Metadata cache:** TTL expiration only.
- **`file_id` cache:** invalidate when `cached_files` row is deleted (cache eviction) or replaced.

### 11.4 Key Scheme (LOCKED)

| Pattern | Example | Owner |
|---|---|---|
| `fileid:{media_id}:{format}:{quality}` | `fileid:42:mp4:720p` | `cached_files` projection |
| `meta:{platform}:{video_id}` | `meta:youtube:dQw4w9WgXcQ` | metadata cache |
| `user:{telegram_id}` | `user:123456789` | user cache |
| `lock:{media_id}:{format}:{quality}` | `lock:42:mp4:720p` | download lock |
| `rate:msg:{user_id}` | `rate:msg:123456789` | message throttle |
| `rate:dl_cooldown:{user_id}` | `rate:dl_cooldown:123456789` | download cooldown |
| `settings:{key}` | `settings:free_daily_limit` | settings cache |
| `queue:jobs` | (sorted set) | priority queue |
| `queue:active` | (set) | in-flight job IDs |
| `job:{job_id}` | `job:01J...` | job detail mirror |
| `worker:heartbeat:{worker_id}` | `worker:heartbeat:dl-1` | liveness |
| `provider:health:{name}` | `provider:health:ytdlp` | provider health record (Section 12.6.4) |
| `bcast:progress:{broadcast_id}` | `bcast:progress:7` | broadcast progress |
| `ad_counter:{user_id}` | `ad_counter:123` | ad pacing (V2 candidate) |

Adding a new key requires updating this table.

---

## 12. Queue Architecture

### 12.1 One Queue, Many Worker Kinds (D-021)

A single `queue:jobs` sorted set holds all jobs. Each job carries a `worker_kind` field. Workers filter on dequeue: a downloader takes jobs where `worker_kind = 'download'`, etc. This keeps the protocol simple while supporting V6's multi-engine fallback without forking.

### 12.2 Priority Bands

| Band | Score base | Assigned to (V1) | Reserved for |
|---|---|---|---|
| `URGENT` | 0 | (none) | Admin-triggered priority jobs (V3+) |
| `HIGH` | 500 | (none) | Premium users (V2) |
| `NORMAL` | 1000 | All free users | — |
| `LOW` | 2000 | Retries with backoff | Bulk batches (V2+ multi-link) |

**Score** = `base + (unix_time_ms / 1000)`. Lower score sorts first. FIFO within a band.

### 12.3 Job State Machine (LOCKED)

```
CREATED ─► QUEUED ─► PROCESSING ─► COMPLETED
                       │
                       ├──► FAILED (transient) ─► RETRY_QUEUED ─► QUEUED
                       │                                  (loop, max 3)
                       │
                       ├──► PERMANENTLY_FAILED
                       │
                       ├──► TIMED_OUT ─► (auto re-queue if retries left, else PERMANENTLY_FAILED)
                       │
                       └──► CANCELLED  (admin or user action)
```

Terminal states: `COMPLETED`, `PERMANENTLY_FAILED`, `CANCELLED`. `TIMED_OUT` is transient until a worker re-evaluates.

### 12.4 Fan-Out (LOCKED)

When a duplicate request is detected (the `active_downloads` INSERT raises a unique-constraint violation):

1. Read the existing row's `job_id`.
2. `INSERT INTO job_waiters (job_id, user_id, correlation_id) ON CONFLICT DO NOTHING`.
3. Reply to the user with the existing job's progress.
4. When the worker finishes, it reads all waiters, sends the file to each, inserts a `downloads` row per waiter, and clears the waiters in one statement.

### 12.5 Idempotency

Every worker step is designed to be safe to retry:

- `cached_files` write is UPSERT keyed on `(media_id, format, quality)`.
- `downloads` writes are guarded by an idempotency token: `(job_id, user_id)` is unique per fan-out cohort. A retry that sees a row already exists for that `(job_id, user_id)` skips the insert.
- Counter increments (`users.total_downloads`, `users.daily_download_count`) happen exactly once per `(job_id, user_id)` via a small `job_user_counted` table (V1: track via a column on `downloads` or via a Redis `SETNX` token — the latter is acceptable since over-undercounting a counter is acceptable, while under/over-delivering a file is not).

### 12.6 Download Provider Architecture

The system is **never** tightly coupled to a single download library, extractor, or platform integration. V1 ships with yt-dlp as the only registered provider, but the registry and protocol below are built from day one (D-026). **This is a LOCKED architectural rule.**

#### 12.6.1 Layered Model

```
Application
   │
   ▼
DownloadService  ──────────────►  DownloaderProtocol
URLAnalyzerService                  │
                                    ▼
                           DownloaderRegistry
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
        YtdlpProvider       GalleryDlProvider    DirectHttpProvider
            (V1)               (V6, reserved)        (V6, reserved)
```

Services see only `DownloaderProtocol`. The registry encapsulates provider selection, failover, health tracking, and capability filtering. **No service ever names a specific provider.**

#### 12.6.2 `DownloaderProtocol` (LOCKED interface)

Two async methods on the protocol:

- `extract_info(url: str) -> MediaInfo` — discover formats, metadata, supported qualities.
- `download(media: MediaInfo, format: str, quality: str, dest: Path) -> DownloadedFile` — produce a local file.

Each concrete provider also declares:

| Attribute | Type | Purpose |
|---|---|---|
| `name` | `str` | Unique provider identifier (e.g., `"ytdlp"`). Used in settings, logs, metrics. |
| `supported_platforms` | `set[str]` | Platform IDs (`"youtube"`, `"tiktok"`, ...). The wildcard `"*"` means "any URL". |
| `capabilities` | `set[Capability]` | `VIDEO`, `AUDIO`, `LIVE_STREAM`, `PLAYLIST`, `IMAGE`. |
| `priority` | `int` | Registry tie-breaker — higher wins. |
| `health_check()` | `() -> ProviderHealth` | Returns `OK`, `DEGRADED`, or `UNAVAILABLE`. |

A provider that wishes to opt out of a specific request raises `ProviderUnsupported`; the registry advances to the next candidate.

#### 12.6.3 `DownloaderRegistry` Behavior (LOCKED)

On every `extract_info(url)` or `download(...)` call:

1. **Platform detect.** Infer the platform from the URL. Unknown → `"*"`.
2. **Candidate list.** All providers where:
   - `name` is in `settings.providers_enabled` with value `true`, **and**
   - `supported_platforms` contains the detected platform (or `"*"`), **and**
   - `health_check() != UNAVAILABLE`.
   Sort by `priority DESC`, then by `name ASC` for determinism.
3. **Try first.** Call the first candidate.
4. **On retryable failure** (`ProviderRetryElsewhere`, transient `ExtractionFailedError`, network/timeout from inside the provider):
   - Mark this provider `DEGRADED` for `provider_cooldown_seconds` (Redis).
   - Move to the next candidate.
   - If `settings.provider_failover_enabled == false`, stop and propagate.
5. **On non-retryable failure** (URL genuinely unsupported by all candidates, file actually too large, content blocked by platform):
   - Stop and propagate the domain exception.
6. **If all candidates fail:** raise the first encountered error, with the others attached as `__notes__`.

The registry never silently downgrades quality, format, or content. **Failover is provider-level, not content-level.**

#### 12.6.4 Health Tracking

| Key | Value | Notes |
|---|---|---|
| `provider:health:{name}` | `{status, last_check_ts, error_streak, last_error}` | Overwritten by health checks; no TTL. |

Health updates on:

- Every request outcome — success resets `error_streak`; failure increments it; crossing the configurable threshold trips `DEGRADED`.
- A periodic background task in the worker process — every `provider_health_check_interval_seconds` (default 120 s), it calls each provider's `health_check()`.

Health transitions emit a structured log line and a Prometheus counter `provider_health_changes_total{provider, from, to}`.

#### 12.6.5 V1 Provider Inventory

| Provider | `name` | File | Status | Platforms | Capabilities | Priority |
|---|---|---|---|---|---|---|
| `YtdlpProvider` | `ytdlp` | `infrastructure/downloader/providers/ytdlp_provider.py` | Active (sole V1 provider) | `*` (all yt-dlp-supported) | `VIDEO`, `AUDIO` | `100` |

Reserved provider slots — **not implemented in V1**:

| Reserved Provider | `name` | Planned Version | Intended Use |
|---|---|---|---|
| `GalleryDlProvider` | `gallerydl` | V6 | Image-heavy platforms gallery-dl handles better than yt-dlp. |
| `DirectHttpProvider` | `direct` | V6 | Direct CDN / static-file URLs (no extractor needed). |
| `InternalProvider` | `internal` | post-V6 | Hypothetical in-house extractor (TBD). |

#### 12.6.6 Adding a New Provider — Procedure (LOCKED)

1. Implement the provider in `infrastructure/downloader/providers/<name>_provider.py`, conforming to `DownloaderProtocol`.
2. Register it in every composition root (`bot/main.py`, `workers/main.py`, `api/main.py`) via `DownloaderRegistry.register(provider)`.
3. Add a row to Section 12.6.5 (V1 Provider Inventory).
4. If the provider needs configuration, add settings keys (Section 13.4).
5. Add a decision-log entry (Section 5).
6. Add integration tests with recorded fixtures of the new provider's response format.
7. Update `PROJECT_PROGRESS.md` per Section 1.8.

**No business logic in `services/`, `bot/`, `workers/`, or `api/` may change to add a provider.** If a change there is required, the abstraction is wrong and must be fixed first (D-029).

#### 12.6.7 Provider-Related Settings (seeded — see Section 13.4)

| Key | Type | Default | Description |
|---|---|---|---|
| `providers_enabled` | json | `{"ytdlp": true}` | Per-provider on/off, by `name`. |
| `provider_priority_overrides` | json | `{}` | Optional runtime override of compile-time `priority` values. |
| `provider_cooldown_seconds` | int | `60` | Time a DEGRADED provider stays skipped before retry. |
| `provider_health_check_interval_seconds` | int | `120` | Background health-check cadence. |
| `provider_failover_enabled` | bool | `true` | If `false`, only the highest-priority candidate is tried. |
| `provider_failure_threshold` | int | `3` | Consecutive errors before `OK → DEGRADED`. |

#### 12.6.8 Failure Strategy

| Failure Class | Provider Behavior | Registry Behavior |
|---|---|---|
| URL syntactically invalid | Raise `URLNotSupportedError` immediately. | Stop. Do not try other providers. |
| URL valid but provider does not support this platform | Raise `ProviderUnsupported`. | Try next candidate silently. |
| Transient extractor error (network, parse, rate limit) | Raise `ProviderRetryElsewhere`. | Mark DEGRADED. Try next. |
| Content truly unavailable (deleted, geo-blocked, login-required) | Raise the appropriate `ExtractionFailedError`. | Stop. Do not try other providers — the issue is content, not provider. |
| Vendor library crashed | Raise `InfrastructureError`. | Mark DEGRADED. Try next. |

#### 12.6.9 AI Agent Rule (Provider Abstraction)

AI agents must never:

- Import a provider's vendor module (e.g., `import yt_dlp`) **outside** the corresponding `infrastructure/downloader/providers/<name>_provider.py`.
- Call a provider class directly from `services/`, `bot/`, `api/`, or `workers/`.
- Add special-case logic anywhere that branches on the identity of a specific provider (e.g., `if provider.name == "ytdlp": ...`).
- Hardcode platform-detection logic outside the registry.
- Add a provider-specific column to the schema before V6 without an updated decision-log entry (the `provider_used` column is reserved for V6 — Section 19.3).

All download and metadata-extraction calls must traverse `DownloaderRegistry` via `DownloaderProtocol`. Violations are architectural defects, not style issues.

---

## 13. Configuration Management

### 13.1 Sources (precedence, highest first)

1. Process environment variables.
2. `settings` table (read-through Redis cache).
3. Default values in `core/config.py`.

Env vars are for things that must be available before the database (DB credentials, Sentry DSN, log level). Tunables (limits, cooldowns, retention) live in `settings`.

### 13.2 Environment Variables (LOCKED set; values CONFIGURABLE per env)

| Var | Type | Required | Default | Notes |
|---|---|---|---|---|
| `BOT_TOKEN` | str | yes | — | Secret. Never logged. |
| `BOT_WEBHOOK_URL` | str | no | — | Empty → polling mode. |
| `BOT_WEBHOOK_SECRET` | str | no | — | Required if webhook mode. |
| `BOT_OWNER_TELEGRAM_ID` | int | yes | — | Hard owner. |
| `BOT_PARSE_MODE` | str | no | `HTML` | |
| `BOT_API_BASE_URL` | str | no | — | Empty → public api.telegram.org (50 MB). Set → self-hosted Bot API server (2 GB). D-040. |
| `DEPLOY_ENV` | str | no | `development` | One of `development`/`test`/`production`. `test` activates the §25.6 isolation guards (`core/environment.py`); the simulation runner (§25.15) and e2e harness require it. Added 2026-06-27 (D-060). |
| `PROD_BOT_TOKEN_FINGERPRINT` | str | no | — | SHA-256 hex digest of the **production** bot token (a one-way hash, **not** a secret). When `DEPLOY_ENV=test` and `sha256(BOT_TOKEN)` equals this, the process **refuses to boot** (D-032 production-fingerprint assertion). Empty → check disabled. Added 2026-06-27 (D-060). |
| `DB_HOST` | str | yes | `localhost` | |
| `DB_PORT` | int | yes | `5432` | |
| `DB_NAME` | str | yes | — | |
| `DB_USER` | str | yes | — | |
| `DB_PASSWORD` | str | yes | — | Secret. |
| `DB_POOL_SIZE` | int | no | `10` | |
| `DB_MAX_OVERFLOW` | int | no | `20` | |
| `DB_SSL` | bool | no | `false` | |
| `REDIS_URL` | str | yes | — | Includes auth if needed. |
| `REDIS_CACHE_DB` | int | no | `0` | |
| `REDIS_QUEUE_DB` | int | no | `1` | |
| `WORKER_COUNT` | int | no | `3` | |
| `WORKER_JOB_TIMEOUT` | int | no | `300` | seconds |
| `WORKER_HEARTBEAT_INTERVAL` | int | no | `30` | seconds |
| `WORKER_MAX_RETRIES` | int | no | `3` | |
| `DOWNLOAD_TEMP_DIR` | str | no | `/tmp/downloads` | |
| `YTDLP_PATH` | str | no | `yt-dlp` | |
| `FFMPEG_PATH` | str | no | `ffmpeg` | |
| `CACHE_FILEID_TTL` | int | no | `2592000` | 30d |
| `CACHE_METADATA_TTL` | int | no | `3600` | 1h |
| `CACHE_USER_TTL` | int | no | `30` | seconds (D-014) |
| `CACHE_LOCK_TTL` | int | no | `600` | seconds |
| `CACHE_SETTINGS_TTL` | int | no | `60` | seconds |
| `SENTRY_DSN` | str | no | — | Empty → disabled. |
| `SENTRY_ENVIRONMENT` | str | no | `development` | |
| `SENTRY_TRACES_SAMPLE_RATE` | float | no | `0.1` | |
| `LOG_LEVEL` | str | no | `INFO` | |
| `LOG_FORMAT` | str | no | `json` | `json` or `console` |
| `API_BIND_HOST` | str | no | `0.0.0.0` | |
| `API_BIND_PORT` | int | no | `8080` | |
| `ADMIN_API_KEY` | str | no | — | Secret. Gates the `/v1/admin/*` HTTP surface (§20.2/§20.3). Empty → the admin router is **not mounted** (those paths 404); set → requests need the key in the `X-API-Key` header or get 401. Added 2026-06-25 (D-051), reconciling §20.3 (which named it) with §13.2 (which omitted it). |
| `TELEGRAM_ALERTS_CHAT_ID` | int | no | — | Owner-monitored alert channel. |
| `DEFAULT_LOCALE` | str | no | `en` | The reference-catalog locale (D-061/D-062) — must match an enabled `core/locales/*.json` `_meta.code`; startup fails otherwise. Same category as `BOT_PARSE_MODE` (a deploy-time rendering knob). Added 2026-07-01 (Sprint 11.5). |

### 13.3 Adding an env var

1. Add a row to Section 13.2.
2. Add the field to `core/config.py`.
3. Add the variable to `.env.example`.
4. Add a decision-log entry (Section 5) if behavior changes.

### 13.4 Seeded `settings` keys (LOCKED set)

| Key | Type | Default | Description |
|---|---|---|---|
| `worker_count` | int | `3` | Display only; actual control via env. |
| `free_daily_limit` | int | `10` | |
| `premium_daily_limit` | int | `100` | (V2 will read this.) |
| `free_max_file_size` | int | `52428800` | 50 MiB (D-005). |
| `premium_max_file_size` | int | `2147483648` | 2 GiB. |
| `download_cooldown_seconds` | int | `30` | Free user. |
| `premium_download_cooldown_seconds` | int | `5` | (V2 will read this.) |
| `maintenance_mode` | bool | `false` | |
| `max_file_size` | int | `2147483648` | Global hard cap. |
| `max_duration` | int | `14400` | Seconds (4 h). |
| `rate_limit_messages_per_minute` | int | `30` | |
| `ads_enabled` | bool | `true` | Master switch. |
| `ads_default_frequency` | int | `1` | Override on a per-ad basis. |
| `error_log_retention_days` | int | `90` | D-017. |
| `downloads_retention_days` | int | `365` | |
| `jobs_retention_days` | int | `90` | |
| `history_page_size` | int | `10` | |
| `broadcast_chunk_size` | int | `25` | |
| `providers_enabled` | json | `{"ytdlp": true}` | Section 12.6.7. |
| `provider_priority_overrides` | json | `{}` | Section 12.6.7. |
| `provider_cooldown_seconds` | int | `60` | Section 12.6.7. |
| `provider_health_check_interval_seconds` | int | `120` | Section 12.6.7. |
| `provider_failover_enabled` | bool | `true` | Section 12.6.7. |
| `provider_failure_threshold` | int | `3` | Section 12.6.7. |

### 13.5 Editing settings

- Owner-only via `/setting_set <key> <value>`.
- `SettingsService` validates value against `value_type`.
- `updated_by` and `updated_at` are recorded.
- Redis cache key is invalidated immediately.

### 13.6 `settings` keys — Sprint 9.5 Ads v2 (SEEDED by migration 202606240001)

These keys are **seeded by the Sprint 9.5 migration** (`migrations/versions/202606240001_ads_v2_schema.py`), separate from the LOCKED §13.4 set. D-042–D-044.

| Key | Type | Planned Default | Description |
|---|---|---|---|
| `ads_storage_chat_id` | int | `0` | Bot-owned storage channel id for copy-mode ads (`0` = copy-mode disabled). |
| `ad_placement_post_download_enabled` | bool | `true` | Compat placement (Sprint 9 post-delivery behavior). Default ON. |
| `ad_placement_video_delivery_enabled` | bool | `false` | Persistent ad under video delivery. Opt-in. |
| `ad_placement_audio_delivery_enabled` | bool | `false` | Persistent ad under audio delivery. Opt-in. |
| `ad_placement_quality_select_enabled` | bool | `false` | Persistent ad on the quality-select screen. Opt-in. |
| `ad_placement_home_enabled` | bool | `false` | Persistent ad on the home/start screen. Opt-in. |
| `ad_placement_history_enabled` | bool | `false` | Persistent ad on history pages. Opt-in. |

No new **environment variable** is required for Ads v2 (the storage channel is a `settings` key, not env), consistent with the "no new dependencies / minimal env surface" design goal.

---

## 14. Security Principles

### 14.1 Trust Boundaries

External → user message → bot → service → infrastructure. The bot validates and normalizes; the service layer trusts its inputs to be syntactically valid (but still validates business rules); the infrastructure layer trusts the service layer.

### 14.2 Input Validation

| Input | Where Validated | Action on Failure |
|---|---|---|
| URL | `URLAnalyzerService` (syntactic) + `YtdlpClient` (semantic) | Localized "unsupported URL" message. |
| Callback data | `bot/callbacks/factory.py` (signed schema) | Silently ignore (do not echo). |
| Admin command args | `AdminHandlers` (per-command parser) | Localized usage hint. |
| Setting writes | `SettingsService` (type cast) | Reject with reason. |
| Bot config at startup | `core/config.py` Pydantic validators | Fail fast — process does not start. |

### 14.3 Secrets

- Loaded only from env.
- Never logged. `structlog` has a scrubbing processor that redacts the configured key list (`BOT_TOKEN`, `DB_PASSWORD`, `SENTRY_DSN`, anything containing `secret`, `token`, `password`).
- `Settings.__repr__` is overridden to redact.
- `.env.example` ships in the repo; `.env` is git-ignored.
- Test fixtures use clearly fake values (`bot-token-test-XXXX`).
- Production secrets come from the container orchestrator's secret backend, not from `.env`.

### 14.4 Secrets Rotation

| Secret | Rotation cadence | Process |
|---|---|---|
| `BOT_TOKEN` | On compromise; otherwise yearly. | Generate via @BotFather; deploy via env update; verify with `/start`. |
| `DB_PASSWORD` | Every 90 days. | Create new role; update orchestrator secret; rolling restart; drop old role. |
| `REDIS` auth | Every 90 days. | Same pattern. |
| `SENTRY_DSN` | On compromise. | Sentry project rotation. |
| `BOT_WEBHOOK_SECRET` | Every 90 days. | New random token; update webhook; deploy. |

### 14.5 Rate Limiting

| Scope | Limit (default) | Window | Source |
|---|---|---|---|
| Messages per user | 30 | 1 min | `rate_limit_messages_per_minute` |
| URL analyses per user | 20 | 1 hr | env (`RATE_LIMIT_ANALYSIS_PER_HOUR`) |
| Downloads per user (free) | 10 / day | day | `free_daily_limit` |
| Downloads per user (premium) | 100 / day | day | `premium_daily_limit` (V2) |
| Admin API | 100 | 1 min | FastAPI middleware |

### 14.6 Data Protection

- No raw user message bodies stored. Only the URL portion.
- DB connections SSL in production (`DB_SSL=true`).
- Redis AUTH; TLS optional per environment.
- Temporary downloaded files deleted within 60 s of Telegram upload; otherwise swept by `CleanupWorker`.
- Tracebacks are sanitized (regex scrub of known secret patterns) before being written to `error_logs`.

### 14.7 Telegram-Specific

- Webhook validates `X-Telegram-Bot-Api-Secret-Token`.
- Bot processes only private chats in V1. Group support is reserved.
- Inline callback data is signed (HMAC) with `BOT_WEBHOOK_SECRET` or a derived key, to prevent forgery.

### 14.8 Backups and Disaster Recovery

| Asset | Strategy | RPO | RTO | Verification |
|---|---|---|---|---|
| PostgreSQL | PITR via WAL archive + nightly base backup; retained 30 days; off-site (S3 or equivalent). | ≤ 15 min | ≤ 60 min | **Monthly restore drill** into a clean throwaway environment. |
| Redis | AOF every 1 s; RDB nightly. Treated as a cache and recoverable from PG + bot activity, but a snapshot avoids cold-cache stampede. | ≤ 24 h | ≤ 30 min | Quarterly restore drill. |
| Cached temp files (`/tmp`) | Not backed up — disposable. | — | — | — |
| `cached_files.telegram_file_id` | Backed up with PG. Telegram itself holds the actual file. | with PG | with PG | — |
| Secrets backend | Vendor's own backup. | per vendor SLA | per vendor SLA | — |

DR plan:
1. Provision new compute + storage.
2. Restore Postgres from latest base + WAL.
3. Provision empty Redis; first requests will warm the cache.
4. Update Telegram webhook URL.
5. Smoke test: send /start, send one cached URL, send one fresh URL.

### 14.9 Dependency Hygiene

- All deps pinned in `pyproject.toml`.
- `pip-audit` runs in CI on every PR; high-severity advisories block merge.
- yt-dlp is updated on a monthly cron; the update is gated by a smoke-test PR.
- Base images use minimal slim variants.

---

## 15. Observability

### 15.1 Logging (LOCKED)

- Library: `structlog` with stdlib integration.
- Format: JSON in production, console in development.
- Levels: `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`.
- Standard fields on every record: `timestamp`, `level`, `logger`, `event`, `correlation_id`, `user_id?`, `job_id?`, `worker_id?`, `duration_ms?`, `component`.
- A `SensitiveScrubber` processor redacts known secret keys.

### 15.2 Correlation IDs

Generated by `LoggingMiddleware` (bot) and `LoggingDependency` (API) on every request. Bound into structlog context. Propagated:

- Into the job payload at enqueue time → `jobs.correlation_id`.
- Into `job_waiters.correlation_id` for fan-out attached users (their own request's correlation, not the original).
- Into `error_logs.correlation_id`.

### 15.3 Metrics

- Exposed at `/v1/metrics` in Prometheus exposition format.
- Counters: `downloads_total{platform,format,quality,result}`, `jobs_created_total`, `jobs_completed_total{result}`, `cache_hits_total{cache}`, `cache_misses_total{cache}`, `ads_shown_total`, `broadcasts_sent_total{result}`, `errors_total{type}`.
- Histograms: `job_processing_seconds`, `download_seconds`, `upload_seconds`, `telegram_send_seconds`.
- Gauges: `queue_depth`, `active_workers`, `db_pool_in_use`, `redis_connected`.

### 15.4 Domain Exceptions (LOCKED hierarchy)

```
AppError
├── UserFacingError
│   ├── URLNotSupportedError
│   ├── FormatNotAvailableError
│   ├── FileTooLargeError
│   ├── RateLimitExceededError
│   ├── DailyLimitExceededError
│   ├── CooldownActiveError
│   ├── MaintenanceModeError
│   └── PermissionDeniedError
├── DownloadError
│   ├── ExtractionFailedError
│   ├── DownloadTimeoutError
│   ├── FFmpegProcessingError
│   └── TelegramUploadError
├── DuplicateDownloadError              # internal — drives fan-out path
├── JobNotFoundError
├── CacheError
│   ├── CacheConnectionError
│   └── CacheSerializationError
└── InfrastructureError
    ├── DatabaseConnectionError
    └── RedisConnectionError
```

### 15.5 Sentry

- Initialized in `core/sentry.py`.
- `traces_sample_rate` default 0.1; configurable per env.
- Tags: `component`, `worker_id?`, `job_id?`, `correlation_id`.
- `before_send` strips known secret patterns from event payload.

### 15.6 Telegram Alerts

A small alerter writes critical events (`CRITICAL` log lines and unhandled exceptions captured by Sentry's webhook) to `TELEGRAM_ALERTS_CHAT_ID`. Throttled to one message per 5 minutes per fingerprint.

### 15.7 Health and Readiness (LOCKED endpoints)

| Endpoint | Checks |
|---|---|
| `GET /v1/health` | Process alive. |
| `GET /v1/ready` | DB ping ≤ 500 ms, Redis ping ≤ 500 ms, queue depth read succeeded, worker heartbeat present (or at least one worker registered). |

---

# Part III — Data Flows (Canonical)

## 16. Canonical Data Flows

Each flow below is the **only** valid implementation. Variation requires a Section 5 decision.

### 16.1 New Download (cache miss path)

```
1. User sends URL → DownloadHandlers
2. URLAnalyzerService.analyze(url)
     a. validate syntax
     b. normalize URL
     c. extract (platform, video_id)
     d. GET meta:{platform}:{video_id}
        miss → call YtdlpClient.extract_info → UPSERT media_metadata (COALESCE merge) → SET meta:{…} EX 1h
3. Handler shows format keyboard from MediaInfo
4. User picks format → quality keyboard
5. User picks quality → DownloadHandlers calls JobService.request(user, media, format, quality, correlation_id)

JobService.request:
   T0:  acquire Redis lock SET lock:{m}:{f}:{q} NX EX 600
        success → continue
        miss    → INSERT INTO active_downloads (...) ON CONFLICT DO NOTHING
                  if no row affected → it's a true active duplicate → fan-out path (16.4)
   T1:  SELECT FROM cached_files WHERE media_id=? AND format=? AND quality=?
        hit → release lock, jump to "deliver cached" (16.3)
        miss →
   T2:  INSERT INTO active_downloads (m,f,q,job_id) ON CONFLICT (m,f,q) DO NOTHING
        if 0 rows → fan-out (16.4)
        else  →
   T3:  INSERT INTO jobs (id=uuid7, user_id, media_id, format, quality, correlation_id, ...)
   T4:  INSERT INTO job_waiters (job_id, user_id, correlation_id)
   T5:  QueueService.enqueue(job)
   T6:  return JobAccepted(job_id)

Worker (download_worker.py):
   W0:  BZPOPMIN queue:jobs → job_payload
   W1:  UPDATE jobs SET status='processing', started_at=NOW() WHERE id=?
   W2:  YtdlpClient.download(media) → temp_file_path
   W3:  optional FfmpegClient.transcode if format/quality requires
   W4:  TelegramFileSender.send_to_owner_channel(temp_file) → (file_id, unique_file_id, size)
   W5:  UPSERT INTO cached_files (media_id, format, quality, file_id, unique_file_id, file_size, usage_count+=1, last_used_at=NOW())
   W6:  SELECT waiters = job_waiters WHERE job_id=?
   W7:  For each waiter:
          INSERT INTO downloads (user_id, cached_file_id, platform, format, quality, file_size, status='completed') ON CONFLICT (job_id,user_id) DO NOTHING
          UPDATE users SET total_downloads += 1,
                           daily_download_count = (CASE WHEN daily_download_count_reset_date = CURRENT_DATE THEN daily_download_count + 1 ELSE 1 END),
                           daily_download_count_reset_date = CURRENT_DATE
                WHERE id = waiter.user_id
          TelegramFileSender.send_file_to_user(waiter.user_id, file_id)
          NotificationService.notify_completed(waiter)
          AdService.maybe_show(waiter)
   W8:  DELETE FROM job_waiters WHERE job_id = ?
   W9:  DELETE FROM active_downloads WHERE job_id = ?
   W10: UPDATE jobs SET status='completed', finished_at=NOW()
   W11: DEL lock:{m}:{f}:{q}
   W12: clear temp_file_path
```

### 16.2 New Download (cache hit path)

If T1 hits:

1. Release lock.
2. `INSERT INTO downloads (user_id, cached_file_id, ...) VALUES (..., 'completed')`.
3. Update counters as in W7.
4. `UPDATE cached_files SET usage_count += 1, last_used_at = NOW() WHERE id = ?`.
5. Send file via cached `file_id`.
6. `AdService.maybe_show(user)`.

### 16.3 Resend from History

1. User taps "Resend" → callback → `HistoryHandlers`.
2. `HistoryService.resend(download_id, user)`.
3. `SELECT cf.* FROM downloads d JOIN cached_files cf ON cf.id = d.cached_file_id WHERE d.id = ? AND d.user_id = ?`.
4. If `cached_file_id IS NULL` or row missing → fall back to `JobService.request(...)`. The new job's completion is the user's resend.
5. Otherwise: send file via `cached_file_id.telegram_file_id`; bump `usage_count`; do **not** insert a new `downloads` row (resends do not duplicate history). Per-resend counters live in `cached_files.usage_count` and (V3+) a `resend_events` table if needed.

### 16.4 Fan-Out (duplicate active request)

1. T2 returns 0 rows.
2. `SELECT job_id FROM active_downloads WHERE media_id=? AND format=? AND quality=?`.
3. `INSERT INTO job_waiters (job_id, user_id, correlation_id) ON CONFLICT (job_id, user_id) DO NOTHING`.
4. Reply with progress: "Already in queue, you will receive it shortly."
5. Worker's W6–W8 handle this user identically to the originator.

### 16.5 Rate Limit Check (every download request)

1. `AuthMiddleware` already loaded `user`.
2. `RateLimitService.check_download(user)`:
   - if `user.is_banned` → reject (already caught in middleware, defensive).
   - if `MAINTENANCE_MODE` → `MaintenanceModeError`.
   - resolve effective plan: `premium` if `is_premium and premium_expires_at > NOW()` else `free`.
   - read `<plan>_daily_limit`, `<plan>_download_cooldown_seconds`, `<plan>_max_file_size`.
   - lazy reset: `if user.daily_download_count_reset_date < CURRENT_DATE: reset to 0`.
   - if `daily_download_count >= limit` → `DailyLimitExceededError`.
   - Redis `GET rate:dl_cooldown:{user_id}` → if exists → `CooldownActiveError(retry_after)`.
3. On success, set `SET rate:dl_cooldown:{user_id} 1 EX <cooldown>`.

### 16.6 Daily Counter Reset (lazy, D-012)

There is no nightly job. Every counter increment uses:

```sql
UPDATE users
SET total_downloads = total_downloads + 1,
    daily_download_count = CASE
        WHEN daily_download_count_reset_date = CURRENT_DATE
            THEN daily_download_count + 1
        ELSE 1
    END,
    daily_download_count_reset_date = CURRENT_DATE
WHERE id = ?
```

### 16.7 Ad Delivery (LOCKED — post-increment, D-010)

```
After delivering a file successfully:
  1. read settings:ads_enabled → if false, return.
  2. read user.is_premium and effective role.
  3. SELECT * FROM advertisements
     WHERE is_active = TRUE
       AND (target_role IS NULL OR target_role = effective_role_for_user)
     ORDER BY priority DESC, id ASC
     (consider only the topmost matching candidate first; falling back to next if frequency fails)
  4. For candidate ad:
        if user.is_premium AND ad.target_role IS NULL: skip (premium users see no untargeted ads).
        if user.total_downloads_after_increment % ad.show_every_n_downloads != 0: skip.
        else: select this ad.
  5. Send ad message. UPDATE advertisements SET impressions = impressions + 1 WHERE id = ?.
  6. If ad has button_url, the callback handler increments clicks.
```

### 16.8 Broadcast Flow

```
Owner runs /broadcast (optionally with --lang, --role).
BroadcastService.create(...)
  1. INSERT INTO broadcasts (..., expected_total = COUNT of matching audience, status='pending').
  2. Enqueue a job with worker_kind='broadcast'.

BroadcastWorker:
  1. SELECT broadcast row → mark in_progress.
  2. Stream users in batches of `broadcast_chunk_size` (cursor-paginated by id, filtered by target_*).
  3. For each user:
        try send_message → total_sent += 1
        except → total_failed += 1, write to error_logs.
  4. Update broadcasts row periodically (every chunk).
  5. On completion: status='completed', completed_at=NOW().
```

### 16.9 Error Handling (per layer)

| Layer | What it does |
|---|---|
| Handler | Catches `UserFacingError` → localized response. Catches anything else → generic apology + Sentry + structured log + correlation ID echoed to the user for support. |
| Service | Raises domain exceptions only. Lets `InfrastructureError` propagate. |
| Infrastructure | Translates vendor errors (e.g., `psycopg.OperationalError`) into `DatabaseConnectionError` etc. Implements retry via `tenacity`. |
| Worker | Wraps the entire job in try/finally. On retryable failure: `retry_count += 1`, re-enqueue with `LOW` priority. On non-retryable: `PERMANENTLY_FAILED`, notify waiters, leave `active_downloads` for cleanup. Always: delete temp files, release lock. |

---

# Part IV — Future Versions Readiness

## 17. Future Versions Readiness Review

For each V1 architectural decision, this section states: (a) why it is right for V1, (b) how it scales into V2+, (c) potential limitations, (d) migration strategy if outgrown, (e) scalability ceiling before redesign.

| # | V1 Decision | V1 Rationale | V2+ Scaling Path | Ceiling | Migration if Outgrown |
|---|---|---|---|---|---|
| 1 | Single `queue:jobs` priority queue with `worker_kind` | One queue is simpler; FIFO within priority is enough | V2: add `HIGH` band for premium users; V6: workers self-filter on `worker_kind`. | ~5k jobs/min sustained on one Redis instance | Shard by `worker_kind` if hot kind dominates throughput. |
| 2 | One PostgreSQL primary | Adequate for 20k DAU. Connection pool + PgBouncer. | V3: add read replica for dashboard reads. V4 onward: route reads. | ~50k writes/min sustained | Logical replication to a second primary in another region. |
| 3 | Monthly RANGE partitioning of `downloads`, `jobs`, `error_logs` | Future-proof for 18M rows/year/table. Retention is a partition drop. | Same scheme through V6. | ~24 months without sub-partitioning | Sub-partition by `user_id` HASH if a tenant becomes hot. |
| 4 | `users` row holds counters and ban fields | One-row hot-path read | ~~V2: add `referral_count` column.~~ **Superseded (Sprint 13):** referral tracking shipped as `referred_by_id`/`referral_code`/`referral_bonus_downloads` on `users` plus a separate `referrals` table (D-066), not a single counter column. V4: add `stripe_customer_id`. | Row still narrow at 30+ cols | Move analytic counters to a side table if updates collide. |
| 5 | Settings as key/value with `value_type` | Simple, dynamic | V3 web edit. (i18n did **not** end up using `settings` — Sprint 11.5 discovers locales from `core/locales/*.json` instead, D-062.) | ~1k keys (still fits in a single PG row scan) | Switch to JSONB document per category. |
| 6 | `DownloaderRegistry` + `DownloaderProtocol` shipped in V1 even though V1 has one provider | Builds the abstraction before it is forced. ~200 LOC up front prevents a V6 refactor that would touch every service. | V6 only adds provider implementations; registry, failover, health, and settings already exist. Zero changes to services or handlers. | unchanged | None — already in place. |
| 7 | Per-process composition root | Easy to reason about | V3 splits API into its own service; V4 may split payment webhook into a dedicated process | unchanged | Same pattern in new processes. |
| 8 | Redis as cache + queue + locks (one cluster) | Operationally simple | V2 split logical DBs already done. V3+: separate Redis instances for queue vs. cache when workloads diverge. | ~20k qps per instance | Move queue to its own Redis. |
| 9 | UUIDv7 for `jobs.id` | Time-ordered; non-enumerable | All later versions inherit | unchanged | n/a |
| 10 | `target_role` enum on ads | Extends to V2 premium tier with zero schema change | unchanged | unchanged | Widen enum. |
| 11 | API versioned under `/v1/` | Cheapest path to V2 dashboard | V3 introduces `/v2/` with breaking changes; old endpoints stay until deprecated | unchanged | Maintain two prefixes during deprecation window. |
| 12 | ~~i18n strings centralized but unused in V1~~ **Superseded (Sprint 11.5):** i18n shipped in V1 — en/ar catalogs, both live. | Single canonical message catalog **is the reference locale** (D-062); every other locale is validated as a subset of it at startup. | Additional locales: drop in one more `core/locales/*.json` file. | unchanged | None. |
| 13 | `job_waiters` table | Durable fan-out from day one | V2 "multiple links per request" still uses fan-out at media-id level; one user → many `job_waiters` rows | unchanged | None. |
| 14 | `engine_used` column reserved on `media_metadata` | V6 fallback | V6: write per-attempt rows in a future `download_attempts` log; engine tag travels | unchanged | Add the attempts log table. |
| 15 | `correlation_id` propagated to DB rows | Tracing from message to job to error | All versions improve on this | unchanged | None. |

## 18. Extension Points Catalog

Each row is a place V1 leaves intentionally open for a future version. V1 must **not** close any of these.

| ID | Extension Point | Location | Future Use |
|---|---|---|---|
| EP-1 | ~~`users.referred_by BIGINT NULL FK → users.id` (not yet added)~~ **Realized (Sprint 13, D-066).** `users.referred_by_id` (self-FK, `ON DELETE SET NULL`) + `referral_code` (unique) + `referral_bonus_downloads`, plus a new `referrals` table (one row per successful referral, `referred_id` unique) — richer than the original single-column sketch. | `users`, `referrals` | Closed. V5 may extend with payment-linked tiers once V4 payments exist. |
| EP-2 | `users.stripe_customer_id VARCHAR(255) NULL` (not yet added) | `users` | V4 Stripe. |
| EP-3 | `user_preferences.preferred_language` | `user_preferences` | **Superseded, not consumed (Sprint 11.5).** i18n shipped in V1 via `users.language` instead (D-061); this column remains reserved/unused for a possible distinct future purpose. |
| EP-4 | Settings `premium_*` keys seeded | `settings` | V2 reads. |
| EP-5 | `target_role` on ads supports `'premium'` value | `advertisements` | V2 ad targeting. |
| EP-6 | Priority `HIGH` band reserved | queue | V2 premium queue. |
| EP-7 | `engine_used` column on `media_metadata` (planned migration in V6) | `media_metadata` | V6 multi-engine. |
| EP-8 | Single FastAPI app with `/v1/` prefix | `api/` | V3 web dashboard; V4 payment webhooks. |
| EP-9 | `worker_kind` column on `jobs` | `jobs` | V2 (broadcast workers), V6 (multi-engine). |
| EP-10 | `job_waiters` table | new | V2 multi-link batched requests. |
| EP-11 | ~~i18n loader in `NotificationService` accepts a `locale` arg, even though V1 always passes `en`~~ **Realized (Sprint 11.5).** `locale` is now a required param, resolved per-recipient (D-063), and every send routes through `core.i18n.translate`. | `services/notification_service.py` | Closed — further languages are additive catalog files, not code changes. |
| EP-12 | `advertisements.button_url` | ads | V4/V5 promotional links. |
| EP-13 | `value_type` on settings | settings | V3 web UI form generation. |
| EP-14 | `jobs.correlation_id` | jobs | All versions; basis for V3 dashboard "see this job's whole story". |
| EP-15 | `broadcasts.expected_total` | broadcasts | V3 dashboard progress display. |
| EP-16 | `DownloaderRegistry` accepts `register(provider)` and routes by `priority` and `supported_platforms` | `infrastructure/downloader/registry.py` | V6 multi-engine adds providers without service-layer changes. The single most important V1→V6 extension. |
| EP-17 | `provider_used` column reserved on `media_metadata` (added in V6 only) | `media_metadata` (migration in V6) | Per-row provenance for fallback diagnostics. Not added in V1 because 100% of rows would have the same value. |
| EP-18 | `Capability` enum (`VIDEO`, `AUDIO`, ...) is open to additive values | `domain/enums/` | V6 may add `LIVE_STREAM`, `PLAYLIST`, `IMAGE`. |
| EP-19 | Ads v2 `advertisements` + `ad_audience_rules` are open to a future `campaign_id` + `variant_group`/`weight` (weighted selection) | `advertisements` (Sprint 9.5 schema) | Monetization: partner **campaigns**, **A/B testing**, **sponsored placements**. Additive columns + a `ad_campaigns` table; no change to the selection contract. |
| EP-20 | Ads v2 `ad_audience_rules.dimension` reserves `country` | `ad_audience_rules` (Sprint 9.5 schema) | Geo-targeting once a user→region source exists. Additive rule rows; evaluator already iterates dimensions. |
| EP-21 | `AdButtonSpec.callback_data` (reserved) + a future `quota` placement | `services/ad_service.py`, rate-limit error path | F-1 quota-unlock sponsored ads (#32): tracked-click "Open Sponsor" button + unlock side-effect. |
| EP-22 | `CallbackSigner` accepts new action prefixes; admin services already command-driven | `bot/handlers/` | F-2 admin inline control panel (#33): signed-callback keyboards delegating to existing services. |
| EP-23 | `AdService.create`/`add_button` + copy-mode are operation-complete | `bot/handlers/` (FSM) | F-3 rich ad builder (#34): an FSM wizard over the existing ad operations. |

## 19. Database Evolution Strategy

### 19.1 Migration Rules (LOCKED)

1. Every schema change goes through Alembic. Never edit migrations after they merge.
2. Migrations are **additive-first**:
   - Adding columns: allowed any sprint.
   - Adding tables/indexes/constraints: allowed any sprint.
   - Adding NOT-NULL columns to non-empty tables: requires two-step migration (add nullable + backfill + alter to NOT NULL).
   - Renaming columns: requires three-step migration (add new, dual-write, switch reads, drop old).
   - Dropping columns or tables: requires Owner approval and a deprecation window of at least one sprint.
3. Every migration has a descriptive name and a docstring describing the change and its motivation.
4. Migrations are forward-only. Down-migrations are written but never run in production; they are a development convenience.
5. Migrations are tested on a copy of production-sized data before promotion.

### 19.2 Versioned Migration File Naming

`migrations/versions/{YYYYMMDDHHMM}_{slug}.py` — e.g., `202607151430_add_referred_by.py`. The timestamp prefix establishes ordering.

### 19.3 Roadmap of Schema Changes

| Version | Migration | Description |
|---|---|---|
| V1 Sprint 1 | Initial schema | Tables 1–12 created, partitions seeded, indexes created. |
| V1 Sprint 9.5 | `202606240001_ads_v2_schema` | **Applied**. ALTERs `advertisements` (placement, delivery_mode, storage_chat_id, storage_message_id, parse_mode, audience_mode; widens `type` via the domain enum); ALTERs `broadcasts` (`advertisement_id`); creates `ad_buttons`, `ad_audience_rules`, `audience_segments`, `audience_segment_members`; adds `ix_ads_placement_active_priority`; seeds the Section 13.6 keys. Additive-only — no data backfill (AdService dual-reads legacy ads). D-042–D-045. |
| V1 Sprint 9.5.10 | `202606250002_scheduling` | **Applied**. Adds nullable `broadcasts.scheduled_at` + `advertisements.scheduled_at` and a partial index `ix_broadcasts_scheduled` (pending + scheduled rows). Additive-only; NULL preserves immediate/always-eligible behavior. D-053. |
| V1 Sprint 9.6 | `202606270001_unified_audience` | **Applied**. Creates `audience_expressions` + `audience_rules` + `ix_audience_rules_expression`; adds nullable `audience_expression_id` FK (ON DELETE SET NULL) to `advertisements` + `broadcasts`; backfills an equivalent expression per ad that has `ad_audience_rules`. Additive; legacy rules retained + dual-read. D-055. |
| V1 Sprint 9.6 | `202606270002_multi_placement_and_internal_metadata` | **Applied** (head `202606270002`). Creates `ad_placements` (+`ix_ad_placements_placement`), backfills one row per ad from the scalar `placement`; adds `advertisements.internal_name` + `internal_notes` (admin-only). Additive; scalar `placement` retained + dual-read. D-056/D-058. |
| V1 Sprint 9.5.9 | `202606250001_ad_events` | **Applied**. Creates the partitioned `ad_events` analytics table (monthly RANGE by `created_at`, like `error_logs`) + `ix_ad_events_ad` / `ix_ad_events_type_created`; seeds a rolling 13-month partition window. Additive-only; no FKs (analytics-write cheapness). Promoted from `migrations/planned/`. Rows written off the delivery hot path (D-052). The cleanup worker keeps partitions rolling via `RUNTIME_PARTITIONED_TABLES`; `ad_events` has no retention key, so it is not auto-dropped (D-052). D-045. |
| V2 | `add_premium_columns` | (None — already present.) |
| V2 | `add_default_format_quality_to_preferences` | V2 power-user preferences. |
| V3 | `add_admin_audit_log` | New `audit_logs` table for the web dashboard. |
| V3 | `add_resend_events` | If per-resend analytics desired. |
| V4 | `add_payments_subscriptions_plans` | New tables: `payments`, `subscriptions`, `premium_plans`. |
| V4 | `add_stripe_customer_id_to_users` | EP-2. |
| V5 | `add_referrals_referral_codes` | New tables; `users.referred_by`. |
| V6 | `add_engine_used_to_media_metadata` | EP-7. |
| V6 | `add_download_attempts` | Per-attempt log for fallback diagnostics. |

### 19.4 Adding a New Table Checklist

1. Add a section in Section 10.
2. Write the Alembic migration (additive).
3. Add the SQLAlchemy model under `infrastructure/database/models/`.
4. Add a repository protocol under `domain/protocols/repositories.py`.
5. Add a repository implementation under `infrastructure/database/repositories/`.
6. Wire the repository into the relevant service via the composition root.
7. Add tests: schema test (column types), repository test (CRUD), service test (behavior).
8. Add a Component Card to Section 9.
9. Add a decision-log entry to Section 5.

## 20. API Evolution Strategy

### 20.1 Versioning (D-019)

All endpoints live under `/v1/...`. When V3 introduces breaking changes:
- New endpoints go under `/v2/`.
- V1 endpoints continue to work for one full version cycle (V3 + V4) as deprecated.
- A `Deprecation` HTTP header announces removal date.

Within a major prefix:
- Adding endpoints: additive, no version bump.
- Adding optional fields to responses: additive.
- Adding required request fields: forbidden — must wait for next major.
- Renaming or removing fields: forbidden within the same major.

### 20.2 V1 Endpoint Surface (LOCKED)

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/v1/health` | Liveness | none |
| `GET` | `/v1/ready` | Readiness | none |
| `GET` | `/v1/metrics` | Prometheus | network ACL |
| `GET` | `/v1/admin/stats` | System stats | admin API key |
| `GET` | `/v1/admin/users` | List/search users | admin API key |
| `GET` | `/v1/admin/users/{id}` | User detail | admin API key |
| `POST` | `/v1/admin/users/{id}/ban` | Ban (audit) | admin API key (owner only) |
| `POST` | `/v1/admin/users/{id}/unban` | Unban | admin API key (owner only) |
| `GET` | `/v1/admin/jobs` | List/search jobs | admin API key |
| `GET` | `/v1/admin/queue` | Queue summary | admin API key |
| `GET` | `/v1/admin/errors` | Browse `error_logs` | admin API key |
| `GET` | `/v1/admin/settings` | List settings | admin API key |
| `PUT` | `/v1/admin/settings/{key}` | Update a setting | admin API key (owner only) |

### 20.3 Auth

V1 admin endpoints use a single admin API key from env (`ADMIN_API_KEY`, now in the §13.2 LOCKED set — D-051). The key travels in the `X-API-Key` request header and is compared in constant time. When `ADMIN_API_KEY` is unset the entire `/v1/admin/*` surface is **not mounted** — those paths return 404 ("silently ignored", consistent with the bot's owner-only-commands behavior); when it is set, a missing/wrong key returns 401. With a single shared key there is no per-request HTTP identity in V1, so the "(owner only)" markers in the §20.2 table collapse to "valid-key-only" (the key is the owner's). V3 introduces JWT-based auth that backs a web dashboard; the V1 key path stays usable for tooling.

## 21. Queue and Worker Scalability

### 21.1 Scaling Tiers

```
V1 (single host)
  bot × 1
  worker × N (WORKER_COUNT env)
  api × 1
  postgres × 1
  redis × 1
  pgbouncer × 1
  uptime-kuma × 1

V2 (vertical + tuning)
  Larger CPU/RAM
  WORKER_COUNT raised
  Redis tuned

V3 (separation)
  bot, worker, api split across hosts
  PG behind PgBouncer
  Read replica for dashboard

V4 (distributed workers)
  Many worker hosts pulling from one Redis queue
  PG main + read replicas
  Separate Redis for queue vs. cache

V6 (multi-engine workers)
  Several download_worker types — yt-dlp / gallery-dl / direct HTTP
  Same queue, filtered by worker_kind
```

### 21.2 Worker Scaling Rules

1. Workers are stateless aside from their current job.
2. Job timeouts (`WORKER_JOB_TIMEOUT`) ensure no worker holds a slot forever.
3. Heartbeats expire after `2 × WORKER_HEARTBEAT_INTERVAL`; stale workers are detected by `CleanupWorker` and their in-flight jobs are re-queued.
4. New worker types subclass the same protocol and are wired in `workers/main.py`. They do not require schema changes.

### 21.3 Queue Failure Modes

| Failure | Mitigation |
|---|---|
| Redis down briefly | Jobs in flight time out; restart processes; `active_downloads` table is the durable record; cleanup worker re-queues. |
| Redis full restart (data loss) | `active_downloads` rows survive in PG; cleanup worker re-creates queue entries from non-terminal `jobs` rows on startup. |
| Worker host dies mid-job | Heartbeat expires; cleanup re-queues; idempotency makes re-execution safe. |
| Queue depth spikes | Dashboard alerts at 100; scale `WORKER_COUNT`. |

---

# Part V — Execution

## 22. Master Execution Plan

### 22.1 From Current State to V1 Launch

**Current state (2026-06-23):** Empty working directory; reference docs only. No code.

**Implementation order — fundamental rule:** any artifact depended on by another artifact must be implemented first. The order below reflects that.

1. **Sprint 0 — Bootstrap.** Repo, tooling, CI, docker-compose, base layout, no business logic.
2. **Sprint 1 — Foundation.** Config, logging, Sentry, core helpers (UUIDv7), structured error hierarchy.
3. **Sprint 2 — Persistence layer.** Postgres schema, all 12 tables, partitioning, repositories, settings seed, Alembic baseline.
4. **Sprint 3 — Cache and queue.** Redis client, key schema enforcement, queue primitives, distributed lock, settings cache, user cache.
5. **Sprint 4 — User identity.** `UserService`, ban/role rules, `AuthMiddleware`, throttle middleware.
6. **Sprint 5 — URL analyzer + provider abstraction.** `DownloaderProtocol`, `DownloaderRegistry`, `YtdlpProvider` (sole V1 provider), `URLAnalyzerService`, metadata cache, format/quality keyboards. Provider abstraction lands here, not in V6 — services consume it via the registry from the moment URL analysis exists.
7. **Sprint 6 — Job pipeline (single user, no fan-out).** `JobService`, `DownloadService`, `DownloadWorker`, `TelegramFileSender`, end-to-end download.
8. **Sprint 7 — Fan-out and resend.** `job_waiters`, multi-user fan-out, history, instant resend.
9. **Sprint 8 — Admin and ops.** Statistics, ban/unban commands, settings commands, broadcasts (with `BroadcastWorker`).
10. **Sprint 9 — Ads.** `AdService`, admin ad CRUD, ad delivery hook.
11. **Sprint 10 — Observability and backup.** Sentry integration end-to-end, metrics endpoint, Telegram alerts, health/readiness, PgBouncer, backup-restore drill, operational runbook.
12. **Sprint 11 — Testing framework, security validation, load and stress.** Sandbox bot, E2E harness, full security suite, user simulation framework (5 profiles + traffic generators), load levels L1–L4, stress scenarios ST-1 through ST-6, capacity report.
13. **Sprint 12 — Launch readiness.** Production deploy, smoke tests, E2E re-runs in production, owner training.

Each sprint ships independently usable code. The bot is runnable from Sprint 6 onward (single-user). Production launch occurs at the end of Sprint 12.

### 22.2 Why this order

- **Bootstrap before everything** so every later step lands in CI.
- **Persistence before services** so services can be tested with real storage.
- **Cache + queue before the user-facing services** so services use the real protocols immediately, not stubs.
- **Auth/throttle before any handler** so every handler is gated correctly from inception.
- **URL analyzer before job pipeline** because the pipeline depends on a `MediaInfo`.
- **Single-user pipeline before fan-out** because fan-out is layered on top of a working pipeline.
- **Admin/ads after the user pipeline** because ad delivery hooks the post-download point.
- **Hardening last** because it tests the whole thing.

### 22.3 Critical-Path Dependencies

| Sprint | Depends On |
|---|---|
| S1 | S0 |
| S2 | S1 |
| S3 | S2 |
| S4 | S2, S3 |
| S5 | S2, S3 |
| S6 | S4, S5 |
| S7 | S6 |
| S8 | S7 |
| S9 | S7 |
| S10 | S9 |
| S11 | S10 |
| S12 | S11 |

## 23. Sprint Plan

The remainder of this section defines each sprint in detail. The format for every sprint:

> **Goal · Scope · Tasks · Validation Checklist · Exit Criteria · Human Verification Required · Stop Point · Risks · Testing Requirements**

The AI agent **stops at every sprint's stop point** and waits for explicit Owner approval before starting the next sprint.

---

### Sprint 0 — Bootstrap

**Goal:** A repository in which every later sprint can land code with zero infrastructure friction.

**Scope:** Tooling, layout, CI, local stack. No business logic.

**Tasks**

- **0.1** Initialize git repo. `.gitignore` for Python, IDE, `.env`, temp files.
- **0.2** Create `pyproject.toml`. Add pinned dependencies from Section 6.1 and 6.2 (only those needed by Sprint 0: `pydantic`, `pydantic-settings`, `structlog`, `ruff`, `mypy`, `pytest`, `pytest-asyncio`).
- **0.3** Create the directory tree in Section 7 with `__init__.py` placeholders, including every `tests/` subdirectory listed in Section 25.2 (`unit`, `integration`, `security`, `performance`, `e2e`, `regression`, `simulation`). No non-empty files.
- **0.4** Add `ruff` config, `mypy.ini` (strict), pre-commit config (`.pre-commit-config.yaml`).
- **0.5** Add CI workflow (`.github/workflows/ci.yml`) running: lint, type-check, tests, `pip-audit`, `bandit`.
- **0.6** Add an import-linter config enforcing Section 8 dependency rules. CI runs it.
- **0.7** Add `.env.example` containing every key from Section 13.2.
- **0.8** Add `deploy/docker-compose.yml` with postgres-15, redis-7, pgbouncer, uptime-kuma services. No app containers yet.
- **0.9** Add `deploy/Dockerfile.bot`, `Dockerfile.worker`, `Dockerfile.api` skeletons (multi-stage; final image based on slim).
- **0.10** Add `MASTER_PLAN.md` (this file) reference in `README.md`.

**Validation Checklist**

- [ ] `ruff check .` clean.
- [ ] `mypy --strict .` clean (passes on empty packages).
- [ ] `pytest -q` runs and shows 0 collected tests (no errors).
- [ ] `docker-compose up -d` brings postgres, redis, pgbouncer, uptime-kuma online.
- [ ] `pip-audit` reports no high-severity issues.
- [ ] `import-linter` reports no violations on the empty tree.
- [ ] `.env.example` lists every key in Section 13.2.

**Exit Criteria**

1. Validation checklist passes.
2. CI green on `main`.
3. `docker-compose up` and `docker-compose down` cycle works.

**Human Verification Required**

- Confirm the chosen Sentry environment naming (`production`, `staging`, `development`).
- Confirm CI provider choice (GitHub Actions, GitLab CI, etc.) and account access.
- Confirm hosting target (managed VPS, cloud, on-prem) so deployment can be tailored.

**Stop Point**

Agent stops. Owner reviews `pyproject.toml`, `docker-compose.yml`, and CI workflow. Approval required to begin Sprint 1.

**Risks**

| Risk | Mitigation |
|---|---|
| Tooling churn (ruff/mypy config drift) | Lock versions in `pyproject.toml`. |
| Wrong Python version on CI | Pin in CI workflow. |
| Docker image bloat | Multi-stage builds. |

**Testing Requirements**

- No business tests. Only configuration validates above.

---

### Sprint 1 — Foundation

**Goal:** `core/` is real, useful, and tested.

**Scope:** Config, logging, Sentry, UUIDv7, constants, base error hierarchy.

**Tasks**

- **1.1** Implement `core/config.py` using `pydantic-settings`. One `Settings` class covering all env keys in Section 13.2 with validators. `__repr__` redacts secrets.
- **1.2** Implement `core/logging.py`: structlog setup with `SensitiveScrubber`, JSON vs. console toggle, correlation-ID context handling.
- **1.3** Implement `core/sentry.py`: SDK init guarded on DSN; integrations (Aiogram, FastAPI, SQLAlchemy, Redis, asyncio); `before_send` scrubber.
- **1.4** Implement `core/uuid7.py`: pure 80-line implementation (D-013, D-023).
- **1.5** Implement `core/constants.py`: priorities, role values, format/quality enums (imported by `domain/enums/`).
- **1.6** Implement `domain/exceptions.py` exactly matching Section 15.4.
- **1.7** Implement `domain/enums/` with `JobStatus`, `UserRole`, `MediaFormat`, `Quality`, `ErrorType`, `AdType`.
- **1.8** Wire `core/logging.py` into a tiny `__main__` test entry that emits one structured log line.
- **1.9** Unit tests for each `core/` module.

**Validation Checklist**

- [ ] `Settings()` builds from `.env.example` (with safe placeholders) without raising.
- [ ] `core/logging.py` emits JSON in JSON mode with the correct keys.
- [ ] `SensitiveScrubber` redacts a sample token in a log message under test.
- [ ] `core/uuid7.py` returns monotonically non-decreasing UUIDs across 1000 calls within 1 ms intervals.
- [ ] `core/sentry.py` is a no-op when `SENTRY_DSN` is empty (verified by patching the SDK init).
- [ ] All `domain/enums/` and `domain/exceptions.py` import cleanly.
- [ ] `mypy --strict` clean. `ruff` clean.

**Exit Criteria**

1. Validation passes.
2. Unit test coverage for `core/` ≥ 90%.
3. Section 9 cards for all `core/` components are present.

**Human Verification Required**

- Inspect a sample JSON log line. Confirm field naming.
- Approve the redaction key list in `SensitiveScrubber`.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 2.

**Risks**

| Risk | Mitigation |
|---|---|
| UUIDv7 implementation drift across processes | Single implementation in `core/uuid7.py`; test for monotonicity within process. |
| Settings field types that change later | Use Pydantic v2; cast at boundary. |

**Testing Requirements**

- Unit tests for every module in `core/`.
- A "smoke" test that imports the whole `core/` and `domain/` package tree.

---

### Sprint 2 — Persistence Layer

**Goal:** Postgres holds every V1 table; repositories are tested against a real database.

**Scope:** Alembic baseline, ORM models, partitions, repositories, settings seed.

**Tasks**

- **2.1** Configure Alembic. Connection string from `core/config.py`.
- **2.2** Write the baseline migration: create tables 1–12 exactly per Section 10. Set up monthly partitioning for `downloads`, `jobs`, `error_logs` (initial 12 partitions). Create all indexes and FK constraints.
- **2.3** Write the seed migration: insert `settings` keys from Section 13.4. Insert the Owner user (Telegram ID from env). No other data.
- **2.4** Implement `infrastructure/database/engine.py` and `session.py`. AsyncEngine, AsyncSession factory.
- **2.5** Implement ORM models in `infrastructure/database/models/` (one file per table).
- **2.6** Implement repository protocols in `domain/protocols/repositories.py`.
- **2.7** Implement repository classes in `infrastructure/database/repositories/`: `UserRepository`, `MediaRepository`, `CachedFileRepository`, `DownloadRepository`, `JobRepository`, `ActiveDownloadRepository`, `JobWaiterRepository`, `BroadcastRepository`, `AdRepository`, `SettingsRepository`, `ErrorLogRepository`, `UserPreferenceRepository`.
- **2.8** Write a partition rollover helper: `ensure_partitions_for_next_n_months(n=12)`. Tested with a fake clock.
- **2.9** Integration tests against postgres-15 in CI service container.

**Validation Checklist**

- [ ] `alembic upgrade head` on an empty DB creates 12 tables, 3 partitioned, 24+ partitions seeded.
- [ ] `\d+ downloads` shows monthly partitions for the rolling 12 months.
- [ ] Every table's columns match Section 10 row-for-row (verified by an introspection test).
- [ ] Every FK and ON DELETE action matches Section 10.14.
- [ ] Every index in Section 10 exists.
- [ ] All seeded settings rows are present with the correct `value_type`.
- [ ] Each repository has at least: create, read by id, list paginated, delete (where applicable). Tests pass.
- [ ] Lazy `daily_download_count` reset works for a user crossing midnight.
- [ ] `JobRepository.create` accepts an externally generated UUIDv7.
- [ ] Partition rollover helper creates next month's partition with one day's lead.

**Exit Criteria**

1. Validation passes.
2. Integration test coverage for repositories ≥ 80%.
3. Alembic baseline merged.
4. All schema deviations vs. Section 10 logged as decisions (or rejected and fixed).

**Human Verification Required**

- Run `alembic upgrade head` locally and inspect `psql \d` output for a sample table.
- Approve the partition naming scheme (suggested: `downloads_y2026m07`).

**Stop Point**

Agent stops. Owner reviews schema. Approval required to begin Sprint 3.

**Risks**

| Risk | Mitigation |
|---|---|
| FK to a partitioned table requires PG 15+ | Pinned in Section 6.1. |
| Partition pruning broken by wrong index on parent | All indexes created on partitions, not parents. |
| Seed data conflicts on re-run | Use ON CONFLICT DO NOTHING for seeds. |

**Testing Requirements**

- Schema introspection test (compares actual schema to Section 10).
- Repository CRUD tests for each repo.
- Partition rollover test.

---

### Sprint 3 — Cache and Queue

**Goal:** Every Redis interaction goes through the documented key scheme and is testable.

**Scope:** Redis client, cache, queue, locks. No business code yet.

**Tasks**

- **3.1** Implement `infrastructure/redis/client.py`: connection manager, separate DBs for cache (0) and queue (1).
- **3.2** Implement `infrastructure/redis/cache.py` implementing `CacheProtocol`. Methods: `get`, `set`, `delete`, `incr_with_ttl`. Enforces Section 11.4 key scheme via static keys (do not let callers pass raw strings).
- **3.3** Implement `infrastructure/redis/locks.py`: distributed lock with TTL, `acquire`/`release` returning a token to prevent foreign release.
- **3.4** Implement `infrastructure/redis/queue.py` implementing `QueueProtocol`. Sorted-set scoring per Section 12.2. Atomic dequeue + move to active set via Lua script.
- **3.5** Implement service-side wrappers: `services/cache_service.py`, `services/queue_service.py`. These are thin and delegate; they exist for testability and clarity.
- **3.6** Implement `services/settings_service.py`: read-through cache, type-cast, write-through invalidation.
- **3.7** Integration tests against real Redis (CI service container).

**Validation Checklist**

- [ ] Putting + getting a `file_id` round-trips.
- [ ] Distributed lock prevents concurrent `acquire` by two pseudo-clients.
- [ ] Lock token foreign-release rejection works.
- [ ] Enqueue + dequeue with priority returns lower-priority first.
- [ ] Enqueue 1000 jobs; dequeue concurrently from two workers; no duplicates.
- [ ] `SettingsService.get("free_daily_limit")` returns the int 10 (cast from text seed).
- [ ] `SettingsService.set` updates DB and invalidates Redis.
- [ ] `CacheService` never accepts raw key strings (only typed methods).

**Exit Criteria**

1. Validation passes.
2. Coverage for `infrastructure/redis/` ≥ 80%.
3. All Section 11.4 keys are emitted by exactly one helper method.

**Human Verification Required**

- Confirm queue priorities behave correctly under hand-tested mixed batch.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 4.

**Risks**

| Risk | Mitigation |
|---|---|
| Lua script bugs (atomic dequeue) | Test with concurrent dequeue. |
| Race between lock release and TTL expiry | Token-tagged release. |
| TTL drift between cache and source-of-truth | TTLs documented; integration test for staleness. |

**Testing Requirements**

- Concurrent enqueue/dequeue test.
- Lock contention test.
- Cache invalidation test.

---

### Sprint 4 — User Identity

**Goal:** Every Telegram update results in a properly authenticated, throttled handler call.

**Scope:** `UserService`, `RateLimitService`, `AuthMiddleware`, `ThrottleMiddleware`, `LoggingMiddleware`, `DbSessionMiddleware`.

**Tasks**

- **4.1** Implement `services/user_service.py`: `get_or_create_user(telegram_user)`, `set_role`, `ban`, `unban`, `record_activity`, user-cache reads/writes (D-014).
- **4.2** Implement `services/rate_limit_service.py`: download cooldown, daily-limit check (lazy reset), message-rate window.
- **4.3** Implement `bot/middlewares/logging.py`: bind UUIDv7 correlation ID.
- **4.4** Implement `bot/middlewares/db_session.py`: session per update, commit/rollback semantics.
- **4.5** Implement `bot/middlewares/auth.py`: load user via `UserService`, reject if banned with localized message.
- **4.6** Implement `bot/middlewares/throttle.py`: enforce `rate_limit_messages_per_minute`.
- **4.7** Implement `bot/filters/role_filter.py`: declarative role gating.
- **4.8** Implement minimal `bot/handlers/start.py` and `bot/handlers/help.py` (no business logic, prove the pipeline).
- **4.9** Implement `bot/main.py` composition root wiring up the pipeline. Long-polling mode supported. Webhook mode supported but optional.

**Validation Checklist**

- [ ] `/start` from an unknown user creates a `users` row with correct defaults.
- [ ] Second `/start` from the same user reuses the row (no duplicate).
- [ ] Banned user receives only the ban message; handlers are skipped.
- [ ] 31 messages in 60 s from one user → message 31 returns rate-limit response.
- [ ] Owner ID from env is recognized as `owner` role.
- [ ] Correlation ID appears on every log line emitted by the request flow.
- [ ] `record_activity` is debounced (write at most every 5 s per user).
- [ ] User cache hit ratio in a synthetic test reaches > 95% after warm-up.

**Exit Criteria**

1. Validation passes.
2. Bot runs against the real Telegram API in a sandbox channel and responds to `/start` and `/help`.
3. No service imports infrastructure directly (`import-linter` green).

**Human Verification Required**

- Send `/start` from the Owner's Telegram account; confirm the Owner role.
- Send `/start` from a second account; confirm `user` role.
- Test ban/unban via direct SQL; confirm the banned account is blocked.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 5.

**Risks**

| Risk | Mitigation |
|---|---|
| Aiogram middleware ordering pitfalls | Order documented and tested. |
| Hot-path PG hits if user cache misses | Section 11.3 invalidation rules tested. |

**Testing Requirements**

- Unit tests for `UserService` and `RateLimitService`.
- Integration tests for each middleware in isolation.
- End-to-end: synthetic Aiogram updates through the full middleware stack.

---

### Sprint 5 — URL Analyzer

**Goal:** Given a URL, the user is shown a clean keyboard of available formats and qualities.

**Scope:** `DownloaderProtocol`, `DownloaderRegistry`, `YtdlpProvider`, `URLAnalyzerService`, metadata cache, format/quality keyboards.

**Tasks**

- **5.1** Define `domain/protocols/downloader.py`: `DownloaderProtocol` with `extract_info`, `download`; plus `Capability` enum and `ProviderHealth`, `ProviderUnsupported`, `ProviderRetryElsewhere`.
- **5.2** Implement `infrastructure/downloader/registry.py` (`DownloaderRegistry`) per Section 12.6.3: registration, platform detect, candidate selection, failover, health update on outcome.
- **5.3** Implement `infrastructure/downloader/providers/ytdlp_provider.py`: subprocess wrap; JSON parsing; map vendor errors to domain exceptions; declare `name="ytdlp"`, `supported_platforms={"*"}`, `capabilities={VIDEO, AUDIO}`, `priority=100`; implement `health_check()`.
- **5.4** Implement background `provider_health_check_task` in `workers/main.py`, runs every `provider_health_check_interval_seconds`.
- **5.5** Implement `services/url_analyzer.py`: URL validation; `(platform, video_id)` extraction; metadata cache lookup; on miss, call **`DownloaderRegistry.extract_info`** (never the provider directly); UPSERT `media_metadata` with COALESCE merge (D-011); cache write.
- **5.6** Implement format-extraction post-processing (provider-agnostic) producing a deduplicated, sorted list of `(format, quality, approx_size)`.
- **5.7** Implement `bot/keyboards/format_select.py` and `bot/keyboards/quality_select.py`.
- **5.8** Implement `bot/callbacks/factory.py`: signed callback data carrying `media_id`, `format`, `quality`.
- **5.9** Update `bot/handlers/download.py` to receive a URL and present the format keyboard.
- **5.10** Register `YtdlpProvider` in `bot/main.py` and `workers/main.py` composition roots.
- **5.11** Lint check (`import-linter` rule): nothing under `services/`, `bot/`, `workers/`, `api/` imports `yt_dlp` or `infrastructure.downloader.providers.*` directly.

**Validation Checklist**

- [ ] Hand-test 5 sample URLs across platforms: each returns a sensible format list within 3 s p95 (warm cache 200 ms p95).
- [ ] Sending the same URL again hits the metadata cache.
- [ ] An unsupported URL returns `URLNotSupportedError` translated to a user-friendly message.
- [ ] An invalid URL returns the same.
- [ ] Callback data is rejected if its signature is wrong.
- [ ] COALESCE merge keeps a previously richer `metadata_json` when a thinner refresh runs.
- [ ] `DownloaderRegistry.extract_info` works with `YtdlpProvider` registered.
- [ ] A unit test registers a fake second provider; the registry sorts candidates by `priority`, calls the higher first.
- [ ] A unit test simulates `ProviderRetryElsewhere` from the first provider; the registry advances to the second and marks the first DEGRADED.
- [ ] A unit test simulates `URLNotSupportedError`; the registry does **not** try further providers.
- [ ] `providers_enabled["ytdlp"] = false` causes `extract_info` to raise — registry exposes no fallback to the absent vendor.
- [ ] `provider_failover_enabled = false` causes a single attempt only.
- [ ] `import-linter` reports zero violations for the new "no provider imports outside registry" rule.
- [ ] `provider:health:ytdlp` Redis key updates after a forced failure.

**Exit Criteria**

1. Validation passes.
2. yt-dlp invocation is timed and logged with `duration_ms`.

**Human Verification Required**

- Hand-test 5 URLs from each target platform in scope (YouTube, TikTok, Instagram, Twitter/X, generic).

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 6.

**Risks**

| Risk | Mitigation |
|---|---|
| yt-dlp output schema drift | Resilient parsing; clear `ExtractionFailedError` on schema mismatch. |
| Platform anti-bot blocks | Document; handle as `PLATFORM_ERROR`. |

**Testing Requirements**

- Unit tests with recorded yt-dlp JSON fixtures.
- Integration test calling real yt-dlp on a stable URL (skipped in offline CI).

---

### Sprint 6 — Job Pipeline (single-user)

**Goal:** End-to-end download for one user, with cache.

**Scope:** `JobService`, `DownloadService`, `DownloadWorker`, `TelegramFileSender`, basic delivery.

**Tasks**

- **6.1** Define `domain/protocols/transcoder.py`, `domain/protocols/file_sender.py`.
- **6.2** Implement `infrastructure/downloader/ffmpeg_client.py`.
- **6.3** Implement `infrastructure/telegram/file_sender.py`.
- **6.4** Implement `services/job_service.py` with the cache-hit, cache-miss, and lock paths from Section 16.1–16.2 (skip fan-out — TODO points to Sprint 7).
- **6.5** Implement `services/download_service.py` end-to-end happy path: download, transcode if needed, upload, `cached_files` UPSERT, `downloads` insert, counter update, lock release.
- **6.6** Implement `workers/download_worker.py`: dequeue, run `DownloadService`, retry logic via `tenacity`.
- **6.7** Implement `workers/main.py` composition root.
- **6.8** Hook `bot/handlers/download.py` post-quality callback to call `JobService.request(...)`.
- **6.9** Implement `services/notification_service.py` happy path: job started, job completed, job failed (no progress percent in V1, only state).
- **6.10** Implement `CleanupWorker` minimal sweep: temp files older than 60 s; will be expanded in Sprint 10.

**Validation Checklist**

- [ ] Cache hit: a previously downloaded video is delivered in < 1 s p95.
- [ ] Cache miss: yt-dlp downloads, FFmpeg transcodes if needed, Telegram receives the file, `file_id` is cached, the user receives the file. Round-trip ≤ 90 s p95 for a 50 MB MP4.
- [ ] `jobs` row transitions: created → queued → processing → completed.
- [ ] On simulated yt-dlp failure: job moves to retry_queued, retries up to 3, then permanently_failed; user is notified.
- [ ] `downloads` row inserted with denormalized `platform`, `format`, `quality`, `file_size`.
- [ ] `users.daily_download_count` and `total_downloads` incremented atomically.
- [ ] `active_downloads` row deleted on completion.
- [ ] Temp file removed.

**Exit Criteria**

1. Validation passes.
2. End-to-end metrics (`download_seconds`, `upload_seconds`, `job_processing_seconds`) emitted.
3. Single-user, single-process load test: 50 sequential downloads succeed with no errors.

**Human Verification Required**

- Run the bot. Send a URL. Confirm the file arrives.
- Send the same URL again. Confirm instant delivery from cache.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 7.

**Risks**

| Risk | Mitigation |
|---|---|
| Telegram upload size limits (2 GB) | Pre-checked against `max_file_size`. |
| Long-running uploads blocking the worker | Configurable timeout; chunked send. |
| Out-of-disk on temp dir | Cleanup worker on a tight schedule; alert. |

**Testing Requirements**

- Unit tests for `JobService` decision tree.
- Integration test for full pipeline against a known stable URL.

---

### Sprint 7 — Fan-Out and Resend

**Goal:** Two users requesting the same content while a download is in flight both receive the file. Resend from history works.

**Scope:** `job_waiters` writes, multi-recipient delivery, `HistoryService`, history handlers.

**Tasks**

- **7.1** Update `JobService.request(...)` to detect duplicates via the active_downloads conflict path; insert `job_waiters`.
- **7.2** Update `DownloadService` to read all waiters and deliver to each. Per-waiter idempotency via `(job_id, user_id)` uniqueness in `downloads` insert.
- **7.3** Implement `services/history_service.py`: paginated read, resend.
- **7.4** Implement `bot/handlers/history.py` and `bot/keyboards/history.py`.

**Validation Checklist**

- [ ] Two synthetic users send the same URL within 1 s of each other; both receive the file once.
- [ ] Each receives a `downloads` row, both counters increment, only one cache entry exists.
- [ ] History command displays a paginated list, most recent first.
- [ ] Resend from history sends instantly when the cache is intact.
- [ ] Resend when `cached_file_id` is NULL falls back to a new download.
- [ ] No double-delivery under retried worker (idempotency).

**Exit Criteria**

1. Validation passes.
2. Fan-out tested with up to 10 simultaneous waiters.

**Human Verification Required**

- Two human accounts request the same URL within seconds; both receive it.
- Resend from history.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 8.

**Risks**

| Risk | Mitigation |
|---|---|
| Race between `active_downloads` insert and lock | Documented order; tested under stress. |
| One waiter's delivery failure blocking others | Per-waiter try/except, log + continue. |

**Testing Requirements**

- Concurrent-request stress test with synthetic users.
- Idempotency test (retry a job after partial delivery).

---

### Sprint 8 — Admin and Ops

**Goal:** Owner and Moderator can administer the bot from within Telegram.

**Scope:** `/stats`, `/userinfo`, `/ban`, `/unban`, `/settings`, `/setting_set`, `/broadcast`, `BroadcastService`, `BroadcastWorker`.

**Tasks**

- **8.1** Implement `services/broadcast_service.py` + `workers/broadcast_worker.py`.
- **8.2** Implement `bot/handlers/admin.py` with command set.
- **8.3** Add API endpoints under `/v1/admin/*` per Section 20.2.

**Validation Checklist**

- [ ] `/stats` returns correct totals.
- [ ] `/ban` and `/unban` update the DB and audit fields correctly.
- [ ] `/setting_set` validates value_type and rejects bad input.
- [ ] `/broadcast` enqueues; `BroadcastWorker` processes; `total_sent` and `total_failed` reflect actuality.
- [ ] Broadcast filters (`--lang`, `--role`) target the correct audience.
- [ ] Non-owner users cannot run owner-only commands.
- [ ] Admin API requires API key; without it, 401.

**Exit Criteria**

1. Validation passes.
2. Broadcast of 1000 synthetic users completes within the configured rate limits without manual intervention.

**Human Verification Required**

- Run each admin command at least once.
- Send a broadcast to a test segment.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 9.

**Risks**

| Risk | Mitigation |
|---|---|
| Telegram rate-limits during broadcast | Chunking, sleep between chunks. |
| Owner mis-broadcast | Confirmation prompt before sending. |

**Testing Requirements**

- Service unit tests.
- Integration test for a 100-user broadcast (synthetic recipients).

---

### Sprint 9 — Smart Advertisements

**Goal:** Admin can manage ads; ads are delivered per algorithm.

**Scope:** `AdService`, admin commands for ads, delivery hook in `DownloadService`.

**Tasks**

- **9.1** Implement `services/ad_service.py` per Section 16.7.
- **9.2** Implement `/ad_create`, `/ad_list`, `/ad_edit`, `/ad_toggle`, `/ad_delete`, `/ad_stats`, `/ad_global`.
- **9.3** Hook `DownloadService` to call `AdService.maybe_show(user)` after delivery.
- **9.4** Implement click-tracking callback for ads with buttons.

**Validation Checklist**

- [ ] Ad shown according to `show_every_n_downloads` (post-increment, D-010).
- [ ] Premium users do not see untargeted ads.
- [ ] `target_role='premium'` ads show to premium users only.
- [ ] `ads_enabled=false` master switch suppresses all ads.
- [ ] Impressions and clicks are persisted.
- [ ] Highest `priority` ad wins among matching candidates.
- [ ] Photo/video/animation ads render correctly.

**Exit Criteria**

1. Validation passes.
2. Synthetic flow: 50 downloads, ad shown the expected number of times.

**Human Verification Required**

- Create an ad. Run downloads. See the ad. Click the button. Verify the count rises.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 10.

**Risks**

| Risk | Mitigation |
|---|---|
| Modulo timing surprise | D-010 locks the choice. |
| Bad media `file_id` causes ad delivery failure | Validate at upload time. |

**Testing Requirements**

- Selection algorithm unit tests (full truth table).
- Integration tests for impression/click increments.

---

### Sprint 9.5 — Ads v2 (IMPLEMENTED — tasks 9.5.1–9.5.8; 9.5.9/9.5.10 deferred)

> **Status: IMPLEMENTED (2026-06-25).** Tasks 9.5.1–9.5.8 are built, tested, and live: the core schema migration `migrations/versions/202606240001_ads_v2_schema.py` is applied, the Section 13.6 settings are seeded, and the engine (audience targeting, multi-button, copy-mode, placements, ad broadcast, commands) is wired. **9.5.9 (`ad_events` analytics) IMPLEMENTED 2026-06-25** (migration `202606250001`, recording off the hot path, D-052). **9.5.10 (scheduling) IMPLEMENTED 2026-06-25** (migration `202606250002`: `scheduled_at` on broadcasts + ads, broadcast due-poller + ad selection gate, D-053). Both in the deferred-backlog session. Decisions D-042–D-045, D-052, D-053. The original design specification is preserved below for reference.

**Goal:** Evolve the Sprint 9 ad foundation into a flexible, audience-targeted advertisement system supporting rich Telegram content, multiple placements, ad broadcasts, and first-class audience segmentation — all additively, with no rewrite of the Sprint 9 selection core and no new Python dependency.

**Why it is low-risk:** Sprint 9 was built port-first. `AdService` is the single selection authority; `AdSenderProtocol` is an injected transport; click tracking is a generic signed callback; content is already stored as Telegram `file_id` (never raw bytes). Every item below is an added column, an added table, an added sender method, an added thin hook, or an added command — not a refactor of existing code paths.

#### Scope

1. **Broadcast advertisements** — send a stored ad to an audience (all / selected / language / role / segment), reusing the Sprint 8 broadcast plumbing.
2. **Persistent + placement-based advertisements** — ads that appear in-flow at named placements (video delivery, audio delivery, quality-select, home, history), each behind a per-placement toggle.
3. **Rich Telegram content** — text, photo, video, **document**, **audio**, animation/GIF, **album**, captions, Markdown/HTML formatting, and **multiple inline buttons**.
4. **Media reuse** — two delivery modes behind `AdSenderProtocol`: `fields` (Sprint 9, programmatic) and `copy` (store a complete message in a bot-owned storage channel; deliver via `bot.copy_message`). Minimises storage and upload cost.
5. **First-class audience targeting & segmentation** — include/exclude by role, plan (free/premium), language, explicit user IDs, and reusable custom segments; "everyone except X" semantics; Owner exemption preserved and overridable.
6. **Management commands** — create/list/edit/enable/disable/delete/preview/broadcast/stats + audience and segment management.
7. **Future analytics** (designed, partly deferred) — impressions, per-button clicks, broadcast delivery counts, active status, and placement dimension; optional `ad_events` table for per-event/time-series reporting added without touching the increment hot path.
8. **Future scheduling** (designed, deferred) — `scheduled_at` column + a due-poller worker, specified but not built in this sprint.

#### Design goals (LOCKED for this sprint)

- **No new Python dependency** — `copyMessage`/`copyMessages`, `send_document`, `send_audio`, `send_media_group` are already on the aiogram `Bot`.
- **Reuse existing aiogram capabilities** and the Sprint 8 `broadcasts` plumbing.
- **Minimise storage/upload cost** — store Telegram `file_id`/`message_id`, never bytes; copy-mode re-sends without re-upload.
- **Audience targeting is first-class from day one**, not bolted on.
- **Extensible for monetization** — campaigns, A/B variants, sponsored placements, and partner targeting are reachable as additive extensions (EP-19, EP-20); not built here.

#### Proposed schema (PLANNED — pending the Section-19 migration; not in live Section 10 yet)

`advertisements` (ALTER, all additive with back-compat defaults):

| Column | Type | Default | Notes |
|---|---|---|---|
| `placement` | VARCHAR(30) NOT NULL | `'post_download'` | enum: `post_download` (compat = today), `video_delivery`, `audio_delivery`, `quality_select`, `home`, `history`, `broadcast`. |
| `delivery_mode` | VARCHAR(10) NOT NULL | `'fields'` | `fields` (Sprint 9) \| `copy` (copyMessage). |
| `storage_chat_id` | BIGINT NULL | NULL | copy-mode source (bot-owned storage channel). |
| `storage_message_id` | BIGINT NULL | NULL | copy-mode source message. |
| `parse_mode` | VARCHAR(10) NULL | NULL | fields-mode rich text (`HTML`/`MarkdownV2`). |
| `audience_mode` | VARCHAR(10) NOT NULL | `'all'` | `all` \| `include` \| `exclude`. |
| `type` (widen enum) | — | — | + `document`, `audio`, `album` (additive to text/photo/video/animation). |

`ad_buttons` (NEW — replaces the single `button_text`/`button_url` pair, which is retained one deprecation window for back-compat):

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK Identity | |
| `advertisement_id` | BIGINT NOT NULL FK→`advertisements` ON DELETE CASCADE | |
| `text` | VARCHAR(100) NOT NULL | |
| `url` | TEXT NULL | NULL = callback-only button (reserved). |
| `row` | SMALLINT NOT NULL DEFAULT 0 | keyboard row. |
| `position` | SMALLINT NOT NULL DEFAULT 0 | within-row order. |
| `clicks` | BIGINT NOT NULL DEFAULT 0 | per-button analytics. |

Indexes: `ix_ad_buttons_ad(advertisement_id, row, position)`.

`ad_audience_rules` (NEW — first-class targeting):

| Column | Type | Notes |
|---|---|---|
| `id` | BIGINT PK Identity | |
| `advertisement_id` | BIGINT NOT NULL FK→`advertisements` ON DELETE CASCADE | |
| `effect` | VARCHAR(10) NOT NULL | `include` \| `exclude`. |
| `dimension` | VARCHAR(20) NOT NULL | `role` \| `plan` \| `language` \| `user_id` \| `segment` \| `country` (reserved). |
| `value` | VARCHAR(64) NOT NULL | e.g. `premium`, `ar`, `12345`, or a segment id. |

Indexes: `ix_ad_audience_rules_ad(advertisement_id)`, `ix_ad_audience_rules_dim(dimension, value)`.

`audience_segments` (NEW — reusable custom groups) + `audience_segment_members` (NEW):

| Table | Columns |
|---|---|
| `audience_segments` | `id` PK, `name` VARCHAR(100) UNIQUE NOT NULL, `description` TEXT NULL, `created_by` BIGINT FK→`users.id` ON DELETE RESTRICT, `created_at`, `updated_at`. |
| `audience_segment_members` | PK (`segment_id` FK→`audience_segments` ON DELETE CASCADE, `user_id` FK→`users.id` ON DELETE CASCADE); index `(user_id)`. |

`broadcasts` (ALTER): `+ advertisement_id BIGINT NULL FK→advertisements ON DELETE SET NULL` (a broadcast may deliver a stored ad via copyMessage instead of plain text).

`ad_events` (NEW — **deferred to the last task / optional**; monthly RANGE-partitioned like `error_logs`): `id`, `advertisement_id`, `user_id` NULL, `event_type` (`impression`/`click`), `placement` NULL, `button_id` NULL, `created_at` (partition key). Counters on `advertisements`/`ad_buttons` stay the hot path; this is the additive route to per-placement/time-series analytics with **no hot-path change**.

New index for placement selection (additive; the LOCKED `ix_ads_active_priority_role` is retained): `ix_ads_placement_active_priority(placement, is_active, priority DESC)`.

#### Audience evaluation semantics (LOCKED for this sprint)

- `audience_mode='all'` → everyone, still subject to the global Owner/premium exemptions (Section 16.7) unless an explicit rule overrides.
- `audience_mode='include'` → show only to users matching the include expression.
- `audience_mode='exclude'` → show to everyone **except** users matching the exclude expression (covers "all users except Premium").
- Within a dimension, multiple values are **OR** (`role ∈ {free, premium}`). Across dimensions it is **AND** (`role∈X AND language∈Y`).
- `dimension='user_id'` and `dimension='segment'` are evaluated against the requesting user's id / segment membership (`audience_segment_members`, indexed by `user_id`, cache-friendly).
- Evaluation runs in Python over the small per-placement candidate list (ads are post-action, not on the hottest path); supersedes the Sprint 9 `target_role` fast-path, which is migrated into an equivalent `include`/`role` rule (D-043). `target_role` is retained as a denormalized fast pre-filter for one deprecation window.
- Examples: *Ad A* free-only → `include role=free`; *Ad B* premium-only → `include role=premium`; *Ad C* Arabic-only → `include language=ar`; *Ad D* → `include user_id=12345`, `include user_id=67890`; *Ad E* all-except-premium → `exclude plan=premium`.

#### Tasks

- **9.5.1** Migration + models + repos + protocols for the schema above; backfill existing single-button → `ad_buttons` and existing `target_role` → an audience rule. (Section-19 entry; D-042–D-045.)
- **9.5.2** Multi-button rendering + per-button signed click callbacks (`a|<ad_id>|<button_id>`) + per-button click counters; `/ad_preview`.
- **9.5.3** Widen `fields`-mode content: `document` / `audio` / `album` send paths in `TelegramAdSender`.
- **9.5.4** `copy`-mode delivery: bot-owned storage channel (`ads_storage_chat_id` setting), `AdSenderProtocol.copy_ad` via `bot.copy_message`; `/ad_create` copy-mode (forward/reply to store the source message). Buttons re-attached from `ad_buttons` (copyMessage drops the original keyboard).
- **9.5.5** Audience targeting engine: an `AudienceService` evaluator + rules/segments CRUD (`/ad_audience`, `/ad_segment_*`); integrate into `AdService` selection.
- **9.5.6** Placement model: `placement` column + per-placement `settings` toggles + thin hooks at `quality_select`, `home` (start), `history` (video/audio placements reuse the Sprint 9 hook).
- **9.5.7** `/ad_broadcast`: `BroadcastService.create_from_ad` + a `BroadcastWorker` copyMessage branch; broadcast delivery-count analytics (reuses `broadcasts.total_sent`/`total_failed`).
- **9.5.8** Command surface: `/ad_enable`, `/ad_disable` (alias `/ad_toggle`), `/ad_preview`, `/ad_broadcast`; `/ad_stats` gains placement + per-button + delivery-count breakdown.
- **9.5.9** *(IMPLEMENTED 2026-06-25)* `ad_events` analytics table + per-placement / per-button reporting. Migration `202606250001` (partitioned, no FKs); `AdEvent` model + `AdEventRepository` (`record` / `count_for_ad`); `AdEventRecorderProtocol` port + fire-and-forget `AdEventRecorder` adapter wired into `AdService` (impression in `maybe_show`, click in `record_click`), written off the delivery hot path (D-052). `RUNTIME_PARTITIONED_TABLES` keeps partitions rolling.
- **9.5.10** *(IMPLEMENTED 2026-06-25)* scheduling scaffold: nullable `scheduled_at` on `broadcasts` + `advertisements` (migration `202606250002`). Broadcasts use a **due-poller** (`BroadcastRepository.get_next_pending(now)` filters NULL-or-due; the existing `BroadcastWorker` loop is the poller); ads use `scheduled_at` as a placement-selection gate in `AdService.maybe_show`. Commands: `--at <ISO>` on `/broadcast` + `/ad_broadcast`, `scheduled_at=<ISO>` on `/ad_create` + `/ad_edit`. `core.timeparse.parse_iso_datetime` parses input. D-053.

#### Command surface (target)

`/ad_create` (fields **or** copy-mode), `/ad_list`, `/ad_edit`, `/ad_enable`, `/ad_disable` (`/ad_toggle` alias kept), `/ad_delete`, `/ad_preview`, `/ad_broadcast`, `/ad_stats`, `/ad_global` (master switch, unchanged), `/ad_audience <id> ...`, `/ad_segment_create|_add|_remove|_list`. All Owner-only via `OwnerFilter`; non-owners silently ignored (item #18). Public surface: the existing signed ad-click callback (extended with `button_id`).

#### Configuration (PLANNED — see Section 13.6; NOT seeded in this sprint)

`ads_storage_chat_id`, `ad_placement_post_download_enabled`, `ad_placement_video_delivery_enabled`, `ad_placement_audio_delivery_enabled`, `ad_placement_quality_select_enabled`, `ad_placement_home_enabled`, `ad_placement_history_enabled`. Per-placement toggles default the compat placement ON and the new placements OFF (opt-in), so persistent ads never appear until the Owner enables a placement.

#### Future monetization readiness (design hooks; NOT built in 9.5 — EP-19, EP-20)

Different ads per plan (audience rules), no ads for premium (default exclude rule / Section 16.7 exemption), premium-specific promotions (`include plan=premium`), partner campaigns (a future `ad_campaigns` table + `advertisements.campaign_id`), A/B testing (a `variant_group` + `weight` on ads, weighted selection), sponsored placements (`placement` + a future `sponsor`/`advertiser` field + budget caps). All reachable additively; reserved as extension points, not implemented.

#### Validation Checklist (for when implemented)

- [ ] Existing Sprint 9 ads keep working unchanged after migration (compat defaults).
- [ ] Multi-button ads render and track per-button clicks.
- [ ] `document` / `audio` / `album` ads deliver correctly (fields-mode).
- [ ] copy-mode ad reproduces a rich message (media + caption + formatting) with re-attached buttons.
- [ ] Audience include/exclude across role / plan / language / user_id / segment behaves per the semantics above (full truth table).
- [ ] Owner exemption preserved; overridable by an explicit include rule.
- [ ] `/ad_broadcast` reaches exactly the targeted audience; delivery counts persisted.
- [ ] Per-placement toggles gate persistent placements; all default safe (no surprise ads).
- [ ] No regression in the Sprint 9 post-download flow.

#### Exit Criteria

1. Validation checklist passes.
2. Synthetic audience matrix: ads A–E from the semantics examples each reach exactly their intended users and no others.
3. A copy-mode rich ad broadcast to a synthetic 100-user segment delivers once per recipient with correct counts.

#### Human Verification Required

Create a rich copy-mode ad with two buttons; preview it; target it to a segment; broadcast it; place a persistent ad under video delivery; confirm a premium/Owner account is excluded as configured; verify per-button click counts and delivery counts rise.

#### Stop Point

Agent stops after each task per the standard per-task DoD; full-sprint sign-off (Gate-style) required before the sprint is marked Completed.

#### Risks

| Risk | Mitigation |
|---|---|
| Storage channel is a hard dependency for copy-mode (delete the source post → dead ad). | Document the constraint; `/ad_preview` doubles as a health check; validate source on create. |
| Placement density feels spammy and depresses conversion. | Per-placement toggles default OFF for new placements; ship placements incrementally; measure. |
| copyMessage drops inline keyboards. | Buttons are first-class in `ad_buttons` and re-attached on delivery; impressions always tracked, clicks only on attached callback buttons. |
| Audience rule evaluation cost. | Tiny per-placement candidate sets; Python evaluation; segment membership indexed by `user_id` + cacheable. |
| Album ads are multi-message and can't carry buttons on the group. | Buttons sent as a follow-up message; phase album last. |
| Migrating the LOCKED `target_role` semantics. | Retain `target_role` as a fast pre-filter for one deprecation window; backfill into rules (D-043). |

#### Testing Requirements

- Audience evaluator unit tests (full include/exclude truth table across all dimensions).
- Multi-button + per-button click unit + integration tests.
- copy-mode delivery integration test (mocked Bot.copy_message).
- `/ad_broadcast` integration test (synthetic segment, delivery counts).
- Placement-toggle gating tests.
- Regression: the entire Sprint 9 suite stays green.

---

### Sprint 10 — Observability and Backup

**Goal:** The system is production-grade across logs, metrics, alerts, and DR. (Security validation and the load-test framework move to Sprint 11.)

**Scope:** End-to-end Sentry; `/v1/metrics`; Telegram alerter; health/readiness; PgBouncer; backup-restore drill; operational runbook.

**Tasks**

- **10.1** Verify Sentry captures from bot, worker, api processes; tag with `component`, `correlation_id`, `job_id`.
- **10.2** Implement `/v1/metrics` exposing all metrics in Section 15.3.
- **10.3** Implement the Telegram alerter (throttled, deduplicated).
- **10.4** Implement `/v1/health` and `/v1/ready` per Section 15.7.
- **10.5** Enable `CleanupWorker` full duties: partitions rollover, temp files, stale `active_downloads`, stale `job_waiters`, retention drops.
- **10.6** Configure PgBouncer; verify connection counts (D-020).
- **10.7** Perform a backup-restore drill into a throwaway DB; verify all data + a sample download flow.
- **10.8** Write the operational runbook at `deploy/README.md` covering: deploy, rollback, backup verify, common alerts.

**Validation Checklist**

- [ ] Sentry receives a deliberate test exception from each process.
- [ ] `/v1/metrics` returns ≥ 30 distinct metric series.
- [ ] Telegram alert fires on a forced critical log.
- [ ] `/v1/ready` returns 503 when Redis is down.
- [ ] Restore drill produces a working bot.
- [ ] Runbook covers deploy + rollback + 5 most-likely failure modes.

**Exit Criteria**

1. Validation passes.
2. Restore-drill report appended to `PERFORMANCE_REPORT.md` (DR section) and `deploy/restore-drill-report.md`.
3. Test reports updated (`TEST_RESULTS.md`).

**Human Verification Required**

- Read restore-drill report.
- Approve runbook.

**Stop Point**

Agent stops. Owner reviews. Approval required to begin Sprint 11.

**Risks**

| Risk | Mitigation |
|---|---|
| DR drill exposes restore gap | Fix backup config; re-drill. |
| Alerter loop / noise | Throttle + deduplicate from day one. |

**Testing Requirements**

- Chaos tests for this sprint: kill workers, kill Redis briefly, kill PG briefly; observe recovery. Full load and stress testing belong to Sprint 11.

---

### Sprint 11 — Testing Framework, Security Validation, Load and Stress

**Goal:** A reusable, reproducible test framework — covering security, load, stress, and Telegram E2E — is implemented and run. Production-readiness is established by simulation, not by hope.

**Scope:** Sandbox bot + test environment; E2E harness; full security test suite; user simulation framework; load levels L1–L4 (L5/L6 are optional/long-running here); stress scenarios; capacity report.

**Tasks**

- **11.1** Create the sandbox bot (via @BotFather) and provision the isolated test environment per Section 25.6 (separate PG, Redis, queue prefix, temp dir). Add `DEPLOY_ENV=test` plumbing and the production-fingerprint startup assertion.
- **11.2** Implement `tests/e2e/harness.py` — sandbox-bot client, test-account pool, deterministic action delays.
- **11.3** Implement Telegram E2E test suites under `tests/e2e/{bot_core, download_flow, cache_flow, queue_flow, error_flow}/` covering every scenario in Section 25.7.
- **11.4** Implement the five named E2E scenarios under `tests/e2e/scenarios/` (S-1 through S-5). S-3 uses a mocked secondary provider (real second provider arrives in V6).
- **11.5** Implement the security test suite under `tests/security/` covering all five categories in Section 25.9. Wire `pip-audit` and `bandit` as CI gates (high severity blocks merge).
- **11.6** Implement `tests/simulation/` framework: `SimulationRunner`, `BotClient`, `MetricsCollector`, `ReportWriter`, `UserProfile` base. Production-credential rejection in `SimulationRunner.__init__`.
- **11.7** Implement the five V1 user profiles (`Casual`, `Active`, `Heavy`, `Abuse`; `Premium` stub for V2).
- **11.8** Implement the AI-controlled traffic generators (`RandomTraffic`, `ScheduledSpike`, `PeakHour`, `Viral`, `PlatformPattern`).
- **11.9** Implement the stress-scenario catalog under `tests/simulation/scenarios/` (ST-1 through ST-6).
- **11.10** Run load levels **L1, L2, L3, L4** end-to-end. Append a versioned entry to `PERFORMANCE_REPORT.md` per level (date, git SHA, hardware, metrics from Section 25.15.5).
- **11.11** Run stress scenarios ST-1 through ST-6. Append each to `PERFORMANCE_REPORT.md`.
- **11.12** Run the full regression suite + every security category. Append outcomes to `TEST_RESULTS.md` and `SECURITY_REPORT.md`.
- **11.13** Generate the capacity-planning report (Section 25.15.7) and append it to `PERFORMANCE_REPORT.md`.
- **11.14** Update the Manual Test Catalog with M-17 through M-22 outcomes.

**Validation Checklist**

- [ ] Sandbox bot reachable; test environment fully isolated; production-fingerprint assertion blocks misconfigured boots.
- [ ] All E2E scenarios S-1, S-2, S-4, S-5 pass on a clean run. S-3 passes against the mocked secondary provider.
- [ ] Every security category (Section 25.9) has at least one passing test; `pip-audit` / `bandit` clean.
- [ ] `python -m tests.simulation.runner --level=L1 --profile=Casual --seed=42` runs to completion and writes a deterministic report entry.
- [ ] Same command with `--profile=Abuse` shows every abuse user blocked (zero successful downloads).
- [ ] L1, L2, L3, L4 reports present in `PERFORMANCE_REPORT.md`, each with timestamp and git SHA.
- [ ] ST-1 through ST-6 outcomes recorded; expected behaviors observed.
- [ ] Capacity report shows current max supported users, downloads/hr, queue throughput, scaling recommendations.
- [ ] V1 SLOs (Section 2.5) met at L4. If not met, sprint is blocked and the bottleneck is documented.

**Exit Criteria**

1. Validation passes.
2. `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md` are populated with this sprint's outputs.
3. Capacity report signed off by Owner.

**Human Verification Required**

- Review the capacity-planning report.
- Confirm sandbox-bot ownership and access.
- Sign off Gate G-5 (Security configuration) since security suite is now active.

**Stop Point**

Agent stops. Owner reviews all three report files. Approval required to begin Sprint 12.

**Risks**

| Risk | Mitigation |
|---|---|
| Load test exposes a hot-path bottleneck | Profile; document; iterate; potentially block Sprint 12 until fixed. |
| Sandbox bot rate-limited by Telegram during high simulation levels | Throttle simulation; or use multiple sandbox bots; documented in runbook. |
| Abuse profile not blocked by current rate limits | Adjust `rate_limit_*` settings; rerun; record adjustment in `SECURITY_REPORT.md`. |
| Test environment drift from production | A nightly diff job compares config and schema versions. |

**Testing Requirements**

- Every category in Section 25.3 has at least one new test.
- Load runs are reproducible (fixed seed in CI).
- The framework is invocable from a single command (Section 25.15.9).

---

### Sprint 11.5 — Internationalization (i18n)

> **Status: IMPLEMENTED (2026-07-01).** Tasks 11.5.1–11.5.12 are built, tested, and merged: English + Arabic catalogs are live, every handler/keyboard/service renders through `core.i18n.translate`, and the full regression suite (unit + security + e2e-scaffold + i18n-specific) passes with ruff/mypy --strict clean. Decisions D-061 through D-064. Pulled forward from V2 (§2.4) into V1 at explicit Owner direction, ahead of the remaining Sprint 12 launch-ops work. No database migration — see D-061/D-062.

**Goal:** Every piece of bot UI copy — welcome/menus/buttons/progress/errors/notifications/help/admin panel — renders in the user's own language, with English and Arabic shipping now and any future language addable by dropping in one catalog file, with zero business-logic change.

**Why it was pulled forward:** The Owner supplied a complete localization spec mid-Sprint-11, ahead of the originally-planned V2 slot (§2.4 previously locked "Multi-language interface" as out-of-scope for V1). Asked directly, the Owner chose to build it now rather than wait for V2. The design went through three rounds of Owner simplification during review — captured in full in D-061–D-064 — converging on: no first-contact gate (new users default to English immediately), no `/language` command (a permanent button only), and supported languages discovered from the filesystem rather than stored in the database.

#### Scope

1. **Core catalog loader** (`core/i18n.py`) — discovers, validates, and looks up locale catalogs; never raises out of `translate()`.
2. **Two shipped locales** — `core/locales/en.json` (the reference/default catalog) and `core/locales/ar.json` (RTL), ~250+ keys each, covering every user-facing surface including the admin panel.
3. **`users.language` as the single locale field** — no new column, no migration; reused from its existing BCP-47 definition (D-022).
4. **A permanent, button-only language-change UX** — no gate, no slash command (D-063).
5. **Full handler/keyboard/service migration** — every hardcoded English string, in both the regular-user surface and the entire admin panel (registry, keyboards, handlers, compose wizard), becomes a `translate(key, locale, **kwargs)` call.
6. **RTL correctness** — every catalog value is a whole-sentence template with named placeholders; Telegram clients render bidi text natively, so there is no custom layout engine to build.

#### Design goals (LOCKED for this sprint)

- **No business logic ever depends on a specific language.** Language only ever selects which string is rendered.
- **Adding a language is a content-only change** — one new `core/locales/<code>.json` file with a valid `_meta` block. No code change, no schema change, no settings-table entry (D-062).
- **User-generated content is never translated** — ad bodies, broadcast bodies, video titles, platform names, filenames pass through untouched; only application chrome is localized.
- **No hardcoded default-locale string anywhere in code** — sourced from `Settings.default_locale` / `DEFAULT_LOCALE` only (D-061).
- **Every fallback path is logged, never crashes the caller** (Hard Rule 10) — a missing key, a missing locale, or a bad `.format()` placeholder all degrade gracefully.

#### Tasks

- **11.5.1** `core/i18n.py` (catalog discovery, `_meta` validation, default-locale-as-reference-catalog invariant, `translate`/`resolve_locale`/`list_enabled_locales`) + `core/locales/en.json` + `ar.json` + `Settings.default_locale` (`DEFAULT_LOCALE` env var, §13.2). D-061, D-062.
- **11.5.2** `UserFacingError.translation_key` property on the domain exception hierarchy (D-064) — no generic `params` dict; traced every raise site first and added only what a real call site consumes.
- **11.5.3** `UserService.set_language(telegram_id, language)`, mirroring the existing `ban`/`unban`/`set_premium` mutation pattern.
- **11.5.4** `AuthMiddleware` seeds a new user's `users.language` from `Settings.default_locale` (never Telegram's auto-detected `language_code`); new `LocaleMiddleware` (`bot/middlewares/i18n.py`) resolves `data["locale"]` fresh on every update, positioned after `auth`, before `throttle`.
- **11.5.5** Composition-root wiring: `dp["translate"] = core.i18n.translate` (static factory, once) in `bot/main.py`; both `bot/main.py` and `workers/main.py` call `i18n.configure(settings.default_locale)` at their own startup.
- **11.5.6** `bot/keyboards/language_select.py` (picker keyboard) + a new signed callback action `l` (`CallbackSigner.pack_language`/`ParsedCallback.language`) + both entry points (the `/start` "🌐 Change Language" button for regular users; a new "🌐 Language" admin-panel section for Owner/Moderator) sharing one apply path in `bot/handlers/start.py`. D-063.
- **11.5.7** `NotificationService` (`send_initial`/`notify_stage`/`notify_completed`/`notify_failed`) takes a required `locale`; `DownloadService._notify_waiters` and `JobService._try_deliver_cached` resolve each fan-out recipient's **own** locale fresh rather than reusing one job-level locale.
- **11.5.8** Migrate the regular-user surface: `bot/handlers/{start,help,download,history}.py`, `bot/keyboards/{format_select,quality_select,history}.py`, `bot/middlewares/{throttle,auth}.py`.
- **11.5.9** Migrate `bot/panel/registry.py` — all six registries (`Section`/`MenuItem`/`SettingField`/`InfoItem`/`AudienceOption`/`PlacementOption`) swap `label` → `label_key`; new `Section("l", "panel.section.language")` added.
- **11.5.10** Migrate `bot/keyboards/admin_panel.py`'s own literals (every builder function, ~40+ labels including the compose-wizard screens).
- **11.5.11** Migrate `bot/handlers/{admin,ads,admin_panel,admin_wizard}.py` — the full admin/ads command surface and the FSM compose wizard.
- **11.5.12** New `tests/unit/test_i18n.py` (catalog validation, fallback behavior, real-catalog invariants including a regression test for the `translate(key, locale, **kwargs)`/`{key}`-placeholder collision found during this sprint); every existing test touched by a handler signature change updated; full suite + ruff + mypy --strict verified clean.

#### Validation Checklist

- [x] Every catalog (`en.json`, `ar.json`) loads cleanly; `_meta` validated; no orphaned keys vs. the default/reference catalog.
- [x] A new user's `users.language` is `DEFAULT_LOCALE` immediately — no forced picker.
- [x] "🌐 Change Language" is reachable from `/start` (regular users) and the admin panel (Owner/Moderator); both render the same picker.
- [x] Picking a language updates `users.language` and the very next message renders in the new locale — no restart, no `/start` re-run required.
- [x] A disabled (or removed) locale falls back to `DEFAULT_LOCALE` on read without ever overwriting the stored value; re-enabling it makes the original pick resolve correctly again with zero data migration.
- [x] Ad bodies, broadcast bodies, video titles, platform names, and filenames are never translated.
- [x] Every `ErrorType` and every `ProgressStage`-equivalent notification resolves to a real key in both catalogs (drift-checked by test).
- [x] Fan-out to multiple waiters with different languages delivers each recipient's own locale correctly.
- [x] Full regression suite green; ruff clean; mypy --strict clean on all touched production and test files.

#### Exit Criteria

1. Validation checklist passes.
2. Both catalogs are complete (no missing keys reachable from any handler) and the en/ar key-parity test passes.
3. A manual `translate()` sweep over every key in both locales succeeds with no `.format()` placeholder or encoding errors.

#### Human Verification Required

Live-bot walkthrough (parked for Sprint 11 Phase B, which needs the sandbox bot per §11.1 — not possible in this session): pick Arabic from `/start`, confirm the very next message is RTL and correctly formatted; pick a language from the admin panel as Owner and confirm only the panel chrome changes, never ad/broadcast content; confirm a fan-out (two users, two languages, one shared download) delivers each in their own language.

#### Stop Point

Agent stops after this sprint's tasks per the standard per-task DoD; the live-bot verification above is explicitly deferred to Sprint 11 Phase B, not a blocker for marking 11.5 code-complete.

#### Risks

| Risk | Mitigation |
|---|---|
| A future catalog edit introduces a typo'd key in a non-default locale. | Startup validation fails loudly, naming the offending key (D-062); a unit test asserts the same invariant against the real shipped catalogs. |
| A handler interpolates an untrusted value (username, title) without escaping. | Unchanged existing convention — callers escape before calling `translate()`; `translate()` never auto-escapes. |
| A new catalog key accidentally collides with a `translate()` parameter name (`key`, `locale`). | Found and fixed once already this sprint (`{key}` → `{setting_key}`); a permanent regression test scans every real catalog value for the reserved names. |
| Fan-out delivers the wrong recipient's locale. | Locale is resolved fresh per-recipient at delivery time, not cached from a single job-level value (D-063). |

#### Testing Requirements

- Catalog discovery + `_meta` validation unit tests (malformed `code`/`direction`/`version`/stray-underscore-key all fail loudly).
- Default-locale-as-reference-catalog invariant, asserted both as a fast unit test and as the real startup check.
- Fallback-chain tests (missing key in non-default locale → default; missing from both → raw key; bad `.format()` placeholder → logged, not raised).
- `resolve_locale` never-writes-back / auto-recovery test.
- `ErrorType` / notification-stage key-drift tests against both catalogs.
- Picker / `set_language` / default-from-config behavior tests for both entry points.
- Regression: the entire pre-existing suite stays green with `locale`/`translate` fixtures added where a handler/service is now constructed directly in a test.

---

### Sprint 12 — Launch Readiness

**Goal:** Bot is ready for public traffic.

**Scope:** Production deploy, smoke tests, monitoring sign-off, owner training.

**Tasks**

- **12.1** Deploy bot, worker, api containers to production.
- **12.2** Configure Sentry production project, Uptime Kuma monitors.
- **12.3** Run smoke tests in production: `/start`, one download (cached), one download (fresh), `/stats`, one ad, ban/unban a test account.
- **12.4** Re-run E2E scenarios S-1, S-2 against production (read-only paths and a small-scale write smoke).
- **12.5** Hand off the runbook to the Owner with a walk-through.
- **12.6** Schedule the first restore drill (30 days post-launch) and the first L4 production-shadow load run (90 days post-launch).
- **12.7** Mark V1 complete in `PROJECT_PROGRESS.md` and append a release entry to `TEST_RESULTS.md` (test summary), `SECURITY_REPORT.md` (security posture), and `PERFORMANCE_REPORT.md` (final pre-launch capacity).

**Validation Checklist**

- [ ] Production smoke tests pass.
- [ ] All Uptime Kuma monitors are green.
- [ ] Owner can log in to Sentry and view recent events.
- [ ] Backup is verified in production.
- [ ] Owner has performed at least one administrative action.
- [ ] E2E scenarios S-1 and S-2 pass against production (read-only and small-scale write smoke).
- [ ] `TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md` each carry a Sprint-12 release entry with the production git SHA.

**Exit Criteria**

1. V1 announce-ready. Owner signs off.

**Human Verification Required**

- Owner runs the full smoke-test list.

**Stop Point**

Project enters maintenance mode. V2 sprint planning begins only on Owner instruction.

**Risks**

| Risk | Mitigation |
|---|---|
| Production-only environment differences | Staging environment used to mirror; differences documented. |
| Last-minute Telegram API surprises | Smoke tests catch them. |

**Testing Requirements**

- Production smoke-test checklist (above).

---

### Sprint 13 — Admin Panel Enhancement and Growth Features

> **Status: IMPLEMENTED (2026-07-05), not yet pushed.** Tasks 13.1–13.9 are built, tested, and gated (ruff/mypy --strict/full unit suite/import-linter green after every one of 18 feature commits): the admin panel gains a "Dashboard Grade" design system, six growth/ops features, and a live main-menu dashboard. Decisions D-066 through D-069. This realizes EP-1 (referral system, sketched for V5 — see §2.4/§3 V5 footnote) ahead of schedule, at Owner direction, alongside five features that were never on the original roadmap at all (platform analytics, richer activity metrics, account-health detection, subscriber export/import, admin-editable message templates). Three additive migrations (`202607050001`–`202607050003`), no destructive schema change. Full detail in `SPRINT_13_PLAN.md` (Owner-authored SSOT for scope and screen design) and `PROJECT_PROGRESS.md`.

**Goal:** Turn the Sprint 9.6 admin panel from functional-but-plain into a polished, dashboard-grade experience, and give the Owner six new growth/operations tools — all discoverable from a live main-menu summary instead of buried in a menu tree.

**Why now, not V5 (or never):** The Owner supplied a full design system + feature spec mid-flight (this bot had no scheduled Sprint 13 before this). The referral system specifically pulls forward a V5 roadmap line item (§3) and closes EP-1; the other five features (platform analytics, activity metrics, health detection, export/import, message templates) were not on any version roadmap — they are net-new V1 scope, added because they materially improve day-to-day bot operation and were cheap to build on top of the existing service-layer architecture.

#### Scope

1. **A reusable UI primitives module** (`bot/panel/ui.py`) — every admin screen renders through it; no more ad-hoc emoji/spacing/table-alignment inlined per handler.
2. **An animation-ready emoji layer** — every icon is a semantic code, not a hardcoded literal; a single map switches the whole panel to animated custom emoji once the Owner obtains a Fragment-purchased bot username (a Telegram Bot-API precondition, D-067).
3. **Per-platform download analytics** with a CSV export.
4. **Richer user-activity cohorts** (24h/7d/30d active, 5d/7d/30d inactive, current/previous-hour).
5. **Blocked-bot / deleted-account detection** via an on-demand Telegram-API sweep, plus list + purge screens.
6. **Subscriber export (CSV/JSON) and import** (create-only — never overwrites an existing user).
7. **A full referral system** — deep link, stacking rewards, admin dashboard + leaderboard (realizes EP-1, D-066).
8. **Admin-editable message templates** for the 9 most user-visible bot messages, with live effect (D-068).
9. **A live main-menu dashboard** — 5 key metrics rendered before any tap, plus every screen the sprint touches redesigned onto the new primitives.

#### Design goals (LOCKED for this sprint)

- **No ad-hoc formatting outside `bot/panel/ui.py`.** Every new or touched screen renders through the shared primitives; a future screen that reaches for a bare emoji literal instead of `ui.emoji(code)` is a regression.
- **The service layer stays framework-free.** Both new features needing to run outside the request session (health sweep, template cache) keep aiogram entirely out of `services/` via the bot-layer/infrastructure-layer split in D-069 — verified by import-linter on every commit, not just at the end.
- **Import-only is never overwritten.** Subscriber import always creates, never updates an existing row — the Owner's own export is safe to re-import without risking silent data loss.
- **Every new i18n key ships in both catalogs in the same edit.** `core.i18n`'s reference-catalog invariant (D-062) fails startup on an orphaned key, so an Arabic gap is caught immediately, matching the existing i18n discipline from Sprint 11.5.

#### Tasks

- **13.1** `bot/panel/ui.py` — `header`/`divider`/`metric`/`progress_bar`/`sparkline`/`badge`/`card`/`table`/`footer`/`status_dot`/`role_icon`/`number_fmt`/`time_ago`, pure presentation, HTML-escaped, RTL-aware without a locale argument (content-sniffed). Plus the animation-ready `emoji(code)` layer + `CUSTOM_EMOJI_IDS` map (D-067). 50 unit tests.
- **13.2** Full UI redesign onto the new primitives: main-menu live dashboard (`open_panel` now injects `user_service_factory`/`queue_service`), Statistics, User-detail (rebuilt as a `ui.card` profile + metrics block), Downloads, System.
- **13.3** `DownloadRepository.count_by_platform`/`total_count` (optional `since`); `AdminService.get_platform_stats(period)`/`get_platform_report()`; a Statistics sub-screen with `ui.sparkline` bars per platform + a period filter; owner-only CSV export sent as a Telegram document.
- **13.4** `UserRepository.count_active_in_hours`/`count_inactive_days`/`count_active_current_hour`/`count_active_previous_hour`; `UserStats` gains the 7 new cohort fields (default 0, non-breaking); surfaced on the redesigned Statistics screen.
- **13.5** Migration `202607050001` (`users.bot_blocked`/`is_deleted`/`status_checked_at` + index); `services/user_health.py::UserHealthChecker` (framework-free, D-069) does a batched, delayed full sweep with a progress callback; bot-layer `AiogramChatProber` + infra `UserHealthStoreAdapter` (D-069). Moderation section gains Check-Status, Blocked/Deleted lists, and confirm-gated Purge.
- **13.6** `UserService.export_users(fmt)` → CSV/JSON bytes (paged); `import_users(rows)` → `ImportResult` (created/skipped/failed, create-only per this sprint's design goals). Users section gains an owner-only Export (format picker → document) and Import (a new `import_subscribers` FSM state).
- **13.7** Migration `202607050002` (`users.referred_by_id`/`referral_code`/`referral_bonus_downloads` + `referrals` table + seeded settings); `ReferralService` (D-066); `/start ?start=ref_CODE` deep-link + referrer notify; `/referral` command; admin section `r` with dashboard + leaderboard.
- **13.8** Migration `202607050003` (`message_templates`); `TemplateService` singleton + the `core/i18n.py::translate()` override hook (D-068); admin section `tp` (list/edit/reset, a new `template_edit` FSM state).
- **13.9** Registry wiring for all of the above — new sections `r`/`tp` (`tp` is `owner_only`), submenu extensions on `t`/`u`/`m`, new read-tier actions `lsb`/`lsd`, two new FSM states, `bot/main.py` composition-root wiring (`referral_service_factory`, the `template_service` singleton + its startup `.load()`, `health_checker_factory(bot)` resolving the bot's own `@username` once via `get_me()`), every new key in both `core/locales/en.json` and `ar.json`.

#### Validation Checklist

- [x] Every one of the 18 feature commits passes `ruff check`/`ruff format --check`/`mypy --strict`/the full `tests/unit` suite/`lint-imports` (7/7 contracts) before being committed — not just at the end.
- [x] `mypy --strict` across `bot/ core/ domain/ infrastructure/ services/ workers/ api/`: 0 issues, 174 source files (grown from the Sprint-11.5-era count as new modules were added).
- [x] `services/user_health.py` and `services/template_service.py` import no aiogram symbol; the aiogram-specific mapping lives in `bot/chat_prober.py` only (D-069) — asserted by import-linter, not just by convention.
- [x] Both new session-owning store adapters (`infrastructure/database/{user_health_store,message_template_store}.py`) never hold the request-bound session open — each opens and commits its own short-lived session per operation.
- [x] Subscriber import never overwrites an existing `users` row (create-only, verified by test).
- [x] Every new i18n key exists in both `en.json` and `ar.json` — the existing reference-catalog invariant (D-062) would fail startup otherwise.
- [x] A custom message template, once set, changes the live message the very next time that key is translated — no restart, no per-call DB query (verified end-to-end via `translate()` in tests).
- [x] The referral reward is permanent and stacks on top of the existing daily limit for both referrer and referred, granted exactly once per referred user (duplicate-referral guard tested).
- [x] All panel icons render as valid Unicode today (no broken glyphs) even though `CUSTOM_EMOJI_IDS` is empty — the animation switch is inert until populated.

#### Exit Criteria

1. Validation checklist passes.
2. Dev Postgres is migrated to head (`202607050003`) and the bot boots clean against it — verified live this sprint after an initial `UndefinedColumnError` was traced to a stale dev DB, not a code defect (see the Known Issues note below and the `PROJECT_PROGRESS.md` Sprint 13 entry).
3. Owner reviews the 19-commit diff (or a live-bot walkthrough) and signs off.

#### Human Verification Required

Live-bot walkthrough (not yet performed in full — the Owner did start the bot mid-session and confirm it boots post-migration, but did not exercise every new screen): open every redesigned/new admin screen (Statistics, Platform Analytics, User detail, Downloads, System, Moderation health screens, Users export/import, Referrals dashboard, Templates); run a referral deep-link end-to-end (`?start=ref_<CODE>` as a second test account, confirm both accounts' bonus and the referrer notification); run a Check-Status sweep against real Telegram accounts; edit and reset a message template and confirm the live message changes; export subscribers and re-import the same file, confirming zero rows are overwritten.

#### Stop Point

Agent stopped after all 9 tasks per the standard per-task DoD (gate + commit per task/sub-slice, no push). Owner review + sign-off required before any further Sprint-13-adjacent work (e.g. the residual 13.2 cosmetic polish noted below) or a push of `claude/happy-bose-71ed46`.

#### Risks

| Risk | Mitigation |
|---|---|
| The Owner expects animated emoji "now." | Explicitly clarified mid-session (3 options presented, Owner chose animation-ready-but-Unicode-for-now) and recorded as D-067; `CUSTOM_EMOJI_IDS` is the one place to flip once a Fragment username exists. |
| A future screen bypasses `ui.py` and reintroduces ad-hoc formatting. | Named as an explicit design goal (LOCKED above) and called out as the sprint's one residual gap (a handful of secondary read screens — user-list rows, moderation banned list, errors/jobs, ads list/detail, settings grouping, broadcast — still use pre-13.2 formatting; functional, flagged for follow-up). |
| Dev/staging Postgres drifts behind the model (as it did mid-session). | Not a code risk, but a process one: `alembic upgrade head` must run after any pull that touches `infrastructure/database/models/`, before starting the bot — recorded in `PROJECT_PROGRESS.md`'s Sprint 13 entry as a lesson for the next session. |
| Import accidentally overwrites existing users. | Explicitly designed as create-only (a design goal, not an incidental choice); tested. |
| `TemplateService`'s singleton cache drifts from the DB if edited outside the running process. | `invalidate_cache()`/`.load()` exist for exactly this; the admin edit/reset path always re-syncs the in-memory map immediately after its own write, so drift can only occur from an out-of-band DB edit, which is not a supported flow. |

#### Testing Requirements

- Full `bot/panel/ui.py` primitive coverage (escaping, RTL, edge values) — 50 tests.
- `ReferralService`: idempotent code generation + collision retry, self/duplicate/disabled/not-found guards, stacking-bonus correctness, dashboard/leaderboard aggregation.
- `UserHealthChecker`: batch + full-sweep behavior against a fake prober/store, progress-callback firing, unmarked-on-error retry semantics.
- `TemplateService` + `core.i18n` override hook: set/get/reset round-trip, end-to-end `translate()` override verification, catalog-vs-override preview distinction.
- `UserService.export_users`/`import_users`: both formats, create-only guarantee, blank-field normalization, invalid-row handling.
- Admin-panel handler tests for every new/redesigned screen (navigation renders the right text/keyboard; write actions gate correctly for Owner vs. Moderator).
- Composition-root test (`test_bot_composition.py`) updated for the three new `build_dispatcher` parameters.

---

### Future — Ads & Admin roadmap (post-V1; design-only, not scheduled)

Captured from Owner feedback #32–#34. Not implemented; the Ads v2 architecture is built
to accommodate them additively.

#### F-1 — Quota-unlock sponsored ads (#32, monetization)

When a user hits a limit (daily-limit / cooldown / rate-limit), the bot may show a
sponsored ad with an **Open Sponsor** button instead of a plain "limit reached" message;
optionally, interacting unlocks extra usage per future business rules.

- **Where it hooks in:** `RateLimitService.authorize_download` raises `DailyLimitExceededError`/
  `CooldownActiveError`/`RateLimitExceededError`; the download handler catches these. The
  hook is to call `AdService.maybe_show(..., placement="quota")` (a new placement) at that
  point instead of (or alongside) the error text.
- **What Ads v2 already provides:** placement model + per-placement toggle, audience
  targeting (sponsor campaigns can target free users), URL buttons (direct open).
- **What's needed:** a `quota` placement value + toggle; a tracked-click button (D-047's
  reserved `callback_data` redirect mode) so "press Open → unlock" can be measured and
  gated; an unlock side-effect (e.g. grant N bonus downloads via a Redis counter). Reserved
  as EP-21.

#### F-2 — Admin inline control panel (#33)

> **Status: COMPLETE — Owner sign-off 2026-06-27 (Sprint 9.6, EP-22).** Built and committed: signed `P|` callback
> namespace + `PanelFilter`; Staff-read / Owner-write with role-aware button hiding;
> `/settings` opens the panel; read sections (Stats/Users/Ads/Settings/Moderation/History/
> Downloads/System); Settings stepper + guided entry; Users + Ads management actions; guided
> User Info. Sprint 9.6 then added the **unified audience engine** (D-055), **multi-placement**
> (D-056), **internal ad metadata** (D-058), and the **registry-driven compose wizard** (D-057/
> D-059) shared by Ads + Broadcasts. **Owner req #10 (direct user-id for every user action) —
> DONE 2026-06-27:** the top-level Users (Ban/Unban/Premium/Admin) and Moderation (Ban/Unban)
> buttons now arm a guided "send the Telegram ID" prompt (`PanelStates.user_action`) that
> re-enters the same apply/confirm path the per-user detail buttons use (owner never
> targetable); `panel_write` also routes section `m` writes. Same change enriched the
> **Statistics** screen (joined today / last 7 days, active today, premium, staff — via new
> `UserRepository` count queries, no schema change). Remaining: Owner req #11 (verify
> daily-limit auto-reset). See `DESIGN_9.6_unified_audience_wizard.md` and `PROJECT_PROGRESS.md`.

Owner/Admin management primarily via inline keyboards instead of memorized commands:
a root panel (`Ads`, `Users`, `Limits`, `Broadcast`, `Channels`, `Statistics`) drilling into
per-area actions (e.g. Ads → `Create`/`List`/`Enable`/`Disable`/`Delete`/`Preview`).

- **What's needed:** a new `bot/handlers/admin_panel.py` rendering signed callback keyboards
  (reuse `CallbackSigner` with new actions, e.g. `p|ads|list`), gated by `OwnerFilter`. Each
  button delegates to the **existing** services (`AdService`, `UserService`, `BroadcastService`,
  `SettingsService`) — no business-logic duplication; the commands remain as the scriptable
  surface. Multi-step flows (create ad, set audience) use an aiogram FSM. Reserved as EP-22.

#### F-3 — Rich ad content builder (#34)

> **Status: COMPLETE — Owner sign-off 2026-06-27 (Sprint 9.6, EP-23).** Realized as part of F-2's compose wizard
> (D-057/D-059): the Content step captures a forwarded/sent message (copy-mode, native content
> preserved) or composed text, plus inline buttons, then Preview → Save — no `key=value`
> command needed. The commands remain as the scriptable surface.

A guided builder: *Create Ad → Add Text → Add Media → Add Buttons → Preview → Save*, or
*Create Ad → forward/send an existing Telegram message → Save*, preserving Telegram-native
formatting.

- **Already implemented in Ads v2:** all content types (text/photo/video/document/audio/
  animation/album), Markdown/HTML via `parse_mode`, **copy-mode** (store + reuse a complete
  forwarded message verbatim — the "forward a message → save" path), captions, and **multiple
  buttons** (`/ad_button_add`).
- **What's needed (the "builder"):** an aiogram **FSM** wrapping those existing operations
  into a step-by-step wizard (part of F-2's panel), so the Owner is prompted for each part
  instead of composing a `key=value` command. No new storage — it drives `AdService.create` +
  `add_button` + `/ad_audience`. Reserved as EP-23.

---

## 24. Task Decomposition Standard

Every task across every sprint follows this format. AI agents must write tasks this way when proposing new ones.

```
Task X.Y — <Imperative title>

Objective
  One paragraph: what done looks like and why it matters.

Files Touched
  - path/to/file.py (new | modified | deleted)
  ...

Implementation Steps
  1. ...
  2. ...

Expected Result
  Concrete observable change ("the bot prints X", "the table contains Y").

Validation Steps
  - Unit: ...
  - Integration: ...
  - Manual: ...

Rollback Considerations
  How to undo the change. (For migrations: forward-only with a recovery note.)

Risks
  - ...
```

Tasks are small enough to:
- Implement in one focused work block (< 1 day of effort).
- Be tested independently.
- Be reverted independently if needed.

If a task would take more than one work block, split it. Do not bundle.

---

## 25. Testing, QA, Security Validation & Telegram Bot Verification

### 25.1 Test-First Mindset (LOCKED)

No feature is "complete" until it has been validated by automated tests, security checks, and end-to-end Telegram bot verification. Implementation without tests is incomplete work — not done work waiting on tests. Section 1.8 (Definition of Done) enforces this per task. This section supplies the categories, environments, scenarios, and reports those gates depend on.

### 25.2 Test Directory Structure (LOCKED — D-033)

```
tests/
├── conftest.py                   # Shared async fixtures
├── unit/                          # Pure unit tests; no I/O
├── integration/                   # Real PG, real Redis, real yt-dlp on fixed URLs
│   ├── database/
│   ├── redis/
│   └── api/
├── security/                      # Input, authz, abuse, secrets, dependencies
│   ├── input_validation/
│   ├── authorization/
│   ├── abuse_protection/
│   ├── data_protection/
│   └── dependency_scan/
├── performance/                   # Repeatable micro-benchmarks (not load)
├── e2e/                           # Telegram bot scenarios via test harness
│   ├── harness.py                 # Sandbox-bot client + test-account pool
│   ├── bot_core/
│   ├── download_flow/
│   ├── cache_flow/
│   ├── queue_flow/
│   ├── error_flow/
│   └── scenarios/                 # Named S-1 .. S-5 scripts (Section 25.8)
├── regression/                    # Pinned past-bug repros
└── simulation/                    # User simulation framework (Section 25.15)
    ├── runner.py
    ├── users/
    ├── bot_client/
    ├── traffic/
    ├── scenarios/                 # Stress scenarios ST-1 .. ST-6
    └── metrics/
```

LOCKED. New top-level subdirectories under `tests/` require Owner approval.

### 25.3 Test Categories (LOCKED — six layers)

| Category | Purpose | Tooling | Required For |
|---|---|---|---|
| **Unit** | Pure functions, single classes | pytest, unittest.mock | Every PR |
| **Integration** | Real PG, real Redis, real yt-dlp on fixed URLs | pytest + service containers | Every PR |
| **Security** | Input, authz, abuse, secrets, deps | pytest + bandit + pip-audit + custom harness | Every PR |
| **Performance** | Repeatable micro-benchmarks | pytest-benchmark | Sprint 11 + every release |
| **E2E** | Telegram bot scenarios | pytest + Telegram test harness | Sprint exit + every release |
| **Regression** | Pinned past-bug repros | pytest | Every PR |

Each category lives in its own `tests/<category>/` directory. CI runs them as separate jobs and reports independently.

### 25.4 Coverage Targets

| Path | Target |
|---|---|
| `core/` | ≥ 90% |
| `domain/` | ≥ 95% (pure code) |
| `services/` | ≥ 85% |
| `infrastructure/` | ≥ 75% (mostly via integration) |
| `bot/` handlers | ≥ 70% (integration-heavy) |
| `tests/simulation/` | n/a (test infra) |

### 25.5 Test Naming, Fixtures, Patterns

- Naming: `test_<system_under_test>_<scenario>_<expected_outcome>`. Tests must read like specs.
- `tests/conftest.py` exposes async fixtures: `db_session`, `redis_client`, `settings`, `bot_app` factory, `sandbox_bot_client`, `test_account_pool`.
- All fixtures are async. All test classes use `asyncio_mode=auto`.
- No real network calls outside `integration/`, `e2e/`, `simulation/`.
- No randomness without a fixed seed in CI.

### 25.6 Test Environment Isolation (LOCKED — D-032)

Production environments are forbidden for testing. A fully isolated test environment is mandatory:

| Asset | Production | Test |
|---|---|---|
| Telegram bot token | `BOT_TOKEN` (production bot) | `BOT_TOKEN` pointing to a dedicated **sandbox bot** created via @BotFather |
| Database | Production PG | Dedicated PG instance (or `test_*` schema on a non-production host) |
| Redis | Production Redis | Dedicated instance, separate logical DBs (e.g., `4`/`5`) |
| Queue | Production queue keys | Test queue with key prefix `test:` |
| Storage / temp files | `/var/lib/.../tmp` | `/tmp/test_downloads` |
| Sentry environment | `production` | `test` |
| Owner Telegram ID | Real Owner | Dedicated test owner account |

`DEPLOY_ENV=test` selects the test environment at startup. CI/CD must never run against production credentials. A startup assertion refuses to boot if `DEPLOY_ENV=test` is paired with a token that matches a known production fingerprint.

### 25.7 Telegram Bot E2E Tests (categorized)

The harness (`tests/e2e/harness.py`) wraps the sandbox-bot client and a pool of test accounts. Scenarios are organized by user journey:

#### 25.7.1 Bot Core
- `/start` from a new user → user row created with `role='user'`.
- `/start` from an existing user → no duplicate; `last_activity_at` debounced-updated.
- `/help` returns the help message.
- Owner Telegram ID gets `role='owner'`.
- Moderator promotion via owner-only command works.
- Banned user receives only the ban message.
- **(Sprint 11.5, shipped V1 — not V2)** New user defaults to `DEFAULT_LOCALE`; tapping "🌐 Change Language" (on `/start`, or the admin-panel Language section for staff) shows the picker; picking a language persists to `users.language` and the very next message renders in the new locale with no restart. Parked for Phase B (needs the sandbox bot, §11.1): the live-bot round-trip of this flow, plus a disabled-then-re-enabled-locale recovery check.

#### 25.7.2 Download Flow
- URL submission → format keyboard within 3 s p95.
- Format selection → quality keyboard.
- Quality selection → job created, queued, processed, file delivered.
- State transitions persisted: `created → queued → processing → completed`.
- `downloads` row inserted with correct denormalized fields.
- `users.total_downloads` incremented; lazy daily reset works across the day boundary.

#### 25.7.3 Cache Flow
- Second request for the same `(media, format, quality)` → instant via cached `file_id`.
- `cached_files.usage_count` increments; `last_used_at` updates.
- Cache miss after row deletion → fresh download with new cache row.
- Two users requesting the same content concurrently → `job_waiters` fan-out delivers to both; single cache row.

#### 25.7.4 Queue Flow
- Priority ordering: HIGH dequeued before NORMAL before LOW.
- Atomic dequeue under concurrency (no double processing).
- Transient failure: job re-queued at LOW; retry count increments.
- Permanent failure: `PERMANENTLY_FAILED`; user notified.

#### 25.7.5 Error Flow
- Provider unavailable: registry tries next; if none, user-friendly error.
- Invalid URL: `URLNotSupportedError` → localized message.
- Unsupported platform: same.
- Timeout: job marked `TIMED_OUT`; auto-retry within limits.
- Worker crash mid-job: cleanup re-queues; waiters notified after recovery.

### 25.8 End-to-End Telegram Validation Scenarios (LOCKED)

Five named scenarios run as part of pre-release validation. Scripts live under `tests/e2e/scenarios/`:

| ID | Name | Steps | Validation |
|---|---|---|---|
| **S-1** | Valid URL Happy Path | Send URL → select quality → receive file | File integrity (hash, size, format). |
| **S-2** | Cache Reuse | Send same URL again | Cached file delivered; `usage_count` incremented; no yt-dlp invocation. |
| **S-3** | Provider Failover | Force primary provider failure (`providers_enabled.ytdlp=false`, mocked secondary provider active) | Registry tries secondary; user receives file; `provider:health:ytdlp` reflects DEGRADED. |
| **S-4** | Worker Crash Recovery | Kill the active worker mid-job | Cleanup re-queues; retry succeeds; user receives file; counters not double-incremented (idempotency). |
| **S-5** | Redis Restart Recovery | Bounce Redis | System recovers; queue rehydrated from `active_downloads` in PG; no duplicate work. |

**Sprint gating:**
- Sprints 5–9: S-1 and S-2 required.
- Sprint 10: S-1, S-2, S-4 (S-4 via in-process worker kill) required.
- Sprint 11: S-1 through S-5 required. S-3 uses a mocked secondary provider until V6 adds a real second provider.
- Sprint 12 (Launch): S-1 through S-5 must all pass against the test environment within the 24 h before the production cutover.

### 25.9 Security Testing (LOCKED — D-039)

Mandatory categories. New categories may be added but never removed.

#### 25.9.1 Input Validation
- Malformed URLs (invalid scheme, bad host, oversized).
- Oversized payloads (commands, callbacks).
- Invalid commands (unknown, malformed).
- Invalid callback data (wrong signature, replay).
- Invalid file requests (negative IDs, non-numeric, foreign user's IDs).

#### 25.9.2 Authentication & Authorization
- A `user` invoking Owner-only commands → `PermissionDeniedError`.
- A `moderator` invoking Owner-only commands → `PermissionDeniedError`.
- Forged callback data attempting privilege escalation → rejected by HMAC verification.
- API key missing or invalid on `/v1/admin/*` → 401.
- A user attempting to read another user's history → `PermissionDeniedError`.

#### 25.9.3 Abuse Protection
- Spam requests: `rate_limit_messages_per_minute` enforced.
- Queue flooding: per-user concurrent-job ceiling.
- Rate-limit bypass attempts (varied callback parameters, multiple sessions): still rate-limited.
- Repeated identical downloads: deduped via cache + `active_downloads`.
- Brute-force on admin API: locked out after N failures within window.

#### 25.9.4 Data Security
- Secrets never appear in logs (`SensitiveScrubber` test with sentinel tokens).
- Tokens never in error responses; never in `error_logs.traceback`.
- Passwords never logged.
- Sentry `before_send` strips secrets.
- `.env` is in `.gitignore`; CI rejects PRs that add `.env` files.

#### 25.9.5 Dependency Security
- `pip-audit` runs every PR. High severity blocks merge.
- `bandit` runs every PR.
- New dependencies require Section 6.4 entry and Owner approval.
- yt-dlp updates require a smoke-test PR before the production cron updates.

All findings go to `SECURITY_REPORT.md`.

### 25.10 Performance & Load Testing (LOCKED — D-035)

Performance testing is divided into:
- **Micro-benchmarks** under `tests/performance/` — repeatable, CI-friendly.
- **Load tests** via the User Simulation Framework (Section 25.15) — six levels.

#### 25.10.1 Load Test Levels (LOCKED)

| Level | Simulated Users | Required For | Output |
|---|---|---|---|
| **L1** | 10 | Every PR (smoke) | `PERFORMANCE_REPORT.md` |
| **L2** | 50 | Sprint exit | `PERFORMANCE_REPORT.md` |
| **L3** | 100 | Sprint exit | `PERFORMANCE_REPORT.md` |
| **L4** | 500 | Pre-release | `PERFORMANCE_REPORT.md` |
| **L5** | 1000 | Pre-release | `PERFORMANCE_REPORT.md` |
| **L6** | 5000 | Pre-major release / capacity audit | `PERFORMANCE_REPORT.md` |

Each level produces a versioned report (date, git SHA, hardware profile, metrics). Reports are **append-only**.

#### 25.10.2 Measured Quantities
Response times, queue latency, Redis performance, database performance, worker throughput. Full catalog in Section 25.15.5.

### 25.11 Regression Testing

Before any release:
1. Every unit test runs.
2. Every integration test runs.
3. Every security test runs.
4. Every regression test runs (pinned past-bug repros).
5. E2E scenarios S-1 through S-5 run.
6. Load levels L1 + L2 run as smoke.

A release is **blocked** if any of the above fails.

For every bug closed: a regression test is added under `tests/regression/` **before** the fix merges. The test fails before the fix; passes after. The corresponding entry is added to `TEST_RESULTS.md`.

### 25.12 AI Agent Validation Workflow (LOCKED)

For every task:

1. **Implement** per the task spec.
2. **Write tests** in every applicable category (unit, integration, security, e2e).
3. **Execute tests** locally; all must pass.
4. **Record results** in `TEST_RESULTS.md`.
5. **Record security findings** in `SECURITY_REPORT.md` (if applicable).
6. **Record performance results** in `PERFORMANCE_REPORT.md` (if applicable).
7. **Update `PROJECT_PROGRESS.md`** with the task transition and validation outcome.
8. **Open PR** linking the three report diffs.
9. **CI re-runs** all suites; must pass.
10. **Mark task `[x] Completed`** only after CI green and — if required — Human Verification Gate sign-off (Section 25.13).

The AI agent must never mark a task completed without successful testing and validation across every applicable category.

### 25.13 Human Verification Gates (LOCKED — D-037)

Critical changes cannot proceed without explicit Owner sign-off. The agent **stops** at every gate and waits.

| Gate | Triggers When | Owner Verifies |
|---|---|---|
| **G-1: Auth changes** | Any change to `AuthMiddleware`, `RoleFilter`, role enum, or auth-related repository methods. | Permission matrix matches expected; no privilege escalation possible. |
| **G-2: Database migrations** | Any new Alembic migration. | Schema diff matches Section 10; backfill plan reviewed; FK semantics correct. |
| **G-3: Queue architecture changes** | Any change to `QueueProtocol`, priority bands, job state machine, fan-out logic. | State machine still idempotent; no new states without decision-log entry. |
| **G-4: Provider registry changes** | Any change to `DownloaderProtocol`, `DownloaderRegistry`, registration, failover algorithm. | Failover matches Section 12.6.3; zero service-layer touches. |
| **G-5: Security configuration** | Any change to secrets handling, scrubber rules, Sentry `before_send`, rate-limit semantics. | No new leak path; rate limits enforce expected behavior. |
| **G-6: Payment integration** (V4+) | Any code under `payment/`. | Compliance, idempotency, refund semantics. |
| **G-7: Subscription enforcement** (V2+) | Premium gates, plan limits. | Plan matrix correct; no bypass. |
| **G-8: Production deploy** | Sprint 12 / release. | Smoke tests, restore drill, runbook current. |

PRs that touch a gate must reference the gate ID in the description; the merge is blocked until Owner posts `Gate <ID> approved`.

### 25.14 Test Reports (LOCKED — D-036)

Three living documents:

| File | Purpose | Update Cadence |
|---|---|---|
| `TEST_RESULTS.md` | Latest test-suite outcomes per category, with timestamps and git SHA. | Every CI run, every local validation run. |
| `SECURITY_REPORT.md` | Security validation results, scan findings, dependency advisories, mitigations. | Every pip-audit, bandit, security-test run; every incident. |
| `PERFORMANCE_REPORT.md` | Load-test results at every level, micro-benchmark history, capacity-planning snapshots. | Every load run; every micro-benchmark series. |

Update rules:
- All three are append-only. Mistakes get a corrective entry, not an edit.
- Every entry includes a UTC timestamp and the git SHA of the code that was tested.
- A PR that should have updated one of these and didn't is **not** done.

### 25.15 User Simulation & Load Testing Framework

The framework lives at `tests/simulation/` (D-034). Reusable, executable on demand, capable of generating realistic Telegram traffic at every load level. It is the **only** way to validate production readiness without real users.

#### 25.15.1 Simulated User Profiles (LOCKED set)

| Profile | File | Behavior |
|---|---|---|
| **Casual** | `tests/simulation/users/casual.py` | 1–3 downloads/day; small files; 5–30 min idle between actions. |
| **Active** | `tests/simulation/users/active.py` | 5–20 downloads/day; varied formats; ~5 min between actions. |
| **Heavy** | `tests/simulation/users/heavy.py` | Continuous requests; large files; ~30 s between actions. |
| **Abuse** | `tests/simulation/users/abuse.py` | Rapid-fire requests, queue-flood attempts, rate-limit-bypass attempts. **Must always be detected and blocked** — abuse profile failing to be blocked is a failing test. |
| **Premium** (V2+) | `tests/simulation/users/premium.py` | Higher frequency, priority-queue usage, larger volumes. Disabled until premium tier exists. |

Each profile emits a stream of `SimulatedAction` events (start chat, send URL, click format, click quality, click resend, etc.) on its own schedule.

#### 25.15.2 Telegram Bot User Simulator

`tests/simulation/bot_client/client.py` performs, against the sandbox bot:
- Start conversations (`/start`).
- Send URLs.
- Click format / quality buttons.
- Request cached files.
- Trigger retry flows.
- Send admin commands (when impersonating Owner/Moderator).

Realistic-user behavior: small randomized delays between actions; deterministic seed in CI.

#### 25.15.3 AI-Controlled Traffic Generation

Generators under `tests/simulation/traffic/`:

| Generator | Purpose |
|---|---|
| `RandomTraffic` | Sample user profiles per a configured distribution. |
| `ScheduledSpike` | Inject a defined spike (e.g., 100 → 1000 users over 30 s). |
| `PeakHour` | Real-world peak-hour distributions per platform. |
| `Viral` | One URL spreading to thousands of users in minutes. |
| `PlatformPattern` | Platform-specific patterns (TikTok-heavy weekend, YouTube prime time). |

Reproducible with a fixed seed; stochastic on demand for live validation.

#### 25.15.4 Load Levels (referenced from 25.10.1)

L1 = 10 (smoke), L2 = 50 (sprint exit), L3 = 100 (sprint exit), L4 = 500 (pre-release), L5 = 1000 (pre-release), L6 = 5000 (pre-major-release).

#### 25.15.5 Metrics Collection (LOCKED catalog)

| Layer | Metrics |
|---|---|
| **Application** | Response time (p50/p95/p99), error rate, request throughput. |
| **Queue** | Queue depth, processing time, retry rate, fan-out cohort size. |
| **Workers** | Worker utilization, processing speed, failure rate, heartbeat liveness. |
| **Redis** | Memory usage, ops/sec, cache hit ratio, cache miss ratio, lock-acquire latency. |
| **Database** | Query latency (p50/p95), pool usage, write throughput, partition I/O. |
| **Providers** | Success rate, failure rate, fallback activation rate, health transitions. |

Each metric is captured per run, written to `PERFORMANCE_REPORT.md`, and exposed via Prometheus during the run.

#### 25.15.6 Stress Test Scenarios (LOCKED)

| ID | Scenario | Expected Behavior |
|---|---|---|
| **ST-1** | 100 → 1000 users in 30 s | Queue absorbs; SLO p95 may degrade; no errors; no data loss. |
| **ST-2** | Queue flood (5000 jobs in 60 s) | Backpressure surfaces; jobs eventually drain; no data loss. |
| **ST-3** | Cache invalidation storm | Cache rebuilds without thundering-herd; rate-limit applies to redownload bursts. |
| **ST-4** | Provider outage (kill primary, no secondary) | Clear user-facing error; registry retries after cooldown. |
| **ST-5** | Database slowdown (artificial 1 s latency) | Timeouts surface gracefully; bot reports degraded mode. |
| **ST-6** | Redis restart | Active downloads resume from `active_downloads` PG; no duplicate work; no lost user data. |

#### 25.15.7 Capacity Planning Reports

After each L4 / L5 / L6 run, an automated capacity report appends to `PERFORMANCE_REPORT.md`:
- Current maximum supported users (steady state).
- Current maximum downloads/hour.
- Current maximum queue throughput.
- Estimated hardware requirements at +50% load.
- Scaling recommendations (vertical vs. horizontal; which subsystem hits the wall first).

#### 25.15.8 Framework Components

| Component | File | Purpose |
|---|---|---|
| `SimulationRunner` | `tests/simulation/runner.py` | Orchestrates a load level: instantiates profiles, drives traffic, collects metrics. |
| `BotClient` | `tests/simulation/bot_client/client.py` | Telegram Bot User Simulator. |
| `MetricsCollector` | `tests/simulation/metrics/collector.py` | Streams metrics into `PERFORMANCE_REPORT.md` and Prometheus. |
| `ReportWriter` | `tests/simulation/metrics/report_writer.py` | Formats and appends entries to the three report files. |
| `ScenarioCatalog` | `tests/simulation/scenarios/__init__.py` | Registry of stress scenarios. |
| `UserProfile` (abstract) | `tests/simulation/users/base.py` | Base class for all user profiles. |

#### 25.15.9 Invocation

A single command runs any level / profile combination:

```
python -m tests.simulation.runner --level=L3 --profile=Active,Heavy --duration=600 --seed=42
```

- Without `--seed`: stochastic.
- Without `--duration`: defaults from `tests/simulation/runner.py`.
- Production credentials are rejected by `SimulationRunner.__init__`.

#### 25.15.10 AI Agent Rule (Simulation)

- Production credentials must never appear under `tests/simulation/`. CI rejects any commit that introduces them.
- Simulation runs must be reproducible: same seed + same code → same outcome.
- New profiles or scenarios must be added to Section 25.15 in this document **and** to `PROJECT_PROGRESS.md`.
- Simulator code is reviewed and maintained with the same rigor as production code.

### 25.16 Manual Test Catalog (V1)

| ID | Test | Sprint |
|---|---|---|
| M-01 | `/start` from a new account creates a user | S4 |
| M-02 | Banned user receives ban message and nothing else | S4 |
| M-03 | Send a URL; receive format keyboard within 3 s | S5 |
| M-04 | Pick format → quality keyboard → download → receive file | S6 |
| M-05 | Send the same URL again → instant cached delivery | S6 |
| M-06 | Two accounts request the same URL within 1 s → both receive | S7 |
| M-07 | Open history → paginate → resend → instant delivery | S7 |
| M-08 | `/stats` shows expected numbers | S8 |
| M-09 | `/ban`, `/unban`, `/userinfo` correct | S8 |
| M-10 | Broadcast to 100 synthetic users; counters match | S8 |
| M-11 | Ad displayed at the configured frequency | S9 |
| M-12 | Premium user sees no untargeted ads | S9 |
| M-13 | `ads_enabled=false` suppresses ads | S9 |
| M-14 | Force a `CRITICAL` log; Telegram alert lands | S10 |
| M-15 | Restore drill produces a working bot | S10 |
| M-16 | Production smoke tests | S12 |
| M-17 | Run L4 load level; SLOs hold | S11 |
| M-18 | Run S-3 provider failover (mocked secondary) | S11 |
| M-19 | Run S-4 worker crash recovery | S11 |
| M-20 | Run S-5 Redis restart recovery | S11 |
| M-21 | Security test categories all pass | S11 |
| M-22 | Abuse profile (Section 25.15.1) blocked end-to-end | S11 |

---

## 26. Progress Tracking

### 26.1 Statuses

| Status | Meaning | Required to transition out |
|---|---|---|
| **Not Started** | Task is on the backlog. | Owner approval to begin. |
| **In Progress** | Active work. | All Definition of Done items (Section 1.8) met. |
| **Blocked** | Cannot proceed. Reason documented. | Blocker cleared. Reason archived in PR. |
| **Under Review** | PR open. | Approved or changes requested. |
| **Completed** | Merged + verified. | None. Move to next task. |

### 26.2 The Live Progress File

The live, mutable status lives in **`PROJECT_PROGRESS.md`** (companion file). That file is the single source of truth for "where are we right now". This document (`MASTER_PLAN.md`) stays stable; `PROJECT_PROGRESS.md` is updated on every task transition.

`PROJECT_PROGRESS.md` contains:
- Sprint Status, Completion Percentage, Completed Tasks, In Progress Tasks, Blocked Tasks, Pending Tasks, Validation Results, Known Issues, Next Recommended Actions — for each sprint.
- A session-handoff section appended at the end of every work session.
- A files-modified log and validation-status log.

### 26.3 Update Cadence (LOCKED)

- **On every task transition** (start, complete, block, unblock): update the task's status marker in `PROJECT_PROGRESS.md`.
- **At the end of every task**: record completion date, validation results, test results, affected files, and implementation notes in `PROJECT_PROGRESS.md`.
- **At the end of every work session**: append a Session Handoff entry to `PROJECT_PROGRESS.md` with: current project state, completed work, remaining work, known issues, recommended next task, files modified, validation status.
- **At the end of every sprint**: write a Sprint Closeout entry in `PROJECT_PROGRESS.md` and stop. Owner reviews and marks the sprint `Completed`.

### 26.4 Documentation-Driven Development Rule (LOCKED)

`PROJECT_PROGRESS.md` must always reflect reality. Code and the progress file must never diverge.

- If a task is not fully implemented, validated, and tested → it must not be marked `[x] Completed`.
- If implementation outpaces the progress file → the PR fails review until the progress file catches up.
- If the progress file claims something is done that is not actually done → that is a documentation defect and must be corrected before any new work.

Status is never set to `[x] Completed` by an AI agent without all three of: (a) task acceptance criteria met, (b) validation results recorded, (c) human verification noted where required.

---

# Part VI — Appendices

## 27. Open Questions

These are unresolved at the time of writing. Each must be answered before the sprint that depends on it begins. The Owner is the answerer.

| ID | Question | Needed By |
|---|---|---|
| OQ-1 | Sentry: self-hosted or SaaS? Per-environment DSNs? | S10 |
| OQ-2 | CI provider (GitHub Actions assumed). | S0 |
| OQ-3 | Production hosting target (managed VPS / cloud / on-prem)? | S11 |
| OQ-4 | Admin API key authentication: single key or per-admin? | S8 |
| OQ-5 | Telegram alerts channel: dedicated chat? Owner DM? | S10 |
| OQ-6 | Object storage for temp files at scale: needed in V1 or V3? | S10 |
| OQ-7 | V2 roadmap document: when expected? | Pre-V2 |
| OQ-8 | Approved list of supported platforms (URL allowlist)? | S5 |
| OQ-9 | yt-dlp update cadence: monthly cron acceptable? | S5 |
| OQ-10 | ~~i18n keys for V1 (English only) — copy approved by whom?~~ **Resolved 2026-07-01 (Sprint 11.5).** English + Arabic, ~250+ keys; content specified directly by the Owner's own design session for this sprint (see D-061–D-064). | S4 |

## 28. Glossary

| Term | Definition |
|---|---|
| `file_id` | Telegram's identifier for an already-uploaded file. Re-using it bypasses upload. |
| `unique_file_id` | Telegram's bot-independent file identifier. |
| Cache hit | A request that is served from a stored `file_id` or metadata without re-doing the underlying work. |
| Fan-out | One in-flight download serving multiple waiting users. |
| Correlation ID | UUIDv7 attached to every log/record produced by one user request. |
| Worker kind | A label on a job (`download`, `broadcast`, etc.) selecting the worker type that handles it. |
| Fingerprint | The `(media_id, format, quality)` tuple that uniquely identifies a downloadable artifact. |
| Lazy reset | A counter reset performed at read time, not via a batch job. |
| RPO / RTO | Recovery Point Objective / Recovery Time Objective. |
| BCP-47 | IETF language tag standard (`en`, `ar`, `pt-BR`). |
| Provider | A concrete `DownloaderProtocol` implementation that talks to one specific download library or service (yt-dlp, gallery-dl, direct HTTP, etc.). V1 has one: `YtdlpProvider`. |
| `DownloaderRegistry` | The single entry point for all download and metadata calls. Selects, orders, and fails over between registered providers. The only place that knows which providers exist. |
| Failover | Automatically trying the next-best provider when the current one fails in a retryable way. Controlled by `provider_failover_enabled`. |
| Provider health | `OK` / `DEGRADED` / `UNAVAILABLE`. Tracked in `provider:health:{name}`. Drives registry selection. |
| `Capability` | An enum value describing what a provider can produce (`VIDEO`, `AUDIO`, ...). Open to additive growth. |

## 29. Supersession Notes (vs. prior docs)

This document overrides `project_reference.md` (v1.2) and `database_reference.md` (v1.0).

**Resolved inconsistencies** (originally identified during the 2026-06-23 audit, now closed by this document):

| Original conflict | Resolved by |
|---|---|
| `users.premium_expires_at` vs. `premium_expire_at` | D-001 (`premium_expires_at`) |
| `user_preferences` table shape | D-002 (surrogate id + UNIQUE user_id, lazy) |
| `advertisements` table shape | D-003 (rich schema with persisted analytics) |
| Ad targeting filter (`free_users_only` vs. `target_role`) | D-004 (`target_role` enum) |
| Settings key naming (`max_free_*` vs. `free_max_*`) | D-005 (`free_max_*`) |
| `cached_files.usage_count` INT vs. BIGINT | D-006 (BIGINT) |
| `cached_files.last_used_at` nullability | D-007 (NOT NULL DEFAULT NOW()) |
| `downloads.cached_file_id` constraint contradiction | D-008 (NULLABLE, ON DELETE SET NULL) |
| Multi-user fan-out without persistent state | D-009 (`job_waiters` table) |
| Ad delivery modulo timing | D-010 (post-increment) |
| `metadata_json` upsert clobbering | D-011 (COALESCE merge) |
| `daily_download_count` reset via batch | D-012 (lazy reset) |
| `jobs.id` UUIDv4 page-split risk | D-013 (UUIDv7) |
| No user cache (hot-path PG hammering) | D-014 (Redis user cache) |
| `downloads`/`jobs`/`error_logs` un-partitioned | D-015, D-016 (monthly partitioning from day one) |
| Missing `error_log_retention_days` seed | D-017 (seeded) |
| Missing ad-selection composite index | D-018 (added) |
| API versioning unspecified | D-019 (`/v1/` prefix) |
| PgBouncer deferred | D-020 (in V1) |
| Multiple queue forks risk | D-021 (single queue, `worker_kind` column) |
| Locale standard unspecified | D-022 (BCP-47) |
| UUIDv7 dependency choice | D-023 (in-tree helper) |
| `notifications_enabled` placement | D-024 (`user_preferences`) |
| Timeout strategy | D-025 (per-layer, defense in depth) |

Both prior documents remain in the repository for historical context. They are not authoritative. Any conflict between them and this document is resolved by this document. Both should eventually be archived under `docs/archive/`.

---

> **End of Master Implementation Plan.**
>
> This document is the canonical reference for the Telegram SaaS Download Bot. Every AI agent must read Section 1 before any other action. Every change to the schema, dependencies, configuration, or sprint plan requires an entry in Section 5 and Owner approval.
>
> **Revision History**
> - v2.0 (2026-06-23): Initial canonical master plan. Supersedes prior `project_reference.md` v1.2 and `database_reference.md` v1.0. Resolves 25 decisions (D-001 through D-025). Establishes 11 sprints with Definition of Done, validation, and stop points. Adds Future Versions Readiness Review (V2–V6), Extension Points Catalog, Database / API / Queue Evolution Strategies, AI Agent Execution Rules.
> - v2.1 (2026-06-23): Elevates `DownloaderRegistry` + `DownloaderProtocol` from a V6 deferred item to a LOCKED V1 architectural component (Section 12.6). Adds AI Hard Rules 11 (no provider references outside infrastructure) and 12 (progress-file update is part of DoD). Adds D-026 through D-030. Adds Extension Points EP-16, EP-17, EP-18. Adds six provider-related settings keys. Updates Sprint 5 from 7 tasks to 11 to absorb registry + provider implementation. Adds `PROJECT_PROGRESS.md` as the SSOT for implementation status; mandates session handoffs and sprint closeouts.
> - v2.2 (2026-06-23): Replaces Section 25 with comprehensive Testing, QA, Security Validation & Telegram Bot Verification strategy (16 sub-sections). Adds the User Simulation & Load Testing Framework with 5 user profiles, 5 traffic generators, 6 load levels, 6 stress scenarios, locked metrics catalog. Defines 8 Human Verification Gates. Locks the three report files (`TEST_RESULTS.md`, `SECURITY_REPORT.md`, `PERFORMANCE_REPORT.md`). Expands Section 1.8 DoD from 13 to 19 items. Adds D-031 through D-039. Restructures sprints: Sprint 10 becomes "Observability and Backup"; new Sprint 11 "Testing Framework, Security, Load and Stress" (14 tasks); Sprint 11 "Launch Readiness" renumbers to Sprint 12. Total sprints: 13. Total tasks: ~107.

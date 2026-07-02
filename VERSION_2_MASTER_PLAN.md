# Version 2 Master Plan — Monetization Base

> **Document Status:** APPROVED PLANNING BASELINE (Owner workshop, 2026-07-02; refinement rounds 1–2 applied 2026-07-02)
> **Version:** 1.2
> **Owner:** Project Architect
> **Scope:** Version 2 only. `MASTER_PLAN.md` remains the canonical V1 architecture document; nothing here modifies V1 architecture except where Section 15 (Migration Strategy) explicitly says so, with rationale and rollback story.
> **Process:** Every decision in this document was made in the V2 product-design workshop (2026-07-01 → 2026-07-02) between the Owner and the Architect. Decisions are recorded in Section 4 with rationale and rejected alternatives.
> **Sprint rule (Owner directive):** every version plan V2–V6 is divided into sprints, each with Goal, Features, Dependencies, Deliverables, Risks, Acceptance Criteria, and Migration Impact. Every sprint ends in a stable, deployable state.

---

## Table of Contents

1. [Goals](#1-goals)
2. [Non-Goals (Explicitly Out of V2)](#2-non-goals-explicitly-out-of-v2)
3. [Feature Summary](#3-feature-summary)
4. [V2 Decision Log](#4-v2-decision-log)
5. [Architecture Changes](#5-architecture-changes)
6. [Database Changes](#6-database-changes)
7. [Cache Changes](#7-cache-changes)
8. [Queue Changes](#8-queue-changes)
9. [Background Jobs](#9-background-jobs)
10. [User Flows](#10-user-flows)
11. [Admin Flows](#11-admin-flows)
12. [Monitoring](#12-monitoring)
13. [Security](#13-security)
14. [Performance Considerations](#14-performance-considerations)
15. [Migration Strategy](#15-migration-strategy)
16. [Risks](#16-risks)
17. [Future Compatibility](#17-future-compatibility)
18. [Sprint Plan](#18-sprint-plan)
19. [Deferred to Future Workshops](#19-deferred-to-future-workshops)
20. [Future Technical Debt Avoided](#20-future-technical-debt-avoided)

---

## 1. Goals

1. **Monetization base.** Introduce the final Plans → Subscriptions → Entitlements architecture, with Manual Grant as the only subscription source in V2. Payment providers (V4) must later plug in as new subscription *sources*, never as architecture changes.
2. **Premium value.** A single user-visible Premium plan with meaningful, entitlement-driven benefits, while Free stays useful.
3. **Multi-link convenience.** Multiple independent URLs in one message, one format/quality choice, per-link independent processing with reservation-based quota.
4. **Analyzer maturity.** Capability classification and normalized metadata so future features (Playlists, Albums, Stories) are routing changes, not analyzer redesigns.
5. **Fair scheduling.** Batches and premium priority must coexist with fairness across users.
6. **Monetization signal.** Advertisement analytics (impressions, delivery, per-language, per-plan) to inform V4 pricing decisions.
7. **i18n hardening.** Land the three actionable outcomes of the V2 localization architecture review.

## 2. Non-Goals (Explicitly Out of V2)

| Excluded | Where it went |
|---|---|
| Payment providers (Stars, Stripe, Paymob, …) | V4. V2 architecture is payment-*ready*, payment-*free*. |
| Playlist Downloads (the feature) | Own future workshop + dedicated sprint(s). Only the entitlement key ships in V2. Playlists ≠ multiple links — independent product capabilities (Owner directive, 2026-07-02). |
| Ad click tracking | Future (needs public redirect endpoint). V2 `ad_events` schema is click-*compatible* (enum value reserved), click-*free*. |
| Multiple premium tiers user-visible | Internally supported day one; user-visible Plus/Pro/Enterprise are future data changes. |
| Web dashboard | V3. All V2 data (plans, subscriptions, ad_events) is designed to be read by it. |
| Grace period on expiry | Rejected by Owner. Hard expiry with 4-touchpoint notification instead. |

## 3. Feature Summary

**User-facing**
- ⭐ Premium plan: higher daily limit, larger files, reduced/zero cooldown, priority queue, ad-free, more links per message, higher concurrent downloads, 2K/4K video, FLAC/lossless audio.
- ⭐ Premium screen: current plan, expiry date, remaining days, benefits list, Renew button (V2: "contact the administrator").
- Multiple links per message (Free and Premium, different caps), one format + one quality choice, per-link results with failure reasons and automatic quota refunds.
- Playlist URLs: friendly localized "planned for a future version" message; hybrid watch-URLs download the single video.
- Expiry notifications at T-7d, T-3d, T-24h, and immediately after expiry.

**Admin-facing**
- Grant / Extend / Remove Premium, Set Expiration (presets + custom date).
- Advertisement analytics: total + daily impressions, delivery counts, per-language, per-plan.

**Internal**
- Plans / Subscriptions / Entitlements (JSONB entitlements, startup-validated).
- Analyzer capability classification + normalized `MediaAnalysis` object with identity block; analyze-once reuse; raw-metadata reservation (config-gated).
- Global shared media cache as a named core rule + multi-level identity resolution (canonical ID → URL normalization → fingerprint fallback).
- Reservation → Settlement quota model.
- Virtual-time queue fairness + per-user concurrency caps.
- Feature flags for staged rollout / deploy-free rollback of every major V2 feature.
- `is_premium` fully retired by end of V2.

## 4. V2 Decision Log

Every non-obvious decision, with rationale. IDs continue the `MASTER_PLAN.md` D-series in a V2 namespace.

| # | Decision | Rationale | Rejected Alternatives |
|---|---|---|---|
| V2-D-001 | Subscriptions point at users (`subscriptions.user_id` FK), never `users.subscription_id`. | Renewals/plan changes append rows instead of repointing the user; V4 payment states (pending/expired/refunded/canceled) need multiple rows per user with one current. | `users.subscription_id` (loses history, repoint-on-renewal). |
| V2-D-002 | Free = absence of an active subscription row. No subscription rows for free users. | Avoids a 300k-row backfill and keeps the table proportional to paying users. Resolver returns the Free plan when no active row exists. | Explicit Free subscription rows. |
| V2-D-003 | One current subscription per user, enforced by partial unique index `UNIQUE(user_id) WHERE status='active'`. | Database-level guarantee; concurrent grants cannot race into two active rows. | Application-level checks only. |
| V2-D-004 | Entitlements are a typed `entitlements JSONB` column on `plans`, validated at startup against a code-side registry in `domain/`. | Read-as-a-whole + cached, so EAV queryability buys nothing; JSONB is simpler to seed and load. Startup validation mirrors the locale-catalog fail-fast philosophy. | `plan_entitlements` EAV table. |
| V2-D-005 | Business logic reads entitlements only — never `is_premium`, never plan codes. One resolver (`EntitlementService`); plan-code branches (`if plan == "premium"`) are forbidden the same way `is_premium` checks are. | Prevents re-scattering the exact problem V2 removes. Adding Plus/Pro must be an INSERT, not a code hunt. | Per-feature plan checks. |
| V2-D-006 | Manual Grant is the only V2 subscription source. `source` enum ships with `manual_grant` + reserved values (`stars`, `stripe`, `paymob`, `promo`). | Owner decision. Payment providers later create subscription rows through the same `SubscriptionService` API; no architecture change. | Early Telegram Stars integration (Owner rejected for V2). |
| V2-D-007 | Expiry is evaluated lazily by the resolver (`expires_at < now()` ⇒ Free), like D-012's lazy daily reset. A background job tidies `status` and fires the T+0 notification. | Correctness never depends on a scheduler tick; the job is UX + hygiene only. | Status flip as the source of truth (midnight-batch fragility). |
| V2-D-008 | Expiry notifications at T-7d, T-3d, T-24h, T+0; idempotency via a milestone bitmask column on `subscriptions`. | Owner-approved touchpoints. Bitmask is the cheapest restart-safe dedupe (Principle 4.2.6); a notification-log table is over-engineering at this volume. | Notification log table; no dedupe. |
| V2-D-009 | In-flight jobs keep the priority stamped at enqueue; expiry affects only new jobs. | Owner decision; already how the queue works (score stamped at enqueue) — zero code. | Re-scoring queued jobs on expiry. |
| V2-D-010 | Quota model is Reservation → Settlement: admission atomically reserves N slots; failures refund automatically; successes keep their slot. | User-visible rule stays "failed downloads never consume quota" while making overshoot impossible and denying the free-labor attack (failures still cost attempts via cooldown/rate limits). | Count-on-completion only (overshoot + abuse hole). |
| V2-D-011 | Batch admission is **partial**: with R slots remaining and N>R links, R are admitted, N−R rejected per-link with a clear message (+ upsell for Free). | Converts better than a hard bounce; trivial under reservation. | Reject entire batch. |
| V2-D-012 | Fairness = virtual-time scoring within priority bands (score = band offset + enqueue time + per-user pending spread), keeping the single ZSET (D-021). Plus a per-user concurrent-jobs cap from entitlements, enforced worker-side. | Batches self-interleave with zero new infrastructure; UUIDv7 tie-break FIFO is preserved. Per-user sub-queues with round-robin rejected: forks the queue, complicates dead-letter, violates D-021's spirit. | Per-user sub-queues; weighted round-robin scheduler. |
| V2-D-013 | Concurrency cap enforced *after* dequeue: worker checks the user's active count; if at cap, re-enqueue with a small score delay. Dequeue Lua stays dumb. | Keeping user-lookup out of Lua keeps the atomic pop simple and auditable; occasional requeue churn is acceptable at V2 scale. | Cap inside the Lua script (needs member→user mapping in Redis, complex + fragile). |
| V2-D-014 | Quality selection rule: highest available quality ≤ user's selection, additionally capped by plan entitlement; never auto-upgrade above the selection. | Owner decision. Predictable, never exceeds plan ceiling, never surprises with larger files. | Nearest-absolute quality (can exceed selection and plan). |
| V2-D-015 | Mixed video+audio batches: the chosen format applies to compatible links; incompatible links automatically get that platform's best default; the summary reports per-link what happened. No extra wizard steps. | Owner decision: UX stays simple. | Reject mixed batches; split two-step choice. |
| V2-D-016 | Pure playlist URLs are detected at analysis, rejected with a localized "Playlist Downloads are planned for a future version" message, quota refunded. Hybrid `watch?v=X&list=Y` URLs download the single video (`--no-playlist` semantics). | Owner decision. Rejection branch is the future playlist pipeline's entry point — one message swapped for a real flow later. | Silent first-item download; playlist expansion. |
| V2-D-017 | Analyzer classifies every URL into a capability (VIDEO, AUDIO, PLAYLIST, ALBUM, STORY, SHORT, LIVE, UNKNOWN) in two stages: cheap URL-pattern pre-classification, authoritative reclassification from extractor metadata. Business logic operates on the final capability, never the raw URL. | URL alone can't reliably classify (short links, premieres). Two stages give instant playlist rejection *and* correct final routing. | One-stage URL-regex classification (wrong for short links); classification-by-extraction only (wastes a network call on pure playlist URLs). |
| V2-D-018 | Live policy: ongoing live stream → localized rejection, no quota; ended live (VOD) → processed as normal video. STORY/SHORT classify distinctly but process as video in V2. | Unbounded content can't be downloaded; classification exists so future features diverge without analyzer changes. | Recording lives (unbounded storage/time); treating lives as errors. |
| V2-D-019 | Analyzer returns a normalized metadata object: a small **typed core** (guaranteed-shape, null-tolerant) + an **`extras` dict** passthrough for platform-specific fields. Fields are promoted from extras to core only when a feature consumes them. Persisted via existing `media_metadata.metadata_json` COALESCE merge (D-011); the analyzer is the single source of truth — services never re-query platforms. | Full normalization of ~30 fields across all platforms is unbounded maintenance chasing yt-dlp field drift. Core+extras gives the same graceful-partial-metadata guarantee at a bounded surface. | Full normalization of every field; new metadata tables. |
| V2-D-020 | Entitlement **keys** are architecture; entitlement **values** are configuration/seed data and do not appear in this document. | Owner directive: business values change without touching architecture docs. | Hard-coding limits in the plan. |
| V2-D-021 | Ad analytics uses an append-only, monthly-partitioned `ad_events` table (impression/delivery events with locale + plan dimensions); existing `advertisements.impressions`/`clicks` counters become denormalized rollups. `event_type` reserves `click` for the future. | Counters can never answer per-day/per-plan/per-language retroactively; events can always rebuild counters. V2's purpose is monetization signal for V4. | Counters only; full event-streaming stack (overkill). |
| V2-D-022 | Grant semantics: Grant starts now; Extend adds to current expiry when an active subscription exists, otherwise starts now; Set Expiration overrides absolutely. Duration presets + custom date in the admin panel. | Owner decision (incl. the Extend-from-current-expiry rule). | Extend-from-now (silently eats remaining paid time). |
| V2-D-023 | ⭐ Premium button is the primary entry point; `/premium` command exists for convenience but is secondary. | Owner decision; mirrors the language-picker "one screen, multiple entry points" pattern. | Command-first UX. |
| V2-D-024 | `is_premium`/`premium_expires_at` retirement is gradual: introduce → backfill → shadow-parity → cutover → drop, across three sprints. Columns are dropped only after cutover has soaked in production. | Owner-approved 4-step migration; always a rollback window where previous code still works. | One-shot migration. |
| V2-D-025 | The `free_*`/`premium_*` settings pairs (D-005) are deprecated in favor of plan entitlements, and removed at cleanup. During shadow mode they remain authoritative. | Two live sources of truth for limits is a standing defect; entitlements are the successor. Seed values migrate into plan rows. | Keeping both indefinitely. |
| V2-D-026 | i18n hardening lands as the first V2 sprint: startup placeholder-set validation, per-locale coverage metric with `admin.*` carve-out, plural-strategy decision recorded (CLDR suffix keys via `babel` when first needed). | Outcomes of the V2 localization architecture review (2026-07-02): placeholder typos are statically checkable and currently reach users as raw templates; coverage invisibility bites at 10+ languages; plural mechanism must be decided before catalogs would need restructuring. | Deferring until language #3 (the review's findings decay). |
| V2-D-027 | `MediaAnalysis` gains an `identity` block (platform, canonical_media_id, id_source, source/canonical URL); identity resolution is a strict 4-level strategy: canonical platform ID → URL normalization → metadata fingerprint (fallback only, stable fields only) → content fingerprint (reserved, not V2). Mutable statistics are never key material. | Cache keys must survive metadata churn (titles/views change; IDs don't). Level 2 makes dedup locks and analysis reuse hit across URL spellings. Owner core requirement 2026-07-02. | Keying on URLs (spelling-sensitive); keying on title/metadata (mutable). |
| V2-D-028 | Level-3 fingerprints are stored as prefixed synthetic values (`fp:<hash>`) in the existing `media_metadata.video_id` column; the prefix convention reserves `ch:<hash>` for future Level-4 content hashes. | Zero schema change; `UNIQUE(platform, video_id)` keeps doing the dedup work; prefixes make id provenance self-describing and Level 4 a data-format addition, not a migration. | New identity column/table; unprefixed hashes (ambiguous provenance). |
| V2-D-029 | `cached_files.last_verified_at` (nullable, additive), written on successful cache-hit delivery — delivery *is* verification, no extra Telegram call. | Owner cache-statistics requirement; gives future LRU/TTL/warming policies a staleness signal; complements the existing `CachedFileExpiredError` self-healing eviction. | Active verification job (pointless API load); overloading `last_used_at` (conflates use with proof of validity). |
| V2-D-030 | Raw extractor output retention is reserved: config-gated (`analyzer_raw_metadata_enabled`, default off), stored under the reserved `_raw` namespace of `media_metadata.metadata_json`, size-capped with logged truncation. | Future features can mine fields without re-extraction or analyzer redesign; off by default because raw info dicts can exceed 100 KB per media. | Always-on raw storage (unbounded growth); no reservation (future features force re-extraction). |
| V2-D-031 | Feature flags for every major V2 feature, implemented as `settings`-table keys read through the existing cached settings service. Flags gate entry points only; every off-state is a defined tested behavior; each flag is removed one release after its feature stabilizes. | Staged rollout + deploy-free rollback (Owner requirement) at zero new infrastructure. Removal rule prevents permanent flag-debt. | New flag service/library (needless dependency); env-var flags (require restarts); permanent flags. |
| V2-D-032 | Analysis adapters are provider-agnostic under the D-026/D-029 contract: a new platform = one adapter returning `MediaAnalysis`; platform-specific branches outside adapters are architecture defects. | Same contract that already governs download providers; keeps V6 multi-engine and future platforms additive. | Ad-hoc per-platform branching in services. |
| V2-D-033 | Analyze-once: `MediaAnalysis` travels with the request lifecycle; downstream services never re-extract or re-query platforms. Short-TTL Redis cache keyed by identity lets concurrent/near-in-time requests share one extraction. | Every expensive operation happens once (Owner principle). Extraction is the most expensive pre-download step; batches would otherwise multiply it. | Per-service re-extraction; long-TTL analysis cache (formats/availability drift). |
| V2-D-034 | `analysis_version` int on `MediaAnalysis`, persisted with every snapshot. V2 behavior: set it, nothing else (reserved). Future analyzer overhauls bump it to detect and lazily refresh stale persisted analysis. Explicitly scoped to analysis snapshots — never invalidates `cached_files`. | Without a version stamp, "is this old snapshot still shaped right?" is unanswerable retroactively; stamping is free now, un-stampable later. The cached_files exclusion prevents an analyzer release from accidentally orphaning millions of valid cached uploads. | No versioning (undetectable staleness); versioning the file cache too (needless mass invalidation). |
| V2-D-035 | Capability forward-compatibility rule: business logic treats any capability value it does not explicitly handle exactly like UNKNOWN (polite rejection, no quota). New capabilities (Podcast, Audiobook, Document, Carousel, …) are enum additions consumed feature-by-feature. | Makes adding an enum value always deploy-safe in any order (analyzer can classify before any feature handles it); the analyzer never needs redesign per media type. | Exhaustive-match requirements (every addition touches all consumers at once). |

## 5. Architecture Changes

### 5.1 Subscription Domain (new)

New domain concepts, all inside existing layers (no new layers, no cross-layer imports):

```
domain/
  entities/plan.py            Plan (code, name, is_active, entitlements)
  entities/subscription.py    Subscription (id, user_id, plan_id, status, source, starts_at, expires_at)
  enums.py                    += SubscriptionStatus, SubscriptionSource, Capability
  entitlements.py             EntitlementRegistry — the typed key registry (see 5.2)
services/
  entitlement_service.py      resolve(user) -> ResolvedEntitlements   (the ONLY read path)
  subscription_service.py     grant / extend / remove / set_expiration (the ONLY write path)
infrastructure/database/
  models/plan.py, models/subscription.py + repositories
```

**Resolution flow (hot path):** incoming update → auth middleware loads `UserSnapshot` (existing D-014 Redis cache, 30 s TTL) → snapshot now carries `plan_code` + resolved entitlements, computed at cache-fill time with one indexed lookup for the active subscription. Expiry is evaluated lazily at resolution (V2-D-007). No new per-update queries.

**Write flow:** all four admin actions go through `SubscriptionService`, which invalidates the user's cache entry (existing invalidation path) and emits a structured audit log entry (Principle 4.2.4). Future payment providers call the same service (V2-D-006) — they are *sources*, not architectures.

### 5.2 Entitlement Registry

The registry in `domain/entitlements.py` defines every key, its type, and its validation rule. Plans' JSONB is validated against it at startup — unknown key, missing key, or wrong type fails boot (same philosophy as locale-catalog validation). **Keys are architecture; values are seed data (V2-D-020).**

| Key | Type | Consumed by |
|---|---|---|
| `daily_download_limit` | int | RateLimitService admission |
| `max_file_size_mb` | int | Download pipeline pre-check |
| `cooldown_seconds` | int | RateLimitService |
| `batch_max_links` | int | Multi-link admission |
| `max_concurrent_jobs` | int | Worker-side dequeue cap |
| `max_video_height` | int | Quality keyboard + server-side revalidation |
| `audio_formats` | list[str] | Format keyboard + server-side revalidation |
| `ad_free` | bool | AdService gating |
| `priority_band` | str (enum: normal/high, extensible) | Queue score computation |
| `playlists_enabled` | bool | Reserved. Seeded false on every plan. Feature ships after its own workshop (V2-D-016, Section 19). |

Forbidden pattern (enforced in code review): `if user.is_premium`, `if plan_code == "premium"`. The only legal read is `entitlements.<key>`.

### 5.3 Analyzer: Capability Classification + Normalized Metadata

Two-stage classification (V2-D-017), inside the existing URL Analyzer service — no new service:

1. **Stage 1 — URL pre-classification** (no network): pattern tables per platform classify into a *provisional* capability. Pure PLAYLIST URLs short-circuit here → localized rejection (V2-D-016), zero extraction cost, quota refunded. Hybrid video+list URLs are stripped to single-video semantics.
2. **Stage 2 — extraction classification** (authoritative): the extractor's own metadata (`_type`, live status, …) produces the final `Capability`. Ongoing LIVE → localized rejection (V2-D-018). Reclassification (e.g. short-link turned out to be a playlist) re-routes to the same rejection paths.

**Normalized analysis object** (V2-D-019, expanded V2-D-027), returned by every successful analysis — the single source of truth for all downstream services:

```
MediaAnalysis
  identity:                  # WHO this media is — cache + dedup key material (5.7)
    platform: str
    canonical_media_id: str  # Level 1–3 derivation, see 5.7.2
    id_source: enum          # canonical | fingerprint  (Level 4 reserved: content_hash)
    source_url: str          # exactly what the user sent
    canonical_url: str|null  # normalized form (Level 2)
  capability: Capability     # VIDEO | AUDIO | PLAYLIST | ALBUM | STORY | SHORT | LIVE | UNKNOWN
  analysis_version: int      # analyzer contract version, persisted with the snapshot (V2-D-034)
  core:                      # typed, EVERY field nullable
    title, description, author, duration_seconds, thumbnail_url, upload_date
    stats: views, likes, comments, shares, favorites    # snapshot-at-analysis, never live
    formats: [ {format_id, kind, height, width, fps, codec, hdr, audio_format,
                filesize_estimate} ]
  extras: dict               # platform-specific passthrough, promoted to core only when a
                             # feature consumes it: channel_id, uploader_id, verified,
                             # subscriber_count, album_info, story_info, live_info, chapters, …
  raw: dict|null             # full extractor output — config-gated, default OFF (V2-D-030)
```

Rules:
- Missing fields are null/absent; **nothing downstream may require a field's presence** — platforms expose different metadata and the system degrades gracefully.
- `filesize_estimate` is explicitly an estimate.
- **Statistics are snapshots, informational only.** Views, likes, comments, shares, favorites are captured at analysis time. No business logic may ever branch on them — not gating, not quota, not scheduling, not caching (they are already banned as identity inputs, 5.7.2). Display and analytics consumers must label them as at-analysis values.
- **Preview contract:** the core must always carry enough to render a media preview card — thumbnail, title, author, duration, platform — whenever the platform exposes them. Any future UI (confirmation screens, history, V3 dashboard) renders previews from the persisted `MediaAnalysis` alone; needing a second metadata request just to draw a preview is a contract violation.
- **Future consumers, by design:** Search, Favorites, Smart Recommendations, the V3 Web Dashboard, User History enrichment, Recently Downloaded, and Media Preview Cards all read the persisted normalized metadata. None of them may re-query platforms — the snapshot in `media_metadata` is their source. (This is documentation of intent, not V2 scope: none of those features ship in V2.)
- **Capability extensibility:** future capabilities (Podcast, Audiobook, Document, Carousel, Podcast Episode, …) are **enum additions, never analyzer redesigns**. Forward-compatibility rule: business logic must treat any capability it does not explicitly handle exactly like UNKNOWN (polite rejection, no quota) — so adding an enum value is always safe before any feature consumes it.
- Persistence: merged into `media_metadata.metadata_json` via the existing D-011 COALESCE merge — richer never clobbered by cheaper — together with `analysis_version`.
- **Raw metadata reservation (V2-D-030):** when `analyzer_raw_metadata_enabled` (config, default `false`) is on, the untouched extractor output is stored under the reserved `_raw` namespace of `metadata_json`, size-capped (configurable) with truncation logged. Purpose: future features can mine fields without re-extracting or redesigning the analyzer. Off by default because raw yt-dlp info dicts can exceed 100 KB per media.

**Provider-agnostic extensibility (V2-D-032):** analysis adapters follow the same contract as download providers (D-026/D-029): adding a platform = one new adapter that returns `MediaAnalysis`. Business logic branches on `capability` and entitlements, never on platform names; a platform-specific branch outside the adapter is an architecture defect, not a workaround.

**Provider independence (explicit restatement):** every provider — yt-dlp today, custom extractors, the V6 engines — returns the **same normalized contract** (`MediaAnalysis` for analysis, the D-026 protocol for downloads). Replacing or adding a provider changes exactly one adapter in `infrastructure/`; downstream services, handlers, workers, and the API must require **zero** changes, per the D-029 test: any required change there means the abstraction is broken and must be fixed first.

**Analyzer versioning (V2-D-034, reserved):** `MediaAnalysis.analysis_version` is a code constant persisted with every snapshot. V2 sets it and does nothing else. When a future analyzer change is significant enough that old snapshots mislead (new identity logic, restructured formats), the version bump lets the system detect stale persisted analysis and refresh lazily on next touch. Scope boundary: the version governs **analysis snapshots only** — it must never invalidate `cached_files`; downloaded media keyed by identity + format + quality stays valid regardless of how the analyzer evolves.

**Analyze-once, reuse everywhere (V2-D-033, strengthened):** every expensive operation happens once per request lifecycle. The `MediaAnalysis` object produced at analysis time travels with the request (format/quality selection, admission, job creation, delivery, history) — **any service needing metadata consumes it; a second extraction within the same request lifecycle is an architecture defect.** A short-TTL Redis entry keyed by `identity` lets concurrent and near-in-time requests for the same media reuse one extraction (Section 7).

**Long-term extensibility principle:** every new platform or media type integrates by **extending existing abstractions** — a new analysis adapter, a new capability enum value, a new entitlement key, a new subscription source — **never by modifying existing business logic**. If adding a platform or media type forces edits inside `services/`, `bot/`, or `workers/` beyond registration, the abstraction has failed and gets fixed before the feature proceeds. Platform support stays additive, not invasive.

### 5.4 Multi-Link Request Pipeline

Sits in front of the existing single-download pipeline; each admitted link becomes a **standard, independent job** (same job type, same quota unit, same delivery path — this is the whole design):

```
message → extract URLs → cap check (batch_max_links) → quota reservation (partial admission)
       → Stage-1 classify (reject playlists/etc., refund) → bounded-concurrency analysis + progress
       → summary → one Format choice → one Quality choice (V2-D-014/015)
       → N independent jobs enqueued → per-link progress → completion summary (successes, failures + reasons, refunds)
```

Single-URL messages take the same path with N=1 — one pipeline, not two.

### 5.5 Queue Fairness

See Section 8. No new queue, no new keys beyond a per-user active counter; D-021's single-queue decision stands.

### 5.6 Advertisement Analytics

`AdService` emits an `ad_events` row per impression/delivery (with locale + plan dimensions) alongside the existing counter increments, which become denormalized rollups (V2-D-021). Aggregation queries power the admin Statistics screens; a daily rollup job keeps dashboard reads off the raw partitions (Section 9).

### 5.7 Global Shared Media Cache — Core System Rule

**The media cache is platform-level and GLOBAL. It never belongs to a user. Users own download history; the platform owns cached media. The two concepts remain independent forever.** (Owner core requirement, 2026-07-02.)

V1 already implements the substance of this rule — this section makes it a named, binding architecture rule and defines the V2 deltas:

| Rule | Status |
|---|---|
| Cache keyed by platform + canonical media ID + format + quality, no user dimension | **V1** — `media_metadata UNIQUE(platform, video_id)` → `cached_files UNIQUE(media_id, format, quality)` |
| Cache hit ⇒ send cached `telegram_file_id` immediately, no download, bump usage stats, record in *that user's* history | **V1** — canonical cache-hit flow |
| Cache miss ⇒ download once, upload once, store file ID globally, immediately available to every future user | **V1** |
| Concurrent identical requests ⇒ exactly ONE download; all waiters served from the one result | **V1** — duplicate-lock + `job_waiters` fan-out (D-009) |
| History ≠ cache: `downloads` records who downloaded what; eviction degrades history to view-only, never deletes it | **V1** — D-008 |
| Global stats: usage count, first cached, last used, file ID, unique file ID | **V1** — `cached_files` columns |
| **Last Verified** timestamp + stale-file-ID self-healing bookkeeping | **V2** — new `cached_files.last_verified_at` (6.5, V2-D-029) |
| **Multi-level identity resolution** (5.7.2) | **V2** — analyzer identity block |
| Future cache policies (LRU, TTL, storage limits, popular-content retention, cache warming) | **Ready** — `ix_cached_last_used` + `ix_cached_usage_count` + nullable-history eviction (D-008) already support all five; policies are future *jobs*, not redesigns |

One binding ordering rule: **entitlement gating happens before cache lookup.** A cached 4K file never leaks to a plan that cannot request 4K — the cache accelerates permitted downloads; it never bypasses admission.

#### 5.7.2 Multi-Level Cache Detection Strategy (V2-D-027/028)

The cache must never key on mutable metadata (titles, descriptions, view counts, usernames). Identity resolution runs in strict preference order; the result lands in `MediaAnalysis.identity.canonical_media_id`:

- **Level 1 — Canonical media identifier (primary).** The platform's own stable ID (YouTube video ID, TikTok video ID, Instagram media ID, …), extracted by the platform adapter. `id_source = canonical`.
- **Level 2 — Canonical URL normalization (pre-analysis).** `youtu.be/X`, `youtube.com/watch?v=X`, `m.youtube.com/watch?v=X` normalize to one canonical form *before* extraction — so the duplicate-download lock and the analysis-reuse cache (V2-D-033) hit even when two users paste different spellings of the same media. Normalization tables live in the platform adapters.
- **Level 3 — Metadata fingerprint (fallback only).** Only when a platform exposes no stable ID: a deterministic hash over **stable** fields (title + author + duration + upload date), stored as a prefixed synthetic value (`fp:<hash>`) in the existing `media_metadata.video_id` column — no schema change (V2-D-028). Mutable statistics (views, likes, comments, shares) are **never** fingerprint inputs. `id_source = fingerprint`.
- **Level 4 — Content fingerprinting (reserved, NOT V2).** Audio fingerprints / perceptual video hashes. The `id_source` enum and the prefixed-key convention already leave room (`ch:<hash>`); no V2 work, no future redesign.

Architecture rule: **always prefer stable identifiers over metadata; metadata raises confidence only when no stable identifier exists.**

### 5.8 Feature Flags (V2-D-031)

Every major V2 feature ships behind an individually toggleable flag for staged rollout and deploy-free rollback. Mechanism: **new keys in the existing `settings` table**, read through the existing cached settings service — no new infrastructure, no new dependency, changes take effect within the settings-cache TTL.

| Flag | Guards |
|---|---|
| `feature_subscriptions_enabled` | Entitlement cutover (off ⇒ legacy `is_premium` path, valid until Step 4 of Section 15) |
| `feature_multilink_enabled` | Multi-link admission (off ⇒ first URL processed, rest politely declined) |
| `feature_premium_quality_gating_enabled` | 2K/4K + lossless-audio restrictions |
| `feature_ad_analytics_enabled` | `ad_events` emission (counters always stay on) |
| `feature_expiry_notifications_enabled` | Expiry notifier job |
| `analyzer_raw_metadata_enabled` | Raw metadata retention (5.3) |

Flag rules: flags gate **entry points**, not scattered branches (one check at the feature's boundary); every flag's off-state is a defined, tested behavior (listed above), not dead code; flags are for rollout safety, not permanent configuration — each is removed in the release after its feature is declared stable, to prevent flag-debt accumulation.

## 6. Database Changes

All changes are **additive** until the final cleanup migration (V2-D-024). Every DDL below enters `MASTER_PLAN.md` Section 19's migration ledger when its sprint starts; this section is the design of record.

### 6.1 New: `plans`

```sql
CREATE TABLE plans (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,          -- 'free', 'premium', future: 'plus', 'pro', 'enterprise'
    name          TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT true,
    sort_order    INT NOT NULL DEFAULT 0,
    entitlements  JSONB NOT NULL,                -- validated against EntitlementRegistry at startup
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Seeded with `free` and `premium`; values come from seed data, not this document (V2-D-020).

### 6.2 New: `subscriptions`

```sql
CREATE TABLE subscriptions (
    id                   UUID PRIMARY KEY,       -- UUIDv7, app-generated (D-013 precedent)
    user_id              BIGINT NOT NULL REFERENCES users(id),
    plan_id              BIGINT NOT NULL REFERENCES plans(id),
    status               subscription_status NOT NULL,   -- ENUM('active','expired','canceled','pending')
    source               subscription_source NOT NULL,   -- ENUM('manual_grant','stars','stripe','paymob','promo')
    starts_at            TIMESTAMPTZ NOT NULL,
    expires_at           TIMESTAMPTZ NOT NULL,
    notified_milestones  SMALLINT NOT NULL DEFAULT 0,    -- bitmask: 1=T-7d, 2=T-3d, 4=T-24h, 8=T+0
    granted_by           BIGINT REFERENCES users(id),    -- admin actor for manual_grant; NULL for future providers
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX ux_subscriptions_one_active ON subscriptions (user_id) WHERE status = 'active';
CREATE INDEX ix_subscriptions_expiring ON subscriptions (expires_at) WHERE status = 'active';
```

`pending` and the reserved `source` values exist for V4/V5 (V2-D-006); V2 writes only `active|expired|canceled` + `manual_grant`. Not partitioned — row count is proportional to paying users, not downloads.

### 6.3 New: `ad_events`

```sql
CREATE TABLE ad_events (
    id          UUID NOT NULL,                    -- UUIDv7
    ad_id       BIGINT NOT NULL,                  -- FK to advertisements
    user_id     BIGINT NOT NULL,
    event_type  ad_event_type NOT NULL,           -- ENUM('impression','delivery','click')  ('click' reserved)
    locale      TEXT NOT NULL,
    plan_code   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);                -- monthly, 12 pre-created (D-015/D-016 pattern)
CREATE INDEX ix_ad_events_ad_day ON ad_events (ad_id, created_at);
```

### 6.4 New: `ad_stats_daily` (rollup)

```sql
CREATE TABLE ad_stats_daily (
    ad_id        BIGINT NOT NULL,
    day          DATE NOT NULL,
    locale       TEXT NOT NULL,
    plan_code    TEXT NOT NULL,
    impressions  BIGINT NOT NULL DEFAULT 0,
    deliveries   BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (ad_id, day, locale, plan_code)
);
```

Maintained by the nightly rollup job (Section 9); admin screens read this, not raw partitions.

### 6.5 Altered: `cached_files` (additive — V2-D-029)

```sql
ALTER TABLE cached_files ADD COLUMN last_verified_at TIMESTAMPTZ;   -- NULL = never re-verified
```

Set whenever a cached `telegram_file_id` is successfully resent (delivery *is* verification — no extra API call) and cleared/handled by the existing `CachedFileExpiredError` self-healing eviction path. Gives future cache policies (LRU, TTL, warming) a staleness signal beyond `last_used_at`. `settings` gains the feature-flag keys (5.8) — rows, not schema.

### 6.6 Removed at cleanup (final V2 migration only, after soak — V2-D-024)

- `users.is_premium`, `users.premium_expires_at`, `ix_users_is_premium`.
- `free_*`/`premium_*` settings rows (V2-D-025) — after cutover verifies nothing reads them.

## 7. Cache Changes

| Cache | Change |
|---|---|
| User snapshot (D-014, Redis, 30 s) | Snapshot gains `plan_code` + resolved entitlements, computed at fill time. Invalidated by `SubscriptionService` writes (existing invalidation path). This keeps entitlement resolution off the per-update path entirely. |
| Plans (new, in-process) | All plan rows loaded + validated at startup; refreshed on a version key (`plans:version` in Redis, bumped by plan writes). Plans change rarely; admin plan edits take effect within the refresh interval. |
| Per-user active-job counter (new, Redis) | `user:active_jobs:{user_id}` incremented on dequeue, decremented on ack/failure. Used by the concurrency cap (V2-D-013). Crash-safety: recomputed from `queue:active` membership on worker recovery. |
| Quota reservation | No new cache: reservations ride the existing `users.daily_download_count` lazy-reset mechanism (D-012) — reserve = counted increment, refund = decrement (Section 10.2). |
| MediaAnalysis reuse (new, Redis, short TTL) | Analysis result cached keyed by `identity` (platform + canonical_media_id), so concurrent/near-in-time requests for the same media — including different URL spellings, via Level-2 normalization — reuse one extraction (V2-D-033). Short TTL because formats/availability drift; the *snapshot* persists in `media_metadata` regardless. |
| Global file-id cache | Unchanged (V1, Section 5.7). V2 adds only the `last_verified_at` write-through on cache-hit delivery. |

## 8. Queue Changes

The single `queue:jobs` ZSET and the Lua atomic-pop dequeue are **unchanged** (D-021 stands). What changes is score computation at enqueue, and a worker-side gate after dequeue:

**Score (V2-D-012):**
```
score = band_offset(priority_band) + enqueue_epoch_seconds + user_pending_count × spread_seconds
```
- `band_offset`: large constants with headroom between bands (normal, high, + room for future plans) so no band can ever bleed into another.
- `user_pending_count × spread_seconds`: each already-queued job by the same user makes the next one score as if it arrived later — batches self-interleave with other users' singles. `spread_seconds` is a configurable knob.
- Ties still break lexicographically on UUIDv7 members ⇒ FIFO within equal scores (preserved V1 property).

**Concurrency cap (V2-D-013):** after dequeue, the worker checks `user:active_jobs:{user_id}` against `max_concurrent_jobs`; at cap ⇒ re-enqueue with a small score delay and pop the next job. The Lua script stays a dumb atomic pop.

**Premium expiry mid-queue (V2-D-009):** scores are stamped at enqueue; nothing re-scores on expiry. In-flight/queued jobs keep their band; new jobs resolve fresh entitlements.

## 9. Background Jobs

| Job | Schedule | Behavior |
|---|---|---|
| Subscription expiry notifier | Periodic (interval configurable) | Scans `ix_subscriptions_expiring` for active subscriptions crossing T-7d/T-3d/T-24h/T+0 windows; sends localized notifications (recipient's locale, per the i18n fan-out rule); sets the milestone bit atomically with the send decision (V2-D-008). At T+0 also flips `status='expired'` (hygiene only — resolution is already lazy, V2-D-007). Idempotent and restart-safe by construction. |
| Ad stats rollup | Nightly | Aggregates yesterday's `ad_events` into `ad_stats_daily`. Idempotent (upsert by PK). |
| Batch settlement sweeper | Periodic, low frequency | Safety net: refunds reservations for jobs that terminally failed without settling (crash between failure and refund). Uses jobs table terminal states as truth. |

All three follow the existing background-task pattern in `workers/` — no new scheduler infrastructure.

## 10. User Flows

### 10.1 Multi-link download

1. User pastes up to `batch_max_links` URLs in one message (more ⇒ excess rejected per-link with a message).
2. Reservation (10.2): partial admission if remaining quota < admitted links (V2-D-011); Free users see an upsell line on trimmed links.
3. Stage-1 classification: playlist URLs rejected with the "planned for a future version" message + refund (V2-D-016); hybrids stripped to single video.
4. Bounded-concurrency analysis with a progress message ("Analyzing 4/10…"); per-link analysis failures are reported and refunded before any choice is asked.
5. Summary → one Format choice → one Quality choice. Compatibility: format applies to compatible links; incompatible links auto-default + per-link note (V2-D-015). Quality: highest ≤ selection, plan-capped, never upgraded (V2-D-014).
6. N independent jobs enqueue (fairness-scored); per-link progress via the existing notification path.
7. Completion summary: ✅ per success, ❌ per failure with localized reason; failed links state that quota was refunded.

### 10.2 Reservation → Settlement (V2-D-010)

- **Reserve:** single atomic `UPDATE users SET daily_download_count = daily_download_count + :admitted WHERE …` guarded by the limit check (with D-012 lazy reset applied first). Reserved = counted.
- **Settle success:** nothing to do — the slot is already counted.
- **Settle failure:** decrement by 1 per failed job (floor at the reset boundary). The sweeper (Section 9) backstops crashes.
- Cooldown and rate limits apply to *attempts*, bounding the failure-spam vector even though failures cost no quota.

### 10.3 ⭐ Premium screen

Entry: ⭐ button on `/start` (primary), `/premium` command (secondary) — one screen, both entry points (V2-D-023). Shows plan name, expiry date, remaining days, benefits (localized catalog keys), and **Renew** → localized "contact the administrator" message in V2. This exact screen is the V4 purchase surface later; only the Renew action changes.

### 10.4 Expiry lifecycle

T-7d / T-3d / T-24h localized warnings with the ⭐ screen linked → at expiry, resolver lazily degrades to Free (V2-D-007) → T+0 notification: premium ended, what changed, Renew pointer. No grace period. In-flight jobs finish at premium priority (V2-D-009).

## 11. Admin Flows

All inside the existing inline admin panel (V1 Sprint 9.6 patterns: signed callbacks, direct user-id input).

- **Users → Premium management:** Grant (presets 7/30/90 days + custom date), Extend (from current expiry if active, else from now — V2-D-022), Remove (immediate downgrade + cache invalidation), Set Expiration (absolute override). Every action: audit-logged with actor (`granted_by`), confirmation step, result screen showing the new state.
- **Statistics → Advertisements:** totals + daily impressions/deliveries, per-language and per-plan breakdowns (from `ad_stats_daily`), per-ad drilldown. CTR column appears grayed "future" — the schema supports it; the tracking doesn't exist yet by decision.
- **Statistics → Subscriptions:** active premium count, grants/extensions/removals over time, upcoming expirations (7-day window) — the Owner's manual-renewal worklist.

## 12. Monitoring

New metrics (existing structured-logging + metrics conventions):

- `subscriptions_active{plan}`, `subscription_grants_total{action}` (grant/extend/remove/set_expiration), `subscription_expiry_notifications_total{milestone}`.
- `entitlement_parity_mismatch_total` — **shadow-mode alarm; must be 0 before cutover (gate for Sprint V2.2).**
- `batch_links_per_message` histogram, `batch_partial_admissions_total`, `quota_refunds_total{reason}`.
- `queue_wait_seconds{band}` histogram — the fairness SLO; premium vs free wait separation is the direct measure of the priority feature.
- `job_requeues_concurrency_cap_total` — requeue-churn watch for V2-D-013.
- `analyzer_capability_total{capability}`, `playlist_rejections_total` — direct demand signal for the future playlist feature.
- `media_identity_resolutions_total{id_source}` — fingerprint-fallback share; a rising `fingerprint` ratio flags platforms needing a canonical-ID extractor.
- `analysis_reuse_hits_total` — extractions saved by V2-D-033.
- Feature-flag state changes are audit-logged (who, which flag, old→new).
- `ad_events_written_total{event_type}`, rollup-job lag.
- `i18n_catalog_coverage{locale}` gauge (Sprint V2.0).

Alerts: parity mismatches > 0 (shadow phase), expiry-notifier failures, rollup lag > 24 h, sustained queue-wait SLO breach per band.

## 13. Security

- **Server-side revalidation:** format/quality callback data is revalidated against the user's *current* entitlements at job creation — a crafted callback (or a stale keyboard from a since-expired premium user) can never mint an over-entitlement download. Never trust the keyboard.
- **Admin actions:** owner/moderator-gated (existing RBAC), signed callbacks (existing), audit-logged with actor, target, action, old/new expiry.
- **Quota integrity:** reservation is a single atomic guarded UPDATE — no TOCTOU between check and increment; the settlement sweeper cannot double-refund (settlement state is recorded on the job).
- **Abuse bounds:** failures don't consume quota but do consume attempt-scoped cooldown/rate limits; batch caps bound per-message fan-out; concurrency caps bound per-user worker occupation.
- **ad_events privacy:** contains `user_id` for reach/dedup analytics only; retention follows the error-log retention pattern (configurable, D-017 precedent); never exposed per-user in admin UI — aggregates only.
- **No payment data of any kind in V2** (V2-D-006).

## 14. Performance Considerations

- **Hot path unchanged:** entitlement resolution rides the existing user-snapshot cache; zero additional per-update queries. This was the design constraint that shaped V2-D-002/V2-D-004.
- **Batch analysis:** bounded concurrency (configurable, small) caps yt-dlp process fan-out per message; progress feedback masks latency. Worst case (max links × analysis time) stays interactive.
- **Queue ops:** enqueue gains one Redis read (pending count); dequeue unchanged; requeue churn from the concurrency cap is bounded and monitored.
- **ad_events writes:** one INSERT per impression/delivery on the download-completion path (not the message hot path), into a partitioned table — negligible at V1 target scale; rollups keep reads cheap.
- **Load levels:** L1–L4 re-run in Sprint V2.5 with mixed free/premium + batch traffic; fairness assertions (no starvation, band wait-time separation) added to the simulation framework.

## 15. Migration Strategy

Four owner-approved steps (V2-D-024), mapped to sprints. Every step is independently deployable and reversible; there is always a window where the previous code still runs correctly.

| Step | Sprint | Change | Rollback |
|---|---|---|---|
| 1. Introduce | V2.1 | Additive migration: `plans`, `subscriptions`, enums, seeds. Backfill current premium users (`is_premium=true`) as active `manual_grant` subscriptions with their existing `premium_expires_at`. `is_premium` **stays authoritative**; resolver runs in shadow, logging parity mismatches. | Drop new tables. Zero behavior change to roll back. |
| 2. Validate | V2.1→V2.2 gate | Shadow parity metric must read 0 over the soak window. | n/a (observation phase). |
| 3. Cutover | V2.2 | Business logic switches to `EntitlementService`; admin premium actions write subscriptions (dual-writing `is_premium` for compatibility); settings `free_*`/`premium_*` reads replaced. | Revert deploy — columns still maintained, old code still correct. |
| 4. Remove | V2.6 (after V2.2–V2.5 soak) | Drop `is_premium`, `premium_expires_at`, index; delete deprecated settings rows. **Point of no return, taken last.** | Restore from migration down-script + backfill from subscriptions (data is fully recoverable from `subscriptions`). |

V1 architecture changes required and justified: (1) `users` loses two columns — *end state only*, after entitlements fully supersede them (V2-D-024/025 rationale); (2) enqueue scoring extends D-021's priority semantics without changing queue structure; (3) everything else is additive.

## 16. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Shadow-parity mismatches reveal edge cases (timezone edges, expired-but-flagged users) | Cutover delay | That's the mechanism working — fix in V2.1, cutover only at 0 mismatches. Backfill script has dry-run + report mode. |
| Entitlement checks re-scatter over time | Long-term architecture decay | V2-D-005 forbidden-pattern rule enforced in code review; single resolver; registry validation. |
| Batch analysis latency frustrates users | UX | Bounded concurrency + progress message + per-link timeout (existing D-025 layering). |
| Fairness spread misconfigured (too small = monopoly, too large = premium batches feel slow) | UX/SLO | `spread_seconds` configurable; `queue_wait_seconds{band}` histogram watches it; L1–L4 fairness assertions. |
| Concurrency-cap requeue churn under pathological load | Worker efficiency | `job_requeues_concurrency_cap_total` monitored; delay knob; cap enforcement can be disabled by config without deploy. |
| Refund logic double-refunds or leaks reservations on crash | Quota integrity | Settlement state on the job row (idempotent, Principle 4.2.6) + sweeper reconciles from terminal job states. |
| yt-dlp field drift breaks metadata normalization | Analyzer correctness | Core+extras design (V2-D-019) confines drift to `extras`; core mapping is per-field defensive; contract tests per platform fixture. |
| Notification job spams on restart | User trust | Milestone bitmask set atomically with send decision (V2-D-008); unit + integration tested for restart replay. |
| `ad_events` growth | Storage | Monthly partitions + configurable retention; rollups preserve analytics after raw drop. |

## 17. Future Compatibility

- **V3 (web dashboard):** reads `plans`, `subscriptions`, `ad_stats_daily`, `MediaAnalysis`-enriched history over the existing versioned API (D-019). No V2 schema was designed with bot-only assumptions.
- **Metadata-consuming features (Search, Favorites, Smart Recommendations, Recently Downloaded, Media Preview Cards, history enrichment — V3+):** all read the persisted normalized snapshots (`media_metadata` + `analysis_version`); the preview contract (5.3) guarantees render-ability without new platform requests. Zero re-extraction by design.
- **V4 (payments):** a payment provider = new `infrastructure/` adapter + webhook routes + new `source` enum values, calling the existing `SubscriptionService`. `status='pending'` already exists for async payment flows. The ⭐ screen's Renew button swaps its action. **Plans, Subscriptions, Entitlements remain unchanged — this is the V2 contract (V2-D-006).**
- **V5 (referrals):** referral rewards create subscriptions with `source='promo'` through the same service; per-plan ad analytics already segment the funnel.
- **V6 (multi-engine):** capability classification is provider-agnostic; `MediaAnalysis` is the normalized boundary any engine must produce — V6 slots under it via the existing `DownloaderRegistry` (D-026).
- **Playlists (future workshop):** entitlement key reserved; analyzer already classifies PLAYLIST and holds playlist info in `extras`; the V2 rejection branch is the pipeline's future entry point. Nothing to undo.

## 18. Sprint Plan

Order is dependency-driven. Every sprint ends stable and deployable (Owner sprint rule). **Every feature-bearing sprint ships behind its Section 5.8 flag, deployed off, enabled per the staged-rollout plan** — this is an implicit deliverable + acceptance criterion for V2.2–V2.7 and is not repeated in each sprint below.

---

### Sprint V2.0 — i18n Hardening

- **Goal:** land the localization review's outcomes before catalog count grows; stand up the feature-flag convention the rest of V2 ships behind.
- **Features:** startup placeholder-set validation (non-default placeholder sets ⊆ default's, boot failure on violation); per-locale coverage metric with `admin.*` carve-out; plural-strategy decision-log entry (CLDR suffix keys via `babel`, implementation deferred until first plural-heavy string); feature-flag mechanism (5.8) — settings keys, cached read helper, audit-logged changes.
- **Dependencies:** none. Fully independent — runs while V2.1 design review proceeds.
- **Deliverables:** extended `core/i18n.py` validation + tests; `i18n_catalog_coverage{locale}` gauge; decision-log entry; flag read/audit helper + seeded flag rows (all off).
- **Risks:** placeholder validation may fail boot on an existing latent catalog defect — that's the feature; fix the catalog.
- **Acceptance criteria:** boot fails on a fixture catalog with a placeholder typo; coverage metric visible; en/ar catalogs pass; flag toggle takes effect within settings-cache TTL without deploy; full test suite green.
- **Migration impact:** settings rows only (no schema).

---

### Sprint V2.1 — Subscription Foundation (shadow mode)

- **Goal:** final subscription schema live in production with **zero behavior change**; parity evidence collected.
- **Features:** `plans` + `subscriptions` migrations, enums, seeds (values from seed data, V2-D-020); `EntitlementRegistry` + startup JSONB validation; `EntitlementService` (shadow) + `SubscriptionService` (write API, unused by UI yet); premium-user backfill (dry-run mode first); snapshot cache extension; `entitlement_parity_mismatch_total`.
- **Dependencies:** none (V2.0 independent).
- **Deliverables:** migrations, domain entities, both services, backfill script + report, parity dashboard.
- **Risks:** backfill edge cases (premium flag set, expiry null/past); mitigated by dry-run report + parity soak.
- **Acceptance criteria:** deployed with zero user-visible change; backfill report matches `is_premium` counts exactly; parity mismatches = 0 across the defined soak window; boot fails on an invalid entitlements fixture.
- **Migration impact:** additive only (Step 1 of Section 15). Rollback = drop tables.

---

### Sprint V2.2 — Entitlement Cutover + Subscription Management

- **Goal:** entitlements become the sole authority; Owner manages premium end-to-end; users see the ⭐ screen and expiry lifecycle.
- **Features:** business-logic cutover (rate limits, file size, cooldown, ad gating via `ad_free`, priority band at enqueue); admin Grant/Extend/Remove/Set-Expiration (V2-D-022 semantics, audit-logged); ⭐ Premium screen + `/premium` (V2-D-023), Renew → contact-admin message; expiry notifier job (V2-D-008); dual-write of legacy columns for rollback safety.
- **Dependencies:** V2.1 parity gate passed (hard gate).
- **Deliverables:** cutover diff, admin panel screens, premium screen, notifier job, localized catalog keys for all new UI, integration + E2E coverage.
- **Risks:** behavioral drift at cutover (mitigated: parity already proved equivalence); notification replay (mitigated: bitmask atomicity tests).
- **Acceptance criteria:** zero `is_premium` reads outside dual-write; all four admin actions verified E2E incl. cache invalidation timing; expiry E2E (T-24h + T+0 in compressed time) passes; Renew shows localized contact-admin message; security suite passes with expired-premium callback-replay cases.
- **Migration impact:** no schema change (Step 3 of Section 15). Rollback = revert deploy; dual-written columns keep old code correct.

---

### Sprint V2.3 — Analyzer: Capability Detection + Normalized Metadata

- **Goal:** analyzer classifies every URL, resolves stable media identity, and returns `MediaAnalysis` — before multi-link multiplies analyzer traffic.
- **Features:** two-stage classification (V2-D-017); `Capability` enum; playlist rejection + hybrid stripping (V2-D-016) with quota refund; live/story/short policy (V2-D-018); `MediaAnalysis` with identity block (V2-D-027) — canonical-ID extraction per adapter, Level-2 URL normalization, Level-3 fingerprint fallback (V2-D-028); core+extras metadata incl. snapshot statistics + preview contract (V2-D-019); `analysis_version` stamping (V2-D-034); capability default-to-UNKNOWN routing (V2-D-035); raw-metadata reservation, config-gated off (V2-D-030); analysis-reuse Redis cache (V2-D-033); `cached_files.last_verified_at` migration + write-through on cache-hit delivery (V2-D-029); provider-agnostic adapter contract (V2-D-032); single-download flow consumes `MediaAnalysis`.
- **Dependencies:** none on V2.1/V2.2 (parallelizable after V2.0). V2.4 hard-depends on this sprint.
- **Deliverables:** classifier + pattern/normalization tables per adapter, identity resolver + fingerprint hasher, normalized mapper with per-platform fixture contract tests, analysis-reuse cache, `last_verified_at` migration, localized rejection messages, capability + identity metrics.
- **Risks:** URL-pattern false positives (Stage 2 authoritative reclassification is the corrective); yt-dlp drift (confined to `extras`); fingerprint collisions on ID-less platforms (stable-field hash + platform scoping keeps risk marginal; `id_source` metric watches fallback share).
- **Acceptance criteria:** classification fixture matrix (per platform × capability, incl. hybrids and short links) passes; the three YouTube URL spellings of one video resolve to one identity (Level-2 fixture); pure playlist URL ⇒ localized "planned for a future version" + refund, zero extraction cost; hybrid ⇒ single video; ongoing live ⇒ rejection; ended live ⇒ video; missing metadata fields never raise downstream; second analysis of the same identity within TTL performs zero extractions; cache-hit delivery sets `last_verified_at`; raw retention off by default, on-flag stores size-capped `_raw`.
- **Migration impact:** additive only (`cached_files.last_verified_at`).

---

### Sprint V2.4 — Multiple Link Requests

- **Goal:** the full multi-link UX on the reservation quota model.
- **Features:** URL extraction; `batch_max_links` cap; reservation with partial admission (V2-D-010/011); bounded-concurrency analysis + progress; summary → single format/quality choice (V2-D-014/015 rules); N independent jobs; completion summary with per-link failure reasons; automatic refunds; settlement sweeper.
- **Dependencies:** V2.3 (capability + analysis pipeline); V2.2 (entitlement caps) — technically only the entitlement read, so a feature-flagged early start behind V2.2's gate is permitted.
- **Deliverables:** admission pipeline, reservation/settlement in `RateLimitService`, batch UX handlers + keyboards (localized), sweeper job, simulation scenarios (mixed batch sizes, failure injection).
- **Risks:** reservation edge cases across the D-012 lazy-reset boundary (dedicated unit matrix); analysis latency (bounded concurrency + progress).
- **Acceptance criteria:** batch of max links E2E: reserve → choose once → N jobs → summary; injected failures refund exactly and the summary says so; partial admission at quota edge verified; single-URL messages behave exactly as V1 (regression suite); mixed video+audio batch follows V2-D-015; security tests cover reservation TOCTOU and overshoot attempts.
- **Migration impact:** none.

---

### Sprint V2.5 — Queue Fairness + Concurrency Caps

- **Goal:** batches and premium priority coexist with cross-user fairness, proven under load.
- **Features:** virtual-time enqueue scoring with band offsets (V2-D-012); per-user active counter + worker-side cap with requeue-delay (V2-D-013); `queue_wait_seconds{band}`; fairness assertions in the simulation framework; L1–L4 re-run with mixed free/premium/batch traffic.
- **Dependencies:** V2.4 (batches are what fairness protects against); V2.2 (`priority_band`, `max_concurrent_jobs`).
- **Deliverables:** scoring change, cap enforcement, counter recovery-on-restart path, updated `PERFORMANCE_REPORT.md` (append-only, D-036).
- **Risks:** spread/delay tuning (config knobs + histogram); counter drift after crashes (recompute from `queue:active` on recovery).
- **Acceptance criteria:** simulation: one user's max batch + M singles from others ⇒ no starvation, interleaving within defined bounds; premium band always dequeues before free at equal arrival; cap verified (max N in-flight per user); L1–L4 within V1 baselines; kill-and-restart worker test recovers counters (Rule 4.3.3).
- **Migration impact:** none (Redis-only scoring semantics; drains naturally through deploy).

---

### Sprint V2.6 — Premium Media Gating + Legacy Cleanup

- **Goal:** last premium differentiators live; legacy premium columns retired.
- **Features:** `max_video_height` gating (2K/4K) and `audio_formats` gating (FLAC) in keyboards + server-side revalidation (Section 13); upsell hint on gated options for Free users (localized); **cleanup migration** dropping `is_premium`, `premium_expires_at`, index, and deprecated settings rows (Step 4 of Section 15).
- **Dependencies:** V2.2 cutover **soaked** through V2.3–V2.5 (Owner gate on the drop migration); V2.3 (format metadata drives the keyboards).
- **Deliverables:** gating logic + tests, upsell UX, cleanup migration + down-script, dual-write removal.
- **Risks:** premature drop (Owner sign-off gate); stale-keyboard replay after expiry (revalidation tests, already covered since V2.2).
- **Acceptance criteria:** Free callback demanding 4K/FLAC rejected server-side even via crafted callback; premium E2E gets 4K/FLAC where available; grep-level zero references to dropped columns; full regression green post-drop.
- **Migration impact:** **destructive step, taken last**, Owner-approved, with documented down-script (Section 15 Step 4).

---

### Sprint V2.7 — Advertisement Analytics

- **Goal:** monetization signal collection + admin visibility.
- **Features:** `ad_events` + `ad_stats_daily` migrations; `AdService` event emission (impression/delivery with locale + plan); nightly rollup job; admin Statistics screens (totals, daily, per-language, per-plan, per-ad drilldown; CTR marked "future"); retention config.
- **Dependencies:** V2.2 (`plan_code` dimension). Otherwise independent — may run in parallel with V2.5/V2.6.
- **Deliverables:** migrations, event emission + rollup job, admin screens (localized), retention enforcement, dashboards.
- **Risks:** event-write failures must never break ad delivery (fire-and-forget with error logging, never in the delivery critical path); partition hygiene (pre-created 12 months, D-015 pattern).
- **Acceptance criteria:** impressions/deliveries produce events with correct dimensions; rollup idempotent (double-run = same totals); admin screens match rollup queries; ad delivery latency unchanged (perf check); `click` enum present and unused.
- **Migration impact:** additive only.

---

## 19. Deferred to Future Workshops

**Playlist Downloads** — independent product capability (Owner directive). Its workshop must answer, minimum: playlist discovery; analysis; maximum size; Free vs Premium limits; full vs range selection; resume of interrupted playlists; retry of failed items; cached vs non-cached items; parallel vs sequential downloading; queue fairness; progress reporting; Telegram delivery strategy; caching; storage optimization; quota accounting; user cancellation; duplicate handling; performance. **No assumptions before that workshop** (Owner directive, 2026-07-02). V2 ships only: the `playlists_enabled` entitlement key, PLAYLIST capability classification, the localized rejection message, and `playlist_rejections_total` as the demand signal.

**Ad click tracking** — requires the public redirect endpoint (rate limiting, bot-click noise, open-redirect hardening). `ad_events.event_type` reserves `click`; the counters exist since V1 (D-003). Revisit alongside V3's web surface or V4's monetization push.

**Plural implementation** — mechanism decided in V2.0's decision entry; implemented when the first plural-heavy string or language lands.

---

## 20. Future Technical Debt Avoided

Long-term architectural documentation (Owner directive): for every major V2 decision — the chosen solution, the future refactor it prevents, and why it was taken now instead of later.

| Decision | Chosen Solution | Refactor Prevented | Why Now, Not Later |
|---|---|---|---|
| Subscription direction (V2-D-001) | `subscriptions.user_id` FK; one active row enforced by partial unique index | Repointing/rewriting user rows and reconstructing lost subscription history when V4 payments need pending/refunded/renewal records | Retrofitting history onto a `users.subscription_id` design means inventing records that were never written — data that cannot be recovered later |
| Entitlements as the only read path (V2-D-004/005) | JSONB on `plans`, code-side registry, one resolver, forbidden-pattern rule | The V2 problem itself, recurring: hunting scattered `is_premium`/plan-code branches across the codebase for every new plan (Plus/Pro/Enterprise) | The scatter grows with every feature that ships; V2 adds the most premium-touching features of any version, so the cutover is cheapest exactly now |
| Payment-ready sources (V2-D-006) | `source` + `status` enums ship with reserved values; providers call the same `SubscriptionService` | V4 redesign of subscription lifecycle to accommodate async payment states | Enum values and a service boundary cost nothing now; a V4 schema redesign under revenue pressure is the most expensive kind |
| Reservation → Settlement (V2-D-010) | Atomic reserve at admission, refund on failure | Re-architecting quota under abuse pressure in production (overshoot + free-labor attack are economic holes, not edge cases) | Admission control must precede batches; bolting it on after multi-link ships means changing live quota semantics under users' feet |
| Fairness inside one queue (V2-D-012) | Virtual-time scoring + band offsets in the existing ZSET | Forked per-user queues with round-robin Lua, new dead-letter paths, and a D-021 reversal once batches starve singles | Scoring is an enqueue-time formula change today; a scheduler rewrite after batch complaints is a queue migration in production |
| Capability classification (V2-D-017) | Two-stage classify; business logic on `Capability`, never raw URLs | Analyzer redesign for each future content type (Playlists, Albums, Stories already classified — features just route) | The multi-link pipeline is being built against the analyzer now; every feature built on raw URLs would need rewriting per new capability |
| Core+extras metadata (V2-D-019) | Small typed core + platform passthrough, promote-on-consumption | Perpetual chasing of yt-dlp per-platform field drift across a fully-normalized 30-field surface | The boundary must be drawn before consumers exist; narrowing an over-promised metadata contract later breaks every consumer |
| Identity levels (V2-D-027/028) | Canonical ID → URL normalization → stable-field fingerprint; prefixed synthetic keys reserve Level 4 | Cache-key migration (rekeying `media_metadata`/`cached_files` at tens of millions of rows) when mutable-metadata keys collide or drift | Cache keys are write-once economics: every row written under a weak key is a row to migrate later |
| Global-cache rule made explicit (5.7) | Named binding rule + `last_verified_at`; policies declared data/jobs, not redesigns | A future contributor "optimizing" per-user caching, or LRU/TTL/warming arriving as schema surgery instead of a background job | The rule already holds in V1 code; writing it down is free and stops it being violated by accident while V2 multiplies cache traffic |
| Analyze-once (V2-D-033) | `MediaAnalysis` travels the request; short-TTL identity-keyed reuse cache | Per-service re-extraction creeping in (each one a platform round-trip), then a painful "deduplicate the extractions" project | Batches multiply extraction cost 10×; the reuse discipline must exist before the multiplier ships |
| Feature flags (V2-D-031) | Settings-table flags, entry-point gating, defined off-states, removal rule | Emergency-revert deploys as the only rollback path; alternatively, permanent flag-debt from an unbounded flag system | V2 ships the largest behavioral change since launch (entitlement cutover); staged rollout is a launch-safety requirement, and the removal rule caps the cost |
| Events over counters (V2-D-021) | Partitioned `ad_events` with reserved `click`; counters demoted to rollups | Rebuilding ad analytics when V4 pricing asks time-series questions counters can never answer retroactively | Events not written are unrecoverable — the data for V4 decisions must start accumulating in V2 |
| Gradual `is_premium` retirement (V2-D-024) | Shadow → parity gate → cutover → soak → drop, across three sprints | A one-shot migration with no rollback window — the classic irreversible-cutover incident | The gradual path only exists if designed in from the first migration; it cannot be added after a big-bang switch |
| i18n hardening first (V2-D-026) | Placeholder validation, coverage metric, plural decision — before language #3 | Catalog restructuring across N languages once plural-heavy strings exist; translator-introduced runtime template errors at scale | Validation added at 2 catalogs is a code change; at 20 catalogs it is a data-cleanup project |
| Analyzer version stamp (V2-D-034) | `analysis_version` persisted with every snapshot; snapshots-only scope | A future analyzer overhaul unable to tell which of millions of persisted snapshots are stale — forcing either mass re-extraction or silent wrong data | A version can only be stamped at write time; every snapshot persisted before the stamp exists is permanently unversionable |
| Capability forward-compatibility (V2-D-035) | Unhandled capabilities behave as UNKNOWN; enum grows freely | Lock-step releases where every new media type must touch every consumer simultaneously | The default-to-UNKNOWN discipline must exist before the second consumer of the enum is written |

# Subscriptions & Entitlements — design (Sprint V2.1)

> **Status:** APPROVED + IMPLEMENTED (2026-07-22). Built as designed with three
> conformed-to-codebase deviations, each noted inline below:
> (1) `status`/`source` are `VARCHAR` columns, not PG `ENUM` types — the codebase has no PG
> enums; the `StrEnum`s enforce values app-side. (2) the file-size entitlement key is
> `max_file_size_bytes`, not `max_file_size_mb` — the live settings it seeds from are
> byte-valued, so bytes keeps the seed lossless. (3) shadow parity is compared at **plan
> level** (resolver plan-code vs `_effective_plan()`) — if the plan matches, every derived
> entitlement matches by construction; and the `UserSnapshot` field extension is deferred to
> V2.2 (when a consumer first reads it), keeping V2.1's cache wire-format unchanged.
> **Scope:** Sprint V2.1 only — the subscription *foundation* in **shadow mode**. Zero
> user-visible behavior change. `is_premium` stays authoritative; the new resolver runs
> in parallel and only *observes*.
> **Plan of record:** `VERSION_2_MASTER_PLAN.md` §5.1–5.2, §6.1–6.2, §15 (Step 1), and
> decisions V2-D-001…005, V2-D-020, V2-D-024. This doc is the *design of record* that
> turns those into an implementable spec; it does not change any V2 decision.

---

## The problem this solves

V1 encodes "premium" as two columns on `users` (`is_premium`, `premium_expires_at`) and
two settings pairs (`free_*`/`premium_*`). Every premium decision re-derives the plan
(`_effective_plan()` in `services/rate_limit_service.py`) and reads a plan-specific
settings key. Adding a second paid tier (Plus/Pro) would mean hunting those branches
across the codebase — the exact scatter V2 exists to remove.

V2.1 lays the final **Plans → Subscriptions → Entitlements** foundation *without changing
behavior yet*. It ships the tables, the resolver, and the write API, then runs the
resolver in **shadow**: it computes each user's entitlements the new way and compares
them to the live `is_premium` path, emitting a parity metric. Cutover (V2.2) only
proceeds once that metric reads **0** over a soak window.

## The shape

```
plans (free, premium)  --<  subscriptions (user_id, plan_id, status, source, expires_at)
   |                              one active row per user (partial unique index)
   | entitlements JSONB
   v
EntitlementRegistry (code-side typed key registry)  --validates-->  plans.entitlements at boot
   |
EntitlementService.resolve(snapshot) -> ResolvedEntitlements   (the ONLY read path)
SubscriptionService.grant/extend/remove/set_expiration        (the ONLY write path; unused by UI in V2.1)
```

Free is the **absence** of an active subscription row (V2-D-002) — no rows for free users,
no 300k-row backfill. The resolver returns the Free plan's entitlements when no active
row exists, evaluating expiry lazily (`expires_at < now() ⇒ Free`, V2-D-007) exactly as
`_effective_plan()` already does today.

---

## Decision 1 — schema is additive; `is_premium` untouched this sprint

New tables + enums only. `users.is_premium`/`premium_expires_at` stay and stay
authoritative. Rollback for the whole sprint = **drop the new tables** (§15 Step 1).

### `plans` (V2-D-004)
```sql
CREATE TABLE plans (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,          -- 'free','premium'; future 'plus','pro'
    name          TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT true,
    sort_order    INT NOT NULL DEFAULT 0,
    entitlements  JSONB NOT NULL,                -- validated against EntitlementRegistry at boot
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `subscriptions` (V2-D-001/003)
```sql
CREATE TYPE subscription_status AS ENUM ('active','expired','canceled','pending');
CREATE TYPE subscription_source AS ENUM ('manual_grant','stars','stripe','paymob','promo');

CREATE TABLE subscriptions (
    id                   UUID PRIMARY KEY,                 -- UUIDv7, app-generated (D-013)
    user_id              BIGINT NOT NULL REFERENCES users(id),
    plan_id              BIGINT NOT NULL REFERENCES plans(id),
    status               subscription_status NOT NULL,
    source               subscription_source NOT NULL,
    starts_at            TIMESTAMPTZ NOT NULL,
    expires_at           TIMESTAMPTZ NOT NULL,
    notified_milestones  SMALLINT NOT NULL DEFAULT 0,      -- bitmask: 1=T-7d,2=T-3d,4=T-24h,8=T+0 (V2.2)
    granted_by           BIGINT REFERENCES users(id),      -- admin actor; NULL for future providers
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX ux_subscriptions_one_active ON subscriptions (user_id) WHERE status = 'active';
CREATE INDEX ix_subscriptions_expiring ON subscriptions (expires_at) WHERE status = 'active';
```

V2.1 only ever writes `status ∈ {active,expired,canceled}` and `source='manual_grant'`.
`pending`/payment sources exist for V4 (V2-D-006). Not partitioned — row count is
proportional to paying users, not downloads.

## Decision 2 — entitlement **keys** are code; **values** are seed data (V2-D-020)

`domain/entitlements.py` defines the typed registry. `plans.entitlements` is validated
against it at startup (unknown key / missing key / wrong type ⇒ boot fails, mirroring the
locale-catalog fail-fast). Business logic's only legal read is `entitlements.<key>`;
`if is_premium` / `if plan_code == "premium"` stay forbidden (V2-D-005, code-review rule).

V2.1 ships the keys the resolver actually needs to prove parity now, plus the reserved
`playlists_enabled`. The remaining keys from plan §5.2 (`batch_max_links`,
`max_concurrent_jobs`, `max_video_height`, `audio_formats`, `priority_band`) are added by
the sprints that consume them (V2.4/V2.5/V2.6) — a key with no consumer buys nothing yet
and would be an unvalidated guess. The registry is designed so adding a key later is one
line + a seed value, never a migration.

| Key (V2.1) | Type | Consumed by (parity surface) |
|---|---|---|
| `daily_download_limit` | int | `RateLimitService.check_download` daily cap |
| `cooldown_seconds` | int | `RateLimitService.check_download` cooldown |
| `max_file_size_mb` | int | download pipeline pre-check |
| `ad_free` | bool | `AdService` gating (PLAN dimension already keys off premium) |
| `playlists_enabled` | bool | **reserved**, seeded `false` on every plan (V2-D-016) |

## Decision 3 — seed entitlements are **derived from the live settings**, so parity is exact by construction

The whole point of shadow mode is that the new path produces byte-identical decisions to
the old one. Rather than hardcode entitlement numbers (which could drift from whatever the
Owner has tuned in production), the seed migration **reads the current `free_*`/`premium_*`
settings rows and writes them into the plan JSONB**:

| Plan | `daily_download_limit` | `cooldown_seconds` | `max_file_size_mb` | `ad_free` | `playlists_enabled` |
|---|---|---|---|---|---|
| free | ← `free_daily_limit` | ← `download_cooldown_seconds` | ← free file-size setting | `false` | `false` |
| premium | ← `premium_daily_limit` | ← `premium_download_cooldown_seconds` | ← premium file-size setting | `true` | `false` |

(Staging today: free 10 / premium 100 daily, 30s / 5s cooldown.) Because the values come
from the same rows `_effective_plan()` reads, the resolver and the legacy path cannot
disagree on limits at seed time — parity mismatches can then only surface a *logic* bug
(expiry edge, plan-selection edge), which is exactly what the soak is meant to catch. The
`free_*`/`premium_*` settings remain authoritative until V2.2 cutover (V2-D-025).

> Resolved: the real keys are `free_max_file_size` (52428800) and `premium_max_file_size`
> (2147483648), both **byte-valued** and currently *unconsumed* in V1 (only the global
> `max_file_size` is enforced). The entitlement key is therefore `max_file_size_bytes`, seeded
> directly from them; per-plan file-size gating becomes authoritative in V2.6.

## Decision 4 — resolution rides the existing snapshot cache; **zero new per-update queries**

`UserSnapshot` (D-014, Redis, 30 s TTL) gains `plan_code: str` and
`entitlements: dict` (or a typed `ResolvedEntitlements`), computed **at cache-fill time**
with one indexed lookup against `ix_subscriptions_expiring` for the user's active row.
`from_row`/`to_cache_dict`/`from_cache_dict` are extended (wire-format stays in one place).
`SubscriptionService` writes invalidate the user's cache entry via the existing path, so a
grant/removal takes effect within the snapshot TTL. Plans are loaded + validated once at
startup and refreshed on a `plans:version` Redis key (rare writes).

**Shadow mode nuance:** in V2.1 the snapshot carries the resolved values, but *no consumer
reads them yet* — `RateLimitService` etc. still use `_effective_plan()`. The resolved
values exist only to be compared (Decision 5). This keeps V2.1 a pure add: even the
snapshot extension is behavior-inert until V2.2 flips `feature_subscriptions_enabled`.

## Decision 5 — parity is measured at cache-fill, not in a separate job

When the snapshot is built (cache miss, ≤ once per 30 s per active user), compute both:
the legacy effective limits (`_effective_plan()` + settings) and the resolver's
entitlements. On any divergence, increment `entitlement_parity_mismatch_total{field}` and
log `entitlement_parity_mismatch` (user id, field, legacy vs resolved). No divergence ⇒
silent. This is a handful of dict comparisons on an already-rare path — cheaper than a
scan job and always current. **Cutover gate (V2.2): this metric must be 0 across the soak.**

## Decision 6 — `SubscriptionService` write API ships now, wired to nothing

`grant / extend / remove / set_expiration` with the V2-D-022 semantics (grant starts now;
extend adds to current expiry if an active row exists else starts now; set_expiration
overrides absolutely; remove ends the active row). Enforces one-active-row via the partial
unique index (racing grants fail at the DB, not in app checks). Emits structured audit
logs with `granted_by`. **No admin UI calls it in V2.1** — it exists so V2.2 wires the
admin panel to a tested service, and so the backfill can use it.

## Decision 7 — backfill is dry-run-first and idempotent

A script (not an app path) turns every `is_premium=true` user into one `active`
`manual_grant` subscription with `starts_at=now()`, `expires_at=premium_expires_at`
(or a sentinel far-future for the historical "premium with null expiry" case — flagged in
the dry-run report for the Owner to rule on). Modes: `--dry-run` (default) prints a report
(counts, per-user planned rows, anomalies) and writes nothing; `--apply` performs it inside
one transaction. Idempotent: skips users who already have an active row. On staging this is
a no-op (0 premium users); on production it must reconcile exactly to the `is_premium` count.

---

## Domain / code layout (all inside existing layers — no new layer, no cross-layer import)

```
domain/entities/plan.py          Plan(code, name, is_active, sort_order, entitlements)
domain/entities/subscription.py  Subscription(id, user_id, plan_id, status, source, starts_at, expires_at, ...)
domain/enums/subscription.py     SubscriptionStatus, SubscriptionSource
domain/entitlements.py           EntitlementRegistry + ResolvedEntitlements + validate()
services/entitlement_service.py  resolve(snapshot|row) -> ResolvedEntitlements  (read path)
services/subscription_service.py grant/extend/remove/set_expiration            (write path)
infrastructure/database/models/plan.py, models/subscription.py + repositories
migrations/versions/2026072002_plans_subscriptions.py   (schema + enums)
migrations/versions/2026072003_seed_plans.py            (data: derive entitlements from settings)
scripts/backfill_subscriptions.py                       (dry-run/apply)
```

## Migration & rollback

- `2026072002` — additive DDL (tables, enums, indexes). Down = drop tables + enums.
- `2026072003` — data-only seed of `free`/`premium` from current settings. Down = delete the two rows.
- Both are Step 1 of §15: **zero behavior change to roll back**, drop-and-forget.
- Chains onto current staging/prod head after V2.0 (`2026072001`).

## Monitoring

- `entitlement_parity_mismatch_total{field}` — **the cutover gate; must be 0** (§12).
- `subscriptions_active{plan}` gauge (set at startup / on writes).
- Boot fails loudly on an invalid `plans.entitlements` (registry validation) — a startup
  log + non-zero exit, same class as the locale-catalog guard.

## Test plan (acceptance for V2.1)

1. **Registry validation:** boot fails on a plan row with an unknown key / missing key /
   wrong type; passes on the seeded rows.
2. **Resolver correctness:** no active row ⇒ Free entitlements; active non-expired premium
   row ⇒ premium entitlements; active row with `expires_at < now()` ⇒ Free (lazy expiry).
3. **One-active-row:** two concurrent `grant`s for one user ⇒ exactly one active row
   (second raises); `extend` adds to current expiry; `set_expiration` overrides; `remove`
   flips to `canceled` and resolver returns Free.
4. **Parity (the headline):** for a matrix of user states (free, active premium, expired
   premium, premium-with-null-expiry), the resolver's `daily_download_limit`/
   `cooldown_seconds`/`max_file_size_mb`/`ad_free` equal the legacy `_effective_plan()`
   values ⇒ `entitlement_parity_mismatch_total == 0`.
5. **Backfill:** dry-run report matches `is_premium` counts exactly and writes nothing;
   apply is idempotent (second run is a no-op).
6. **Snapshot round-trip:** extended `UserSnapshot` serialises/deserialises through the
   Redis cache form unchanged.
7. Deployed with **zero user-visible change**; full suite green; ruff/mypy clean of new
   issues.

## Build order

1. Enums + `plans`/`subscriptions` models + repositories.
2. `EntitlementRegistry` + `domain/entitlements.py` + startup validation wiring.
3. Migration `2026072002` (schema) + `2026072003` (settings-derived seed).
4. `EntitlementService.resolve` (read path) + unit tests (Decision 5 matrix).
5. `SubscriptionService` (write path) + one-active-row tests.
6. `UserSnapshot` extension (plan_code + entitlements) + shadow parity metric at cache-fill.
7. `scripts/backfill_subscriptions.py` (dry-run/apply) + report tests.
8. Verify on staging (shadow, parity 0), commit, then Owner review before V2.2.
```

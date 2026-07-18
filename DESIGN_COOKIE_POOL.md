# DESIGN — YouTube Cookie Pool

> **Status:** DESIGN DRAFT — written before code, per MASTER_PLAN Hard Rule 4.
> **Author/date:** 2026-07-18. **Owner-approved direction** with the nine adjustments in §0.
> **Supersedes:** the single-master cookie model in `deploy/ytdlp-wrapper.sh`.
> **Related:** `deploy/VPS_DEPLOYMENT_CHANGES.md` (2026-07-18 sessions), `MASTER_PLAN.md`,
> `infrastructure/downloader/routing.py`, `services/admin_notification_service.py`.

---

## 0. What the Owner changed from the first draft

| # | Adjustment | Effect on this design |
|---|---|---|
| 1 | Cookie pool instead of one file | Confirmed — §3 onward |
| 2 | Cookie stays on its egress | Affinity promoted from "optional" to a **first-class, Phase-1** concern (§8) |
| 3 | Route failures must NEVER reduce cookie health | Strict **allowlist** classifier; two separate counters (§7) |
| 4 | Notify on Expired / Invalid / Disabled | Terminal-state notifications with a fixed payload incl. last success (§9) |
| 5 | Replace with zero server commands | Fully in-Telegram flow, validate + canary before commit (§10) |
| 6 | Six values configurable | DB-backed admin-editable settings, not env, not constants (§13) |
| 7 | Log every cookie event | Two sinks with an explicit split so it stays viable at scale (§11) |
| 8 | Statistics page | New admin panel screen (§12) |
| 9 | Multi-WARP / multi-proxy / multi-server | **Egress becomes an identified instance** (§4) + store protocol (§14) |

---

## 1. Problem and the evidence behind it

A single `cookies.txt` gives one Google session for the whole bot. It is a single point of
failure, it concentrates rate-limit pressure on one account, and when it dies every
logged-in feature dies with it. Between 2026-07-13 and 2026-07-18 the master export died
twice within minutes of installation.

Two measured facts from the 2026-07-18 investigation shape this design and must not be
forgotten:

1. **The "confirm you're not a bot" wall follows the egress route, not the cookie.**
   Identical results with and without cookies on the residential proxy (both walled) while
   WARP passed both ways. A pool that strikes a cookie on a wall would burn all ten in
   minutes over a problem no cookie can fix. → §7.
2. **Anonymous extraction still works for most videos.** WARP with no cookies returned full
   format lists. → An exhausted pool must degrade to anonymous, never to failure. → §15.

---

## 2. Scope

**In scope:** multiple YouTube cookies with identity/health/stats; egress affinity;
selection strategies; cooldown and automatic recovery; admin notifications; an
in-Telegram replace flow; a statistics screen; configuration; multi-host readiness.

**Out of scope (explicit non-goals):** cookies for platforms other than YouTube (the
model is generic but only YouTube is wired); automated cookie *harvesting* (all cookies
are admin-supplied); solving route-level walls (that is egress work — §16 note).

---

## 3. Architecture

```
domain/
  entities/cookie.py        CookieId, CookieSnapshot, CookieLease, CookieOutcome
  enums/cookie_health.py    HEALTHY | WARNING | EXPIRED | INVALID | DISABLED
  protocols/cookies.py      CookieProviderProtocol   (what the downloader depends on)
                            CookieStoreProtocol      (where cookie material lives)
                            CookieRepositoryProtocol (metadata persistence)
services/
  cookie_pool_service.py    selection, leases, health transitions, cooldown, recovery
  cookie_classifier.py      (returncode, stderr) -> CookieVerdict     [pure, unit-tested]
  cookie_admin_service.py   validate + canary + atomic replace/disable/enable
infrastructure/
  database/repositories/youtube_cookie.py      metadata + events (Postgres)
  cookies/local_store.py    LocalCookieStore    files under cookies.d/  [swappable]
  cookies/redis_state.py    cursor, leases, hot counters
bot/
  panel/cookies.py          list / detail / stats / replace / disable screens
  handlers/cookie_upload.py FSM document handler for the replace flow
deploy/
  ytdlp-wrapper.sh          unchanged mechanics; honours $YTDLP_COOKIE_FILE
```

**Layering.** `YtdlpProvider` (infrastructure) must not import a service. It receives a
`CookieProviderProtocol` by constructor injection exactly as `proxy` / `warp_proxy` are
injected today; the composition roots (`bot/main.py`, `workers/main.py`) wire the concrete
`CookiePoolService`. Unit tests inject a fake pool.

**The wrapper stays.** Python decides *which* cookie; `ytdlp-wrapper.sh` keeps doing *how
to use it safely* — private jar copy, `flock`, merge write-back, never-shrink guard. It is
already covered by nine in-container tests. It gains one behaviour: use `$YTDLP_COOKIE_FILE`
when set, else today's master (backward compatible; an empty pool changes nothing).

**Provider call shape:**

```python
lease = await cookies.acquire(platform="youtube", egress_id=egress.id)   # may be None
try:
    run yt-dlp with env YTDLP_COOKIE_FILE=lease.path   (omit if lease is None)
    verdict = classify(returncode, stderr)
    await cookies.report(lease, verdict)
finally:
    await cookies.release(lease)
```

---

## 4. Egress identity — the scalability foundation (Owner point 9)

Today `Egress` is an enum of *kinds*: `DIRECT | WARP | PROXY`. "Multiple WARP instances and
multiple proxy pools" cannot be expressed by a kind, and cookie affinity must pin to a
concrete exit IP to be meaningful. So:

```
EgressKind   = DIRECT | WARP | PROXY          (unchanged semantics)
EgressId     = stable string: "direct", "warp-1", "warp-2", "proxy-res-1", "proxy-us-2"
EgressEndpoint(id, kind, address, enabled, weight, notes)
```

- `plan_egress()` returns an ordered tuple of **EgressIds**, resolved through an
  `EgressRegistry` (config-driven now, DB-backed later). Existing size-split and
  metadata-only rules are unchanged — they just yield ids instead of enum members.
- One endpoint per id today (`warp-1` = the current `warp-lb`), so this is a rename with a
  seam, not a behaviour change.
- Cookie affinity stores an `egress_id`. Adding `warp-2` later is a config row plus a
  compose service — no schema or selection change.
- Per-endpoint health lives here (not on cookies): wall rates, timeouts, failures. This is
  where route failures are recorded — see §7.

This is the one structural change I would not defer: retrofitting affinity from kind to
instance later means migrating live affinity data.

---

## 5. Where state lives

| Data | Store | Rationale |
|---|---|---|
| Cookie **material** | Files, `deploy/secrets/cookies.d/<label>.v<N>.txt`, behind `CookieStoreProtocol` | yt-dlp needs a path; rotation rewrites the jar on nearly every run — routing that through Postgres means a ~4 KB blob write per request, and puts live Google sessions in every DB backup |
| **Identity, health, stats, audit** | Postgres | Low write volume, queryable, survives restarts, powers the panel, backed up |
| **Cursor, leases, hot counters** | Redis | Atomic across bot + worker containers; counters flushed periodically (same pattern as `AdEventRecorder`) |

The `CookieStoreProtocol` seam is what makes multi-server possible without redesign (§14).

---

## 6. Data model

```sql
youtube_cookies
  id                    bigserial PK
  label                 text UNIQUE          -- "yt-03", admin-facing, used in notifications
  status                text NOT NULL        -- HEALTHY|WARNING|EXPIRED|INVALID|DISABLED
  cooldown_until        timestamptz NULL     -- orthogonal to status (see §7)
  egress_id             text NULL            -- affinity; NULL = unpinned (new cookie)
  file_version          int NOT NULL         -- bumps on every replace; CAS token
  content_hash          text NOT NULL        -- integrity + multi-host materialisation
  auth_failures         int NOT NULL DEFAULT 0   -- consecutive; ONLY auth-classified
  cooldown_cycles       int NOT NULL DEFAULT 0   -- consecutive cooldowns -> EXPIRED
  total_uses            bigint NOT NULL DEFAULT 0
  total_success         bigint NOT NULL DEFAULT 0
  total_auth_failures   bigint NOT NULL DEFAULT 0
  total_other_failures  bigint NOT NULL DEFAULT 0   -- route/content; stats only
  last_used_at          timestamptz NULL
  last_success_at       timestamptz NULL
  last_failure_at       timestamptz NULL
  last_failure_reason   text NULL
  notes                 text NULL
  created_by            bigint NULL REFERENCES users(id)
  created_at/updated_at timestamptz NOT NULL

youtube_cookie_events            -- audit trail + history (monthly partitions, like ad_events)
  id, cookie_id, event, from_status, to_status, reason, egress_id,
  actor_user_id NULL, created_at
```

Two failure counters, deliberately: `auth_failures` drives health, `total_other_failures`
is statistics only. That separation is how Owner point 3 is enforced structurally rather
than by convention.

---

## 7. Health model and classification (Owner point 3)

Five states as requested. **Cooldown is an attribute, not a sixth state** — otherwise
"expired but cooling down" becomes representable and every query needs to special-case it.

| Status | Selectable | Leaves via |
|---|---|---|
| `HEALTHY` | yes | auth failures → `WARNING` |
| `WARNING` | yes, deprioritised | success → `HEALTHY`; more auth failures → cooldown |
| `EXPIRED` | no | admin replace, or recovery probe (§ auto-recovery) |
| `INVALID` | no | admin replace only |
| `DISABLED` | no | admin re-enable only |

`selectable := status IN (HEALTHY, WARNING) AND (cooldown_until IS NULL OR cooldown_until < now())`

### Classification is an allowlist, and the default is "no health impact"

`cookie_classifier.py` is pure and unit-tested. **Only these signals may reduce health:**

| Signal (yt-dlp stderr / rc) | Verdict |
|---|---|
| `cookies are no longer valid` / `rotated` | `EXPIRED` immediately (cooldown is pointless) |
| Cookie file unparseable, missing required auth cookies | `INVALID` |
| `Please sign in` / account-scoped 401 / 403 on auth endpoints | `AUTH_FAILURE` → strike |
| `This account has been terminated` / suspended | `INVALID` |

**Everything else is `NO_IMPACT` on the cookie.** Explicitly including, per Owner point 3:

| Signal | Recorded as | Cookie health |
|---|---|---|
| `confirm you're not a bot` (wall) | **egress event** on `EgressEndpoint` | untouched |
| Proxy/WARP connect failure, SOCKS error, DNS | egress event | untouched |
| HTTP 5xx, timeouts, connection reset | egress event | untouched |
| Video private / removed / geo / members-only | content event | untouched |
| Unrecognised stderr | `other_failure` (stats only) | untouched |

The default-deny stance matters: a false strike removes capacity from a healthy pool, while
a missed signal costs only slower detection through the consecutive counter. When in doubt,
do nothing to the cookie.

### Cooldown and automatic recovery

Half-open circuit breaker, mirroring the vocabulary `DownloaderRegistry` already uses for
providers (`failure_threshold` → `DEGRADED` for `cooldown_seconds` → retry), so the team
meets one concept rather than two.

```
auth failure   -> auth_failures++
auth_failures >= warning_threshold   -> WARNING            (still selectable, deprioritised)
auth_failures >= cooldown_threshold  -> cooldown_until = now + backoff(cooldown_cycles)
                                        cooldown_cycles++
cooldown elapses -> half-open: the next selection is a single probationary lease
    success -> HEALTHY, auth_failures = 0, cooldown_cycles = 0   (+ recovery event)
    failure -> longer backoff; cooldown_cycles >= max_cycles -> EXPIRED + notify
success at any time -> auth_failures = 0 (and WARNING -> HEALTHY)
```

Backoff is configurable (§13); default 5m → 15m → 60m, capped.

**Auto-recovery:** a low-rate prober in `cleanup_worker` re-tests `EXPIRED` cookies against
a canary video on their affine egress at `recovery_probe_interval`. Sessions do sometimes
come back; free recovery beats a support round-trip. `INVALID` and `DISABLED` are never
auto-probed (malformed file / deliberate human decision).

---

## 8. Selection, affinity and concurrency (Owner point 2)

`acquire(platform, egress_id)` — the egress is chosen **first** by existing routing, then
the pool picks a cookie for that egress.

**Candidate order:**
1. Selectable cookies with `egress_id == requested` — ordered by the configured strategy.
2. Selectable cookies with `egress_id IS NULL` (never used) → pinned to this egress on
   first success. This is how new cookies acquire affinity.
3. If `allow_affinity_break` (default **false**): a selectable cookie pinned elsewhere,
   **borrowed without re-pinning**, logged as `cookie_affinity_borrowed`.
4. Nothing available → `None` → run anonymous (§15).

Affinity only changes by (a) first-success pinning, (b) explicit admin action, or (c) the
affine egress being permanently removed. Borrowing never silently re-pins — that is what
would reintroduce the IP-hopping that invalidates sessions.

**Strategies** (configurable, §13): `LEAST_RECENTLY_USED` (default — maximises the gap
between uses of one session, which is what actually reduces rate-limit pressure),
`ROUND_ROBIN`, `STICKY` (hash video id → cookie; cache-friendly), `WEIGHTED` (by success
rate). Implemented behind one interface; the strategy is a policy object, not an `if` chain.

**Concurrency — two locks, deliberately:**

| Layer | Mechanism | Prevents |
|---|---|---|
| Logical | Redis lease per cookie via existing `RedisLock.acquire(key, ttl) -> token` | Two workers using one session at once — the thing that causes rotation races and looks automated. `max_concurrent_leases` default **1**. TTL covers crashed workers |
| Physical | `flock` in the wrapper around the merge write-back | Torn reads if a lease expires mid-run, Redis is down, or someone runs yt-dlp by hand |

The Redis lease is what makes this correct across the bot and worker containers today, and
across hosts tomorrow (§14).

---

## 9. Notifications (Owner point 4)

Extend `AdminNotificationService` with `notify_cookie_unhealthy` / `notify_cookie_recovered`,
reusing its existing fan-out (Owner + all Moderators, each in their own locale, HTML).
i18n keys `adminnotify.cookie_*` added to **both** `en.json` and `ar.json`.

**Fires immediately on transition to `EXPIRED`, `INVALID`, `DISABLED`.** Payload exactly as
specified:

```
🍪 Cookie yt-03 is now EXPIRED
Reason:        cookies are no longer valid (rotated by Google)
Last success:  2026-07-18 09:14 UTC (3h 20m ago)
Consecutive failures: 4
Pool:          4/6 healthy · yt-03 was pinned to warp-1
Time:          2026-07-18 12:34 UTC

[🔄 Replace cookie]  [⏸ Disable]  [📊 Cookie stats]
```

For `DISABLED` the reason line names the acting admin (audit clarity).

**Noise control** (a degrading pool must not produce ten messages):
- One notification per **state transition**, never per failure.
- `WARNING` and cooldown transitions are panel-only — they are self-healing.
- Per-cookie throttle via the existing `AlertThrottle`.
- If more than `n` cookies degrade inside one window, send one aggregated pool message.
- Recovery notices are batched/quiet.
- Pool below `min_healthy_cookies` → `CRITICAL` through the existing Telegram alert
  pipeline, because downloads are about to degrade.

---

## 10. Replace workflow (Owner point 5)

Zero server commands. One implementation, two entry points — the notification button
deep-links into the same panel flow reachable from the admin panel.

```
[🔄 Replace cookie]                      signed callback (CallbackSigner) carrying
        ↓                                 cookie_id + file_version
FSM: AwaitingCookieUpload(cookie_id, file_version, expires_at = now + 10m)
        ↓  "Send the new cookies.txt for yt-03 as a file.  /cancel to abort."
Admin uploads the document
        ↓
1. Authorise    Owner by default; moderators only if explicitly enabled
2. Sanity       size < 1 MB, .txt, downloadable via Bot API
3. Validate     Netscape parse; required auth cookies present
                (SID/HSID/SSID/APISID/SAPISID or the __Secure-*PSID set)
4. Canary       real extraction against a known video, over that cookie's affine egress
5. CAS commit   reject if file_version changed meanwhile (someone else replaced it)
                write <label>.v<N+1>.txt, flip pointer, keep previous version
6. Reset        status = HEALTHY, counters cleared, cooldown cleared, event row written
7. Clean up     delete the uploaded document message; never log contents
        ↓
✅ "yt-03 replaced (v7) and verified — 27 formats via warp-1. Pool: 5/6 healthy."
```

**Why the canary matters:** it converts "I hope that worked" into a verified state change.
Without it, a wrong paste silently occupies a pool slot and the admin finds out hours later.
Failure at step 3 or 4 leaves the old cookie untouched and reports exactly what failed.

**Security notes.** The uploaded file is a live Google session sitting in a Telegram chat —
deleting the message after ingest is mandatory, not cosmetic (bots may delete incoming
messages in private chats). Contents never reach logs (the logging layer's scrubbing must
cover this path). Files are written only under the git-ignored secrets directory. Owner-only
by default, because these are account credentials rather than settings.

Same flow serves **Add cookie** (new label, no `cookie_id`) and **Remove**.

---

## 11. Logging (Owner point 7)

Every event is logged — but to the sink that fits its volume. At 20k downloads/day
selection alone is ~40k events; writing those to Postgres would be waste, so:

| Event | Structured JSON log | `youtube_cookie_events` | Redis counter |
|---|---|---|---|
| `cookie_selected` | ✅ (label, egress, strategy) | — | ✅ |
| `cookie_refreshed` (jar rotated + persisted) | ✅ | — | ✅ |
| `cookie_updated` / `cookie_replaced` | ✅ | ✅ | — |
| `cookie_expired` / `cookie_invalid` | ✅ | ✅ | — |
| `cookie_recovered` | ✅ | ✅ | — |
| `cookie_disabled` / `cookie_enabled` | ✅ | ✅ (with actor) | — |
| `cookie_health_changed` | ✅ | ✅ | — |
| `cookie_affinity_pinned` / `_borrowed` | ✅ | ✅ (pinned only) | — |
| `cookie_lease_timeout` | ✅ | — | ✅ |

Rule of thumb: **state changes are durable rows; per-request activity is logs plus
counters**, flushed to `youtube_cookies` totals periodically. Structured logs are already
JSON, greppable, and now archived across deploys by `deploy/capture-logs.sh`.

Every log line carries `cookie_label` and `egress_id` so a bad cookie or a bad route can be
isolated with one grep.

---

## 12. Statistics page (Owner point 8)

New screen in `bot/panel/cookies.py`, registered in the existing panel registry.

**List view** — one row per cookie, sorted worst-first so problems surface at the top:

```
🍪 Cookie Pool — 4/6 healthy
──────────────────────────────
🟢 yt-01  warp-1    98.2%  ·  used 2m ago
🟢 yt-02  warp-1    97.5%  ·  used 6m ago
🟡 yt-04  proxy-1   81.0%  ·  cooldown 12m
🔴 yt-03  warp-1    —      ·  EXPIRED 3h ago
⚪ yt-06  —         —      ·  DISABLED
[➕ Add] [🔄 Refresh]
```

**Detail view** — every field the Owner listed:

```
🍪 yt-03  ·  EXPIRED  ·  v6
Requests   1,284 total · 1,190 ok · 94 failed
Success    92.7%
Last used     2026-07-18 12:34 UTC
Last success  2026-07-18 09:14 UTC
Last failure  2026-07-18 12:34 UTC — cookies no longer valid
Egress        warp-1 (pinned 2026-07-14)
Auth failures 4 consecutive · 2 cooldown cycles
[🔄 Replace] [⏸ Disable] [🧪 Test now] [📜 History]
```

`🧪 Test now` runs the canary on demand — the fastest way for an admin to answer "is this
one actually broken?" without touching the server. `📜 History` pages the event rows.

---

## 13. Configuration (Owner point 6)

All six requested values are **DB-backed admin-editable settings** (`SettingsService`,
Redis-cached) rather than env or constants, so they are tunable without a redeploy — the
same surface the existing provider `failure_threshold` / `cooldown_seconds` already use.

| Setting key | Default | Meaning |
|---|---|---|
| `cookie_pool_max` | 10 | Maximum cookies; add is refused beyond it |
| `cookie_selection_strategy` | `lru` | `lru` \| `round_robin` \| `sticky` \| `weighted` |
| `cookie_cooldown_seconds` | 300 | Base backoff; ×3 per cycle, capped at `cookie_cooldown_max_seconds` (3600) |
| `cookie_max_concurrent_leases` | 1 | In-flight runs per cookie |
| `cookie_warning_threshold` | 2 | Consecutive auth failures → `WARNING` |
| `cookie_cooldown_threshold` | 3 | Consecutive auth failures → cooldown |
| `cookie_max_cooldown_cycles` | 3 | Cooldown cycles before `EXPIRED` |
| `cookie_recovery_probe_interval` | 3600 | Seconds between `EXPIRED` recovery probes |
| `cookie_lease_ttl_seconds` | 900 | Lease expiry safety net |
| `cookie_min_healthy_alert` | 2 | Below this → CRITICAL pool alert |
| `cookie_allow_affinity_break` | false | Permit borrowing across egresses |

Env keeps only paths and infrastructure: `YTDLP_COOKIE_POOL_DIR`, `YTDLP_COOKIE_CANARY_URL`.

---

## 14. Multi-server scalability (Owner point 9)

| Concern | Today | What changes for N servers |
|---|---|---|
| Metadata / health / stats | Postgres | Already shared — nothing |
| Leases, cursor, counters | Redis | Already shared and atomic — nothing |
| Egress endpoints | `EgressRegistry`, config-driven | Move to a DB table; per-host reachability recorded per endpoint |
| **Cookie material** | `LocalCookieStore` (bind mount) | **The only blocker.** Implement `SharedCookieStore` (object storage or encrypted DB blob) behind the same protocol |

`CookieStoreProtocol` is deliberately small:

```python
async def read(label, version) -> bytes
async def write(label, version, content) -> None      # returns/records content_hash
async def materialise(label, version) -> Path         # local path for yt-dlp
```

Each host keeps a local materialisation cache keyed by `(label, file_version)`; a version
bump in Postgres invalidates it, so a replace on host A propagates to host B on next use.

**Rotation write-back across hosts** is already safe: the Redis lease serialises use, so
only one host mutates a jar at a time, and write-back carries an optimistic
`file_version`/`content_hash` check. The concurrency design was chosen with this in mind.

---

## 15. Failure modes and graceful degradation

| Situation | Behaviour |
|---|---|
| No cookie available for the egress | **Run anonymous.** Measured: most videos extract fine without cookies. Losing the pool costs age-restricted content, not the service |
| Whole pool unhealthy | Anonymous + one `CRITICAL` alert; do not spam per-cookie |
| Redis unavailable | Fall back to "first selectable cookie" + `flock` only; log degraded mode. Never block downloads on the pool |
| Postgres unavailable | Serve from the last known snapshot in memory; suspend health writes |
| Cookie file missing but row exists | Mark `INVALID`, notify (startup reconciliation scan) |
| Canary fails during replace | Old cookie untouched; admin told exactly what failed |
| Lease holder crashes | TTL expires; cookie returns to the pool automatically |

---

## 16. Phased delivery

| Phase | Contents | Why this order |
|---|---|---|
| **1** | `EgressId` refactor · schema + repo · `LocalCookieStore` · classifier · LRU selection + affinity + leases · cooldown/recovery · wrapper `$YTDLP_COOKIE_FILE` · notifications · replace flow (validate + canary) | The complete loop, minimally. Delivers the actual goal: automatic failover plus no-server-command replacement |
| **2** | Statistics page · `🧪 Test now` · history view · recovery prober · configurable strategies in the panel | UX and autonomy on top of a working core |
| **3** | `SharedCookieStore` · DB-backed egress registry · per-cookie analytics over time | Only when a second host actually exists |

Migration is non-breaking: on first boot the existing `cookies.txt` is imported as `yt-01`
(pinned to `warp-1`); an empty pool behaves exactly like today.

---

## 17. Risks and open questions

1. **Account bans.** Rotating several accounts to spread automated load is contrary to
   YouTube's ToS, and the realistic outcome is periodic account loss. Use dedicated
   accounts, never a personal one, and treat cookie churn as routine operations. This is
   precisely why the *replace* UX matters more than the rotation logic.
2. **Blast radius.** Up to ten live Google sessions on one box. Recommend the pool
   directory be writable only by the processes that need it, and consider that the bot
   container needs write access solely for the replace flow.
3. **This may not be the bottleneck.** The evidence says walls tracked the *route*, and
   WARP served everything anonymously. A pool buys logged-in content and spreads
   per-account rate limits; it will not fix route-level walls. **Egress diversity is likely
   the higher-leverage investment**, and the two compose exactly (pin cookie *i* to egress *i*).
4. **Open — canary choice.** A fixed canary video is simple but becomes a fingerprint if
   requested constantly. Suggest a small rotating set, probed at low rate.
5. **Open — moderator access.** Owner-only by default; confirm whether moderators should
   ever replace cookies.

---

## 18. Test plan

- **Unit (pure):** classifier truth table, incl. explicit cases asserting that bot-check,
  proxy failure, WARP failure, timeout and content errors leave health untouched; state
  machine transitions; backoff maths; strategy implementations; affinity candidate ordering.
- **Unit (services):** lease acquire/release, TTL expiry, concurrency cap, anonymous
  fallback, CAS rejection on stale `file_version`.
- **Integration:** repository round-trips, event partitioning, counter flush, startup
  reconciliation.
- **In-container:** wrapper honours `$YTDLP_COOKIE_FILE`; concurrent runs across different
  cookies do not cross-contaminate jars (extends the existing 9-case self-test).
- **E2E (manual, `ADS_MANUAL_TEST.md` style):** notification → replace → canary → resume;
  disable/enable; recovery probe restoring an `EXPIRED` cookie.

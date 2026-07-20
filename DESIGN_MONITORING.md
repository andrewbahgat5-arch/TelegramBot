# Monitoring & Observability — design

> **Status:** Owner-approved direction (2026-07-19), not yet implemented.
> Written before code per Hard Rule 4 (this changes the `error_logs` schema).
> Related: `core/error_report.py`, `services/error_report_service.py`, `core/alerting.py`,
> `api/routes/admin.py`, `deploy/docker-compose.prod.yml` (uptime-kuma).

## The problem this solves

Everything currently lands in one undifferentiated pile: structured logs on stdout, a
thin `error_logs` table, and CRITICAL-level Telegram alerts. There is no way to answer
"what is failing right now" without SSH, and no way to see *which* user hit *which*
link. The first attempt at fixing that (Sprint 15, already on staging) sent a rich
Telegram report for every failure — which at target scale turns one broken extractor
into hundreds of messages and trains the operator to ignore the channel.

## The shape

Three destinations, one classification.

| Destination | Carries | Why |
|---|---|---|
| **Telegram** | Critical events **only** — things needing intervention *now* | An alert channel is only useful if every message deserves attention |
| **Dashboard → Errors** | Application errors (our bugs, infra faults) | Needs tables and filters; Telegram cannot do this well |
| **Dashboard → Logs** | Operational events, recoverable failures, user mistakes | Complete visibility without noise |

Every event is classified **once at the emit site** with `(severity, category)`. A
routing policy table — not scattered `if` statements — decides where it goes. Adding a
new event type means picking a severity, not editing a dispatch list.

## Decision 1 — alert on STATE, not on error events

This is the central change from the current implementation.

The Owner's critical list (DB unavailable, Redis unavailable, queue failure, storage
failure, cookies expired, auth failures stopping downloads) describes **system states,
not individual failures**. When Postgres drops, every in-flight request raises an
exception; alerting per exception sends hundreds of messages for one outage — precisely
the flood we are trying to avoid.

Dependency health is therefore a small state machine per dependency:

```
   healthy ──────▶ UNHEALTHY   🔴 one alert: what broke, how many requests are failing
      ▲                │
      └── RECOVERED ◀──┘        🟢 one alert: recovered, outage lasted 4m12s
```

* **One** alert on the healthy→unhealthy transition, **one** on recovery (with
  duration). Nothing in between.
* Individual exceptions during the outage go to the Logs table, never to Telegram.
* Data source already exists: `/v1/ready` checks database, redis, queue and workers.
* Cookie-pool exhaustion is the same shape — transition when no usable cookie remains,
  recovery when one returns.

**"Server down" is deliberately NOT self-reported.** A dead process cannot send a
Telegram message. That probe belongs to **uptime-kuma**, which already runs in the
stack on port 3010: it watches `/v1/ready` from outside and alerts when it stops
answering. The app reports its dependencies; uptime-kuma reports the app.

## Decision 2 — one table, two views

`error_logs` today holds only `user_id, job_id, correlation_id, error_type, message,
traceback, created_at`, which supports none of the required filters.

Extend it rather than adding a second table:

| New column | Purpose |
|---|---|
| `severity` | `critical` / `error` / `warning` / `info` — drives routing AND the view split |
| `category` | `unsupported_url`, `extraction`, `download`, `telegram_api`, `database`, … |
| `platform` | filter by site |
| `url` | the full link (see *Privacy* below) |
| `url_host` | cheap filtering/grouping without parsing `url` |
| `username`, `chat_id` | who hit it, without a join |
| `context` (JSONB) | quality, format, stage, worker id, duration, cache hit — open-ended |

"Errors" and "Logs" are then two **filtered views** of one table, not two systems.
Reclassifying an event type (say, demoting extraction failures to Logs) becomes a
config change instead of a data migration, and there is one retention policy and one
query path to maintain.

## Decision 3 — the dashboard lives in the existing API service

There is no web dashboard in this repo today; the admin panel is Telegram-only and
`api/routes/admin.py` returns JSON. Port 3010 is **uptime-kuma's own** dashboard — a
third-party app that cannot host custom pages.

So the Errors/Logs UI is added to the **existing FastAPI `api` service** as
server-rendered HTML: no new container, no frontend build, no new deployment unit.

* `GET /admin/errors` — application errors, filterable
* `GET /admin/logs` — operational events, filterable
* Filters: severity, category, platform, user, date range; paged.
* **URL column renders a short `Link` label** hyperlinking to the original URL, so the
  table stays readable while the real link is one click away.

### Access: localhost-bound, reached over an SSH tunnel

The dashboard displays user URLs, usernames and chat IDs. Port 8080 is currently bound
to `0.0.0.0` and serves plain HTTP, so exposing an admin UI there would put user data
and the admin key on the open internet unencrypted.

The dashboard therefore binds to **127.0.0.1** and is reached with:

```sh
ssh -L 8081:localhost:8080 root@<host>   # then open http://localhost:8081/admin/logs
```

Nothing new is exposed publicly, no certificate or domain is needed, and the data never
crosses the network in the clear. If browser-anywhere access is wanted later, the
upgrade path is a reverse proxy with TLS — an additive change.

## Decision 4 — retention: 30 days, auto-pruned

Long enough to spot a pattern ("this platform broke two weeks ago"), short enough to
bound table growth and to limit how long user URLs and usernames are retained. Pruning
rides on the existing `cleanup_worker`, alongside the current partition maintenance.

Retention is also the privacy control: see below.

## Decision 5 — a compact Telegram errors view stays

The Telegram **System** section gains a *last 10 errors* summary — a glance at "what is
failing right now" from a phone, without a laptop or a tunnel. Deliberately summary
only: real filtering and browsing stay on the dashboard, where tables work.

This is a *pull* (the operator asks), which does not contradict "Telegram carries only
critical alerts" — that rule is about *pushed* messages.

## Privacy note — a deliberate reversal

Until now the codebase deliberately kept user URLs out of the logs, recording only
`platform` / `url_host` / a short `url_hash`. This design stores the **full URL**, plus
username, first/last name and chat id.

That is a real trade, made deliberately: an unsupported-URL report is worthless without
the link, since the whole point is deciding whether to support that site later. It is
bounded by three things — the dashboard is localhost-only, the data is pruned at 30
days, and the audience is Owner/Moderators.

## What changes from what is already on staging

The Sprint 15 work (`core/error_report.py`, `services/error_report_service.py`) stays —
the report model, severity levels, escaping and the 4096-char handling are all still
right. What changes:

1. **Routing**: only CRITICAL reaches Telegram. `unsupported_url`, `extraction_failed`
   and friends stop being pushed and become dashboard rows.
2. **Infra alerts** move from per-exception to the state machine above.
3. `error_logs` grows the columns, and the report is persisted with full context.
4. The dashboard and the Telegram summary view are new.

## Build order

1. Migration: new `error_logs` columns + index on `(severity, created_at)`.
2. Persist full reports; switch routing so only CRITICAL is pushed.
3. Dependency health state machine + uptime-kuma probe for liveness.
4. Dashboard: `/admin/errors`, `/admin/logs`, localhost-bound.
5. Telegram System → last-10-errors summary.
6. 30-day pruning in `cleanup_worker`.

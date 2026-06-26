# Design — Unified Audience Engine, Multi-Placement, and the Shared Ad/Broadcast Wizard

**Status:** DRAFT (Revision 2) for Owner review. **No code, schema, or migration has been written.**
Per Owner directive (2026-06-27) and MASTER_PLAN §1 Hard Rule 4, this document is produced
*before* any schema change. Nothing here is implemented until the Owner approves the
decision-log entries (§7) and the checkpoint sequence (§8).

**Revision 2 (Owner review 2, 2026-06-27)** incorporates: Option A confirmed (§4.1); premium kept
independent of role with role+attribute targeting (§2 of feedback → §4.1); **multi-mode creation —
Wizard *and* Copy both first-class** (§4.4); **edit-from-preview hub** instead of restart (§4.3a);
**internal admin-only ad metadata** (§4.6, new schema D-058); **draft-compatible architecture**, no
draft impl this sprint (§4.7); and **Telegram-ID standardization** across user operations (§4.8).

**Revision 3 (Owner final review, 2026-06-27) — architecture APPROVED for implementation.**
Incorporates: explicit **multi-select Audience builder UI** (§4.1) and **multi-select Placement
builder UI** (§4.2); **full pre-save validation** that jumps to the offending section (§4.9, new);
**enhanced Preview** incl. existing Ad id when editing (§4.3); **registry-driven wizard engine** —
steps as independent registered objects (§4.10, new, **D-059**); **audience/placement registries**
(§4.11, new); **forward-compatibility hooks** for ad history, search, bulk ops, and analytics
(§4.12, new — design-compatible only, no implementation). The five §9 questions are resolved as
adopted defaults. Implementation proceeds on the C1→C9 checkpoint sequence (§8), stopping after each.

**Sprint:** 9.6 (Admin Inline Control Panel, F-2 / EP-22), extending into F-3 / EP-23.
**Author target:** the EP-22 wizard work (was Task 9.6.10) re-scoped after Owner feedback.
**Baseline:** branch `claude/happy-bose-71ed46`, last commit `0af65c0`, migration head
`202606250002`. 608-test green baseline (with the documented environmental deselects).

---

## 1. Why this document exists

The original Task 9.6.10 was a *UI-only* job: wire FSM wizards onto the **existing** ad/broadcast
services. Owner feedback (2026-06-27) expanded the requirements to:

1. A **generic include/exclude audience engine**, with **premium as an audience attribute**
   (not a role), **shared by both Advertisements and Broadcasts** and reusable by future
   messaging features.
2. **Multi-placement** ads (an ad may occupy several placements at once).
3. A **single compose wizard** that is the foundation for both Ads and Broadcasts (Broadcasts
   skip the placement step), collecting **configuration first** and **content last** ("the next
   Telegram message becomes the ad", preserving Telegram-native content).

Items (1) and (2) change the **LOCKED** Sprint 9.5 data model. They cannot ride inside a "wizard"
task; they need decision-log entries and Owner sign-off (§1 Hard Rule 4). Item (3) is mostly UI,
but it *consumes* (1) and (2), so it is sequenced after them.

---

## 2. Current state — what already exists (reuse, do not rebuild)

Grounded in the code as of `0af65c0`:

| Capability | Where | Notes |
|---|---|---|
| First-class **include/exclude** audience rules for **ads** | `services/audience_service.py`, `domain/enums/ad_audience.py`, `infrastructure/database/models/ad_audience_rule.py` | `effect` (include/exclude) × `dimension` × `value`; OR within a dimension, AND across dimensions; `exclude` removes a match. **LOCKED, D-043.** |
| **Premium is already a dimension** (`plan` = free/premium) | `AudienceService._rule_hit` (`AudienceDimension.PLAN`) | The Owner's "premium as an attribute, not a role" is **already true for ads**. |
| Other dimensions | enum `AudienceDimension` | `role`, `plan`, `language`, `user_id`, `segment`, `country` (country reserved, EP-20). |
| Reusable **segments** | `audience_segments`, `audience_segment_members`, `AudienceService` segment CRUD | Membership loaded lazily only when a `segment` rule is present. |
| Per-viewer **Python matcher** | `AudienceService.matches(ad, ctx)` | Evaluates one ad against one `AudienceContext`. Used on the ad-delivery path (small per-placement candidate list, one viewer). |
| **Copy-mode** native content | `AdService` (`delivery_mode=copy`), `ads_storage_chat_id` setting, `AdSenderProtocol.copy_ad` | "Forward/send a message → reuse it verbatim" already works (D-042). |
| Ad CRUD | `AdService.create/edit/add_button/delete/set_active/overall_stats` | Drives all ad mutations; validated `key=value` field map. |
| Ad → broadcast | `BroadcastService.create_from_ad` + `BroadcastWorker` copy branch | A broadcast can deliver a stored ad via `copy_message` (D-045). Already wired into the panel (Task 9.6.9). |
| Scheduling | `scheduled_at` on ads + broadcasts, broadcast due-poller, ad selection gate | D-053. |

**Conclusion:** the Owner's audience vision is ~80 % built **for ads**. The genuine gaps are
narrow and specific (next section).

---

## 3. Gap analysis — what is actually missing

| Gap | Today | Needed | Touches schema? |
|---|---|---|---|
| **G1 — Broadcasts cannot target by premium / segment / include-exclude** | `broadcasts.target_role` + `target_language` only; worker pages via `UserRepository.page_for_broadcast(role, language)` and counts via `count_for_broadcast(role, language)` | Broadcasts evaluate the **same rule model** as ads | **Yes** — broadcasts must persist a rule set, and the worker must page an audience defined by rules. |
| **G2 — Audience rules cannot be compiled to SQL** | `AudienceService.matches` evaluates **one user in Python** | A **set-based SQL evaluator** to `COUNT` and `PAGE` an audience of thousands (broadcast fan-out) | No (new code, no schema) |
| **G3 — Ads are single-placement** | `advertisements.placement` is one `String(30)` column; `list_active_for_placement(place)` filters `WHERE placement = place` | An ad may belong to **several** placements | **Yes** — placement becomes one-to-many. |
| **G4 — No compose wizard** | `key=value` commands + the read/stepper panel | A shared Ad/Broadcast FSM wizard (config-first, content-last) | No (UI only; consumes G1–G3) |
| **G5 — Rich content in the wizard** | Copy-mode exists for commands | The wizard's final "send content" step stores a native message | No (reuses copy-mode columns) |

---

## 4. Proposed architecture

### 4.1 Unified Audience Engine (G1, G2)

**Core idea:** an **audience expression** is a portable bundle of `(mode, [rules])` that any
messaging feature can own. It has **two evaluators** over the *same* persisted rules:

1. **Per-viewer matcher (exists)** — `AudienceService.matches`, used by ad delivery (one user).
2. **Set-based SQL compiler (new)** — turns a rule set into SQLAlchemy `WHERE` predicates over
   `users`, used by broadcast **count** and **paging** (thousands of users). This is the one
   genuinely new evaluation component.

Both evaluators MUST agree bit-for-bit on semantics (OR within dimension, AND across dimensions,
exclude removes, mode all/include/exclude) and on the **effective-premium** definition (below).

#### Persistence — two options (Owner to choose in review)

- **Option A (recommended) — normalized shared entity.** New `audience_expressions(id, …)` and
  generic `audience_rules(expression_id FK CASCADE, effect, dimension, value)`. Add a nullable
  `audience_expression_id` FK to **both** `advertisements` and `broadcasts`. Existing
  `ad_audience_rules` are **backfilled** into the new tables and dual-read for one deprecation
  window (mirroring how D-043 deprecated `target_role`). *Pro:* one rule model reused by every
  future feature (the Owner's stated goal). *Con:* larger migration; a deprecation window for
  `ad_audience_rules`.
- **Option B (minimal) — parallel table.** Keep `ad_audience_rules` as-is; add a mirror
  `broadcast_audience_rules(broadcast_id FK, effect, dimension, value)`. `AudienceService` and the
  SQL compiler operate on a generic rule list regardless of source table. *Pro:* no change to the
  LOCKED ad path, smallest migration. *Con:* two tables to evolve; "reusable for future features"
  is by convention, not by schema.

> **DECISION (Owner review 2): Option A is approved.** A single shared `audience_expressions` +
> `audience_rules` model, reusable by Ads, Broadcasts, and every future messaging feature. Option B
> is retained in this doc only as the documented rejected alternative.

**Role and attribute are independent dimensions (Owner #2).** `role` (owner/moderator/user) and
`plan` (free/premium) are *separate* dimensions that compose freely: e.g. *include* `role=user` +
*include* `plan=premium` is "premium regular users"; *include* `plan=free` alone is "all free users
regardless of role". Premium is never modeled as a role. Future attribute dimensions (e.g. a paid
tier, a cohort flag) slot in the same way without disturbing role targeting.

#### Effective-premium semantics (shared by both evaluators)

`plan = premium` ⇔ `users.is_premium = TRUE AND (users.premium_expires_at IS NULL OR
users.premium_expires_at > now())`; `plan = free` is the negation. This matches the Python
matcher's existing `AudienceContext.plan` (computed via `AdService._is_premium_active`). The SQL
compiler must encode the **identical** predicate so a "Premium Users" broadcast and a
"premium-only" ad target the same set.

#### SQL compiler — dimension → predicate

| Dimension | SQL predicate over `users` |
|---|---|
| `role` | `users.role IN (values…)` |
| `plan` | effective-premium predicate above (or its negation for `free`) |
| `language` | `users.language IN (values…)` |
| `user_id` | `users.telegram_id IN (values…)` — see inconsistency note below |
| `segment` | `users.id IN (SELECT user_id FROM audience_segment_members WHERE segment_id IN (values…))` |
| `country` | reserved (EP-20) — compiles to FALSE / ignored, no source yet |

Combination: within a dimension `OR` the values; across dimensions `AND`; an `exclude` expression
becomes `AND NOT (expr)`; `mode=include` requires the include expr; `mode=exclude` is "everyone
except"; `mode=all` is "everyone unless an exclude matches".

#### Default guards (safety, preserved from today)

The audience always intersects with **non-banned** users, and **staff (owner/moderator) are
excluded unless an explicit `include role=…` rule names them** — preserving the current
`page_for_broadcast` behavior (`role IS NULL → role NOT IN staff`). This prevents an "all users"
broadcast from messaging admins or banned users by accident.

#### Known inconsistency to standardize (flag)

`AudienceDimension.USER_ID`'s enum comment says "user row id", but `AudienceService._rule_hit`
compares `str(ctx.telegram_id) == value` — i.e. the value is the **Telegram id**. The SQL compiler
will match `users.telegram_id`. Recommendation: standardize on **Telegram id** (what admins type)
and fix the enum comment. No behavior change for existing ads.

#### Audience builder UI (wizard step 2, Owner #1)

The audience step is an explicit **multi-select** builder with **separate Include and Exclude
sections**, rendered from the dimension registry (§4.11). Toggling an item adds/removes a rule on the
in-progress expression; the screen shows the running selection so the Owner reviews all rules before
continuing, and the step is independently re-openable from the Preview edit-hub (§4.3).

```
Audience

Include
  ☑ Free Users          ☐ Languages…
  ☑ Premium Users       ☐ Segments…
  ☐ All Users           ☐ Specific User IDs…

Exclude
  ☐ Owner               ☐ Free Users
  ☐ Moderators          ☐ Specific User IDs…
  ☐ Premium Users

[ ⬅️ Back ]  [ ❌ Cancel ]  [ 🏠 Home ]   [ Continue ▸ ]
```

- Simple toggles (Free/Premium/All/Owner/Moderators) flip a rule immediately. Dimensions that need a
  value (Languages, Segments, Specific User IDs) open a sub-prompt (typed input / pick list) and may
  hold **several** values (each a rule; OR-ed within the dimension). Telegram has no native checkbox,
  so ☑/☐ is rendered in the button label and toggled in place (signed callback carries the
  dimension + value + include/exclude).
- "All Users" = `mode=all` with no include rules; adding Excludes narrows it. Choosing any Include
  switches the expression to `mode=include`.

### 4.2 Multi-placement for ads (G3)

- New join table `ad_placements(advertisement_id FK CASCADE, placement, PRIMARY KEY
  (advertisement_id, placement))`. An ad with placements `{video_delivery, audio_delivery}` has two
  rows.
- `AdRepository.list_active_for_placement(place)` joins `ad_placements` instead of filtering the
  scalar column: `… JOIN ad_placements ap ON ap.advertisement_id = a.id WHERE ap.placement = :place`.
- Selection index moves to `ad_placements(placement)` (+ the existing active/priority ordering on
  `advertisements`). The LOCKED `ix_ads_placement_active_priority` is retained for the deprecation
  window (additive, mirroring D-044's "retain the old index" rule).
- **Deprecation window:** keep `advertisements.placement` (single) populated with the ad's *primary*
  placement and **backfill** one `ad_placements` row per ad; dual-read until the window closes
  (same pattern D-043/D-044 used). Per-placement **settings toggles** (§13.6) are unchanged — an
  ad shows in a placement only if that placement's toggle is ON *and* the ad has that placement row.
- **Scope guard:** broadcasts are not a placement of a persistent ad — `placement=broadcast`
  (D-044) stays as the compat marker; the wizard's "Broadcast" type drives `BroadcastService`, not a
  placement row.

#### Placement builder UI (wizard step 3, ads only, Owner #2)

The placement step is a **multi-select** builder rendered from the placement registry (§4.11); an ad
may belong to several placements at once. Broadcasts skip this step entirely.

```
Placements

  ☑ Video Delivery      ☐ Home
  ☑ Audio Delivery      ☐ History
  ☐ Quality Selection

[ ⬅️ Back ]  [ ❌ Cancel ]  [ 🏠 Home ]   [ Continue ▸ ]
```

Each ☑ becomes one `ad_placements` row on Save. A placement still only *shows* if its §13.6 toggle
is ON (the toggle is global; the ☑ is per-ad). Independently re-openable from the Preview edit-hub.

### 4.3 Unified Compose Wizard (G4) — one FSM for Ads and Broadcasts

A single aiogram FSM (default `MemoryStorage`, **no new Redis key**, §11.4 stays locked) drives both
flows. Steps are a **declarative list** so future steps insert without rewriting navigation
(satisfies the "modular, plugin-friendly" goal):

```
1. Type        : [📢 Persistent Ad] [📣 Broadcast]
2. Audience    : multi-select include/exclude builder  (writes rules to the expression)
3. Placement   : multi-select  (PERSISTENT AD ONLY — Broadcast skips this step)
4. Settings    : enabled · priority · frequency (ads) · internal name/notes · schedule (future)
5. Content     : "Please send the advertisement content."  → next message captured natively
                 (content mode chosen here: Copy = forward/send a message; Fields = composed text)
6. Preview     : Type · Audience (Include / Exclude listed separately) · Placement(s) ·
                 Settings · Internal metadata · rendered content preview
7. Confirm     : [✅ Save] [✏️ Edit ▸ section] [❌ Cancel]
8. Save        : persist only on Save
```

- **Step 2 (Audience)** renders from a **dimension registry** (the `AudienceDimension` members with
  presets: Free, Premium, All, By Language, By User ID, By Segment) with Include/Exclude toggles and
  multi-select. Each selection is a rule on the in-progress expression. "All Users" = `mode=all`
  with no include rules; adding excludes narrows it.
- **Step 3 (Placement)** renders from the placement registry (the `AdPlacement` members with their
  §13.6 toggles), multi-select. Skipped entirely when Type = Broadcast.
- **Step 5 (Content)** — see §4.4.
- **Preview (Step 6, Owner #4/#9):** a complete verification screen representing the **final object
  exactly as it will be stored** — Type · **Include rules** and **Exclude rules** (listed
  separately) · Placement(s) · Enabled/Disabled · Priority · Internal Name · Internal Notes · a
  rendered preview of the actual content (`AdService.preview` for ads; the composed message for
  broadcasts) · and, **when editing an existing object, its Ad/Broadcast id**.
- **Edit-from-preview hub (Step 7, Owner #10) — NOT a restart.** The Preview is a *hub*. "✏️ Edit"
  opens a section picker — `[Audience] [Placement] [Settings] [Content] [Metadata]` — and selecting
  one **jumps directly to that step**; on completing it the wizard returns **straight to Preview**,
  never replaying the earlier steps. This makes the step model "linear on first pass, then
  hub-and-spoke for edits": each step is independently addressable by a step id carried in the
  signed callback `arg`, and every step knows its return target (Preview when reached via Edit,
  the next step when reached on the first pass).
- **Navigation:** every step carries ⬅️ Back · ❌ Cancel · 🏠 Home (reuses `nav_row` /
  `build_input_prompt`). Back re-arms the previous step; Cancel clears state and returns to the
  section menu; the panel message is **edited in place** (no chat spam).
- **Busy-wizard protection (#3):** the FSM is per-(chat,user); entering a wizard while one is active
  refuses with a hint ("finish or cancel the current wizard first"). Any panel navigation/write
  clears stale state (the existing `state.clear()` discipline in `panel_navigate`/`panel_write`).
- **Authorization:** entire wizard is **Owner-only** (write tier). All step callbacks are new
  **write** action codes — unlisted in `READ_ACTIONS`, so they fail safe to owner-only and are
  hidden from moderators (defense in depth, §9.1). Every `callback_data` is HMAC-signed and ≤64
  bytes; step indices and small option ids ride in the existing `arg`/`value` ints (no raw strings
  in callbacks).
- **No business logic in handlers (§9.1):** the wizard only collects input and calls
  `AdService.create/edit/add_button`, `AudienceService.add_rule`, `BroadcastService.create`, and the
  new placement/expression service methods. Validation stays in the services.

### 4.4 Rich Telegram content capture (G5)

**Two co-equal creation methods (Owner #8), both always available:**

- **Wizard Mode** — the step-by-step flow above (config first, then compose/send content).
- **Copy Mode** — forward or send an existing Telegram message and reuse it verbatim. In the shared
  wizard this is the **default content mode** at Step 5 (the message is stored and delivered via
  `copy_message`). It also keeps its **standalone fast paths**: the existing `/ad_create
  delivery=copy` command, and a panel "📋 Copy existing message" entry that captures a forwarded
  message and then runs only the minimal config it still needs (audience, placement). Neither method
  is removed; they share the same persistence and audience/placement engine.

The Content step asks the Owner to **send the message**; the next Telegram message becomes the
content, preserving native formatting:

- **Default = copy-mode.** Store `(storage_chat_id, storage_message_id)` and deliver later via
  `copy_message` — this preserves text/photo/video/animation/audio/document/album, captions,
  Telegram formatting, and (re-attached) buttons verbatim (D-042). The durable source is the
  `ads_storage_chat_id` channel when configured; if unset, the source is the Owner's own message
  (works as long as it is not deleted — the Preview/Confirm warns about this).
- **Fields-mode** remains available for purely programmatic text ads (the typed path), reusing
  `AdService.create(delivery=fields, …)`.
- **Broadcasts of rich content** reuse the **ad** copy-mode storage: a rich broadcast creates a
  copy-mode ad row and calls `BroadcastService.create_from_ad` (already wired). A plain-text
  broadcast uses `BroadcastService.create(message_text=…)`. No new broadcast content columns.
- Inline buttons captured during the wizard map to `AdService.add_button` (multi-button, D-042).

### 4.5 Future-proofing (explicitly requested)

- **New audience dimension:** add an enum member + one branch in the Python matcher + one branch in
  the SQL compiler + (optionally) a wizard preset. The wizard's audience step reads the dimension
  registry, so **no flow redesign**.
- **New placement:** add an `AdPlacement` member + a §13.6 toggle. The wizard's placement step reads
  the placement registry — **no flow redesign**.
- **New messaging feature:** give it an `audience_expression_id` (Option A) and reuse the matcher
  (per-recipient) or the SQL compiler (bulk). The engine is feature-agnostic.
- **New wizard step:** append to the declarative step list; navigation is index-driven.

### 4.6 Internal advertisement metadata (Owner #11) — admin-only

Each advertisement gains optional, **admin-only** metadata that **end users never see**:

- `advertisements.internal_name VARCHAR(120) NULL` — a label like "Summer Campaign", "Black Friday".
- `advertisements.internal_notes TEXT NULL` — free-form administration notes.

These are set in the wizard's Settings step (and via `/ad_create`/`/ad_edit` `internal_name=…`,
`notes=…`), shown in the panel's ad list/detail and Preview, and **excluded from every delivery
path** (`AdSenderProtocol` reads only content fields; the metadata columns are never passed to
`send_ad`/`copy_ad`). This is a small additive schema change (D-058). Scope: ads only for now;
broadcasts can adopt the same columns later via the shared entity if wanted (open question §9).

### 4.7 Draft-compatible architecture (Owner #15) — no draft implementation this sprint

We do **not** build drafts now, but we keep the door open additively:

- The wizard's in-progress state is modeled as a single **serializable `WizardState` payload**
  (type, expression-rules-in-progress, placements, settings, metadata, content ref, current step).
  Today it lives in aiogram `MemoryStorage` (ephemeral — lost on process restart), which is fine for
  an active session but cannot survive a restart.
- **Future "Save as Draft / Resume Draft" is then purely additive:** persist that same `WizardState`
  (e.g. a `wizard_drafts` row keyed by admin) and offer "Resume Draft" on entry. No flow redesign,
  because the state is already a self-contained, serializable object and steps are independently
  addressable (the edit-hub work in §4.3 already requires this).
- Alternative kept open: persist the composing ad early as a `draft`-status row + expression so the
  partial work is durable from the start. Heavier (needs a draft lifecycle + cleanup); deferred.

### 4.8 Telegram-ID standardization (Owner #12)

Every user-targeted operation — User Info / Ban / Unban / Premium / Set Role / the audience
`user_id` dimension / any future user action — uses the **Telegram user id** (what admins know),
never the internal row id, as the value an admin types or that rides in a rule. The `user_id`
dimension's enum comment is corrected to say "Telegram id" (no behavior change — the Python matcher
already compares `ctx.telegram_id`). This aligns with queued Owner requirement #10 (direct user-id
input for every user action) and is applied consistently across the panel.

### 4.9 Full pre-save validation (Owner #3)

Save is gated by a complete validation pass over the assembled object. Each check names the **step
it belongs to**, so on failure the wizard jumps **directly to that section** (then returns to
Preview) — never a restart. Checks (delegated to the services, not the handlers):

- audience expression is non-empty / coherent (an `include` mode has ≥1 include rule);
- a **Persistent Ad has ≥1 placement** (broadcasts: N/A);
- content exists (fields-mode: text or media per ad type; copy-mode: a stored message ref);
- buttons valid (each has both text and a syntactically valid URL — reuses `AdService` button
  validation);
- include/exclude rules are **not contradictory** (e.g. the same dimension+value both included and
  excluded → flagged);
- required fields complete (title for ads, etc.).

The same validators run regardless of how the step was reached (first pass or edit-hub), so a
saved object is always internally consistent. Service-layer validation stays authoritative
(`AdService.create/edit`, `BroadcastService.create`, `AudienceService.add_rule`).

### 4.10 Registry-driven wizard engine (Owner #10) — D-059

The wizard is **not** hardcoded flow logic. It is a small engine that navigates a **registry of
step objects**, each declaring:

| Field | Meaning |
|---|---|
| `step_id` | stable short id (rides in the signed callback `arg`) |
| `title` / `description` | rendered header + helper text |
| `applies_to` | which wizard kinds use it (e.g. `{ad, broadcast}`; placement = `{ad}` only) |
| `render(state)` | builds the screen text + keyboard from the in-progress `WizardState` |
| `validate(state)` | returns ok / a field-level error (feeds §4.9 and the edit-hub jump) |
| `prev` / `next` | navigation targets (the engine computes the *applicable* next, so Broadcast auto-skips Placement) |

The engine handles Back/Cancel/Home, the first-pass linear walk, and the edit-hub return-to-Preview
behaviour generically — it never hardcodes "step 3 is placement". Adding **Scheduling**, **Country
Targeting**, **A/B testing**, **Campaign Expiration**, or any future step = **register one step
object**; no engine change. This is the architectural backbone that makes the wizard future-proof
(Owner #10/#13) and is the first thing built in checkpoint C5.

### 4.11 Audience & Placement registries (Owner #11)

Mirroring the panel's existing `SECTIONS`/`SUBMENUS` registry pattern (`bot/panel/registry.py`):

- an **AudienceDimension registry** — each entry: dimension code, label, whether it needs a typed
  value, presets (Free/Premium/All/By Language/By Segment/By User ID), and its Python-matcher +
  SQL-compiler handlers (so a new dimension registers a row + two small handlers, never edits to the
  wizard or the evaluators' control flow);
- a **Placement registry** — each entry: placement code, label, and its §13.6 toggle key.

The audience builder (§4.1) and placement builder (§4.2) render **from these registries**, so adding
a dimension or placement is a registration, not a wizard change (Owner #11/#13). The reserved
`country` dimension (EP-20) is the first beneficiary — it registers when a country source exists.

### 4.12 Forward-compatibility hooks (Owner #6/#7/#8/#9) — design-compatible, NOT built now

No implementation this sprint; the architecture is kept compatible:

- **Ad/Broadcast history pages** (#6: Recent Ads / Recent Broadcasts / Recently Edited / Recently
  Disabled) — `advertisements` already has `created_at`/`updated_at`; broadcasts have
  `created_at`/`completed_at`. "Recently disabled" would later add a `disabled_at` timestamp (a
  future additive column). The panel's list builders are already paginated-ready (`pg` action).
- **Search** (#7: ads / broadcasts / users) — the new `internal_name` (D-058) and existing indexed
  ids/titles give searchable handles; a future search step reuses the guided-input mechanism. Nothing
  in this design precludes it.
- **Bulk operations** (#8: enable/disable/delete/broadcast multiple) — the multi-select UI pattern
  (§4.1/§4.2) and the registry engine make a future multi-select list + batch action additive;
  services already expose per-item `set_active`/`delete`.
- **Analytics** (#9: displayed/clicked/CTR/last-displayed/active-placements) — impressions/clicks
  counters exist on `advertisements`; per-event analytics already exist in `ad_events` (D-052);
  "last displayed" / "active placements" are future additive reads/columns. The model stays
  extensible.

These are recorded so checkpoints do not accidentally close the door on them; none gate Sprint 9.6.

---

## 5. Data model & migration plan (additive, deprecation-windowed)

All migrations are **additive** and back-compatible; existing rows keep working (the D-043/D-044
playbook). Proposed new head chain on top of `202606250002`:

1. **`2026XXXX0001_unified_audience`** (G1/G2 persistence, Option A):
   - create `audience_expressions(id …)` and `audience_rules(expression_id, effect, dimension,
     value)`;
   - add nullable `advertisements.audience_expression_id` and `broadcasts.audience_expression_id`
     FKs;
   - backfill: one expression per ad that has `ad_audience_rules`, copy its rules; keep
     `ad_audience_rules` for the deprecation window (dual-read).
   - *(Option B variant: instead create `broadcast_audience_rules` and skip the ad backfill.)*
2. **`2026XXXX0002_ad_placements`** (G3): create `ad_placements`, backfill one row per ad from
   `advertisements.placement`, add `ix_ad_placements_placement`; retain the old column + index for
   the window.
3. **`2026XXXX0003_ad_internal_metadata`** (§4.6): add nullable `advertisements.internal_name
   VARCHAR(120)` and `internal_notes TEXT`. Additive; no backfill (NULL = no metadata). D-058.

No new **settings key** and no new **environment variable** are required by this design (the
audience/placement state is relational; copy-mode storage already has `ads_storage_chat_id`). If a
future step needs a config key, it stops for separate approval (Hard Rule 5).

---

## 6. Architecture notes / invariants

- **Two evaluators, one semantics.** The Python matcher and the SQL compiler are tested against a
  **shared truth table** of (rule set × user) cases so they can never drift. This is the single
  highest-risk area and gets the most test coverage.
- **Hot path untouched.** Ad delivery keeps using the Python matcher over the small per-placement
  candidate list (D-043). The SQL compiler runs only on the broadcast count/paging path (already
  off the user's interactive path, in `BroadcastWorker`).
- **Worker change is localized.** `BroadcastWorker._fan_out` already pages with
  `page_for_broadcast(role, language)`; it changes to page by an expression's compiled predicate.
  The chunked, crash-safe counter logic is unchanged.
- **Layering preserved (§8).** New SQL compilation lives in the repository/infrastructure layer
  (it builds SQLAlchemy predicates); `AudienceService` stays transport-free; handlers stay logic-free.
- **Governance.** This supersedes nothing destructively: D-043 (rules), D-044 (placement), D-045
  (ad broadcast) are **extended additively**, not replaced.

---

## 7. Draft decision-log entries (for MASTER_PLAN §5 — NOT yet committed)

These are drafted here for review. On approval they are appended to the LOCKED MASTER_PLAN decision
log (current last id **D-054**) and the §23 F-2/F-3 / EP-22/EP-23 notes updated.

- **D-055 — Unified audience engine (ads + broadcasts).** *(Option A approved, Owner review 2.)*
  Introduce an `audience_expressions` +
  `audience_rules` model (Option A) referenced by nullable FKs on `advertisements` and `broadcasts`;
  add a **set-based SQL evaluator** alongside the existing per-viewer Python matcher, sharing one
  semantics (OR-in/AND-across/exclude-removes) and one effective-premium predicate. Broadcasts gain
  premium/segment/include-exclude targeting; the `BroadcastWorker` pages by a compiled predicate.
  Banned excluded always; staff excluded unless explicitly included. `target_role`/`target_language`
  on broadcasts and `ad_audience_rules` are retained + dual-read for one deprecation window.
  *Alternatives:* parallel `broadcast_audience_rules` (Option B); premium-only flag on broadcasts
  (does not generalize); per-user Python eval for broadcasts (does not scale to bulk count/paging).
- **D-056 — Multi-placement ads.** Replace the single `advertisements.placement` with a one-to-many
  `ad_placements` join table (backfilled, dual-read for one window); `list_active_for_placement`
  joins it; the per-placement §13.6 toggles are unchanged. *Alternatives:* a comma-list column (not
  queryable/indexable); an array column (weaker FK/index story); keeping single placement (rejected
  by Owner #12).
- **D-057 — Unified compose wizard (EP-22 + EP-23).** One Owner-only aiogram FSM drives both Ad and
  Broadcast creation: config-first (Type → Audience → Placement[ads] → Settings) then content-last
  ("send the message") → Preview → Save/Edit/Cancel. **Two co-equal content methods (Wizard compose
  and Copy-mode forward/send), both retained** (Owner #8). The **Preview is an edit hub**: "Edit"
  jumps to a chosen section and returns to Preview rather than restarting (Owner #10). Steps are
  declarative and **independently addressable**, and the wizard state is a single **serializable
  payload** so a future "Save/Resume Draft" is additive (Owner #15) — no draft built this sprint.
  Busy-wizard protection (one active wizard per admin); signed ≤64-byte callbacks; drives existing
  services + the D-055/D-056/D-058 surfaces only (no business logic in handlers). Realizes the
  reserved EP-22 (panel) and EP-23 (rich builder) as a single flow. *Alternatives:* separate Ad and
  Broadcast wizards (duplicate flow); a restart-on-edit wizard (rejected by Owner #10); keeping
  `key=value` commands as the only builder (rejected by Owner #4/#10).
- **D-058 — Internal advertisement metadata.** Add nullable `advertisements.internal_name`
  (VARCHAR 120) + `internal_notes` (TEXT), admin-only and **never on any delivery path** (Owner #11).
  Shown in panel list/detail/Preview and editable in the wizard + `/ad_create`/`/ad_edit`. Additive,
  no backfill. *Alternatives:* a separate metadata table (overkill for two nullable columns); reusing
  `title` as the admin label (conflates the user-visible title with an internal name — rejected).
- **D-059 — Registry-driven wizard engine + audience/placement registries (Owner #10/#11).** The
  compose wizard is a generic engine over a **registry of step objects** (`step_id`, title,
  `applies_to`, `render`, `validate`, `prev`/`next`); the engine computes the applicable next step
  (Broadcast auto-skips Placement), drives the edit-hub return-to-Preview, and runs §4.9 validation —
  never hardcoding the flow. Audience **dimensions** and **placements** are likewise registries
  (mirroring `bot/panel/registry.py`): a new dimension/placement/step is a *registration*, not an
  engine edit. Enables future Scheduling / Country / A/B / Expiration / bulk / search without wizard
  redesign. *Alternatives:* hardcoded linear FSM transitions (every new feature edits the flow —
  rejected by Owner #10); per-wizard bespoke flows (duplication). Pairs with D-057.

---

## 8. Proposed checkpoint sequence (each: implement → test → commit → STOP for review)

Dependency order. Schema-gated checkpoints are blocked until the relevant D-entry above is approved.

| # | Checkpoint | Depends on | Schema? |
|---|---|---|---|
| C1 | **Audience SQL compiler** + shared semantics test (truth table vs Python matcher). Pure code over existing rule shape. | D-055 approved (persistence shape) | No (new code) |
| C2 | **Unified audience persistence** migration (`audience_expressions` + `audience_rules`, FKs, backfill, dual-read). | C1 | **Yes** |
| C3 | **Broadcasts use the engine**: `BroadcastService.create(expression)`, `count`/`page` by compiled predicate, `BroadcastWorker` paging. | C2 | No (uses C2) |
| C4 | **Multi-placement** migration (`ad_placements`, backfill) + `AdService`/repo reads, **and** internal-metadata columns (D-058). | D-056 + D-058 approved | **Yes** |
| C5 | **Wizard engine + registries (D-059)**: step-registry engine, audience/placement registries, serializable `WizardState`, **Preview edit-hub**, §4.9 validation framework, busy-protection, Back/Cancel/Home. (Type → Settings → Preview → Confirm skeleton.) | D-057 + D-059 approved | No |
| C6 | **Wizard — Audience step** (multi-select include/exclude over the dimension registry; editable from Preview). | C3, C5 | No |
| C7 | **Wizard — Placement step** (multi-select; ads only; editable from Preview). | C4, C5 | No |
| C8 | **Wizard — Content step** (both modes: Copy capture + Fields compose + buttons) + internal metadata + **Edit-Ad**. | C4, C5 | No |
| C9 | **Docs & final sweep** (was 9.6.11): PROJECT_PROGRESS, MASTER_PLAN §23/§5, COMMANDS, TEST_RESULTS, EP-22/EP-23 status, baseline. | C1–C8 | No |

A lower-risk **fallback path** if the Owner prefers to ship value before the schema work: do the
no-schema broadcast wizard on the existing role+language targeting first (old Task 9.6.10c), then
land C1–C9. This is the "Defer both" option from the prior review; recorded here as an alternative.

---

## 9. Decisions on the prior open questions

The Owner declared the architecture complete and approved implementation (final review). The five
prior open questions are **resolved as the adopted defaults below**; any of these is cheap to revise
at the relevant checkpoint's stop-for-review if the Owner objects.

1. **Audience persistence = Option A** (normalized `audience_expressions` + `audience_rules`).
   *(Owner review 2.)*
2. **`user_id` dimension = Telegram id**, enum comment corrected. *(Owner #12.)*
3. **Deprecation windows = yes, dual-read** for `ad_audience_rules`, `advertisements.placement`, and
   broadcast `target_role`/`target_language` for one window (the D-043/D-044 pattern); no hard cutover.
4. **Default guards = adopted:** every audience always excludes **banned** users and excludes
   **staff** (owner/moderator) unless an explicit `include role=…` rule names them — preserving the
   current broadcast behavior. Applies to ads and broadcasts. *(Drives the C1 truth table.)*
5. **Internal metadata scope = ads only** for now (broadcasts can adopt later via the shared entity).
6. **Draft approach = serialize `WizardState` later** (§4.7); the early-persist `draft` entity stays a
   documented alternative. Only shapes `WizardState` now; nothing built this sprint.
7. **Sequencing = the C1→C9 order** (Owner: "continue with the approved checkpoint sequence").

### C1 implementation note (test strategy for invariant #17)

The SQL-compiler↔Python-matcher equivalence (§6, Owner #17) is proven by a **shared truth table**:
a matrix of (rule set × mode) against synthetic users with expected membership. The **Python
matcher** is asserted against it directly (unit); the **SQL compiler** is asserted against the *same*
table via an **integration test on the existing Postgres test DB** (no new dependency — an
in-memory SQLite path would require adding `aiosqlite`, which is gated by Hard Rule 3). This honors
"no new dependency" while still proving real-SQL equivalence. Heed the documented Postgres test
gotchas (settings drift, live-worker queue drain) when running the integration suite.

## 10. What I will NOT do until you approve

- No migration, model, or schema change (C2 blocked on D-055; C4 blocked on D-056 + D-058).
- No edit to the LOCKED `MASTER_PLAN.md` (the D-055/D-056/D-057/D-058 drafts above stay in this doc
  until you approve them; only then do they go into §5/§23).
- No new dependency, settings key, or env var (none are needed by this design; if that changes I
  stop and ask — Hard Rules 3 & 5).
- No removal of the existing `key=value` admin commands (they remain the scriptable surface).

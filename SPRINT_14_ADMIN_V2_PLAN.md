# Sprint 14 — Admin Panel V2: History, Ads, Broadcast, Templates

Implementation plan for the Owner's V2 request list (History fixes, Broadcast/Ads
management, Ad statistics, placements, audience, message templates). Written to be
executed top-to-bottom by an implementing agent (Opus) with no other context.

---

## 0. Ground rules (read first)

- **Work in this worktree** (`happy-bose-71ed46`, branch `claude/happy-bose-71ed46`).
  There are **uncommitted changes** here that already implement part of this request
  (history titles, caption ads, language-first create, broadcast drafts). **Do not
  revert or redo them.** First action: run the test suite, then commit the existing
  work as a baseline commit before starting new work.
- Verify loop: `.venv\Scripts\python.exe -m pytest tests/unit -q` · `ruff check .` ·
  `mypy` on changed files. Unit tests must stay green after every phase.
- DB: app never self-migrates. New migrations continue after head `202607080002`
  (use `2026070900NN` ids). Apply with `.venv\Scripts\python.exe -m alembic upgrade head`.
- Architecture invariants (MASTER_PLAN §9.1, §14.2):
  - Handlers never contain business logic or authz decisions — parse → delegate to a
    service → format. Panel authz comes from `PanelFilter` + `bot/panel/registry.py`.
  - Every new panel action code must be considered in `bot/panel/registry.py`:
    read/navigation actions go in `READ_ACTIONS`; anything mutating (or leading to a
    mutation) is left unlisted → defaults to WRITE (owner-only). **Fail-safe default:
    when unsure, do not add to `READ_ACTIONS`.**
  - Callback data is signed and ≤64 bytes (`bot/callbacks/factory.py`). Use short
    action codes + small int args (registry indices), never raw strings.
  - i18n: every new user/admin-visible string gets a key in **both**
    `core/locales/en.json` and `core/locales/ar.json` (a parity test enforces this).
    Owner-authored content (ad text, broadcast bodies) is never translated.
  - Language lists are **data-driven** from `core.i18n.list_enabled_locales()`
    (returns `LocaleMeta` with `code` and `native_name`). Never hardcode `("en","ar")`
    in new code — new locales must appear with zero code changes. (Existing hardcoded
    en/ar grouping in the uncommitted broadcast list is refactored in Phase 3.)
- Panel text is rendered through `bot/panel/ui.py` primitives (`ui.header`, `ui.card`,
  `ui.metric`, `ui.footer`) — match that style for every new screen.
- After finishing: `graphify update .` and update `PROJECT_PROGRESS.md`.

### Decision points already resolved (Owner-approved defaults)

These were flagged to the Owner with recommendations; implement the recommended
option unless the Owner has said otherwise in the conversation:

| # | Question | Approved default |
|---|----------|------------------|
| D-1 | What replaces "Done — here is your file"? | **Delete** the progress message on completion (no final text at all). Fallback: if delete fails, edit to `✅`. |
| D-2 | Button clicks are untrackable on URL buttons | **Owner decided (2026-07-09): keep plain URL buttons.** Telegram fires no callback for URL buttons, so per-button click counts are technically impossible — the "button clicks" stat is **deferred**. Stats show impression-based metrics; click/CTR fields render `—` (or the legacy counter value for old callback-era ads). Do NOT add a tracked mode, `button_mode` column, or any button-rendering change. |
| D-3 | "Times Sent" vs "Times Displayed" semantics | Sent = broadcast fan-out deliveries (sum of `total_sent` on broadcasts linked to the ad). Displayed = placement impressions (`advertisements.impressions`, repeat views counted — already non-unique). Telegram cannot observe an actual render, so "displayed" = successfully delivered at a placement. |
| D-4 | History ad on the re-download fallback path | Fire the HISTORY placement ad **only after a cached resend** (`ResendKind.RESENT`). When the resend falls back to a fresh download (`REQUEUED`), the normal post-download ad hook already fires — showing both would double-ad the user. |
| D-5 | Audience excludes | The Audience page shows **exactly** the Owner's list (All / Free / Premium / Moderators / Owner / Specific User ID). Exclude toggles are removed from the UI; existing stored audience expressions keep working (read path unchanged). |
| D-6 | Broadcast Create buttons | Unify with Ads: single **Create** → language chooser (replaces the English/Arabic buttons) — pending Owner approval in Phase 8; **do not do this until approved** (it is listed as proposal P-1). Until then leave Broadcast create buttons as-is. |

---

## Phase 0 — Baseline: verify the uncommitted work, commit it

1. Run `pytest tests/unit -q`, `ruff check .`. Fix nothing yet — just confirm green.
2. Commit everything currently uncommitted as one baseline commit
   (`feat(wip): history titles, caption ads, language-first create, broadcast drafts`).
3. Verify (read, don't rewrite) that these already work — they are prerequisites:
   - **History titles (req 1.1)**: `downloads.title` column exists (migration
     `202607080001`), `DownloadService`/`JobService` persist the media title, and
     `bot/handlers/history.py::_render` shows `title · quality` with a platform emoji.
     Old rows (pre-migration) have `title = NULL` and fall back to the format string —
     acceptable; they cannot be backfilled (metadata was never stored).
     Confirm a **new** download stores its title (unit test exists in
     `tests/unit/test_history_handler.py` / `test_download_handler.py`).
   - **Caption ads (req 5.4)**: `AdPlacement.CAPTION`, `services/caption_ad_mixer.py`,
     wired into `JobService._caption_addon` (new downloads), `HistoryService.resend`
     (history), and the cached-download path in `DownloadService`. Confirm all three
     call sites exist; if the cached-delivery path in `download_service.py` does NOT
     run the mixer, add it (same pattern as `history_service._caption_addon`).
   - **Broadcast drafts**: `BroadcastService.create_draft` / `publish_draft` /
     `list_saved`, status `draft|pending|completed`, detail screen with Publish.
   - **Ads `target_language`** (migration `202607080002`) + language filter in
     `AdService._select_due_ad`.

---

## Phase 1 — History (req 1.2, 1.3)

### 1.1 Move the History ad to after item delivery (req 1.2)

Current: `bot/handlers/history.py::handle_history` calls `show_placement_ad(...,
AdPlacement.HISTORY)` right after listing (lines ~72-73). Remove that.

New behavior — in `handle_resend`, after a successful cached resend only (D-4):

```python
if outcome is ResendKind.RESENT:
    await notification_service.notify_completed(...)   # becomes delete, see 1.2
    await show_placement_ad(ad_service_factory(session), user, AdPlacement.HISTORY.value)
```

- `handle_resend` needs `ad_service_factory` injected (same optional workflow-data
  pattern `handle_history` uses today).
- Remove the now-unused `ad_service_factory` parameter from `handle_history` and its
  wiring **only if** no other placement remains there (HOME stays in `start.py`).
- Flow check (must hold): `/history` → list (no ad) → user taps item → media sent →
  ad. `NEEDS_RELINK` / `NOT_FOUND` / `REQUEUED` outcomes show **no** history ad.
- Update `tests/unit/test_history_handler.py`: assert no ad on `/history`, ad fires
  after RESENT, no ad on the other outcomes.

### 1.2 Remove "Done — here is your file" everywhere (req 1.3)

The string exists only as `notification.completed` in `core/locales/en.json` /
`ar.json`, sent by `NotificationService.notify_completed`
(`services/notification_service.py:82`) from three call sites
(`download_service.py:483`, `job_service.py:271`, `history.py:123`).

Implement D-1:
- Add `delete_message(chat_id, message_id)` to `MessageSenderProtocol`
  (`domain/protocols/file_sender.py`) and its aiogram implementation
  (`infrastructure/telegram/` — find the class implementing the protocol).
- `notify_completed` → try `delete_message`; on failure fall back to editing the
  message to `"✅"` (no words). Keep the method name (call sites unchanged).
- Delete `notification.completed` from **both** locale files (parity test).
- Grep the whole repo for `here is your file` / `إليك ملفك` afterwards — zero hits.
- Update any unit tests asserting the old edit text.

---

### 1.3 Rich history screen (P-7 Tier A — Owner approved 2026-07-09)

Upgrade the `/history` message toward the Owner's mock: detail lines per item,
audio/video filters, compact numbered buttons. All in-chat (HTML + inline keyboard);
the Mini App tier stays a Phase-8 proposal.

**Data.** Migration `2026070900NN`: add `duration_seconds` (Integer, nullable) and
`size_bytes` (BigInteger, nullable) to `downloads`. Persist them wherever `title` is
persisted today (the `202607080001` change is the template — the same
`DownloadService`/`JobService` delivery paths know duration and file size; cover the
cache-hit path too). Old rows stay NULL and their line simply omits those segments.

**Repository.** `list_for_user` gains `format_filter: str | None` (`audio`/`video` →
filter on `downloads.format`; None = all). Add `count_by_format(user_id) ->
dict[str, int]` (one grouped query) for the filter-button counts. Update the protocol
+ `_fakes.py`.

**Service.** `HistoryService.list_history(user_id, page=0, format_filter=None)`;
`HistoryPage` gains `format_filter`, `audio_count`, `video_count`.

**Rendering** (`bot/handlers/history.py::_render`): header + subtitle
(`history.header` / new `history.subtitle`), then per item two lines:

```
1. Red Bull SIKA
   🕐 01:52 · 1.9 MB · mp4 · 144p · ▶️ YouTube
```

- Duration `MM:SS` (reuse/copy `_format_duration` from `bot/handlers/download.py`),
  size humanized (`KB`/`MB`, one decimal), format, quality, platform emoji + name
  (emoji map exists). Skip any NULL segment cleanly (no dangling `·`).
- Footer: `💡 history.tip` ("Tap a number to get it again.") and the existing
  30-day retention note if present.

**Keyboard** (`bot/keyboards/history.py::build_history_keyboard` — rebuild):
- Row 1: `🎧 Audio only · N` / `🎥 Video only · N` — toggles; the active filter shows
  a ✓ and tapping it again returns to All. Callback action `h` with a packed arg.
- Item buttons: labels `1`…`7` in rows of 4, each carrying the existing resend
  callback `r|<download_id>` (number = position on the current page).
- Nav row: `◀`/`»` prev/next (same packed arg), then `Back` — Back **deletes the
  history message** (closes it); new tiny callback action `hx`.
- **Packed arg** for `h`: `arg = filter_index * 100 + page` (0=all, 1=audio,
  2=video); one `encode`/`decode` helper shared with the Phase 3 broadcast pager —
  put it in a small shared module (e.g. `bot/callbacks/paging.py`), don't duplicate.
- Page size stays the `history_page_size` setting (default 7 matches the mock).

**i18n**: `history.subtitle`, `history.tip`, `history.filter_audio`,
`history.filter_video`, `history.close` (en + ar).

**Tests**: `test_history_handler.py` + `test_keyboards.py` — filtered listing,
counts, packed-arg round-trip, NULL duration/size rendering, Back deletes, and the
Phase-1.1 assertions (ad only after RESENT) still green.

---

## Phase 2 — Ads section restructure (req 3.1, 3.2, 3.3)

Target UX:

```
Ads menu:            [ List ] [ Create ] [ Statistics ] [ Placements ] [ Back ]
Create   → language chooser (data-driven) → compose wizard (existing)
List     → language categories → ads of that language → tap ad → management page
Management page → Edit / Enable|Disable / Delete / Statistics / Broadcast / Back
```

### 2.1 Single Create button with in-flow language choice (req 3.1)

- In `bot/panel/registry.py` `SUBMENUS["a"]`: remove `cen` / `car` items and the
  top-level `ed`/`en`/`di`/`de` items. New menu: `List` (`ls`), `Create` (`cr`),
  `Statistics` (`stt`), `Placements` (`pl` — Phase 5).
- New action `cr` (WRITE): renders a language-chooser screen. Buttons generated from
  `list_enabled_locales()` — label `meta.native_name`, callback `("a", "crl", index)`
  where `index` is the position in `list_enabled_locales()` order. Plus Back.
- New action `crl` (WRITE): resolves `index → locale.code`, then calls the existing
  `admin_wizard.start(..., kind="ad", target_language=code)` (exactly what `cen`/`car`
  do today in `admin_panel.py::panel_write` lines ~265-271). Guard: index out of
  range → `callback.answer()` silently.
- Keyboard builder: `build_language_chooser(section, action, signer, locale)` in
  `bot/keyboards/admin_panel.py` — **shared** with Broadcast (Phase 3) and the ads
  List (2.2). One builder, parametrized by section + follow-up action.
- i18n keys: `panel.ads.create_pick_language` (+ ar). Remove
  `panel.menu.a.create_en` / `panel.menu.a.create_ar` keys.

### 2.2 Language-first ads list (req 3.2)

- `a`/`ls` (READ, exists) now renders the **language category screen**, not the flat
  list: one button per enabled locale (`native_name + count`), plus one
  `🌐 All languages` bucket for ads with `target_language IS NULL` (legacy /
  deliberately untargeted), plus Back.
- New READ action `lsl` with `arg = locale index` (`-1`/sentinel `arg=None`… use
  index `len(locales)` for the NULL bucket): lists ads filtered by language, each row
  opening `("a", "inf", ad_id)` (existing detail action).
- Repository: add `list_by_language(language: str | None)` to
  `infrastructure/database/repositories/advertisement.py` + protocol
  (`domain/protocols/repositories.py`); `AdService.list_ads(language=...)` passthrough.
- If a language has >10 ads, paginate with the same prev/next pattern built for
  broadcasts in Phase 3 (share the helper).
- Register `lsl` in `READ_ACTIONS`.

### 2.3 Management page = the ad detail screen (req 3.3)

`build_ad_detail` (`bot/keyboards/admin_panel.py:375`) already shows
Enable|Disable / Broadcast / Delete. Extend (owner-only rows):

- **Edit** → `("a", "ed", ad_id)` — already implemented in `panel_write`
  (`start_edit` loads the ad into the compose wizard). Just add the button.
- **Statistics** → `("a", "ast", ad_id)` (new READ action) → per-ad stats screen
  (Phase 4).
- Back → returns to the language list the admin came from. The detail screen doesn't
  know the origin language; simplest correct fix: Back goes to `("a", "ls")` (the
  category screen). Acceptable; do not build a breadcrumb stack.
- Delete the `_AD_PICKER_ACTIONS` flow (`admin_panel.py:1651`,
  `build_ad_action_list`) once the section menu no longer offers un-targeted
  enable/disable/delete/edit — all management now starts from the detail page. Keep
  the `ed`-with-arg, `en`, `di`, `de`+confirm handlers in `_ads_write` (they are the
  detail-page actions).
- Update `tests/unit/test_keyboards.py` + `test_admin_panel_handler.py`.

---

## Phase 3 — Broadcast: language filter, pagination, actions (req 2.1–2.3)

Target UX:

```
Broadcast menu: [ Create EN ] [ Create AR ] [ Saved ]     (create unchanged until P-1 approved)
Saved → language chooser (data-driven, + "All/untagged") → paginated list (5/page)
      → tap broadcast → detail: [ Publish ] [ Edit ] [ Delete ] [ Back ]
```

### 3.1 Language filter before the saved list (req 2.2)

- `b`/`ls` (READ) renders the shared `build_language_chooser` (from 2.1) with
  follow-up action `lsl` + an untagged bucket, replacing the current single grouped
  list (`_broadcast_list_text` / `build_broadcast_list` currently hardcode en/ar —
  delete that grouping).
- New READ action `b`/`lsl` `arg=<locale index>`: paginated list for that language.

### 3.2 Pagination (req 2.1)

- Repository (`infrastructure/database/repositories/broadcast.py`): change/extend
  `list_all()` → `list_saved(language: str | None, *, limit: int, offset: int)` and
  `count_saved(language: str | None)`. Filter `target_language = :lang` (or `IS NULL`
  for the untagged bucket). Newest first. Update the protocol.
- `BroadcastService.list_saved(language=None, page=0, page_size=5)` returns a small
  page dataclass (`rows`, `page`, `has_prev`, `has_next`) — mirror
  `HistoryPage`/`HistoryService.list_history` (`services/history_service.py:92`).
- Callback encoding problem: `lsl` needs *language + page* but a signed callback has
  one small int arg. Encode as `arg = language_index * 100 + page` (page < 100,
  language count tiny) — decode with `divmod(arg, 100)`. Document this at the
  encode/decode site; write both in one helper (`encode_lang_page`/`decode_lang_page`)
  so they cannot drift.
- Keyboard: rows of broadcasts (existing `_broadcast_button_label`), then a
  `◀ Prev / Next ▶` row when applicable, then Back (to the language chooser).
- i18n: `panel.broadcast.pick_language`, `panel.nav.prev`, `panel.nav.next` (check —
  history keyboards already have prev/next labels; **reuse those keys** if present).

### 3.3 Broadcast detail actions (req 2.3)

`build_broadcast_detail` (`bot/keyboards/admin_panel.py:440`) currently shows only
Publish-for-drafts. New layout (owner-only; the whole section is owner-only already):

- **Publish** (`pbd`, exists) — drafts only. Route through a **confirm screen** first
  (use the existing `build_confirm` pattern: `pbd` renders confirm, new `pbc` action
  executes). Publishing must never be one tap (Owner: "publishing should only happen
  after pressing Publish" — a confirm additionally protects fat-fingers; it matches
  the Delete/Broadcast-ad pattern `_AD_CONFIRM` in `admin_panel.py`).
- **Edit** (`bed`, new WRITE) — drafts only. Loads the draft into the compose wizard
  the same way ads `start_edit` does: add `admin_wizard.start_edit_broadcast(...)`
  that seeds `WizardState` (kind=`broadcast`, content text, target_language, audience
  rules from its `audience_expression_id`) and jumps to `STEP_PREVIEW`. On save,
  **update the existing draft row** instead of creating a new one: add
  `BroadcastService.update_draft(broadcast_id, message_text=..., audience_...)` +
  repo `update_draft` (re-snapshot `expected_total`, replace expression). The wizard
  state needs an optional `editing_broadcast_id` field (mirror how ad edit carries
  `editing_ad_id` — check `bot/panel/wizard.py::WizardState`).
- **Delete** (`bde` → confirm → `bdc`, new WRITE) — allowed for `draft` and
  `completed` (history cleanup); **refuse for `pending`/`in_progress`** (worker may
  be mid-fan-out) with an alert toast. `BroadcastService.delete_broadcast(id)` +
  repo delete.
- **Back** → the language list.
- Non-draft statuses show no Publish/Edit (completed shows Delete + Back).
- Tests: `test_admin_panel_handler.py` (detail renders per status; publish confirm;
  delete refusal for pending), service tests for `update_draft`/`delete_broadcast`.

---

## Phase 4 — Ad statistics (req 4, 4.1)

### 4.1 Data layer

Counters that already exist and are **non-unique** (repeat views count — req 4.1
already satisfied; verify, don't change): `advertisements.impressions`, `.clicks`,
`ad_buttons.clicks`, `advertisements.last_shown_at`, `.created_at`, and the
partitioned `ad_events` table (`event_type`, `placement`, `button_id`, `created_at`).

Add:
- Migration `2026070900xx`: index on `ad_events (advertisement_id, event_type)`
  (aggregation queries below hit it). Note: `ad_events` is RANGE-partitioned —
  create the index on the parent table (partitioned index).
- Repo aggregates (advertisement repo or a small new `ad_stats` repo module):
  - `impressions_by_placement(ad_id) -> dict[str, int]` (GROUP BY placement).
  - `broadcast_totals_for_ad(ad_id) -> (times_sent, last_sent_at)` — from
    `broadcasts` where `advertisement_id = :id`: `SUM(total_sent)`,
    `MAX(completed/finished timestamp)` (check the broadcast model's actual
    finished-column name).
  - `buttons_with_clicks(ad_id)` — exists as `list_for_ad` (has `.clicks`); reuse.
- `AdService.detailed_stats(ad_id) -> AdDetailedStats` dataclass:
  `title, internal_name, is_active, created_at, times_sent (D-3), impressions_total,
  impressions_by_placement, clicks_total, ctr, last_shown_at, last_sent_at,
  buttons: [(text, clicks)]`.

### 4.2 Button clicks — deferred (D-2: keep plain URL buttons)

Owner decision: ad buttons stay **plain URL buttons** (`AdService._build_buttons`,
`services/ad_service.py:330`) — direct open, no extra tap. Telegram fires no callback
for URL buttons, so per-button click counting is not possible and req 4's "button
click counts" line is **deferred** (revisit only if the Owner later opts into a
tracked mode).

- **No code change** to button rendering; no `button_mode` column; no wizard toggle.
- Keep the existing click plumbing intact but dormant (`handle_ad_click`,
  `record_click`, `ad_buttons.clicks`, ad_events click rows) — legacy callback-era
  ads may still feed it, and it is the ready-made hook for a future tracked mode.
- Stats screens (4.3): the buttons block lists each configured button with its click
  counter as-is; for URL buttons this stays 0/`—`. Render CTR as `—` when clicks are
  0 and add a one-line footnote i18n key (`panel.ads.stats.clicks_note`) explaining
  that direct-link buttons cannot report taps.

### 4.3 Stats screens

- **Per-ad screen** (`a`/`ast`, READ, from the management page): `ui.card` with all
  `AdDetailedStats` fields — name, times sent, times displayed (total + per-placement
  lines), button clicks (one line per button: `text — N clicks`), CTR, created date,
  last sent/shown. Dates via the existing `_fmt_dt` style.
- **Overall screen** (`a`/`stt`, exists — `_overall_stats_text`): keep totals
  (Total / Active / Views / Clicks / CTR); beneath, one compact row per ad
  (`#id title — sent X · shown Y · clicks Z`) so the Owner sees per-ad numbers at a
  glance; each could be reached via List → ad → Statistics (no buttons needed here).
- i18n keys under `panel.ads.stats.*` (en + ar).

---

## Phase 5 — Independent, configurable placements (req 5)

### 5.1 Placement inventory (after this phase)

| Placement | Enum code | Trigger point | Status |
|---|---|---|---|
| Analysis Ad | `analysis` (**new**) | after URL analysis / chooser message | **new call site** |
| Quality Ad | `quality_select` (exists) | after the user picks a quality | **wire it** (enum exists, never triggered) |
| History Ad | `history` (exists) | after a cached resend (Phase 1) | done in Phase 1 |
| Caption Ad | `caption` (exists) | inside media caption (new/cached/history) | verify Phase 0 |
| Post-download | `post_download` (exists) | after delivery (reply to media) | keep as-is |
| Home | `home` (exists) | after /start | keep as-is |

- Add `ANALYSIS = "analysis"` to `domain/enums/ad_placement.py` and
  `PlacementOption(7, "analysis", "panel.placement.analysis")` to
  `bot/panel/registry.py::PLACEMENT_OPTIONS` (**append — indices are stable ids**).
- Call sites (both use the existing best-effort `show_placement_ad` helper from
  `bot/handlers/ads.py`, injected `ad_service_factory` pattern from `history.py`):
  - `bot/handlers/download.py::handle_url` — after the analysis result/chooser
    message is sent (success path only) → `AdPlacement.ANALYSIS`.
  - `bot/handlers/download.py::handle_quality_choice` — after the choice is accepted
    and the job is enqueued/cache-served → `AdPlacement.QUALITY_SELECT`.

### 5.2 Per-placement enable/disable UI

`AdService._placement_enabled` already gates every placement on the
`ad_placement_<code>_enabled` settings key; unseeded keys default to ON only for
`post_download` + `caption`.

- Migration: seed `ad_placement_<code>_enabled` bool settings rows for **all**
  placements (`post_download=true, caption=true, others=false` — preserves current
  behavior; description text for each). Settings writes require existing rows
  (`SettingsService.set_validated` raises on unknown keys), which is why seeding is
  required.
- New Ads-menu screen **Placements** (`a`/`pl`, READ to view; toggle action `plt`
  WRITE with `arg = PLACEMENT_OPTIONS index`): one row per placement —
  `✅/❌ <label>` button that flips the setting via
  `SettingsService.set_validated(key, "true"/"false", updated_by=owner)` and
  re-renders. Include a `caption` row and an `analysis` row.
- This screen is the **placement master switch** layer; the per-ad Enabled toggle and
  per-ad placement targeting stay as they are (two independent layers, both required
  to show an ad).
- Tests: toggle write path + `_placement_enabled` respects seeded rows.

---

## Phase 6 — Audience page (req 6, D-5)

File: `bot/panel/registry.py::AUDIENCE_OPTIONS` + wizard toggle logic in
`bot/handlers/admin_wizard.py` (`_toggle_audience`, `_collapse_all_users`,
`_recompute_audience_mode`) + keyboard `build_wizard_audience`.

Replace `AUDIENCE_OPTIONS` with exactly (indices restart — the options are only
referenced by live wizard callbacks, never persisted, so renumbering is safe;
**verify** nothing persists option indices, only concrete rules):

```
0  panel.audience.all        include  (pseudo-option: clears all rules → mode ALL)
1  panel.audience.free       include  plan   free
2  panel.audience.premium    include  plan   premium
3  panel.audience.moderators include  role   moderator
4  panel.audience.owner      include  role   owner
5  panel.audience.user_id    include  user_id  (typed sub-input)
```

- **Language option removed** (language is chosen at Create; the wizard already
  carries `target_language`). Remove the `panel.audience.language` keys.
- **Exclude options removed from the UI** (D-5). Keep the audience engine's exclude
  support intact (`AudienceService`, expressions) — old expressions must still match.
- **Default = All Users**: with zero selected rules the wizard must produce
  `audience_mode="all"` with no rules. `_collapse_all_users` /
  `_recompute_audience_mode` likely already do this — verify and add a unit test:
  “no audience selection → broadcast/ad targets everyone”.
- **Specific User ID**: selecting it arms the typed input (existing `value=None`
  machinery); with a user-id rule present the message goes only to that user.
  Add/verify test: audience with one `user_id` include matches exactly that user.
- "All Users" as a real button: tapping it clears every audience rule and re-renders
  (selected state ✓ when no rules). Implement in `_toggle_audience`.
- The audience preview / recipient estimate (`estimate_recipients`) keeps working
  unchanged.
- Update `tests/unit/test_admin_wizard.py` for the new option set.

---

## Phase 7 — Message Templates (req 7)

Files: `services/template_service.py`, panel section `tp`
(`admin_panel.py:1345-1495`, `build_template_list`/`build_template_detail`),
`infrastructure/database/models/message_template.py` + repo.

### 7.1 Fix the missing/broken templates (investigate first — this is a bug hunt)

Finding from planning: `user.banned` and `system.maintenance` have **no send sites**
in `bot/` — the templates are editable but likely never delivered.

1. Trace how a banned user and maintenance mode are actually handled (grep middlewares:
   `bot/middlewares/` — there is presumably a ban/maintenance gate). Confirm whether
   the user gets *any* message.
2. Wire the real sends: banned users receive `translate("user.banned", locale,
   reason=...)`; when `maintenance_mode` is on, non-staff receive
   `translate("system.maintenance", locale)`. Because `TemplateService` mirrors
   overrides into `core.i18n`, sending via `translate(...)` automatically picks up
   admin-edited text — that is the whole point; **do not** read TemplateService
   directly at send time.
   Rate-limit the banned/maintenance reply (once per N minutes per user — reuse the
   existing rate-limit/cooldown infrastructure) so a banned user spamming the bot
   doesn't generate a message per update. Keep it simple: an in-memory TTL set in the
   middleware is acceptable.
3. Audit each of the 9 `TEMPLATE_DEFS` i18n keys: confirm each key is actually used
   by the code path it names (`user.welcome`, `user.help`, `download.started`,
   `download.complete`*, `download.failed`, `limit.daily_reached`, `limit.cooldown`,
   `user.banned`, `system.maintenance`). *Note `download.complete` — after Phase 1
   the completion message is deleted, so this template is dead; **remove it from
   `TEMPLATE_DEFS`** (and its panel row) or repurpose — removing is correct per
   req 1.3. Fix any other key that is defined-but-never-sent.

### 7.2 Accurate "Current content" + placeholder help (req 7)

`_template_detail_text` (`admin_panel.py:1355`) currently shows an 80-char preview
(`TemplateView.content_preview`). Replace with:

- `TemplateService.full_content(key, locale) -> str`: the **exact** stored custom
  content, or the i18n catalog default (`i18n.catalog_template`) when not customized.
  Show it verbatim (escaped) in a `<blockquote>` — never truncated, never rendered
  with substituted values (the admin must see the raw `{placeholders}`).
- Below it, a **placeholder legend**: extend `TemplateDef` with
  `placeholder_help: tuple[tuple[str, str], ...]` — `(placeholder, example)` pairs;
  descriptions come from i18n keys `panel.templates.ph.<name>`
  (e.g. `{first_name}` → "User's Telegram first name", example "Andrew"). Render:
  ```
  {first_name} → User's Telegram first name (e.g. Andrew)
  ```
- Below that, an **"Example result"** block: the template rendered with the example
  values (`str.format`-safe: wrap in try/except and show a warning line if the admin
  saved a template with an unknown placeholder).
- Edit validation (probably exists in `on_template_edit` — verify): reject content
  whose placeholders are not a subset of the template's declared placeholders, with a
  friendly message listing the allowed ones.

### 7.3 Buttons — fixed everywhere except Banned + Maintenance (req 7)

- Migration: add `buttons` JSONB (nullable) to `message_templates`
  (list of `{"text": str, "url": str}` rows; one button per row, max 3).
- `TemplateDef` gets `allow_buttons: bool` — `True` only for `banned_message` and
  `maintenance`.
- Template detail screen (only when `allow_buttons`): current buttons listed +
  `Edit buttons` (WRITE) arming a typed input — format `Text | https://url` per line,
  empty message = clear. Parse/validate URL scheme (http/https only), store.
- `TemplateService`: cache `(key, locale) -> buttons`, expose
  `buttons_for(i18n_key, locale)`; the banned/maintenance send sites (7.1) attach
  them as URL inline buttons.
- All other templates: no button UI whatsoever (their send sites keep hardcoded
  keyboards).
- Tests: service round-trip, parse/validation, detail render with/without buttons.

---

## Phase 8 — UX proposals (DO NOT IMPLEMENT — present for Owner approval)

Owner instruction: propose, explain, wait. Present these in the final report; touch
no code for them.

- **P-1 Unify Broadcast Create with Ads Create**: single `Create` → language chooser
  (identical flow, shared keyboard). Why: one mental model for both sections; adding
  a locale then requires zero menu changes anywhere. (Currently Broadcast still has
  per-language create buttons.)
- **P-2 Draft-first publishing for Ads broadcasts too**: "Broadcast this ad" from the
  ad page currently queues immediately after one confirm; a draft it could share the
  broadcast detail page (Publish/Edit/Delete) for full parity.
- **P-3 Scheduled publish in the broadcast detail**: `scheduled_at` exists end-to-end
  (service + worker); a `Schedule…` button next to Publish (typed `YYYY-MM-DD HH:MM`)
  exposes it in the panel instead of only via the legacy `/ad_broadcast --at`.
- **P-4 Ad internal names in admin lists**: `internal_name` exists (D-058) but lists
  show public titles; showing `internal_name or title` helps the Owner manage many
  similarly-titled campaigns.
- **P-5 History screen**: add a per-row 🗑 delete (users asking to clear history is a
  common SaaS support request) — needs soft-delete or row delete on `downloads`.
- **P-6 Stats time windows**: per-ad stats "last 7 / 30 days" toggles using
  `ad_events.created_at` (the data is already partitioned by month for exactly this).
- **P-7 History Mini App** (Tier B of the Owner's 2026-07-09 mock; Tier A was
  **approved** and is now Phase 1.3). The exact card visuals (icons, badges, layout)
  need a Telegram Web App: static frontend + authenticated history endpoints on the
  existing FastAPI process (`api/` currently serves only health/metrics), `initData`
  HMAC validation, public HTTPS hosting, and an `Open in Mini App` `web_app` button.
  Real scope: new deploy surface, auth, CORS/CSP, i18n on the web side. Recommend
  scoping as its own V2/V3 item (fits the V3 Bot Factory direction) — do not start.

---

## Cross-cutting checklists

### Migrations (in order, `2026070900NN_*`)
1. `downloads.duration_seconds` + `downloads.size_bytes` (nullable, Phase 1.3).
2. `ad_events` index `(advertisement_id, event_type)` (partitioned parent).
3. Seed `ad_placement_*_enabled` settings rows (all placements incl. `analysis`).
4. `message_templates.buttons` JSONB nullable.

### New/changed panel actions (registry review — security-critical)
- READ (add to `READ_ACTIONS`): `lsl` (ads + broadcast language lists share the
  code), `ast` (per-ad stats), `pl` (view placements screen).
- WRITE (do **not** list): `cr`, `crl`, `plt`, `pbc`, `bed`, `bde`, `bdc`,
  template-button edit action.
- Every new action gets a `PanelFilter` routing test in
  `tests/unit/test_admin_panel_handler.py` (moderator gets silence on WRITE actions).

### i18n
- All new keys in `en.json` **and** `ar.json`; run the parity test; remove dead keys
  (`notification.completed`, `panel.menu.a.create_en/ar`, `panel.audience.language`,
  exclude-option labels, `download_complete` template strings if removed).

### Tests to touch (minimum)
`test_history_handler.py`, `test_download_handler.py`, `test_admin_panel_handler.py`,
`test_admin_wizard.py`, `test_keyboards.py`, `test_ad_service_v2.py`,
`test_template_service*.py`, `tests/unit/_fakes.py` (new repo/protocol methods),
plus new tests named in each phase.

### Suggested commit sequence
One commit per phase (0–7), each with green `pytest tests/unit -q` + `ruff` + `mypy`
on changed files. Push to remote `second` (origin is 403).

### Definition of done
- Every numbered Owner requirement 1.1–7 maps to a phase above and is demonstrably
  working (manual flows listed in each phase).
- Phase 8 items are **reported, not implemented**.
- `graphify update .` run; `PROJECT_PROGRESS.md` updated with a Sprint 14 section.

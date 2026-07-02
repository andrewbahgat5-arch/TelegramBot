# Sprint 11.5 — Internationalization (i18n) — Implementation Review Brief

> **Purpose of this document:** a self-contained handoff for an independent reviewer (human or AI)
> to verify that the localization system described below was actually implemented correctly,
> completely, and without regressions. Everything here is checkable against the live repository
> state — file paths, function names, and numbers are exact, not paraphrased. Nothing has been
> committed to git yet (see "Commit status" at the end) — all changes are in the working tree of
> the worktree at `J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46`
> (branch `claude/happy-bose-71ed46`).

---

## 1. What was requested

The Owner asked to continue the project toward Sprint 12 (Launch Readiness), then supplied a
full localization specification mid-session:

- Support English + Arabic now, architected for unlimited future languages.
- All application UI localized (menus, buttons, progress, errors, notifications, help, premium
  messages, queue messages, admin/moderator/statistics/broadcast/settings screens).
- User-generated content (ad bodies, broadcast bodies, video titles, platform names, filenames)
  must **never** be translated — only application chrome.
- Adding a future language must require **only** a new translation file, never a business-logic
  change.
- No hardcoded strings anywhere in handlers/services — everything through a localization
  provider.
- RTL support for Arabic.
- Admin panel must be localized (Owner sees his own selected language; only dynamic content
  stays unchanged).
- No schema redesign — reuse the existing `users.language` field.

This was **originally out of scope for V1** (`MASTER_PLAN.md` §2.4 reserved "Multi-language
interface" for V2). Asked directly, the Owner chose to pull it forward into V1, ahead of the
remaining Sprint 12 launch-ops work.

The design then went through **three rounds of Owner simplification** during review (this
matters for a reviewer — some early assumptions in the codebase's git history / plan file are
superseded by later rounds; the design in §2 below is the **final, approved, implemented**
version only):

1. Round 1 replaced an initial "first-contact language picker gate" idea with: every user
   defaults to English immediately, no forced choice; a permanent "Change Language" button
   changes it anytime, applied instantly, no restart.
2. Round 2 simplified further: dropped a planned `/language` command (button-only) and dropped
   storing the supported-language list in the `settings` database table (discovered from the
   filesystem instead).
3. Round 3 added the `_meta.version` field, the "default locale is the reference catalog, no
   orphaned keys" invariant, the "never overwrite a user's stored locale on fallback" guarantee,
   and the "`_` prefix is reserved for metadata only" rule.

## 2. Final approved design (what should actually be in the code)

- **Storage:** `users.language` (existing column, BCP-47, nullable) is the **only** field used.
  `user_preferences.preferred_language` is **not** touched — deliberately left reserved/unused.
  **No database migration in this sprint.**
- **Default:** `Settings.default_locale` (new field, env var `DEFAULT_LOCALE`, default `"en"`).
  A brand-new user's `users.language` is set to this value at creation — **never** from
  Telegram's auto-detected `language_code` (that value isn't restricted to languages the bot
  actually catalogs, so it would be untrustworthy as a UI locale).
- **Catalog discovery:** supported languages are discovered from `core/locales/*.json` files at
  startup — **not** stored in the `settings` table. Adding a language = add one file with
  `_meta.enabled: true`. No code or schema change.
- **Catalog contract:** every file has a `_meta` block:
  `{"code": "en", "native_name": "English", "direction": "ltr", "enabled": true, "version": 1}`.
  `_meta` is the **only** reserved top-level key — any other key starting with `_` fails
  validation at startup.
- **Reference-catalog invariant:** the default locale's catalog is authoritative — every other
  locale's keys must be a **subset** of it. An orphaned/typo'd key in a non-default catalog fails
  startup, naming the offending key.
- **Fallback behavior:** `translate(key, locale, **kwargs)` never raises. Miss in a non-default
  locale → falls back to the default locale (logged). Miss in both → falls back to the raw key
  string (logged). Bad `.format()` placeholder → caught, logged, raw template returned.
- **Never overwrites the DB on fallback:** `resolve_locale(stored)` is read-only. A user whose
  stored locale becomes disabled (or was never valid) silently reads as the default — but the
  stored value is never rewritten. If that locale is re-enabled later, the same user
  automatically resolves back to it with zero data migration.
- **Change UX:** **no first-contact gate, no `/language` command.** A permanent
  "🌐 Change Language" inline button on `/start` (regular users) and a "🌐 Language" section in
  the admin panel (Owner/Moderator) — both render the same picker and share one apply path. A
  pick takes effect on the very next message, no restart.
- **Fan-out correctness:** one download job can have multiple waiters (`job_waiters`) in
  different languages — each recipient's locale must be resolved fresh per delivery, never one
  shared "job locale."
- **Scope boundary:** only application UI strings are localized. Ad bodies, broadcast bodies,
  video titles, platform names, filenames are interpolated as data but never translated.
- **RTL:** Telegram renders bidi text natively per message/button — no custom layout engine.
  The real requirement is that every catalog value is a whole-sentence template with named
  placeholders (`{name}`), never built by concatenating independently-translated fragments
  (fragment concatenation breaks Arabic word order).

Full rationale and every alternative considered/rejected: `MASTER_PLAN.md` decision log entries
**D-061 through D-064** (search for those IDs). The full sprint definition (goal, scope, tasks,
validation checklist, exit criteria) is `MASTER_PLAN.md` §23, section
`### Sprint 11.5 — Internationalization (i18n)`, inserted between Sprint 11 and Sprint 12.

## 3. What was implemented — by component

### 3.1 Core module (new)

- **`core/i18n.py`** (214 lines) — the catalog loader. Public API:
  `configure(default_locale, *, locales_dir=None)`, `translate(key, locale, **kwargs) -> str`,
  `resolve_locale(stored: str | None) -> str`, `list_enabled_locales() -> list[LocaleMeta]`,
  `LocaleMeta` dataclass, `LocaleCatalogError` exception, `Translator` type alias. Framework-free
  — no import of `core.config.Settings`, mirroring `core/logging.py`'s explicit
  `configure()`/`get_logger()` pattern (no import-time side effects).
- **`core/locales/en.json`** and **`core/locales/ar.json`** (new) — **333 keys each, verified
  programmatically equal** (`python -c "import json; ..."` — see §6). Covers every UI surface:
  `errors.*`, `notification.*`, `language.*`, `start.*`, `help.*`, `download.*`, `common.*`,
  `history.*`, `panel.section.*`, `panel.action.*`, `panel.menu.*`, `panel.settings.*`,
  `panel.audience.*`, `panel.placement.*`, `panel.wizard.*`, `panel.users.*`, `panel.ads.*`,
  `panel.broadcast.*`, `panel.stats.*`, `panel.jobs.*`, `panel.errors.*`, `panel.downloads.*`,
  `panel.system.*`, `admin.*`, `ads.*`.
- **`core/config.py`** — added `default_locale: str = Field("en", alias="DEFAULT_LOCALE")`.
- **`.env.example`** — added `DEFAULT_LOCALE=en` with a comment.

### 3.2 Domain layer

- **`domain/exceptions.py`** — added `UserFacingError.translation_key` property
  (`f"errors.{self.error_type.value}"`). **Deliberately did not** add a generic `params` dict to
  `AppError` — every raise site was traced first and none needed one; see D-064 for why adding
  unused "future-proofing" was rejected.

### 3.3 Services layer

- **`services/user_service.py`** — added `set_language(telegram_id, language) -> UserSnapshot | None`,
  mirroring the existing `ban`/`unban`/`set_premium` mutation pattern.
- **`services/notification_service.py`** — `send_initial`/`notify_stage`/`notify_completed`/
  `notify_failed` all now take a **required** `locale: str` and route copy through
  `core.i18n.translate`.
- **`services/download_service.py`** — `process()` resolves a `locale` for the initiating chat;
  `_notify_waiters` does a **fresh per-recipient locale lookup** for every waiter (not a single
  shared job locale) — this is the fan-out-correctness requirement from §2.
- **`services/job_service.py`** — `_try_deliver_cached` resolves the requesting user's locale
  fresh before calling `notify_completed`.

### 3.4 Bot middleware / composition roots

- **`bot/middlewares/auth.py`** — `AuthMiddleware` constructor takes `default_locale: str`
  (keyword-only); `get_or_create_user(..., language=self._default_locale)` **replaces**
  `language=tg_user.language_code`.
- **`bot/middlewares/i18n.py`** (new, 30 lines) — `LocaleMiddleware`: reads `data["user"]`,
  calls `core.i18n.resolve_locale`, injects `data["locale"]`. Positioned **after** `AuthMiddleware`
  (needs the user), **before** `ThrottleMiddleware` (its own message needs a resolved locale).
- **`bot/main.py`** — calls `i18n.configure(settings.default_locale)` at startup; injects
  `dp["translate"] = i18n.translate` once (static factory, matching the existing
  `dp["callback_signer"]` pattern); wires `LocaleMiddleware` into the chain.
- **`workers/main.py`** — also calls `i18n.configure(settings.default_locale)` at its own
  startup (a separate process needs its own configured state).

### 3.5 Callback signing + keyboards

- **`bot/callbacks/factory.py`** — new action `l`: `CallbackSigner.pack_language(code)`,
  `ParsedCallback.language: str | None`. Uses an empty-string sentinel for "open the picker" vs.
  a real code for "apply this pick" — reuses the existing signed-callback path rather than adding
  an unsigned callback.
- **`bot/keyboards/language_select.py`** (new, 40 lines) — `build_change_language_button` +
  `build_language_picker` (one button per `list_enabled_locales()`, labeled by `native_name`).
- **`bot/keyboards/{format_select,quality_select,history}.py`** — every builder now takes a
  `locale: str` and resolves labels via `translate()`. Quality/size text ("720p", "50 MB") is
  deliberately left untranslated (technical/universal).
- **`bot/keyboards/admin_panel.py`** — every builder function (`nav_row`, `build_main_menu`,
  `build_section_menu`, `build_settings_menu`, `build_setting_stepper`, `build_input_prompt`,
  `build_confirm`, `build_user_list`, `build_ad_list`, `build_ad_action_list`, `build_ad_detail`,
  `build_user_detail`, `build_wizard_*` ×6) now takes `locale` and resolves via `translate()`.

### 3.6 Handlers (regular-user surface + admin panel)

All of the following now take `translate: Translator, locale: str` and contain **zero**
hardcoded user-facing English strings:

- `bot/handlers/start.py` — rewritten; new `handle_language_callback` + `apply_language_pick()`
  (shared logic used by both entry points).
- `bot/handlers/help.py`, `bot/handlers/history.py`, `bot/handlers/download.py` — migrated.
  `download.py`'s `except UserFacingError as exc:` catch site calls
  `translate(exc.translation_key, locale)`.
- `bot/handlers/admin.py`, `bot/handlers/ads.py`, `bot/handlers/admin_panel.py`,
  `bot/handlers/admin_wizard.py` — the entire admin/ads command surface and the FSM compose
  wizard migrated. `admin_wizard.py`'s `_ad_fields()` **deliberately keeps** `"Untitled ad"` /
  `"Broadcast"` as fixed English literal fallback titles — these become persisted `ad.title`
  values (admin-facing only, never shown to end users), so translating them would make a stored
  title depend on which locale the creating admin happened to be using at that moment.

### 3.7 Admin panel registry

- **`bot/panel/registry.py`** — all six registries (`Section`, `MenuItem`, `SettingField`,
  `InfoItem`, `AudienceOption`, `PlacementOption`) renamed their `label: str` field to
  `label_key: str`, with every literal replaced by a dot-named key. New
  `Section("l", "panel.section.language")` appended.

### 3.8 Tests

- **`tests/conftest.py`** — new autouse `_configure_i18n` fixture calls `i18n.configure("en")`
  before every test.
- **`tests/unit/test_i18n.py`** (new, 235 lines, **22 tests**) — catalog validation via crafted
  `tmp_path` catalogs (malformed `code`/`direction`/`version`/stray-underscore-key all fail
  loudly), `translate()`/`resolve_locale()` fallback behavior, the never-writes-back /
  auto-recovery guarantee, and invariants against the **real shipped catalogs** (en/ar key
  parity, and a regression test scanning every real catalog value for the `{key}`/`{locale}`
  reserved placeholder names — see the bug in §5).
- Every other touched test file (`test_bot_middlewares.py`, `test_bot_handlers.py` — **5 new
  language-picker tests**, `test_download_handler.py`, `test_history_handler.py`,
  `test_keyboards.py`, `test_notification_service.py`, `test_admin_handler.py`,
  `test_ad_handler.py`, `test_admin_panel_handler.py`, `test_admin_panel_keyboards.py`,
  `test_admin_wizard.py`, `test_exceptions.py`) updated to pass `translate, locale` (or
  `"en"`) through to the (now-changed) function signatures they exercise.

## 4. Complete file manifest

**New files:**

| File | Lines | Purpose |
|---|---|---|
| `core/i18n.py` | 214 | Catalog loader / lookup |
| `core/locales/en.json` | — (333 keys) | English catalog (default/reference) |
| `core/locales/ar.json` | — (333 keys) | Arabic catalog (RTL) |
| `bot/middlewares/i18n.py` | 30 | `LocaleMiddleware` |
| `bot/keyboards/language_select.py` | 40 | Picker keyboard + change-language button |
| `tests/unit/test_i18n.py` | 235 | 22 new tests for `core/i18n.py` |

**Modified files** (41 total changed, +2,436/−894 lines; full `git diff --stat` reproduced below):

```
 .env.example                             |   5 +
 MASTER_PLAN.md                           | 146 ++++++-
 PROJECT_PROGRESS.md                      |  75 +++-
 TEST_RESULTS.md                          |  25 +-
 bot/callbacks/factory.py                 |  16 +-
 bot/handlers/admin.py                    | 131 ++++--
 bot/handlers/admin_panel.py              | 676 +++++++++++++++++++++----------
 bot/handlers/admin_wizard.py             | 293 ++++++++++----
 bot/handlers/ads.py                      | 302 +++++++++-----
 bot/handlers/download.py                 |  62 +--
 bot/handlers/help.py                     |  18 +-
 bot/handlers/history.py                  |  34 +-
 bot/handlers/start.py                    | 106 ++++-
 bot/keyboards/admin_panel.py             | 277 +++++++++----
 bot/keyboards/format_select.py           |  13 +-
 bot/keyboards/history.py                 |  19 +-
 bot/keyboards/quality_select.py          |   9 +-
 bot/main.py                              |  19 +-
 bot/middlewares/auth.py                  |  22 +-
 bot/panel/registry.py                    | 232 +++++++----
 core/config.py                           |   7 +
 domain/exceptions.py                     |  11 +
 project_reference.md                     |  79 +++-
 services/download_service.py             |  41 +-
 services/job_service.py                  |   5 +-
 services/notification_service.py         |  47 ++-
 services/user_service.py                 |  10 +
 tests/conftest.py                        |  12 +
 tests/unit/test_ad_handler.py            | 128 +++++-
 tests/unit/test_admin_handler.py         |  90 +++-
 tests/unit/test_admin_panel_handler.py   |  39 +-
 tests/unit/test_admin_panel_keyboards.py |  55 +--
 tests/unit/test_admin_wizard.py          |  55 ++-
 tests/unit/test_bot_handlers.py          | 110 ++++-
 tests/unit/test_bot_middlewares.py       |  32 +-
 tests/unit/test_download_handler.py      |  31 +-
 tests/unit/test_exceptions.py            |  35 ++
 tests/unit/test_history_handler.py       |  37 +-
 tests/unit/test_keyboards.py             |  14 +-
 tests/unit/test_notification_service.py  |  10 +-
 workers/main.py                          |   2 +
```

(`MASTER_PLAN.md`, `PROJECT_PROGRESS.md`, `TEST_RESULTS.md`, `project_reference.md` are
documentation, covered in §7.)

**Untracked, unrelated to this sprint — leave alone:** `MARKDOWN_REMOVAL_GUIDE.md` (predates this
session; a prior handoff note says to leave it uncommitted unless asked).

## 5. A real bug found and fixed during this work

`translate(key: str, locale: str, **kwargs)`'s own first parameter is named `key`. Two catalog
templates (`admin.setting_set.unknown_key`, `admin.setting_set.success`) originally used `{key}`
as their **own** placeholder name, and `bot/handlers/admin.py` called
`translate(..., key=escape(key))` — which raised `TypeError: got multiple values for argument
'key'` the moment that code path actually ran (caught by a real failing test, not by inspection).

**Fix:** renamed the catalog placeholder to `{setting_key}` in both `en.json`/`ar.json` and
updated the two call sites in `admin.py` to pass `setting_key=`. **Verification for a reviewer:**
`tests/unit/test_i18n.py::test_real_catalogs_never_use_translate_reserved_placeholder_names` uses
`string.Formatter().parse()` to scan every real catalog value for `{key}`/`{locale}` and asserts
none exist — this is a permanent regression guard, not a one-time fix.

## 6. Test / verification results (exact numbers, reproducible)

Run from the worktree root with the project's own venv (`.venv/Scripts/python.exe`):

| Check | Command | Result |
|---|---|---|
| Full test suite | `python -m pytest -q` | **853 collected, 0 failed, 0 errors, 114 skipped** |
| Lint | `python -m ruff check .` | All checks passed |
| Format | `python -m ruff format --check .` | Clean |
| Types | `python -m mypy .` | 37 errors / 12 files — **all pre-existing, see below** |
| Import layering | `.venv/Scripts/lint-imports.exe` | 7/7 contracts kept |
| Security lint | `python -m bandit -c pyproject.toml -r bot core domain services workers infrastructure api` | 0 issues, all severities |
| Catalog key parity | `python -c "import json; ..."` (see §3.1) | en=333, ar=333, equal |

**Why 114 skipped, not 0:** every skip is a `tests/integration/*` or `tests/e2e/*` test that
needs live Postgres/Redis/a sandbox Telegram bot. This session's environment has **no Docker
daemon running** (`docker ps` fails to connect) — confirmed, not assumed. This is an environment
limitation, not a code problem: none of the skipped tests exercise i18n-touched code paths in a
way that differs from the unit-level coverage already green (this sprint touched zero
integration-layer/repository/schema code). **A reviewer with live Postgres/Redis available
should re-run the integration suite** to get a true green-light on that layer; it's expected to
pass unchanged since no integration-layer file was modified (see the manifest in §4 — nothing
under `infrastructure/database/` or `migrations/` was touched).

**Why mypy shows 37 errors instead of 0** — this needed a careful check, not a hand-wave. A
clean-cache mypy run against the **original, unmodified commit** (`git stash`, clear
`.mypy_cache`, run, `git stash pop`) produces **42 errors in 13 files**. This sprint's branch
produces 37/12 — **fewer** errors than the baseline, not more. Per-file `git diff` confirms 8 of
the 12 still-erroring files (`test_wizard_engine.py`, `test_job_service.py`,
`test_history_service.py`, `test_broadcast_service.py`, `test_broadcast_worker.py`,
`test_authorization.py`, `test_ad_placements.py`, `test_bot_composition.py`) have **zero diff**
from the original commit — any error in them cannot possibly be something this sprint
introduced. The remaining 4 touched files (`test_admin_wizard.py`, `test_notification_service.py`,
`test_download_handler.py`, `test_history_handler.py`) were checked individually and their
specific remaining errors (a `PanelStates` re-export note, an `unpack_panel` arg-type note, and a
`FakeMessageSender`/`MessageSenderProtocol` `parse_mode` mismatch) were confirmed present in the
original committed file via `git show HEAD:<path>` and/or a zero-diff check on the underlying
type definitions (`tests/unit/_fakes.py`, `domain/protocols/file_sender.py`). **A reviewer should
independently re-run this exact baseline comparison** if in doubt — it's fully reproducible with
the commands above plus `git stash`/`git stash pop`.

## 7. Documentation updated (and what a reviewer should cross-check)

- **`MASTER_PLAN.md`** — new §23 section `### Sprint 11.5 — Internationalization (i18n)`
  (inserted between Sprint 11 and Sprint 12); decision log entries **D-061 through D-064**; §2.4
  (Out of Scope table), §3 (Version Roadmap), §9 (two new Component Catalog cards: `I18n` and
  `LocaleMiddleware`, plus corrected stale "i18n in V2" mentions in `DownloadHandlers`,
  `AuthMiddleware`, `NotificationService`), §10.2/§10.13 (schema notes on `users.language` vs
  `user_preferences.preferred_language`), §13.2 (new `DEFAULT_LOCALE` env var row), §17/§18
  (Future-Versions-Readiness row 5/12 and Extension Points EP-3/EP-11 marked realized-or-
  superseded), §25.7.1 (E2E scenario bullet updated), §27 (OQ-10 resolved).
- **`project_reference.md`** — §23.2/§23.3 rewritten from a stale "Future/P1 roadmap" design
  sketch to the as-built system; a couple of scattered stale mentions (§11.5, the `broadcasts`
  and `user_preferences` table notes) corrected. **Note for the reviewer:** this file had been
  completely untouched since the initial bootstrap commit (verified via `git log -- 
  project_reference.md`) — this was a deliberate, narrowly-scoped exception to update just the
  relevant section, not a full document resync.
- **`PROJECT_PROGRESS.md`** — new Sprint 11.5 detail section (goal/tasks/validation/next steps),
  Files Modified Log row, Validation Status Log row, `OQ-10` marked resolved, a full Session
  Handoff entry. **Also fixed two pre-existing stale rows found in passing**: the Sprint Overview
  table's Sprint 11 row still said "Not Started, 0%" despite Phase A having been complete for
  days, and Sprint 12's still said "0/7" despite its A1 sub-task shipping earlier the same day —
  both corrected with the arithmetic shown so a reviewer can re-derive the totals.
- **`TEST_RESULTS.md`** — new standing entry with the exact numbers from §6; Status Summary rows
  updated.

**A reviewer should specifically check:** that D-061–D-064's stated rationale actually matches
what the code does (e.g., does `AuthMiddleware` really no longer read `tg_user.language_code`?
Does `core/i18n.py` really reject an orphaned key at startup? Does a disabled locale really never
get written back?) — this document asserts it does; a good review re-derives that from the code
rather than trusting the assertion.

## 8. Explicitly NOT verified (be honest about these)

- **No live Telegram bot round-trip.** There is no sandbox bot token in this environment
  (Sprint 11 Phase B, which this depends on, is itself blocked on Owner-provisioned
  infrastructure). Nobody has visually confirmed Arabic actually renders RTL correctly inside a
  real Telegram client, that the "Change Language" button actually appears where expected, or
  that a live fan-out to two users in two languages actually delivers correctly.
- **No live Postgres/Redis this session** — integration tests skipped (§6), not run.
- **No visual/manual QA** of any kind — this is a backend Telegram bot with no browser surface,
  and even the bot-side check above wasn't possible here.

If a reviewer has access to a sandbox bot or the ability to run this bot for real, the concrete
walkthrough to perform is: pick Arabic from `/start`, confirm the next message is RTL-correct;
pick a language from the admin panel as Owner and confirm **only** the panel chrome changes,
never ad/broadcast content; trigger a fan-out (two users, two languages, one shared download) and
confirm each gets their own language.

## 9. Suggested concrete review checklist

For a reviewing AI with repo access, in rough priority order:

1. Read `core/i18n.py` in full. Confirm: `configure()` validates `_meta` (code/native_name/
   direction/enabled/version), rejects non-`_meta` underscore-prefixed keys, rejects a
   non-default locale defining a key absent from the default locale's catalog, and that
   `translate()`/`resolve_locale()` cannot raise under any input you can construct.
2. Open both `core/locales/en.json` and `core/locales/ar.json`. Spot-check that Arabic values are
   actual Arabic (not machine-garbled), and that no value contains a `{key}` or `{locale}`
   placeholder (the bug from §5).
3. Grep the entire `bot/` tree for suspicious hardcoded English strings that should have become
   catalog keys but didn't (e.g. `grep -rn '"[A-Z][a-z]* [a-z]' bot/handlers bot/keyboards` and
   manually judge the hits — some will be legitimate non-UI strings like log messages or dict
   keys).
4. Confirm `bot/handlers/admin_wizard.py::_ad_fields()`'s `"Untitled ad"`/`"Broadcast"` literals
   really are stored-data fallbacks (check where their return value flows), not something that
   should have been translated.
5. Re-run `python -m pytest -q` yourself and confirm 0 failures/errors independently.
6. Re-run the mypy baseline comparison from §6 yourself rather than trusting the numbers here.
7. If you have Docker/Postgres/Redis available, provision them and re-run the integration suite
   (`pytest tests/integration -q`) — this sprint asserts (but could not verify) that it's
   unaffected.
8. Read `MASTER_PLAN.md` D-061 through D-064 and confirm each decision's stated rationale is
   still true of the code as it stands (not just true of what was intended).

## 10. Commit status

**Nothing in this sprint's work is committed.** `git log --oneline -3` shows the branch HEAD is
still the pre-existing commit `7894067`; every file in §4 is a working-tree modification or an
untracked new file. No push has occurred. This document itself is also uncommitted.

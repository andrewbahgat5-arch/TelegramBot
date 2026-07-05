# Sprint 13 Session Prompt

Copy everything below the line into a new Claude Code session.

---

## Context

You are working on a production Telegram download bot. The codebase is a Python 3.13 project using aiogram 3, FastAPI, SQLAlchemy (async), Redis, and Postgres.

**Worktree:** `J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46`
**Branch:** `claude/happy-bose-71ed46`
**Remote:** `origin` = `https://github.com/xAndReWxx/telegram_download_bot.git`
**Venv:** `.venv` in the worktree root

## Your Task

Execute **Sprint 13: Admin Panel Enhancement & Growth Features**. The full sprint plan with design system, task breakdown, data models, service contracts, and screen mockups is in `SPRINT_13_PLAN.md` at the worktree root. Read it completely before starting.

## What Sprint 13 Delivers

1. **Custom UI design system** — A `bot/panel/ui.py` module with reusable formatting primitives (headers, metrics, sparklines, progress bars, cards, tables, badges, footers) that make every admin screen look like a polished dashboard app. NOT a copy of any existing bot — an original design with visual hierarchy, proportional bars, and contextual color language.

2. **Full UI/UX redesign** — Apply the design system to ALL existing admin panel screens (main menu, statistics, users, settings, ads, broadcast, moderation, downloads, system, errors). The main menu itself becomes a live dashboard showing 5 key metrics before the owner taps anything.

3. **Per-platform download analytics** — Sparkline-based breakdown (TikTok ▰▰▰▰▰▰▰▰▱▱ 451 62.7%) with time filters (today/week/month/all) and CSV export.

4. **Enhanced user activity metrics** — Active 24h/7d/30d, inactive 5d/7d/30d, hourly activity, all displayed with the new design system.

5. **Blocked bot & deleted account detection** — New `bot_blocked` / `is_deleted` columns on users, batch checker via Telegram API with progress bar, purge actions.

6. **Export/Import subscribers** — CSV and JSON export of all users, CSV/JSON import with preview and validation.

7. **Full referral system** — Deep links (`?start=ref_CODE`), tracking, reward (+N bonus downloads for both), admin dashboard with leaderboard and sparklines, configurable via settings.

8. **Admin-editable message templates** — 9 key user-facing messages editable from the admin panel with live preview, stored in DB, integrated with i18n (custom overrides fall through to locale defaults).

## Execution Rules

- Read `SPRINT_13_PLAN.md` fully before writing any code
- Follow the execution order in Section 4 of the plan (13.1 first, then 13.2, etc.)
- One task → all gates → commit → continue to next task
- Gates after each task:
  ```powershell
  .\.venv\Scripts\python.exe -m ruff check .
  .\.venv\Scripts\python.exe -m ruff format --check .
  .\.venv\Scripts\python.exe -m mypy --strict bot/ core/ domain/ infrastructure/ services/ workers/ api/
  .\.venv\Scripts\python.exe -m pytest tests/unit -q
  .\.venv\Scripts\python.exe -m importlinter
  ```
- Architecture rules are in Section 6 of the plan — follow them strictly
- Key files to read first are in Section 7
- Push only when I explicitly ask

## Important Notes

- The bot uses a **registry-driven admin panel** (`bot/panel/registry.py`). New sections and actions are registered there, not hardcoded in handlers.
- All callbacks are **HMAC-signed** (`bot/callbacks/factory.py`). Never build raw callback strings.
- **i18n is mandatory** — all user-facing text uses `translate(key, locale, **kwargs)`. Add keys to both `locales/ar/messages.json` and `locales/en/messages.json`.
- **Defense in depth** — write actions must be hidden from moderators at the keyboard layer AND blocked at the filter layer.
- The **service layer is pure** — no aiogram imports. Handlers are thin wrappers that call services and format output.
- Database changes require **Alembic migrations** (`alembic revision --autogenerate -m "description"`).

Start by reading `SPRINT_13_PLAN.md`, then begin Task 13.1 (UI helpers module).

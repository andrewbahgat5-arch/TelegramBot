# Markdown Removal Guide

A complete technical reference for removing **Markdown parsing / rendering / language
support** from this project, should that ever be desired. Everything you need is in this
document — you should not have to search the codebase.

> **Branch / worktree:** live code is in `happy-bose-71ed46` (branch
> `claude/happy-bose-71ed46`). Run all gates with the venv tools under
> `J:\TelegramProjectNewCustomer\TelegramBot\.venv\Scripts\`.

---

## 0. Important context: three separate things

This project does **not** use a third-party Markdown library and does **not** parse
Markdown itself. All "formatting" is rendered **by Telegram**, requested through the
**aiogram** library in one of three ways. Be precise about which one you mean:

| # | Mechanism | Is it "Markdown"? | Where |
|---|-----------|-------------------|-------|
| **A** | **Rich Markdown** via `sendRichMessage` (`InputRichMessage(markdown=…)`) | ✅ **YES — this is the only real Markdown** | Ads only (`delivery_mode = "rich"`) |
| **B** | **HTML** via `parse_mode="HTML"` | ❌ No — this is HTML, not Markdown | Global default + broadcasts + `fields`-mode ads |
| **C** | **Copy mode** via `copyMessage` (entities preserved natively) | ❌ No — no markup language at all | `delivery_mode = "copy"` ads |

**If you only want to remove Markdown, you only need to remove (A).**
(B) and (C) are HTML / native-entity rendering and are independent of Markdown.

This guide therefore has two removal plans:

- **Plan A — Remove Markdown only** (recommended for the literal request): delete the
  Rich Markdown ad engine. HTML formatting keeps working.
- **Plan B — Remove ALL message formatting** (Markdown **and** HTML): also strip the
  global `parse_mode` and every `parse_mode=` call so the bot sends pure plain text.

---

## 1. Every place Markdown is used

### 1.1 Markdown (A) — the Rich Markdown ad engine

| Layer | File | Symbol / line | Role |
|-------|------|---------------|------|
| Enum | `domain/enums/ad_placement.py` | `AdDeliveryMode.RICH = "rich"` (~L31) | Marks an ad as Rich-Markdown |
| Enum export | `domain/enums/__init__.py` | `AdDeliveryMode` import + `__all__` | Re-export |
| Protocol | `domain/protocols/advertising.py` | `AdSenderProtocol.send_rich_ad` (~L77) | Interface for the rich send |
| Sender (impl) | `infrastructure/telegram/ad_sender.py` | `TelegramAdSender.send_rich_ad` (~L129); imports `InputRichMessage`, `ReplyParameters` (~L28); `bot.send_rich_message(InputRichMessage(markdown=…))` (~L142–145) | **The actual Telegram Rich-Markdown call** |
| Service (delivery) | `services/ad_service.py` | `_deliver` rich branch (~L257); `_send_rich` (~L290+); `deliver_plan` rich branch (~L114) | Chooses rich path; classic fallback |
| Service (CRUD) | `services/ad_service.py` | `_FIELD_TO_COLUMN["delivery"]` (~L66); `create()` `_parse_choice(… AdDeliveryMode …)` (~L386); `_validate_edit` delivery (~L574) | Accepts/stores `delivery="rich"` |
| Wizard state | `bot/panel/wizard.py` | `WizardState.content_markdown` field (~L76); `to_data`/`from_data` (~L100) | Holds the raw Markdown source |
| Wizard capture | `bot/handlers/admin_wizard.py` | `on_content` sets `ws.content_markdown = message.text` (~L407); `_ad_fields` sets `fields["delivery"]="rich"`, `fields["text"]=ws.content_markdown` (~L578–583); `start_edit` `content_markdown=ad.content_text` (~L146) | Captures typed Markdown, saves as a rich ad |
| Command help | `bot/handlers/ads.py` | `/ad_create` help text mentions `delivery (fields/copy)` (~L93) | Lets `/ad_create delivery=rich` work via the enum |
| Dependency | aiogram `3.29.0` | `Bot.send_rich_message`, `aiogram.types.InputRichMessage` | Provides the Rich Message API |

### 1.2 HTML / `parse_mode` (B) — NOT Markdown, documented for Plan B

| File | Symbol / line | Role |
|------|---------------|------|
| `core/config.py` | `bot_parse_mode: str = Field("HTML", alias="BOT_PARSE_MODE")` (~L41) | Global default parse mode |
| `infrastructure/telegram/client.py` | `DefaultBotProperties(parse_mode=settings.bot_parse_mode)` (~L25) | Applies HTML to **every** bot message |
| `.env.example` | `BOT_PARSE_MODE=HTML` (L20) | Env default |
| `domain/protocols/file_sender.py` | `MessageSenderProtocol.send_message(..., parse_mode=None)` (~L63) | Optional parse mode on the generic sender |
| `infrastructure/telegram/file_sender.py` | `TelegramMessageSender.send_message(..., parse_mode=…)` (~L132) | Passes parse mode to Telegram |
| `workers/broadcast_worker.py` | `send_message(telegram_id, text, parse_mode="HTML")` (~L199) | Broadcasts delivered as HTML |
| `bot/handlers/admin.py` | `message_text=escape(text)` in `/broadcast` | HTML-escapes raw command text |
| `infrastructure/telegram/ad_sender.py` | `send_ad(..., parse_mode=…)` (the `send_photo/send_video/send_message` calls, ~L53–108) | `fields`-mode ads delivered with the ad's `parse_mode` |
| `services/ad_service.py` | `_FIELD_TO_COLUMN["parse_mode"]`; `AdBroadcastPlan.parse_mode`; `_deliver`/`deliver_plan` pass `parse_mode` | Threads the ad's `parse_mode` |
| ~14 files under `bot/handlers/` | `<b>…</b>`, `<code>…</code>`, `escape(...)` in UI text | All bot UI text relies on the global HTML parse mode |

### 1.3 Database

| File | What | Notes |
|------|------|-------|
| `infrastructure/database/models/advertisement.py` | `delivery_mode VARCHAR(10)` (~L38), `parse_mode VARCHAR(10)` (~L41) | Columns. `delivery_mode` can hold `"rich"` |
| `infrastructure/database/repositories/advertisement.py` | `create_ad(... delivery_mode, parse_mode ...)` (~L106–130) | Persists the columns |
| `domain/protocols/repositories.py` | `create_ad` signature `delivery_mode`, `parse_mode` (~L321–324) | Protocol |
| `migrations/versions/202606240001_ads_v2_schema.py` | `ADD COLUMN delivery_mode` (L47), `ADD COLUMN parse_mode` (L51) | The migration that created the columns |

> There is **no DB CHECK constraint** on `delivery_mode`, so `"rich"` is just a string —
> removing the enum value does **not** require a migration. The columns themselves can stay
> (harmless) or be dropped via a new migration (Gate G-2). See §5.

### 1.4 Documentation / comments mentioning Markdown (cosmetic)

`MASTER_PLAN.md` (L2901, L3256), `PROJECT_PROGRESS.md`, `project_reference.md` (L2090),
`database_reference.md`, `DESIGN_9.6_unified_audience_wizard.md`. These are docs only — no
runtime impact. Update for tidiness, last.

### 1.5 Tests referencing the rich engine

`tests/unit/test_ad_service_v2.py` (`test_rich_mode_uses_send_rich_message`,
`test_rich_mode_falls_back_to_classic_send_when_unsupported`),
`tests/unit/test_admin_wizard.py` (`test_save_ad_text_content_uses_rich_markdown`,
`content_markdown=…`), `tests/unit/_fakes.py` (`FakeAdSender.send_rich_ad`, `self.rich`).

---

## 2. How messages are currently sent (the delivery paths)

```
Ad delivery — services/ad_service.py :: AdService._deliver(ad, chat_id)
  if ad.delivery_mode == RICH  → _send_rich → TelegramAdSender.send_rich_ad
                                   → bot.send_rich_message(InputRichMessage(markdown=ad.content_text))
                                   (on failure → classic send_ad, parse_mode=None)   ← MARKDOWN (A)
  elif ad.delivery_mode == COPY → TelegramAdSender.copy_ad → bot.copy_message          ← (C)
  else (fields)                 → TelegramAdSender.send_ad → send_photo/video/...       ← HTML (B)
                                   with parse_mode=ad.parse_mode

Ad broadcast — services/ad_service.py :: deliver_plan(sender, plan, chat_id)
  same three branches as above, driven by plan.delivery_mode (AdBroadcastPlan).

Plain broadcast — workers/broadcast_worker.py :: _deliver_one
  → MessageSenderProtocol.send_message(telegram_id, text, parse_mode="HTML")            ← HTML (B)

All other bot messages (handlers, notifications)
  → no explicit parse_mode → inherit the GLOBAL default parse_mode=HTML                 ← HTML (B)
    (set in infrastructure/telegram/client.py via DefaultBotProperties)
```

Wizard content capture — `bot/handlers/admin_wizard.py :: on_content`:
- A **text** message → `content_markdown = message.text` (raw Markdown source) **and**
  `content_text = message.html_text` (HTML fallback); saved as `delivery="rich"`.
- Any **non-text** message (photo/video/…) → `delivery="copy"` (path C, no Markdown).

---

## 3. Dependencies / libraries related to Markdown

- **Only `aiogram==3.29.0`** (`pyproject.toml` L31). It provides `send_rich_message`,
  `InputRichMessage`, and the `parse_mode` plumbing.
- **No standalone Markdown package** (`markdown`, `markdown-it-py`, `mistune`,
  `commonmark`, …) is installed or used.
- **Conclusion:** removing Markdown requires **no dependency change**. Do **not** remove
  aiogram — it is the core bot framework.

---

## 4. Plan A — Remove Markdown only (recommended)

Goal: delete the Rich Markdown (`sendRichMessage`) engine. Ads fall back to the existing
`fields` (HTML) / `copy` paths. HTML formatting elsewhere is untouched.

**Edits (in dependency order):**

1. **`bot/handlers/admin_wizard.py`**
   - In `on_content`, delete the `ws.content_markdown = message.text` line and the
     `ws.content_markdown = None` line.
   - In `_ad_fields`, change the text branch back to HTML delivery:
     ```python
     fields["delivery"] = "fields"
     fields["type"] = "text"
     fields["text"] = ws.content_text or ""
     fields["parse_mode"] = "HTML"        # keep HTML rendering of native formatting
     ```
   - In `start_edit`, delete the `content_markdown=ad.content_text` argument.

2. **`bot/panel/wizard.py`** — delete the `content_markdown` field from `WizardState`
   and its entry in `to_data` (and remove it from `from_data` if explicitly listed —
   `from_data` filters by known fields, so just deleting the field is enough).

3. **`services/ad_service.py`**
   - In `_deliver`, delete the `if ad.delivery_mode == AdDeliveryMode.RICH …` branch and
     the whole `_send_rich` method.
   - In `deliver_plan`, delete the `if plan.delivery_mode == AdDeliveryMode.RICH …` branch.

4. **`infrastructure/telegram/ad_sender.py`** — delete `send_rich_ad` and the now-unused
   imports `InputRichMessage`, `ReplyParameters`.

5. **`domain/protocols/advertising.py`** — delete `send_rich_ad` from `AdSenderProtocol`.

6. **`domain/enums/ad_placement.py`** — delete `RICH = "rich"` from `AdDeliveryMode`.

7. **Database (optional, no migration required):**
   - Existing ads with `delivery_mode='rich'` will no longer match any branch and would
     fall through to the `else` (HTML `send_ad`) path. **Normalize them** so they render:
     ```sql
     UPDATE advertisements SET delivery_mode = 'fields', parse_mode = 'HTML'
     WHERE delivery_mode = 'rich';
     ```
   - The `delivery_mode` / `parse_mode` **columns stay** (still used by `fields`/`copy`).

8. **Tests** — delete the rich tests and fake method:
   - `tests/unit/test_ad_service_v2.py`: `test_rich_mode_uses_send_rich_message`,
     `test_rich_mode_falls_back_to_classic_send_when_unsupported`, and the `ad_sender`
     param on `_build` if unused.
   - `tests/unit/test_admin_wizard.py`: `test_save_ad_text_content_uses_rich_markdown`
     (replace with a `delivery == "fields"` / `parse_mode == "HTML"` assertion), and
     remove `content_markdown=` usages.
   - `tests/unit/_fakes.py`: delete `FakeAdSender.send_rich_ad`, `self.rich`, and the
     `rich_error` constructor param.

9. **Docs** — update the §1.4 files to drop Rich-Markdown mentions.

After Plan A, the only message formatting left is HTML (B) + copy (C). The required common
styles (bold/italic/underline/strikethrough/spoiler/inline code/code blocks/blockquotes/
links) still render via HTML when the owner uses Telegram's native formatting; headings /
task-lists / tables (Rich-Markdown-only) will no longer render.

---

## 5. Plan B — Remove ALL message formatting (Markdown + HTML)

Do **Plan A first**, then strip HTML so the bot sends pure plain text.

1. **Global default** — `infrastructure/telegram/client.py`: remove
   `parse_mode=settings.bot_parse_mode` from `DefaultBotProperties` (or set it to `None`).
2. **`core/config.py`** — remove `bot_parse_mode` (or default it to `None`); remove
   `BOT_PARSE_MODE` from `.env.example` and `MASTER_PLAN.md` §13.2 (LOCKED — needs an
   Owner decision-log entry).
3. **Broadcasts** — `workers/broadcast_worker.py`: change
   `send_message(telegram_id, text, parse_mode="HTML")` → `send_message(telegram_id, text)`.
   - `bot/handlers/admin.py`: the `escape(text)` in `/broadcast` is now optional (only
     needed when sending HTML); you may revert to `message_text=text`.
4. **Ads** — `services/ad_service.py` / `infrastructure/telegram/ad_sender.py`: stop passing
   `parse_mode`; or normalize all ads to `delivery='fields'` with `parse_mode = NULL`.
5. **`MessageSenderProtocol` / `TelegramMessageSender`** — you may drop the optional
   `parse_mode` parameter (added for the broadcast HTML feature) to fully simplify.
6. **Handler UI text** — the ~14 files under `bot/handlers/` use literal `<b>`, `<code>`,
   `escape(...)`. With no parse mode these tags would show **literally**. You must strip the
   tags (and the `escape()` calls become unnecessary). This is the **largest** part of Plan B.
7. **Drop the columns (optional)** — write a **new** Alembic migration (forward-only; this
   is **Gate G-2 — needs Owner sign-off**) to drop `advertisements.delivery_mode` and
   `advertisements.parse_mode`, and remove `AdDeliveryMode`/`AdPlacement` delivery plumbing.
   Easier alternative: leave the columns; they become inert.

> Plan B is invasive and removes **all** rich presentation from the bot UI. Only do it if
> you truly want plain-text everywhere.

---

## 6. Side effects / features affected

| Removal | Affected feature | Result |
|---------|------------------|--------|
| Plan A | Rich-Markdown ads (`delivery='rich'`) | Headings / task-lists / tables no longer render; bold/italic/etc. still render via HTML if authored natively |
| Plan A | Existing `rich` ads in DB | Must be normalized (SQL in §4.7) or they render as raw HTML/text |
| Plan A | `/ad_create delivery=rich` | Rejected as an unknown delivery mode (only `fields`/`copy` remain) |
| Plan B | Broadcasts | Sent as plain text (no formatting) |
| Plan B | Admin panel & all bot UI | `<b>…</b>` etc. show **literally** unless every tag is stripped (§5.6) |
| Plan B | `/start`, `/help`, stats, errors, user/ad detail screens | Lose bold/code styling |
| Both | aiogram dependency | **Unchanged** — keep it |
| Both | DB schema | No change required (columns can stay); dropping them = Gate G-2 migration |

---

## 7. How to test after removal

Run from the repo root with the venv tools. **Baseline before you start** so you can compare:

```bash
# Static gates
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\mypy.exe --strict api bot core domain infrastructure services workers
.venv\Scripts\lint-imports.exe
.venv\Scripts\bandit.exe -r bot workers infrastructure services domain api core -q

# Test suite (with the known-environmental deselects)
.venv\Scripts\python.exe -m pytest \
  --deselect "tests/integration/test_redis_queue.py::test_concurrent_dequeue_no_duplicates" \
  --deselect "tests/integration/test_repositories.py::test_settings_get_and_upsert" \
  --ignore=tests/integration/test_settings_service.py
```

Expected after a correct **Plan A**: all gates green; test count drops by the deleted rich
tests; **no** `mypy`/`ruff`/`lint-imports` errors (a leftover `send_rich_ad` reference will
fail mypy — that is your safety net).

Manual smoke (needs a running bot):
- Create a text ad via the wizard → it delivers (HTML formatting if authored natively).
- Preview an ad (`/ad_preview <id>`) → renders without error.
- Send a broadcast → recipients receive it.
- Open the admin panel (`/admin`) → headings/bold still styled (Plan A) or plain (Plan B).

---

## 8. Verification checklist (no Markdown code remains)

Run these greps from the repo root; each should return **nothing** after Plan A
(ignore `__pycache__` and this guide):

```bash
grep -rn "send_rich_message"      --include=*.py .
grep -rn "InputRichMessage"       --include=*.py .
grep -rn "send_rich_ad"           --include=*.py .
grep -rni "AdDeliveryMode.RICH\|\"rich\"\|'rich'" --include=*.py domain services bot infrastructure
grep -rn "content_markdown"       --include=*.py .
```

- [ ] `AdDeliveryMode.RICH` deleted from `domain/enums/ad_placement.py`.
- [ ] `send_rich_ad` gone from `domain/protocols/advertising.py` **and**
      `infrastructure/telegram/ad_sender.py`.
- [ ] `InputRichMessage` / `ReplyParameters` imports removed from `ad_sender.py`.
- [ ] `_send_rich` and both `RICH` branches removed from `services/ad_service.py`
      (`_deliver` + `deliver_plan`).
- [ ] `content_markdown` removed from `bot/panel/wizard.py` and `bot/handlers/admin_wizard.py`.
- [ ] `_ad_fields` writes `delivery="fields"` (Plan A) — no `"rich"`.
- [ ] DB normalized: `SELECT count(*) FROM advertisements WHERE delivery_mode='rich';` → `0`.
- [ ] Rich tests + `FakeAdSender.send_rich_ad` removed; suite green.
- [ ] (Plan B only) global `parse_mode` removed from `client.py`; `BOT_PARSE_MODE` gone;
      broadcast/ad `parse_mode="HTML"` removed; handler `<b>`/`<code>` tags stripped.
- [ ] (Plan B only) new Gate-G-2 migration dropping `delivery_mode`/`parse_mode` (optional).
- [ ] Docs in §1.4 updated.
- [ ] All gates green; manual smoke passes.

---

## 9. One-line summary

- **The only true Markdown in this project is the Rich-Markdown ad engine** built on
  aiogram's `send_rich_message` / `InputRichMessage(markdown=…)`.
- **Remove it by deleting `AdDeliveryMode.RICH`, `send_rich_ad`, `_send_rich`, the two
  `RICH` branches in `ad_service.py`, and `content_markdown` in the wizard** — no
  dependency change, no migration required (Plan A).
- Everything else (`parse_mode="HTML"`, the global default, `copyMessage`) is **HTML /
  native rendering, not Markdown**, and only needs touching if you also want plain-text
  everywhere (Plan B).

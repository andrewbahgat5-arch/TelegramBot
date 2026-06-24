# Self-hosted (Local) Telegram Bot API — testing & risks

> Status: **opt-in, not default.** The public `api.telegram.org` (50 MB upload cap)
> remains the default. Setting `BOT_API_BASE_URL` switches the bot **and** worker to a
> self-hosted Bot API server (up to 2 GB). Decision D-040.

## How the app selects it

`infrastructure/telegram/client.py:build_bot` reads `BOT_API_BASE_URL`:

- **empty** → `api.telegram.org` (public, 50 MB).
- **set** (e.g. `http://localhost:8081`) → `AiohttpSession(api=TelegramAPIServer.from_base(<url>))`.

Both composition roots (`bot/main.py`, `workers/main.py`) build their `Bot` via this
helper, so a single env var flips delivery + uploads to the local server. This is
unit-verified (`tests/unit/test_telegram_client.py`): the session's API base contains
the configured host when set, and `api.telegram.org` when empty.

## Required configuration

1. Get a free **api_id / api_hash** from <https://my.telegram.org> → "API development tools".
2. Run a Bot API server (example with the community image):
   ```bash
   docker run -d --name telegram-bot-api -p 8081:8081 \
     -e TELEGRAM_API_ID=<api_id> \
     -e TELEGRAM_API_HASH=<api_hash> \
     aiogram/telegram-bot-api:latest
   ```
   For local-file optimizations add `--local` (server flag) and mount a shared volume;
   not required for our flow (we upload files, we don't `getFile` to disk).
3. In `.env`:
   ```
   BOT_API_BASE_URL=http://localhost:8081
   # Optionally raise the operator cap (settings table key, already defaults to 2 GiB):
   #   max_file_size = 2147483648
   ```
4. Restart **both** `python -m bot.main` and `python -m workers.main`.

### ⚠️ Token migration gotcha (most common failure)

A bot token that has already talked to the **cloud** API must be **logged out of the
cloud** before a local server will accept it, otherwise the local server returns
`401 Unauthorized` / "logged in from another server". Either:

- use a **fresh** test-bot token that has only ever been used with the local server, **or**
- log the existing token out of the cloud once:
  ```bash
  curl https://api.telegram.org/bot<TOKEN>/logOut
  ```
  then start the bot against the local server.

## What to verify (live, with the server running)

| Check | Expected |
|---|---|
| Bot starts | `bot_starting mode=polling`, no 401 |
| Small download (<50 MB) | delivered once, same as public API |
| **Large download (>50 MB)** | delivered successfully (public API would reject) |
| Upload behavior | one upload per request; cached `file_id` reused on resend |
| Progress + filenames | single progress bar; file named after the title |
| Compare vs public | identical UX below 50 MB; only the cap differs |

## Known risks / limitations

- **`file_id`s are server- and bot-scoped.** A `file_id` minted by the local server (or
  by a given bot token) is **not** valid on the cloud API / a different bot. Our
  `cached_files` rows store the `file_id` of whichever server+bot produced them — so
  **switching `BOT_API_BASE_URL` (or rotating the bot token) invalidates the existing
  cache**. **Mitigation (implemented):** the bot is now **self-healing** — a cache-hit
  resend that Telegram rejects with "wrong file identifier" raises `CachedFileExpiredError`,
  which evicts the stale `cached_files` row + Redis key and re-downloads the item fresh.
  So a switch no longer fails the user; the first resend of each cached item just
  re-downloads. (You can still `TRUNCATE cached_files;` in a test DB to clear it eagerly.)
- **Operational surface.** The local server is another process to run, monitor, secure,
  and back up; it holds the bot session. Production use needs it in the deploy topology
  (compose/k8s), TLS if remote, and resource limits (large uploads use disk + memory).
- **2 GB still has limits.** Very large 4K videos can exceed 2 GB; `max_file_size`
  guards this and the job fails cleanly (`FileTooLargeError`).
- **`logOut` is irreversible for ~10 minutes** (Telegram enforces a cooldown before the
  token can be used again) — don't run it against a production token casually.

## Recommendation

Keep `BOT_API_BASE_URL` **empty (public API) as the default** until the live checks above
pass in a test environment and a cache-invalidation plan is agreed. The switch is a
single env var with no code change, so it can be enabled per-environment once verified.

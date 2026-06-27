# Bot Commands Reference

Every command and interactive control the bot exposes today, grouped by who can use it.
Generated from the live handlers (`bot/handlers/`) — this reflects what is actually
wired, not aspirational features.

**Access model**
- Roles are `owner`, `moderator`, `user` (`domain/enums/user_role.py`). "Staff" = owner + moderator.
- Authorization is declarative (`bot/filters/role_filter.py`); handlers never decide it.
- **Unauthorized admin commands are silently ignored** — a non-staff user who types an
  admin command gets *no reply* (the command is invisible to them). This is intentional (#18).
- The **Owner is unlimited** (no download quota, cooldown, or throttle) and, like premium
  users, is exempt from *untargeted* ads.

---

## 1. Everyone (all users)

| Command / action | What it does |
|---|---|
| `/start` | Register (first time) or restart; shows the welcome message. |
| `/help` | Shows usage help. |
| `/history` | Lists your past downloads (newest first), paginated; tap an entry to resend it. |
| **Send a link** | Any message containing `http://` or `https://` starts a download. The bot replies with a **format** keyboard (Video / Audio), then a **quality/codec** keyboard; pick one and it downloads and delivers the file. |

### Inline buttons (tap, not typed)

These appear on bot messages — no typing needed:

| Button | Where | Effect |
|---|---|---|
| **Video / Audio** | after sending a link | choose the format → shows quality options |
| **Quality / codec** (e.g. 720p, MP3) | after choosing a format | starts the download |
| **⬅️ Back** | format/quality screens | returns to the previous choice |
| **🔁 Resend** | `/history` rows | re-sends that file (instant from cache, or re-downloads if expired) |
| **⬅️ Prev / Next ➡️** | `/history` | paginates your history |
| **Ad button** | under a delivered ad (if configured) | a Telegram URL button — tapping opens the destination directly |

---

> **Admin inline panel (Sprint 9.6, F-2/EP-22).** Most administration now happens through an
> inline keyboard panel rather than typed commands. `/admin` opens the root panel and `/settings`
> opens it at Settings (both Staff; Owner sees write actions, Moderators see read-only — write
> buttons are hidden, not disabled). Ads/Broadcast **Create** opens a guided **compose wizard**
> (Type → Audience → Placement → Settings → Content → Preview → Save) with multi-select audience
> (incl. premium) and placement, native-content capture, and an edit-from-preview hub. The
> `key=value` commands below remain as the scriptable/scriptable-debug surface.

## 2. Staff (Owner **and** Moderator) — read-only admin

| Command | Usage | What it does |
|---|---|---|
| `/admin` | `/admin` | Opens the inline admin control panel (Sprint 9.6). |
| `/stats` | `/stats` | System stats: total users, banned count, lifetime downloads, queue depth + in-flight jobs. |
| `/userinfo` | `/userinfo <telegram_id>` | Shows one user's detail (name, role, status, download counts). |
| `/settings` | `/settings` | Opens the inline Settings panel (current values + per-field editors). |

---

## 3. Owner only

| Command | Usage | What it does |
|---|---|---|
| `/users` | `/users` | Lists registered users (id, @username, name, language, role, status). |
| `/ban` | `/ban <telegram_id> [reason]` | Bans a user (optional reason). |
| `/unban` | `/unban <telegram_id>` | Lifts a ban. |
| `/setting_set` | `/setting_set <key> <value>` | Updates an **existing** setting (the key set is locked; value is type-validated). |
| `/broadcast` | `/broadcast <text> [--lang <code>] [--role <role>] [--at <ISO-8601>]` | Queues a message to users. No flags → normal users only (staff excluded). `--lang ar`, `--role premium`, etc. `--at 2026-07-01T12:00:00Z` schedules it (UTC; the worker sends it once due). |

### Advertisement commands (Owner only)

| Command | Usage | What it does |
|---|---|---|
| `/ad_create` | `/ad_create title=… [type=text\|photo\|video\|animation] [text=…] [file_id=…] [button_text=… button_url=…] [target=user\|premium\|none] [every=N] [priority=P] [scheduled_at=<ISO-8601>]` | Creates an ad. For media ads, attach the media or reply to a media message instead of `file_id=`. `scheduled_at` (UTC) gates when the ad starts showing at its placement. |
| `/ad_list` | `/ad_list` | Lists all ads (id, title, type, active, priority, frequency, target, impressions, clicks). |
| `/ad_edit` | `/ad_edit <id> field=value …` | Edits an ad's fields (same field names as `/ad_create`, including `scheduled_at=<ISO>` or `scheduled_at=none` to clear). |
| `/ad_toggle` | `/ad_toggle <id>` | Enables/disables an ad (flips its active state). |
| `/ad_delete` | `/ad_delete <id>` | Deletes an ad. |
| `/ad_stats` | `/ad_stats [id]` | Overall ad totals + CTR, or one ad's impressions/clicks/CTR. |
| `/ad_global` | `/ad_global <on\|off>` | Master switch for the whole ad system. |
| `/ad_enable` | `/ad_enable <id>` | Activate an ad. |
| `/ad_disable` | `/ad_disable <id>` | Deactivate an ad. |
| `/ad_preview` | `/ad_preview <id>` | Send the ad to yourself exactly as a user sees it. |
| `/ad_button_add` | `/ad_button_add <id> <text> \| <url> [\| row]` | Add an inline button (ads support multiple). |
| `/ad_button_clear` | `/ad_button_clear <id>` | Remove all of an ad's buttons. |
| `/ad_audience` | `/ad_audience <id> <all\|include\|exclude> [!]dim:value …` | Set audience targeting (see below). |
| `/ad_broadcast` | `/ad_broadcast <id> [--lang xx] [--role xx] [--at <ISO-8601>]` | Send a stored ad to an audience (reuses broadcast fan-out). `--at` schedules it (UTC). |
| `/ad_segment_create` | `/ad_segment_create <name> [description]` | Create a reusable audience segment. |
| `/ad_segment_add` | `/ad_segment_add <segment> <telegram_id>` | Add a user to a segment. |
| `/ad_segment_remove` | `/ad_segment_remove <segment> <telegram_id>` | Remove a user from a segment. |
| `/ad_segment_list` | `/ad_segment_list` | List segments and their member counts. |

**`/ad_create` fields**
- `title` — required, admin-facing label.
- `type` — `text` (default), `photo`, `video`, `animation`.
- `text` — content (required for text ads; caption for media ads).
- `file_id` — Telegram file id for media ads (or attach/reply to the media).
- `button_text` + `button_url` — optional inline button (both or neither).
- `target` — `user` (free), `premium`, or `none`/`all` (untargeted). Premium users and the Owner never see untargeted ads. *(Legacy fast-path; richer targeting via `/ad_audience`.)*
- `every` — show on every Nth completed download (default `1`).
- `priority` — higher wins among matching ads (default `0`).
- `placement` — `post_download` (default), `video_delivery`, `audio_delivery`, `quality_select`, `home`, `history`, `broadcast`. Persistent placements are gated by per-placement settings (default off except `post_download`).
- `delivery` — `fields` (default) or `copy`. For `copy`, reply to a message in the storage channel to reuse it verbatim (rich content, multiple buttons, formatting).
- `audience` — `all` / `include` / `exclude`; set rules with `/ad_audience`.

### `/ad_audience` targeting

`/ad_audience <id> <mode> [!]dim:value …` — `mode` is `all`/`include`/`exclude`. Each rule is `dim:value`; a `!` prefix makes it an *exclude* rule. Dimensions: `role`, `plan` (free/premium), `lang`, `user` (telegram id), `segment` (id). Within a dimension values OR; across dimensions they AND.

Examples: free-only → `/ad_audience 5 include plan:free`; Arabic-only → `/ad_audience 5 include lang:ar`; all-except-premium → `/ad_audience 5 exclude plan:premium`; specific users → `/ad_audience 5 include user:12345 user:67890`.

---

*Source of truth: `bot/handlers/{start,help,history,download,admin,ads}.py`. If a command
changes there, update this file in the same change (it is documentation, not behavior).*

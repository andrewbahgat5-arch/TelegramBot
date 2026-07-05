# Sprint 13 — Admin Panel Enhancement & Growth Features

> **Status:** PLANNED  
> **Scope:** UI/UX redesign, per-platform analytics, activity metrics, user health checks, export/import, referral system, message templates  
> **Worktree:** `happy-bose-71ed46`  
> **Branch:** `claude/happy-bose-71ed46`  
> **Depends on:** Sprint 12 (current code, all gates green)

---

## 1. Sprint Workflow

Same as every sprint:

1. One task → all gates → commit → STOP for Owner review
2. Push only when explicitly asked
3. No new dependencies without Owner approval
4. Exactly-pinned versions only
5. No `print()` — structlog only
6. Follow existing architecture: registry-driven admin panel, pure service layer, defense-in-depth authorization, signed callbacks

---

## 2. UI/UX Design System — "Dashboard Grade"

**Design philosophy:** The admin panel should feel like a native mobile dashboard app, not a chat message. Every screen is a structured card with clear visual hierarchy, not a wall of text with emoji sprinkled in.

### 2.1 Core Visual Primitives

The UI helper module `bot/panel/ui.py` exposes these reusable building blocks. All functions return plain strings (Telegram HTML parse mode). Every primitive is locale-aware and works in both LTR (English) and RTL (Arabic).

#### Header Block

A screen title with a thin rule above and below. The emoji sits left of the title (or right in RTL). A subtle dot pattern replaces the heavy ── ≪ ≫ ── style.

```
▸ Platform Analytics                ◂
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
```

Arabic variant:

```
◂                    تحليلات المنصات ◂
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
```

Function: `header(title: str, icon: str | None = None) -> str`

#### Section Divider

A light break between logical groups inside a single screen. NOT a full header — just breathing room.

```
┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
```

Function: `divider() -> str`

#### Metric Line

A single stat with a label and value. The label is dimmed (no bold), the value is bold. An optional trend arrow shows direction.

```
  👥  Members          247
  🆕  New today          5  ↑
  ⚡  Active 24h        34
```

Function: `metric(icon: str, label: str, value: int | str, trend: str | None = None) -> str`

Right-aligned values using monospace-friendly padding (Telegram code blocks or pre tags) so numbers line up in a column.

#### Progress Bar

A horizontal bar that shows a ratio visually. Uses block characters for a smooth fill. Percentage shown inline.

```
  ▰▰▰▰▰▰▰▱▱▱  68%
```

Function: `progress_bar(current: int, total: int, width: int = 10) -> str`

#### Sparkline Row

A metric line with an inline mini-bar showing the value relative to a maximum, so the owner can scan proportions at a glance.

```
  YouTube     ▰▰▰▰▰▰▰▰▱▱  451
  TikTok      ▰▰▱▱▱▱▱▱▱▱   59
  Instagram   ▰▰▰▱▱▱▱▱▱▱  197
```

Function: `sparkline(label: str, value: int, max_value: int, width: int = 10) -> str`

#### Status Badge

An inline indicator for boolean states. Not just ✅/❌ — uses color-meaningful shapes.

```
  🟢 Active    🔴 Banned    🟡 Pending    ⚪ Inactive
```

Function: `badge(state: str) -> str` — maps semantic names to dots.

#### Card Block

A bordered content area that groups related information into a visual unit. Uses Telegram's `<pre>` or `<code>` for alignment where needed, and HTML bold/italic for emphasis.

```
┌─ User Profile ──────────────────┐
│                                 │
│  Name:     Ahmed                │
│  ID:       5868066136           │
│  Role:     👑 Owner             │
│  Status:   🟢 Active            │
│  Premium:  ⭐ Yes (no expiry)   │
│                                 │
│  Downloads: 142 today / 1,203   │
│  Joined:    2026-06-15          │
│  Last seen: 2 min ago           │
│                                 │
└─────────────────────────────────┘
```

**Note:** Telegram doesn't render box-drawing perfectly on all clients. The actual implementation uses a simpler approach — bold title line + indented fields + divider — that looks clean on every device:

```
◆ User Profile

  Name       Ahmed
  ID         5868066136
  Role       👑 Owner
  Status     🟢 Active
  Premium    ⭐ Yes (no expiry)

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  Downloads  142 today / 1,203 total
  Joined     2026-06-15
  Last seen  2 min ago
```

Function: `card(title: str, fields: list[tuple[str, str]], icon: str = "◆") -> str`

#### Compact Table

For data-heavy screens (platform stats, leaderboard). Uses monospace alignment.

```
  #   Platform       Count    Share
  ─────────────────────────────────
  1   TikTok           451   62.7%
  2   Instagram        197   27.4%
  3   Facebook          59    8.2%
  4   YouTube            2    0.3%
  ─────────────────────────────────
      Total            719  100.0%
```

Function: `table(headers: list[str], rows: list[list[str]], footer: list[str] | None = None) -> str`

#### Footer / Timestamp

A subtle metadata line at the bottom of every screen.

```
                    ∙ Updated 12:30 UTC ∙
```

Function: `footer(timestamp: datetime | None = None) -> str`

### 2.2 Button Layout Rules

Telegram inline keyboards support up to 8 buttons per row. Our design rules:

1. **Primary actions:** Full-width single button (1 per row) — used for the most important CTA
2. **Equal actions:** 2 per row — used for section navigation, paired options
3. **Compact toggles:** 3 per row max — used for time filters, format selectors
4. **Navigation row:** Always last — `⬅️ Back` left, `❌ Close` right (2 per row)
5. **Destructive actions:** Always isolated on their own row, marked with 🔴 prefix
6. **Labels:** Short (under 15 chars), no full sentences. Use icon + word: `📊 Stats`, `👥 Users`

Button style hierarchy:
- **Section buttons:** `📊 Statistics`, `👥 Users`, `⚙️ Settings` — icon + noun
- **Action buttons:** `✏️ Edit`, `🗑 Delete`, `📤 Export` — icon + verb
- **Toggle buttons:** `🟢 ON` / `🔴 OFF` — dot color + state word
- **Filter buttons:** `Today`, `Week`, `Month`, `All` — no icon, text only (compact)

### 2.3 Color Language (Emoji-Based)

Since Telegram has no CSS, we use emoji as color indicators with strict semantic meaning:

| Color | Emoji | Meaning | Used for |
|---|---|---|---|
| Green | 🟢 | Healthy / Active / Enabled | Active users, enabled features |
| Red | 🔴 | Critical / Banned / Disabled | Banned users, disabled features, errors |
| Yellow | 🟡 | Warning / Pending | Pending actions, approaching limits |
| Blue | 🔵 | Informational / Neutral | Stats, metadata |
| White | ⚪ | Inactive / Empty | No data, zeroed counters |
| Star | ⭐ | Premium / Special | Premium users, featured items |
| Crown | 👑 | Owner | Owner role indicator |
| Shield | 🛡 | Moderator / Protected | Moderator role, security features |
| Fire | 🔥 | Trending / Hot | High activity, growth indicators |
| Bolt | ⚡ | Real-time / Current | Live metrics, current hour |

### 2.4 Screen Templates

Every admin screen follows one of three templates:

**Dashboard Screen** — Stats + quick actions:
```
▸ TITLE

  [metric block]
  
  ┈┈┈┈┈┈┈┈┈┈┈┈

  [metric block]

                    ∙ Updated HH:MM ∙

[Action buttons]
[Nav row]
```

**List Screen** — Scrollable items + pagination:
```
▸ TITLE (N items)

  [item rows with badges]

  Page 1/3

[Pagination: ◀ Prev | ▶ Next]
[Nav row]
```

**Detail Screen** — Single entity view + actions:
```
◆ ENTITY TITLE

  [card fields]

  ┈┈┈┈┈┈┈┈┈┈┈┈

  [secondary info]

[Contextual action buttons]
[Nav row]
```

### 2.5 Main Menu Design

The main menu is the landing screen. It should feel like a dashboard home, not a list of buttons.

```
◆ Admin Dashboard

  👥  247 members  ·  🟢 34 active
  📥  719 downloads · ⚡ 3 in queue
  ⭐  12 premium   ·  🔴 2 banned

                    ∙ Updated 12:30 ∙
```

Buttons (2 per row):
```
[📊 Statistics]    [👥 Users]
[📢 Broadcast]     [🎯 Ads]
[🔗 Referrals]     [🛡 Moderation]
[⚙️ Settings]      [📝 Templates]
[💾 Downloads]     [🖥 System]
[🌐 Language]      [❌ Close]
```

The key innovation: the main menu message itself shows a **live dashboard summary** (5 key metrics), so the owner gets value before tapping anything.

---

## 3. Task Breakdown

### Task 13.1 — UI Helpers Module (`bot/panel/ui.py`)

**What to build:** A pure presentation module that all admin panel screens use for consistent formatting. No I/O, no service calls — just string builders.

**Functions to implement:**

```python
def header(title: str, icon: str | None = None) -> str
def divider() -> str
def metric(icon: str, label: str, value: int | str, trend: str | None = None) -> str
def progress_bar(current: int, total: int, width: int = 10) -> str
def sparkline(label: str, value: int, max_value: int, width: int = 10) -> str
def badge(state: str) -> str
def card(title: str, fields: list[tuple[str, str]], icon: str = "◆") -> str
def table(headers: list[str], rows: list[list[str]], footer: list[str] | None = None) -> str
def footer(timestamp: datetime | None = None) -> str
def status_dot(enabled: bool) -> str
def role_icon(role: str) -> str
def number_fmt(n: int) -> str  # 1234 → "1,234"
def time_ago(dt: datetime) -> str  # → "2 min ago", "3 hours ago", "yesterday"
```

**Rules:**
- All output is Telegram HTML (bold = `<b>`, italic = `<i>`, code = `<code>`, pre = `<pre>`)
- All user-facing labels come from i18n keys (the function receives the already-translated label)
- Right-align numeric values for visual scanning
- Escape HTML entities in all dynamic content (`html.escape()`)
- Works correctly with both Latin and Arabic text

**Tests:** Unit tests for every function — verify HTML output, number formatting, edge cases (0, negative, very large numbers, empty strings, RTL text).

---

### Task 13.2 — Full UI Redesign (Apply Design System to All Existing Screens)

**What to change:** Every text-rendering function in `bot/handlers/admin_panel.py` and every keyboard builder in `bot/keyboards/admin_panel.py`.

**Screens to redesign:**

1. **Main Menu** (`_nav_text` / `build_main_menu`):
   - Message: live dashboard summary (5 key metrics in 3 lines) using `metric()` + `footer()`
   - Keyboard: 2-column grid with icons as shown in §2.5
   - Add quick-stats fetch so the main menu itself is informative

2. **Statistics** (`_stats_text` / section "t"):
   - Split into sub-screens: User Stats | Download Stats | System Stats
   - Each sub-screen uses `metric()` lines with proper grouping via `divider()`
   - Add submenu buttons to jump between stat views

3. **User List** (`_users_text` / `build_user_list`):
   - Each user row: `badge(status) + name + role_icon(role) + last_seen_relative`
   - Cleaner layout with index numbers

4. **User Detail** (`_user_detail_text` / `build_user_detail`):
   - Use `card()` format with Profile section + Activity section separated by `divider()`
   - Contextual action buttons change based on user state (banned → show unban, not show ban)

5. **Settings** (`_settings_text` / `build_settings_menu`):
   - Group settings by category with bold category headers:
     - 📥 Download Limits
     - ⏱ Rate Limiting  
     - 📢 Broadcast
     - 🗃 Retention
     - 🔧 Workers
   - Stepper: show current value + min/max range hint

6. **Ads List/Detail** — card-style with metrics (impressions, clicks, CTR)
7. **Moderation** — badge-enhanced ban list with reason excerpts
8. **Downloads/Queue** — status dashboard with `progress_bar()` for queue depth
9. **System/Errors** — log severity with `badge()` colors
10. **Broadcast** — cleaner wizard steps with progress indicator

**i18n:** Add/update all locale keys to support the new format strings. Every `translate()` call must use named placeholders (`{total}`, `{active}`, etc.), never positional.

**Button layouts:** Restructure all keyboards to follow the 2-column rule from §2.2.

---

### Task 13.3 — Per-Platform Download Analytics

**What exists:** `downloads.platform` column (String(50)) is populated on every download. No aggregation queries exist.

**Database layer** (`infrastructure/database/repositories/download.py`):

```python
async def count_by_platform(self, *, since: datetime | None = None) -> list[tuple[str, int]]:
    """GROUP BY platform, COUNT(*), ordered by count DESC."""

async def total_count(self, *, since: datetime | None = None) -> int:
    """Total downloads, optionally filtered by date."""
```

**Service layer** (`services/admin_service.py`):

```python
async def get_platform_stats(self, *, period: str = "all") -> PlatformStatsView:
    """Per-platform breakdown. period: 'today' | 'week' | 'month' | 'all'."""
```

`PlatformStatsView` dataclass:
```python
@dataclass(frozen=True)
class PlatformStatsView:
    platforms: list[PlatformCount]  # sorted by count DESC
    total: int
    period: str

@dataclass(frozen=True)
class PlatformCount:
    platform: str
    count: int
    share_pct: float  # percentage of total
```

**Admin panel screen** (new sub-screen of Statistics "t"):

Display using `sparkline()` for visual proportional bars:

```
▸ Platform Analytics

  TikTok      ▰▰▰▰▰▰▰▰▱▱   451  62.7%
  Instagram   ▰▰▰▱▱▱▱▱▱▱   197  27.4%
  Facebook    ▰▱▱▱▱▱▱▱▱▱    59   8.2%
  Twitter/X   ▰▱▱▱▱▱▱▱▱▱    10   1.4%
  YouTube     ▰▱▱▱▱▱▱▱▱▱     2   0.3%

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
  Total                      719

                   ∙ Updated 12:30 ∙
```

**Buttons:**
```
[Today] [Week] [Month] [All Time]
[📄 Export Report]
[⬅️ Back]
```

**"Export Report" button** — generates a CSV file:
- Columns: Platform, Today, This Week, This Month, All Time, Share %
- Sent as `bot.send_document()` with filename `download_stats_2026-07-04.csv`

**Platform display names** — i18n keys mapping platform codes to localized names:
- `platform.youtube` → "YouTube" / "يوتيوب"
- `platform.tiktok` → "TikTok" / "تيك توك"
- `platform.facebook` → "Facebook" / "فيسبوك"
- `platform.instagram` → "Instagram" / "إنستغرام"
- `platform.twitter` → "Twitter/X" / "تويتر"
- `platform.soundcloud` → "SoundCloud" / "ساوند كلاود"
- `platform.pinterest` → "Pinterest" / "بنتريست"
- `platform.snapchat` → "Snapchat" / "سناب شات"
- (add all platforms the bot supports — check the provider/downloader code for the full list)

---

### Task 13.4 — Enhanced User Activity Metrics

**What exists:** `UserStats` has: total_users, banned_users, total_downloads, new_today, new_this_week, active_today, premium_users, staff_users. The `users` table has `last_activity_at`.

**Database layer** (`infrastructure/database/repositories/user.py`):

```python
async def count_active_in_hours(self, hours: int) -> int:
    """Users with last_activity_at >= now - N hours."""

async def count_inactive_days(self, days: int) -> int:
    """Users with last_activity_at < now - N days OR last_activity_at IS NULL."""

async def count_active_current_hour(self) -> int:
    """Users active in the current clock hour."""

async def count_active_previous_hour(self) -> int:
    """Users active in the previous clock hour."""
```

**Extend `UserStats`** — add fields to the existing dataclass (or create `DetailedUserStats`):

```python
active_24h: int
active_7d: int
active_30d: int
inactive_5d: int
inactive_7d: int
inactive_30d: int
active_current_hour: int
active_previous_hour: int
```

**Update `get_stats()`** to populate the new fields with the new repository methods.

**Admin panel** — Redesigned user statistics screen:

```
▸ User Analytics

  👥  Total Members       247
  ⭐  Premium              12
  🛡  Staff                 3
  🔴  Banned                2

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  🆕  New today              5  ↑
  🔥  Active 24h            34
  🔥  Active 7d             49
  🔥  Active 30d           124

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  💤  Inactive 5d          204
  💤  Inactive 7d          198
  💤  Inactive 30d         123

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  ⚡  This hour               0
  ⚡  Previous hour           26

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  💀  Deleted accounts        0
  🚫  Blocked bot             0

                   ∙ Updated 12:30 ∙
```

Buttons:
```
[🔄 Refresh] [🔍 Check Status]
[📊 Platform Stats]
[⬅️ Back]
```

---

### Task 13.5 — Blocked Bot & Deleted Account Detection

**Database** (Alembic migration — add columns to `users`):

```python
bot_blocked: Mapped[bool] = mapped_column(default=False)
is_deleted: Mapped[bool] = mapped_column(default=False)
status_checked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
```

**Checker logic** (new module `services/user_health.py`):

```python
class UserHealthChecker:
    """Batch-checks user status via Telegram API."""
    
    async def check_batch(self, bot: Bot, user_ids: list[int], batch_size: int = 25) -> HealthReport:
        """Check up to batch_size users per call. Rate-limited to avoid API throttling.
        
        For each user, calls bot.get_chat(user_id):
        - BotBlocked / Forbidden → bot_blocked = True
        - ChatNotFound / user deactivated → is_deleted = True  
        - Success → clear both flags, update status_checked_at
        
        Returns a HealthReport with counts of each outcome.
        """
    
    async def check_all(self, bot: Bot, progress_callback: Callable | None = None) -> HealthReport:
        """Full sweep of all users. Calls check_batch in chunks with 1s delay between chunks.
        If progress_callback is provided, calls it with (checked, total) after each chunk.
        """
```

`HealthReport` dataclass:
```python
@dataclass(frozen=True)
class HealthReport:
    total_checked: int
    active: int
    blocked: int
    deleted: int
    errors: int
    duration_seconds: float
```

**Repository methods** (`infrastructure/database/repositories/user.py`):
```python
async def count_blocked(self) -> int
async def count_deleted(self) -> int
async def list_blocked(self, *, limit: int = 30, offset: int = 0) -> Sequence[User]
async def list_deleted(self, *, limit: int = 30, offset: int = 0) -> Sequence[User]
async def mark_blocked(self, telegram_id: int) -> None
async def mark_deleted(self, telegram_id: int) -> None
async def mark_active(self, telegram_id: int) -> None  # clears both flags
async def get_unchecked_ids(self, *, limit: int = 100) -> list[int]  # status_checked_at IS NULL or oldest
async def purge_blocked(self) -> int  # DELETE blocked users, return count
async def purge_deleted(self) -> int  # DELETE deleted users, return count
```

**Admin panel screens:**

"🔍 Check Status" button on user stats → triggers `check_all()` with progress edits:
```
⏳ Checking user status...

  ▰▰▰▰▰▱▱▱▱▱  124 / 247

  🟢 Active: 98
  🚫 Blocked: 20
  💀 Deleted: 6
```

After completion:
```
✅ Health check complete

  🟢 Active    221  (89.5%)
  🚫 Blocked    20  ( 8.1%)
  💀 Deleted     6  ( 2.4%)

  ⏱ Completed in 8.2s

                   ∙ Checked 12:30 ∙
```

"Blocked accounts" list screen:
```
▸ Blocked Accounts (20)

  1. @user123 · Ahmed · ID: 12345
  2. @someone · Ali · ID: 67890
  ...

  Page 1/2
```

Buttons:
```
[🗑 Purge All Blocked]   ← destructive, confirm screen
[◀ Prev] [▶ Next]
[⬅️ Back]
```

Same pattern for "Deleted accounts" screen with `[🗑 Purge All Deleted]`.

---

### Task 13.6 — Export & Import Subscribers

**Export** (admin panel button in Users section):

1. Button `📤 Export` in Users submenu
2. Format selection keyboard:
   ```
   [📊 CSV] [📋 JSON]
   [⬅️ Back]
   ```
3. On selection → generate file in temp directory → send as document

**CSV format:**
```csv
telegram_id,username,first_name,language,role,is_premium,is_banned,bot_blocked,total_downloads,daily_download_count,referred_by,created_at,last_activity_at
5868066136,xAndReW,Andrew,ar,owner,false,false,false,142,5,,2026-06-15T00:00:00Z,2026-07-04T12:30:00Z
```

**JSON format:**
```json
{
  "exported_at": "2026-07-04T12:30:00Z",
  "total_users": 247,
  "users": [
    {
      "telegram_id": 5868066136,
      "username": "xAndReW",
      "first_name": "Andrew",
      "language": "ar",
      "role": "owner",
      "is_premium": false,
      "is_banned": false,
      "bot_blocked": false,
      "total_downloads": 142,
      "referred_by": null,
      "created_at": "2026-06-15T00:00:00Z",
      "last_activity_at": "2026-07-04T12:30:00Z"
    }
  ]
}
```

**Filename:** `subscribers_{date}.csv` / `subscribers_{date}.json`

**Import:**

1. Button `📥 Import` in Users submenu (owner-only, destructive tier)
2. FSM state `import_subscribers` — waiting for file upload
3. User sends a `.csv` or `.json` document
4. Parse + validate:
   - Required field: `telegram_id` (integer)
   - Optional fields: `username`, `first_name`, `language`
   - Skip rows with missing/invalid `telegram_id`
5. Preview before applying:
   ```
   ◆ Import Preview

     📄 File: subscribers_backup.csv
     📊 Rows parsed: 150
     🆕 New users: 45
     ♻️ Already exist: 103
     ❌ Invalid/skipped: 2

     Proceed with import?
   ```
6. Confirm screen → upsert new users (create only, never overwrite existing)
7. Result:
   ```
   ✅ Import Complete

     🆕 Created: 45 users
     ♻️ Skipped: 103 (already exist)
     ❌ Failed: 2

                    ∙ Imported 12:35 ∙
   ```

**Service method** (`services/user_service.py`):
```python
async def export_users(self, format: str = "csv") -> tuple[bytes, str]:
    """Export all users. Returns (file_bytes, filename)."""

async def import_users(self, data: list[dict]) -> ImportResult:
    """Bulk-create users from parsed import data. Skip existing. Return counts."""
```

`ImportResult` dataclass:
```python
@dataclass(frozen=True)
class ImportResult:
    created: int
    skipped: int
    failed: int
    errors: list[str]  # per-row error messages for failed rows
```

---

### Task 13.7 — Referral System (Full with Rewards)

**Database** (Alembic migration):

New columns on `users`:
```python
referred_by_id: Mapped[int | None] = mapped_column(
    BigInteger, ForeignKey("users.id", ondelete="SET NULL")
)
referral_code: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
referral_bonus_downloads: Mapped[int] = mapped_column(default=0)
```

New table `referrals`:
```python
class Referral(Base):
    __tablename__ = "referrals"
    
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    referred_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    reward_granted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

**Settings keys** (add to default settings seeder):
- `referral_enabled` — bool, default `true`
- `referral_reward_downloads` — int, default `5`, stepper min 1 max 50 step 1

**Service** (`services/referral_service.py`):

```python
class ReferralService:
    async def generate_code(self, user_id: int) -> str:
        """Generate a unique referral code for a user. Idempotent — returns existing if already set."""
    
    async def process_referral(self, referrer_code: str, new_user_id: int) -> ReferralResult:
        """Called during /start when payload contains ref_<CODE>.
        Creates the referral record, grants rewards to both users.
        Returns result indicating success/failure reason."""
    
    async def get_user_referral_stats(self, user_id: int) -> UserReferralStats:
        """Stats for a single user: invite count, rewards earned, referral link."""
    
    async def get_dashboard(self) -> ReferralDashboard:
        """Admin dashboard: totals, leaderboard, period breakdowns."""
    
    async def get_leaderboard(self, *, limit: int = 10) -> list[ReferrerEntry]:
        """Top referrers sorted by invite count."""
```

Dataclasses:
```python
@dataclass(frozen=True)
class ReferralResult:
    success: bool
    reason: str  # "ok" | "self_referral" | "already_referred" | "referrer_not_found" | "disabled"

@dataclass(frozen=True)
class UserReferralStats:
    referral_code: str
    referral_link: str  # https://t.me/BOT?start=ref_CODE
    total_invited: int
    total_bonus_downloads: int

@dataclass(frozen=True)
class ReferralDashboard:
    total_referrals: int
    referrals_today: int
    referrals_week: int
    referrals_month: int
    total_rewards_granted: int
    top_referrers: list[ReferrerEntry]

@dataclass(frozen=True)
class ReferrerEntry:
    user_id: int
    username: str | None
    first_name: str
    invite_count: int
    rewards_earned: int
```

**Bot layer — `/start` handler integration:**

In the existing `/start` handler (likely `bot/handlers/start.py` or `bot/handlers/user.py`):
- Parse payload: if `message.text` matches `/start ref_<CODE>`, extract code
- Check `referral_enabled` setting
- Call `referral_service.process_referral(code, user.telegram_id)`
- If success: notify referrer via `bot.send_message(referrer_id, ...)`:
  ```
  🎉 Someone joined using your referral link!
  You earned +5 bonus downloads.
  Total referrals: 12
  ```

**User-facing referral screen** (new handler, accessible via `/referral` command or main menu button):

```
◆ Your Referral Link

  🔗 https://t.me/dangeriiivvBot?start=ref_a1b2c3

  Share this link with friends!
  You both get +5 bonus downloads.

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  👥  Total invited          12
  🎁  Bonus downloads        60
```

Buttons:
```
[📤 Share Link]    ← ForwardMessage-friendly formatted text
[⬅️ Back]
```

**Admin panel — Referral section** (new section "r" in registry):

Dashboard screen:
```
▸ Referral Analytics

  📊  Total referrals        156
  🆕  Today                    8  ↑
  📅  This week               23
  📅  This month              67
  🎁  Rewards granted        312

  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

  🏆 Top Referrers

  1. @ahmed      ▰▰▰▰▰▰▰▰▱▱  42
  2. @ali        ▰▰▰▰▱▱▱▱▱▱  23
  3. @sara       ▰▰▰▱▱▱▱▱▱▱  18
  4. @omar       ▰▰▱▱▱▱▱▱▱▱  11
  5. @fatima     ▰▱▱▱▱▱▱▱▱▱   8

                   ∙ Updated 12:30 ∙
```

Buttons:
```
[🏆 Full Leaderboard]
[⚙️ Referral Settings]
[⬅️ Back]
```

Referral Settings sub-screen (owner-only):
```
◆ Referral Settings

  🟢  System          Enabled
  🎁  Reward          5 downloads

```

Buttons:
```
[🟢 Enabled / 🔴 Disabled]   ← toggle
[🎁 Reward Amount]            ← stepper (1-50)
[⬅️ Back]
```

**Daily limit integration:**

In the daily-limit check (likely `services/user_service.py` or wherever `free_daily_limit` is enforced):
```python
effective_limit = base_limit + user.referral_bonus_downloads
```

The bonus is permanent (not per-day, not expiring). It stacks with the base limit.

---

### Task 13.8 — Message Templates (Admin-Editable)

**Database** (Alembic migration):

```python
class MessageTemplate(Base):
    __tablename__ = "message_templates"
    
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    locale: Mapped[str] = mapped_column(String(10), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_custom: Mapped[bool] = mapped_column(default=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

**Editable template keys** (V1 scope — these are the messages users see most):

| Key | Default source | Placeholders |
|---|---|---|
| `welcome` | `user.welcome` locale key | `{name}` |
| `help` | `user.help` locale key | none |
| `download_started` | `download.started` | `{title}`, `{platform}` |
| `download_complete` | `download.complete` | `{title}`, `{format}`, `{quality}` |
| `download_failed` | `download.failed` | `{error}` |
| `daily_limit_reached` | `limit.daily_reached` | `{limit}`, `{reset_in}` |
| `banned_message` | `user.banned` | `{reason}` |
| `cooldown_message` | `limit.cooldown` | `{seconds}` |
| `maintenance` | `system.maintenance` | none |

**Service** (`services/template_service.py`):

```python
class TemplateService:
    async def get(self, key: str, locale: str) -> str | None:
        """Get custom template content if exists, else None (caller falls through to i18n)."""
    
    async def set(self, key: str, locale: str, content: str, updated_by: int) -> None:
        """Upsert a custom template."""
    
    async def reset(self, key: str, locale: str) -> None:
        """Delete custom template, reverting to i18n default."""
    
    async def list_all(self, locale: str) -> list[TemplateView]:
        """All template keys with custom/default status and preview."""
    
    def invalidate_cache(self) -> None:
        """Clear the in-memory cache after an edit."""
```

`TemplateView` dataclass:
```python
@dataclass(frozen=True)
class TemplateView:
    key: str
    locale: str
    is_custom: bool
    content_preview: str  # first 80 chars
    updated_at: datetime | None
```

**Integration with i18n:**

Modify the `translate()` function in `core/i18n.py` to check templates first:

```python
def translate(key: str, locale: str, **kwargs) -> str:
    # 1. Check message_templates cache for custom override
    # 2. Fall through to locale file catalog
    # 3. Fall through to default locale
    # 4. Return key itself as last resort
```

**Important:** The template cache must be a simple dict loaded at startup and invalidated on edit. No per-request DB queries — templates are read-heavy, write-rare.

**Admin panel — Templates section** (new section "tp" or sub-section of Settings):

List screen:
```
▸ Message Templates

  📝  welcome           ✏️ Custom
  📄  help              📝 Default
  📝  download_started  ✏️ Custom
  📄  download_complete 📝 Default
  📄  download_failed   📝 Default
  📄  daily_limit       📝 Default
  📄  banned_message    📝 Default
  📄  cooldown          📝 Default
  📄  maintenance       📝 Default

```

Each row is a button that opens the edit screen:
```
[📝 welcome ✏️]
[📄 help]
[📝 download_started ✏️]
...
[⬅️ Back]
```

Edit screen (after tapping a template):
```
◆ Edit Template: welcome

  🌐 Locale: ar

  Current content:
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  مرحباً {name}! 👋
  أرسل لي رابط فيديو وسأحمله لك.
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄

  Placeholders: {name}
  Status: ✏️ Custom (edited 2026-07-04)
```

Buttons:
```
[✏️ Edit Content]     ← FSM state: type new content
[🔄 Reset to Default] ← destructive, confirm
[⬅️ Back]
```

After owner types new content → preview screen:
```
◆ Preview

  مرحباً Ahmed! 👋
  مرحباً بك في بوت التحميل!
  أرسل لي رابط وسأحمله لك فوراً.

  Save this template?
```

Buttons:
```
[✅ Save] [❌ Cancel]
```

---

### Task 13.9 — Registry Wiring & Final Integration

Wire everything together:

1. **`bot/panel/registry.py`** — register new sections and actions:
   - Section "r" (Referral) with submenu: dashboard, leaderboard, settings
   - Extend section "t" (Statistics) submenu: add platform-stats, user-activity sub-screens
   - Extend section "u" (Users) submenu: add export, import actions
   - Extend section "m" (Moderation) submenu: add blocked-list, deleted-list, purge actions
   - New section "tp" (Templates) with submenu: list, edit, reset

2. **Authorization tiers:**
   - All new read actions (stats, leaderboard, lists) → READ tier (visible to mods)
   - All new write actions (purge, import, template edit, referral settings) → WRITE tier (owner-only)

3. **`bot/panel/states.py`** — new FSM states:
   - `import_subscribers` — waiting for file upload
   - `template_edit` — waiting for new template content

4. **i18n keys** — add ALL new keys to both `locales/ar/messages.json` and `locales/en/messages.json`

5. **Main menu update** — add Referrals and Templates buttons to `build_main_menu()`

6. **Final pass:** verify every new screen uses the UI helpers from Task 13.1, not ad-hoc formatting

---

## 4. Execution Order

| Order | Task | Depends on | Effort |
|---|---|---|---|
| 1 | 13.1 — UI helpers module | nothing | Small |
| 2 | 13.2 — Full UI redesign | 13.1 | Large |
| 3 | 13.3 — Platform analytics | 13.1 | Medium |
| 4 | 13.4 — Activity metrics | 13.1 | Medium |
| 5 | 13.5 — Blocked/deleted detection | 13.4 (migration) | Medium |
| 6 | 13.6 — Export/Import | 13.5 (new columns) | Medium |
| 7 | 13.7 — Referral system | 13.1 (UI) | Large |
| 8 | 13.8 — Message templates | 13.1 (UI) | Large |
| 9 | 13.9 — Registry wiring | all above | Medium |

**Migrations note:** Tasks 13.5, 13.6, and 13.7 each add database columns/tables. They can share a single Alembic migration or be separate — prefer separate for cleaner rollback. Run `alembic upgrade head` after each migration task.

---

## 5. Gates (Run After Each Task)

```powershell
cd J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy --strict bot/ core/ domain/ infrastructure/ services/ workers/ api/
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m importlinter
```

---

## 6. Architecture Rules

- **Service layer is pure** — no aiogram imports, no Telegram types. Services return dataclasses/dicts.
- **Handlers are thin** — call services, format results, send messages. No SQL, no business logic.
- **Registry-driven** — new sections/actions registered in `bot/panel/registry.py`, NOT hardcoded.
- **Signed callbacks** — all panel callbacks use `CallbackSigner.pack_panel()` with HMAC.
- **Defense in depth** — write actions hidden from mods (keyboard layer) AND blocked (filter layer).
- **i18n everywhere** — all user-facing text uses `translate(key, locale, **kwargs)`, no hardcoded strings.
- **Alembic migrations** — every schema change gets a migration file.
- **No new dependencies** without Owner approval. Use stdlib + existing deps only.
- **UI helpers** — all admin panel text rendering goes through `bot/panel/ui.py`. No ad-hoc formatting.

---

## 7. Key Files to Read First

| File | Purpose |
|---|---|
| `bot/panel/registry.py` | Sections, submenus, action tiers |
| `bot/keyboards/admin_panel.py` | All keyboard builders |
| `bot/handlers/admin_panel.py` | All panel handlers (~1278 lines) |
| `bot/handlers/admin_wizard.py` | Compose wizard (~799 lines) |
| `bot/panel/states.py` | FSM states |
| `services/user_service.py` | UserService + UserStats |
| `services/admin_service.py` | AdminService (jobs, errors, downloads) |
| `infrastructure/database/models/` | All ORM models |
| `infrastructure/database/repositories/` | All repo classes |
| `core/i18n.py` | Translation system |
| `locales/ar/messages.json` | Arabic locale strings |
| `locales/en/messages.json` | English locale strings |
| `domain/entities/media.py` | MediaInfo (has `platform` field) |
| `infrastructure/database/models/download.py` | Download model (has `platform` column) |
| `bot/handlers/start.py` or `bot/handlers/user.py` | /start handler (for referral deep link) |

---

> **End of Sprint 13 Plan.** This document is the SSOT for the sprint scope and design system.

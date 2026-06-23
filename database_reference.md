# Telegram SaaS Download Bot — Database Architecture Reference

> **Document Status:** Canonical · Database Source of Truth
> **Last Updated:** 2026-06-22
> **Schema Version:** 1.0
> **Parent Document:** project_reference.md (v1.2)
> **Target Scale:** 20,000 daily users · 300,000 monthly users

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Entity-Relationship Diagram](#2-entity-relationship-diagram)
3. [Table Definitions](#3-table-definitions)
   - 3.1 [users](#31-table-users)
   - 3.2 [media_metadata](#32-table-media_metadata)
   - 3.3 [cached_files](#33-table-cached_files)
   - 3.4 [downloads](#34-table-downloads)
   - 3.5 [jobs](#35-table-jobs)
   - 3.6 [active_downloads](#36-table-active_downloads)
   - 3.7 [broadcasts](#37-table-broadcasts)
   - 3.8 [advertisements](#38-table-advertisements)
   - 3.9 [settings](#39-table-settings)
   - 3.10 [error_logs](#310-table-error_logs)
   - 3.11 [user_preferences](#311-table-user_preferences)
4. [Relationships](#4-relationships)
5. [Foreign Keys](#5-foreign-keys)
6. [Indexes](#6-indexes)
7. [Unique Constraints](#7-unique-constraints)
8. [Data Flow Diagrams](#8-data-flow-diagrams)
9. [Query Optimization Notes](#9-query-optimization-notes)
10. [Scaling Notes](#10-scaling-notes)
11. [Future Expansion Notes](#11-future-expansion-notes)
12. [Design Decision Log](#12-design-decision-log)

---

## 1. Design Principles

These principles govern every table, column, index, and constraint in this schema. Any future modification must be evaluated against these principles.

### 1.1 Core Principles

| # | Principle | Description |
|---|---|---|
| 1 | **Normalized Database** | Data is stored once, in one place. Metadata is not duplicated across tables. Denormalization is applied only where query performance demands it, and each case is documented with rationale. |
| 2 | **No Duplicated Metadata** | Media information (title, duration, platform, thumbnail) exists exclusively in `media_metadata`. All other tables reference it by foreign key. 1,000 users downloading the same video = 1 metadata row, not 1,000. |
| 3 | **Global Cache Architecture** | `cached_files` is the single, global, user-independent source of truth for Telegram `file_id` values. Cache entries are shared across all users. Cache lifecycle is independent from any individual user or download history record. |
| 4 | **History Separated from Cache** | `downloads` records *who downloaded what and when*. `cached_files` records *which Telegram file_ids exist*. They are separate tables with separate lifecycles. Deleting history does not destroy cache. Purging cache does not erase history. |
| 5 | **Extensible Schema** | Tables include intentional extension points for Premium, Payments, Referrals, Analytics, Multi-language, and Group Support. No structural redesign is required to add these features. |
| 6 | **Analytics-Friendly Design** | Download counters, timestamps, platform tags, usage counts, and impression trackers are embedded throughout the schema. Every analytics query the business needs can be answered from existing columns without schema changes. |
| 7 | **Future-Proof Relationships** | Foreign keys, unique constraints, and indexes are designed for the 20,000+ daily user target. Relationship cardinalities are explicitly documented and tested against projected data volumes. |
| 8 | **PostgreSQL Optimized** | The schema leverages PostgreSQL-specific features: `TIMESTAMPTZ` for timezone-aware timestamps, `gen_random_uuid()` for UUID generation, `TEXT` for unbounded strings, partial indexes where beneficial, and `ON CONFLICT` upserts for atomic cache operations. |

### 1.2 PostgreSQL Version Requirement

**Minimum:** PostgreSQL 15+

**Required features:**
- `gen_random_uuid()` — built-in UUID generation (no `pgcrypto` extension)
- `TIMESTAMPTZ` — timezone-aware timestamp storage
- Native `JSONB` — for `metadata_json` in `media_metadata`
- `ON CONFLICT DO UPDATE` — atomic upserts for cache and metadata tables
- Partial indexes — conditional index support for filtered queries

### 1.3 Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Tables | `snake_case`, plural nouns | `cached_files`, `error_logs` |
| Columns | `snake_case` | `telegram_file_id`, `daily_download_count` |
| Primary Keys | `id` (surrogate) or composite | `users.id`, `settings.key` |
| Foreign Keys | `{referenced_table_singular}_id` | `user_id`, `media_id`, `job_id` |
| Indexes | `ix_{table}_{column(s)}` | `ix_users_telegram_id`, `ix_jobs_status_priority` |
| Unique Constraints | `uq_{table}_{column(s)}` | `uq_media_platform_video` |
| Primary Key Constraints | `{table}_pkey` | `users_pkey` |

### 1.4 Data Type Standards

| Use Case | Type | Rationale |
|---|---|---|
| Surrogate primary keys | `BIGINT` | 64-bit integer supports billions of rows. Autoincrement via `GENERATED ALWAYS AS IDENTITY` or `BIGSERIAL`. |
| Job identifiers | `UUID` | Externally visible. Prevents enumeration attacks. Generated via `gen_random_uuid()`. |
| Telegram user IDs | `BIGINT` | Telegram user IDs are 64-bit integers. |
| Telegram file IDs | `VARCHAR(255)` | Telegram `file_id` strings. Length varies by file type. 255 is safe upper bound. |
| Short strings (names, types) | `VARCHAR(N)` | Bounded length for validation. `N` chosen per field. |
| Unbounded text (messages, tracebacks) | `TEXT` | PostgreSQL `TEXT` has no performance penalty vs `VARCHAR`. Used when length is unpredictable. |
| Timestamps | `TIMESTAMPTZ` | Always timezone-aware. Stored as UTC. Compared across timezones safely. |
| Booleans | `BOOLEAN` | PostgreSQL native boolean. No integer tricks. |
| Counters | `INTEGER` or `BIGINT` | `INTEGER` (32-bit, max 2.1B) for bounded counters. `BIGINT` for unbounded counters (total_downloads, impressions). |
| JSON metadata | `JSONB` | Binary JSON. Supports indexing, querying, and efficient storage. Used only for semi-structured, schema-flexible data. |
| File sizes | `BIGINT` | Bytes. Supports files up to 9.2 exabytes (Telegram limit is 2 GB). |

---

## 2. Entity-Relationship Diagram

### 2.1 Complete ERD

```
┌─────────────────────────┐
│      user_preferences   │
│─────────────────────────│
│ id (PK)                 │
│ user_id (FK, UNIQUE)────│──────────────────────────────────────────┐
│ notifications_enabled   │                                          │
│ preferred_language      │                                          │
│ created_at              │                                          │
│ updated_at              │                                          │
└─────────────────────────┘                                          │
                                                                     │
┌─────────────────────────┐         ┌─────────────────────────┐      │
│       broadcasts        │         │        settings         │      │
│─────────────────────────│         │─────────────────────────│      │
│ id (PK)                 │         │ key (PK)                │      │
│ created_by (FK)─────────│──┐      │ value                   │      │
│ target_language         │  │      │ updated_at              │      │
│ target_role             │  │      └─────────────────────────┘      │
│ message_text            │  │                                       │
│ total_sent              │  │                                       │
│ total_failed            │  │                                       │
│ created_at              │  │                                       │
└─────────────────────────┘  │                                       │
                             │                                       │
┌─────────────────────────┐  │                                       │
│     advertisements      │  │                                       │
│─────────────────────────│  │                                       │
│ id (PK)                 │  │                                       │
│ title                   │  │                                       │
│ message_text            │  │                                       │
│ is_enabled              │  │                                       │
│ show_every_downloads    │  │                                       │
│ free_users_only         │  │                                       │
│ created_by (FK)─────────│──┤                                       │
│ created_at              │  │                                       │
│ updated_at              │  │                                       │
└─────────────────────────┘  │                                       │
                             │                                       │
                             │    ┌──────────────────────────────┐    │
                             │    │           users              │    │
                             │    │──────────────────────────────│    │
                             └───►│ id (PK)                      │◄───┘
                                  │ telegram_id (UNIQUE)         │
                              ┌──►│ username                     │◄──┐
                              │   │ first_name                   │   │
                              │   │ language                     │   │
                              │   │ role                         │   │
                              │   │ is_premium                   │   │
                              │   │ premium_expires_at           │   │
                              │   │ is_banned                    │   │
                              │   │ banned_at                    │   │
                              │   │ ban_reason                   │   │
                              │   │ daily_download_count         │   │
                              │   │ total_downloads              │   │
                              │   │ last_activity_at             │   │
                              │   │ created_at                   │   │
                              │   │ updated_at                   │   │
                              │   └──────────────────────────────┘   │
                              │                │                     │
            ┌─────────────────┤                │                     │
            │                 │                │                     │
            │                 │                │                     │
┌───────────┴─────────────┐   │   ┌────────────┴─────────────────┐   │
│        downloads        │   │   │           jobs               │   │
│─────────────────────────│   │   │──────────────────────────────│   │
│ id (PK)                 │   │   │ id (PK, UUID)                │   │
│ user_id (FK)────────────│───┘   │ user_id (FK)─────────────────│───┘
│ cached_file_id (FK)─────│──┐    │ media_id (FK)────────────────│──┐
│ platform                │  │    │ format                       │  │
│ format                  │  │    │ quality                      │  │
│ quality                 │  │    │ priority                     │  │
│ file_size               │  │    │ retry_count                  │  │
│ status                  │  │    │ status                       │  │
│ created_at              │  │    │ error_message                │  │
└─────────────────────────┘  │    │ created_at                   │  │
                             │    │ started_at                   │  │
                             │    │ finished_at                  │  │
                             │    └──────────────────────────────┘  │
                             │                 │                    │
                             │                 │                    │
                             │    ┌────────────┘                    │
                             │    │                                 │
┌────────────────────────────┴┐   │   ┌─────────────────────────────┴┐
│        cached_files         │   │   │       media_metadata         │
│─────────────────────────────│   │   │──────────────────────────────│
│ id (PK)                     │   │   │ id (PK)                      │
│ media_id (FK)───────────────│───│──►│ platform                     │
│ format                      │   │   │ video_id                     │
│ quality                     │   │   │ title                        │
│ telegram_file_id            │   │   │ duration                     │
│ telegram_unique_file_id     │   │   │ thumbnail_url                │
│ file_size                   │   │   │ source_url                   │
│ usage_count                 │   │   │ metadata_json                │
│ last_used_at                │   │   │ created_at                   │
│ created_at                  │   │   │ updated_at                   │
└─────────────────────────────┘   │   └──────────────────────────────┘
                                  │                │
                                  │                │
┌─────────────────────────┐       │   ┌────────────┴─────────────────┐
│    active_downloads     │       │   │        error_logs            │
│─────────────────────────│       │   │──────────────────────────────│
│ id (PK)                 │       │   │ id (PK)                      │
│ media_id (FK)───────────│──►mm  │   │ user_id (FK, NULLABLE)───────│──► users
│ format                  │       │   │ job_id (FK, NULLABLE)────────│──► jobs
│ quality                 │       │   │ error_type                   │
│ job_id (FK)─────────────│──►j   │   │ message                      │
│ created_at              │       │   │ traceback                    │
└─────────────────────────┘       │   │ created_at                   │
                                  │   └──────────────────────────────┘
                                  │
                                  │
                                  └── (FK arrows: j = jobs, mm = media_metadata)
```

### 2.2 Relationship Summary

```
users            1 ──── N   downloads           "A user has many download history records"
users            1 ──── N   jobs                "A user creates many jobs"
users            1 ──── 1   user_preferences    "A user has one preferences record"
users            1 ──── N   broadcasts          "An admin creates many broadcasts"
users            1 ──── N   advertisements      "An admin creates many advertisements"
users            1 ──── N   error_logs          "Errors may be associated with a user"

media_metadata   1 ──── N   cached_files        "One media has many cached file variants"
media_metadata   1 ──── N   jobs                "One media can have many jobs"
media_metadata   1 ──── N   active_downloads    "One media can have active download locks"

cached_files     1 ──── N   downloads           "A cached file is referenced by many history records"

jobs             1 ──── N   error_logs          "A job may generate many error records"
jobs             1 ──── 1   active_downloads    "A job may have one active download lock"
```

### 2.3 Table Count Summary

| Category | Tables | Names |
|---|---|---|
| **Core Identity** | 1 | `users` |
| **Media & Cache** | 2 | `media_metadata`, `cached_files` |
| **Operations** | 3 | `downloads`, `jobs`, `active_downloads` |
| **Admin & Config** | 3 | `broadcasts`, `advertisements`, `settings` |
| **Diagnostics** | 1 | `error_logs` |
| **Preferences** | 1 | `user_preferences` |
| **Total** | **11** | |

---

## 3. Table Definitions

### 3.1 Table: `users`

**Purpose:** Central user registry. Every Telegram user who interacts with the bot gets a row on first `/start`. Stores identity, role, premium status, ban status, and aggregate download counters. This table is read on every incoming update (hot path).

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `telegram_id` | BIGINT | UNIQUE, NOT NULL | — | Telegram user ID — stable external identifier |
| `username` | VARCHAR(255) | NULLABLE | `NULL` | Telegram @username (may change or be absent) |
| `first_name` | VARCHAR(255) | NULLABLE | `NULL` | Telegram first name |
| `language` | VARCHAR(10) | NULLABLE | `NULL` | Telegram client language code (e.g., `en`, `ar`, `ru`) |
| `role` | VARCHAR(20) | NOT NULL | `'user'` | One of: `owner`, `moderator`, `user` |
| `is_premium` | BOOLEAN | NOT NULL | `false` | Whether the user has an active Premium subscription |
| `premium_expires_at` | TIMESTAMPTZ | NULLABLE | `NULL` | When the current Premium period expires (NULL if not premium) |
| `is_banned` | BOOLEAN | NOT NULL | `false` | Whether the user is banned from using the bot |
| `banned_at` | TIMESTAMPTZ | NULLABLE | `NULL` | When the ban was applied (NULL if never banned) |
| `ban_reason` | VARCHAR(500) | NULLABLE | `NULL` | Admin-provided reason for the ban (NULL if never banned) |
| `daily_download_count` | INTEGER | NOT NULL | `0` | Downloads today (reset by scheduled job at midnight UTC) |
| `total_downloads` | BIGINT | NOT NULL | `0` | Lifetime download count |
| `last_activity_at` | TIMESTAMPTZ | NULLABLE | `NULL` | Last meaningful interaction timestamp |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Account creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Last profile data change |

**Role values:**

| Value | Description | Assignment |
|---|---|---|
| `owner` | Full system control. Cannot be demoted. | Hardcoded Telegram ID in config |
| `moderator` | User management and system monitoring. | Assigned by Owner via command |
| `user` | Standard user. Can download and view own history. | Default role on `/start` |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `daily_download_count` on users | Fast limit check without aggregating the `downloads` table. A nightly scheduled task resets it to 0 at midnight UTC. |
| `is_premium` + `premium_expires_at` separated | `is_premium` is the fast boolean check used in middlewares and rate limiters (hot path). `premium_expires_at` is the authoritative expiry used by the premium expiration cron job. |
| `total_downloads` denormalized counter | Updated atomically on each successful download. Avoids `COUNT(*)` on `downloads` for profile display and analytics. |
| Ban fields on `users` (no separate table) | Ban checks are hot-path operations on every update. A JOIN to a separate table adds latency. When unbanned, `is_banned = false` but `banned_at` and `ban_reason` are preserved for audit until the next ban overwrites them. |
| `language` on `users` (not only preferences) | Auto-detected from Telegram client. Used as fallback when `user_preferences.preferred_language` is not set. |

**Future extension points:**

| Future Feature | Extension |
|---|---|
| Referral system | Add `referred_by BIGINT FK → users.id NULLABLE` column |
| Payment tracking | Add `stripe_customer_id VARCHAR(255) NULLABLE` column |
| Group support | No changes needed — groups are tracked in a separate `group_settings` table |

---

### 3.2 Table: `media_metadata`

**Purpose:** Single, normalized source of truth for media information. When a URL is analyzed, the platform and `video_id` are extracted, and metadata is stored **once**. All other tables reference this record by FK rather than duplicating title, duration, or platform.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `platform` | VARCHAR(50) | NOT NULL | — | Source platform identifier (e.g., `youtube`, `tiktok`, `instagram`, `twitter`) |
| `video_id` | VARCHAR(255) | NOT NULL | — | Platform-specific content identifier (e.g., YouTube video ID `dQw4w9WgXcQ`) |
| `title` | VARCHAR(1000) | NOT NULL | — | Media title |
| `duration` | INTEGER | NULLABLE | `NULL` | Duration in seconds (NULL for images/stories) |
| `thumbnail_url` | TEXT | NULLABLE | `NULL` | URL to the thumbnail image |
| `source_url` | TEXT | NOT NULL | — | Original URL submitted by the user (preserved for re-extraction if needed) |
| `metadata_json` | JSONB | NULLABLE | `NULL` | Extended metadata from yt-dlp (uploader, view count, description, tags, etc.) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | First extraction timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Last metadata refresh timestamp |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `UNIQUE(platform, video_id)` | One metadata record per unique media content. The application performs UPSERT on URL analysis. |
| `source_url` as TEXT | URLs can be arbitrarily long. `TEXT` avoids artificial truncation. |
| `metadata_json` as JSONB | Stores platform-specific metadata that varies by platform (e.g., YouTube has `view_count`, TikTok has `like_count`). JSONB supports indexing and querying. Schema-flexible — new platform fields require no migration. |
| `title` as VARCHAR(1000) | Some platforms allow very long titles. 1000 characters is a safe upper bound that prevents unbounded storage without truncating real titles. |
| `updated_at` separate from `created_at` | Metadata can be refreshed (title change, duration correction). `updated_at` tracks the latest refresh. `created_at` tracks when the content was first seen. |

**UPSERT pattern:**

```
INSERT INTO media_metadata (platform, video_id, title, duration, thumbnail_url, source_url, metadata_json)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (platform, video_id)
DO UPDATE SET
  title = EXCLUDED.title,
  duration = EXCLUDED.duration,
  thumbnail_url = EXCLUDED.thumbnail_url,
  source_url = EXCLUDED.source_url,
  metadata_json = EXCLUDED.metadata_json,
  updated_at = NOW()
RETURNING id;
```

---

### 3.3 Table: `cached_files`

**Purpose:** Global Telegram `file_id` cache. User-independent. When a file is uploaded to Telegram, Telegram returns a `file_id` that can be used to re-send the file instantly without re-uploading. This table stores those `file_id` values, keyed by media + format + quality.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `media_id` | BIGINT | FK → `media_metadata.id`, NOT NULL | — | The media this cache entry belongs to |
| `format` | VARCHAR(50) | NOT NULL | — | File format (e.g., `mp4`, `mp3`, `webm`) |
| `quality` | VARCHAR(20) | NOT NULL | — | Quality level (e.g., `720p`, `1080p`, `320kbps`) |
| `telegram_file_id` | VARCHAR(255) | NOT NULL | — | Telegram `file_id` for instant re-delivery |
| `telegram_unique_file_id` | VARCHAR(255) | NOT NULL | — | Telegram `unique_file_id` — stable across bots |
| `file_size` | BIGINT | NULLABLE | `NULL` | File size in bytes |
| `usage_count` | BIGINT | NOT NULL | `0` | Number of times this cached file has been served |
| `last_used_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Last time this cached file was served to any user |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | When the cache entry was created |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `UNIQUE(media_id, format, quality)` | One cache entry per media + format + quality combination. Enforces cache integrity at the database level. UPSERT on download completion. |
| `usage_count` | Tracks popularity. Enables "most popular files" analytics and cache prioritization. |
| `last_used_at` | Enables LRU-style cache eviction. Stale entries (not served in N days) can be periodically purged. |
| `telegram_unique_file_id` | Telegram's `unique_file_id` is stable across different bots and can be used for cross-bot deduplication or future multi-bot architectures. |
| `file_size` nullable | File size may not always be known at cache creation time (e.g., stream-uploaded files). |

**Cache lookup pattern:**

```
SELECT telegram_file_id, id
FROM cached_files
WHERE media_id = ? AND format = ? AND quality = ?;
```

**Cache UPSERT pattern (on download completion):**

```
INSERT INTO cached_files (media_id, format, quality, telegram_file_id, telegram_unique_file_id, file_size)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (media_id, format, quality)
DO UPDATE SET
  telegram_file_id = EXCLUDED.telegram_file_id,
  telegram_unique_file_id = EXCLUDED.telegram_unique_file_id,
  file_size = EXCLUDED.file_size,
  usage_count = cached_files.usage_count + 1,
  last_used_at = NOW()
RETURNING id;
```

---

### 3.4 Table: `downloads`

**Purpose:** User download history. Each row records that a specific user received a specific file at a specific time. This table is a log of user actions — it never serves as a cache and never stores Telegram file IDs directly. It references `cached_files` by FK for resend capability.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `user_id` | BIGINT | FK → `users.id`, NOT NULL | — | The user who performed the download |
| `cached_file_id` | BIGINT | FK → `cached_files.id`, NOT NULL | — | The cached file that was delivered |
| `platform` | VARCHAR(50) | NOT NULL | — | Platform (denormalized for fast history display) |
| `format` | VARCHAR(50) | NOT NULL | — | Format used (denormalized for fast history display) |
| `quality` | VARCHAR(20) | NOT NULL | — | Quality level (denormalized for fast history display) |
| `file_size` | BIGINT | NULLABLE | `NULL` | File size in bytes (denormalized for fast history display) |
| `status` | VARCHAR(20) | NOT NULL | `'completed'` | Download outcome: `completed`, `failed`, `cancelled` |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | When the download was performed |

**Status values:**

| Value | Description |
|---|---|
| `completed` | File was successfully delivered to the user |
| `failed` | Download or delivery failed after all retries |
| `cancelled` | User cancelled the download before completion |

**Design decisions:**

| Decision | Rationale |
|---|---|
| **History ≠ Cache** | Central design principle. `downloads` records *who downloaded what and when*. `cached_files` records *which Telegram file_ids are available*. Separate concerns, separate lifecycles. |
| `platform`, `format`, `quality`, `file_size` denormalized | Avoids a 3-table JOIN (`downloads → cached_files → media_metadata`) for the common "show user history" query. Tradeoff: a few extra bytes per row vs. significant query simplification. |
| `cached_file_id` FK | Enables resend: look up `cached_file_id` → read `cached_files.telegram_file_id` → send via Telegram API. If cache has been purged, fall back to a new download job. |
| No `media_id` FK | Would create a redundant relationship (already reachable via `cached_file_id → cached_files.media_id`). Adding it would create a diamond dependency requiring sync maintenance. |

**History query pattern:**

```
SELECT d.id, d.platform, d.format, d.quality, d.file_size, d.status, d.created_at
FROM downloads d
WHERE d.user_id = ?
ORDER BY d.created_at DESC
LIMIT 20 OFFSET ?;
```

**Resend from history pattern:**

```
SELECT cf.telegram_file_id
FROM downloads d
JOIN cached_files cf ON cf.id = d.cached_file_id
WHERE d.id = ? AND d.user_id = ?;
```

---

### 3.5 Table: `jobs`

**Purpose:** Download job queue persistence. Each row represents a unit of work: download a specific media in a specific format/quality for a specific user. Jobs progress through a lifecycle: `created → queued → processing → completed | failed | timed_out`.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | UUID | PK | `gen_random_uuid()` | Unique job identifier (externally visible, non-guessable) |
| `user_id` | BIGINT | FK → `users.id`, NOT NULL | — | The user who requested the download |
| `media_id` | BIGINT | FK → `media_metadata.id`, NOT NULL | — | The media to download |
| `format` | VARCHAR(50) | NOT NULL | — | Requested format |
| `quality` | VARCHAR(20) | NOT NULL | — | Requested quality |
| `priority` | INTEGER | NOT NULL | `1000` | Priority score (lower = higher priority) |
| `retry_count` | INTEGER | NOT NULL | `0` | Number of retry attempts consumed |
| `status` | VARCHAR(30) | NOT NULL | `'created'` | Current lifecycle status |
| `error_message` | TEXT | NULLABLE | `NULL` | Last error message on failure |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Job creation timestamp |
| `started_at` | TIMESTAMPTZ | NULLABLE | `NULL` | When a worker began processing |
| `finished_at` | TIMESTAMPTZ | NULLABLE | `NULL` | When the job reached a terminal state |

**Status values:**

| Value | Terminal? | Description |
|---|---|---|
| `created` | No | Job created, not yet enqueued |
| `queued` | No | Job enqueued in Redis, waiting for a worker |
| `processing` | No | Worker is actively downloading/processing |
| `completed` | Yes | Successfully downloaded and delivered |
| `failed` | Yes | Permanently failed after max retries |
| `timed_out` | Yes | Worker did not complete within the job timeout |
| `cancelled` | Yes | User or admin cancelled the job |

**Priority values:**

| Score | Tier | Assigned To |
|---|---|---|
| 0 | Highest | Premium users (future) |
| 500 | High | Moderators |
| 1000 | Normal | Free users (default) |

**Design decisions:**

| Decision | Rationale |
|---|---|
| UUID for `id` | Externally visible in user-facing messages. Prevents enumeration. |
| `media_id` FK instead of raw URL | Eliminates URL duplication across jobs. The media record is created during URL analysis before the job is created. |
| No `worker_id` column | Worker assignment is tracked in Redis (transient, high-frequency updates). Persisting it adds write pressure on every heartbeat with no query benefit. |
| `finished_at` instead of separate `completed_at` / `failed_at` | Combined with `status`, a single column records when any terminal state was reached. Simplifies queries. |

---

### 3.6 Table: `active_downloads`

**Purpose:** Durable duplicate download prevention. While Redis distributed locks handle the fast path, this table provides a persistent fallback. If Redis loses a lock (restart, eviction, network partition), the database `UNIQUE` constraint still prevents duplicate work.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `media_id` | BIGINT | FK → `media_metadata.id`, NOT NULL | — | The media being downloaded |
| `format` | VARCHAR(50) | NOT NULL | — | Format being downloaded |
| `quality` | VARCHAR(20) | NOT NULL | — | Quality being downloaded |
| `job_id` | UUID | FK → `jobs.id`, NOT NULL | — | The job performing the download |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Lock acquisition timestamp |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `UNIQUE(media_id, format, quality)` | Enforcement mechanism. An `INSERT` that violates it proves another download is already in progress. |
| Row deleted on completion | When a download completes or permanently fails, the `active_downloads` row is deleted, freeing the slot. |
| Cleanup job for orphans | A periodic cleanup scans for rows whose associated `jobs.status` is terminal but the row was not deleted (edge case). |
| Multi-user fan-out | If User A requests video X in 720p and User B requests the same while active, the system detects the existing row and attaches User B to the same job's notification list (in Redis). Both users receive the file when the job completes. |

---

### 3.7 Table: `broadcasts`

**Purpose:** Admin broadcast message log. When an Owner sends a broadcast to all users (or a filtered subset), the broadcast is recorded for auditing, delivery tracking, and analytics.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `created_by` | BIGINT | FK → `users.id`, NOT NULL | — | The admin who initiated the broadcast |
| `target_language` | VARCHAR(10) | NULLABLE | `NULL` | If set, broadcast only to users with this language (NULL = all) |
| `target_role` | VARCHAR(20) | NULLABLE | `NULL` | If set, broadcast only to users with this role (NULL = all) |
| `message_text` | TEXT | NOT NULL | — | The broadcast message content |
| `total_sent` | INTEGER | NOT NULL | `0` | Number of messages successfully delivered |
| `total_failed` | INTEGER | NOT NULL | `0` | Number of delivery failures |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Broadcast initiation timestamp |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `target_language` | Enables localized broadcasts (e.g., only Arabic-speaking users). Foundation for multi-language system. |
| `target_role` | Enables role-targeted broadcasts (e.g., announce Premium features only to premium users). |
| `total_sent` / `total_failed` on row | Updated as the broadcast job progresses. Provides delivery tracking without a separate per-user delivery log table (which can be added later if per-user tracking is needed). |
| No `status` column | A broadcast is either in-progress (total_sent + total_failed < expected) or done. Status can be derived. Adding a status would require a separate "expected_total" column and state management. |

---

### 3.8 Table: `advertisements`

**Purpose:** Smart advertisement system. Stores admin-managed advertisements shown to users based on configurable rules. Advertisements are entirely database-driven — no code changes needed to create, update, enable, disable, or retarget ads.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `title` | VARCHAR(255) | NOT NULL | — | Internal admin label for identifying this ad |
| `message_text` | TEXT | NOT NULL | — | Text content of the advertisement (Telegram HTML/Markdown) |
| `is_enabled` | BOOLEAN | NOT NULL | `true` | Whether this ad is currently being served |
| `show_every_downloads` | INTEGER | NOT NULL | `1` | Show this ad every N downloads (1 = every, 3 = every 3rd) |
| `free_users_only` | BOOLEAN | NOT NULL | `true` | When true, ad is only shown to non-premium users |
| `created_by` | BIGINT | FK → `users.id`, NOT NULL | — | Admin who created the advertisement |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Last modification timestamp |

**Ad delivery rules:**

| Scenario | Configuration |
|---|---|
| Show ad after every download | `show_every_downloads = 1`, `is_enabled = true` |
| Show ad every 3rd download | `show_every_downloads = 3`, `is_enabled = true` |
| Show ad only to free users | `free_users_only = true` |
| Show ad to all users | `free_users_only = false` |
| Disable specific ad | `is_enabled = false` |
| Disable all ads globally | Set `ads_enabled = false` in `settings` table |

**Ad selection algorithm:**

```
1. IF settings.ads_enabled == false → NO AD
2. IF user.is_premium == true AND ad.free_users_only == true → SKIP AD
3. IF user.total_downloads % ad.show_every_downloads != 0 → NO AD
4. SELECT * FROM advertisements WHERE is_enabled = true
     AND (free_users_only = false OR user.is_premium = false)
   ORDER BY id ASC
   → Return first matching ad
5. IF no match → NO AD
```

**Design decisions:**

| Decision | Rationale |
|---|---|
| `free_users_only` boolean | Simple, clear targeting. Premium users get an ad-free experience by default. Easily extendable to per-role targeting in the future by adding a `target_role` column. |
| `show_every_downloads` integer | Works with `users.total_downloads`: `IF total_downloads % show_every_downloads == 0 THEN show_ad`. Simple modulo check, no additional state tracking. |
| `title` for admin use | Human-readable label for the admin. Not shown to users. Helps identify ads in `/ad_list` command output. |
| Global kill switch in `settings` | `ads_enabled` in `settings` acts as a master override. When `false`, no ads are shown regardless of individual `is_enabled` status. |
| No `impressions`/`clicks` columns | Ad analytics are tracked via application-level Redis counters for real-time performance. If persistent analytics are needed later, add `impressions BIGINT DEFAULT 0` and `clicks BIGINT DEFAULT 0` columns — no structural change required. |

---

### 3.9 Table: `settings`

**Purpose:** Dynamic system configuration. Key-value store for runtime settings that can be changed without redeployment. These override or supplement environment variables for values that need to be adjustable by the Owner via bot commands or the admin API.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `key` | VARCHAR(100) | PK | — | Setting name |
| `value` | TEXT | NOT NULL | — | Setting value (stored as text, parsed by application layer) |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Last modification timestamp |

**Expected initial settings (seed data):**

| Key | Default Value | Type | Description |
|---|---|---|---|
| `worker_count` | `3` | Integer | Number of concurrent download workers |
| `free_daily_limit` | `10` | Integer | Max downloads per day for free users |
| `premium_daily_limit` | `100` | Integer | Max downloads per day for premium users |
| `max_free_file_size` | `52428800` | Integer (bytes) | Max file size for free users (50 MB) |
| `max_premium_file_size` | `2147483648` | Integer (bytes) | Max file size for premium users (2 GB) |
| `download_cooldown_seconds` | `30` | Integer | Min seconds between downloads for free users |
| `premium_download_cooldown_seconds` | `5` | Integer | Min seconds between downloads for premium users |
| `maintenance_mode` | `false` | Boolean | When `true`, bot replies with maintenance message |
| `max_file_size` | `2147483648` | Integer (bytes) | Global max file size (Telegram limit: 2 GB) |
| `max_duration` | `14400` | Integer (seconds) | Max media duration (4 hours) |
| `rate_limit_messages_per_minute` | `30` | Integer | Throttle: messages per user per minute |
| `ads_enabled` | `true` | Boolean | Global advertisement kill switch |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `key` as PK | No surrogate key needed. Settings are looked up by name, always. |
| `value` as TEXT | Keeps the schema simple. Application layer parses to the expected type. Avoids a separate column per data type. |
| Redis cache layer | Application reads settings through a Redis cache (TTL ~60s). Avoids hitting PostgreSQL on every request. `updated_at` enables cache invalidation when a setting is changed via admin command. |

---

### 3.10 Table: `error_logs`

**Purpose:** Persistent error log for operational diagnostics. Complements Sentry (external) with an internal, queryable error store. Enables admin dashboard error browsing, per-user error history, and error-type analytics without depending on external services.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `user_id` | BIGINT | FK → `users.id`, NULLABLE | `NULL` | The user affected (NULL for system-level errors) |
| `job_id` | UUID | FK → `jobs.id`, NULLABLE | `NULL` | The job that failed (NULL for non-job errors) |
| `error_type` | VARCHAR(30) | NOT NULL | — | Error category |
| `message` | TEXT | NOT NULL | — | Human-readable error description |
| `traceback` | TEXT | NULLABLE | `NULL` | Python traceback (sanitized — no secrets) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Error occurrence timestamp |

**Error type values:**

| Value | Description |
|---|---|
| `DOWNLOAD_ERROR` | yt-dlp download failed |
| `UPLOAD_ERROR` | Telegram file upload failed |
| `FFMPEG_ERROR` | FFmpeg transcoding failed |
| `CACHE_ERROR` | Redis cache operation failed |
| `PLATFORM_ERROR` | Source platform blocked/rate-limited the request |
| `UNKNOWN_ERROR` | Unclassified error |

**Design decisions:**

| Decision | Rationale |
|---|---|
| Both `user_id` and `job_id` nullable | Some errors are system-level (e.g., Redis connection failure at startup) and not associated with any user or job. |
| `traceback` sanitized | Must strip secrets (bot token, DB credentials) before storage. Defense-in-depth against information leakage. |
| Retention policy | This table grows indefinitely. A retention policy should delete records older than N days (configurable via `settings`). |

---

### 3.11 Table: `user_preferences`

**Purpose:** User-specific preferences separate from the core `users` table. Isolating preferences keeps the frequently-queried `users` table lean and provides a clean extension point for future preference categories.

| Column | Type | Constraints | Default | Description |
|---|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | — | Internal surrogate key |
| `user_id` | BIGINT | FK → `users.id`, UNIQUE, NOT NULL | — | One-to-one relationship with `users` |
| `notifications_enabled` | BOOLEAN | NOT NULL | `true` | Whether the user receives job status notifications |
| `preferred_language` | VARCHAR(10) | NULLABLE | `NULL` | User's explicitly chosen interface language (overrides Telegram language) |
| `created_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `NOW()` | Last preference change |

**Design decisions:**

| Decision | Rationale |
|---|---|
| `preferred_language` vs `users.language` | `users.language` = Telegram client language (auto-detected). `user_preferences.preferred_language` = user's explicit choice. Explicit takes precedence. This supports the multi-language system. |
| `UNIQUE` on `user_id` | Enforces strict one-to-one relationship. One preferences record per user. |
| Created lazily | Row created on first preference change, not on `/start`. Avoids creating empty preference rows for users who never customize settings. |
| Future columns | `default_format`, `default_quality`, `auto_download`, `theme` can be added as columns without structural changes. |

---

## 4. Relationships

### 4.1 Complete Relationship Map

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           RELATIONSHIP CARDINALITIES                            │
├───────────────────────┬──────────┬──────────────────────┬───────────────────────┤
│ Parent Table          │ Type     │ Child Table          │ Description           │
├───────────────────────┼──────────┼──────────────────────┼───────────────────────┤
│ users                 │ 1 ── N   │ downloads            │ User has many history │
│ users                 │ 1 ── N   │ jobs                 │ User creates many jobs│
│ users                 │ 1 ── 1   │ user_preferences     │ One prefs per user    │
│ users                 │ 1 ── N   │ broadcasts           │ Admin → many bcast    │
│ users                 │ 1 ── N   │ advertisements       │ Admin → many ads      │
│ users                 │ 1 ── N   │ error_logs           │ Errors linked to user │
│                       │          │                      │                       │
│ media_metadata        │ 1 ── N   │ cached_files         │ Media → many variants │
│ media_metadata        │ 1 ── N   │ jobs                 │ Media → many jobs     │
│ media_metadata        │ 1 ── N   │ active_downloads     │ Media → active locks  │
│                       │          │                      │                       │
│ cached_files          │ 1 ── N   │ downloads            │ Cache → many history  │
│                       │          │                      │                       │
│ jobs                  │ 1 ── N   │ error_logs           │ Job → many errors     │
│ jobs                  │ 1 ── 1   │ active_downloads     │ Job → one lock        │
├───────────────────────┴──────────┴──────────────────────┴───────────────────────┤
│ settings              │ (standalone — no FK relationships)                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Dependency Order (for migration creation and seeding)

Tables must be created in this order to satisfy foreign key dependencies:

```
1. users               (no FK dependencies)
2. settings             (no FK dependencies)
3. media_metadata       (no FK dependencies)
4. user_preferences     (depends on: users)
5. broadcasts           (depends on: users)
6. advertisements       (depends on: users)
7. cached_files         (depends on: media_metadata)
8. jobs                 (depends on: users, media_metadata)
9. downloads            (depends on: users, cached_files)
10. active_downloads    (depends on: media_metadata, jobs)
11. error_logs          (depends on: users, jobs)
```

Drop/truncate order is the reverse.

---

## 5. Foreign Keys

### 5.1 Complete Foreign Key Reference

| # | Source Table | Source Column | Target Table | Target Column | ON DELETE | Rationale |
|---|---|---|---|---|---|---|
| FK1 | `downloads` | `user_id` | `users` | `id` | CASCADE | Deleting a user removes their download history |
| FK2 | `downloads` | `cached_file_id` | `cached_files` | `id` | RESTRICT | Cannot delete a cache entry referenced by history. Purge history first or nullify. |
| FK3 | `jobs` | `user_id` | `users` | `id` | CASCADE | Deleting a user removes their jobs |
| FK4 | `jobs` | `media_id` | `media_metadata` | `id` | RESTRICT | Cannot delete media that has associated jobs |
| FK5 | `cached_files` | `media_id` | `media_metadata` | `id` | CASCADE | Deleting media metadata removes its cached files |
| FK6 | `active_downloads` | `media_id` | `media_metadata` | `id` | CASCADE | Deleting media removes its active download locks |
| FK7 | `active_downloads` | `job_id` | `jobs` | `id` | CASCADE | Deleting a job removes its active download lock |
| FK8 | `broadcasts` | `created_by` | `users` | `id` | RESTRICT | Cannot delete a user who created broadcasts (audit trail) |
| FK9 | `advertisements` | `created_by` | `users` | `id` | RESTRICT | Cannot delete a user who created advertisements (audit trail) |
| FK10 | `error_logs` | `user_id` | `users` | `id` | SET NULL | Deleting a user nullifies error references (preserve error log) |
| FK11 | `error_logs` | `job_id` | `jobs` | `id` | SET NULL | Deleting a job nullifies error references (preserve error log) |
| FK12 | `user_preferences` | `user_id` | `users` | `id` | CASCADE | Deleting a user removes their preferences |

### 5.2 ON DELETE Behavior Rationale

| Behavior | When Used | Why |
|---|---|---|
| **CASCADE** | Parent owns child completely. Child has no value without parent. | User deletion should clean up their jobs, downloads, preferences, locks. |
| **RESTRICT** | Child has audit or integrity value beyond the parent. | Cannot delete cache entries that history still references. Cannot delete users who authored broadcasts or ads (preserve audit trail). |
| **SET NULL** | Child has diagnostic value independent of the parent. | Error logs should survive user/job deletion — they're system diagnostics, not user-owned data. |

---

## 6. Indexes

### 6.1 Primary Indexes (auto-created from PKs and UNIQUEs)

| # | Table | Index Name | Column(s) | Created By |
|---|---|---|---|---|
| 1 | `users` | `users_pkey` | `id` | PK |
| 2 | `users` | `uq_users_telegram_id` | `telegram_id` | UNIQUE |
| 3 | `media_metadata` | `media_metadata_pkey` | `id` | PK |
| 4 | `media_metadata` | `uq_media_platform_video` | `(platform, video_id)` | UNIQUE |
| 5 | `cached_files` | `cached_files_pkey` | `id` | PK |
| 6 | `cached_files` | `uq_cached_media_format_quality` | `(media_id, format, quality)` | UNIQUE |
| 7 | `downloads` | `downloads_pkey` | `id` | PK |
| 8 | `jobs` | `jobs_pkey` | `id` | PK |
| 9 | `active_downloads` | `active_downloads_pkey` | `id` | PK |
| 10 | `active_downloads` | `uq_active_media_format_quality` | `(media_id, format, quality)` | UNIQUE |
| 11 | `broadcasts` | `broadcasts_pkey` | `id` | PK |
| 12 | `advertisements` | `advertisements_pkey` | `id` | PK |
| 13 | `settings` | `settings_pkey` | `key` | PK |
| 14 | `error_logs` | `error_logs_pkey` | `id` | PK |
| 15 | `user_preferences` | `user_preferences_pkey` | `id` | PK |
| 16 | `user_preferences` | `uq_user_prefs_user_id` | `user_id` | UNIQUE |

**Total auto-created indexes: 16**

### 6.2 Secondary Indexes (manually created for query performance)

| # | Table | Index Name | Column(s) | Purpose |
|---|---|---|---|---|
| 1 | `users` | `ix_users_role` | `role` | Filter users by role (admin queries, broadcast targeting) |
| 2 | `users` | `ix_users_is_premium` | `is_premium` | Filter premium users (expiry jobs, analytics) |
| 3 | `users` | `ix_users_is_banned` | `is_banned` | Fast ban check in auth middleware (hot path) |
| 4 | `users` | `ix_users_last_activity` | `last_activity_at` | Inactive user detection, DAU/WAU/MAU analytics |
| 5 | `users` | `ix_users_created_at` | `created_at` | User growth analytics, cohort analysis |
| 6 | `media_metadata` | `ix_media_platform` | `platform` | Platform-specific analytics |
| 7 | `media_metadata` | `ix_media_created_at` | `created_at` | Time-based queries, data cleanup |
| 8 | `cached_files` | `ix_cached_media_id` | `media_id` | Lookup all cached variants of a media |
| 9 | `cached_files` | `ix_cached_last_used` | `last_used_at` | Cache eviction policy (LRU) |
| 10 | `cached_files` | `ix_cached_usage_count` | `usage_count` | Analytics: most popular cached files |
| 11 | `downloads` | `ix_downloads_user_id` | `user_id` | User history lookup |
| 12 | `downloads` | `ix_downloads_user_created` | `(user_id, created_at DESC)` | Optimized paginated user history (covering index) |
| 13 | `downloads` | `ix_downloads_platform` | `platform` | Platform analytics |
| 14 | `downloads` | `ix_downloads_created_at` | `created_at` | Time-based analytics, retention |
| 15 | `jobs` | `ix_jobs_user_id` | `user_id` | User's job lookup |
| 16 | `jobs` | `ix_jobs_status` | `status` | Queue management: find jobs by state |
| 17 | `jobs` | `ix_jobs_media_id` | `media_id` | Find all jobs for a specific media |
| 18 | `jobs` | `ix_jobs_created_at` | `created_at` | Time-based queries, cleanup |
| 19 | `jobs` | `ix_jobs_status_priority` | `(status, priority, created_at)` | Optimized queue dequeue (DB-backed fallback) |
| 20 | `active_downloads` | `ix_active_job_id` | `job_id` | Lookup active download by job |
| 21 | `error_logs` | `ix_errors_user_id` | `user_id` | Per-user error history |
| 22 | `error_logs` | `ix_errors_job_id` | `job_id` | Per-job error history |
| 23 | `error_logs` | `ix_errors_type` | `error_type` | Error-type analytics |
| 24 | `error_logs` | `ix_errors_created_at` | `created_at` | Time-based queries, retention policy |
| 25 | `broadcasts` | `ix_broadcasts_created_at` | `created_at` | Broadcast history browsing |
| 26 | `advertisements` | `ix_ads_is_enabled` | `is_enabled` | Filter active ads for delivery |

**Total manually-created indexes: 26**

**Grand total indexes: 42** (16 auto + 26 manual)

### 6.3 Index Design Rationale

| Category | Principle |
|---|---|
| **Hot path indexes** | `ix_users_is_banned`, `uq_users_telegram_id` — queried on every incoming update. Must be as fast as possible. |
| **Composite indexes** | `ix_downloads_user_created` (`user_id`, `created_at DESC`) — covers the paginated history query without a sort operation. `ix_jobs_status_priority` (`status`, `priority`, `created_at`) — covers the queue dequeue pattern. |
| **Analytics indexes** | `ix_downloads_platform`, `ix_downloads_created_at`, `ix_users_last_activity` — support aggregation queries for the admin dashboard without full table scans. |
| **Maintenance indexes** | `ix_cached_last_used`, `ix_errors_created_at` — support cleanup/retention policies. |

### 6.4 Indexes NOT Created (and why)

| Skipped Index | Why Not Created |
|---|---|
| `users.username` | Usernames are rarely queried directly. Lookups are by `telegram_id`. |
| `users.first_name` | No query pattern requires name-based lookups. |
| `downloads.status` | Rarely filtered by status. Most history queries return all statuses. |
| `downloads.file_size` | No query pattern requires file-size filtering. |
| `jobs.error_message` | Text column. Full-text search would require GIN index — unnecessary for current use cases. |
| `media_metadata.title` | No query pattern requires title search. If needed, add a GIN trigram index later. |
| `settings.updated_at` | Settings table is tiny (< 20 rows). Sequential scan is faster than index lookup. |
| `broadcasts.created_by` | Broadcasts table grows slowly. No performance-critical query on this column. |

---

## 7. Unique Constraints

### 7.1 All Unique Constraints

| # | Table | Constraint Name | Column(s) | Purpose |
|---|---|---|---|---|
| 1 | `users` | `uq_users_telegram_id` | `telegram_id` | One row per Telegram user |
| 2 | `media_metadata` | `uq_media_platform_video` | `(platform, video_id)` | One metadata record per unique media content |
| 3 | `cached_files` | `uq_cached_media_format_quality` | `(media_id, format, quality)` | One cache entry per media + format + quality |
| 4 | `active_downloads` | `uq_active_media_format_quality` | `(media_id, format, quality)` | Only one active download per media + format + quality |
| 5 | `user_preferences` | `uq_user_prefs_user_id` | `user_id` | One preferences record per user |

### 7.2 How Unique Constraints Are Used

| Constraint | Usage Pattern |
|---|---|
| `uq_users_telegram_id` | `INSERT ... ON CONFLICT (telegram_id) DO UPDATE` for user upsert on every interaction |
| `uq_media_platform_video` | `INSERT ... ON CONFLICT (platform, video_id) DO UPDATE` for media metadata upsert |
| `uq_cached_media_format_quality` | `INSERT ... ON CONFLICT (media_id, format, quality) DO UPDATE` for cache upsert on download completion |
| `uq_active_media_format_quality` | `INSERT ... ON CONFLICT → duplicate download detected` — the constraint IS the deduplication mechanism |
| `uq_user_prefs_user_id` | Ensures one-to-one relationship enforcement at the database level |

---

## 8. Data Flow Diagrams

### 8.1 New Download — Complete Path

```
User sends URL
        │
        ▼
  URLAnalyzerService extracts (platform, video_id)
        │
        ▼
  UPSERT into media_metadata
  ON CONFLICT (platform, video_id) DO UPDATE
  Returns media_metadata.id
        │
        ▼
  SELECT from cached_files
  WHERE media_id = ? AND format = ? AND quality = ?
        │
   ┌────┴────┐
   │         │
  HIT      MISS
   │         │
   │         ▼
   │    INSERT into active_downloads
   │    (media_id, format, quality, job_id)
   │    ON CONFLICT → duplicate detected → attach to existing job
   │         │
   │         ▼
   │    INSERT into jobs
   │    (user_id, media_id, format, quality, ...)
   │         │
   │         ▼
   │    Worker downloads file via yt-dlp
   │         │
   │         ▼
   │    Worker uploads to Telegram → gets file_id
   │         │
   │         ▼
   │    UPSERT into cached_files
   │    (media_id, format, quality, telegram_file_id)
   │    Returns cached_files.id
   │         │
   ◄─────────┘
   │
   ▼
  INSERT into downloads
  (user_id, cached_file_id, platform, format, ...)
        │
        ▼
  UPDATE users SET
    daily_download_count = daily_download_count + 1,
    total_downloads = total_downloads + 1
        │
        ▼
  UPDATE cached_files SET
    usage_count = usage_count + 1,
    last_used_at = NOW()
        │
        ▼
  DELETE FROM active_downloads WHERE job_id = ?
        │
        ▼
  Send file to user via telegram_file_id (instant)
        │
        ▼
  AdService checks if ad should be shown
  IF yes → send ad after file delivery
```

### 8.2 Instant Resend — From History

```
User requests resend from history
        │
        ▼
  SELECT cf.telegram_file_id
  FROM downloads d
  JOIN cached_files cf ON cf.id = d.cached_file_id
  WHERE d.id = ? AND d.user_id = ?
        │
   ┌────┴────┐
   │         │
  Found    Not Found (cache purged)
   │         │
   │         ▼
   │    Create new download job
   │    (re-enters §8.1 flow)
   │
   ▼
  Send file via cached telegram_file_id (instant)
  UPDATE cached_files SET usage_count = usage_count + 1,
    last_used_at = NOW()
```

### 8.3 Rate Limit Check — On Download Request

```
User requests download
        │
        ▼
  SELECT is_banned, is_premium, daily_download_count
  FROM users WHERE telegram_id = ?
        │
   ┌────┴────┐
   │         │
  Banned   Not banned
   │         │
   ▼         ▼
  REJECT   Read settings:
           IF is_premium: read premium_daily_limit, premium_download_cooldown_seconds
           ELSE: read free_daily_limit, download_cooldown_seconds
                │
                ▼
           Check daily_download_count < limit
                │
           ┌────┴────┐
           │         │
          OK       EXCEEDED → "Daily limit reached"
           │
           ▼
           Check cooldown via Redis (last_download:{user_id} TTL)
                │
           ┌────┴────┐
           │         │
          OK       IN_COOLDOWN → "Wait N seconds"
           │
           ▼
           Check file size against max_{plan}_file_size
                │
           ┌────┴────┐
           │         │
          OK       TOO_LARGE → "File too large for your plan"
           │
           ▼
           Proceed with download
```

---

## 9. Query Optimization Notes

### 9.1 Hot Path Queries (every request)

| Query | Expected Frequency | Optimization |
|---|---|---|
| User lookup by `telegram_id` | Every incoming Telegram update | B-tree index on `uq_users_telegram_id`. Single-row lookup. O(log n). |
| Ban check (`is_banned`) | Every incoming update | Value is on the `users` row already fetched. No additional query needed. |
| Settings lookup by `key` | Every download request | Cached in Redis with 60s TTL. PostgreSQL hit only on cache miss. |

### 9.2 Frequent Queries

| Query | Optimization |
|---|---|
| Cache lookup (`media_id`, `format`, `quality`) | Composite unique index `uq_cached_media_format_quality`. Single-row lookup. |
| User history (paginated, newest first) | Composite index `ix_downloads_user_created (user_id, created_at DESC)`. Index-only scan for pagination. |
| Queue dequeue (next job to process) | Composite index `ix_jobs_status_priority (status, priority, created_at)`. Index scan for top-1 row. |
| Active download check | Composite unique index `uq_active_media_format_quality`. INSERT + ON CONFLICT is the check. |

### 9.3 Analytics Queries (background/admin)

| Query | Approach |
|---|---|
| Downloads per day | `GROUP BY DATE(created_at)` on `downloads` with `ix_downloads_created_at` index. At scale, consider pre-aggregation into `daily_stats` (see §11). |
| Downloads by platform | `GROUP BY platform` on `downloads` with `ix_downloads_platform` index. |
| Most popular files | `ORDER BY usage_count DESC` on `cached_files` with `ix_cached_usage_count` index. |
| User growth | `GROUP BY DATE(created_at)` on `users` with `ix_users_created_at` index. |
| Active users (DAU) | `COUNT(*) WHERE last_activity_at >= today` on `users` with `ix_users_last_activity` index. |
| Error distribution | `GROUP BY error_type` on `error_logs` with `ix_errors_type` index. |

### 9.4 Write Optimization Notes

| Write Pattern | Optimization |
|---|---|
| User upsert (every interaction) | `ON CONFLICT (telegram_id) DO UPDATE`. Single statement, no read-then-write. |
| Download counter increment | `UPDATE users SET daily_download_count = daily_download_count + 1, total_downloads = total_downloads + 1`. Atomic, no read-before-write. |
| Cache usage counter | `UPDATE cached_files SET usage_count = usage_count + 1, last_used_at = NOW()`. Atomic. |
| Job status transitions | `UPDATE jobs SET status = ?, started_at/finished_at = NOW() WHERE id = ?`. Indexed by PK. |
| Active download cleanup | `DELETE FROM active_downloads WHERE job_id = ?`. Indexed by `ix_active_job_id`. |

### 9.5 Connection Pool Sizing

| Parameter | Value | Rationale |
|---|---|---|
| Pool size | 10 | Handles normal load. Each connection can process ~100 queries/second. |
| Max overflow | 20 | Burst capacity. Total max connections = pool_size + max_overflow = 30. |
| Statement timeout | 30s | Prevents runaway queries from holding connections. |
| Idle timeout | 300s | Reclaims idle connections after 5 minutes. |

---

## 10. Scaling Notes

### 10.1 Projected Data Volumes

| Table | Growth Rate | Rows at 1 Year (20k DAU) | Notes |
|---|---|---|---|
| `users` | ~500/day new users | ~300,000 | Grows with new user registrations. Slow growth. |
| `media_metadata` | ~2,000/day new content | ~730,000 | Many URLs lead to same media (deduped by UNIQUE). |
| `cached_files` | ~3,000/day new variants | ~1,100,000 | Multiple format+quality variants per media. |
| `downloads` | ~50,000/day | ~18,000,000 | **Largest table.** Append-only log. |
| `jobs` | ~50,000/day | ~18,000,000 | Matches downloads. Can be pruned after completion. |
| `active_downloads` | ~100 concurrent | ~100 | **Constant size.** Rows are transient. |
| `broadcasts` | ~1/day | ~365 | Negligible. |
| `advertisements` | ~1/week | ~52 | Negligible. |
| `settings` | static | ~15 | Negligible. |
| `error_logs` | ~500/day | ~180,000 (with 1-year retention) | Prunable. Retention policy recommended. |
| `user_preferences` | ~200/day | ~73,000 | Only created on explicit preference change. |

### 10.2 Tables Requiring Retention Policies

| Table | Recommended Retention | Cleanup Strategy |
|---|---|---|
| `downloads` | 365 days | Nightly job: `DELETE FROM downloads WHERE created_at < NOW() - INTERVAL '365 days'` |
| `jobs` | 90 days (completed/failed) | Nightly job: `DELETE FROM jobs WHERE status IN ('completed', 'failed', 'timed_out', 'cancelled') AND finished_at < NOW() - INTERVAL '90 days'` |
| `error_logs` | 90 days | Nightly job: `DELETE FROM error_logs WHERE created_at < NOW() - INTERVAL '90 days'` |

### 10.3 Partitioning Strategy (when tables exceed ~50M rows)

| Table | Partition Strategy | Partition Key |
|---|---|---|
| `downloads` | Range partitioning by month | `created_at` |
| `jobs` | Range partitioning by month | `created_at` |
| `error_logs` | Range partitioning by month | `created_at` |

PostgreSQL native declarative partitioning. Benefits:
- Partition pruning on time-range queries
- Fast partition drops for retention (instant vs. slow DELETE)
- Smaller index sizes per partition

### 10.4 Read Replica Strategy (at Phase 4: 15,000+ DAU)

| Query Type | Target |
|---|---|
| User history | Read replica |
| Analytics aggregations | Read replica |
| Admin dashboard | Read replica |
| User upsert, download insert, job updates | Primary |
| Cache lookups (for decision-making) | Primary (consistency required) |

### 10.5 Vacuuming Notes

| Table | Autovacuum Tuning |
|---|---|
| `users` | Default settings. Moderate update frequency. |
| `downloads` | Increase `autovacuum_vacuum_scale_factor` to 0.05 (from default 0.2). High insert volume. |
| `jobs` | Increase `autovacuum_vacuum_scale_factor` to 0.05. High update frequency (status transitions). |
| `active_downloads` | Set `autovacuum_vacuum_threshold` to 50. Small table with high insert/delete churn. |
| `cached_files` | Default. Low update frequency. |

---

## 11. Future Expansion Notes

### 11.1 Future Reserved Tables

These tables are NOT implemented in V1. They are documented here for future planning to ensure the current schema is compatible.

---

#### 11.1.1 `payments` (Future)

```
(future) payments
  - id                    BIGINT PK
  - user_id               BIGINT FK → users.id
  - provider              VARCHAR(30)     -- stripe, yookassa, crypto, telegram_stars
  - provider_payment_id   VARCHAR(255)
  - amount                DECIMAL(10,2)
  - currency              VARCHAR(10)
  - status                VARCHAR(30)     -- pending, completed, failed, refunded
  - metadata_json         JSONB
  - created_at            TIMESTAMPTZ
  - completed_at          TIMESTAMPTZ
```

**Integration point:** On successful payment, update `users.is_premium = true` and `users.premium_expires_at = NOW() + plan.duration`.

---

#### 11.1.2 `subscriptions` (Future)

```
(future) subscriptions
  - id                    BIGINT PK
  - user_id               BIGINT FK → users.id
  - plan_id               BIGINT FK → premium_plans.id
  - status                VARCHAR(30)     -- active, expired, cancelled
  - started_at            TIMESTAMPTZ
  - expires_at            TIMESTAMPTZ
  - payment_id            BIGINT FK → payments.id
  - cancelled_at          TIMESTAMPTZ
```

**Prerequisite:** Requires `premium_plans` table (future).

```
(future) premium_plans
  - id                    BIGINT PK
  - name                  VARCHAR(100)
  - duration_days          INTEGER
  - price                 DECIMAL(10,2)
  - currency              VARCHAR(10)
  - max_daily_downloads   INTEGER
  - max_file_size         BIGINT
  - features_json         JSONB
  - is_active             BOOLEAN
```

---

#### 11.1.3 `referrals` (Future)

```
(future) referrals
  - id                    BIGINT PK
  - referrer_id           BIGINT FK → users.id
  - referred_id           BIGINT FK → users.id
  - bonus_type            VARCHAR(30)
  - bonus_value           INTEGER
  - status                VARCHAR(30)     -- pending, credited, expired
  - created_at            TIMESTAMPTZ

(future) referral_codes
  - id                    BIGINT PK
  - user_id               BIGINT FK → users.id
  - code                  VARCHAR(50) UNIQUE
  - usage_count           INTEGER DEFAULT 0
  - max_uses              INTEGER
  - is_active             BOOLEAN
  - created_at            TIMESTAMPTZ
```

**Integration point:** Add `referred_by BIGINT FK → users.id NULLABLE` to `users` table.

---

#### 11.1.4 `audit_logs` (Future)

```
(future) audit_logs
  - id                    BIGINT PK
  - actor_id              BIGINT FK → users.id
  - action                VARCHAR(100)    -- user_banned, setting_changed, ad_created, ...
  - target_type           VARCHAR(50)     -- user, setting, advertisement, ...
  - target_id             VARCHAR(255)
  - details_json          JSONB
  - created_at            TIMESTAMPTZ
```

**Purpose:** Full admin action audit trail. Records who did what, when, and to what.

---

#### 11.1.5 `group_settings` (Future)

```
(future) group_settings
  - id                    BIGINT PK
  - telegram_group_id     BIGINT UNIQUE
  - group_name            VARCHAR(255)
  - is_enabled            BOOLEAN DEFAULT true
  - daily_limit           INTEGER
  - added_by              BIGINT FK → users.id
  - created_at            TIMESTAMPTZ
  - updated_at            TIMESTAMPTZ
```

**Purpose:** Per-group configuration when the bot is added to Telegram groups.

---

#### 11.1.6 `analytics_snapshots` (Future)

```
(future) daily_stats
  - date                  DATE PK
  - total_downloads       INTEGER
  - unique_users          INTEGER
  - new_users             INTEGER
  - jobs_created          INTEGER
  - jobs_completed        INTEGER
  - jobs_failed           INTEGER
  - cache_hits            INTEGER
  - cache_misses          INTEGER
  - errors_count          INTEGER

(future) platform_daily_stats
  - date                  DATE
  - platform              VARCHAR(50)
  - download_count        INTEGER
  - unique_users          INTEGER
  - PK(date, platform)
```

**Purpose:** Pre-aggregated analytics. Populated by a nightly ETL job. Avoids expensive real-time aggregations on `downloads` (18M+ rows at scale).

---

### 11.2 Schema Compatibility Matrix

This matrix shows which future features can be added WITHOUT modifying existing tables:

| Future Feature | New Tables | Existing Table Changes | Schema-Compatible? |
|---|---|---|---|
| Premium subscriptions | `premium_plans`, `subscriptions` | None — `users.is_premium` and `premium_expires_at` already exist | ✅ Yes |
| Payments | `payments` | None | ✅ Yes |
| Referrals | `referrals`, `referral_codes` | Add `referred_by` column to `users` | ✅ Yes (minor ALTER) |
| Multi-language | None | None — `user_preferences.preferred_language` already exists | ✅ Yes |
| Group support | `group_settings` | None | ✅ Yes |
| Analytics dashboard | `daily_stats`, `platform_daily_stats` | None — all source data already exists | ✅ Yes |
| Web dashboard | None | None — FastAPI admin API + existing schema | ✅ Yes |
| Multiple download engines | None | None — `media_metadata.platform` already identifies the engine | ✅ Yes |
| Audit logging | `audit_logs` | None | ✅ Yes |
| Ad analytics persistence | None | Add `impressions`, `clicks` columns to `advertisements` | ✅ Yes (minor ALTER) |

---

## 12. Design Decision Log

Every non-obvious design decision is documented here with its rationale. This log ensures future developers understand **why** the schema looks the way it does, not just **what** it contains.

### 12.1 Why 11 Tables?

| Table | Exists Because |
|---|---|
| **`users`** | Core identity table. Every authorization check, rate limit, download counter, and history query starts here. |
| **`media_metadata`** | **Normalization.** Without it, title, duration, platform, and thumbnail would be duplicated across `jobs`, `cached_files`, and `downloads`. 1,000 downloads = 1,000 metadata copies. This table stores it once. |
| **`cached_files`** | **Separation of cache from history.** The single, global, user-independent source of truth for Telegram file IDs. Cache can be evicted without affecting history. History can be deleted without destroying cache. |
| **`downloads`** | **User action log.** Records who downloaded what and when. Used for history display, analytics, and Premium usage tracking. Never stores file IDs directly. |
| **`jobs`** | **Work unit tracking.** Queue system needs persistent status, retry, timing, and error records. Required for monitoring, debugging, and admin dashboard. |
| **`active_downloads`** | **Durable deduplication.** Redis locks are volatile. This table's `UNIQUE` constraint prevents duplicate downloads even if Redis loses state. Enables multi-user fan-out. |
| **`broadcasts`** | **Audit and tracking.** Delivery tracking for mass messages. Without it, no way to know what was sent or how many deliveries succeeded. |
| **`advertisements`** | **Revenue and engagement.** Database-driven ad system. Admins manage ads without code changes. Supports frequency control, targeting, and global kill switch. |
| **`settings`** | **Runtime configuration.** Rate limits, file size limits, maintenance mode — all changeable without redeployment. |
| **`error_logs`** | **Internal diagnostics.** Queryable error history independent of Sentry. For admin dashboards and per-user error inspection. |
| **`user_preferences`** | **Extension point.** Keeps the high-traffic `users` table lean. Clean place for future settings without widening the core table. |

### 12.2 Why History and Cache Are Separate Tables

This is the single most important design decision in the schema.

```
WRONG (old design):
┌──────────────────────────────┐
│       download_records       │  ← Cache AND history in one table
│──────────────────────────────│
│ user_id                      │  ← User-specific
│ telegram_file_id             │  ← Cache (should be global)
│ title, duration, platform    │  ← Metadata (duplicated per row)
│ created_at                   │
└──────────────────────────────┘
  Problem: Delete user history → lose cached file_id
  Problem: 1000 downloads of same video → 1000 copies of file_id + metadata

RIGHT (current design):
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  downloads   │────►│  cached_files    │────►│  media_metadata  │
│  (history)   │     │  (global cache)  │     │  (stored once)   │
│──────────────│     │──────────────────│     │──────────────────│
│ user_id      │     │ telegram_file_id │     │ title            │
│ cached_file_id     │ media_id         │     │ duration         │
│ status       │     │ format, quality  │     │ platform         │
│ created_at   │     │ usage_count      │     │ video_id         │
└──────────────┘     └──────────────────┘     └──────────────────┘
  ✓ Delete history → cache survives
  ✓ Purge cache → history survives (resend falls back to new download)
  ✓ 1000 downloads → 1 metadata row, 1 cache row, 1000 history rows
```

### 12.3 Why Ban Fields Live on `users` (Not a Separate Table)

| Approach | Query Pattern | Latency |
|---|---|---|
| Separate `banned_users` table | `SELECT ... FROM users u LEFT JOIN banned_users b ON b.user_id = u.id` | JOIN on every request |
| Fields on `users` table | `SELECT ... FROM users WHERE telegram_id = ?` (already fetched) | Zero additional queries |

The bot checks ban status on **every incoming Telegram update**. At 20,000 DAU, that's potentially millions of checks per day. A JOIN adds measurable latency. Since ban is a simple boolean check on data already being read, it belongs on the `users` table.

Audit trail: When a user is unbanned, `is_banned = false` but `banned_at` and `ban_reason` are **preserved**. They are only overwritten when a new ban is applied.

### 12.4 Why `daily_download_count` is a Denormalized Counter

**Alternative:** `SELECT COUNT(*) FROM downloads WHERE user_id = ? AND created_at >= today`

**Problem:** At 50,000 downloads/day, this aggregation scans thousands of rows. It's performed on every download request (rate limiting). Unacceptable latency.

**Solution:** `daily_download_count` on `users` is updated atomically: `SET daily_download_count = daily_download_count + 1`. A nightly scheduled job resets it: `UPDATE users SET daily_download_count = 0`.

**Tradeoff:** Counter may drift if a download is recorded but the counter update fails (crash between operations). This is acceptable — the counter is a rate limiter, not an auditable financial record. The `downloads` table is the authoritative history.

### 12.5 Why Settings Uses Key-Value Instead of a Typed Table

**Alternative:** `settings(id, name, value_int, value_bool, value_text, type)`

**Problem:** Adds complexity (which column to read?), requires type dispatch in application layer regardless, and wastes storage (3 NULL columns per row).

**Solution:** `settings(key PK, value TEXT, updated_at)`. Application parses `value` to the expected type. Schema stays simple. The number of settings is small (< 20 rows) — there is no performance concern.

### 12.6 Why `jobs.id` is UUID While Others Use BIGINT

Jobs are referenced in user-facing messages ("Your download #abc-123 is processing..."). Using sequential BIGINT would allow users to:
1. Enumerate total system usage (privacy concern)
2. Guess other users' job IDs

UUIDs prevent both issues. Other tables use BIGINT because their IDs are never exposed to users.

### 12.7 Why `metadata_json` Uses JSONB Instead of Additional Columns

Platform-specific metadata varies wildly:
- YouTube: `view_count`, `like_count`, `channel_name`, `description`, `tags[]`
- TikTok: `like_count`, `comment_count`, `share_count`, `author`
- Instagram: `media_type`, `carousel_count`, `is_reel`

Creating columns for all possible fields across all platforms would require:
- Dozens of nullable columns
- A migration every time a new platform is added
- Sparse data (most columns NULL for most rows)

`JSONB` stores the full yt-dlp output per media, queryable and indexable, without schema rigidity.

---

> **End of Database Architecture Reference**
>
> This document is the permanent database source of truth for the Telegram SaaS Download Bot. All database implementation (models, migrations, repositories) must conform to this specification. Changes to this document require database architect review.
>
> **Revision History:**
> - v1.0 (2026-06-22): Initial database architecture reference — 11 production tables, 42 indexes, 12 foreign keys, 5 unique constraints, 6 future reserved tables

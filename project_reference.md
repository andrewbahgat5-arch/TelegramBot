# Telegram SaaS Download Bot — Master Architecture Reference

> **Document Status:** Canonical · Single Source of Truth
> **Last Updated:** 2026-06-22
> **Architecture Version:** 1.2

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Technology Stack](#3-technology-stack)
4. [Architecture Principles](#4-architecture-principles)
5. [Directory Structure](#5-directory-structure)
6. [Component Responsibilities](#6-component-responsibilities)
7. [Service Boundaries](#7-service-boundaries)
8. [Data Flow](#8-data-flow)
9. [Queue Flow](#9-queue-flow)
10. [Cache Flow](#10-cache-flow)
11. [Error Handling Flow](#11-error-handling-flow)
12. [Database Architecture](#12-database-architecture)
13. [Role-Based Access Control](#13-role-based-access-control)
14. [Logging Strategy](#14-logging-strategy)
15. [Monitoring Strategy](#15-monitoring-strategy)
16. [Security Principles](#16-security-principles)
17. [Future Scalability Strategy](#17-future-scalability-strategy)
18. [Configuration Management](#18-configuration-management)
19. [Deployment Architecture](#19-deployment-architecture)
20. [Glossary](#20-glossary)
21. [Admin Panel V1 Requirements](#21-admin-panel-v1-requirements)
22. [Smart Advertisement System](#22-smart-advertisement-system)
23. [Future Features Roadmap](#23-future-features-roadmap)

---

## 1. System Overview

### 1.1 Purpose

A production-grade Telegram SaaS Download Bot that allows users to submit media URLs, select format and quality, and receive downloaded files directly in Telegram. The system caches Telegram `file_id` values to enable instant re-delivery of previously downloaded content and maintains a full download history per user.

### 1.2 Target Scale

| Metric | Initial Launch | Target Scale |
|---|---|---|
| Daily Active Users | 100 – 1,000 | 20,000 |
| Monthly Active Users | — | 300,000 |

### 1.3 Core Capabilities

- Accept media URLs from users via Telegram.
- Analyze URLs and present available formats/qualities.
- Queue-based download processing with adjustable worker count.
- Deliver downloaded files back to Telegram.
- Cache Telegram `file_id` for instant re-delivery of identical content.
- Maintain rich download history (not link-only) with instant resend capability.
- Prevent duplicate concurrent downloads of the same resource.
- Role-based access control (Owner, Moderator, User).
- Production-grade logging, monitoring, and error tracking.
- Future-ready for Premium tier and horizontal scaling.

---

## 2. Architecture Overview

### 2.1 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TELEGRAM CLOUD                               │
│                     (Bot API / Webhooks)                             │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      BOT LAYER (Aiogram 3)                          │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Handlers │  │  Middlewares  │  │   Keyboards  │  │  Filters   │  │
│  │  (thin)  │  │              │  │              │  │            │  │
│  └────┬─────┘  └──────────────┘  └──────────────┘  └────────────┘  │
│       │  Delegates to service layer — no business logic here        │
└───────┼─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SERVICE LAYER                                  │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ URL Analyzer │  │  Job Service │  │  History / Cache Service │   │
│  │   Service    │  │              │  │                          │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘   │
│         │                 │                      │                   │
└─────────┼─────────────────┼──────────────────────┼───────────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       QUEUE LAYER (Redis)                           │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │                  Job Queue (priority-aware)                 │     │
│  └──────────────────────────┬──────────────────────────────────┘     │
│                             │                                       │
│  ┌──────────┐ ┌──────────┐ │ ┌──────────┐  (adjustable count)      │
│  │ Worker 1 │ │ Worker 2 │ │ │ Worker N │                           │
│  └──────────┘ └──────────┘ │ └──────────┘                           │
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐    ┌──────────────────┐
│  yt-dlp +    │   │  PostgreSQL  │    │  Redis Cache     │
│  FFmpeg      │   │  (storage)   │    │  (file_id,       │
│  (download)  │   │              │    │   metadata,      │
│              │   │              │    │   locks)         │
└──────────────┘   └──────────────┘    └──────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     ADMIN / API LAYER (FastAPI)                      │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ Health Check │  │  Admin API   │  │  Monitoring Endpoints    │   │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY                                    │
│                                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌─────────────┐                   │
│  │  Sentry  │  │  Uptime Kuma │  │  Structured │                   │
│  │  (errors)│  │  (uptime)    │  │  Logging    │                   │
│  └──────────┘  └──────────────┘  └─────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Architectural Style

The system follows **Clean Architecture** principles adapted for a Python service:

```
Handlers / API Controllers  (outer ring — frameworks & drivers)
        │
        ▼
   Service Layer            (use cases / application logic)
        │
        ▼
  Domain Models / Entities  (enterprise business rules)
        │
        ▼
 Repository / Gateway       (interface adapters)
        │
        ▼
Infrastructure              (frameworks, DB, Redis, yt-dlp, Telegram API)
```

**Dependency Rule:** Dependencies point inward only. Inner layers never import from outer layers. Outer layers depend on abstractions (protocols / abstract base classes) defined in inner layers.

---

## 3. Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Runtime | Python | 3.13 | Application runtime |
| Telegram Framework | Aiogram | 3.x | Telegram Bot API interaction |
| HTTP / Admin API | FastAPI | latest | Health checks, admin endpoints, monitoring |
| Database | PostgreSQL | 15+ | Persistent data storage |
| ORM | SQLAlchemy | 2.0 | Database access, async sessions |
| Migrations | Alembic | latest | Schema migrations |
| Cache / Queue | Redis | 7+ | Caching, job queue, download locks |
| Downloader | yt-dlp | latest | Media extraction and download |
| Media Processing | FFmpeg | latest | Audio/video transcoding |
| Error Tracking | Sentry | latest SDK | Exception aggregation & alerting |
| Uptime Monitoring | Uptime Kuma | latest | Service availability monitoring |

### 3.1 Supporting Libraries (Expected)

| Library | Purpose |
|---|---|
| `pydantic` / `pydantic-settings` | Configuration validation, data schemas |
| `structlog` | Structured JSON logging |
| `uvicorn` | ASGI server for FastAPI |
| `aiohttp` | Async HTTP (Aiogram's transport) |
| `asyncpg` | Async PostgreSQL driver for SQLAlchemy |
| `redis.asyncio` (`redis[hiredis]`) | Async Redis client |
| `tenacity` | Retry logic |
| `orjson` | Fast JSON serialization |

---

## 4. Architecture Principles

### 4.1 Thin Bot Layer

Telegram handlers are thin dispatchers. They:

- Parse incoming updates.
- Extract parameters.
- Call the appropriate service method.
- Format and return the service response.

Handlers contain **zero** business logic. No database queries, no cache lookups, no download orchestration.

### 4.2 Service-Owned Business Logic

All business rules, validation, orchestration, and decision-making live in the **Service Layer**. Services are framework-agnostic — they do not import Aiogram or FastAPI types.

### 4.3 Queue-Based Architecture

Downloads are never processed inline. Every download request produces a **Job** that enters the Redis-backed queue. Workers consume jobs asynchronously. This decouples request acceptance from resource-intensive processing.

### 4.4 Adjustable Worker Count

The number of concurrent download workers is configurable via environment variables and can be changed at deployment time without code changes. Each worker is an independent asyncio task (or process) consuming from the shared queue.

### 4.5 Horizontal Scaling Readiness

All state is externalized (PostgreSQL, Redis). No in-process state is assumed to be authoritative. This allows future deployment of multiple bot instances and worker pools behind a shared Redis queue and PostgreSQL database without architectural changes.

### 4.6 Production-Grade Logging

Every significant operation emits structured log entries with correlation IDs. Logs are machine-parseable (JSON) and human-readable in development.

### 4.7 Production-Grade Monitoring

Health checks, queue depth metrics, worker status, error rates, and uptime are continuously monitored. Alerts fire on anomalies.

### 4.8 Modular Architecture

Each concern is encapsulated in its own module with clear public interfaces. Modules communicate through well-defined service interfaces, not through shared mutable state.

### 4.9 Clean Architecture Dependency Rule

Inner layers define abstractions (protocols/ABCs). Outer layers implement them. No inner layer imports a concrete outer-layer class.

### 4.10 Future Premium System Readiness

The data model, role system, and service interfaces are designed to accommodate a Premium tier (rate limits, priority queues, extended history, higher quality limits) without structural refactoring.

---

## 5. Directory Structure

```
project_root/
│
├── bot/                          # Telegram Bot Layer
│   ├── __init__.py
│   ├── main.py                   # Bot entry point, dispatcher setup
│   ├── handlers/                 # Thin Aiogram handlers
│   │   ├── __init__.py
│   │   ├── start.py              # /start, /help commands
│   │   ├── download.py           # URL submission, format/quality selection
│   │   ├── history.py            # History browsing, resend
│   │   ├── admin.py              # Admin/moderator commands
│   │   └── errors.py             # Global error handler for updates
│   ├── middlewares/               # Aiogram middlewares
│   │   ├── __init__.py
│   │   ├── auth.py               # Role verification middleware
│   │   ├── throttle.py           # Rate limiting middleware
│   │   ├── logging.py            # Request logging middleware
│   │   └── db_session.py         # Database session injection
│   ├── keyboards/                 # Inline & reply keyboards
│   │   ├── __init__.py
│   │   ├── format_select.py      # Format selection keyboard
│   │   ├── quality_select.py     # Quality selection keyboard
│   │   ├── history.py            # History pagination keyboard
│   │   └── confirm.py            # Confirmation keyboards
│   ├── filters/                   # Custom Aiogram filters
│   │   ├── __init__.py
│   │   ├── url_filter.py         # URL detection filter
│   │   └── role_filter.py        # Role-based access filter
│   └── callbacks/                 # Callback query data schemas
│       ├── __init__.py
│       └── factory.py            # Callback data factories
│
├── services/                     # Service Layer (Business Logic)
│   ├── __init__.py
│   ├── url_analyzer.py           # URL analysis, metadata extraction
│   ├── job_service.py            # Job creation, status tracking
│   ├── download_service.py       # Download orchestration
│   ├── history_service.py        # Download history management
│   ├── cache_service.py          # Cache operations (file_id, metadata)
│   ├── user_service.py           # User registration, role management
│   ├── queue_service.py          # Queue operations interface
│   └── notification_service.py   # User notification delivery
│
├── workers/                      # Queue Workers
│   ├── __init__.py
│   ├── main.py                   # Worker pool entry point
│   ├── download_worker.py        # Download job processor
│   └── cleanup_worker.py         # Temp file / stale job cleanup
│
├── domain/                       # Domain Layer (Entities & Value Objects)
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── user.py               # User entity
│   │   ├── job.py                # Download job entity
│   │   ├── download_record.py    # History record entity
│   │   └── media_info.py         # Media metadata entity
│   ├── enums/
│   │   ├── __init__.py
│   │   ├── job_status.py         # JobStatus enum
│   │   ├── media_format.py       # MediaFormat enum
│   │   ├── user_role.py          # UserRole enum
│   │   └── quality.py            # Quality enum
│   ├── exceptions.py             # Domain-specific exceptions
│   └── protocols/                # Abstract interfaces (protocols)
│       ├── __init__.py
│       ├── repository.py         # Repository protocols
│       ├── cache.py              # Cache protocols
│       └── queue.py              # Queue protocols
│
├── infrastructure/               # Infrastructure Layer
│   ├── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── engine.py             # SQLAlchemy async engine setup
│   │   ├── session.py            # Session factory
│   │   ├── models/               # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # Declarative base, mixins
│   │   │   ├── user.py           # User table model
│   │   │   ├── job.py            # Job table model
│   │   │   └── download_record.py# Download history table model
│   │   └── repositories/         # Concrete repository implementations
│   │       ├── __init__.py
│   │       ├── user_repo.py
│   │       ├── job_repo.py
│   │       └── history_repo.py
│   ├── redis/
│   │   ├── __init__.py
│   │   ├── client.py             # Redis connection manager
│   │   ├── cache.py              # Cache implementation
│   │   ├── queue.py              # Job queue implementation
│   │   └── locks.py              # Distributed lock implementation
│   ├── downloader/
│   │   ├── __init__.py
│   │   ├── ytdlp_client.py       # yt-dlp wrapper
│   │   └── ffmpeg_client.py      # FFmpeg wrapper
│   └── telegram/
│       ├── __init__.py
│       └── file_sender.py        # Telegram file upload abstraction
│
├── api/                          # FastAPI Admin/Health Layer
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entry point
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── health.py             # Health check endpoints
│   │   ├── admin.py              # Admin API endpoints
│   │   └── metrics.py            # Metrics / stats endpoints
│   └── dependencies.py           # FastAPI dependency injection
│
├── core/                         # Cross-Cutting Concerns
│   ├── __init__.py
│   ├── config.py                 # Pydantic settings / env config
│   ├── logging.py                # Structured logging setup
│   ├── sentry.py                 # Sentry SDK initialization
│   └── constants.py              # Application-wide constants
│
├── migrations/                   # Alembic Migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── tests/                        # Test Suite
│   ├── __init__.py
│   ├── conftest.py               # Shared fixtures
│   ├── unit/
│   │   ├── services/
│   │   ├── domain/
│   │   └── infrastructure/
│   ├── integration/
│   │   ├── database/
│   │   ├── redis/
│   │   └── api/
│   └── e2e/
│
├── alembic.ini                   # Alembic configuration
├── pyproject.toml                # Project metadata & dependencies
├── Dockerfile                    # Production container image
├── docker-compose.yml            # Local development stack
├── .env.example                  # Environment variable template
└── project_reference.md          # THIS FILE — master architecture doc
```

---

## 6. Component Responsibilities

### 6.1 Bot Layer (`bot/`)

| Component | Responsibility |
|---|---|
| **Handlers** | Receive Telegram updates, extract parameters, delegate to services, format responses. **No business logic.** |
| **Middlewares** | Cross-cutting concerns executed on every update: authentication, rate limiting, session injection, request logging. |
| **Keyboards** | Build inline and reply keyboards for format selection, quality selection, history pagination, and confirmations. |
| **Filters** | Custom Aiogram filters for URL detection, role-based access gating, and message type routing. |
| **Callbacks** | Define callback data schemas and factories for type-safe callback query parsing. |

### 6.2 Service Layer (`services/`)

| Service | Responsibility |
|---|---|
| **URLAnalyzerService** | Accepts a URL, invokes yt-dlp metadata extraction (via infrastructure), validates the URL, returns structured media info with available formats and qualities. Checks metadata cache first. |
| **JobService** | Creates download jobs, assigns priority, checks for duplicates, tracks job status transitions, provides job lookup. |
| **DownloadService** | Orchestrates the full download lifecycle: invokes yt-dlp download, handles FFmpeg post-processing, invokes file sending, updates cache with `file_id`, creates history record. |
| **HistoryService** | Manages download history per user. Provides paginated history retrieval. Supports instant resend by looking up cached `file_id` from the history record. |
| **CacheService** | Abstracts all cache operations: `file_id` lookup/store, metadata cache lookup/store, download lock acquire/release. |
| **UserService** | Manages user registration (on first `/start`), role assignment, user lookup, ban/unban. |
| **QueueService** | Enqueues jobs, dequeues jobs, provides queue depth, manages priority ordering. |
| **NotificationService** | Sends status updates to users (job started, progress, completed, failed) via the Telegram bot instance. |

### 6.3 Worker Layer (`workers/`)

| Worker | Responsibility |
|---|---|
| **DownloadWorker** | Long-running consumer. Dequeues jobs from Redis, invokes `DownloadService`, handles retries and failure reporting. Runs as N concurrent tasks/processes (configurable). |
| **CleanupWorker** | Periodic task. Removes stale temporary files, marks timed-out jobs as failed, purges expired cache entries. |

### 6.4 Domain Layer (`domain/`)

| Component | Responsibility |
|---|---|
| **Entities** | Pure data classes representing core business objects (User, Job, DownloadRecord, MediaInfo). No framework dependencies. |
| **Enums** | Strongly-typed enumerations for job statuses, media formats, user roles, quality levels. |
| **Exceptions** | Domain-specific exception hierarchy (e.g., `URLNotSupportedError`, `DuplicateDownloadError`, `QuotaExceededError`). |
| **Protocols** | Abstract interfaces (Python `Protocol` classes) defining contracts for repositories, cache, and queue. Infrastructure layer provides concrete implementations. |

### 6.5 Infrastructure Layer (`infrastructure/`)

| Component | Responsibility |
|---|---|
| **Database (engine, session, models, repositories)** | SQLAlchemy 2.0 async engine/session management. ORM models mapped to PostgreSQL tables. Repository classes implement domain protocols for data access. |
| **Redis (client, cache, queue, locks)** | Redis connection management. Concrete implementations of cache protocol (file_id, metadata), queue protocol (job enqueue/dequeue with priority), and distributed locking. |
| **Downloader (ytdlp_client, ffmpeg_client)** | Thin wrappers around yt-dlp and FFmpeg CLIs. Handle process invocation, output parsing, error translation into domain exceptions. |
| **Telegram (file_sender)** | Abstraction over Aiogram's file-sending methods. Handles large file chunking, retry logic, and `file_id` extraction from Telegram's response. |

### 6.6 API Layer (`api/`)

| Component | Responsibility |
|---|---|
| **Health Routes** | `/health` — liveness probe. `/ready` — readiness probe (checks DB + Redis connectivity). Used by Uptime Kuma and container orchestrators. |
| **Admin Routes** | Protected endpoints for user management, job inspection, queue management, system stats. Authenticated via API key or internal token. |
| **Metrics Routes** | Expose operational metrics: queue depth, active workers, download counts, error rates, cache hit ratios. |

### 6.7 Core (`core/`)

| Component | Responsibility |
|---|---|
| **Config** | Central configuration loaded from environment variables via Pydantic Settings. Single source of truth for all tunables. |
| **Logging** | Structured logging setup with `structlog`. Configures JSON output for production, human-readable for development. Injects correlation IDs. |
| **Sentry** | Sentry SDK initialization. Configures DSN, environment, sample rates, integrations (Aiogram, FastAPI, SQLAlchemy). |
| **Constants** | Application-wide magic values: max file sizes, timeout durations, retry counts, cache TTLs. |

---

## 7. Service Boundaries

### 7.1 Boundary Rules

Each layer has strict import rules enforcing the Clean Architecture dependency rule:

```
┌────────────────────────────────────────────────────────────┐
│ Layer               │ May Import From                      │
├─────────────────────┼──────────────────────────────────────┤
│ bot/                │ services/, domain/, core/            │
│ api/                │ services/, domain/, core/            │
│ services/           │ domain/, core/                       │
│ workers/            │ services/, domain/, core/            │
│ domain/             │ core/ (constants only)               │
│ infrastructure/     │ domain/, core/                       │
│ core/               │ (no project imports — leaf layer)    │
└────────────────────────────────────────────────────────────┘
```

### 7.2 Dependency Injection Strategy

Services receive their infrastructure dependencies via **constructor injection**. The application entry points (bot `main.py`, worker `main.py`, API `main.py`) are responsible for wiring — constructing infrastructure implementations and injecting them into services.

```
Entry point creates:
  redis_client  = RedisClient(config)
  db_session    = SessionFactory(config)
  cache         = RedisCache(redis_client)          # implements CacheProtocol
  queue         = RedisQueue(redis_client)           # implements QueueProtocol
  user_repo     = UserRepository(db_session)         # implements UserRepoProtocol
  job_repo      = JobRepository(db_session)          # implements JobRepoProtocol
  history_repo  = HistoryRepository(db_session)      # implements HistoryRepoProtocol

Entry point injects:
  url_service      = URLAnalyzerService(cache, ytdlp_client)
  job_service      = JobService(job_repo, queue, cache)
  download_service = DownloadService(ytdlp_client, ffmpeg_client, file_sender, cache, history_repo)
  history_service  = HistoryService(history_repo, cache)
  user_service     = UserService(user_repo)
```

### 7.3 Inter-Service Communication

Services do **not** call each other directly in the hot path. Communication patterns:

| Pattern | When Used |
|---|---|
| **Direct method call** | Handler → Service (always synchronous within the request) |
| **Queue** | Service → Worker (job enqueue → worker dequeue) |
| **Shared cache** | Services share data via Redis cache (file_id, metadata) |
| **Shared database** | Services share state via PostgreSQL (job status, history) |

Services may reference other services only at the orchestration level within the same request context (e.g., a handler may call `job_service` then `notification_service`). Deep inter-service nesting is avoided.

---

## 8. Data Flow

### 8.1 Primary User Flow — Complete Download

```
Step  Actor            Action                                    Target
─────────────────────────────────────────────────────────────────────────
 1    User             Sends a URL                               Bot
 2    Bot Handler      Receives message, extracts URL            URLAnalyzerService
 3    URLAnalyzerService  Checks metadata cache                  Redis (metadata cache)
 4a   [Cache HIT]      Returns cached metadata                   Bot Handler
 4b   [Cache MISS]     Calls yt-dlp extract_info                 yt-dlp
 5    URLAnalyzerService  Caches metadata, returns formats       Redis + Bot Handler
 6    Bot Handler      Presents format selection keyboard        User
 7    User             Selects format                            Bot
 8    Bot Handler      Presents quality selection keyboard       User
 9    User             Selects quality                           Bot
10    Bot Handler      Calls JobService.create_job()             JobService
11    JobService       Checks file_id cache for exact match      Redis (file_id cache)
12a   [Cache HIT]      Returns cached file_id → instant send     User (skip to step 19)
12b   [Cache MISS]     Checks for duplicate active download      Redis (download lock)
13a   [Duplicate]      Attaches user to existing job listener    Redis pub/sub or polling
13b   [No duplicate]   Acquires download lock, enqueues job      Redis queue + lock
14    Worker           Dequeues job from priority queue          Redis queue
15    Worker           Invokes DownloadService.process()         DownloadService
16    DownloadService  Downloads via yt-dlp                      yt-dlp + FFmpeg
17    DownloadService  Sends file to Telegram                    Telegram API
18    DownloadService  Extracts file_id from Telegram response   Telegram API response
19    DownloadService  Caches file_id                            Redis (file_id cache)
20    DownloadService  Creates history record                    PostgreSQL
21    DownloadService  Releases download lock                    Redis (lock)
22    Worker           Marks job complete                        PostgreSQL + Redis
23    NotificationService  Notifies user of completion           Telegram (message)
```

### 8.2 Instant Resend Flow (From History)

```
Step  Actor            Action                                    Target
─────────────────────────────────────────────────────────────────────────
 1    User             Opens history (/history)                  Bot
 2    Bot Handler      Calls HistoryService.get_history()        HistoryService
 3    HistoryService   Queries paginated history                 PostgreSQL
 4    Bot Handler      Presents history with resend buttons      User
 5    User             Taps "Resend"                             Bot
 6    Bot Handler      Calls HistoryService.resend()             HistoryService
 7    HistoryService   Looks up file_id from history record      PostgreSQL + Redis cache
 8a   [file_id valid]  Sends file using cached file_id           Telegram API
 8b   [file_id stale]  Creates new download job                  JobService (back to §8.1)
```

### 8.3 Data Flow — Format Selection Detail

```
URL received
    │
    ▼
┌─────────────────────────┐
│  URLAnalyzerService     │
│                         │
│  1. Validate URL format │
│  2. Check metadata cache│
│  3. Extract info (yt-dlp│
│     if cache miss)      │
│  4. Parse available     │
│     formats & qualities │
│  5. Cache metadata      │
│  6. Return MediaInfo    │
└────────┬────────────────┘
         │
         ▼
    MediaInfo contains:
    ├── title: str
    ├── duration: int (seconds)
    ├── thumbnail_url: str
    ├── source_platform: str
    ├── formats: List[FormatOption]
    │       ├── format_id: str
    │       ├── format_type: MediaFormat (video/audio)
    │       ├── extension: str
    │       ├── quality: str
    │       ├── file_size_approx: int (bytes)
    │       └── codec: str
    └── original_url: str
```

---

## 9. Queue Flow

### 9.1 Queue Architecture

```
                    Producers                              Consumers
              ┌──────────────────┐                  ┌──────────────────┐
              │   Bot Handlers   │                  │   Worker Pool    │
              │   (via JobService│                  │   (N workers)    │
              │    .create_job) │                  │                  │
              └────────┬─────────┘                  └────────┬─────────┘
                       │                                     │
                       ▼                                     │
              ┌──────────────────────────────────────────────┐
              │              Redis Queue                      │
              │                                              │
              │  ┌────────────────────────────────────────┐  │
              │  │  Priority Queue (Sorted Set)           │  │
              │  │                                        │  │
              │  │  Score = priority_weight + timestamp    │  │
              │  │                                        │  │
              │  │  Members = serialized Job references    │  │
              │  └────────────────────────────────────────┘  │
              │                                              │
              │  ┌────────────────────────────────────────┐  │
              │  │  Active Jobs Set                       │  │
              │  │  (currently being processed)           │  │
              │  └────────────────────────────────────────┘  │
              │                                              │
              │  ┌────────────────────────────────────────┐  │
              │  │  Job Data Hash                         │  │
              │  │  (job_id → serialized job details)     │  │
              │  └────────────────────────────────────────┘  │
              └──────────────────────────────────────────────┘
```

### 9.2 Job Lifecycle States

```
    CREATED
       │
       ▼
    QUEUED ──────────────────┐
       │                     │ (timeout or system restart)
       ▼                     │
   PROCESSING ───────────────┤
       │         │           │
       ▼         ▼           ▼
  COMPLETED   FAILED      TIMED_OUT
                 │
                 ▼
            RETRY_QUEUED ──→ QUEUED (max 3 retries)
                 │
                 ▼
          PERMANENTLY_FAILED
```

| Status | Description |
|---|---|
| `CREATED` | Job entity created, not yet enqueued |
| `QUEUED` | Job placed in Redis priority queue |
| `PROCESSING` | Worker has dequeued and is actively processing |
| `COMPLETED` | Download finished, file delivered to user |
| `FAILED` | Processing failed (transient error), eligible for retry |
| `RETRY_QUEUED` | Re-enqueued after failure, retry count incremented |
| `TIMED_OUT` | Worker did not complete within the deadline |
| `PERMANENTLY_FAILED` | Max retries exhausted or non-retryable error |

### 9.3 Priority System

| Priority Level | Score Weight | Description |
|---|---|---|
| `HIGH` | 0 | (Reserved for future Premium users) |
| `NORMAL` | 1000 | Standard user requests |
| `LOW` | 2000 | Bulk/retry jobs |

**Score formula:** `score = priority_weight + unix_timestamp`

Lower score = dequeued first. Within the same priority, earlier jobs are processed first (FIFO within priority band).

### 9.4 Worker Pool Management

- Worker count is set via `WORKER_COUNT` environment variable (default: 3).
- Each worker is an independent asyncio task running in the worker process.
- Workers use `BRPOPLPUSH` (or `BZPOPMIN` for sorted sets) for blocking dequeue with atomic move to active set.
- A worker heartbeat mechanism writes a timestamp to Redis every N seconds. The cleanup worker detects stale heartbeats and re-enqueues orphaned jobs.

### 9.5 Duplicate Processing Prevention

Before enqueuing a new job, `JobService` computes a **content fingerprint**:

```
fingerprint = hash(normalized_url + format_id + quality)
```

1. Check `file_id` cache by fingerprint → instant delivery (no job needed).
2. Check active jobs set by fingerprint → attach user to existing job's notification list.
3. Check download lock by fingerprint → reject as duplicate.
4. If none match → acquire lock, create job, enqueue.

---

## 10. Cache Flow

### 10.1 Cache Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     Redis Cache                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  1. File ID Cache                                   │    │
│  │     Key:   fileid:{fingerprint}                     │    │
│  │     Value: {file_id, file_type, file_size, ...}     │    │
│  │     TTL:   30 days                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  2. Metadata Cache                                  │    │
│  │     Key:   meta:{url_hash}                          │    │
│  │     Value: {title, formats[], duration, ...}        │    │
│  │     TTL:   1 hour                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  3. Download Lock                                   │    │
│  │     Key:   lock:{fingerprint}                       │    │
│  │     Value: {job_id, worker_id, timestamp}           │    │
│  │     TTL:   10 minutes (auto-release safety)         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  4. User Rate Limit                                 │    │
│  │     Key:   rate:{user_id}                           │    │
│  │     Value: counter                                  │    │
│  │     TTL:   sliding window (1 minute / 1 hour)       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 File ID Cache — Detailed Flow

```
User requests download (URL + format + quality)
        │
        ▼
  Compute fingerprint = hash(normalized_url, format_id, quality)
        │
        ▼
  GET fileid:{fingerprint} from Redis
        │
   ┌────┴────┐
   │         │
  HIT      MISS
   │         │
   │         ▼
   │    Proceed with download
   │    ...
   │    After Telegram upload:
   │    SET fileid:{fingerprint} = {file_id, ...} EX 30d
   │
   ▼
  Send file via file_id (instant, no re-download)
  Telegram re-serves from its CDN
```

### 10.3 Metadata Cache — Detailed Flow

```
User sends URL
        │
        ▼
  Compute url_hash = hash(normalized_url)
        │
        ▼
  GET meta:{url_hash} from Redis
        │
   ┌────┴────┐
   │         │
  HIT      MISS
   │         │
   │         ▼
   │    Call yt-dlp extract_info(url)
   │    Parse response into MediaInfo
   │    SET meta:{url_hash} = serialized MediaInfo  EX 1h
   │         │
   ◄─────────┘
   │
   ▼
  Return MediaInfo to handler
```

### 10.4 Download Lock — Detailed Flow

```
JobService.create_job(fingerprint)
        │
        ▼
  SET lock:{fingerprint} NX EX 600  (acquire lock, 10-min TTL)
        │
   ┌────┴────┐
   │         │
  OK       FAIL (lock exists)
   │         │
   │         ▼
   │    Another download for same content is in progress
   │    → Attach user to existing job's notification list
   │    → Do NOT create a new job
   │
   ▼
  Lock acquired → create and enqueue job
  ...
  On job completion or failure:
  DEL lock:{fingerprint}
```

### 10.5 Cache Key Naming Convention

| Pattern | Example | Purpose |
|---|---|---|
| `fileid:{fingerprint}` | `fileid:a1b2c3d4e5` | Telegram file_id by content fingerprint |
| `meta:{url_hash}` | `meta:f6g7h8i9j0` | URL metadata cache |
| `lock:{fingerprint}` | `lock:a1b2c3d4e5` | Download deduplication lock |
| `rate:{user_id}` | `rate:123456789` | Per-user rate limit counter |
| `queue:jobs` | `queue:jobs` | Main job queue (sorted set) |
| `queue:active` | `queue:active` | Currently processing jobs set |
| `job:{job_id}` | `job:uuid-here` | Job detail hash |
| `worker:heartbeat:{id}` | `worker:heartbeat:w1` | Worker liveness signal |

---

## 11. Error Handling Flow

### 11.1 Error Classification

| Category | Examples | Action |
|---|---|---|
| **User Error** | Invalid URL, unsupported platform, file too large | Return user-friendly message via bot. No retry. No Sentry. |
| **Transient Error** | Network timeout, Telegram API 429, temporary yt-dlp failure | Retry with exponential backoff (max 3 retries). Log as warning. |
| **Infrastructure Error** | Redis connection lost, PostgreSQL down, disk full | Circuit-break. Alert via Sentry. Log as error. Graceful degradation. |
| **Fatal Error** | Unhandled exception, corrupted state | Log as critical. Report to Sentry immediately. Kill affected task. |

### 11.2 Error Handling Strategy per Layer

```
┌────────────────────────────────────────────────────────────────────┐
│  Bot Layer (Handlers)                                              │
│                                                                    │
│  • Catches domain exceptions → maps to user-friendly messages      │
│  • Global error handler catches unhandled exceptions               │
│  • Never exposes stack traces or internal details to users         │
│  • Logs correlation_id with every error for traceability           │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│  Service Layer                                                     │
│                                                                    │
│  • Raises domain-specific exceptions (from domain/exceptions.py)   │
│  • Does NOT catch infrastructure exceptions — lets them propagate  │
│  • Validates inputs before delegating to infrastructure            │
│  • Wraps infrastructure errors in domain exceptions where needed   │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                              │
│                                                                    │
│  • Handles low-level errors (connection, timeout, parse)           │
│  • Translates external errors to domain exceptions                 │
│  • Implements retry logic for transient failures (via tenacity)    │
│  • Manages connection pooling and reconnection                     │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│  Worker Layer                                                      │
│                                                                    │
│  • Wraps entire job processing in try/except                       │
│  • On retryable failure: increments retry count, re-enqueues       │
│  • On permanent failure: marks PERMANENTLY_FAILED, notifies user   │
│  • Always releases download lock in finally block                  │
│  • Always cleans up temporary files in finally block               │
│  • Reports all failures to Sentry with job context                 │
└────────────────────────────────────────────────────────────────────┘
```

### 11.3 Domain Exception Hierarchy

```
AppError (base)
├── UserFacingError (base for errors that produce user messages)
│   ├── URLNotSupportedError
│   ├── FormatNotAvailableError
│   ├── FileTooLargeError
│   ├── RateLimitExceededError
│   └── PermissionDeniedError
├── DownloadError (base for download-related failures)
│   ├── ExtractionFailedError
│   ├── DownloadTimeoutError
│   ├── FFmpegProcessingError
│   └── TelegramUploadError
├── DuplicateDownloadError
├── JobNotFoundError
├── CacheError
│   ├── CacheConnectionError
│   └── CacheSerializationError
└── InfrastructureError
    ├── DatabaseConnectionError
    └── RedisConnectionError
```

### 11.4 Retry Policy

| Operation | Max Retries | Backoff | Jitter |
|---|---|---|---|
| yt-dlp metadata extraction | 2 | Exponential (1s, 2s) | ±500ms |
| yt-dlp download | 3 | Exponential (2s, 4s, 8s) | ±1s |
| Telegram file upload | 3 | Exponential (1s, 2s, 4s) | ±500ms |
| Redis operation | 3 | Fixed 500ms | ±200ms |
| PostgreSQL query | 2 | Fixed 1s | ±300ms |
| Job processing (queue-level) | 3 | Exponential (30s, 60s, 120s) | ±10s |

### 11.5 User-Facing Error Messages

All user-facing error messages are:

- Written in clear, non-technical language.
- Localized via `core.i18n.translate` (Sprint 11.5) — never a hardcoded literal in a handler; see §23.3.
- Include actionable guidance where possible (e.g., "Try a different URL" or "Please wait and try again").
- Never expose internal error details, stack traces, or system information.

---

## 12. Database Architecture

### 12.0 Why the Previous Design Was Insufficient

The original 3-table design (`users`, `jobs`, `download_records`) had critical flaws that would block the project's growth trajectory and violate several target design goals:

| Flaw | Impact |
|---|---|
| **`download_records` stored `telegram_file_id` alongside history** | Cache and history were coupled into a single table. Deleting a user's history would destroy cached file IDs needed for global re-delivery. History cannot be retained or pruned independently of the file cache. |
| **No centralized media metadata** | Media metadata (title, duration, platform, thumbnail) was duplicated in `download_records` — once per download. 100 users downloading the same video = 100 identical rows of metadata. Violates normalization. |
| **No global file cache table** | The system had no single authoritative source for "which Telegram file_ids exist for which content." Every lookup required scanning `download_records` with denormalized fields. |
| **No Premium or payment readiness** | The `users` table had no fields for premium status, premium expiry, or download counters. Adding these later would require a migration and service-layer refactoring. |
| **No active download tracking in the database** | Duplicate download prevention relied entirely on Redis locks. If Redis lost the lock (restart, eviction), duplicate downloads could proceed. No durable fallback. |
| **No broadcast, settings, error log, or user preferences tables** | These essential operational tables were missing entirely, blocking admin tooling, multi-language support, analytics, and dynamic configuration. |
| **`jobs` table stored raw URL but no FK to media** | Jobs had no relationship to a normalized media record. The same video submitted by different users would create unrelated job rows with duplicated URL data. |

The redesigned schema solves every one of these issues.

---

### 12.1 Entity-Relationship Diagram

```
┌─────────────────────────┐
│      user_preferences   │
│─────────────────────────│
│ user_id (PK, FK)────────│──────────────────────────────────────────┐
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
                              │   │ premium_expire_at            │   │
                              │   │ is_banned                    │   │
                              │   │ banned_at                    │   │
                              │   │ ban_reason                   │   │
                              │   │ daily_download_count         │   │
                              │   │ total_downloads              │   │
                              │   │ created_at                   │   │
                              │   │ updated_at                   │   │
                              │   │ last_activity_at             │   │
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
                             │                                      │
                             │    ┌──────────────────────────────┐  │
                             │    │      media_metadata          │  │
                             │    │──────────────────────────────│  │
                             │    │ id (PK)                      │◄─┘
                             │    │ platform                     │
                             │    │ video_id                     │
                             │    │ title                        │
                             │    │ duration                     │
                             │    │ thumbnail_url                │
                             │    │ source_url                   │
                             │    │ metadata_json                │
                             │    │ created_at                   │
                             │    │ updated_at                   │
                             │    │ UNIQUE(platform, video_id)   │
                             │    └──────────────────────────────┘
                             │                  │
                             │                  │
                             │    ┌──────────────────────────────┐
                             │    │      cached_files            │
                             │    │──────────────────────────────│
                             └───►│ id (PK)                      │
                                  │ media_id (FK)────────────────│──► media_metadata
                                  │ format                       │
                                  │ quality                      │
                                  │ telegram_file_id             │
                                  │ telegram_unique_file_id      │
                                  │ file_size                    │
                                  │ usage_count                  │
                                  │ last_used_at                 │
                                  │ created_at                   │
                                  │ UNIQUE(media_id,format,qual) │
                                  └──────────────────────────────┘

┌─────────────────────────┐       ┌──────────────────────────────┐
│    active_downloads     │       │        error_logs            │
│─────────────────────────│       │──────────────────────────────│
│ id (PK)                 │       │ id (PK)                      │
│ media_id (FK)───────────│──►    │ user_id (FK, NULLABLE)───────│──► users
│ format                  │  mm   │ job_id (FK, NULLABLE)────────│──► jobs
│ quality                 │       │ error_type                   │
│ job_id (FK)─────────────│──►j   │ message                      │
│ created_at              │       │ traceback                    │
└─────────────────────────┘       │ created_at                   │
                                  └──────────────────────────────┘

┌──────────────────────────────┐
│       advertisements         │
│──────────────────────────────│
│ id (PK)                      │
│ type                         │
│ content_text                 │
│ content_media_file_id        │
│ button_text                  │
│ button_url                   │
│ target_role                  │
│ show_every_n_downloads       │
│ is_active                    │
│ priority                     │
│ impressions                  │
│ clicks                       │
│ created_by (FK)──────────────│──► users
│ created_at                   │
│ updated_at                   │
└──────────────────────────────┘
```

### 12.2 Relationship Summary

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

---

### 12.3 Table Definitions

#### 12.3.1 Table: `users`

**Purpose:** Central user registry. Every Telegram user who interacts with the bot gets a row on first `/start`. Stores identity, role, premium status, ban status, and aggregate download counters.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `telegram_id` | BIGINT | UNIQUE, NOT NULL | Telegram user ID — stable external identifier |
| `username` | VARCHAR(255) | NULLABLE | Telegram @username (may change or be absent) |
| `first_name` | VARCHAR(255) | NULLABLE | Telegram first name |
| `language` | VARCHAR(10) | NULLABLE | Telegram client language code (e.g., `en`, `ru`) |
| `role` | VARCHAR(20) | NOT NULL, DEFAULT `'user'` | One of: `owner`, `moderator`, `user` |
| `is_premium` | BOOLEAN | NOT NULL, DEFAULT `false` | Whether the user has an active Premium subscription |
| `premium_expire_at` | TIMESTAMPTZ | NULLABLE | When the current Premium period expires (NULL if not premium) |
| `is_banned` | BOOLEAN | NOT NULL, DEFAULT `false` | Whether the user is banned from using the bot |
| `banned_at` | TIMESTAMPTZ | NULLABLE | When the ban was applied (NULL if not banned) |
| `ban_reason` | VARCHAR(500) | NULLABLE | Admin-provided reason for the ban (NULL if not banned) |
| `daily_download_count` | INTEGER | NOT NULL, DEFAULT `0` | Downloads today (reset by scheduled job at midnight UTC) |
| `total_downloads` | BIGINT | NOT NULL, DEFAULT `0` | Lifetime download count |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Account creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Last profile data change |
| `last_activity_at` | TIMESTAMPTZ | NULLABLE | Last meaningful interaction timestamp |

**Design notes:**

- `daily_download_count` is stored on the user for fast limit checks without aggregating the `downloads` table. A nightly scheduled task resets it to 0.
- `is_premium` + `premium_expire_at` are separated: `is_premium` is the fast boolean check used in middlewares and rate limiters; `premium_expire_at` is the authoritative expiry used by the premium expiration job.
- `total_downloads` is a denormalized counter updated atomically on each successful download. It avoids `COUNT(*)` queries on the `downloads` table for profile display and analytics.
- `is_banned`, `banned_at`, `ban_reason` live directly on the `users` table (no separate banned_users table). Ban checks are hot-path operations performed on every update via middleware; a JOIN to a separate table would add unnecessary latency. When a user is unbanned, `is_banned` is set to `false` but `banned_at` and `ban_reason` are preserved for audit trail until the next ban.

---

#### 12.3.2 Table: `media_metadata`

**Purpose:** Single, normalized source of truth for media information. When a URL is analyzed, the platform and video_id are extracted, and metadata is stored **once**. All other tables reference this record by FK rather than duplicating title, duration, or platform.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `platform` | VARCHAR(50) | NOT NULL | Source platform identifier (e.g., `youtube`, `tiktok`, `instagram`) |
| `video_id` | VARCHAR(255) | NOT NULL | Platform-specific content identifier (e.g., YouTube video ID) |
| `title` | VARCHAR(1000) | NOT NULL | Media title |
| `duration` | INTEGER | NULLABLE | Duration in seconds (NULL for images/stories) |
| `thumbnail_url` | TEXT | NULLABLE | URL to the thumbnail image |
| `source_url` | TEXT | NOT NULL | The original URL used to discover this media |
| `metadata_json` | JSONB | NULLABLE | Full yt-dlp metadata snapshot for advanced use (formats list, uploader, tags, etc.) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | First discovery timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Last metadata refresh |

**Unique constraint:** `UNIQUE(platform, video_id)`

**Design notes:**

- The `(platform, video_id)` pair is the natural key. This prevents inserting duplicate metadata for the same content from different URL variants (e.g., `youtube.com/watch?v=X` vs `youtu.be/X`).
- `metadata_json` (JSONB) stores the complete yt-dlp response. This supports future analytics dashboards, format availability analysis, and avoids re-extraction for data that rarely changes.
- `source_url` stores the first URL used to discover this content. It is informational — the canonical reference is `(platform, video_id)`.
- `updated_at` is refreshed when metadata is re-extracted (e.g., title change, new formats available).

---

#### 12.3.3 Table: `cached_files`

**Purpose:** Global Telegram File ID cache. This is the **single source of truth** for all reusable Telegram files. When a file is uploaded to Telegram, the returned `file_id` is stored here, keyed by media + format + quality. Any future request for the same content + format + quality can be served instantly by re-sending the cached `file_id`.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `media_id` | BIGINT | FK → `media_metadata.id`, NOT NULL | The media this file was generated from |
| `format` | VARCHAR(50) | NOT NULL | File format (e.g., `mp4`, `mp3`, `webm`) |
| `quality` | VARCHAR(20) | NOT NULL | Quality level (e.g., `360p`, `720p`, `1080p`, `128kbps`) |
| `telegram_file_id` | VARCHAR(255) | NOT NULL | Telegram file_id — used for instant re-send |
| `telegram_unique_file_id` | VARCHAR(255) | NOT NULL | Telegram unique_file_id — stable across bots, used for dedup verification |
| `file_size` | BIGINT | NULLABLE | File size in bytes |
| `usage_count` | INTEGER | NOT NULL, DEFAULT `0` | Number of times this cached file has been served |
| `last_used_at` | TIMESTAMPTZ | NULLABLE | Last time this cached file was served to any user |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Cache entry creation timestamp |

**Unique constraint:** `UNIQUE(media_id, format, quality)`

**Design notes:**

- This table is **completely independent from user history**. Deleting a user's download history does not affect the cache. Purging old cache entries does not destroy history.
- `usage_count` and `last_used_at` enable cache analytics: which files are most popular, which are stale. Future eviction policies can use `last_used_at` to remove entries that haven't been served in N days.
- `telegram_unique_file_id` is stored alongside `telegram_file_id` because Telegram's `unique_file_id` is stable across different bots and can be used for cross-bot deduplication or future multi-bot architectures.
- The `UNIQUE(media_id, format, quality)` constraint ensures exactly one cache entry per media-format-quality combination. The application performs an upsert on download completion.

---

#### 12.3.4 Table: `downloads`

**Purpose:** User download history. Each row records that a specific user received a specific file at a specific time. History is a **log of user actions** — it never serves as a cache and never stores Telegram file IDs directly. Instead, it references `cached_files` by FK for resend capability.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `user_id` | BIGINT | FK → `users.id`, NOT NULL | The user who performed the download |
| `cached_file_id` | BIGINT | FK → `cached_files.id`, NOT NULL | The cached file that was delivered |
| `platform` | VARCHAR(50) | NOT NULL | Platform (denormalized from media_metadata for fast history display) |
| `format` | VARCHAR(50) | NOT NULL | Format used (denormalized for fast history display) |
| `quality` | VARCHAR(20) | NOT NULL | Quality level (denormalized for fast history display) |
| `file_size` | BIGINT | NULLABLE | File size in bytes (denormalized for fast history display) |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT `'completed'` | Download outcome: `completed`, `failed`, `cancelled` |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | When the download was performed |

**Design notes:**

- **History ≠ Cache.** This is the central design principle. `downloads` records *who downloaded what and when*. `cached_files` records *which Telegram file_ids are available*. They are separate concerns with separate lifecycles.
- `platform`, `format`, `quality`, and `file_size` are **intentionally denormalized** in this table. This avoids a 3-table JOIN (downloads → cached_files → media_metadata) for the common "show user history" query. The tradeoff is a few extra bytes per row — negligible at scale — versus significant query simplification and performance gain.
- To resend a file from history: look up `cached_file_id` → read `cached_files.telegram_file_id` → send via Telegram API. If the cached file has been purged, fall back to a new download job.
- The `status` field distinguishes successful downloads from failed attempts and cancellations, enabling accurate analytics.

---

#### 12.3.5 Table: `jobs`

**Purpose:** Download job queue. Each row represents a unit of work: download a specific media in a specific format/quality for a specific user. Jobs progress through the lifecycle defined in §9.2.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | UUID | PK, DEFAULT `gen_random_uuid()` | Unique job identifier |
| `user_id` | BIGINT | FK → `users.id`, NOT NULL | The user who requested the download |
| `media_id` | BIGINT | FK → `media_metadata.id`, NOT NULL | The media to download |
| `format` | VARCHAR(50) | NOT NULL | Requested format |
| `quality` | VARCHAR(20) | NOT NULL | Requested quality |
| `priority` | INTEGER | NOT NULL, DEFAULT `1000` | Priority score (lower = higher priority, see §9.3) |
| `retry_count` | INTEGER | NOT NULL, DEFAULT `0` | Number of retry attempts |
| `status` | VARCHAR(30) | NOT NULL, DEFAULT `'created'` | Current lifecycle status (see §9.2) |
| `error_message` | TEXT | NULLABLE | Last error message on failure |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Job creation timestamp |
| `started_at` | TIMESTAMPTZ | NULLABLE | When a worker began processing |
| `finished_at` | TIMESTAMPTZ | NULLABLE | When the job completed or permanently failed |

**Design notes:**

- `media_id` replaces the old `url` / `normalized_url` / `fingerprint` columns. The media record is created during URL analysis (before the job is created), so the FK is always available. This eliminates URL duplication across jobs for the same content.
- The old `fingerprint` column is no longer needed on the `jobs` table. Duplicate detection now uses `(media_id, format, quality)` lookups against `active_downloads` and `cached_files`.
- `worker_id` has been removed from this table. Worker assignment is tracked in Redis (transient, high-frequency updates). Persisting it added write pressure on every heartbeat with no query benefit.
- `finished_at` replaces the old split `completed_at`. Combined with `status`, it records when any terminal state was reached.

---

#### 12.3.6 Table: `active_downloads`

**Purpose:** Durable duplicate download prevention. While Redis locks handle the fast path, this table provides a persistent fallback. If Redis loses a lock (restart, eviction, network partition), the database record still prevents duplicate work.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `media_id` | BIGINT | FK → `media_metadata.id`, NOT NULL | The media being downloaded |
| `format` | VARCHAR(50) | NOT NULL | Format being downloaded |
| `quality` | VARCHAR(20) | NOT NULL | Quality being downloaded |
| `job_id` | UUID | FK → `jobs.id`, NOT NULL | The job performing the download |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Lock acquisition timestamp |

**Unique constraint:** `UNIQUE(media_id, format, quality)`

**Design notes:**

- The `UNIQUE(media_id, format, quality)` constraint is the enforcement mechanism. An `INSERT` that violates it proves another download is already in progress.
- When a download completes (or permanently fails), the corresponding `active_downloads` row is deleted.
- A cleanup job periodically scans for `active_downloads` rows whose associated `jobs.status` is terminal (completed, permanently_failed, timed_out) and removes them. This handles edge cases where the delete was missed.
- **Multi-user scenario:** If User A requests video X in 720p and User B requests the same while User A's download is active, the system detects the existing `active_downloads` row, and attaches User B to the same job's notification list (in Redis). When the job completes, both users receive the cached file.

---

#### 12.3.7 Table: `broadcasts`

**Purpose:** Admin broadcast message log. When an owner sends a broadcast to all users (or a filtered subset), the broadcast is recorded for auditing, delivery tracking, and analytics.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `created_by` | BIGINT | FK → `users.id`, NOT NULL | The admin who initiated the broadcast |
| `target_language` | VARCHAR(10) | NULLABLE | If set, broadcast only to users with this language (NULL = all) |
| `target_role` | VARCHAR(20) | NULLABLE | If set, broadcast only to users with this role (NULL = all) |
| `message_text` | TEXT | NOT NULL | The broadcast message content |
| `total_sent` | INTEGER | NOT NULL, DEFAULT `0` | Number of messages successfully delivered |
| `total_failed` | INTEGER | NOT NULL, DEFAULT `0` | Number of delivery failures |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Broadcast initiation timestamp |

**Design notes:**

- `target_language` enables audience-filtered broadcasts (e.g., send only to Arabic-speaking users), matched against `users.language`. Distinct from — and predates — the UI-localization system (§23.3): this filters *who* receives a broadcast, not *which language its body is written in* (broadcast bodies are always user-generated content and are never translated).
- `target_role` enables role-targeted broadcasts (e.g., announce Premium features only to premium users).
- `total_sent` and `total_failed` are updated as the broadcast job progresses. They provide delivery tracking without a separate delivery log table (which can be added later if per-user delivery tracking is needed).

---

#### 12.3.8 Table: `settings`

**Purpose:** Dynamic system configuration. Key-value store for runtime settings that can be changed without redeployment. These override or supplement environment variables for values that need to be adjustable via admin commands or an admin dashboard.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `key` | VARCHAR(100) | PK | Setting name (e.g., `worker_count`, `free_daily_limit`) |
| `value` | TEXT | NOT NULL | Setting value (stored as text, parsed by application layer) |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Expected initial settings:**

| Key | Default Value | Description |
|---|---|---|
| `worker_count` | `3` | Number of concurrent download workers |
| `free_daily_limit` | `10` | Max downloads per day for free users |
| `premium_daily_limit` | `100` | Max downloads per day for premium users |
| `free_max_file_size` | `52428800` | Max file size for free users (50 MB) |
| `premium_max_file_size` | `2147483648` | Max file size for premium users (2 GB, Telegram limit) |
| `download_cooldown_seconds` | `30` | Minimum seconds between downloads for free users |
| `premium_download_cooldown_seconds` | `5` | Minimum seconds between downloads for premium users |
| `maintenance_mode` | `false` | When `true`, bot replies with maintenance message |
| `max_file_size` | `2147483648` | Global maximum downloadable file size in bytes (2 GB) |
| `max_duration` | `14400` | Maximum media duration in seconds |
| `rate_limit_messages_per_minute` | `30` | Throttle: messages per user per minute |
| `ads_enabled` | `true` | Global advertisement kill switch (`false` = no ads shown) |
| `ads_default_frequency` | `1` | Default: show ad every N downloads (overridden per-ad) |

**Design notes:**

- Values are stored as `TEXT` and parsed by the application layer. This keeps the schema simple and avoids type columns.
- The application reads settings with a short Redis cache layer (TTL ~60s) to avoid hitting PostgreSQL on every request.
- `updated_at` is updated on every change, enabling cache invalidation and audit trails.

---

#### 12.3.9 Table: `error_logs`

**Purpose:** Persistent error log for operational diagnostics. Complements Sentry (external) with an internal, queryable error store. Enables admin dashboard error browsing, per-user error history, and error-type analytics without depending on external services.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `user_id` | BIGINT | FK → `users.id`, NULLABLE | The user affected (NULL for system-level errors) |
| `job_id` | UUID | FK → `jobs.id`, NULLABLE | The job that failed (NULL for non-job errors) |
| `error_type` | VARCHAR(30) | NOT NULL | Error category (see below) |
| `message` | TEXT | NOT NULL | Human-readable error description |
| `traceback` | TEXT | NULLABLE | Python traceback (stripped of secrets) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Error occurrence timestamp |

**Error type values:**

| Value | Description |
|---|---|
| `DOWNLOAD_ERROR` | yt-dlp download failed |
| `UPLOAD_ERROR` | Telegram file upload failed |
| `FFMPEG_ERROR` | FFmpeg transcoding failed |
| `CACHE_ERROR` | Redis cache operation failed |
| `PLATFORM_ERROR` | Source platform blocked/rate-limited the request |
| `UNKNOWN_ERROR` | Unclassified error |

**Design notes:**

- Both `user_id` and `job_id` are nullable because some errors are system-level (e.g., Redis connection failure at startup) and not associated with any user or job.
- `traceback` stores the full Python traceback for debugging but must be sanitized to remove secrets (bot token, DB credentials) before storage.
- This table grows indefinitely. A retention policy should periodically delete records older than N days (configurable via `settings`).

---

#### 12.3.10 Table: `user_preferences`

**Purpose:** User-specific preferences that are separate from the core `users` table. Isolating preferences into a dedicated table keeps the frequently-queried `users` table lean and provides a clean extension point for future preference categories.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `user_id` | BIGINT | PK, FK → `users.id` | One-to-one relationship with `users` |
| `notifications_enabled` | BOOLEAN | NOT NULL, DEFAULT `true` | Whether the user receives job status notifications |
| `preferred_language` | VARCHAR(10) | NULLABLE | User's explicitly chosen interface language (overrides Telegram language) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Record creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Last preference change |

**Design notes:**

- `preferred_language` vs `users.language`: **as of Sprint 11.5, this is reversed from the original design sketch below.** `users.language` is now the single field driving the bot's UI locale — set to the configured default locale when a user is created, then updated only by an explicit in-bot language pick (never from Telegram's auto-detected client language, which isn't restricted to the languages the bot actually catalogs). `user_preferences.preferred_language` remains **reserved and unused** — see §23.3 and MASTER_PLAN.md D-061.
- `user_id` is both the PK and the FK, enforcing a strict one-to-one relationship. Created lazily on first preference change (not on `/start`).
- Future preference fields (e.g., `default_format`, `default_quality`, `auto_download`, `theme`) can be added as columns without structural changes.

---

#### 12.3.11 Table: `advertisements`

**Purpose:** Smart advertisement system. Stores admin-managed advertisements that are shown to users based on configurable rules: after every download, every N downloads, only to free users, etc. Advertisements are entirely database-driven — no code changes are needed to create, update, enable, disable, or retarget ads.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | BIGINT | PK, auto-increment | Internal surrogate key |
| `type` | VARCHAR(20) | NOT NULL | Ad content type: `text`, `photo`, `video`, `animation` |
| `content_text` | TEXT | NULLABLE | Text content of the advertisement (supports Telegram HTML/Markdown) |
| `content_media_file_id` | VARCHAR(255) | NULLABLE | Telegram `file_id` for photo/video/animation ads |
| `button_text` | VARCHAR(100) | NULLABLE | Inline button label (NULL = no button) |
| `button_url` | TEXT | NULLABLE | Inline button URL (NULL = no button) |
| `target_role` | VARCHAR(20) | NULLABLE | Show only to this role: `user`, `premium`, or NULL = all non-premium users by default |
| `show_every_n_downloads` | INTEGER | NOT NULL, DEFAULT `1` | Show this ad every N downloads (1 = every download, 3 = every 3rd download) |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT `true` | Whether this ad is currently being served |
| `priority` | INTEGER | NOT NULL, DEFAULT `0` | When multiple ads match, higher priority wins |
| `impressions` | BIGINT | NOT NULL, DEFAULT `0` | Total times this ad has been shown |
| `clicks` | BIGINT | NOT NULL, DEFAULT `0` | Total times the ad button was clicked (if applicable) |
| `created_by` | BIGINT | FK → `users.id`, NOT NULL | Admin who created the advertisement |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Ad type values:**

| Value | Description |
|---|---|
| `text` | Text-only advertisement (sent as a message) |
| `photo` | Photo with optional caption |
| `video` | Video with optional caption |
| `animation` | GIF/animation with optional caption |

**Targeting rules:**

| Scenario | Configuration |
|---|---|
| Show ad after every download | `show_every_n_downloads = 1`, `is_active = true` |
| Show ad every 3rd download | `show_every_n_downloads = 3`, `is_active = true` |
| Show ad only to free users | `target_role = 'user'`, `is_active = true` |
| Show ad only to premium users | `target_role = 'premium'`, `is_active = true` |
| Disable all ads globally | Set `ads_enabled = false` in `settings` table |
| Disable specific ad | Set `is_active = false` on the ad row |

**Design notes:**

- Premium users do not see advertisements by default. The ad delivery service checks `users.is_premium` and skips ad delivery when `true`, unless the ad explicitly targets `target_role = 'premium'`.
- The `show_every_n_downloads` field works with `users.total_downloads` (or a Redis counter): `IF total_downloads % show_every_n_downloads == 0 THEN show_ad`.
- `impressions` and `clicks` are updated atomically for analytics. CTR (click-through rate) = `clicks / impressions`.
- Multiple ads can be active simultaneously. The ad delivery service selects the best matching ad by `priority` (highest priority first), filtering by `is_active = true`, `target_role` match, and `show_every_n_downloads` match.
- `content_media_file_id` uses Telegram's `file_id` for media ads. The admin uploads the media once, and the `file_id` is stored for instant re-delivery — the same caching principle used for download files.
- The global `ads_enabled` setting in the `settings` table acts as a master kill switch. When `false`, no ads are shown regardless of individual ad `is_active` status.

---

### 12.4 Indexes

#### 12.4.1 Primary Indexes (from PKs and UNIQUEs — auto-created)

| Table | Index | Column(s) | Created By |
|---|---|---|---|
| `users` | `users_pkey` | `id` | PK |
| `users` | `uq_users_telegram_id` | `telegram_id` | UNIQUE |
| `media_metadata` | `media_metadata_pkey` | `id` | PK |
| `media_metadata` | `uq_media_platform_video` | `(platform, video_id)` | UNIQUE |
| `cached_files` | `cached_files_pkey` | `id` | PK |
| `cached_files` | `uq_cached_media_format_quality` | `(media_id, format, quality)` | UNIQUE |
| `downloads` | `downloads_pkey` | `id` | PK |
| `jobs` | `jobs_pkey` | `id` | PK |
| `active_downloads` | `active_downloads_pkey` | `id` | PK |
| `active_downloads` | `uq_active_media_format_quality` | `(media_id, format, quality)` | UNIQUE |
| `broadcasts` | `broadcasts_pkey` | `id` | PK |
| `settings` | `settings_pkey` | `key` | PK |
| `error_logs` | `error_logs_pkey` | `id` | PK |
| `user_preferences` | `user_preferences_pkey` | `user_id` | PK |
| `advertisements` | `advertisements_pkey` | `id` | PK |

#### 12.4.2 Secondary Indexes (manually created for query performance)

| Table | Index Name | Column(s) | Purpose |
|---|---|---|---|
| `users` | `ix_users_role` | `role` | Filter users by role (admin queries, broadcast targeting) |
| `users` | `ix_users_is_premium` | `is_premium` | Filter premium users (expiry jobs, analytics) |
| `users` | `ix_users_last_activity` | `last_activity_at` | Inactive user detection, analytics |
| `media_metadata` | `ix_media_platform` | `platform` | Platform-specific analytics |
| `media_metadata` | `ix_media_created_at` | `created_at` | Time-based queries, cleanup |
| `cached_files` | `ix_cached_media_id` | `media_id` | Lookup all cached variants of a media |
| `cached_files` | `ix_cached_last_used` | `last_used_at` | Cache eviction policy (LRU) |
| `cached_files` | `ix_cached_usage_count` | `usage_count` | Analytics: most popular cached files |
| `downloads` | `ix_downloads_user_id` | `user_id` | User history lookup |
| `downloads` | `ix_downloads_user_created` | `(user_id, created_at DESC)` | Optimized paginated user history |
| `downloads` | `ix_downloads_platform` | `platform` | Platform analytics |
| `downloads` | `ix_downloads_created_at` | `created_at` | Time-based analytics, retention |
| `jobs` | `ix_jobs_user_id` | `user_id` | User's job lookup |
| `jobs` | `ix_jobs_status` | `status` | Queue management: find jobs by state |
| `jobs` | `ix_jobs_media_id` | `media_id` | Find all jobs for a specific media |
| `jobs` | `ix_jobs_created_at` | `created_at` | Time-based queries, cleanup |
| `jobs` | `ix_jobs_status_priority` | `(status, priority, created_at)` | Optimized queue dequeue (if DB-backed fallback is needed) |
| `active_downloads` | `ix_active_job_id` | `job_id` | Lookup active download by job |
| `error_logs` | `ix_errors_user_id` | `user_id` | Per-user error history |
| `error_logs` | `ix_errors_job_id` | `job_id` | Per-job error history |
| `error_logs` | `ix_errors_type` | `error_type` | Error-type analytics |
| `error_logs` | `ix_errors_created_at` | `created_at` | Time-based queries, retention policy |
| `broadcasts` | `ix_broadcasts_created_at` | `created_at` | Broadcast history browsing |
| `users` | `ix_users_is_banned` | `is_banned` | Fast ban check in middleware |
| `advertisements` | `ix_ads_is_active` | `is_active` | Filter active ads for delivery |
| `advertisements` | `ix_ads_target_role` | `target_role` | Role-targeted ad selection |
| `advertisements` | `ix_ads_active_priority` | `(is_active, priority DESC)` | Optimized active ad selection by priority |

---

### 12.5 All Foreign Key Relationships

| Source Table | Source Column | Target Table | Target Column | ON DELETE | Rationale |
|---|---|---|---|---|---|
| `downloads` | `user_id` | `users` | `id` | CASCADE | Deleting a user removes their history |
| `downloads` | `cached_file_id` | `cached_files` | `id` | RESTRICT | Cannot delete a cache entry that history references (purge history first or nullify) |
| `jobs` | `user_id` | `users` | `id` | CASCADE | Deleting a user removes their jobs |
| `jobs` | `media_id` | `media_metadata` | `id` | RESTRICT | Cannot delete media that has associated jobs |
| `cached_files` | `media_id` | `media_metadata` | `id` | CASCADE | Deleting media metadata removes its cached files |
| `active_downloads` | `media_id` | `media_metadata` | `id` | CASCADE | Deleting media removes its active download locks |
| `active_downloads` | `job_id` | `jobs` | `id` | CASCADE | Deleting a job removes its active download lock |
| `broadcasts` | `created_by` | `users` | `id` | RESTRICT | Cannot delete a user who created broadcasts (preserve audit trail) |
| `error_logs` | `user_id` | `users` | `id` | SET NULL | Deleting a user nullifies their error references (preserve error log) |
| `error_logs` | `job_id` | `jobs` | `id` | SET NULL | Deleting a job nullifies its error references (preserve error log) |
| `user_preferences` | `user_id` | `users` | `id` | CASCADE | Deleting a user removes their preferences |
| `advertisements` | `created_by` | `users` | `id` | RESTRICT | Cannot delete a user who created advertisements (preserve audit trail) |

---

### 12.6 All Unique Constraints Summary

| Table | Constraint Name | Column(s) | Purpose |
|---|---|---|---|
| `users` | `uq_users_telegram_id` | `telegram_id` | One row per Telegram user |
| `media_metadata` | `uq_media_platform_video` | `(platform, video_id)` | One metadata record per unique media content |
| `cached_files` | `uq_cached_media_format_quality` | `(media_id, format, quality)` | One cache entry per media + format + quality combination |
| `active_downloads` | `uq_active_media_format_quality` | `(media_id, format, quality)` | Only one active download per media + format + quality |

---

### 12.7 Why Each Table Exists

| Table | Exists Because |
|---|---|
| **`users`** | Core identity table. Every authorization check, rate limit, download counter, and history query starts here. Without it, the system cannot identify or manage users. |
| **`media_metadata`** | **Normalization.** Without it, title, duration, platform, and thumbnail would be duplicated across `jobs`, `cached_files`, and `downloads`. A single popular video downloaded by 1,000 users would create 1,000 copies of its metadata. This table stores it once. |
| **`cached_files`** | **Separation of cache from history.** The old design stored `telegram_file_id` in `download_records`, coupling cache and history. This table is the single, global, user-independent source of truth for which Telegram file IDs are available. Cache entries can be evicted without affecting history. History can be deleted without destroying the cache. |
| **`downloads`** | **User action log.** Records who downloaded what and when. Used for history display, analytics, and Premium usage tracking. References `cached_files` by FK for resend — but never stores file IDs itself. |
| **`jobs`** | **Work unit tracking.** The queue system needs a persistent record of every job's status, retries, timing, and errors. Required for monitoring, debugging, and the admin dashboard. |
| **`active_downloads`** | **Durable deduplication.** Redis locks are the primary dedup mechanism, but they are volatile. This table ensures that even if Redis loses state, a `UNIQUE` constraint in PostgreSQL prevents duplicate downloads. Also enables the multi-user fan-out scenario (many users waiting on one download). |
| **`broadcasts`** | **Audit and tracking.** Broadcast messages to thousands of users need delivery tracking. Without this table, there's no way to know what was sent, to whom, or how many deliveries succeeded. |
| **`settings`** | **Runtime configuration.** Some settings (daily limits, maintenance mode, max file size) must be changeable without redeploying. A key-value table is the simplest durable solution. |
| **`error_logs`** | **Internal diagnostics.** Sentry is the primary error tracker but is an external dependency. This table provides a queryable, internal error history for admin dashboards, per-user error inspection, and error-type analytics without external API calls. |
| **`user_preferences`** | **Extension point.** Separating preferences from `users` keeps the `users` table lean (high-read, every-request table) and provides a clean place to add future settings (default format, theme, notification preferences) without widening the core table. |
| **`advertisements`** | **Revenue and engagement.** Database-driven advertisement system allows admins to create, target, enable/disable, and track ads without code changes. Supports frequency control, role-based targeting, impression/click analytics, and a global kill switch. Essential for monetization of the free tier. |

---

### 12.8 Data Flow Through the New Schema

#### 12.8.1 New Download — Complete Path

```
User sends URL
        │
        ▼
  URLAnalyzerService extracts (platform, video_id)
        │
        ▼
  UPSERT into media_metadata  ───────────────────────┐
  ON CONFLICT (platform, video_id) DO UPDATE          │
  Returns media_metadata.id                           │
        │                                             │
        ▼                                             │
  SELECT from cached_files                            │
  WHERE media_id = ? AND format = ? AND quality = ?   │
        │                                             │
   ┌────┴────┐                                        │
   │         │                                        │
  HIT      MISS                                       │
   │         │                                        │
   │         ▼                                        │
   │    INSERT into active_downloads                  │
   │    (media_id, format, quality, job_id)            │
   │    ON CONFLICT → duplicate detected              │
   │         │                                        │
   │         ▼                                        │
   │    INSERT into jobs                              │
   │    (user_id, media_id, format, quality, ...)     │
   │         │                                        │
   │         ▼                                        │
   │    Worker downloads file                         │
   │         │                                        │
   │         ▼                                        │
   │    Worker uploads to Telegram → gets file_id     │
   │         │                                        │
   │         ▼                                        │
   │    UPSERT into cached_files                      │
   │    (media_id, format, quality, telegram_file_id) │
   │    Returns cached_files.id                       │
   │         │                                        │
   ◄─────────┘                                        │
   │                                                  │
   ▼                                                  │
  INSERT into downloads                               │
  (user_id, cached_file_id, platform, format, ...)    │
        │                                             │
        ▼                                             │
  UPDATE users SET                                    │
    daily_download_count = daily_download_count + 1,  │
    total_downloads = total_downloads + 1             │
        │                                             │
        ▼                                             │
  UPDATE cached_files SET                             │
    usage_count = usage_count + 1,                    │
    last_used_at = NOW()                              │
        │                                             │
        ▼                                             │
  DELETE from active_downloads WHERE job_id = ?       │
        │                                             │
        ▼                                             │
  UPDATE jobs SET status = 'completed',               │
    finished_at = NOW()                               │
        │                                             │
        ▼                                             │
  Send file to user via Telegram                      │
```

#### 12.8.2 Instant Resend from History

```
User taps "Resend" on history item
        │
        ▼
  SELECT d.cached_file_id, cf.telegram_file_id
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
   │    (re-enters §12.8.1 flow)
   │
   ▼
  Send file via cached telegram_file_id (instant)
  UPDATE cached_files SET usage_count = usage_count + 1,
    last_used_at = NOW()
```

---

### 12.9 Future Expansion Notes

#### 12.9.1 Premium System

**No schema changes required for the base Premium system.** The `users` table already has `is_premium`, `premium_expire_at`, and `daily_download_count`. The `settings` table has `free_daily_limit` and `premium_daily_limit`. The `jobs` table has `priority` for Premium queue priority.

**When subscription management is added**, create:

```
(future) premium_plans
  - id, name, duration_days, price, max_daily_downloads,
    max_file_size, max_quality, features_json, is_active

(future) user_subscriptions
  - id, user_id (FK), plan_id (FK), started_at, expires_at,
    status, payment_id (FK), cancelled_at
```

#### 12.9.2 Payment System

**When payment integration is added**, create:

```
(future) payments
  - id, user_id (FK), provider (stripe/yookassa/crypto),
    provider_payment_id, amount, currency, status,
    metadata_json, created_at, completed_at

(future) invoices
  - id, user_id (FK), payment_id (FK), subscription_id (FK),
    amount, currency, invoice_url, created_at
```

The `users.is_premium` and `users.premium_expire_at` fields will be updated by the payment webhook handler upon successful payment.

#### 12.9.3 Referral System

**When referrals are added**, create:

```
(future) referrals
  - id, referrer_id (FK → users), referred_id (FK → users),
    bonus_type, bonus_value, status, created_at

(future) referral_codes
  - id, user_id (FK), code (UNIQUE), usage_count,
    max_uses, is_active, created_at
```

Add to `users`: `referred_by (FK → users, NULLABLE)`.

#### 12.9.4 Web Dashboard

The existing schema fully supports a web dashboard without changes:

- **User management:** Query `users` with filtering by role, premium status, activity.
- **Job monitoring:** Query `jobs` with filtering by status, user, time range.
- **Analytics:** Aggregate `downloads` by platform, time, user; aggregate `cached_files` by usage_count.
- **Error inspection:** Query `error_logs` with filtering by type, user, time.
- **Settings management:** CRUD on `settings` table.
- **Broadcast management:** CRUD on `broadcasts` table.

The FastAPI admin API layer already provides the endpoints; the dashboard is a frontend consumer.

#### 12.9.5 Analytics

The current schema supports these analytics queries without additional tables:

| Metric | Source |
|---|---|
| Downloads per day/week/month | `downloads.created_at` aggregation |
| Downloads by platform | `downloads.platform` aggregation |
| Most popular media | `cached_files.usage_count` ranking |
| User growth over time | `users.created_at` aggregation |
| Active users (DAU/WAU/MAU) | `users.last_activity_at` window counts |
| Premium conversion rate | `users.is_premium` ratio |
| Average downloads per user | `users.total_downloads` statistics |
| Cache hit rate | `cached_files.usage_count` vs `jobs` count |
| Error distribution | `error_logs.error_type` aggregation |
| Peak hours | `downloads.created_at` hour-of-day aggregation |

**When advanced analytics are needed**, create:

```
(future) daily_stats
  - date (PK), total_downloads, unique_users, new_users,
    jobs_created, jobs_completed, jobs_failed,
    cache_hits, cache_misses, errors_count

(future) platform_daily_stats
  - date, platform, download_count, unique_users
  - PK(date, platform)
```

These materialized aggregation tables are populated by a nightly ETL job and avoid expensive real-time aggregations on the transactional tables at scale.

---

## 13. Role-Based Access Control

### 13.1 Role Definitions

| Role | Description | Assignment |
|---|---|---|
| **Owner** | Full system control. Cannot be demoted. | Hardcoded Telegram ID in config |
| **Moderator** | User management and system monitoring. | Assigned by Owner via command |
| **User** | Standard user. Can download and view own history. | Default role on `/start` |

### 13.2 Permission Matrix

| Action | Owner | Moderator | User |
|---|---|---|---|
| Submit download URL | ✅ | ✅ | ✅ |
| View own history | ✅ | ✅ | ✅ |
| Resend from own history | ✅ | ✅ | ✅ |
| View system stats | ✅ | ✅ | ❌ |
| View queue status | ✅ | ✅ | ❌ |
| Ban/unban users (with reason) | ✅ | ✅ | ❌ |
| View ban details (reason, date) | ✅ | ✅ | ❌ |
| View any user's history | ✅ | ✅ | ❌ |
| Promote to Moderator | ✅ | ❌ | ❌ |
| Demote Moderator | ✅ | ❌ | ❌ |
| Configure rate limits | ✅ | ❌ | ❌ |
| Configure file size limits | ✅ | ❌ | ❌ |
| Configure download cooldowns | ✅ | ❌ | ❌ |
| Manage advertisements (CRUD) | ✅ | ❌ | ❌ |
| Enable/disable ads globally | ✅ | ❌ | ❌ |
| View ad analytics | ✅ | ✅ | ❌ |
| System configuration | ✅ | ❌ | ❌ |
| Broadcast message | ✅ | ❌ | ❌ |
| Access admin API | ✅ | ✅ (read-only) | ❌ |

### 13.3 Enforcement Points

1. **Bot Middleware (`auth.py`):** Checks role on every incoming update. Banned users receive a static message and are blocked from all actions.
2. **Bot Filter (`role_filter.py`):** Declarative role requirement on individual handlers.
3. **API Dependencies (`dependencies.py`):** API key validation + role check for admin endpoints.

---

## 14. Logging Strategy

### 14.1 Logging Framework

**Library:** `structlog` with `stdlib` integration.

**Format:**
- **Production:** JSON lines to stdout (consumed by log aggregator).
- **Development:** Human-readable colored console output.

### 14.2 Log Levels and Usage

| Level | Usage | Examples |
|---|---|---|
| `DEBUG` | Detailed diagnostic information. Disabled in production by default. | Cache key lookups, SQL query details, yt-dlp raw output |
| `INFO` | Normal operational events. | Job created, download started, file sent, user registered |
| `WARNING` | Unexpected but recoverable situations. | Rate limit hit, retry triggered, cache miss on expected hit |
| `ERROR` | Failures that affect a single operation but not the system. | Download failed after retries, Telegram upload error, invalid URL |
| `CRITICAL` | System-level failures requiring immediate attention. | Database connection lost, Redis unreachable, worker crash |

### 14.3 Structured Log Fields

Every log entry includes the following standard fields:

| Field | Source | Description |
|---|---|---|
| `timestamp` | Auto | ISO-8601 timestamp |
| `level` | Auto | Log level |
| `logger` | Auto | Logger name (module path) |
| `event` | Manual | Human-readable event description |
| `correlation_id` | Middleware | Unique ID tracing a single user request across all layers |
| `user_id` | Context | Telegram user ID (when available) |
| `job_id` | Context | Job UUID (when processing a job) |
| `worker_id` | Context | Worker identifier (in worker context) |
| `duration_ms` | Measured | Operation duration in milliseconds |
| `component` | Manual | Component name (bot, service, worker, api) |

### 14.4 Correlation ID Flow

```
User sends message
    │
    ▼
Logging Middleware generates correlation_id (UUID4)
    │
    ▼
correlation_id is bound to structlog context for the entire request
    │
    ▼
All service calls, DB queries, cache operations, and queue
operations within this request emit logs with the same correlation_id
    │
    ▼
When a job is enqueued, correlation_id is stored in the job payload
    │
    ▼
Worker picks up job → binds correlation_id to its logging context
    │
    ▼
All worker logs for this job share the original correlation_id
    │
    ▼
End-to-end traceability from user message to file delivery
```

### 14.5 Sensitive Data Policy

The following data is **never** logged:

- Bot token
- API keys
- Database connection strings
- Redis credentials
- Full user messages (only URL portion is logged)
- Telegram file content

User Telegram IDs are logged as they are necessary for operational debugging and are not considered sensitive in this context.

---

## 15. Monitoring Strategy

### 15.1 Health Checks

| Endpoint | Type | Checks | Used By |
|---|---|---|---|
| `GET /health` | Liveness | Process is running | Container orchestrator, Uptime Kuma |
| `GET /ready` | Readiness | PostgreSQL ping, Redis ping | Container orchestrator, Uptime Kuma |

### 15.2 Uptime Kuma Monitors

| Monitor | Type | Target | Interval | Alert |
|---|---|---|---|---|
| Bot Process | HTTP | `/health` | 30s | Down > 1 min |
| Bot Readiness | HTTP | `/ready` | 60s | Down > 2 min |
| PostgreSQL | TCP/Ping | DB host:port | 60s | Down > 1 min |
| Redis | TCP/Ping | Redis host:port | 30s | Down > 1 min |
| Worker Process | HTTP | Worker `/health` | 30s | Down > 1 min |

### 15.3 Key Metrics to Track

| Metric | Source | Alert Threshold |
|---|---|---|
| Queue depth | Redis `ZCARD queue:jobs` | > 100 pending jobs |
| Active workers | Redis active set count | < configured WORKER_COUNT |
| Job processing time (p95) | Application logs | > 120 seconds |
| Job failure rate | PostgreSQL job status counts | > 10% in 5 min window |
| Cache hit ratio (file_id) | Application counter | < 30% (warn, not critical) |
| Error rate (Sentry) | Sentry | > 50 events/hour |
| API response time | FastAPI middleware | p99 > 2 seconds |
| Disk usage (temp files) | OS metrics | > 80% |
| Memory usage | OS metrics | > 85% |

### 15.4 Sentry Integration

| Setting | Value | Rationale |
|---|---|---|
| DSN | From environment variable | Per-environment isolation |
| Environment | `production` / `staging` / `development` | Filter by deploy target |
| Traces sample rate | 0.1 (10%) in production | Balance observability vs. cost |
| Error sample rate | 1.0 (100%) | Capture all errors |
| Integrations | Aiogram, FastAPI, SQLAlchemy, Redis, asyncio | Automatic instrumentation |
| Release tracking | Git SHA / version tag | Link errors to deployments |
| User context | Telegram user ID, username | Associate errors with users |
| Tags | `component`, `worker_id`, `job_id` | Filterable in Sentry dashboard |

### 15.5 Operational Dashboard Panels (Recommended)

1. **Queue Health:** Queue depth over time, enqueue/dequeue rates.
2. **Worker Health:** Active worker count, processing times, idle times.
3. **Download Success Rate:** Completed vs. failed jobs over time.
4. **Cache Efficiency:** Hit/miss ratios for file_id and metadata caches.
5. **User Activity:** Active users, downloads per hour, new registrations.
6. **Error Trends:** Sentry error count by category over time.
7. **System Resources:** CPU, memory, disk usage per container.

---

## 16. Security Principles

### 16.1 Input Validation

| Input | Validation | Action on Failure |
|---|---|---|
| URL from user | URL format validation, protocol whitelist (http, https), domain blacklist check | Return user-friendly "unsupported URL" message |
| Callback data | Cryptographic signing or schema validation | Silently ignore invalid callbacks |
| Admin API requests | API key validation, role verification | 401/403 HTTP response |
| Configuration values | Pydantic validators at startup | Fail fast — do not start the application |

### 16.2 Bot Token & Secrets Management

- Bot token, database credentials, Redis credentials, Sentry DSN, and API keys are loaded exclusively from environment variables.
- Secrets are **never** hardcoded, logged, or included in error responses.
- `.env` files are used only for local development and are `.gitignore`-d.
- In production, secrets are injected via container orchestrator secret management.

### 16.3 Rate Limiting

| Scope | Limit | Window | Enforcement |
|---|---|---|---|
| Downloads per user | 10 | 1 hour | Redis counter with sliding window |
| URL analysis per user | 20 | 1 hour | Redis counter with sliding window |
| Messages per user | 30 | 1 minute | Aiogram throttle middleware |
| Admin API | 100 | 1 minute | FastAPI middleware |

Rate limits are configurable via environment variables. Future Premium tier will have elevated limits.

### 16.4 Data Protection

- No user messages are stored beyond the URL content needed for processing.
- Download history is owned by the user and visible only to the user and moderators/owner.
- Temporary downloaded files are deleted immediately after Telegram upload.
- Database connections use SSL in production.
- Redis connections use AUTH + optional TLS in production.

### 16.5 Telegram-Specific Security

- Webhook mode validates the `X-Telegram-Bot-Api-Secret-Token` header.
- Inline keyboard callback data uses structured schemas to prevent injection.
- Bot ignores messages from non-private chats (if designed for private use) or validates group admin status.

### 16.6 Dependency Security

- Dependencies are pinned in `pyproject.toml` with exact versions.
- Regular dependency audit via `pip-audit` or equivalent.
- Docker images use minimal base images (e.g., `python:3.13-slim`).
- FFmpeg and yt-dlp are installed from official sources only.

---

## 17. Future Scalability Strategy

### 17.1 Scaling Phases

```
Phase 1: Single Server (Current Architecture)
─────────────────────────────────────────────
  • 1 Bot process
  • 1 Worker process (N async workers)
  • 1 FastAPI process
  • 1 PostgreSQL instance
  • 1 Redis instance
  • All on single server or docker-compose

  Capacity: ~1,000 daily users

Phase 2: Vertical Scaling
─────────────────────────
  • Increase WORKER_COUNT
  • Increase server resources (CPU, RAM, disk)
  • Add PostgreSQL connection pooling (PgBouncer)
  • Redis persistence tuning

  Capacity: ~5,000 daily users

Phase 3: Service Separation
────────────────────────────
  • Bot process on Server A
  • Worker pool on Server B (or multiple)
  • PostgreSQL on managed DB service
  • Redis on managed cache service
  • FastAPI behind reverse proxy

  Capacity: ~15,000 daily users

Phase 4: Horizontal Scaling
────────────────────────────
  • Multiple bot instances (webhook mode, behind load balancer)
  • Multiple worker pools consuming from shared Redis queue
  • PostgreSQL read replicas for history queries
  • Redis Cluster or Sentinel for HA
  • Object storage for temp files (S3-compatible)
  • CDN for frequently requested files

  Capacity: 20,000+ daily users
```

### 17.2 Horizontal Scaling Prerequisites (Built Into Current Architecture)

| Requirement | How It's Met |
|---|---|
| No in-process state | All state in PostgreSQL and Redis |
| Idempotent workers | Job locking + fingerprint dedup prevents double-processing |
| Shared queue | Redis-based queue accessible from any worker instance |
| Stateless bot | Bot handlers are pure functions over injected services |
| Externalized config | All tunables via environment variables |
| Graceful shutdown | Workers finish current job before stopping |

### 17.3 Future Premium System Hooks

The architecture includes the following extension points for a future Premium tier:

| Hook | Location | Status | Purpose |
|---|---|---|---|
| `users.is_premium` field | `users` table | ✅ Built | Fast boolean check for premium status |
| `users.premium_expire_at` field | `users` table | ✅ Built | Expiry tracking for subscription management |
| Priority queue levels | Queue system (§9.3) | ✅ Built | `HIGH` priority (score 0) reserved for Premium users |
| `free_daily_limit` / `premium_daily_limit` | `settings` table | ✅ Built | Per-plan download limits, dynamically configurable |
| `free_max_file_size` / `premium_max_file_size` | `settings` table | ✅ Built | Per-plan file size limits |
| `download_cooldown_seconds` / `premium_download_cooldown_seconds` | `settings` table | ✅ Built | Per-plan cooldown between downloads |
| `advertisements.target_role` | `advertisements` table | ✅ Built | Premium users skip ads by default |
| `ads_enabled` global switch | `settings` table | ✅ Built | Master ad kill switch |
| Rate limit configuration | Config + Redis | ✅ Built | Per-role rate limits |
| Quality limit configuration | Config / Settings | 🔮 Future | Per-role maximum quality |
| History retention policy | HistoryService | 🔮 Future | Extended retention for Premium |
| Concurrent download limits | JobService | 🔮 Future | More concurrent jobs for Premium |
| Playlist download support | DownloadService | 🔮 Future | Premium-only batch playlist downloads |

**Premium Benefits Summary (approved):**

| Benefit | Free User | Premium User |
|---|---|---|
| Queue priority | Normal (score 1000) | High (score 0) |
| Processing speed | Standard | Prioritized (faster queue position) |
| Advertisements | Shown per ad rules | No ads (unless explicitly targeted) |
| Max file size | Configurable (default 50 MB) | Configurable (default 2 GB) |
| Daily download limit | Configurable (default 10) | Configurable (default 100) |
| Download cooldown | Configurable (default 30s) | Configurable (default 5s) |
| Playlist downloads | ❌ | ✅ (future) |
| Additional future benefits | — | Extended as configured |

No structural database or architecture changes are required to activate Premium — only configuration values in the `settings` table and service-level condition checks.

---

## 18. Configuration Management

### 18.1 Configuration Source

All configuration is loaded from **environment variables** using `pydantic-settings`. A single `Settings` class validates and provides typed access to all configuration values.

### 18.2 Configuration Categories

#### Bot Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | str | *required* | Telegram Bot API token |
| `BOT_WEBHOOK_URL` | str | None | Webhook URL (None = polling mode) |
| `BOT_WEBHOOK_SECRET` | str | None | Webhook secret token |
| `BOT_OWNER_ID` | int | *required* | Owner's Telegram user ID |
| `BOT_PARSE_MODE` | str | `HTML` | Default message parse mode |

#### Database Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `DB_HOST` | str | `localhost` | PostgreSQL host |
| `DB_PORT` | int | `5432` | PostgreSQL port |
| `DB_NAME` | str | *required* | Database name |
| `DB_USER` | str | *required* | Database user |
| `DB_PASSWORD` | str | *required* | Database password |
| `DB_POOL_SIZE` | int | `10` | Connection pool size |
| `DB_MAX_OVERFLOW` | int | `20` | Max overflow connections |
| `DB_SSL` | bool | `false` | Enable SSL connections |

#### Redis Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `REDIS_URL` | str | `redis://localhost:6379/0` | Redis connection URL |
| `REDIS_PASSWORD` | str | None | Redis AUTH password |
| `REDIS_SSL` | bool | `false` | Enable TLS |
| `REDIS_CACHE_DB` | int | `0` | Redis DB for cache |
| `REDIS_QUEUE_DB` | int | `1` | Redis DB for queue |

#### Worker Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `WORKER_COUNT` | int | `3` | Number of concurrent workers |
| `WORKER_JOB_TIMEOUT` | int | `300` | Max seconds per job |
| `WORKER_HEARTBEAT_INTERVAL` | int | `30` | Heartbeat interval (seconds) |
| `WORKER_MAX_RETRIES` | int | `3` | Max job retry attempts |

#### Download Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `DOWNLOAD_TEMP_DIR` | str | `/tmp/downloads` | Temporary download directory |
| `DOWNLOAD_MAX_FILE_SIZE` | int | `2147483648` | Max file size (2 GB, Telegram limit) |
| `DOWNLOAD_MAX_DURATION` | int | `14400` | Max media duration (seconds) |
| `YTDLP_PATH` | str | `yt-dlp` | yt-dlp executable path |
| `FFMPEG_PATH` | str | `ffmpeg` | FFmpeg executable path |

#### Cache Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `CACHE_FILEID_TTL` | int | `2592000` | file_id cache TTL (30 days) |
| `CACHE_METADATA_TTL` | int | `3600` | Metadata cache TTL (1 hour) |
| `CACHE_LOCK_TTL` | int | `600` | Download lock TTL (10 minutes) |

#### Rate Limit Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `RATE_LIMIT_DOWNLOADS_PER_HOUR` | int | `10` | Downloads per user per hour |
| `RATE_LIMIT_ANALYSIS_PER_HOUR` | int | `20` | URL analyses per user per hour |
| `RATE_LIMIT_MESSAGES_PER_MINUTE` | int | `30` | Messages per user per minute |

#### Monitoring Configuration

| Variable | Type | Default | Description |
|---|---|---|---|
| `SENTRY_DSN` | str | None | Sentry DSN (disabled if None) |
| `SENTRY_ENVIRONMENT` | str | `development` | Sentry environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | float | `0.1` | Sentry traces sample rate |
| `LOG_LEVEL` | str | `INFO` | Minimum log level |
| `LOG_FORMAT` | str | `json` | Log format: `json` or `console` |

---

## 19. Deployment Architecture

### 19.1 Docker Compose (Development & Phase 1 Production)

```
docker-compose.yml
│
├── bot          (Python — Aiogram bot process)
├── worker       (Python — Worker pool process)
├── api          (Python — FastAPI via uvicorn)
├── postgres     (PostgreSQL 15+)
├── redis        (Redis 7+)
└── uptime-kuma  (Uptime Kuma monitoring)
```

### 19.2 Process Architecture

| Process | Entry Point | Responsibility |
|---|---|---|
| `bot` | `bot/main.py` | Telegram polling/webhook, handlers, FastAPI mount (optional) |
| `worker` | `workers/main.py` | Queue consumer pool, cleanup tasks |
| `api` | `api/main.py` | Health checks, admin endpoints, metrics |

The bot and API can optionally run in the same process (FastAPI mounted as a sub-application of the bot's ASGI app) in Phase 1, and be separated in Phase 3+.

### 19.3 Startup Sequence

```
1. Load and validate configuration (fail fast on invalid config)
2. Initialize structured logging
3. Initialize Sentry SDK
4. Connect to PostgreSQL (run Alembic migrations check)
5. Connect to Redis (verify connectivity)
6. Initialize service layer (dependency injection)
7. Register bot handlers and middlewares
8. Start worker pool (if worker process)
9. Start FastAPI server (if API process)
10. Start bot polling / webhook
11. Log "System ready" with component versions
```

### 19.4 Graceful Shutdown Sequence

```
1. Receive SIGTERM / SIGINT
2. Stop accepting new Telegram updates
3. Stop accepting new API requests
4. Signal workers to stop after current job
5. Wait for active workers to complete (with timeout)
6. Re-enqueue any incomplete jobs
7. Close Redis connections
8. Close PostgreSQL connections
9. Flush logs
10. Exit
```

---

## 20. Glossary

| Term | Definition |
|---|---|
| **file_id** | A unique identifier that Telegram assigns to every file uploaded to its servers. Using a `file_id`, files can be re-sent instantly without re-uploading. |
| **fingerprint** | A hash computed from `normalized_url + format_id + quality`. Used to identify identical download requests for caching and deduplication. |
| **normalized_url** | A URL stripped of tracking parameters, fragments, and other non-essential components. Two visually different URLs pointing to the same content should normalize to the same value. |
| **job** | A unit of work representing a single download request. Jobs are created by the service layer, enqueued in Redis, and processed by workers. |
| **worker** | An asyncio task (or process) that consumes download jobs from the Redis queue. Multiple workers run concurrently. |
| **correlation_id** | A UUID generated at the start of each user interaction. Propagated through all layers and logged with every operation for end-to-end traceability. |
| **download lock** | A Redis key that prevents duplicate concurrent downloads of the same content. Automatically expires after the configured TTL. |
| **media info** | Structured metadata about a URL's content: title, duration, available formats and qualities. Extracted via yt-dlp and cached in Redis. |
| **thin handler** | A Telegram handler that contains no business logic. It parses the update, delegates to a service, and returns the formatted result. |
| **protocol** | A Python `Protocol` class defining an abstract interface. Used to enforce the Clean Architecture dependency rule — inner layers define protocols, outer layers implement them. |
| **priority queue** | A Redis sorted set where each job's score determines its processing order. Lower scores are processed first. |
| **instant resend** | Delivering a previously downloaded file to a user by sending the cached `file_id` to Telegram, bypassing the download pipeline entirely. |
| **cooldown** | The minimum number of seconds a user must wait between consecutive downloads. Configurable per plan (free vs. premium) via the `settings` table. |
| **impression** | A single display of an advertisement to a user. Counted atomically in the `advertisements.impressions` column. |
| **CTR** | Click-Through Rate. Calculated as `clicks / impressions`. Used to measure advertisement effectiveness. |
| **ad targeting** | The mechanism by which advertisements are shown to specific user segments based on role (`user`, `premium`) and download frequency (`show_every_n_downloads`). |

---

## 21. Admin Panel V1 Requirements

### 21.1 Overview

The Admin Panel V1 is the in-bot management interface accessible to Owner and Moderator roles. All admin actions are performed via Telegram bot commands and inline keyboards — no external web dashboard is required for V1.

All configurable values are stored in the `settings` database table and cached in Redis, making them dynamically adjustable without redeployment.

### 21.2 Rate Limiting Management

**Accessible by:** Owner only.

The Owner can configure the following rate limiting parameters at runtime via bot commands:

| Setting | Setting Key | Default | Description |
|---|---|---|---|
| Free daily download limit | `free_daily_limit` | 10 | Maximum downloads per day for free users |
| Premium daily download limit | `premium_daily_limit` | 100 | Maximum downloads per day for premium users |
| Free download cooldown | `download_cooldown_seconds` | 30 | Seconds between downloads for free users |
| Premium download cooldown | `premium_download_cooldown_seconds` | 5 | Seconds between downloads for premium users |
| Free max file size | `free_max_file_size` | 50 MB | Maximum file size for free users |
| Premium max file size | `premium_max_file_size` | 2 GB | Maximum file size for premium users |

**Rate Limit Enforcement Flow:**

```
User requests download
        │
        ▼
  Middleware checks users.is_banned → reject if true
        │
        ▼
  Middleware checks users.is_premium
        │
   ┌────┴────┐
   │         │
  Free    Premium
   │         │
   ▼         ▼
  Read       Read
  free_*     premium_*
  settings   settings
   │         │
   ▼         ▼
  Check daily_download_count < daily_limit
        │
   ┌────┴────┐
   │         │
  OK       EXCEEDED
   │         │
   │         ▼
   │    Return "Daily limit reached" message
   │
   ▼
  Check cooldown (Redis: last_download:{user_id} TTL)
        │
   ┌────┴────┐
   │         │
  OK       IN_COOLDOWN
   │         │
   │         ▼
   │    Return "Please wait N seconds" message
   │
   ▼
  Check file size against max_file_size setting
        │
   ┌────┴────┐
   │         │
  OK       TOO_LARGE
   │         │
   │         ▼
   │    Return "File too large for your plan" message
   │
   ▼
  Proceed with download
```

### 21.3 User Ban System

**Accessible by:** Owner and Moderators.

| Action | Command Pattern | Fields Updated |
|---|---|---|
| Ban user | `/ban <user_id> <reason>` | `is_banned = true`, `banned_at = NOW()`, `ban_reason = <reason>` |
| Unban user | `/unban <user_id>` | `is_banned = false` (preserves `banned_at` and `ban_reason` for audit) |
| View ban info | `/userinfo <user_id>` | Reads `is_banned`, `banned_at`, `ban_reason` |

**Ban Enforcement:**

- The `auth.py` middleware checks `users.is_banned` on **every incoming update**.
- Banned users receive a static message: "Your account has been suspended. Contact support for assistance."
- All further processing is blocked for banned users — no downloads, no history, no commands.
- Ban checks use the `ix_users_is_banned` index for performance.
- When unbanned, the user's `is_banned` is set to `false`, but `banned_at` and `ban_reason` are **preserved** for moderation audit trail. These fields are overwritten only when a new ban is applied.

### 21.4 System Statistics

**Accessible by:** Owner and Moderators.

The bot provides real-time system statistics via the `/stats` command:

| Metric | Source |
|---|---|
| Total registered users | `COUNT(*) FROM users` |
| Active users today | `COUNT(*) FROM users WHERE last_activity_at >= today` |
| Total downloads today | `SUM(daily_download_count) FROM users` |
| Total downloads all-time | `SUM(total_downloads) FROM users` |
| Current queue depth | Redis `ZCARD queue:jobs` |
| Active workers | Redis active set count |
| Premium users count | `COUNT(*) FROM users WHERE is_premium = true` |
| Banned users count | `COUNT(*) FROM users WHERE is_banned = true` |
| Cache entries | `COUNT(*) FROM cached_files` |
| Errors today | `COUNT(*) FROM error_logs WHERE created_at >= today` |

---

## 22. Smart Advertisement System

### 22.1 Overview

The advertisement system is fully database-driven. Admins create, update, enable, disable, and target advertisements through bot commands or the admin API. No code changes are required for ad management.

### 22.2 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Advertisement Delivery Flow                  │
│                                                             │
│  Download completes → NotificationService sends file        │
│         │                                                   │
│         ▼                                                   │
│  AdService.should_show_ad(user)                             │
│         │                                                   │
│    ┌────┴────┐                                              │
│    │         │                                              │
│   YES       NO                                              │
│    │         │                                              │
│    ▼         ▼                                              │
│  Select    Done                                             │
│  best ad                                                    │
│    │                                                        │
│    ▼                                                        │
│  Send ad                                                    │
│  message                                                    │
│    │                                                        │
│    ▼                                                        │
│  Increment                                                  │
│  impressions                                                │
└─────────────────────────────────────────────────────────────┘
```

### 22.3 Ad Selection Algorithm

```
AdService.should_show_ad(user):

  1. IF settings.ads_enabled == false → return NO
  2. IF user.is_premium == true → return NO (unless ad targets 'premium')
  3. IF user.total_downloads % ad.show_every_n_downloads != 0 → return NO
  4. Query active ads matching user's role:
     SELECT * FROM advertisements
     WHERE is_active = true
       AND (target_role IS NULL OR target_role = user_effective_role)
     ORDER BY priority DESC
     LIMIT 1
  5. IF no matching ad → return NO
  6. Return YES + selected ad
```

### 22.4 Ad Management Commands

| Command | Role | Description |
|---|---|---|
| `/ad_create` | Owner | Interactive flow to create a new advertisement |
| `/ad_list` | Owner | List all advertisements with status and stats |
| `/ad_edit <id>` | Owner | Edit an existing advertisement |
| `/ad_toggle <id>` | Owner | Enable/disable a specific advertisement |
| `/ad_delete <id>` | Owner | Permanently delete an advertisement |
| `/ad_stats` | Owner, Moderator | View ad analytics (impressions, clicks, CTR) |
| `/ad_global <on\|off>` | Owner | Enable/disable ads globally (updates `ads_enabled` setting) |

### 22.5 Ad Analytics

| Metric | Source | Formula |
|---|---|---|
| Total impressions | `advertisements.impressions` | Direct read |
| Total clicks | `advertisements.clicks` | Direct read |
| Click-Through Rate | Computed | `clicks / impressions * 100` |
| Best performing ad | Computed | Highest CTR among active ads |
| Ads served today | Application counter (Redis) | `INCR ads_served:{date}` |

---

## 23. Future Features Roadmap

### 23.1 Overview

The following features are planned for future versions. The current architecture and database schema are designed to accommodate all of these without structural refactoring.

### 23.2 Roadmap by Priority

| Priority | Feature | Architecture Readiness | Database Readiness |
|---|---|---|---|
| ~~P1~~ | ~~Multiple language support~~ | **✅ SHIPPED — V1, Sprint 11.5 (2026-07-01), pulled forward from its original V2 slot at Owner direction.** See §23.3 for the as-built design. | ✅ Live — no migration used |
| **P1** | Payment integrations | `users.is_premium` + `premium_expire_at` built. Future `payments` + `invoices` tables (see §12.9.2). | ✅ Schema hooks built |
| **P2** | Referral system | Future `referrals` + `referral_codes` tables + `users.referred_by` column (see §12.9.3). | ✅ Schema hooks defined |
| **P2** | Advanced analytics | Current schema supports all basic analytics queries. Future `daily_stats` + `platform_daily_stats` for pre-aggregation (see §12.9.5). | ✅ Ready for aggregation tables |
| **P2** | Web dashboard | FastAPI admin API already provides data endpoints. Dashboard is a frontend-only addition. Schema fully supports it (see §12.9.4). | ✅ Ready |
| **P3** | Group support | Requires bot handlers for group context, group-level rate limits, and optionally a `groups` table. Service layer is group-agnostic — handlers translate group context. | 🔮 Minimal changes |
| **P3** | Multi-engine downloads | `media_metadata.platform` already identifies the source. Adding new engines (gallery-dl, direct HTTP, etc.) requires new downloader implementations behind the existing protocol interface. | ✅ Architecture ready |
| **P3** | Playlist downloads | Requires batch job creation from playlist URL analysis. Jobs are already individual per-media — playlists decompose into N jobs. Premium-only feature. | 🔮 Service-level addition |

### 23.3 Multi-Language System Design (IMPLEMENTED — V1 Sprint 11.5, 2026-07-01)

> This replaces the earlier design sketch (retained in git history only). The system described
> below is live: English + Arabic ship today; any further language is a content-only addition.
> Full rationale and alternatives-rejected history: MASTER_PLAN.md decisions D-061–D-064.

```
Locale resolution (core.i18n.resolve_locale, called fresh every update):
  1. users.language, IF it names a currently-enabled catalog   (explicit user choice)
  2. Settings.default_locale (env DEFAULT_LOCALE, default "en") (fallback)

  Read-only: a stored value pointing at a disabled/unknown locale is NEVER
  overwritten. Re-enabling that locale later makes it resolve correctly again
  with zero data migration.

Catalog loading (core/i18n.py, core/locales/*.json):
  - Supported languages are DISCOVERED from disk at startup, not stored in `settings`.
    Adding a language = one new JSON file with `_meta.enabled: true`. No code or
    schema change.
  - Every file carries a standardized `_meta` block:
      {"code": "ar", "native_name": "العربية", "direction": "rtl",
       "enabled": true, "version": 1}
  - DEFAULT_LOCALE's catalog is the reference: every key used anywhere in the
    codebase must exist there. Every other locale's keys must be a SUBSET of the
    reference catalog's — an orphaned/typo'd key fails startup, naming the key.
  - translate(key, locale, **kwargs) never raises: a miss in a non-default locale
    falls back to the default locale's value (logged); a miss in both falls back
    to the raw key string (logged); a bad `.format()` placeholder is caught and
    logged rather than crashing the caller.

Storage: users.language ONLY (BCP-47, D-022) — no new column, no migration.
  user_preferences.preferred_language remains reserved/unused (see §12.3 notes).
  A new user's users.language is set to DEFAULT_LOCALE at creation (never from
  Telegram's auto-detected client language, which isn't restricted to the
  languages this bot actually catalogs).

Changing language — button only, no gate, no command (two rounds of Owner
simplification during the design review superseded the original first-contact-
picker and /language-command ideas):
  - Regular users: a permanent "🌐 Change Language" inline button on the /start
    screen.
  - Owner/Moderator: a "🌐 Language" section in the admin panel.
  - Both render the same picker and share one apply path (UserService.set_language
    + a signed callback action). The pick takes effect on the very next message —
    no restart, no /start re-run.

Scope: only application UI is localized (menus, buttons, progress, errors,
notifications, help, the entire admin panel). User-generated content — ad
bodies, broadcast bodies, video titles, platform names, filenames — is never
translated. `broadcasts.target_language` (§12.3) is unrelated: it filters WHO
receives a broadcast, not what language the (always user-authored) body is in.

RTL: Telegram clients render bidi text natively per message/button — there is no
custom layout engine to adapt. The real engineering requirement is that every
catalog value is a whole-sentence template with named placeholders (e.g.
"{name}"), never built by concatenating independently-translated fragments
(fragment concatenation breaks Arabic word order).
```

### 23.4 Payment Integration Design (Future)

```
Supported Providers (planned):
  - Stripe (international)
  - YooKassa (Russia/CIS)
  - Crypto (TON, USDT)
  - Telegram Stars (native)

Flow:
  User → /premium → Select plan → Select payment method
  → Provider generates payment link → User pays
  → Webhook callback → PaymentService processes
  → users.is_premium = true, premium_expire_at = NOW() + plan.duration
  → Confirmation message sent

Database additions:
  - payments table (see §12.9.2)
  - premium_plans table (see §12.9.1)
  - user_subscriptions table (see §12.9.1)
```

### 23.5 Referral System Design (Future)

```
Flow:
  User A → /referral → Gets unique referral link
  User B → Clicks link → /start with referral code
  → System registers User B with referred_by = User A
  → Both users receive bonus (extra downloads, extended trial, etc.)

Database additions:
  - referrals table (see §12.9.3)
  - referral_codes table (see §12.9.3)
  - users.referred_by column (see §12.9.3)

Analytics:
  - Top referrers
  - Conversion rate (clicks → registrations)
  - Referral chain depth
```

---

> **End of Master Architecture Reference**
>
> This document is the single source of truth for all design decisions, component boundaries, data flows, and operational requirements of the Telegram SaaS Download Bot. All implementation must conform to this specification. Updates to this document require architectural review.
>
> **Revision History:**
> - v1.0 (2026-06-22): Initial architecture document
> - v1.1 (2026-06-22): Database redesign — 10 normalized tables replacing 3-table design
> - v1.2 (2026-06-22): Admin Panel V1 requirements, ban system, smart advertisements, premium roadmap, future features roadmap


"""Application configuration (MASTER_PLAN Task 1.1, Section 13.2).

A single ``Settings`` class covering every environment variable in the LOCKED set
(Section 13.2). Values come from process environment first, then an optional
``.env`` file, then the defaults below (Section 13.1). Secrets use ``SecretStr``
and are additionally redacted by an explicit ``__repr__`` so they never leak into
logs, tracebacks, or error messages (Section 14.3).

Only env vars belong here. Operator tunables (limits, cooldowns, retention) live
in the ``settings`` table and are read via ``SettingsService`` (Section 13.1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.constants import REDACTED, SECRET_KEY_SUBSTRINGS
from core.environment import EnvironmentMisconfiguredError, evaluate_environment_safety

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class Settings(BaseSettings):
    """Typed view over the Section 13.2 environment-variable set."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Telegram bot ---
    bot_token: SecretStr = Field(..., alias="BOT_TOKEN")
    bot_webhook_url: str = Field("", alias="BOT_WEBHOOK_URL")
    bot_webhook_secret: SecretStr = Field(SecretStr(""), alias="BOT_WEBHOOK_SECRET")
    bot_owner_telegram_id: int = Field(..., alias="BOT_OWNER_TELEGRAM_ID")
    bot_parse_mode: str = Field("HTML", alias="BOT_PARSE_MODE")
    # Empty → public api.telegram.org (50 MB upload cap). Set to a self-hosted
    # Telegram Bot API server base URL (e.g. http://bot-api:8081) to raise the cap
    # to 2 GB (D-040). Used by the bot + worker Telegram clients.
    bot_api_base_url: str = Field("", alias="BOT_API_BASE_URL")
    # Support contact the Start-home "Contact us" button opens (bugs / problems /
    # suggestions). A t.me deep link to the support account/bot.
    support_contact_url: str = Field("https://t.me/i_wbot", alias="SUPPORT_CONTACT_URL")

    # --- Deployment environment / test isolation (D-060, D-032) ---
    # Selects the deployment environment. `test` activates the §25.6 isolation
    # guards (see core.environment); the simulation runner / e2e harness require it.
    deploy_env: Literal["development", "test", "production"] = Field(
        "development", alias="DEPLOY_ENV"
    )
    # SHA-256 hex fingerprint of the PRODUCTION bot token — a one-way hash, not a
    # secret. When DEPLOY_ENV=test and sha256(BOT_TOKEN) equals this, the process
    # refuses to boot (production-fingerprint assertion, D-032/D-060). Empty → off.
    prod_bot_token_fingerprint: str = Field("", alias="PROD_BOT_TOKEN_FINGERPRINT")

    # --- Database ---
    db_host: str = Field("localhost", alias="DB_HOST")
    db_port: int = Field(5432, alias="DB_PORT")
    db_name: str = Field(..., alias="DB_NAME")
    db_user: str = Field(..., alias="DB_USER")
    db_password: SecretStr = Field(..., alias="DB_PASSWORD")
    db_pool_size: int = Field(10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(20, alias="DB_MAX_OVERFLOW")
    db_ssl: bool = Field(False, alias="DB_SSL")

    # --- Redis ---
    redis_url: str = Field(..., alias="REDIS_URL")
    redis_cache_db: int = Field(0, alias="REDIS_CACHE_DB")
    redis_queue_db: int = Field(1, alias="REDIS_QUEUE_DB")

    # --- Workers ---
    worker_count: int = Field(3, alias="WORKER_COUNT")
    worker_job_timeout: int = Field(300, alias="WORKER_JOB_TIMEOUT")
    worker_heartbeat_interval: int = Field(30, alias="WORKER_HEARTBEAT_INTERVAL")
    worker_max_retries: int = Field(3, alias="WORKER_MAX_RETRIES")

    # --- Download / media toolchain ---
    download_temp_dir: str = Field(  # nosec B108: configurable default, overridden by env
        "/tmp/downloads",  # noqa: S108
        alias="DOWNLOAD_TEMP_DIR",
    )
    ytdlp_path: str = Field("yt-dlp", alias="YTDLP_PATH")
    ffmpeg_path: str = Field("ffmpeg", alias="FFMPEG_PATH")
    # Optional residential/ISP HTTP proxy (secret; set in .env, never committed). Used —
    # only for platforms that block our datacenter IP (see routing.PROTECTED_PLATFORMS) —
    # as the primary egress for extraction + the fast aria2c download path (clean IP + many
    # parallel connections). Empty ⇒ that egress is skipped and WARP is used instead.
    ytdlp_proxy: str = Field("", alias="YTDLP_PROXY")
    # WARP (Cloudflare) SOCKS proxy — the primary egress for protected platforms since
    # 2026-07-18 (metadata always, downloads up to the size split below).
    # Internal address, not a secret. Empty ⇒ WARP egress is skipped.
    ytdlp_warp_proxy: str = Field("socks5://warp-lb:1080", alias="YTDLP_WARP_PROXY")
    # Download size split for protected platforms (routing.plan_egress): downloads at or
    # under this go over WARP, larger ones over the residential proxy (WARP is bandwidth-
    # capped and cannot use aria2c). Retune per deployment without a code change.
    ytdlp_warp_max_download_mb: int = Field(500, alias="YTDLP_WARP_MAX_DOWNLOAD_MB")
    # --- YouTube cookie pool (DESIGN_COOKIE_POOL.md) ---
    # Paths/infrastructure live here; the tunable *policy* (strategy, thresholds,
    # cooldowns, lease cap) is admin-editable at runtime via SettingsService instead.
    # Directory holding the versioned pool files (git-ignored, server-only).
    ytdlp_cookie_pool_dir: str = Field(
        "/etc/yt-dlp/cookies.d", alias="YTDLP_COOKIE_POOL_DIR"
    )
    # The pre-pool single master. Imported once as yt-01 when the pool is empty.
    ytdlp_cookie_legacy_file: str = Field(
        "/etc/yt-dlp/cookies.txt", alias="YTDLP_COOKIE_LEGACY_FILE"
    )
    # Video used to verify a freshly uploaded cookie before it is accepted (§10 step 4).
    ytdlp_cookie_canary_url: str = Field(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", alias="YTDLP_COOKIE_CANARY_URL"
    )

    # --- Cache TTLs (seconds) ---
    cache_fileid_ttl: int = Field(2_592_000, alias="CACHE_FILEID_TTL")
    cache_metadata_ttl: int = Field(3_600, alias="CACHE_METADATA_TTL")
    cache_user_ttl: int = Field(30, alias="CACHE_USER_TTL")
    cache_lock_ttl: int = Field(600, alias="CACHE_LOCK_TTL")
    cache_settings_ttl: int = Field(60, alias="CACHE_SETTINGS_TTL")

    # --- Error tracking (Sentry) ---
    sentry_dsn: SecretStr = Field(SecretStr(""), alias="SENTRY_DSN")
    sentry_environment: str = Field("development", alias="SENTRY_ENVIRONMENT")
    sentry_traces_sample_rate: float = Field(0.1, alias="SENTRY_TRACES_SAMPLE_RATE")

    # --- Logging ---
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field("json", alias="LOG_FORMAT")

    # --- API ---
    api_bind_host: str = Field(  # nosec B104: configurable default for containerized binding
        "0.0.0.0",  # noqa: S104
        alias="API_BIND_HOST",
    )
    api_bind_port: int = Field(8080, alias="API_BIND_PORT")
    # Admin HTTP API key (Task 8.3, §20.3; the §13.2 row added 2026-06-25, D-051).
    # Secret; never logged. Empty → the /v1/admin/* surface is disabled: api/main.py
    # does not mount the admin router, so those paths return 404 (the surface does not
    # exist). Set it to enable the admin API; requests then need a matching key or 401.
    admin_api_key: SecretStr = Field(SecretStr(""), alias="ADMIN_API_KEY")

    # --- Alerting ---
    telegram_alerts_chat_id: int | None = Field(None, alias="TELEGRAM_ALERTS_CHAT_ID")

    # --- Localization (Sprint 11.5) ---
    # Reference/fallback locale (BCP-47). Must match a discovered core/locales/*.json
    # file with _meta.enabled=true (core/i18n.py validates this at startup). Same
    # category as bot_parse_mode — a deploy-time rendering knob, not a per-user
    # runtime tunable, so it lives here rather than in the `settings` table.
    default_locale: str = Field("en", alias="DEFAULT_LOCALE")

    # --- Validators ---
    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}, got {value!r}")
        return normalized

    @field_validator("deploy_env", mode="before")
    @classmethod
    def _normalize_deploy_env(cls, value: object) -> object:
        # Env values arrive verbatim; accept any case/whitespace, then let the
        # Literal reject anything outside development/test/production.
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("telegram_alerts_chat_id", mode="before")
    @classmethod
    def _empty_chat_id_is_none(cls, value: object) -> object:
        # An unset optional int comes through dotenv as "" — treat it as None.
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("sentry_traces_sample_rate")
    @classmethod
    def _check_sample_rate(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("SENTRY_TRACES_SAMPLE_RATE must be between 0.0 and 1.0")
        return value

    @model_validator(mode="after")
    def _webhook_secret_required_in_webhook_mode(self) -> Settings:
        if self.bot_webhook_url and not self.bot_webhook_secret.get_secret_value():
            raise ValueError("BOT_WEBHOOK_SECRET is required when BOT_WEBHOOK_URL is set")
        return self

    @model_validator(mode="after")
    def _enforce_environment_safety(self) -> Settings:
        # Self-enforcing isolation guard (D-060): every process that builds Settings
        # runs the §25.6 safety rules. Raises a non-ValueError so it propagates out
        # of Settings() unchanged (refuse-to-boot) instead of becoming a generic
        # ValidationError. Extend the rule set in core.environment, not here.
        violations = evaluate_environment_safety(self)
        if violations:
            raise EnvironmentMisconfiguredError(violations)
        return self

    # --- Derived helpers ---
    @property
    def sentry_enabled(self) -> bool:
        """Sentry is active only when a DSN is configured (Section 15.5)."""
        return bool(self.sentry_dsn.get_secret_value())

    @property
    def admin_api_enabled(self) -> bool:
        """The HTTP admin API is mounted only when a key is configured (Task 8.3)."""
        return bool(self.admin_api_key.get_secret_value())

    @property
    def use_webhook(self) -> bool:
        """Empty webhook URL means long-polling mode (Section 13.2)."""
        return bool(self.bot_webhook_url)

    @property
    def is_test_env(self) -> bool:
        """True when running the isolated test deployment (D-032, Section 25.6)."""
        return self.deploy_env == "test"

    @property
    def is_production(self) -> bool:
        """True when running the production deployment (D-032)."""
        return self.deploy_env == "production"

    @property
    def use_local_bot_api(self) -> bool:
        """A configured base URL selects the self-hosted Bot API server (D-040)."""
        return bool(self.bot_api_base_url)

    # --- Safe representation (Section 14.3) ---
    def __repr__(self) -> str:
        parts: list[str] = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, SecretStr) or _is_secret_name(name):
                rendered = REDACTED
            else:
                rendered = repr(value)
            parts.append(f"{name}={rendered}")
        return f"Settings({', '.join(parts)})"

    __str__ = __repr__


def _is_secret_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in SECRET_KEY_SUBSTRINGS)

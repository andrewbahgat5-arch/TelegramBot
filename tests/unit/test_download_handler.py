"""Unit tests for the download handlers (MASTER_PLAN Task 5.9)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.download import (
    _human_size,
    _media_caption,
    _quality_caption,
    _subject_to_free_cap,
    handle_back,
    handle_format_choice,
    handle_quality_choice,
    handle_url,
)
from core.i18n import translate
from domain.entities.media import MediaFormatOption, MediaInfo
from domain.entities.user import UserSnapshot
from domain.enums import MediaFormat, Quality, UserRole
from domain.exceptions import ExtractionFailedError, URLNotSupportedError
from services.job_service import JobService
from services.notification_service import NotificationService
from services.queue_service import QueueService
from services.rate_limit_service import RateLimitService
from services.reward_service import RewardService
from services.settings_service import SettingsService
from services.url_analyzer import URLAnalyzerService
from tests.unit._fakes import (
    DEFAULT_RATE_SETTINGS,
    FakeActiveDownloadRepo,
    FakeCache,
    FakeCachedFileRepo,
    FakeDownloadRepo,
    FakeFileSender,
    FakeJobRepo,
    FakeJobWaiterRepo,
    FakeMediaRepo,
    FakeMessageSender,
    FakeProvider,
    FakeQueueBackend,
    FakeRewardRepo,
    FakeSettingsStore,
    FakeUser,
    FakeUserRepo,
    load_settings,
    make_cache_service,
)


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


def _user() -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=555,
        role=UserRole.USER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=_today(),
        total_downloads=0,
    )


class _NoCaptionAds:
    """AdService stand-in with the caption layer off (no ad injected)."""

    async def select_caption_ad(self, **_kw: object) -> None:
        return None

    async def maybe_show(self, **_kw: object) -> bool:
        return False


def _no_ads(_session: AsyncSession) -> object:
    return _NoCaptionAds()


_URL = "https://example.org/clip"


def _result() -> MediaInfo:
    return MediaInfo(
        platform="x",
        video_id="vid",
        title="A Clip",
        source_url=_URL,
        formats=(
            MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 1_000_000, "a"),
            MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 100_000, "b"),
        ),
    )


def _analyzer(error: Exception | None = None) -> URLAnalyzerService:
    downloader = FakeProvider("ytdlp", result=_result(), error=error)
    cache_service, _ = make_cache_service()
    return URLAnalyzerService(downloader, cache_service, FakeMediaRepo())


def _session() -> AsyncSession:
    return object()  # type: ignore[return-value]  # analyzer factory ignores it here


def _message_with_ack() -> tuple[AsyncMock, AsyncMock]:
    """A message whose .answer returns an ack message (both with async shortcuts)."""
    ack = AsyncMock(spec=Message)
    ack.edit_text = AsyncMock()
    ack.delete = AsyncMock()
    message = AsyncMock(spec=Message)
    message.text = _URL
    message.answer = AsyncMock(return_value=ack)
    message.answer_photo = AsyncMock()
    return message, ack


async def test_url_message_shows_format_keyboard() -> None:
    analyzer = _analyzer()  # _result() has no thumbnail → ack is edited in place
    message, ack = _message_with_ack()

    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )

    message.answer.assert_awaited_once()  # the instant "Analyzing…" ack
    ack.edit_text.assert_awaited_once()
    assert ack.edit_text.await_args.kwargs.get("reply_markup") is not None


async def test_url_message_unsupported_replies_without_keyboard() -> None:
    analyzer = _analyzer(error=URLNotSupportedError())
    message, ack = _message_with_ack()

    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )

    ack.edit_text.assert_awaited_once()  # the ack is edited to the error text
    assert ack.edit_text.await_args.kwargs.get("reply_markup") is None


async def test_url_message_extraction_failed_replies() -> None:
    analyzer = _analyzer(error=ExtractionFailedError())
    message, ack = _message_with_ack()
    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )
    ack.edit_text.assert_awaited_once()
    assert ack.edit_text.await_args.kwargs.get("reply_markup") is None


async def test_url_message_transient_failure_shows_try_again() -> None:
    # A transient failure that survived retries must read as temporary, not "private/removed"
    # (#12).
    from core.i18n import translate as _translate
    from domain.protocols.downloader import ProviderRetryElsewhere

    analyzer = _analyzer(error=ProviderRetryElsewhere("rate limited"))
    message, ack = _message_with_ack()
    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )
    ack.edit_text.assert_awaited_once()
    assert ack.edit_text.await_args.args[0] == _translate("download.temporary_error", "en")
    assert ack.edit_text.await_args.kwargs.get("reply_markup") is None


async def test_url_message_transient_failure_logs_platform_and_host() -> None:
    # The failure log must carry platform + host + url hash so production logs can
    # tell WHICH site is failing without ever recording the full user URL.
    from structlog.testing import capture_logs

    from domain.protocols.downloader import ProviderRetryElsewhere

    analyzer = _analyzer(error=ProviderRetryElsewhere("rate limited"))
    message, ack = _message_with_ack()
    message.text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    with capture_logs() as logs:
        await handle_url(
            message,
            _session(),
            _user(),
            lambda s: analyzer,
            _no_ads,
            CallbackSigner("k"),
            translate,
            "en",
        )
    failure = next(e for e in logs if e["event"] == "analyze_transient_failure")
    assert failure["platform"] == "youtube"
    assert failure["url_host"] == "www.youtube.com"
    assert len(failure["url_hash"]) == 12


async def test_url_message_video_unavailable_gets_honest_message() -> None:
    # The per-video bot-check wall is NOT transient — the user gets the dedicated
    # "this video needs verification, try another" text, not "busy, try again".
    from core.i18n import translate as _translate
    from domain.exceptions import VideoUnavailableError

    analyzer = _analyzer(error=VideoUnavailableError("bot-check wall"))
    message, ack = _message_with_ack()
    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )
    ack.edit_text.assert_awaited_once()
    assert ack.edit_text.await_args.args[0] == _translate("errors.video_unavailable", "en")


class _RecordingErrorLogService:
    """ErrorLogService stand-in capturing record_failure calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def record_failure(self, error: BaseException, **kwargs: object) -> None:
        self.calls.append({"error": error, **kwargs})


async def test_url_message_failure_is_persisted_to_error_log() -> None:
    # Analysis failures must land in error_logs (queryable after docker logs rotate),
    # tagged with the user and a greppable platform/host/hash context.
    from domain.protocols.downloader import ProviderRetryElsewhere

    recorder = _RecordingErrorLogService()
    analyzer = _analyzer(error=ProviderRetryElsewhere("rate limited"))
    message, ack = _message_with_ack()
    message.text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    snapshot = _user()
    await handle_url(
        message,
        _session(),
        snapshot,
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
        error_log_service_factory=lambda s: recorder,  # type: ignore[arg-type, return-value]
    )
    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["user_id"] == snapshot.id  # the internal users.id, not the telegram id
    assert "youtube" in str(call["context"])
    assert "www.youtube.com" in str(call["context"])


async def test_url_message_unexpected_error_replies_and_swallows() -> None:
    # A genuine bug in analysis must not strand the user on "Analyzing…" or crash the
    # update: the ack is edited to the generic apology and nothing propagates.
    from core.i18n import translate as _translate

    analyzer = _analyzer(error=RuntimeError("boom"))
    message, ack = _message_with_ack()
    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )
    ack.edit_text.assert_awaited_once()
    assert ack.edit_text.await_args.args[0] == _translate("errors.unexpected", "en")


async def test_url_message_no_formats_replies() -> None:
    downloader = FakeProvider(
        "ytdlp",
        result=MediaInfo(platform="x", video_id="v", title="T", source_url=_URL, formats=()),
    )
    cache_service, _ = make_cache_service()
    analyzer = URLAnalyzerService(downloader, cache_service, FakeMediaRepo())
    message, ack = _message_with_ack()
    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )
    ack.edit_text.assert_awaited_once()
    assert ack.edit_text.await_args.kwargs.get("reply_markup") is None


async def test_format_choice_expired_media_alerts() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()  # repo is empty → analyze_by_media_id returns None
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_format(123, MediaFormat.VIDEO)
    callback.answer = AsyncMock()
    await handle_format_choice(
        callback, _session(), _user(), lambda s: analyzer, _no_ads, signer, translate, "en"
    )
    callback.answer.assert_awaited_once()
    args = callback.answer.await_args
    assert args is not None and args.kwargs.get("show_alert") is True


async def test_format_choice_shows_quality_keyboard() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()
    analyzed = await analyzer.analyze(_URL)  # populate repo + cache

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_format(analyzed.media_id, MediaFormat.VIDEO)
    callback.message = AsyncMock(spec=Message)
    callback.message.photo = None  # text chooser → edit_text path
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_format_choice(
        callback, _session(), _user(), lambda s: analyzer, _no_ads, signer, translate, "en"
    )

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_format_choice_edits_caption_for_photo_chooser() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()
    analyzed = await analyzer.analyze(_URL)

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_format(analyzed.media_id, MediaFormat.VIDEO)
    callback.message = AsyncMock(spec=Message)
    callback.message.photo = [object()]  # photo chooser → edit_caption path
    callback.message.edit_caption = AsyncMock()
    callback.answer = AsyncMock()

    await handle_format_choice(
        callback, _session(), _user(), lambda s: analyzer, _no_ads, signer, translate, "en"
    )

    callback.message.edit_caption.assert_awaited_once()


async def test_back_returns_to_format_keyboard() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()
    analyzed = await analyzer.analyze(_URL)  # populate repo + cache

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_back(analyzed.media_id)
    callback.message = AsyncMock(spec=Message)
    callback.message.photo = None
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_back(
        callback, _session(), _user(), lambda s: analyzer, _no_ads, signer, translate, "en"
    )

    callback.message.edit_text.assert_awaited_once()
    call = callback.message.edit_text.await_args
    assert call is not None and call.kwargs.get("reply_markup") is not None
    callback.answer.assert_awaited_once()


async def test_back_forged_ignored() -> None:
    analyzer = _analyzer()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "b|1|deadbeef00"  # bad signature
    callback.answer = AsyncMock()
    await handle_back(
        callback,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )
    callback.answer.assert_awaited_once()


async def test_format_choice_forged_data_ignored() -> None:
    analyzer = _analyzer()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "f|1|video|deadbeef00"  # bad signature
    callback.answer = AsyncMock()

    called = False

    def factory(s: AsyncSession) -> URLAnalyzerService:
        nonlocal called
        called = True
        return analyzer

    await handle_format_choice(
        callback, _session(), _user(), factory, _no_ads, CallbackSigner("k"), translate, "en"
    )

    callback.answer.assert_awaited_once()
    assert called is False  # forged callback never reaches the analyzer


async def test_url_message_with_thumbnail_sends_photo() -> None:
    info = MediaInfo(
        platform="x",
        video_id="vid",
        title="A Clip",
        source_url=_URL,
        thumbnail_url="https://img.example/t.jpg",
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 1_000_000, "a"),),
    )
    downloader = FakeProvider("ytdlp", result=info)
    cache_service, _ = make_cache_service()
    analyzer = URLAnalyzerService(downloader, cache_service, FakeMediaRepo())
    message, ack = _message_with_ack()

    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
    )

    message.answer.assert_awaited_once()  # instant ack
    message.answer_photo.assert_awaited_once()  # thumbnail + keyboard
    ack.delete.assert_awaited_once()  # ack removed once the rich message is shown


def _user() -> UserSnapshot:
    return UserSnapshot(
        id=7,
        telegram_id=555,
        role=UserRole.USER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=_today(),
        total_downloads=0,
    )


def _owner() -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=999,
        role=UserRole.OWNER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=_today(),
        total_downloads=0,
    )


def test_owner_is_exempt_from_single_active_cap() -> None:
    # Free user is subject to the single-active cap; the Owner never is (#21).
    assert _subject_to_free_cap(_user()) is True
    assert _subject_to_free_cap(_owner()) is False


def _job_service() -> tuple[JobService, FakeQueueBackend]:
    cache_service, _ = make_cache_service()
    backend = FakeQueueBackend()
    service = JobService(
        job_repo=FakeJobRepo(),
        cached_file_repo=FakeCachedFileRepo(),
        active_download_repo=FakeActiveDownloadRepo(),
        job_waiter_repo=FakeJobWaiterRepo(),
        download_repo=FakeDownloadRepo(),
        user_repo=FakeUserRepo(),
        queue_service=QueueService(backend),
        cache_service=cache_service,
        file_sender=FakeFileSender(),
        notification_service=NotificationService(FakeMessageSender()),
        settings=load_settings(),
    )
    return service, backend


def _rate_limit_service() -> RateLimitService:
    """A permissive rate limiter: with an empty user repo, authorize_download is a no-op."""
    cache_service, _ = make_cache_service()
    settings_service = SettingsService(
        FakeSettingsStore(dict(DEFAULT_RATE_SETTINGS)), FakeCache(), cache_ttl=60
    )
    return RateLimitService(
        settings_service, cache_service, FakeUserRepo(), RewardService(FakeRewardRepo())
    )


async def test_quality_choice_enqueues_job() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()
    analyzed = await analyzer.analyze(_URL)  # populate repo so analyze_by_media_id works
    job_service, backend = _job_service()
    notifier = NotificationService(FakeMessageSender())

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_quality(analyzed.media_id, MediaFormat.VIDEO, Quality.P720)
    callback.from_user = SimpleNamespace(id=555)
    callback.answer = AsyncMock()

    await handle_quality_choice(
        callback,
        _session(),
        _user(),
        lambda s: analyzer,
        lambda s: job_service,
        lambda s: _rate_limit_service(),
        _no_ads,
        notifier,
        signer,
        translate,
        "en",
    )

    callback.answer.assert_awaited_once()
    assert await backend.depth() == 1  # a job was enqueued (cache miss)


def _single_small_analyzer(size: int) -> URLAnalyzerService:
    info = MediaInfo(
        platform="x",
        video_id="vid",
        title="A Clip",
        source_url=_URL,
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P720, size, "a"),),
    )
    cache_service, _ = make_cache_service()
    return URLAnalyzerService(FakeProvider("ytdlp", result=info), cache_service, FakeMediaRepo())


class _AutoOnPrefService:
    async def get(self, user_id: int) -> object:
        from services.user_preference_service import UserPreferences

        return UserPreferences(auto_download_small=True)


async def test_auto_download_single_small_file_skips_the_picker() -> None:
    # Item #10: opted-in user + one small format → enqueue directly, no picker shown.
    analyzer = _single_small_analyzer(5_000_000)  # 5 MB < 20 MiB ceiling
    job_service, backend = _job_service()
    message, ack = _message_with_ack()

    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
        preference_service_factory=lambda s: _AutoOnPrefService(),
        job_service_factory=lambda s: job_service,
        rate_limit_service_factory=lambda s: _rate_limit_service(),
        notification_service=NotificationService(FakeMessageSender()),
    )

    ack.delete.assert_awaited_once()  # the "Analyzing…" ack was removed
    ack.edit_text.assert_not_awaited()  # never rendered a picker
    assert await backend.depth() == 1  # enqueued straight away


async def test_auto_download_skips_large_file_and_shows_picker() -> None:
    # A single LARGE file still asks (the whole point of the opt-in).
    analyzer = _single_small_analyzer(500_000_000)  # 500 MB > ceiling
    job_service, backend = _job_service()
    message, ack = _message_with_ack()

    await handle_url(
        message,
        _session(),
        _user(),
        lambda s: analyzer,
        _no_ads,
        CallbackSigner("k"),
        translate,
        "en",
        preference_service_factory=lambda s: _AutoOnPrefService(),
        job_service_factory=lambda s: job_service,
        rate_limit_service_factory=lambda s: _rate_limit_service(),
        notification_service=NotificationService(FakeMessageSender()),
    )

    ack.edit_text.assert_awaited_once()  # picker shown
    assert await backend.depth() == 0  # nothing auto-enqueued


def _rate_limit_service_at_limit() -> RateLimitService:
    """A rate limiter that rejects: free_daily_limit=0 with the user already present."""
    cache_service, _ = make_cache_service()
    settings_service = SettingsService(
        FakeSettingsStore({**DEFAULT_RATE_SETTINGS, "free_daily_limit": ("0", "int")}),
        FakeCache(),
        cache_ttl=60,
    )
    repo = FakeUserRepo()
    repo.by_tid[555] = FakeUser(id=7, telegram_id=555)
    return RateLimitService(settings_service, cache_service, repo, RewardService(FakeRewardRepo()))


async def test_quality_choice_blocked_when_over_daily_limit() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()
    analyzed = await analyzer.analyze(_URL)
    job_service, backend = _job_service()

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_quality(analyzed.media_id, MediaFormat.VIDEO, Quality.P720)
    callback.answer = AsyncMock()

    await handle_quality_choice(
        callback,
        _session(),
        _user(),
        lambda s: analyzer,
        lambda s: job_service,
        lambda s: _rate_limit_service_at_limit(),
        _no_ads,
        NotificationService(FakeMessageSender()),
        signer,
        translate,
        "en",
    )

    # Rejected with an alert; no job enqueued.
    callback.answer.assert_awaited_once()
    args = callback.answer.await_args
    assert args is not None and args.kwargs.get("show_alert") is True
    assert await backend.depth() == 0


async def test_quality_choice_forged_ignored() -> None:
    job_service, backend = _job_service()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "q|x|video|720p|bad"
    callback.answer = AsyncMock()

    await handle_quality_choice(
        callback,
        _session(),
        _user(),
        lambda s: _analyzer(),
        lambda s: job_service,
        lambda s: _rate_limit_service(),
        _no_ads,
        NotificationService(FakeMessageSender()),
        CallbackSigner("k"),
        translate,
        "en",
    )
    callback.answer.assert_awaited_once()
    assert await backend.depth() == 0  # forged → never enqueued


def _rich_info() -> MediaInfo:
    return MediaInfo(
        platform="youtube",
        video_id="v",
        title="Clip",
        source_url="https://x/y",
        duration=181,
        formats=(
            MediaFormatOption(MediaFormat.VIDEO, Quality.P1080, 3_250_000, "137"),
            MediaFormatOption(MediaFormat.VIDEO, Quality.P360, 1_500_000, "134"),
            MediaFormatOption(MediaFormat.AUDIO, Quality.MP3, 2_800_000, "140"),
        ),
        raw={
            "view_count": 691200,
            "like_count": 9100,
            "comment_count": 147,
            "upload_date": "20210924",
            "channel": "Uzu",
            "channel_follower_count": 18100,
        },
    )


def test_quality_caption_lists_sizes_in_description() -> None:
    caption = _quality_caption(_rich_info(), MediaFormat.VIDEO, translate, "en")
    # Rich metadata header (views · likes · comments · date · channel/subscribers).
    assert "👁 691.2K" in caption
    assert "💬 147" in caption
    assert "Sep 24, 2021" in caption
    assert "18.1K subscribers" in caption
    # Each video tier is listed with its size in the description (not on a button).
    assert "1080p" in caption and "3.1 MB" in caption
    assert "360p" in caption and "1.4 MB" in caption
    # Only the chosen format is listed — no audio line on the video quality screen.
    assert "MP3" not in caption


def test_caption_links_title_and_channel() -> None:
    info = MediaInfo(
        platform="youtube",
        video_id="v",
        title="A Clip",
        source_url="https://www.youtube.com/watch?v=abc",
        duration=60,
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P1080, 3_250_000, "137"),),
        raw={"channel": "Joe HaTTab", "channel_url": "https://www.youtube.com/@JoeHattab"},
    )
    caption = _media_caption(info, translate, "en")
    # Title links to the source page; channel name links to the channel page.
    assert '<a href="https://www.youtube.com/watch?v=abc"><b>A Clip</b></a>' in caption
    assert '<a href="https://www.youtube.com/@JoeHattab">Joe HaTTab</a>' in caption


def test_caption_without_channel_url_stays_plain_text() -> None:
    # No channel_url in metadata → channel name is plain text, no dangling anchor.
    caption = _quality_caption(_rich_info(), MediaFormat.VIDEO, translate, "en")
    assert "👤 Uzu" in caption
    assert "<a" not in caption.split("👤", 1)[1]


def test_media_caption_defers_size_list_to_quality_screen() -> None:
    # The format screen shows the header but not the per-size list (formats_for=None).
    caption = _media_caption(_rich_info(), translate, "en")
    assert "👁 691.2K" in caption
    assert "3.1 MB" not in caption


def test_human_size_units() -> None:
    assert _human_size(None) is None
    assert _human_size(0) is None
    assert _human_size(500_000) == "488 KB"
    assert _human_size(3_250_000) == "3.1 MB"
    assert _human_size(3 * 1024**3) == "3.0 GB"

"""Unit tests for the compose-wizard orchestration (Sprint 9.6, D-057/D-059; Sprint 11.5 i18n)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.handlers import admin_wizard
from bot.panel.wizard import (
    STEP_AUDIENCE,
    STEP_CONTENT,
    STEP_PLACEMENT,
    STEP_PREVIEW,
    WizardState,
    step_index,
)
from core.i18n import translate
from domain.entities.user import UserSnapshot
from domain.enums import UserRole

_LOCALE = "en"


def _signer() -> CallbackSigner:
    return CallbackSigner("wizard-secret")


def _user() -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=7,
        role=UserRole.OWNER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=__import__("datetime").date(2026, 6, 27),
        total_downloads=0,
    )


class _FSM:
    """Minimal FSMContext: stores data + state in memory."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.state: str | None = None

    async def set_state(self, st: Any = None) -> None:
        self.state = st

    async def get_state(self) -> str | None:
        return self.state

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)

    async def update_data(self, data: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
        if data:
            self.data.update(data)
        self.data.update(kw)
        return dict(self.data)

    async def clear(self) -> None:
        self.data = {}
        self.state = None


class _FakeAds:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None
        self.edited: dict[str, Any] | None = None
        self.placements: list[str] = []
        self.buttons: list[tuple[str, str]] = []
        self.active: bool | None = None
        self.cleared_buttons = False
        self.ad: Any = None  # the ad returned by get() in edit mode
        self.conflicts: list[Any] = []  # active post-download ads for the #9 warning
        self.replaced_keep_id: int | None = None

    async def active_conflicts(self, placement: str, *, exclude_id: int | None = None) -> list[Any]:
        return [c for c in self.conflicts if getattr(c, "id", None) != exclude_id]

    async def replace_active_on_placement(self, placement: str, *, keep_id: int) -> list[int]:
        self.replaced_keep_id = keep_id
        return [c.id for c in self.conflicts if c.id != keep_id]

    async def create(self, fields: Any, *, created_by: int, **kw: Any) -> Any:
        self.created = {"fields": dict(fields), "created_by": created_by, **kw}
        return SimpleNamespace(id=11)

    async def get(self, ad_id: int) -> Any:
        return self.ad

    async def edit(self, ad_id: int, fields: Any) -> Any:
        self.edited = {"ad_id": ad_id, "fields": dict(fields)}
        return SimpleNamespace(id=ad_id)

    async def list_placements(self, ad_id: int) -> list[str]:
        return ["video_delivery"]

    async def list_buttons(self, ad_id: int) -> list[Any]:
        return [SimpleNamespace(text="Old", url="https://old")]

    async def set_placements(self, ad_id: int, placements: Any) -> list[str]:
        self.placements = list(placements)
        return self.placements

    async def add_button(self, ad_id: int, *, text: str, url: str) -> Any:
        self.buttons.append((text, url))
        return SimpleNamespace(id=1)

    async def clear_buttons(self, ad_id: int) -> int:
        self.cleared_buttons = True
        self.buttons = []
        return 0

    async def set_active(self, ad_id: int, active: bool) -> Any:
        self.active = active
        return SimpleNamespace(id=ad_id)


class _FakeAudience:
    def __init__(self) -> None:
        self.rules: list[tuple[int, str, str, str]] = []
        self.cleared = False

    async def add_rule(self, ad_id: int, *, effect: str, dimension: str, value: str) -> Any:
        self.rules.append((ad_id, effect, dimension, value))
        return SimpleNamespace(id=len(self.rules))

    async def list_rules(self, ad_id: int) -> list[Any]:
        return [SimpleNamespace(effect="include", dimension="plan", value="free")]

    async def clear_rules(self, ad_id: int) -> int:
        self.cleared = True
        return 0


class _FakeBroadcasts:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    async def create(self, **kw: Any) -> Any:
        self.created = kw
        return SimpleNamespace(id=7, expected_total=99)

    async def create_from_ad(self, **kw: Any) -> Any:
        self.created = kw
        return SimpleNamespace(id=8, expected_total=50)

    async def estimate_recipients(self, *, audience_mode: Any, audience_rules: Any) -> int:
        self.estimated = {"audience_mode": audience_mode, "rules": list(audience_rules)}
        return 1234


def _callback() -> Any:
    cb = AsyncMock(spec=CallbackQuery)
    cb.message = AsyncMock(spec=Message)
    cb.message.chat = SimpleNamespace(id=10)
    cb.message.message_id = 20
    cb.bot = AsyncMock()
    cb.answer = AsyncMock()
    return cb


async def _dispatch(
    cb: Any, fsm: _FSM, panel: ParsedPanel, *, ads: Any, casts: Any, aud: Any
) -> None:
    await admin_wizard.dispatch(
        cb,
        panel,
        fsm,  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        user=_user(),
        signer=_signer(),
        ad_service_factory=lambda s: ads,
        broadcast_service_factory=lambda s: casts,
        audience_service_factory=lambda s: aud,
        translate=translate,
        locale=_LOCALE,
    )


def _seed(fsm: _FSM, ws: WizardState) -> None:
    ws.chat_id, ws.message_id = 10, 20
    fsm.data["wizard"] = ws.to_data()


# --- entry + navigation ---------------------------------------------------
async def test_start_opens_audience_step() -> None:
    # No Type step: the kind is fixed by the entry section and the wizard opens straight on
    # Audience (#1/#2).
    fsm, cb = _FSM(), _callback()
    await admin_wizard.start(cb, fsm, _signer(), translate, _LOCALE, kind="ad")  # type: ignore[arg-type]
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.kind == "ad" and ws.step == STEP_AUDIENCE
    assert "Audience" in cb.bot.edit_message_text.await_args.args[0]


async def test_start_broadcast_language_first_seeds_target() -> None:
    # Language-first: the Broadcast-menu "English" shortcut opens the wizard with the
    # language recorded (scopes delivery on save) and a clean All audience to narrow.
    fsm, cb = _FSM(), _callback()
    await admin_wizard.start(
        cb,
        fsm,
        _signer(),
        translate,
        _LOCALE,
        kind="broadcast",
        target_language="en",
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.kind == "broadcast" and ws.step == STEP_AUDIENCE
    assert ws.target_language == "en"
    assert ws.audience_mode == "all"
    assert ws.rules == []


async def test_broadcast_preview_shows_recipient_estimate() -> None:
    # Navigating to Preview on a broadcast computes and shows the audience size (#7).
    fsm, cb = _FSM(), _callback()
    _seed(
        fsm,
        WizardState(kind="broadcast", step=STEP_CONTENT, content_mode="fields", content_text="hi"),
    )
    casts = _FakeBroadcasts()
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "go", step_index(STEP_PREVIEW)),
        ads=_FakeAds(),
        casts=casts,
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.step == STEP_PREVIEW
    assert ws.estimated_recipients == 1234
    assert "1,234" in cb.bot.edit_message_text.await_args.args[0]


async def test_ad_preview_has_no_recipient_estimate() -> None:
    # Ads deliver opportunistically, so their Preview shows no single reach number (#7).
    fsm, cb = _FSM(), _callback()
    _seed(
        fsm,
        WizardState(
            kind="ad",
            step=STEP_CONTENT,
            placements=["home"],
            content_mode="fields",
            content_text="hi",
        ),
    )
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "go", step_index(STEP_PREVIEW)),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.step == STEP_PREVIEW
    assert ws.estimated_recipients is None


async def test_edit_from_preview_marks_return_to_preview() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="ad", step=STEP_PREVIEW))
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "ed", step_index(STEP_AUDIENCE)),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.step == STEP_AUDIENCE and ws.return_to == "preview"


# --- audience + placement toggles -----------------------------------------
async def test_toggle_audience_preset_adds_rule_and_switches_mode() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_AUDIENCE))
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 1),  # index 1 = Free
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ["include", "plan", "free"] in ws.rules
    assert ws.audience_mode == "include"


async def test_toggle_placement_selects_code() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="ad", step=STEP_PLACEMENT))
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "ptg", 1),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert "video_delivery" in ws.placements


# --- typed input + content capture ----------------------------------------
async def test_typed_user_id_value_becomes_a_rule() -> None:
    fsm = _FSM()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_AUDIENCE))
    # Arming via a typed audience option (5 = include user_id…).
    cb = _callback()
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 5),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    assert fsm.state == admin_wizard.PanelStates.wizard_text
    msg: Any = AsyncMock(spec=Message)
    msg.text = "12345"
    await admin_wizard.on_text(
        msg,
        fsm,  # type: ignore[arg-type]
        AsyncMock(),
        object(),  # type: ignore[arg-type]
        _signer(),
        lambda s: _FakeAds(),  # type: ignore[arg-type, return-value]
        translate,
        _LOCALE,
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ["include", "user_id", "12345"] in ws.rules


async def test_content_text_sets_fields_mode() -> None:
    fsm = _FSM()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_CONTENT))
    msg: Any = AsyncMock(spec=Message)
    msg.content_type = "text"
    msg.text = "hello world"
    msg.html_text = "hello world"
    await admin_wizard.on_content(
        msg,
        fsm,  # type: ignore[arg-type]
        AsyncMock(),
        object(),  # type: ignore[arg-type]
        _signer(),
        lambda s: _FakeAds(),  # type: ignore[arg-type, return-value]
        translate,
        _LOCALE,
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.content_mode == "fields" and ws.content_text == "hello world"


async def test_content_media_sets_copy_mode() -> None:
    fsm = _FSM()
    _seed(fsm, WizardState(kind="ad", step=STEP_CONTENT))
    msg: Any = AsyncMock(spec=Message)
    msg.content_type = "photo"
    msg.text = None
    msg.chat = SimpleNamespace(id=555)
    msg.message_id = 4242
    await admin_wizard.on_content(
        msg,
        fsm,  # type: ignore[arg-type]
        AsyncMock(),
        object(),  # type: ignore[arg-type]
        _signer(),
        lambda s: _FakeAds(),  # type: ignore[arg-type, return-value]
        translate,
        _LOCALE,
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.content_mode == "copy"
    assert ws.storage_chat_id == 555 and ws.storage_message_id == 4242


# --- save -----------------------------------------------------------------
def _ready_ad() -> WizardState:
    return WizardState(
        kind="ad",
        step=STEP_PREVIEW,
        placements=["home"],
        rules=[["include", "plan", "premium"]],
        content_mode="copy",
        storage_chat_id=1,
        storage_message_id=2,
        buttons=[["Open", "https://x"]],
        internal_name="Camp",
    )


async def test_save_ad_creates_with_placements_rules_and_buttons() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, _ready_ad())
    ads, aud = _FakeAds(), _FakeAudience()
    await _dispatch(cb, fsm, ParsedPanel("w", "sv"), ads=ads, casts=_FakeBroadcasts(), aud=aud)
    assert ads.created is not None and ads.created["fields"]["delivery"] == "copy"
    assert ads.placements == ["home"]
    assert aud.rules == [(11, "include", "plan", "premium")]
    assert ads.buttons == [("Open", "https://x")]
    assert fsm.data == {}  # state cleared after a successful save
    assert "created" in cb.answer.await_args.args[0]


async def test_save_ad_text_content_uses_rich_markdown() -> None:
    # Typed text is authored as Rich Markdown and saved as a rich-delivery ad carrying the
    # raw source, so sendRichMessage renders the full format (headings/lists/details/…).
    fsm, cb = _FSM(), _callback()
    _seed(
        fsm,
        WizardState(
            kind="ad",
            step=STEP_PREVIEW,
            placements=["home"],
            content_mode="fields",
            content_text="<b>Sale</b>",
            content_markdown="# Sale\n- item",
            internal_name="Camp",
        ),
    )
    ads = _FakeAds()
    await _dispatch(
        cb, fsm, ParsedPanel("w", "sv"), ads=ads, casts=_FakeBroadcasts(), aud=_FakeAudience()
    )
    assert ads.created is not None
    assert ads.created["fields"]["delivery"] == "rich"
    assert ads.created["fields"]["text"] == "# Sale\n- item"  # raw markdown source
    assert "parse_mode" not in ads.created["fields"]


async def test_save_broadcast_uses_unified_engine() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(
        fsm,
        WizardState(
            kind="broadcast",
            step=STEP_PREVIEW,
            audience_mode="include",
            rules=[["include", "plan", "premium"]],
            content_mode="fields",
            content_text="hi all",
        ),
    )
    casts = _FakeBroadcasts()
    await _dispatch(
        cb, fsm, ParsedPanel("w", "sv"), ads=_FakeAds(), casts=casts, aud=_FakeAudience()
    )
    assert casts.created is not None
    assert casts.created["audience_mode"] == "include"
    assert casts.created["message_text"] == "hi all"
    assert "saved" in cb.answer.await_args.args[0].lower()


async def test_save_broadcast_scopes_delivery_to_target_language() -> None:
    # Language-first: a broadcast composed for English seeds an INCLUDE language rule so the
    # audience snapshot + worker fan-out only reach English users, even with a clean audience.
    fsm, cb = _FSM(), _callback()
    _seed(
        fsm,
        WizardState(
            kind="broadcast",
            step=STEP_PREVIEW,
            target_language="en",
            audience_mode="all",
            content_mode="fields",
            content_text="hello",
        ),
    )
    casts = _FakeBroadcasts()
    await _dispatch(
        cb, fsm, ParsedPanel("w", "sv"), ads=_FakeAds(), casts=casts, aud=_FakeAudience()
    )
    assert casts.created is not None
    assert casts.created["target_language"] == "en"
    rules = casts.created["audience_rules"]
    assert any(
        r.effect == "include" and r.dimension == "language" and r.value == "en" for r in rules
    )


def _ready_post_download_ad() -> WizardState:
    return WizardState(
        kind="ad",
        step=STEP_PREVIEW,
        placements=["post_download"],
        rules=[["include", "plan", "premium"]],
        content_mode="copy",
        storage_chat_id=1,
        storage_message_id=2,
        internal_name="New",
    )


async def test_save_warns_on_post_download_conflict() -> None:
    # Saving a second active post-download ad shows the Keep both / Replace / Cancel warning
    # instead of silently going live (#9).
    fsm, cb = _FSM(), _callback()
    _seed(fsm, _ready_post_download_ad())
    ads = _FakeAds()
    ads.conflicts = [SimpleNamespace(id=9, title="Existing")]
    await _dispatch(
        cb, fsm, ParsedPanel("w", "sv"), ads=ads, casts=_FakeBroadcasts(), aud=_FakeAudience()
    )
    assert ads.created is None  # not saved yet — warned first
    assert "#9" in cb.bot.edit_message_text.await_args.args[0]


async def test_save_keep_both_creates_without_replacing() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, _ready_post_download_ad())
    ads = _FakeAds()
    ads.conflicts = [SimpleNamespace(id=9, title="Existing")]
    await _dispatch(
        cb, fsm, ParsedPanel("w", "svk"), ads=ads, casts=_FakeBroadcasts(), aud=_FakeAudience()
    )
    assert ads.created is not None  # saved
    assert ads.replaced_keep_id is None  # the existing ad stays active


async def test_save_replace_disables_existing() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, _ready_post_download_ad())
    ads = _FakeAds()
    ads.conflicts = [SimpleNamespace(id=9, title="Existing")]
    await _dispatch(
        cb, fsm, ParsedPanel("w", "svr"), ads=ads, casts=_FakeBroadcasts(), aud=_FakeAudience()
    )
    assert ads.created is not None
    assert ads.replaced_keep_id == 11  # the newly created ad id (from _FakeAds.create)


async def test_save_blocks_on_invalid_and_jumps_to_step() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="ad", step=STEP_PREVIEW))  # no placement, no content
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "sv"),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.step == STEP_PLACEMENT  # jumped to the first incomplete section
    assert cb.answer.await_args.kwargs.get("show_alert") is True


async def test_cancel_clears_state() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="ad", step=STEP_AUDIENCE))
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "cx"),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    assert fsm.data == {}


async def test_cancel_returns_to_section_menu() -> None:
    # Cancel from a broadcast wizard clears state and re-renders the Broadcast section menu
    # with a confirmation (#5).
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_AUDIENCE))
    await admin_wizard.cancel(cb, fsm, _signer(), translate, _LOCALE)  # type: ignore[arg-type]
    assert fsm.data == {}
    assert cb.bot.edit_message_text.await_count == 1
    cb.answer.assert_awaited()


async def test_cancel_is_graceful_when_state_already_lost() -> None:
    # If the FSM state was already gone (e.g. a stale button), Cancel must still exit
    # cleanly by editing the current message rather than dead-ending on "expired" (#5/#6).
    fsm, cb = _FSM(), _callback()  # no wizard seeded
    await admin_wizard.cancel(cb, fsm, _signer(), translate, _LOCALE)  # type: ignore[arg-type]
    assert fsm.data == {}
    # Falls back to the callback message's own coordinates when ws is gone.
    assert cb.bot.edit_message_text.await_args.kwargs["chat_id"] == 10
    assert cb.bot.edit_message_text.await_args.kwargs["message_id"] == 20
    cb.answer.assert_awaited()


# --- edit-in-wizard (Bug-fix sprint) --------------------------------------
def _existing_ad() -> Any:
    return SimpleNamespace(
        id=5,
        title="Camp",
        is_active=True,
        priority=3,
        show_every_n_downloads=2,
        audience_mode="include",
        internal_name="Camp",
        internal_notes=None,
        delivery_mode="fields",
        content_text="Promo!",
        storage_chat_id=None,
        storage_message_id=None,
    )


async def test_start_edit_loads_ad_into_wizard() -> None:
    fsm, cb = _FSM(), _callback()
    ads, aud = _FakeAds(), _FakeAudience()
    ads.ad = _existing_ad()
    await admin_wizard.start_edit(
        cb,
        5,
        fsm,  # type: ignore[arg-type]
        _signer(),
        translate,
        _LOCALE,
        ads=ads,  # type: ignore[arg-type]
        audience=aud,  # type: ignore[arg-type]
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.editing_ad_id == 5 and ws.step == STEP_PREVIEW
    assert ws.placements == ["video_delivery"]
    assert ws.rules == [["include", "plan", "free"]]
    assert ws.buttons == [["Old", "https://old"]]
    assert ws.priority == 3 and ws.frequency == 2 and ws.content_text == "Promo!"
    assert "Preview" in cb.bot.edit_message_text.await_args.args[0]


async def test_save_edit_updates_existing_ad() -> None:
    fsm, cb = _FSM(), _callback()
    ws = WizardState(
        kind="ad",
        step=STEP_PREVIEW,
        editing_ad_id=5,
        placements=["home"],
        rules=[["include", "plan", "premium"]],
        content_mode="fields",
        content_text="New copy",
        buttons=[["Go", "https://x"]],
        enabled=False,
        internal_name="Camp",
    )
    _seed(fsm, ws)
    ads, aud = _FakeAds(), _FakeAudience()
    await _dispatch(cb, fsm, ParsedPanel("w", "sv"), ads=ads, casts=_FakeBroadcasts(), aud=aud)
    assert ads.created is None and ads.edited is not None
    assert ads.edited["ad_id"] == 5 and ads.edited["fields"]["text"] == "New copy"
    assert ads.placements == ["home"]
    assert aud.cleared and aud.rules == [(5, "include", "plan", "premium")]
    assert ads.cleared_buttons and ads.buttons == [("Go", "https://x")]
    assert ads.active is False
    assert "updated" in cb.answer.await_args.args[0]
    assert fsm.data == {}


# --- audience: All Users + collapse (Owner UX) ----------------------------
async def test_audience_all_users_clears_rules() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(
        fsm,
        WizardState(
            kind="broadcast",
            step=STEP_AUDIENCE,
            audience_mode="include",
            rules=[["include", "plan", "free"]],
        ),
    )
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 0),  # index 0 = All Users
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.rules == []
    assert ws.audience_mode == "all"


async def test_audience_free_plus_premium_collapses_to_all() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_AUDIENCE))
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 1),  # index 1 = Free
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 2),  # index 2 = Premium
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.rules == []  # both plan includes cleared
    assert ws.audience_mode == "all"


def test_audience_keyboard_shows_all_users_checked_when_no_rules() -> None:
    from bot.keyboards.admin_panel import build_wizard_audience

    signer = _signer()
    ws = WizardState(kind="broadcast", step=STEP_AUDIENCE, audience_mode="all", rules=[])
    markup = build_wizard_audience(ws, signer, _LOCALE)
    all_btn = None
    for row in markup.inline_keyboard:
        for b in row:
            p = signer.unpack_panel(b.callback_data)
            if p is not None and p.action == "atg" and p.arg == 0:
                all_btn = b
    assert all_btn is not None
    assert "☑" in all_btn.text

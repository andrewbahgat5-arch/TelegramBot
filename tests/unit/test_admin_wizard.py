"""Unit tests for the compose-wizard orchestration (Sprint 9.6, D-057/D-059)."""

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
from domain.entities.user import UserSnapshot
from domain.enums import UserRole


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
    )


def _seed(fsm: _FSM, ws: WizardState) -> None:
    ws.chat_id, ws.message_id = 10, 20
    fsm.data["wizard"] = ws.to_data()


# --- entry + navigation ---------------------------------------------------
async def test_start_opens_type_step() -> None:
    fsm, cb = _FSM(), _callback()
    await admin_wizard.start(cb, fsm, _signer(), kind="ad")  # type: ignore[arg-type]
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.kind == "ad" and ws.step == "type"
    assert "Compose" in cb.bot.edit_message_text.await_args.args[0]


async def test_type_selection_advances_to_audience() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="ad", step="type"))
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "ty", 1),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.kind == "broadcast" and ws.step == STEP_AUDIENCE


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
        ParsedPanel("w", "atg", 1),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ["include", "plan", "premium"] in ws.rules
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
async def test_typed_language_value_becomes_a_rule() -> None:
    fsm = _FSM()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_AUDIENCE))
    # Arming via a typed audience option (3 = include language…).
    cb = _callback()
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 3),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    assert fsm.state == admin_wizard.PanelStates.wizard_text
    msg: Any = AsyncMock(spec=Message)
    msg.text = "en"
    await admin_wizard.on_text(msg, fsm, AsyncMock(), object(), _signer(), lambda s: _FakeAds())  # type: ignore[arg-type]
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ["include", "language", "en"] in ws.rules


async def test_content_text_sets_fields_mode() -> None:
    fsm = _FSM()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_CONTENT))
    msg: Any = AsyncMock(spec=Message)
    msg.content_type = "text"
    msg.text = "hello world"
    msg.html_text = "hello world"
    await admin_wizard.on_content(msg, fsm, AsyncMock(), object(), _signer(), lambda s: _FakeAds())  # type: ignore[arg-type]
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
    await admin_wizard.on_content(msg, fsm, AsyncMock(), object(), _signer(), lambda s: _FakeAds())  # type: ignore[arg-type]
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
    assert "queued" in cb.answer.await_args.args[0]


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
    await admin_wizard.start_edit(cb, 5, fsm, _signer(), ads=ads, audience=aud)  # type: ignore[arg-type]
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


# --- audience mutual exclusivity (Owner UX #1/#2/#3) ----------------------
async def test_audience_selecting_opposite_side_swaps_not_conflicts() -> None:
    fsm, cb = _FSM(), _callback()
    _seed(fsm, WizardState(kind="broadcast", step=STEP_AUDIENCE))
    # Include Premium (opt 1), then Exclude Premium (opt 5) for the SAME target.
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 1),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    await _dispatch(
        cb,
        fsm,
        ParsedPanel("w", "atg", 5),
        ads=_FakeAds(),
        casts=_FakeBroadcasts(),
        aud=_FakeAudience(),
    )
    ws = WizardState.from_data(fsm.data["wizard"])
    assert ws.rules == [["exclude", "plan", "premium"]]  # never both — the side swapped
    assert ws.audience_mode == "all"  # no include rule remains
    assert ws.step == STEP_AUDIENCE  # stayed on the same screen (Owner #4/#5)


def test_audience_keyboard_hides_the_opposite_side() -> None:
    from bot.keyboards.admin_panel import build_wizard_audience

    signer = _signer()
    ws = WizardState(
        kind="broadcast",
        step=STEP_AUDIENCE,
        audience_mode="include",
        rules=[["include", "plan", "premium"]],
    )
    markup = build_wizard_audience(ws, signer)
    shown = {
        p.arg
        for row in markup.inline_keyboard
        for b in row
        if (p := signer.unpack_panel(b.callback_data)) is not None and p.action == "atg"
    }
    assert 1 in shown  # Include Premium still offered (and marked)
    assert 5 not in shown  # Exclude Premium hidden while Premium is included

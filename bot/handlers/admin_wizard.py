"""Compose-wizard orchestration (Sprint 9.6, F-2 / EP-22, D-057/D-059).

Drives the shared Ad/Broadcast wizard over the :mod:`bot.panel.wizard` engine: turns
signed ``w`` panel callbacks and typed/forwarded messages into edits of the in-progress
:class:`WizardState` (held in aiogram FSM data), renders the current step in place, and on
Save delegates to the existing services — ``AdService`` (+ ``AudienceService`` for an ad's
``ad_audience_rules`` + placements + buttons) for ads, and ``BroadcastService`` (unified
audience engine, D-055) for broadcasts. No business logic lives here beyond assembling
service calls (§9.1); validation is the engine's (§4.9).

Busy-wizard protection (#14) falls out of the panel's existing discipline: navigating to
any other section runs ``state.clear()``, discarding the in-progress wizard, so only one is
ever active per admin.
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.keyboards.admin_panel import (
    build_section_menu,
    build_wizard_audience,
    build_wizard_content,
    build_wizard_input_prompt,
    build_wizard_placement,
    build_wizard_preview,
    build_wizard_settings,
    build_wizard_type,
)
from bot.panel.registry import audience_option, placement_option
from bot.panel.states import PanelStates
from bot.panel.wizard import (
    STEP_AUDIENCE,
    STEP_CONTENT,
    STEP_PLACEMENT,
    STEP_PREVIEW,
    STEP_SETTINGS,
    STEP_TYPE,
    WizardKind,
    WizardState,
    first_invalid_step,
    next_step,
    step_at,
    step_index,
    validate_step,
)
from domain.entities.audience import AudienceRuleSpec
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.ad_service import AdService, InvalidAdError
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService, InvalidBroadcastError

AdServiceFactory = Callable[[AsyncSession], AdService]
BroadcastServiceFactory = Callable[[AsyncSession], BroadcastService]
AudienceServiceFactory = Callable[[AsyncSession], AudienceService]

_DATA_KEY = "wizard"
_AUDIENCE_MODES = ("all", "include", "exclude")
_SECTION_FOR_KIND = {"ad": "a", "broadcast": "b"}


# --- state plumbing -------------------------------------------------------
def _load(data: dict[str, object]) -> WizardState | None:
    raw = data.get(_DATA_KEY)
    return WizardState.from_data(raw) if isinstance(raw, dict) else None


async def _persist(state: FSMContext, ws: WizardState) -> None:
    await state.update_data({_DATA_KEY: ws.to_data()})


async def _edit(bot: Bot, ws: WizardState, markup: InlineKeyboardMarkup, text: str) -> None:
    try:
        await bot.edit_message_text(
            text, chat_id=ws.chat_id, message_id=ws.message_id, reply_markup=markup
        )
    except TelegramBadRequest:
        pass  # "message is not modified" — harmless when re-rendering the same screen


# --- entry ----------------------------------------------------------------
async def start(
    callback: CallbackQuery, state: FSMContext, signer: CallbackSigner, *, kind: WizardKind
) -> None:
    """Open the wizard at the Type step (kind pre-selected from the section)."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(None)
    ws = WizardState(
        kind=kind,
        step=STEP_TYPE,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await _persist(state, ws)
    await _edit(callback.bot, ws, build_wizard_type(signer), _screen_text(ws))  # type: ignore[arg-type]
    await callback.answer()


async def start_edit(
    callback: CallbackQuery,
    ad_id: int,
    state: FSMContext,
    signer: CallbackSigner,
    *,
    ads: AdService,
    audience: AudienceService,
) -> None:
    """Open the wizard pre-loaded from an existing ad, landing on the Preview edit-hub."""
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    ad = await ads.get(ad_id)
    if ad is None:
        await callback.answer("Ad not found.", show_alert=True)
        return
    placements = list(await ads.list_placements(ad_id))
    buttons = await ads.list_buttons(ad_id)
    rules = await audience.list_rules(ad_id)
    await state.set_state(None)
    ws = WizardState(
        kind="ad",
        step=STEP_PREVIEW,
        return_to="flow",
        editing_ad_id=ad.id,
        audience_mode=ad.audience_mode,
        rules=[[r.effect, r.dimension, r.value] for r in rules],
        placements=placements,
        enabled=ad.is_active,
        priority=ad.priority,
        frequency=ad.show_every_n_downloads,
        internal_name=ad.internal_name or ad.title,
        internal_notes=ad.internal_notes,
        content_mode=_content_mode_of(ad),
        content_text=ad.content_text,
        content_markdown=ad.content_text,  # stored content is the rich-markdown source
        storage_chat_id=ad.storage_chat_id,
        storage_message_id=ad.storage_message_id,
        buttons=[[b.text, b.url] for b in buttons],
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await _persist(state, ws)
    await _edit(callback.bot, ws, build_wizard_preview(ws, signer), _screen_text(ws))  # type: ignore[arg-type]
    await callback.answer()


def _content_mode_of(ad: object) -> str | None:
    if getattr(ad, "delivery_mode", None) == "copy":
        return "copy"
    if getattr(ad, "content_text", None):
        return "fields"
    return None


# --- callback dispatch ----------------------------------------------------
async def dispatch(
    callback: CallbackQuery,
    panel: ParsedPanel,
    state: FSMContext,
    *,
    session: AsyncSession,
    user: UserSnapshot,
    signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    audience_service_factory: AudienceServiceFactory,
) -> None:
    """Handle one ``w`` wizard callback. State is never cleared here (busy-state lives on)."""
    await state.set_state(None)  # a button press cancels any pending typed input
    data = await state.get_data()
    ws = _load(data)
    if ws is None or not isinstance(callback.message, Message):
        await callback.answer("This wizard expired — reopen it from the menu.", show_alert=False)
        return
    action, arg, value = panel.action, panel.arg, panel.value

    if action == "cx":
        await _cancel(callback, state, ws, signer)
        return
    if action == "sv":
        await _save(
            callback,
            state,
            ws,
            session,
            user,
            signer,
            ad_service_factory,
            broadcast_service_factory,
            audience_service_factory,
        )
        return
    if action in {"in", "no", "ct", "ba"} or (action == "atg" and _is_typed(arg)):
        await _arm_input(callback, state, ws, signer, action=action, arg=arg)
        return

    _apply(ws, action, arg, value)
    await _persist(state, ws)
    await _render(callback.bot, ws, signer, session, ad_service_factory)  # type: ignore[arg-type]
    await callback.answer()


def _is_typed(arg: int | None) -> bool:
    opt = audience_option(arg)
    return opt is not None and opt.value is None


def _apply(ws: WizardState, action: str, arg: int | None, value: int | None) -> None:
    """Mutate the wizard state for a non-input action (navigation / toggles / steppers)."""
    if action == "ty":
        ws.kind = "broadcast" if arg == 1 else "ad"
        forward = next_step(ws.kind, STEP_TYPE)
        ws.step = forward or STEP_PREVIEW
    elif action == "go":
        target = step_at(arg)
        if target is not None:
            ws.step = target
            if target == STEP_PREVIEW:
                ws.return_to = "flow"
    elif action == "ed":  # edit-from-preview hub
        target = step_at(arg)
        if target is not None:
            ws.step = target
            ws.return_to = "preview"
    elif action == "am":
        if arg is not None and 0 <= arg < len(_AUDIENCE_MODES):
            ws.audience_mode = _AUDIENCE_MODES[arg]
    elif action == "atg":
        _toggle_audience(ws, arg)
    elif action == "ptg":
        _toggle_placement(ws, arg)
    elif action == "en":
        ws.enabled = not ws.enabled
    elif action == "pr":
        ws.priority = max(0, value if value is not None else ws.priority)
    elif action == "fr":
        ws.frequency = max(1, value if value is not None else ws.frequency)
    elif action == "bc":
        ws.buttons = []


def _opposite(effect: str) -> str:
    return "exclude" if effect == "include" else "include"


def _set_rule(ws: WizardState, effect: str, dimension: str, value: str) -> None:
    """Select a target on one side, clearing it from the other — never both (Owner #1)."""
    opposite = [_opposite(effect), dimension, value]
    if opposite in ws.rules:
        ws.rules.remove(opposite)
    rule = [effect, dimension, value]
    if rule not in ws.rules:
        ws.rules.append(rule)


def _recompute_audience_mode(ws: WizardState) -> None:
    """Choosing any Include switches to include; removing the last reverts to All."""
    if any(e == "include" for e, _d, _v in ws.rules):
        ws.audience_mode = "include"
    elif ws.audience_mode == "include":
        ws.audience_mode = "all"


def _toggle_audience(ws: WizardState, arg: int | None) -> None:
    opt = audience_option(arg)
    if opt is None or opt.value is None:
        return
    rule = [opt.effect, opt.dimension, opt.value]
    if rule in ws.rules:
        ws.rules.remove(rule)  # deselect
    else:
        _set_rule(ws, opt.effect, opt.dimension, opt.value)  # select + clear opposite
    _recompute_audience_mode(ws)


def _toggle_placement(ws: WizardState, arg: int | None) -> None:
    opt = placement_option(arg)
    if opt is None:
        return
    if opt.code in ws.placements:
        ws.placements.remove(opt.code)
    else:
        ws.placements.append(opt.code)


# --- typed / forwarded input ----------------------------------------------
async def _arm_input(
    callback: CallbackQuery,
    state: FSMContext,
    ws: WizardState,
    signer: CallbackSigner,
    *,
    action: str,
    arg: int | None,
) -> None:
    prompts = {
        "in": "Send the internal name (admin-only).",
        "no": "Send internal notes (admin-only).",
        "ba": "Send the button as <code>Label | https://url</code>.",
    }
    if action == "ct":
        await state.set_state(PanelStates.wizard_content)
        await _persist(state, ws)
        prompt = (
            "📩 Send the advertisement content now (text, photo, video, … — forwarded is fine)."
        )
    else:
        field = action if action != "atg" else f"aud:{arg}"
        await state.set_state(PanelStates.wizard_text)
        await state.update_data({_DATA_KEY: ws.to_data(), "field": field})
        if action == "atg":
            opt = audience_option(arg)
            dim = opt.dimension if opt else "value"
            prompt = (
                f"Send a {dim} value ({'language code' if dim == 'language' else 'Telegram id'})."
            )
        else:
            prompt = prompts[action]
    if isinstance(callback.message, Message):
        markup = build_wizard_input_prompt(signer, back_step=step_index(ws.step))
        await _edit(callback.bot, ws, markup, f"✏️ <b>{escape(prompt)}</b>")  # type: ignore[arg-type]
    await callback.answer()


async def on_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
) -> None:
    """Capture a typed wizard value (internal name / notes / audience value / button)."""
    data = await state.get_data()
    ws = _load(data)
    field = data.get("field")
    if ws is None or not isinstance(field, str):
        await state.set_state(None)
        return
    raw = (message.text or "").strip()
    error = _apply_text(ws, field, raw)
    if error is not None:
        await message.reply(error)  # keep the state armed for another attempt
        return
    await state.set_state(None)
    await _persist(state, ws)
    await _render(bot, ws, signer, session, ad_service_factory)


def _apply_text(ws: WizardState, field: str, raw: str) -> str | None:
    if field == "in":
        ws.internal_name = raw or None
        return None
    if field == "no":
        ws.internal_notes = raw or None
        return None
    if field == "button":
        text, _, url = raw.partition("|")
        text, url = text.strip(), url.strip()
        if not text or not url.startswith(("http://", "https://", "tg://")):
            return "Send it as <code>Label | https://url</code>."
        ws.buttons.append([text, url])
        return None
    if field.startswith("aud:"):
        opt = audience_option(int(field[4:]) if field[4:].isdigit() else None)
        if opt is None:
            return None
        if opt.dimension == "user_id" and not raw.lstrip("-").isdigit():
            return "Send a numeric Telegram id."
        _set_rule(ws, opt.effect, opt.dimension, raw)  # select + clear opposite (#1)
        _recompute_audience_mode(ws)
        return None
    return None


async def on_content(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
) -> None:
    """Capture the advertisement content: plain text → fields mode, anything else → copy mode."""
    data = await state.get_data()
    ws = _load(data)
    if ws is None:
        await state.set_state(None)
        return
    if message.content_type == "text" and message.text:
        ws.content_mode = "fields"
        # Keep both renderings: the raw text is the Rich-Markdown source an ad delivers via
        # sendRichMessage (headings/lists/details/…); html_text is the broadcast send and the
        # ad's classic fallback.
        ws.content_text = message.html_text or message.text
        ws.content_markdown = message.text
        ws.storage_chat_id = None
        ws.storage_message_id = None
    else:  # preserve native Telegram content verbatim via copy_message
        ws.content_mode = "copy"
        ws.content_text = None
        ws.content_markdown = None
        ws.storage_chat_id = message.chat.id
        ws.storage_message_id = message.message_id
    await state.set_state(None)
    await _persist(state, ws)
    await _render(bot, ws, signer, session, ad_service_factory)


# --- rendering ------------------------------------------------------------
async def _render(
    bot: Bot, ws: WizardState, signer: CallbackSigner, session: AsyncSession, _ads: AdServiceFactory
) -> None:
    await _edit(bot, ws, _screen_markup(ws, signer), _screen_text(ws))


def _screen_markup(ws: WizardState, signer: CallbackSigner) -> InlineKeyboardMarkup:
    if ws.step == STEP_TYPE:
        return build_wizard_type(signer)
    if ws.step == STEP_AUDIENCE:
        return build_wizard_audience(ws, signer)
    if ws.step == STEP_PLACEMENT:
        return build_wizard_placement(ws, signer)
    if ws.step == STEP_SETTINGS:
        return build_wizard_settings(ws, signer)
    if ws.step == STEP_CONTENT:
        return build_wizard_content(ws, signer)
    return build_wizard_preview(ws, signer)


def _screen_text(ws: WizardState) -> str:
    kind = "📢 Persistent Ad" if ws.kind == "ad" else "📣 Broadcast"
    if ws.step == STEP_TYPE:
        return "🧙 <b>Compose</b>\n\nChoose what to create."
    if ws.step == STEP_AUDIENCE:
        return f"🎯 <b>Audience</b> ({kind})\n\nMode: <b>{ws.audience_mode}</b>\n{_rules_text(ws)}"
    if ws.step == STEP_PLACEMENT:
        shown = ", ".join(ws.placements) or "—"
        return f"📍 <b>Placement</b>\n\nSelected: <b>{escape(shown)}</b>"
    if ws.step == STEP_SETTINGS:
        return (
            f"⚙️ <b>Settings</b> ({kind})\n\n"
            f"Enabled: <b>{'yes' if ws.enabled else 'no'}</b> · Priority: <b>{ws.priority}</b>"
            + (f" · Every: <b>{ws.frequency}</b>" if ws.kind == "ad" else "")
            + f"\nInternal name: {escape(ws.internal_name or '—')}"
        )
    if ws.step == STEP_CONTENT:
        return f"📝 <b>Content</b>\n\n{_content_text(ws)}"
    return _preview_text(ws, kind)


def _rules_text(ws: WizardState) -> str:
    if not ws.rules:
        return "Rules: none (everyone)."
    inc = [f"{d}={v}" for e, d, v in ws.rules if e == "include"]
    exc = [f"{d}={v}" for e, d, v in ws.rules if e == "exclude"]
    lines = []
    if inc:
        lines.append("Include: " + ", ".join(escape(x) for x in inc))
    if exc:
        lines.append("Exclude: " + ", ".join(escape(x) for x in exc))
    return "\n".join(lines)


def _content_text(ws: WizardState) -> str:
    if ws.content_mode is None:
        return "No content yet — tap 📩 Send content."
    if ws.content_mode == "fields":
        preview = (ws.content_text or "")[:120]
        return f"Text content set:\n<code>{escape(preview)}</code>"
    return "Stored a forwarded/sent message (copy mode)." + (
        f"\nButtons: {len(ws.buttons)}" if ws.buttons else ""
    )


def _preview_text(ws: WizardState, kind: str) -> str:
    lines = [
        "👁 <b>Preview</b>",
        f"Type: <b>{kind}</b>",
        _rules_text(ws),
    ]
    if ws.kind == "ad":
        lines.append("Placement(s): " + (", ".join(ws.placements) or "—"))
        lines.append(f"Priority: {ws.priority} · Every: {ws.frequency}")
    lines.append(f"Enabled: {'yes' if ws.enabled else 'no'}")
    lines.append(f"Internal name: {escape(ws.internal_name or '—')}")
    if ws.internal_notes:
        lines.append(f"Notes: {escape(ws.internal_notes)}")
    lines.append(_content_text(ws))
    return "\n".join(lines)


# --- cancel + save --------------------------------------------------------
async def _cancel(
    callback: CallbackQuery, state: FSMContext, ws: WizardState, signer: CallbackSigner
) -> None:
    await state.clear()
    section = _SECTION_FOR_KIND.get(ws.kind, "a")
    if isinstance(callback.message, Message):
        await _edit(
            callback.bot,  # type: ignore[arg-type]
            ws,
            build_section_menu(section, UserRole.OWNER, signer),
            "❌ <b>Wizard cancelled.</b>",
        )
    await callback.answer("Cancelled")


async def _save(
    callback: CallbackQuery,
    state: FSMContext,
    ws: WizardState,
    session: AsyncSession,
    user: UserSnapshot,
    signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    audience_service_factory: AudienceServiceFactory,
) -> None:
    invalid = first_invalid_step(ws)
    if invalid is not None:
        ws.step = invalid
        ws.return_to = "preview"
        await _persist(state, ws)
        if isinstance(callback.message, Message):
            await _edit(callback.bot, ws, _screen_markup(ws, signer), _screen_text(ws))  # type: ignore[arg-type]
        await callback.answer(validate_step(ws, invalid) or "Incomplete", show_alert=True)
        return
    try:
        toast = (
            await _save_ad(ws, session, user, ad_service_factory, audience_service_factory)
            if ws.kind == "ad"
            else await _save_broadcast(
                ws, session, user, ad_service_factory, broadcast_service_factory
            )
        )
    except (InvalidAdError, InvalidBroadcastError) as exc:
        await callback.answer(f"Couldn't save: {exc}", show_alert=True)
        return
    await state.clear()
    section = _SECTION_FOR_KIND.get(ws.kind, "a")
    if isinstance(callback.message, Message):
        await _edit(
            callback.bot,  # type: ignore[arg-type]
            ws,
            build_section_menu(section, UserRole.OWNER, signer),
            f"✅ <b>{escape(toast)}</b>",
        )
    await callback.answer(toast)


def _ad_fields(ws: WizardState) -> dict[str, str]:
    fields: dict[str, str] = {
        "title": ws.internal_name or "Untitled ad",
        "priority": str(ws.priority),
        "every": str(max(1, ws.frequency)),
        "audience": ws.audience_mode,
    }
    if ws.internal_name:
        fields["internal_name"] = ws.internal_name
    if ws.internal_notes:
        fields["notes"] = ws.internal_notes
    if ws.content_mode == "copy":
        fields["delivery"] = "copy"
    else:
        # Typed text is authored as Rich Markdown and delivered via sendRichMessage, so it
        # renders the full format (headings/lists/collapsible blocks/images + inline styles)
        # that classic parse_mode cannot. The raw source is stored as the ad's content_text;
        # delivery falls back to a classic text send if the Bot API lacks rich messages.
        fields["delivery"] = "rich"
        fields["type"] = "text"
        fields["text"] = ws.content_markdown or ws.content_text or ""
    return fields


async def _save_ad(
    ws: WizardState,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    audience_service_factory: AudienceServiceFactory,
) -> str:
    ads = ad_service_factory(session)
    audience = audience_service_factory(session)
    if ws.editing_ad_id is not None:
        return await _update_ad(ws, ads, audience, ws.editing_ad_id)
    ad = await ads.create(
        _ad_fields(ws),
        created_by=user.id,
        storage_chat_id=ws.storage_chat_id,
        storage_message_id=ws.storage_message_id,
    )
    if ws.placements:
        await ads.set_placements(ad.id, ws.placements)
    for effect, dimension, value in ws.rules:
        await audience.add_rule(ad.id, effect=effect, dimension=dimension, value=value)
    for text, url in ws.buttons:
        await ads.add_button(ad.id, text=text, url=url)
    if not ws.enabled:
        await ads.set_active(ad.id, False)
    return f"Ad #{ad.id} created"


async def _update_ad(ws: WizardState, ads: AdService, audience: AudienceService, ad_id: int) -> str:
    """Apply an edit composition onto an existing ad (replace rules/placements/buttons)."""
    fields = _ad_fields(ws)
    if ws.content_mode == "copy":
        if ws.storage_chat_id is not None:
            fields["storage_chat_id"] = str(ws.storage_chat_id)
        if ws.storage_message_id is not None:
            fields["storage_message_id"] = str(ws.storage_message_id)
    ad = await ads.edit(ad_id, fields)
    if ad is None:
        raise InvalidAdError("That ad no longer exists.")
    if ws.placements:
        await ads.set_placements(ad_id, ws.placements)
    await audience.clear_rules(ad_id)
    for effect, dimension, value in ws.rules:
        await audience.add_rule(ad_id, effect=effect, dimension=dimension, value=value)
    await ads.clear_buttons(ad_id)
    for text, url in ws.buttons:
        await ads.add_button(ad_id, text=text, url=url)
    await ads.set_active(ad_id, ws.enabled)
    return f"Ad #{ad_id} updated"


async def _save_broadcast(
    ws: WizardState,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
) -> str:
    casts = broadcast_service_factory(session)
    rules = [AudienceRuleSpec(e, d, v) for e, d, v in ws.rules]
    if ws.content_mode == "copy":
        ads = ad_service_factory(session)
        ad = await ads.create(
            {"title": ws.internal_name or "Broadcast", "delivery": "copy"},
            created_by=user.id,
            storage_chat_id=ws.storage_chat_id,
            storage_message_id=ws.storage_message_id,
        )
        for text, url in ws.buttons:
            await ads.add_button(ad.id, text=text, url=url)
        broadcast = await casts.create_from_ad(
            created_by_user_id=user.id,
            advertisement_id=ad.id,
            audience_mode=ws.audience_mode,
            audience_rules=rules,
        )
    else:
        broadcast = await casts.create(
            created_by_user_id=user.id,
            message_text=ws.content_text or "",
            audience_mode=ws.audience_mode,
            audience_rules=rules,
        )
    return f"Broadcast #{broadcast.id} queued to {broadcast.expected_total} users"

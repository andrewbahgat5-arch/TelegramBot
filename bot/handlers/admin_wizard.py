"""Compose-wizard orchestration (Sprint 9.6, F-2 / EP-22, D-057/D-059; Sprint 11.5 i18n).

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

Every screen is rendered in the acting admin's own ``locale`` (Sprint 11.5); ``WizardState``
carries no locale of its own (the wizard is a single, short-lived conversation, always
driven by the same admin, so the request's resolved locale is always the right one).
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
from core.i18n import Translator
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
    callback: CallbackQuery,
    state: FSMContext,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
    *,
    kind: WizardKind,
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
    await _edit(
        callback.bot,  # type: ignore[arg-type]
        ws,
        build_wizard_type(signer, locale),
        _screen_text(ws, translate, locale),
    )
    await callback.answer()


async def start_edit(
    callback: CallbackQuery,
    ad_id: int,
    state: FSMContext,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
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
        await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
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
    await _edit(
        callback.bot,  # type: ignore[arg-type]
        ws,
        build_wizard_preview(ws, signer, locale),
        _screen_text(ws, translate, locale),
    )
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
    translate: Translator,
    locale: str,
) -> None:
    """Handle one ``w`` wizard callback. State is never cleared here (busy-state lives on)."""
    await state.set_state(None)  # a button press cancels any pending typed input
    data = await state.get_data()
    ws = _load(data)
    if ws is None or not isinstance(callback.message, Message):
        await callback.answer(translate("panel.wizard.expired", locale), show_alert=False)
        return
    action, arg, value = panel.action, panel.arg, panel.value

    if action == "cx":
        await _cancel(callback, state, ws, signer, translate, locale)
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
            translate,
            locale,
        )
        return
    if action in {"in", "no", "ct", "ba"} or (action == "atg" and _is_typed(arg)):
        await _arm_input(callback, state, ws, signer, translate, locale, action=action, arg=arg)
        return

    _apply(ws, action, arg, value)
    await _persist(state, ws)
    await _render(callback.bot, ws, signer, translate, locale)  # type: ignore[arg-type]
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
    translate: Translator,
    locale: str,
    *,
    action: str,
    arg: int | None,
) -> None:
    prompt_keys = {
        "in": "panel.wizard.prompt_internal_name",
        "no": "panel.wizard.prompt_notes",
        "ba": "panel.wizard.prompt_button",
    }
    if action == "ct":
        await state.set_state(PanelStates.wizard_content)
        await _persist(state, ws)
        prompt = translate("panel.wizard.prompt_content", locale)
    else:
        field = action if action != "atg" else f"aud:{arg}"
        await state.set_state(PanelStates.wizard_text)
        await state.update_data({_DATA_KEY: ws.to_data(), "field": field})
        if action == "atg":
            opt = audience_option(arg)
            dim = opt.dimension if opt else "value"
            hint_key = (
                "panel.wizard.hint_language_code"
                if dim == "language"
                else "panel.wizard.hint_telegram_id"
            )
            prompt = translate(
                "panel.wizard.prompt_audience_value",
                locale,
                dim=dim,
                hint=translate(hint_key, locale),
            )
        else:
            prompt = translate(prompt_keys[action], locale)
    if isinstance(callback.message, Message):
        markup = build_wizard_input_prompt(signer, locale, back_step=step_index(ws.step))
        await _edit(
            callback.bot,  # type: ignore[arg-type]
            ws,
            markup,
            translate("panel.wizard.input_prompt_wrapper", locale, prompt=escape(prompt)),
        )
    await callback.answer()


async def on_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    """Capture a typed wizard value (internal name / notes / audience value / button)."""
    data = await state.get_data()
    ws = _load(data)
    field = data.get("field")
    if ws is None or not isinstance(field, str):
        await state.set_state(None)
        return
    raw = (message.text or "").strip()
    error = _apply_text(ws, field, raw, translate, locale)
    if error is not None:
        await message.reply(error)  # keep the state armed for another attempt
        return
    await state.set_state(None)
    await _persist(state, ws)
    await _render(bot, ws, signer, translate, locale)


def _apply_text(
    ws: WizardState, field: str, raw: str, translate: Translator, locale: str
) -> str | None:
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
            return translate("panel.wizard.error_button_format", locale)
        ws.buttons.append([text, url])
        return None
    if field.startswith("aud:"):
        opt = audience_option(int(field[4:]) if field[4:].isdigit() else None)
        if opt is None:
            return None
        if opt.dimension == "user_id" and not raw.lstrip("-").isdigit():
            return translate("panel.wizard.error_numeric_id", locale)
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
    translate: Translator,
    locale: str,
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
    await _render(bot, ws, signer, translate, locale)


# --- rendering ------------------------------------------------------------
async def _render(
    bot: Bot, ws: WizardState, signer: CallbackSigner, translate: Translator, locale: str
) -> None:
    await _edit(bot, ws, _screen_markup(ws, signer, locale), _screen_text(ws, translate, locale))


def _screen_markup(ws: WizardState, signer: CallbackSigner, locale: str) -> InlineKeyboardMarkup:
    if ws.step == STEP_TYPE:
        return build_wizard_type(signer, locale)
    if ws.step == STEP_AUDIENCE:
        return build_wizard_audience(ws, signer, locale)
    if ws.step == STEP_PLACEMENT:
        return build_wizard_placement(ws, signer, locale)
    if ws.step == STEP_SETTINGS:
        return build_wizard_settings(ws, signer, locale)
    if ws.step == STEP_CONTENT:
        return build_wizard_content(ws, signer, locale)
    return build_wizard_preview(ws, signer, locale)


def _kind_label(ws: WizardState, translate: Translator, locale: str) -> str:
    return translate(
        "panel.wizard.persistent_ad" if ws.kind == "ad" else "panel.wizard.broadcast_type", locale
    )


def _screen_text(ws: WizardState, translate: Translator, locale: str) -> str:
    kind = _kind_label(ws, translate, locale)
    if ws.step == STEP_TYPE:
        return translate("panel.wizard.compose_title", locale)
    if ws.step == STEP_AUDIENCE:
        return translate(
            "panel.wizard.audience_screen",
            locale,
            kind=kind,
            mode=ws.audience_mode,
            rules=_rules_text(ws, translate, locale),
        )
    if ws.step == STEP_PLACEMENT:
        shown = ", ".join(ws.placements) or "—"
        return translate("panel.wizard.placement_screen", locale, selected=escape(shown))
    if ws.step == STEP_SETTINGS:
        yes_no = translate("panel.wizard.yes" if ws.enabled else "panel.wizard.no", locale)
        freq_suffix = (
            translate("panel.wizard.frequency_suffix", locale, frequency=ws.frequency)
            if ws.kind == "ad"
            else ""
        )
        return translate(
            "panel.wizard.settings_screen",
            locale,
            kind=kind,
            enabled=yes_no,
            priority=ws.priority,
            frequency_suffix=freq_suffix,
            name=escape(ws.internal_name or "—"),
        )
    if ws.step == STEP_CONTENT:
        return translate(
            "panel.wizard.content_screen", locale, body=_content_text(ws, translate, locale)
        )
    return _preview_text(ws, kind, translate, locale)


def _rules_text(ws: WizardState, translate: Translator, locale: str) -> str:
    if not ws.rules:
        return translate("panel.wizard.rules_none", locale)
    inc = [f"{d}={v}" for e, d, v in ws.rules if e == "include"]
    exc = [f"{d}={v}" for e, d, v in ws.rules if e == "exclude"]
    lines = []
    if inc:
        lines.append(
            translate("panel.wizard.rules_include", locale, items=", ".join(escape(x) for x in inc))
        )
    if exc:
        lines.append(
            translate("panel.wizard.rules_exclude", locale, items=", ".join(escape(x) for x in exc))
        )
    return "\n".join(lines)


def _content_text(ws: WizardState, translate: Translator, locale: str) -> str:
    if ws.content_mode is None:
        return translate("panel.wizard.content_none", locale)
    if ws.content_mode == "fields":
        preview = (ws.content_text or "")[:120]
        return translate("panel.wizard.content_fields", locale, preview=escape(preview))
    suffix = (
        translate("panel.wizard.content_copy_buttons", locale, count=len(ws.buttons))
        if ws.buttons
        else ""
    )
    return translate("panel.wizard.content_copy", locale) + suffix


def _preview_text(ws: WizardState, kind: str, translate: Translator, locale: str) -> str:
    lines = [
        translate("panel.wizard.preview_title", locale),
        translate("panel.wizard.preview_type", locale, kind=kind),
        _rules_text(ws, translate, locale),
    ]
    if ws.kind == "ad":
        placements = ", ".join(ws.placements) or "—"
        lines.append(translate("panel.wizard.preview_placements", locale, placements=placements))
        lines.append(
            translate(
                "panel.wizard.preview_priority_freq",
                locale,
                priority=ws.priority,
                frequency=ws.frequency,
            )
        )
    yes_no = translate("panel.wizard.yes" if ws.enabled else "panel.wizard.no", locale)
    lines.append(translate("panel.wizard.preview_enabled", locale, enabled=yes_no))
    lines.append(
        translate(
            "panel.wizard.preview_internal_name", locale, name=escape(ws.internal_name or "—")
        )
    )
    if ws.internal_notes:
        lines.append(
            translate("panel.wizard.preview_notes", locale, notes=escape(ws.internal_notes))
        )
    lines.append(_content_text(ws, translate, locale))
    return "\n".join(lines)


# --- cancel + save --------------------------------------------------------
async def _cancel(
    callback: CallbackQuery,
    state: FSMContext,
    ws: WizardState,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    await state.clear()
    section = _SECTION_FOR_KIND.get(ws.kind, "a")
    if isinstance(callback.message, Message):
        await _edit(
            callback.bot,  # type: ignore[arg-type]
            ws,
            build_section_menu(section, UserRole.OWNER, signer, locale),
            translate("panel.wizard.cancelled", locale),
        )
    await callback.answer(translate("panel.wizard.cancelled_toast", locale))


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
    translate: Translator,
    locale: str,
) -> None:
    invalid = first_invalid_step(ws)
    if invalid is not None:
        ws.step = invalid
        ws.return_to = "preview"
        await _persist(state, ws)
        if isinstance(callback.message, Message):
            await _edit(
                callback.bot,  # type: ignore[arg-type]
                ws,
                _screen_markup(ws, signer, locale),
                _screen_text(ws, translate, locale),
            )
        await callback.answer(
            validate_step(ws, invalid) or translate("panel.wizard.incomplete", locale),
            show_alert=True,
        )
        return
    try:
        toast = (
            await _save_ad(
                ws, session, user, ad_service_factory, audience_service_factory, translate, locale
            )
            if ws.kind == "ad"
            else await _save_broadcast(
                ws, session, user, ad_service_factory, broadcast_service_factory, translate, locale
            )
        )
    except (InvalidAdError, InvalidBroadcastError) as exc:
        await callback.answer(
            translate("panel.wizard.save_failed", locale, error=str(exc)), show_alert=True
        )
        return
    await state.clear()
    section = _SECTION_FOR_KIND.get(ws.kind, "a")
    if isinstance(callback.message, Message):
        await _edit(
            callback.bot,  # type: ignore[arg-type]
            ws,
            build_section_menu(section, UserRole.OWNER, signer, locale),
            f"✅ <b>{escape(toast)}</b>",
        )
    await callback.answer(toast)


def _ad_fields(ws: WizardState) -> dict[str, str]:
    # "Untitled ad" is a system fallback baked into the persisted ad.title (admin-facing
    # label, not shown to end users) — kept as a fixed literal rather than translated, so
    # a stored title never depends on which locale the creating admin happened to be using
    # (Sprint 11.5 requirement #3: never translate stored/user-generated content).
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
    translate: Translator,
    locale: str,
) -> str:
    ads = ad_service_factory(session)
    audience = audience_service_factory(session)
    if ws.editing_ad_id is not None:
        return await _update_ad(ws, ads, audience, ws.editing_ad_id, translate, locale)
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
    return translate("panel.wizard.ad_created", locale, id=ad.id)


async def _update_ad(
    ws: WizardState,
    ads: AdService,
    audience: AudienceService,
    ad_id: int,
    translate: Translator,
    locale: str,
) -> str:
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
    return translate("panel.wizard.ad_updated", locale, id=ad_id)


async def _save_broadcast(
    ws: WizardState,
    session: AsyncSession,
    user: UserSnapshot,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    translate: Translator,
    locale: str,
) -> str:
    casts = broadcast_service_factory(session)
    rules = [AudienceRuleSpec(e, d, v) for e, d, v in ws.rules]
    if ws.content_mode == "copy":
        ads = ad_service_factory(session)
        # "Broadcast" fallback title: same reasoning as _ad_fields — a fixed literal, not
        # translated (it becomes stored ad.title, admin-facing only).
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
    return translate(
        "panel.wizard.broadcast_queued", locale, id=broadcast.id, count=broadcast.expected_total
    )

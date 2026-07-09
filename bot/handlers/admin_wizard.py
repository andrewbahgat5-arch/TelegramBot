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
    build_ad_conflict_confirm,
    build_section_menu,
    build_wizard_audience,
    build_wizard_content,
    build_wizard_input_prompt,
    build_wizard_placement,
    build_wizard_preview,
    build_wizard_settings,
)
from bot.panel.registry import audience_option, placement_option
from bot.panel.states import PanelStates
from bot.panel.wizard import (
    STEP_AUDIENCE,
    STEP_CONTENT,
    STEP_PLACEMENT,
    STEP_PREVIEW,
    STEP_SETTINGS,
    WizardKind,
    WizardState,
    first_invalid_step,
    first_step,
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
_AUDIENCE_MODES = ("all", "include")
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
    target_language: str | None = None,
) -> None:
    """Open the wizard at its first real step (Audience).

    The ``kind`` (Ad vs Broadcast) is fixed by the section the admin entered from, so the
    wizard never re-asks it (#1/#2). ``target_language`` seeds the language picked on the
    Ads/Broadcast menu before the wizard opened (language-first creation) — never re-asked;
    for broadcasts it also scopes delivery to that language (see :func:`_save_broadcast`).
    The wizard always opens on a clean ``all`` audience; the admin narrows it (plan, extra
    rules) on the Audience screen.
    """
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(None)
    ws = WizardState(
        kind=kind,
        step=first_step(kind),
        target_language=target_language,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
    )
    await _persist(state, ws)
    await _render(callback.bot, ws, signer, translate, locale)  # type: ignore[arg-type]
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

    if action == "cx":  # defensive: Cancel is a read action, normally routed via cancel()
        await cancel(callback, state, signer, translate, locale)
        return
    if action in {"sv", "svk", "svr", "pb"}:
        if action in {"svk", "svr"}:  # answer to the post-download conflict warning (#9)
            ws.conflict_ack = True
            ws.conflict_replace = action == "svr"
        if action == "pb":  # Publish (broadcasts only): send now, and save automatically
            ws.publish = True
        elif action == "sv":  # Save (broadcasts: draft, never sent; ads: the only Save)
            ws.publish = False
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
    await _refresh_estimate(ws, session, broadcast_service_factory)
    await _persist(state, ws)
    await _render(callback.bot, ws, signer, translate, locale)  # type: ignore[arg-type]
    await callback.answer()


async def _refresh_estimate(
    ws: WizardState,
    session: AsyncSession,
    broadcast_service_factory: BroadcastServiceFactory,
) -> None:
    """Recompute the broadcast recipient estimate whenever the Preview step is shown (#7).

    Best-effort: an estimate must never block the wizard, so any failure just leaves the
    count unknown. Only broadcasts show a count (a broadcast is a one-shot send to a fixed
    audience); ads deliver opportunistically over time, so a single reach number would
    mislead.
    """
    if ws.step != STEP_PREVIEW or ws.kind != "broadcast":
        ws.estimated_recipients = None
        return
    try:
        casts = broadcast_service_factory(session)
        rules = [AudienceRuleSpec(e, d, v) for e, d, v in ws.rules]
        ws.estimated_recipients = await casts.estimate_recipients(
            audience_mode=ws.audience_mode, audience_rules=rules
        )
    except Exception:  # an estimate is advisory; it must never break composing
        ws.estimated_recipients = None


def _is_typed(arg: int | None) -> bool:
    opt = audience_option(arg)
    return opt is not None and opt.value is None


def _apply(ws: WizardState, action: str, arg: int | None, value: int | None) -> None:
    """Mutate the wizard state for a non-input action (navigation / toggles / steppers)."""
    if action == "go":
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


_INCLUDE_FREE = ["include", "plan", "free"]
_INCLUDE_PREMIUM = ["include", "plan", "premium"]


def _collapse_all_users(ws: WizardState) -> None:
    """Free + Premium together == everyone, so collapse the redundant pair to All (#3).

    In SQL these two include rules OR within the ``plan`` dimension to ``~premium OR
    premium`` = every user (``infrastructure/database/audience_query.py``), so keeping both
    is duplicated targeting. Selecting both simply clears them and drops back to the All
    audience — a single, internally-consistent way to say "everyone".
    """
    if _INCLUDE_FREE in ws.rules and _INCLUDE_PREMIUM in ws.rules:
        ws.rules.remove(_INCLUDE_FREE)
        ws.rules.remove(_INCLUDE_PREMIUM)


def _recompute_audience_mode(ws: WizardState) -> None:
    """Normalize the audience: collapse Free+Premium → All, then reconcile the mode.

    Choosing any Include switches the mode to include; removing the last include (or
    collapsing Free+Premium) reverts to All.
    """
    _collapse_all_users(ws)
    if any(e == "include" for e, _d, _v in ws.rules):
        ws.audience_mode = "include"
    elif ws.audience_mode == "include":
        ws.audience_mode = "all"


def _toggle_audience(ws: WizardState, arg: int | None) -> None:
    opt = audience_option(arg)
    if opt is None or opt.value is None:
        return
    if opt.dimension == "__all__":
        ws.rules.clear()
        ws.audience_mode = "all"
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
    if field == "ba":
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
    if ws.step == STEP_AUDIENCE:
        return translate(
            "panel.wizard.audience_screen",
            locale,
            kind=kind,
            mode=translate(f"panel.audience.mode.{ws.audience_mode}", locale),
            rules=_rules_text(ws, translate, locale),
        )
    if ws.step == STEP_PLACEMENT:
        shown = ", ".join(ws.placements) or "—"
        text = translate("panel.wizard.placement_screen", locale, selected=escape(shown))
        if "caption" in ws.placements:  # explain the text+buttons-only limitation (#caption)
            text += "\n\n" + translate("panel.placement.caption_warning", locale)
        return text
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
    if ws.kind == "broadcast" and ws.estimated_recipients is not None:
        # Count only — never names (#7): lets the admin sanity-check the audience size
        # before sending.
        lines.append(
            translate(
                "panel.wizard.preview_recipients",
                locale,
                count=f"{ws.estimated_recipients:,}",
            )
        )
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
        # Enabled / internal name are ad-only concepts (a broadcast is a one-shot send).
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
async def cancel(
    callback: CallbackQuery,
    state: FSMContext,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Safely exit the wizard from any step (#5).

    Cancel (``w/cx``) is a *read*-tier action, so it is routed here from the panel's read
    handler rather than the wizard dispatch — the old code let the read handler's blanket
    ``state.clear()`` wipe the wizard and then render nothing, so Cancel looked dead. This
    reads the kind *before* clearing, drops the FSM state, and returns to the originating
    section menu (Advertisements / Broadcast) with a confirmation. Resilient when the state
    was already lost: it falls back to editing the current message directly.
    """
    data = await state.get_data()
    ws = _load(data)
    await state.clear()
    section = _SECTION_FOR_KIND.get(ws.kind, "a") if ws is not None else "a"
    if isinstance(callback.message, Message):
        markup = build_section_menu(section, UserRole.OWNER, signer, locale)
        text = translate("panel.wizard.cancelled", locale)
        # Prefer the wizard's own message coordinates; fall back to the callback's message
        # when the state (and thus ws) was already lost.
        chat_id = ws.chat_id if ws and ws.chat_id is not None else callback.message.chat.id
        message_id = (
            ws.message_id if ws and ws.message_id is not None else callback.message.message_id
        )
        try:
            await callback.bot.edit_message_text(  # type: ignore[union-attr]
                text, chat_id=chat_id, message_id=message_id, reply_markup=markup
            )
        except TelegramBadRequest:
            pass
    await callback.answer(translate("panel.wizard.cancelled_toast", locale))


_POST_DOWNLOAD = "post_download"


async def _post_download_conflicts(
    ws: WizardState, session: AsyncSession, ad_service_factory: AdServiceFactory
) -> list[object]:
    """Other active post-download ads that would coexist with this one on Save (#9).

    Only ads (not broadcasts) that are being enabled on the post-download placement can
    conflict, and the admin is asked at most once (``conflict_ack``).
    """
    if ws.kind != "ad" or not ws.enabled or ws.conflict_ack:
        return []
    if _POST_DOWNLOAD not in ws.placements:
        return []
    ads = ad_service_factory(session)
    return list(await ads.active_conflicts(_POST_DOWNLOAD, exclude_id=ws.editing_ad_id))


def _wizard_conflict_text(
    ws: WizardState, conflicts: list[object], translate: Translator, locale: str
) -> str:
    active_lines = "\n".join(
        translate(
            "panel.ads.conflict.active_row",
            locale,
            id=getattr(ad, "id", "?"),
            title=escape(str(getattr(ad, "title", ""))),
        )
        for ad in conflicts
    )
    return "\n".join(
        [
            f"⚠️ <b>{escape(translate('panel.ads.conflict.title', locale))}</b>",
            "",
            translate("panel.ads.conflict.body", locale),
            "",
            translate("panel.ads.conflict.already_active", locale),
            active_lines,
            "",
            translate(
                "panel.ads.conflict.about_to_create",
                locale,
                title=escape(ws.internal_name or "Untitled ad"),
            ),
        ]
    )


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
    conflicts = await _post_download_conflicts(ws, session, ad_service_factory)
    if conflicts:  # warn before a second post-download ad goes live (#9)
        await _persist(state, ws)
        if isinstance(callback.message, Message):
            await _edit(
                callback.bot,  # type: ignore[arg-type]
                ws,
                build_ad_conflict_confirm(
                    signer,
                    locale,
                    keep=("w", "svk", None),
                    replace=("w", "svr", None),
                    cancel=("w", "go", step_index(STEP_PREVIEW)),
                ),
                _wizard_conflict_text(ws, conflicts, translate, locale),
            )
        await callback.answer()
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
    if ws.target_language:
        fields["language"] = ws.target_language
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
    elif ws.conflict_replace:  # "Replace existing" answer to the post-download warning (#9)
        await ads.replace_active_on_placement(_POST_DOWNLOAD, keep_id=ad.id)
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
    if ws.enabled and ws.conflict_replace:  # "Replace existing" answer (#9)
        await ads.replace_active_on_placement(_POST_DOWNLOAD, keep_id=ad_id)
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
    """Publish (send now) or Save (draft, never sent) — both persist the composition.

    Publish also saves automatically: the only difference is the stored ``status``
    (``pending`` vs ``draft``), so the same audience/content assembly below covers both.
    """
    casts = broadcast_service_factory(session)
    rules = [AudienceRuleSpec(e, d, v) for e, d, v in ws.rules]
    # Language-first delivery: the language picked before the wizard opened scopes the
    # audience, so an English broadcast reaches only English users. Injected as an INCLUDE
    # language rule (ANDed with any plan/other includes the admin added); it activates the
    # include path even when the admin left the mode on "all". (An admin who deliberately
    # switches to "exclude" mode overrides this — includes are ignored there by design.)
    if ws.target_language and not any(r.dimension == "language" for r in rules):
        rules.append(AudienceRuleSpec("include", "language", ws.target_language))
    status = "pending" if ws.publish else "draft"
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
            target_language=ws.target_language,
            audience_mode=ws.audience_mode,
            audience_rules=rules,
            status=status,
        )
    else:
        broadcast = await casts.create(
            created_by_user_id=user.id,
            message_text=ws.content_text or "",
            target_language=ws.target_language,
            audience_mode=ws.audience_mode,
            audience_rules=rules,
            status=status,
        )
    if ws.publish:
        return translate(
            "panel.wizard.broadcast_published",
            locale,
            id=broadcast.id,
            count=broadcast.expected_total,
        )
    return translate("panel.wizard.broadcast_saved", locale, id=broadcast.id)

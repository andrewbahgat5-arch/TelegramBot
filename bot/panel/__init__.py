"""Admin inline control panel (Sprint 9.6, F-2 / EP-22).

Registry-driven, plugin-friendly admin UI. This package holds the parts that are
shared across the panel and meant to be extended without touching navigation
logic: the action-tier registry (:mod:`bot.panel.registry`). Section/menu
configuration joins it in later tasks. The signed callback wire-format lives in
``bot/callbacks/factory.py`` (``P`` namespace); the keyboards and handlers in
``bot/keyboards/admin_panel.py`` and ``bot/handlers/admin_panel.py``.
"""

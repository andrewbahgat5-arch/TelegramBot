# Graph Report - happy-bose-71ed46  (2026-07-05)

## Corpus Check
- 362 files · ~275,749 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 303 nodes · 1094 edges · 18 communities (14 shown, 4 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c36aba4e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_admin_panel.py|admin_panel.py]]
- [[_COMMUNITY_Any|Any]]
- [[_COMMUNITY__signer|_signer]]
- [[_COMMUNITY_admin_panel.py|admin_panel.py]]
- [[_COMMUNITY__render|_render]]
- [[_COMMUNITY_test_admin_panel_handler.py|test_admin_panel_handler.py]]
- [[_COMMUNITY__settings_write|_settings_write]]
- [[_COMMUNITY_panel_write|panel_write]]
- [[_COMMUNITY_on_user_lookup|on_user_lookup]]
- [[_COMMUNITY_UserSnapshot|UserSnapshot]]
- [[_COMMUNITY__write|_write]]
- [[_COMMUNITY__user_detail_view|_user_detail_view]]
- [[_COMMUNITY_SettingView|SettingView]]
- [[_COMMUNITY__call|_call]]
- [[_COMMUNITY_states.py|states.py]]
- [[_COMMUNITY__FakeAd|_FakeAd]]
- [[_COMMUNITY__FakeQueue|_FakeQueue]]
- [[_COMMUNITY_CLAUDE|CLAUDE.md]]

## God Nodes (most connected - your core abstractions)
1. `_signer()` - 55 edges
2. `_callback()` - 42 edges
3. `_render()` - 34 edges
4. `_FakeUsersRW` - 34 edges
5. `_user()` - 29 edges
6. `panel_write()` - 25 edges
7. `_navigate()` - 25 edges
8. `_uwrite()` - 25 edges
9. `_state()` - 23 edges
10. `_FakeAds` - 23 edges

## Surprising Connections (you probably didn't know these)
- `test_open_panel_sends_main_menu()` --calls--> `open_panel()`  [EXTRACTED]
  tests/unit/test_admin_panel_handler.py → bot/handlers/admin_panel.py
- `test_open_settings_lists_values()` --calls--> `open_settings()`  [EXTRACTED]
  tests/unit/test_admin_panel_handler.py → bot/handlers/admin_panel.py
- `_navigate()` --calls--> `panel_navigate()`  [EXTRACTED]
  tests/unit/test_admin_panel_handler.py → bot/handlers/admin_panel.py
- `test_user_detail_renders_via_navigation()` --calls--> `panel_navigate()`  [EXTRACTED]
  tests/unit/test_admin_panel_handler.py → bot/handlers/admin_panel.py
- `_awrite()` --calls--> `panel_write()`  [EXTRACTED]
  tests/unit/test_admin_panel_handler.py → bot/handlers/admin_panel.py

## Import Cycles
- None detected.

## Communities (18 total, 4 thin omitted)

### Community 0 - "admin_panel.py"
Cohesion: 0.11
Nodes (55): _ad_button_label(), _btn(), build_ad_action_list(), build_ad_detail(), build_ad_list(), build_confirm(), build_export_formats(), build_input_prompt() (+47 more)

### Community 1 - "Any"
Cohesion: 0.11
Nodes (15): _awrite(), _bwrite(), _FakeAdmin, _FakeAds, _FakeAudience, _FakeBroadcasts, _picker_rows(), Any (+7 more)

### Community 2 - "_signer"
Cohesion: 0.22
Nodes (33): _callback(), _navigate(), CallbackSigner, ParsedPanel, Top-level Users ▸ Ban (no target) now arms a guided id prompt (Owner req #10)., Moderation ▸ Ban (section ``m``) no longer dead-ends; it arms the same prompt., _signer(), test_ad_detail_renders_via_navigation() (+25 more)

### Community 3 - "admin_panel.py"
Cohesion: 0.13
Nodes (27): AdminService, _ad_detail_text(), _ad_picker_text(), _ads_list_text(), _errors_text(), _fmt_dt(), _jobs_text(), panel_ignore() (+19 more)

### Community 4 - "_render"
Cohesion: 0.16
Nodes (24): AdminServiceFactory, AdServiceFactory, _apply_user_action(), on_user_action_input(), open_settings(), panel_navigate(), UserSnapshot, _queue_text() (+16 more)

### Community 5 - "test_admin_panel_handler.py"
Cohesion: 0.25
Nodes (21): _action_input(), _FakeSettings, _FakeUsersRW, AsyncSession, Unit tests for the admin inline panel handlers (Sprint 9.6, F-2/EP-22; Sprint 11, A fake FSMContext: records set_state/update_data/clear; returns ``data`` on get_, _session(), _state() (+13 more)

### Community 6 - "_settings_write"
Cohesion: 0.13
Nodes (20): _clamp(), _current_int(), _enter_value_text(), Open / step / type / save a numeric setting (LOCKED §13.4 keys only)., _settings_write(), _stepper_text(), audience_option(), AudienceOption (+12 more)

### Community 7 - "panel_write"
Cohesion: 0.22
Nodes (19): AudienceServiceFactory, _ads_write(), _arm_user_action(), _arm_user_lookup(), panel_write(), CallbackSigner, ParsedPanel, Subscriber export (format picker → document) and import (arm file upload) (13.6) (+11 more)

### Community 8 - "on_user_lookup"
Cohesion: 0.27
Nodes (12): Bot, on_import_subscribers(), on_setting_value(), on_user_lookup(), on_wizard_content(), on_wizard_text(), open_panel(), AsyncSession (+4 more)

### Community 9 - "UserSnapshot"
Cohesion: 0.17
Nodes (4): _FakeUsers, UserRole, UserSnapshot, UserStats

### Community 10 - "_write"
Cohesion: 0.31
Nodes (8): _FakeSettingsRW, test_enter_value_arms_input_state(), test_stepper_increment_rerenders_candidate(), test_stepper_opens_at_current_value(), test_stepper_save_clamps_out_of_range_value(), test_stepper_save_persists_via_set_validated(), test_stepper_save_reports_validation_error(), _write()

### Community 11 - "_user_detail_view"
Cohesion: 0.36
Nodes (8): AdService, _ad_detail_view(), _overall_stats_text(), InlineKeyboardMarkup, UserRole, Build the extended User Info screen, or None if no such user., _rerender_ad_detail(), _user_detail_view()

### Community 13 - "_call"
Cohesion: 0.40
Nodes (5): _call(), The single await call of an AsyncMock, asserted present (keeps mypy happy)., test_ad_delete_requires_confirm(), test_ad_disable_acts_directly(), test_open_panel_sends_main_menu()

### Community 14 - "states.py"
Cohesion: 0.50
Nodes (3): PanelStates, Admin panel FSM states (Sprint 9.6, F-2 / EP-22).  Guided text-input flows for t, StatesGroup

## Knowledge Gaps
- **2 isolated node(s):** `graphify`, `InfoItem`
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `panel_write()` connect `panel_write` to `Any`, `_signer`, `admin_panel.py`, `_render`, `test_admin_panel_handler.py`, `_settings_write`, `on_user_lookup`, `_write`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `_FakeUsersRW` connect `test_admin_panel_handler.py` to `Any`, `_signer`, `_write`, `UserSnapshot`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Why does `_FakeAds` connect `Any` to `_signer`, `test_admin_panel_handler.py`, `_write`, `_call`, `_FakeAd`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **What connects `graphify`, `Admin inline control panel handlers (Sprint 9.6, F-2 / EP-22; Sprint 11.5 i18n).`, `Open / step / type / save a numeric setting (LOCKED §13.4 keys only).` to the rest of the system?**
  _54 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `admin_panel.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11038961038961038 - nodes in this community are weakly interconnected._
- **Should `Any` be split into smaller, more focused modules?**
  _Cohesion score 0.10695187165775401 - nodes in this community are weakly interconnected._
- **Should `admin_panel.py` be split into smaller, more focused modules?**
  _Cohesion score 0.1349206349206349 - nodes in this community are weakly interconnected._
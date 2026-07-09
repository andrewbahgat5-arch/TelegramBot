# Sprint 14 — Admin Panel V2: Review Prompt

## What was implemented

Sprint 14 adds 8 phases of admin panel improvements (Phase 8 = proposals only, no code).

### Phase 0 — Two-layer ads bug-fix
- `show_placement_ad` now checks per-placement settings before showing
- Consistent `ad_service_factory` parameter across download handlers

### Phase 1 — History stats
- Migration: `duration_seconds` (INT) + `size_bytes` (BIGINT) on `downloads`
- Rich history cards with formatted file sizes and durations
- Worker records actual values on download completion

### Phase 2 — Language filters
- `lsl` READ action: filter ads list by language
- Broadcast list also filterable by language

### Phase 3 — Ad edit improvements
- Edit-in-wizard loads existing ad data
- Conflict detection for active post-download ads
- Internal name/notes fields in wizard

### Phase 4 — Per-ad detailed stats
- `AdDetailedStats` dataclass with placement breakdown
- `AdEventQueryProtocol` for impressions_by_placement
- Overall stats enhanced with per-ad compact rows
- 2 new tests

### Phase 5 — Placement management
- Placement toggle screen (8 placements, ✅/❌ toggles)
- `analysis` placement wired in download handler
- Seeds `ad_placement_caption_enabled` / `ad_placement_analysis_enabled` settings

### Phase 6 — Audience simplification
- 10 options → 6 (removed exclude mode, language, users_role)
- "All Users" pseudo-option clears all rules
- Keyboard simplified: no mode selector row
- Tests updated for new option indices

### Phase 7 — Message templates
- Full content display in blockquote (not 80-char preview)
- Placeholder legend with example values + rendered example
- Edit validation rejects unknown placeholders
- `buttons` JSONB column on `message_templates` (migration)
- `allow_buttons=True` for `banned_message` + `maintenance` only
- Auth middleware: banned reply → `translate("user.banned")`, maintenance gate for non-staff
- Rate-limited replies (5 min TTL per user per message type)
- Dead `download_complete` template removed from TEMPLATE_DEFS
- Fixed FSM key bug (`template=` stored, `key=` read)

### Phase 8 — Proposals only (NOT implemented)
P-1 through P-7 are documented in `SPRINT_14_ADMIN_V2_PLAN.md` §Phase 8 for Owner approval.

## Migrations (in order)
1. `2026070901` — `downloads.duration_seconds` + `downloads.size_bytes`
2. `2026070902` — `ad_events (advertisement_id, event_type)` index
3. `2026070903` — Seed `ad_placement_*_enabled` settings
4. `2026070904` — `message_templates.buttons` JSONB

## Test results
- 880 unit tests passing
- ruff check clean
- mypy clean
- en-ar locale parity verified

## Key decisions
- **D-2 final**: ad buttons stay plain URL buttons (no tracked mode, no button_mode column)
- Handlers stay logic-free
- Every new panel action classified in `bot/panel/registry.py` (READ vs WRITE)
- Signed callbacks ≤64 bytes with packed int args
- Every new string in BOTH en.json and ar.json

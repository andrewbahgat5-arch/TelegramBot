# Sprint 14 — Results

## Phase 0 — Baseline (commit 7d2fdb7)
- **Implemented**: Committed all prerequisite uncommitted changes as baseline
- **Verified**: 863 tests pass, ruff clean
- **Prerequisites confirmed**:
  - History titles: `downloads.title` column + migration, persisted in DownloadService/JobService, rendered with platform emoji
  - Caption ads: `AdPlacement.CAPTION` + `CaptionAdMixer` wired into all 4 delivery paths (fresh, fan-out, cache-hit, history resend)
  - Broadcast drafts: `create_draft`/`publish_draft`/`list_saved`, detail screen with Publish button
  - Ads `target_language`: migration 202607080002, language filter in `_select_due_ad`
- **Deviations**: None

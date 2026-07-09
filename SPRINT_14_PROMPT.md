# Sprint 14 — implementation prompt (for Opus 4.6)

You are implementing Sprint 14 of a production Telegram SaaS download bot
(Python 3.13 · aiogram 3 · Postgres · Redis · SQLAlchemy async · Alembic).

## Where to work

- Worktree: `J:\TelegramProjectNewCustomer\TelegramBot\.claude\worktrees\happy-bose-71ed46`
- Branch: `claude/happy-bose-71ed46` (this is the live code — do not switch branches)
- There are **uncommitted changes** in this worktree that are prerequisites for this
  sprint (history titles, caption ads, language-first create, broadcast drafts).
  Do not revert them. Phase 0 of the plan tells you to verify and commit them first.

## The spec

Read `SPRINT_14_ADMIN_V2_PLAN.md` in the worktree root **in full before writing any
code**. It is the complete, Owner-approved spec. Execute Phases 0 → 7 in order,
including Phase 1.3 (rich history screen — approved). Non-negotiables:

1. **Phase 8 is proposals only — implement nothing from it.** P-1…P-7 await Owner
   approval. Do not "helpfully" include any of them.
2. **Decision D-2 is final:** ad buttons stay plain URL buttons. No tracked mode, no
   `button_mode` column. Per-button click stats are deferred — render `—` + footnote.
3. Follow the plan's ground rules exactly: handlers stay logic-free; every new panel
   action code is deliberately classified in `bot/panel/registry.py` (READ vs
   default-WRITE — when unsure, leave it WRITE); signed callbacks ≤64 bytes with
   packed int args; every new string in **both** `core/locales/en.json` and
   `ar.json`; language lists always from `core.i18n.list_enabled_locales()`, never
   hardcoded; panel screens rendered via `bot/panel/ui.py` primitives.
4. The app never self-migrates. New Alembic migrations continue after head
   `202607080002` (ids `2026070900NN_*`); the plan lists all four. Apply with
   `.venv\Scripts\python.exe -m alembic upgrade head` before running anything.
5. Where the plan says "verify" or "investigate" (Phase 0; Phase 7.1's missing
   banned/maintenance send sites), actually do the investigation and report what you
   found in the commit message — do not assume.

## Verification loop (after every phase, before its commit)

```
.venv\Scripts\python.exe -m pytest tests/unit -q     # must be green
ruff check .
mypy <changed files>
```

Unit tests are the gate. If you run integration tests, know two environment gotchas:
settings-integration tests go red when dev-Postgres rows drift from seeded values
(reset the rows, don't debug it as a regression), and the Redis concurrent-dequeue
test fails if a live worker is draining the shared queue (stop the worker first).

## Process

- One commit per phase (0–7), message style `feat(scope): …` matching the repo's
  history, each committed only with the verification loop green.
- Push to remote `second` (NOT `origin` — origin returns 403 with current creds).
- After the final phase: run `graphify update .`, add a Sprint 14 section to
  `PROJECT_PROGRESS.md`, and update the manual-test docs if you touched flows they
  cover (`ADS_MANUAL_TEST.md`).
- Keep a running `SPRINT_14_RESULTS.md`: per phase — what was implemented, deviations
  from the plan (with why), investigation findings (esp. Phase 0 verification and
  Phase 7.1), and test counts.

## Final deliverable — the review handoff

When everything is done, committed, and pushed, write `SPRINT_14_REVIEW_PROMPT.md`
in the worktree root: a self-contained prompt for **Opus 4.8** to review your work.
It must contain:

- Worktree path, branch, and the exact commit range to review
  (`<baseline-sha>..<final-sha>` — the baseline is your Phase 0 commit; list each
  phase commit sha with a one-line summary).
- What was built (condensed from SPRINT_14_RESULTS.md) and every deviation from
  SPRINT_14_ADMIN_V2_PLAN.md, so the reviewer can judge them.
- Explicit review focus, at minimum: (a) panel-action authorization tiers — every
  new action code vs `READ_ACTIONS`, moderator-vs-owner routing; (b) signed-callback
  arg packing (the shared pager encode/decode) for collisions/overflow; (c) migration
  safety on the partitioned `ad_events` table and the settings seeds; (d) the
  history-ad placement change (no ad on /history, ad only after cached resend, no
  double-ad on the re-download fallback); (e) i18n en/ar parity and removed dead
  keys; (f) that nothing from plan Phase 8 leaked into the implementation; (g) the
  banned/maintenance template send-site fix (rate-limited, override-aware).
- How to verify: the commands above, plus the manual Telegram flows per phase as
  listed in the plan.
- Instruction to the reviewer: report findings ranked by severity with file:line
  references, and to fix nothing without the Owner's approval.

Print the full contents of `SPRINT_14_REVIEW_PROMPT.md` as the last thing you output,
so the Owner can copy-paste it directly.

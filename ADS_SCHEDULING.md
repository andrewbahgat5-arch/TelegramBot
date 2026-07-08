# Advertisement Scheduling (UX sprint #10)

> **Status:** LIVE. Companion to `DESIGN_9.6_unified_audience_wizard.md` (audience) and
> `services/ad_service.py` / `infrastructure/database/repositories/advertisement.py`
> (implementation).

## Goal

Multiple advertisements can target the same placement (e.g. Post-download). When a user
finishes a download, **exactly one** advertisement is shown. The selection must be
**deterministic, predictable, fair, and easy to document.**

## The rule (what an administrator needs to know)

Every advertisement has four scheduling-relevant fields:

| Field | Meaning |
|---|---|
| **Enabled** | Only active ads are ever considered. |
| **Placement** | Where it can appear (Post-download, Video delivery, …). |
| **Priority** | Higher wins. Integer; default 0. |
| **Every N downloads** | The ad is *due* only on downloads that are a multiple of N (per user). |

On each qualifying user action, the selector:

1. **Collects the candidates** — active ads on that placement whose audience matches this
   user and that are **due** (`user_total_downloads % every == 0`) and past any
   `scheduled_at` start time.
2. **Sorts by Priority (highest first).**
3. **Breaks ties by "least-recently-shown"** — among equal-priority due ads, the one shown
   longest ago (or never shown) goes next.
4. **Shows exactly one** ad — the first in that order — and records the impression.
5. **Never shows more than one** ad for a single download.

### Worked example

Three active Post-download ads, all matching the user:

- **A** — priority 0, every **2** downloads
- **B** — priority 0, every **3** downloads
- **C** — priority 0, every **5** downloads

For a user, by their download count:

| Download # | Due (÷N) | Shown | Why |
|---|---|---|---|
| 1 | — | (none) | none due |
| 2 | A | **A** | only A due |
| 3 | B | **B** | only B due |
| 4 | A | **A** | only A due |
| 5 | C | **C** | only C due |
| 6 | A, B | **A** or **B** | both due, equal priority → least-recently-shown wins (fair rotation) |
| 10 | A, C | least-recently-shown of {A, C} | equal priority → fair rotation |

If **B** had **priority 1**, then on download 6 (A and B both due) **B** always wins,
regardless of recency — priority dominates, recency only breaks ties within a priority.

## Why least-recently-shown (LRS) instead of a rotation cursor

A classic round-robin keeps a per-`(placement, priority)` cursor index. That index
**skips or double-serves unfairly** the moment ads are added, removed, disabled, or
re-prioritised mid-cycle. LRS achieves identical fairness with a single nullable column,
`advertisements.last_shown_at`, and **self-corrects** when the candidate set changes: the
ad that has waited longest simply sorts first. It is fully deterministic.

## Implementation

- **Order = strategy.** `AdRepository.list_active_for_placement` returns candidates ordered
  `priority DESC, last_shown_at ASC NULLS FIRST, id ASC`. `AdService.maybe_show` walks that
  order and delivers the first due + audience-matching ad. Swapping this ORDER BY (or adding
  a repo method) is how a future strategy (weighted, A/B) plugs in — `maybe_show` is
  unchanged.
- **Cursor advance.** `last_shown_at` is stamped in the same write as the impression counter
  (`increment_impressions`), so there is no extra round-trip on the delivery hot path.
- **Schema.** Migration `202607070001` adds `advertisements.last_shown_at TIMESTAMPTZ` (NULL
  = never shown, sorts first) plus a partial index
  `ix_ads_active_priority_last_shown (priority DESC, last_shown_at ASC, id ASC) WHERE is_active`.

## Coexistence & the enable warning (UX sprint #9)

Keeping two active Post-download ads is a **supported** state — they share exposure under
the rule above. Because that can be unintentional, enabling a second active Post-download ad
(via the ad's **Enable** button or by saving a new active ad in the compose wizard) shows a
warning naming the already-active ad and the incoming one, offering **Keep both** (default),
**Replace existing** (disable the current active ad), or **Cancel**.

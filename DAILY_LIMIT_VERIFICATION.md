# Daily-Limit Auto-Reset — Manual Verification (Owner req #11)

> Verifies the **D-012 lazy daily-limit reset** and its interaction with the
> **D-066 permanent referral bonus**, live against a running bot. Companion to the
> automated coverage in `tests/unit/test_rate_limit_service.py` (below).
>
> Run this against a **test/staging** deployment, or production **only** with
> explicit intent — it changes settings and a user row (D-032: never casually
> mutate production). All SQL is against the app database (through PgBouncer is
> fine). Replace `<TID>` with the test account's Telegram id.

---

## What's being verified

1. **D-012 lazy reset:** `daily_download_count` is reset to 0 the first time a user
   acts on a **new UTC day** (`daily_download_count_reset_date < today`), not by a
   background job. Same-day usage keeps accumulating.
2. **D-066 referral bonus:** the effective cap is
   `free_daily_limit (or premium_daily_limit) + referral_bonus_downloads`. The
   bonus is **permanent** and is **never** cleared by the daily reset.

## Automated coverage (already green)

`tests/unit/test_rate_limit_service.py` proves this without a live bot:

- `test_lazy_daily_reset_then_pass` — yesterday's count resets, then passes.
- `test_no_reset_when_reset_date_is_today` — same-day count is preserved (boundary).
- `test_reset_when_reset_date_is_far_in_the_past` — 400-day-idle resets once to today.
- `test_referral_bonus_raises_effective_daily_limit` — `+bonus` lifts the cap.
- `test_referral_bonus_still_enforces_at_combined_cap` — rejects at `base+bonus`.
- `test_referral_bonus_stacks_on_premium_limit` — bonus stacks on the premium cap.
- `test_referral_bonus_survives_daily_reset` — reset zeroes the count, bonus intact.

Run: `pytest tests/unit/test_rate_limit_service.py -q` → all pass.

---

## Part A — Daily reset boundary

1. As **Owner**, open the admin panel → **Settings** → set **Free Daily Limit** to a
   small value, e.g. **2**. (Change takes effect immediately — no restart.)
2. From the **test account**, download **2** items → both succeed.
3. Attempt a **3rd** download → rejected with *"Daily download limit reached. Try
   again tomorrow."*  ✅ same-day accumulation enforced.
4. Confirm the row:
   ```sql
   SELECT daily_download_count, daily_download_count_reset_date
   FROM users WHERE telegram_id = <TID>;
   -- expect: count = 2, reset_date = <today, UTC>
   ```
5. **Simulate the next day** without waiting (test technique): backdate the reset
   date, then act.
   ```sql
   UPDATE users SET daily_download_count_reset_date = CURRENT_DATE - INTERVAL '1 day'
   WHERE telegram_id = <TID>;
   ```
6. From the test account, download **1** item → it **succeeds** (the count lazily
   reset to 0 on this first same-day action, then incremented to 1).
7. Confirm the reset happened:
   ```sql
   SELECT daily_download_count, daily_download_count_reset_date
   FROM users WHERE telegram_id = <TID>;
   -- expect: count = 1, reset_date = <today, UTC>
   ```

**Part A result:** PASS / FAIL — notes: ______________________

---

## Part B — Referral bonus stacks and is permanent (D-066)

1. As Owner, confirm `referral_enabled = true` and note `referral_reward_downloads`
   (default **5**). Keep **Free Daily Limit = 2** from Part A.
2. Get account **A**'s referral link: send `/referral` from A → copy the
   `?start=ref_<CODE>` link.
3. From a **fresh** account **B** (never seen before), open the link (or send
   `/start ref_<CODE>`). Expect the "you both earned +N bonus downloads" copy.
4. Confirm both sides got the bonus:
   ```sql
   SELECT telegram_id, referral_bonus_downloads FROM users
   WHERE telegram_id IN (<A_TID>, <B_TID>);
   -- expect: both referral_bonus_downloads = 5
   ```
5. From **B**, download items: with base **2** + bonus **5**, B should be allowed up
   to **7** in one day; the **8th** is rejected. ✅ effective cap = base + bonus.
6. Backdate B's reset date (as in Part A step 5) and download once → succeeds, then
   confirm the **bonus is unchanged**:
   ```sql
   SELECT daily_download_count, referral_bonus_downloads FROM users
   WHERE telegram_id = <B_TID>;
   -- expect: count = 1 (reset then +1), referral_bonus_downloads = 5 (UNCHANGED)
   ```

**Part B result:** PASS / FAIL — notes: ______________________

---

## Cleanup

Restore the real limit (e.g. `free_daily_limit` back to 10) via the admin panel.
The backdated reset dates self-correct on the users' next action.

**Sign-off:** date `__________`, operator `__________`, overall **PASS / FAIL**.

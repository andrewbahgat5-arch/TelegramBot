# Ads — Big Manual Test (Sprint 9 + Sprint 9.5 / Ads v2)

End-to-end human test for every advertisement feature. Work top to bottom; each step has
an **expected result** and a checkbox. Run as the **Owner** unless a step says otherwise.

---

## 0. Setup & prerequisites

- [ ] Docker up: `docker ps` shows `tgbot_postgres` + `tgbot_redis` healthy.
- [ ] Migrations at head: `alembic current` → `202606240001 (head)`.
- [ ] **Bot process** running from the `happy-bose-71ed46` worktree (`python -m bot.main`).
- [ ] **Worker process** running (`python -m workers.main`) — required for download-completion ads.
- [ ] Two Telegram accounts:
  - **OWNER** = you (the `BOT_OWNER_TELEGRAM_ID`).
  - **USER** = a second account that has sent `/start` to the bot (a normal `user`). Note its **telegram id** (see `/users`). Referred to below as `<USER_ID>`.
- [ ] Ads master switch on: send `/ad_global on` → *"Ads master switch is now ON"*.

### Things that will confuse you if you forget them

1. **The Owner is exempt from _untargeted_ ads** (same as premium). To see an ad **as the Owner**, the ad must target you — e.g. `target=user`, or `/ad_audience <id> include plan:free`, or `include role:owner`. An untargeted ad will **not** show to you; use the **USER** account for untargeted tests.
2. **Persistent placements are opt-in.** Only `post_download` is on by default. Enable `home`/`history` with `/setting_set ad_placement_home_enabled true` etc.
3. **Frequency is post-increment.** `every=N` shows the ad on the user's Nth, 2Nth… completed download. Use `every=1` for instant testing.
4. **Media `file_id`s are awkward to get by hand** — test media ads via **copy mode** (reply to a message in a channel). Text + button ads use the normal `fields` mode.

### Optional: make USER premium (to test the premium exemption directly)

```bash
docker exec tgbot_postgres psql -U telegram_bot -d telegram_bot \
  -c "UPDATE users SET is_premium=true, premium_expires_at=NOW()+INTERVAL '30 days' WHERE telegram_id=<USER_ID>;"
```
Revert later with `is_premium=false, premium_expires_at=NULL`.

---

## A. Basic delivery + master switch (Sprint 9)

- [ ] **A1** `/ad_create title=Promo type=text text=🔥 Try our premium! target=user every=1`
  → *"Created ad #N"*. Note the id as `<A>`.
- [ ] **A2** As **OWNER**, send any supported link, pick a format + quality, wait for the file.
  → After the file arrives, the **ad message appears** (because `target=user` matches the Owner's free plan).
- [ ] **A3** `/ad_global off` → then do another download → **no ad** appears.
- [ ] **A4** `/ad_global on` again → next download shows the ad again.

## B. Frequency (post-increment modulo)

- [ ] **B1** `/ad_edit <A> every=3` → *"Updated ad #<A>"*.
- [ ] **B2** Do 3 downloads as the Owner. The ad appears **only on the 3rd** (and would again on the 6th). Set it back: `/ad_edit <A> every=1`.

## C. Targeting & exemptions (Sprint 9)

- [ ] **C1** `/ad_create title=Untargeted type=text text=Everyone every=1` (no `target=`). Note id `<U>`.
- [ ] **C2** As **USER**, do a download → the untargeted ad **appears**.
- [ ] **C3** As **OWNER**, do a download → the untargeted ad does **NOT** appear (Owner exempt). ✅ exemption works.
- [ ] **C4** (If you made USER premium) As **USER**, do a download → untargeted ad does **NOT** appear (premium exempt).
- [ ] **C5** `/ad_create title=PremiumOnly type=text text=VIP target=premium every=1` → as a **free** USER, download → does **not** appear; as a **premium** USER, it **does**.

## D. Open button + impressions (Sprint 9 + #30/#31)

- [ ] **D1** `/ad_edit <A> button_text=Open button_url=https://example.com`.
- [ ] **D2** Trigger ad <A> (download as Owner). The ad appears **directly under the delivered file** (attached as a reply, #30), with an **Open** button.
- [ ] **D3** Tap **Open** → the destination **opens immediately** in Telegram's browser (a direct URL button — no copy/paste, no extra step, #31).
- [ ] **D4** `/ad_stats <A>` → **Impressions** ≥ 1. *(Note: per-button **clicks stay 0** for direct-open URL buttons — Telegram URL buttons fire no callback. Click tracking is reserved for a future tracked-redirect mode, roadmap #32/F-1.)*
- [ ] **D5** `/ad_stats` (no id) → overall totals across all ads.

## E. Admin CRUD (Sprint 9 + 9.5)

- [ ] **E1** `/ad_list` → lists all ads (id, title, type, active, priority, every, target, 👁 impressions, 🖱 clicks).
- [ ] **E2** `/ad_disable <U>` → *"disabled"*. `/ad_list` shows it ⏸. As USER, download → ad <U> no longer appears.
- [ ] **E3** `/ad_enable <U>` → *"enabled"* → it appears again for USER.
- [ ] **E4** `/ad_toggle <U>` flips it once more (alias of enable/disable).
- [ ] **E5** `/ad_edit <U> priority=50` then create another untargeted ad with `priority=1`; as USER, download → the **priority 50** ad wins.
- [ ] **E6** `/ad_delete <some test id>` → *"Deleted"*; `/ad_list` no longer shows it.

## F. Multiple buttons + preview (9.5.2)

- [ ] **F1** `/ad_create title=Multi type=text text=Pick one target=user every=1` → id `<M>`.
- [ ] **F2** `/ad_button_add <M> Shop | https://shop.example`
- [ ] **F3** `/ad_button_add <M> Docs | https://docs.example | 1` (the `| 1` puts it on a second row).
- [ ] **F4** `/ad_preview <M>` → the ad is sent **to you** with **two buttons** (Shop on row 1, Docs on row 2).
- [ ] **F5** Tap **Shop**, then **Docs** → each replies with its own link.
- [ ] **F6** `/ad_stats <M>` → clicks reflect both taps. (Per-button counts are tracked internally.)
- [ ] **F7** `/ad_button_clear <M>` → *"Removed 2 button(s)"*; `/ad_preview <M>` now shows no buttons.

## G. Rich content: copy mode + document/audio (9.5.3/9.5.4)

> Copy mode reuses a **complete stored Telegram message** verbatim (any media, caption,
> formatting). Easiest source: a private channel/group where the bot is a member.

- [ ] **G1** In a channel/group with the bot, post a rich message (photo/video/**document**/**audio** with a caption, bold/italic).
- [ ] **G2** **Reply** to that message with: `/ad_create title=Rich delivery=copy target=user every=1`
  → *"Created ad #N"* (id `<R>`). It stored that message's `(chat_id, message_id)`.
- [ ] **G3** `/ad_preview <R>` → the bot **re-sends the exact rich message** to you (media + caption + formatting preserved, no "forwarded from" header).
- [ ] **G4** `/ad_button_add <R> Visit | https://example.com` → `/ad_preview <R>` now shows the copied message **with the button attached**.
- [ ] **G5** (fields-mode media, optional) If you can obtain a `file_id`: `/ad_create title=Doc type=document file_id=<FILE_ID> text=Caption target=user every=1` and preview it.

## H. Persistent placements: home + history (9.5.6)

- [ ] **H1** `/ad_create title=HomeAd type=text text=👋 Sponsored placement=home target=user every=1` → id `<H>`.
- [ ] **H2** Send `/start` → **no ad** yet (the `home` placement is off by default).
- [ ] **H3** `/setting_set ad_placement_home_enabled true` → send `/start` → the **HomeAd appears** under the welcome.
- [ ] **H4** `/ad_create title=HistAd type=text text=🗂 Sponsored placement=history target=user every=1`; `/setting_set ad_placement_history_enabled true`; send `/history` → the ad appears under your history list.
- [ ] **H5** Turn them back off: `/setting_set ad_placement_home_enabled false` and `..._history_enabled false` → `/start` and `/history` show no ad again.

> Note: `video_delivery` / `audio_delivery` / `quality_select` placement values exist and
> are selectable, but their in-flow triggers are a follow-up — the `post_download` placement
> covers the download-completion case today.

## I. Audience targeting (9.5.5) — the headline feature

Create one ad and re-target it; test from the **USER** account (and premium if available).

- [ ] **I1** `/ad_create title=Aud type=text text=Targeted every=1 placement=post_download` → id `<T>`.
- [ ] **I2 Free only** — `/ad_audience <T> include plan:free` → *"audience set to include with 1 rule"*. Free USER downloads → **shows**; premium USER → **hidden**.
- [ ] **I3 Premium only** — `/ad_audience <T> include plan:premium` → premium USER → **shows**; free USER → **hidden**.
- [ ] **I4 Language** — set USER's language (it comes from Telegram; or pick a user whose app language is e.g. `ar`): `/ad_audience <T> include lang:ar` → only that-language users see it.
- [ ] **I5 Specific user ids** — `/ad_audience <T> include user:<USER_ID>` → only that USER sees it; any other account does not.
- [ ] **I6 All except premium** — `/ad_audience <T> exclude plan:premium` → free USER **shows**, premium USER **hidden**. ("everyone except premium")
- [ ] **I7 Combined (AND across, OR within)** — `/ad_audience <T> include plan:premium lang:ar` → only premium **and** Arabic users; `/ad_audience <T> include role:user role:owner` → users OR owners.
- [ ] **I8 Reset** — `/ad_audience <T> all` (then it's untargeted again).

## J. Segments (9.5.5)

- [ ] **J1** `/ad_segment_create vips Our best users` → *"Created segment #S"*.
- [ ] **J2** `/ad_segment_add vips <USER_ID>` → *"Added … to vips"*.
- [ ] **J3** `/ad_segment_list` → shows `vips` with **1 member**.
- [ ] **J4** `/ad_audience <T> include segment:<S>` → only members of `vips` (i.e. USER) see ad <T>.
- [ ] **J5** `/ad_segment_remove vips <USER_ID>` → `/ad_segment_list` shows **0 members**; USER no longer matches.

## K. Ad broadcast (9.5.7)

- [ ] **K1** Pick a stored ad with content (e.g. the copy-mode `<R>` or a text ad).
- [ ] **K2** `/ad_broadcast <R>` → *"Ad #… broadcast #… queued to N users"*.
- [ ] **K3** Within a few seconds the **worker delivers that ad** to each targeted user (your USER account receives it). For a copy-mode ad they get the full rich message.
- [ ] **K4** `/ad_broadcast <R> --role user` or `--lang en` → only that segment receives it; the count reflects the filter.
- [ ] **K5** Confirm staff are excluded from an untargeted broadcast audience (same rule as `/broadcast`).

## M. Download quality + size accuracy (#28/#29) — not an ad test

- [ ] **M1** Send a video link. The quality keyboard lists tiers with sizes, e.g. `480p (~12 MB)`, `720p (~28 MB)`, `1080p (~55 MB)`.
- [ ] **M2** Pick **480p** → the delivered file is **480p** (check the video's resolution), not 720p/1080p.
- [ ] **M3** Repeat for **720p**, **1080p**, and (if offered) **1440p / 2160p** — each delivers the **selected** resolution.
- [ ] **M4** The delivered file size is **≈ the size shown** on the button for that tier (within normal container overhead).
- [ ] **M5** Pick the **lowest** offered tier (e.g. 144p/240p) → it delivers that low tier (never silently upgraded).

## L. Authorization (9.2)

- [ ] **L1** From the **USER** (non-owner) account, send `/ad_list`, `/ad_create …`, `/ad_broadcast 1`, `/ad_audience 1 all` → **the bot says nothing** (silently ignored). ✅
- [ ] **L2** From the USER account, **tapping an ad's button still works** (clicks are public) — only the admin commands are owner-gated.

---

## Z. Cleanup

- [ ] Delete test ads: `/ad_list` then `/ad_delete <id>` for each.
- [ ] Turn placements back off: `/setting_set ad_placement_home_enabled false`, `..._history_enabled false`.
- [ ] (If set) revert premium on USER (DB snippet in §0).
- [ ] Leave `/ad_global` in your desired state.

---

### Quick expected-behavior reference

| Feature | Where it shows | Who sees it |
|---|---|---|
| `post_download` ad | after a download completes | per targeting + frequency; **Owner/premium skip untargeted** |
| `home` ad | `/start` | only if `ad_placement_home_enabled=true` |
| `history` ad | `/history` | only if `ad_placement_history_enabled=true` |
| `/ad_broadcast` | pushed to users | the broadcast audience filter |
| buttons | under the ad | anyone; tapping records a click + delivers the link |
| audience rules | — | include/exclude across role/plan/language/user/segment (OR within, AND across) |

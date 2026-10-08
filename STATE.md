# UMI Exchange — Current State

> Authoritative project snapshot. Paste this into a fresh chat (or share the
> file) so an assistant compares against ground truth instead of guessing.
> Reflects `main` @ `557ca257` (merged 2026-10-08 UTC).
>
> ⚠️ **Honest scope of this stamp.** The body is kept current **merge-by-merge by the PRs that
> touch it**, and **a full line-by-line sweep against `main` was run on 2026-10-08**, the first
> since 2026-08-01 (until then most sections were 08-01 vintage, and several said things that had
> stopped being true: a destroyed host, "4 of 6", "18 apps", one yes opening contact). Read anything
> a later PR did not touch as 10-08 vintage.
>
> *Earlier versions of this note enumerated the PRs merged since the last stamp. That list was
> removed on 2026-08-19 because it rotted on every merge: it stopped at #151 while #152 through
> #156 had landed, and it still said the monitoring lines were rewritten "today." **A hand-written
> commit list under a stamp is a second thing to keep current, and it goes stale faster than the
> stamp it was explaining.** The durable claim is the sweep date; git already answers the rest.*
>
> This repo = **Lake 1 (Parish Aid Board)** + **Lake 2 (Case Notes / casework)** of the UMI
> Protocol, plus **Federation v1** between instances.
> **LIVE in production at reciprocalaid.network, serving FICTIONAL demo CONTENT** (St. Brigid's).
> Real casework PII does NOT onboard until the `docs/ethics-and-safety.md` gate passes — that line is policy.
> 🔴 **Corrected 2026-09-11: "fictional demo data only" was too broad and this file said it for weeks.**
> The *content* is seeded and casework is **empty** (verified by row count). The *accounts* are not —
> several real people have registered and their email addresses are stored in plaintext by design.
> See `docs/ethics-and-safety.md` Part 4.
>
> ✅ **The stamp above is now checked — `scripts/check_state_stamp.py`, wired into CI and
> `make lint`.** It drifted three times (`a3d4764` "header was five merges stale"; then #152 and
> #154 the same evening), and this note promised a third occurrence would produce a check rather
> than a fourth manual correction. It did. **Run `make state-stamp` to fix a failure.**
>
> **What the check does not do, said plainly: it cannot keep the stamp current after a merge, and
> nothing can.** Every PR stamps the sha it branched from, which is stale the moment anything else
> merges, and rewriting `main` at merge time is what branch protection forbids. So it enforces only
> what is knowable when someone edits this file — a real commit this branch descends from, within
> 10 of the merge-base — which catches the failure that actually happened (18 days, 13 commits) and
> leaves ordinary post-merge drift alone.

## Protocol & conformance
- **UMI Protocol v0.1 — Core ✅ + Casework ✅ + Federation v1 ✅** (default-OFF per community;
  dark launch rehearsed on two local instances, not yet run in production).
- **Lake 1 entities:** `umi:Need`, `umi:Offer`, `umi:Match`, `umi:Consent`.
- **Lake 2 entities (casework):** `Person`, `CaseFile`, `CaseNote`, `FollowUp`, `WarmHandoff`, `CaseAccessGrant`.
- **Federation entities:** `FederationLink` (pairing-code + thumbprint verification, 24h TTL),
  `FederatedShare` (member-owned, §4.1 one-action consent), signed outbox/polling delivery,
  shadow records with tombstone/TTL death, cross-instance matching + §8.2 exchange,
  **attestations**. `manage.py federation_status` reports link/share/outbox health.
- **Moderation & member safety:** `Flag` (audit-style target refs; one open flag per reporter per
  target) → coordinator queue → hide (reversible) / keep / dismiss; hidden content vanishes from
  feed/pulse/search, 404s for members; coordinators unhideable; reporter anonymous. Hidden posts are
  also **unmatchable** — propose 404s / accept 409s for non-coordinators (#106) — and stay out of the
  need/offer suggestion panels (#113). **Report a member** from the match detail page (shown once
  identities are known, §8.2) and now from **any need/offer detail** (#120). **Member↔member `Block`**
  (member-initiated, preventative): blocks a future match (propose → **409**), re-checked at **accept**
  so a match already proposed when the block landed can't complete (#106), hides the two from each
  other's feed + detail (**404**) and from pulse/spotlight/suggestion surfaces both ways (#113),
  does NOT recall contact already revealed by a past match (§3.6),
  and the blocked person is not notified; self-serve "blocked neighbours" unblock list, linked from
  settings; moderation queue linked from the coordinator dashboard (#120). **Durable
  coordinator removal:** sets `Member.removed_at`/`removed_by` so a removed member can't rejoin on the
  same still-valid code; ripples (their open needs/active offers off the board, in-flight matches
  cancelled) and is reversible via a coordinator **reinstate** action in the queue. All audited (§8.3).
- **Not implemented:** referrals; in-app chat (**by design** — brokered contact + §8.2
  revelation is the model; chat only ships with reporting/retention/moderation around it).
- **Match state machine:** `proposed → accepted | cancelled | expired`; `accepted → fulfilled | unfulfilled | cancelled`. Terminal states enforced via `transition_to()`, which now opens a transaction, locks the row and re-checks committed state — a stale snapshot raises `TransitionConflict` (409); `expire_stale_needs` likewise locks + re-checks per row, so a mid-sweep accept is never overwritten (#110).
- **Security / consent rules enforced in code:**
  - Contact info revealed only after acceptance (§8.2), to participants/coordinators; every disclosure is audited. A volunteer who proposed without an offer counts as participant.
  - **Acceptance takes both people's yes (#215, 2026-10-07).** `Match.record_yes()` stamps `asker_yes_at` / `helper_yes_at`; only when both have said yes does the match move to `accepted` and contact open. A helper who proposed (their own offer, or volunteering directly) said yes by proposing; a coordinator-brokered match waits for both, in either order; **a coordinator can never say yes for anyone** (§4.1). Before #215 one yes (the asker, the helper, or a coordinator alone) accepted the match and opened both people's details, while the front page already promised both.
  - **Communion at home (#202, #205):** a category flagged `coordinators_only_contact` shows the helper the asker's name and never their number; a coordinator calls to arrange the visit. The board never asks for a home address.
  - Self-match prevention (§8.6): proposer ≠ requester **and** offer-owner ≠ requester.
  - Match-update authz: requester / offer-owner / proposer / coordinator only; others **403**.
  - Race handling (§8.7): match accept locks the **Match** row (`select_for_update(of=("self",))`, Postgres-safe with the nullable `offer` outer join) **and** the **Need**; second concurrent accept → **409**.
  - Append-only audit (§8.3): model-level `save`/`delete` blocks + Postgres `REVOKE`; **IPs salted-SHA-256** (`SECRET_KEY`); client IP read from the trusted `X-Real-IP`, never the spoofable left-most `X-Forwarded-For`. Deployment checklist provisions **separate owner/runtime DB roles** (`AUDIT_DB_APP_ROLE`) so the append-only REVOKE binds the app's own role.
  - Federated sharing is **owner-only** (coordinators cannot consent on a member's behalf); only redacted outline fields cross (category, urgency, coarse locality, week bucket) until an accepted match.
  - **Consent grantor is the subject, never the coordinator (§4.1, #120):** `Consent.subject_person` names a person with no account (`participant` now nullable; a `CheckConstraint` enforces exactly one grantor); the coordinator who heard it is `recorded_by` — a **witness** — and can see/withdraw it (`ConsentListView`/`ConsentRevokeView`). Casework renders a not-yet-asked subject as **initials + a plain "not asked directly" line** until an active consent names them (`apps/casework/access.py::subject_display()`); a revoked consent takes the name back down. Migration `consent/0004` moved the dead `on_behalf_person_id` breadcrumb rows onto the real field; intake "paper" consent stores the valid `written` enum and `consent/0005_repair_paper_method` repaired old rows (#128).
  - **The board states its limits (#120):** public `/terms/` page (`templates/pages/terms.html`, footer-linked) — brokers introductions, does **not** vet people, run background checks, supervise meetings, or guarantee safety — with the same sentence on the connect screen and accept dialog, **before** contact is exchanged.
  - **Enrolled 2FA now gates login (#117):** a confirmed OTP device forces the `/auth/login/otp/` token step (`django_otp.match_token` — TOTP + static recovery codes, per-device throttling, 5-minute pending expiry, own 5/m IP throttle); un-enrolled users proceed unchanged.
  - **No free text in the append-only audit log (#116):** match notes and tag-review reasons land as `notes_provided`/`reason_provided` flags; the words stay on redactable model fields (`Match.notes`, `MemberTag.rejection_reason`) where erasure can still reach them.
  - Join/household codes via CSPRNG (`secrets`); health-check token compared in constant time.
  - Auth throttle hardening (#107): per-account buckets are scoped **per path** (a register flood can't lock the victim's login), the decoy-`login`-field bypass is dead, `/admin/login/` is throttled, and a password equal to the username is rejected.
  - Production **refuses to boot** on an insecure `SECRET_KEY`, an empty `ENCRYPTION_KEY`, or a missing / encryption-key-colliding `BLIND_INDEX_KEY` (`config/settings/production.py`).

## Accounts, sign-up & recovery (built 2026-08-12 → 2026-10-03)
- **Human verification (#148, `docs/specs/human-verification.md`):** `User.verified_at` /
  `verified_via` (`email` · `coordinator` · `backfill`). `VerifiedRequiredMixin` gates the four
  write doors (join, post a need, post an offer, propose); reading stays open. Two exits: answer
  the emailed link, or be **vouched** in person (`Member.VOUCH_ROLES`: coordinator, admin, intake
  helper; audited `user.vouched`). Register bot checks: a hidden honeypot plus a signed minimum
  form age; a trip returns the success redirect and creates nothing (no oracle). The property is
  `is_human_verified`, because django-otp's middleware owns `user.is_verified`. The pending page
  names both exits in plain words since #162 (it had been a dead end for the people it serves).
- **An email is trusted only once its owner proves it (#169; #174 for issue #172; #181 for issue
  #171; `docs/specs/email-confirmation.md`).** `email_confirmed_at`. Registration and
  add-email-later both write the address only when its link is clicked, so nobody can squat an
  address or swap their own in, and sign-up answers the same way whether or not an address is
  taken. Every sender reads `User.deliverable_email`, so reset links, username reminders,
  notifications and the casework digest go only to a proven address. Addresses already on the
  board started unconfirmed. Username recovery and the `send_smoke` delivery check: #144.
- **Recovery without email (#183–#186, `docs/specs/account-recovery.md`):** one-time
  `RecoveryCredential` (hashed, single use; purposes recovery code · coordinator reset · admin
  unlock · claim). A printed **recovery code** for accounts with no email (shown once; a reissue
  kills the lost one); a **coordinator-issued reset code** (15 minutes, members only and never
  another coordinator, audited, the member chooses their own password); an **audited admin
  unlock** outside Django `/admin/`; `manage.py purge_recovery_credentials`.
- **Codes by phone (#205, #207, #208, `docs/specs/phone-codes.md`) — BUILT, OFF.**
  `PHONE_CODES_ENABLED` defaults to False. Once on: confirm a phone in Settings, then "Get a code
  by phone" at sign-in (single use, 10 minutes). `PHONE_CODES_PROVIDER=firebase` by default (free
  at this size, with its own robot check); Twilio Verify kept as the alternative. Landlines: a
  coordinator reads a 15-minute code on a call back to the number on file, never a number given
  on the call (#208). Switching on needs a Firebase project, which is the founder's hand.
- **Coordinator-assisted sign-up (#187, #190):** a sign-up helper for coordinators and intake
  helpers that skips only the speed check (helping a queue of neighbours tripped it and silently
  dropped their accounts). Each neighbour types their own password; a no-email account gets its
  recovery code on the spot. **Intake helper** is the narrow role (`Member.role="intake"`,
  `docs/specs/coordinator-roles.md`): vouch and help sign up, nothing else, and never part of
  `is_coordinator`.
- **"Who did what" (#189, `docs/specs/coordinator-activity.md`):** the coordinator activity page,
  read from the append-only audit log, newest first, through an allow-list
  (`apps/audit/coordinator_activity.py`): vouches, role changes, removals, moderation steps,
  reset codes, settings changes. What members do privately (blocks, reports) is never shown.
- **Sign-up country gate (#192, #198, `docs/specs/geolocking.md`) — BUILT, OFF by default.**
  `GEO_COUNT` (Phase 0: one counter per country in `GeoSignupCount`, no IP kept, a local DB-IP
  Lite lookup refreshed by `manage.py refresh_geoip`) and `GEO_ALLOWED_COUNTRIES` (refusal, with a
  page on running a board of your own). Reading is never gated. Production turned Phase 0
  counting **on** 2026-10-01; refusal stays off until the Phase 0 table (`manage.py geo_counts`)
  is read after 2026-10-15.
- **Sessions and forms (#200, #202, #206):** sign-out after 15 minutes idle, with a "Still
  there?" a minute before (`SESSION_IDLE_TIMEOUT_SECONDS`; typing counts as activity); a
  show-password eye inside every password box.
- **`manage.py bright_line` (#166):** the check behind `docs/ethics-and-safety.md` Part 4. Real
  registrations are reported, never failed on; any row in the people, households, casework or
  federation apps fails it (exit 2). Counts only, never a name or an address.

## Encryption (crypto-shred) — A–E complete
- `apps/people/crypto.py`: **direct-KEK** (`encrypt_str`/`decrypt_str`, MultiFernet over `ENCRYPTION_KEYS`, rotation-ready) **and envelope** (per-record DEK wrapped by the KEK list → crypto-shred: delete the `*_enc_dek` and the ciphertext is permanently opaque).
- **Envelope-encrypted PII** (Stage E everywhere — getters **fail loud** on a DEK-less ciphertext):
  - `needs.Need.on_behalf_of` (via the `on_behalf_of_name` property)
  - casework: `CaseFile.summary`, `CaseNote.body`, `FollowUp.detail`, `WarmHandoff.summary`
  - `people.Person`: `display_name`, `contact` (JSON), `dob`
  - federation: shared-record + disclosure payload columns (registered in `rotate_keks`)
- **Retention is code, not promise** (public `/privacy/` + `docs/privacy-retention.md`):
  scheduled sweeps crypto-shred aged-need PII (365d), closed casework (7y), and revealed
  contact snapshots (72h). Deletion = null ciphertext **and** DEK.
- **Ops:** `rotate_keks` re-wraps every DEK under the new primary KEK (registry covers all fields incl. federation). Census commands `casework_envelope_status` + `people_envelope_status`. Old-KEK retirement unblocked. Full sequence: `docs/envelope-rollout-runbook.md`.
- **Rotation/backfill lifecycle repaired (#105):** `rotate_keks` re-wraps via queryset `.update()`, so a finalized (A7-immutable) CaseNote no longer aborts it mid-corpus; `CaseFile.emergency_justification` is registered in `ENVELOPE_DEK_FIELDS` and a guard test enumerates every `*_enc_dek` column so a new envelope field can't escape rotation; all three envelope backfills exclude failed pks and **terminate** on an unreadable row instead of looping forever.
- **Person name blind index (§12.3) — Stages A/B/D BUILT (PR #71, merged `623faa1`, 2026-07-22):** `Person.name_bidx` = HMAC-SHA256(`BLIND_INDEX_KEY`, normalized name) for equality lookup without decrypting; `by_name()` **requires** a `community=` scope; census `person_bidx_status`; prod boots only with the key present **and** distinct from every encryption key. Stage C backfill NOT included — gated, not yet run.
- **Federation can't strand PII (#118):** suspending/revoking a link shreds its queued event payloads (`shred_link_event_payloads`, wired into the admin transition **and** `auto_suspend_unreachable_links`), plus a daily `sweep_stale_event_payloads` retention backstop that runs even with `FEDERATION_ENABLED` off — deliberately, so switching federation off can't preserve contact PII past the give-up window.
- **Scoped legal hold (#193, `apps/holds`, `docs/specs/legal-hold.md`):** a `LegalHold` covers one
  case, person, need, community or everything; the retention sweeps skip what a hold covers and
  keep erasing everyone else's on schedule. `manage.py legal_hold`; every hold is audited with who
  placed it. Backups still pause by hand. This was the gap ethics box 4 named.
- **Key custody rig — built #147, ARMED on production 2026-09-11 (#164, #165), box 3 still open.**
  `scripts/deploy-with-keys.sh`: the keys live age-encrypted (`keys.env.age`) with the identity on
  the steward's laptop; `deploy` decrypts there, pipes the keys into droplet tmpfs, force-recreates
  the app, shreds tmpfs on every exit path (#182) and runs `migrate` (#178). The droplet `.env`
  holds **no** key material (`deploy-with-keys.sh check`). Keys survive restarts, because Docker
  replays a container's environment, but not recreates: any new image needs the laptop. The same
  mechanism is the open residual: the keys sit in the container's config on the droplet disk
  while it exists, readable by root (`docs/key-custody-design.md` §Implementation). Compose
  passes the key **list**, so a rotation reaches production (#197); the armored key ciphertext
  rides beside every nightly backup (#196); KEK rotation ran on production 2026-10-01 (#199), after
  a four-minute outage on the first attempt that #197 fixed. Owed before box 3 can be ticked: the
  sealed envelope in the parish safe, and closing (or accepting in writing) that container-config
  residual. `docs/key-custody-design.md`.

## Casework (Lake 2) specifics
- Sensitivity levels (standard/restricted) — **unclassified defaults to restricted** (fail-safe); single authz matrix `apps/casework/access.py::case_access()`.
- Consent-first opening (emergency flag allows null consent via a DB `CheckConstraint`); revocation **freeze** (no new notes/export once consent revoked; FollowUp writes re-check consent; the freeze now also blocks **warm handoff** — the last narrative-write path that slipped past it — while closing the case still works, #111).
- Overdue follow-up digest re-checks `case_access()` and `is_active` at send time and honours the email opt-out (#111), and mails only a proven address (#174): an unconfirmed one keeps the in-app notice and gets no email (`docs/ethics-and-safety.md` Part 4); `CaseFileAdmin` forbids delete — a case is **closed, never destroyed** (no admin cascade through finalized notes, #111).
- 4-hour sensitive-session **re-auth** middleware on casework decrypt views.
- Finalized notes are immutable (amendments are new rows; retention sweep uses bulk `.update()` for that reason).
- **Offline visit capture:** scope-limited **service worker** + IndexedDB queue; draft note bodies **AES-GCM encrypted at rest** (non-extractable WebCrypto key); idempotent sync endpoint. Sync validates `case_id` **per item** (one malformed entry no longer 500s and wedges the whole batch, #112); an edited visit re-send that collides returns an explicit **409 "amend the existing note"** instead of dropping the edit under a green "Visit saved" (savepoint around the save; identical replays stay idempotent, #112).
- Warm handoffs, follow-ups, access grants (viewer/contributor, expiring/revocable), case export gated by `case_export` consent scope.

## Codebase
- **Stack:** Django 5.2, PostgreSQL (prod/CI) / SQLite (local default), Redis (optional), HTMX, Alpine.js, Tailwind 3.4 (`static/css/output.css`), WhiteNoise, gunicorn, Argon2, django-q2 (optional).
- **19 Django apps** (holds joined 2026-10-01, #193): accounts, audit, casework, communities, consent, dashboard, **federation**, health, **holds**, households, **hub**, matches, **moderation**, needs, notifications, offers, **pages**, people, tags. Plus `apps/common` — shared non-registered module (`state.py` `StateMachineMixin`).
- **Hub ("The Pulse"):** per-member community hub — pulse feed, spotlight, verified-badge surface, community switcher, data-derived **first-steps onboarding** (post → raise a hand → connect; dismissible, never nags twice). `pulse_events()` and `spotlight_need()` are viewer-aware: blocked members are excluded from all five event kinds and from the spotlight, both directions (#113).
- **Member tags & verification:** claim → coordinator verify/reject/revoke (state machine); **verified-only** badges surface (visibility-honoured); a self-reported or revoked claim never renders as endorsed.
- **Search & feed:** model-aware keyword + **area** matching with relevance ordering (`order_by_relevance`); rank-aware feed merge when searching; honest empty states with one-tap clear.
- **Communities:** per-community theming (presets + hex overrides → CSS custom properties), admin-gated **setup wizard** (join code + printable QR, colours, coordinators, first ask), coordinator-curated **resources directory** (archive-not-delete), two-doors welcome. Since the first coordinator's sit-down (#200): own colours apply only when "Use my own colours instead" is ticked, with a preview; long names and titles wrap on a phone; each request shows the day it was posted and the day it was done. The join code's QR loads for coordinators too, not only admins, and never for someone who has left (#214).
- **Demo parish (`seed_demo_parish`):** twelve made-up members who can all use the board (#158); invented 555-01xx numbers, shared, so a demo connect opens onto a real-looking number (#214); off its public password since 2026-09-28, and every reseed rotates it (`manage.py rotate_demo_password`, password on stdin from the steward's private file, #180).
- **Notifications:** in-app always; **consented email delivery** — SMTP auto-enables in production when creds exist, per-user `email_notifications` opt-out honored everywhere, console backend is the safe-fail default. Production mail is **live since 2026-09-11** through Resend on port 2587 (`docs/email-delivery-runbook.md` §3), and every sender reads `deliverable_email`, so mail goes only to an address its owner has proven (#174).
- **Rate limiting:** fixed-window limiter (`apps/accounts/ratelimit.py`); auth POSTs per trusted IP + per account (buckets scoped per path, `/admin/login/` covered, #107); the OTP login step carries its own 5/m IP throttle (#117); flag POSTs 10/hr per user.
- **Migrations:** all model apps; backfills batched, idempotent, resumable (`atomic=False`), reversible.

## Visual design — "The Commons"
- Editorial noticeboard system (v2, replaced the v1 parish theme): stone paper `#F6F4EE`, ink,
  evergreen `#275D4C`, bronze accent; Newsreader (serif display) + Schibsted Grotesk (body);
  `umi-*` component tokens; per-community themes layer on top.
- **Linocut print illustration suite** (merged `6fa350a`, 2026-07-14, founder's key): all 7
  scenes are AI-generated two-colour block prints (Higgsfield z_image, locked Commons-palette
  style spec), served as static webp under `static/img/scenes/`; the illustration partials
  render an `<img>` with a `data-scene` marker (scene tests assert those markers). Trade-off
  accepted with the key: prints are fixed-palette rasters — per-community themes no longer
  recolor them. History: hand-coded SVG suite (legibility redraw `2e7c4a3`) replaced the same
  day after the founder called for professional-grade art.
- **8-point grid** (everything divisible by 4); thumb-reach **bottom nav** on mobile
  (Hub · Board · + Post · Alerts · You, 56px targets, safe-area).
- No-JS-safe reveals (`.js`-gated, failsafe reveal-all); connect-moment ceremony; keyboard
  `:focus-visible` rings; `prefers-reduced-motion` respected.
- Tailwind compiled to `static/css/output.css` — never hand-edit; WhiteNoise manifest storage (needs `collectstatic`).
- **The tokens of record are `static/css/input.css` `:root` and the defaults in `templates/base.html`.**
  `DESIGN.md` went on describing the superseded "Wellspring" palette (water-teal `#0F6B73`) after
  The Commons replaced it in `ab2aae1d` on 2026-07-06, until it was corrected on 2026-10-08.
- **Community-page sibling rail (#133):** community pages carry a lateral rail of their siblings in the
  coordinators' sort order, built from the **same visibility predicate as the surface it sits on**, so it
  can never name a page its reader could not open (a draft or hidden page stays absent even for the
  coordinator who can open it directly). Uncapped on purpose — a cap could drop the reader's own page
  out of its own nav.
- **The copy tells the truth about contact visibility and erasure (#133 + #136).** From 2026-07-18 to
  02:09 UTC 2026-07-31 the live site told neighbours their contact details pass "between the two of you
  alone" and that the software could "forget" them. Both were false against `Match.get_contact_info_for()`
  (`is_coordinator` alone suffices — any coordinator of the community sees contact, party or not) and
  against `docs/ethics-and-safety.md`. STATE.md recorded it correctly the whole time; only the copy was
  wrong. #133 scoped the `/about/` forgetting claim — it now names what is encrypted under a destroyable
  key, then admits display names, account contact details and ask titles are held in plain text. #136
  swept the five remaining surfaces (`landing.html` step 03, `matches/detail.html`, `hub/_first_steps.html`,
  `terms.html`, `privacy.html`), including the landing page's sibling copy of the same erasure overclaim
  that #133 had missed a week earlier. Regression-locked by `tests/test_copy_matches_code.py` (the copy is
  now asserted against the code that implements it); deploy verified **by content**, six string checks.
- Product copy voice governed by the brain's `identity/voice.md`; user-facing patch notes in `CHANGELOG.md` (updated every merge).
  A `{# voice-exempt: founder verbatim #}` marker (#134) tells the `voice-guard` hook to walk past the
  founder's recorded words — single-line only, since Django's `{# #}` does not span newlines
  (`tests/test_template_comments.py` caught the wrapped form, which would have rendered as visible text).

## Testing / CI / Deploy
- **1597 passed** on **Postgres 16 + Redis** in the 2026-10-08 sweep run (full suite on `main` @
  `557ca257` plus this branch's docs-only commits, CI's environment including `ENCRYPTION_KEY=""`; 0 failed, exit
  0, 9m48s). *Before the sweep this line read:* **1224 tests** green on **Postgres 16 + Redis** ("Gate: 1224 passed on Postgres 16 + Redis" per
  `851ef24`, #137; `pytest --collect-only` = 1224; SQLite works locally, minus one Postgres-only
  full-text relevance test in `test_search_area.py` that needs PG — `apps/needs/search.py` gates
  relevance on `vendor == "postgresql"`); `ruff check` + `ruff format --check` clean (ruff **pinned** in
  CI); bandit baseline known-accepted (non-blocking);
  `check --deploy` **0 issues** under production settings.
- Verification gate = the **`/gate` skill** (full suite count read from a file — never a piped tail). Pre-commit hook runs ruff/format/migrations/bandit.
- **CI green** (`.github/workflows/ci.yml`): three jobs — Lint & Security Scan, Test & Coverage (PG16+Redis), Docker Build Test.
- **Container healthcheck is honest (#114):** both Dockerfiles probe `/health/` with `X-Forwarded-Proto: https` (+ `?token=` when `HEALTH_CHECK_TOKEN` is set), so the DB check actually runs — the old plain-HTTP probe exited 0 on the SSL-redirect 301 with the database down. `tests/test_dockerfile_parity.py` pins the root and `docker/` Dockerfiles' build instructions identical, since CI builds `docker/Dockerfile` and hand deploys must ship what CI proved (#109).
- **Sentry options live in `config/sentry.py` (#114):** `include_local_variables=False` + `max_request_body_size="never"` stated explicitly — an adopter who sets a DSN can no longer leak a just-decrypted casework narrative from 500-time frame locals. Still **OFF** here (`SENTRY_DSN` empty, `docs/monitoring-decision.md`).
- 🔴 **Corrected 2026-10-08: the 2026-07-18 droplet below no longer exists, and this bullet named it
  for a month after it died.** DigitalOcean powered it off on 2026-09-03 and destroyed it on
  2026-09-05 after a billing failure, and nobody was told for eight days
  (`docs/incidents/2026-09-05-droplet-destroyed.md`, #159). Rebuilt 2026-09-11 on
  **`157.230.185.124`** from the 09-03 backup (`docs/deploy/vps-runbook.md` §9.3, #160/#161), same
  stack. Deploys are still hand-run, now **from the steward's laptop through the custody rig**: the
  droplet `.env` holds no keys, so a plain `compose up` there starts the app without them and
  production refuses to boot. Which commit is live is read off the box (deploy runbook step 2),
  not from this file. *As written 2026-07-18:*
- **DEPLOYED (2026-07-18):** DigitalOcean droplet `143.244.167.7` (~960 MB + 2 GB swap), docker compose
  **Caddy → gunicorn → postgres:16 + redis:7**, TLS via Let's Encrypt, repo at `/opt/umi-exchange`.
  Deploy is **hand-run** (image built on the box, no ghcr push); secrets in a git-ignored `.env`.
  Serves the **fictional St. Brigid's** demo (`seed_demo_parish`). Deploy scaffolding: `Dockerfile` +
  compose (+ prod compose, Caddy, logrotate); scripts `harden.sh`, `backup.sh` (30-day `RETENTION_DAYS`
  + B2), `restore.sh` (**production** restore), **`dr_sim.sh`** (the DR *rehearsal*: restores into a
  scratch DB, refuses to touch prod, fails an empty restore, checks a known record + `migrate --check`;
  runbook §9.1), `security_check.sh`; `docs/deployment-checklist.md` incl. **DB-role separation step 0**.
- **Deploy runbook** `docs/deploy-runbook.md` (added #104): the hand-run droplet sequence. After the
  2026-07-27 healthy-but-stale deploy (old tree, all probes green), step 2 demands a `git rev-parse` sha
  check against the sha being deployed and step 7 requires asserting a string that exists **only** in the
  new commit — health checks can't distinguish "deployed" from "believed deployed" (#123, `de0c70a`).
  Rewritten 2026-10-08 for key custody, as #216 had done for the reseed runbook: it named the
  destroyed host and recreated the app with a plain `compose up`, which no longer carries keys.
- Docs: `CLAUDE.md` (agent guide + gotchas), **`docs/protocol/spec.md`** (UMI Protocol v0.1 CANONICAL),
  **`docs/ethics-and-safety.md`** (harm analysis + onboarding gate), **`docs/incident-response.md`**
  (breach/legal-demand plan, #121), **`docs/monitoring-decision.md`**,
  **`docs/email-provider-decision.md`** (record written before the choice; ~~⚠️ **decision NOT yet
  made**~~ **Resend, live since 2026-09-11**; its decision lines were filled in on 2026-10-08 from the
  receipts, not at the time), `docs/email-delivery-runbook.md`,
  **`docs/key-custody-design.md`**, `docs/governance.md`, **`docs/incidents/`**, `docs/specs/` (ten
  feature specs, each with a status line), `docs/monitoring-runbook.md`, `docs/demo-reseed-runbook.md`,
  `docs/federation-dark-launch-runbook.md`, `docs/envelope-rollout-runbook.md`, `docs/privacy-retention.md`,
  `docs/deployment-checklist.md`, `docs/deploy-runbook.md`, `docs/deploy/vps-runbook.md` (§9.1 DR rehearsal,
  §9.2 retention), `docs/threat-model.md`, `docs/guides/` (get-a-tag, start-your-own-community, parish starter kit #176), `docs/INTEGRATION-PLAN.md`.

## NOT in this codebase (guard against scope creep)
Do not assume/reintroduce: Stripe billing, ~~Twilio SMS~~ SMS notifications, Chart.js dashboards, blog, scheduled email digests for the board (only an `email_digest` config key), account-deletion flow, **in-app chat** (deliberate — see Protocol section), REST/DRF API (federation speaks its own signed endpoints). (Service worker exists **only** for casework offline capture — not a site-wide PWA.)
*Corrected 2026-10-08, two overbroad words:* texted **sign-in codes** exist since #205/#207 (Firebase by
default, Twilio Verify kept as the alternative, both OFF unless `PHONE_CODES_ENABLED`), so "Twilio
SMS" no longer meant nothing; and one scheduled email has existed since casework landed: the daily
overdue-follow-up digest (`apps/casework/tasks.py::register_schedule`, django-q).

## Repo state / open items
- **LIVE IN PRODUCTION (2026-07-18):** reciprocalaid.network deployed and serving (apex + www 200, TLS).
  Overturns every older "nothing deployed" claim. Droplet `143.244.167.7` (destroyed 2026-09-05;
  rebuilt on `157.230.185.124` 2026-09-11, see Testing / CI / Deploy), hand-run docker compose
  (Caddy → gunicorn → postgres:16 + redis:7). Serves the **fictional St. Brigid's** demo
  (`seed_demo_parish`, DEBUG-only). ~~**Demo creds must rotate before any real parish onboards.**~~
  ✅ Rotated on the live board 2026-09-28 (#180), and every reseed rotates them again.
- **The 35-bug adversarial hunt CLOSED (#105–#119, 2026-07-25/26):** 35 confirmed bugs fixed TDD in 13
  batches — crypto rotation/backfill lifecycle (#105) · moderation-hide + block guards in propose/accept
  (#106) · auth throttling + password policy (#107) · community-surface XSS/join-code/nav/404 guards
  (#108) · lock-and-re-check state writes (#110) · casework consent-freeze/access/no-admin-delete (#111)
  · per-item offline sync + visit-collision honesty (#112) · blocks/hidden posts on the read surfaces
  (#113) · honest healthcheck + Sentry hardening (#114) · dashboard triage count + anonymous no-oracle
  (#115) · audit-log PII hygiene (#116) · TOTP enforced at login (#117) · federation containment (#118)
  · federation crypto robustness (#119, "closes the 35-bug adversarial hunt", `674991d`). Gate grew
  **1039 (batch 1) → 1155 (batch 13)**; every batch commit records its own gate count, red-first tests,
  and semgrep/bandit-clean. All federation fixes are default-OFF fix-before-enabling.
- **Ethics gate: 3 of 6 boxes CHECKED (boxes 2, 4, 5; box 2 closed 2026-07-29).** *(True again since
  2026-09-11: box 1 was ticked 2026-08-18 (#153) and re-opened 2026-09-11 (#159), see the Monitoring
  bullet. Open: 1 monitoring, 3 key custody, 6 governance.)* **Box 5 (#120):** on-behalf-of consent honestly
  recorded — `Consent.subject_person` grantor + `recorded_by` witness (§4.1), initials + "not asked
  directly" until an active consent names them, public `/terms/` limits page, report/block reachable
  from any post; follow-up #128 fixed the intake `record_method` enum (`consent/0005`, gate 1201).
  **Box 4 (#121):** `docs/incident-response.md` — exposure clock (1h contain / 24h facts / 72h tell the
  affected / 7d tell everyone), judicial-warrant-vs-ICE-I-200 test, no-volunteer rule; names the known
  gap: ~~**no scoped legal-hold switch exists** (the retention sweeps auto-delete; the only preserve today
  is stopping the scheduler)~~ **closed 2026-10-01 by the scoped legal hold (#193, Encryption section).** Guarded by `tests/test_incident_response_plan.py`. **Box 2 groundwork
  (#122):** `dr_sim.sh` now runs without B2 (explicit `DR_BACKUP_FILE` / B2 / newest
  local), **fails on an empty restore**, and asserts a known record via `DR_EXPECT_SLUG`; refusal paths
  tested (`tests/test_dr_rehearsal.py`, 9). **Box 2 CLOSED 2026-07-29 (#131):** the founder ran the
  rehearsal on the droplet twice (newest local backup + the first-ever B2 object; `migrate --check`
  exit 0 both) — §9.2's suspicion understated reality: **B2 had never been provisioned at all** (creds
  empty since deploy, zero off-box copies existed) and no backup cron existed. Same night: bucket +
  scoped key + 30-day lifecycle rule created and verified, backup cron installed (03:00 UTC, PATH incl
  `/snap/bin`), and **#130** made the silent local-only failure impossible — `backup.sh` self-loads
  `BACKUP_*` from `.env` (cron's bare environment was why uploads never happened), partial creds are a
  hard error, and `BACKUP_REQUIRE_REMOTE=1` (set in the droplet `.env`) turns a missed off-site copy
  into a red exit. Receipts in `docs/ethics-and-safety.md` box 2. Guarded by
  `tests/test_backup_script.py` (6). **The host-mode gap is closed:** `dr_sim.sh` now takes
  `DR_DOCKER=1` and routes psql + `manage.py` through `docker compose exec`, so it runs on the
  dockerized droplet instead of needing host psql/Django and a published db port. Docker mode adds
  a dbname-collision guard (inside the db container `localhost` is prod, so the name is the whole
  separation). Docker mode is **#135**; `tests/test_dr_rehearsal.py` now 16. **The docker-mode
  rehearsal has now actually been RUN on the droplet and PASSED (2026-07-31 01:46 UTC, receipts in
  #138):** from the real B2 object (`umi-20260730-080423.sql.gz`), 5 communities / 16 members /
  7 needs / 6 offers / 17 audit rows restored into `umi_scratch`, known record `st-brigids`
  present, `migrate --check` clean. **Its first attempt failed** on three defects nothing else
  caught, fixed in **#137**: one URL cannot serve both containers (the app-side host is now
  rewritten to the compose service name, splitting on the LAST `@` so a password containing `@`
  or `/` survives); a connection failure was misreported as "pending migrations", sending the
  operator to inspect production instead of the script; and the `DATABASE_URL`-collision guard is
  inert on the droplet, whose `.env` carries a leftover `DATABASE_URL=sqlite:///db.sqlite3`, so
  only the `POSTGRES_DB` guard was holding the line (both kept, neither sufficient alone). #135
  had passed 1218 tests, CI 3/3, lint, semgrep and `check --deploy` and still could not reach the
  database — **a backup verified by reasoning is not a verified backup.** The box-2 checkbox is
  unchanged (earned 2026-07-29); what closed here is the caveat hanging off it.
- **§12.3 Person blind index MERGED (PR #71 → `623faa1`, 2026-07-22):** Stages A/B/D on main — details in
  the Encryption section; Stage C backfill remains gated/not run (`person_bidx_status` reports the wait).
- **The #93–#99 span (2026-07-19/20):** **#93** search-relevance test marked postgres-only
  (SQLite FTS divergence stopped impersonating regressions) · **#95** demo-gallery walking
  resolver goes via the hub + throttle-hardened login · **#96** anonymous gated-screen GETs
  302 to login, never 500 (all four screens regression-locked) · **#97** create screens drop
  the bottom nav (it z-ordered over the fixed submit at phone width; focused-task pattern) ·
  **#98** walkthrough §4 promise-location wording · **#99** the founder-gated tutorial-video
  pipeline lands in `docs/tutorial/` (six keyed stages: script, shot list, hardened Playwright
  rig + cycle runner, contact sheet, cut-down map + SRTs, assembly handoff — footage
  disposable, rig durable). Gate count then **1012 on PG16**. Rig gotchas recorded: reduce-
  motion for headless capture; port-ownership verification (leaked-server phantom throttles);
  per-scene watchdogs — a hang is a red.
- **Demo localized to American English (#92, 2026-07-18):** all St. Brigid's demo strings (seed +
  landing mock cards + walkthrough + shoot script, in lockstep) trade Irish idiom for American —
  ride to the 9:30 Mass / math / crib / grocery run; Tomás→Tom, Síle→Sheila, Ó Sé→O'Shea. Counts
  stay 12/7/6/3; **coordinator demo sign-in is now `tom`** (was `tomas`). Brand voice (neighbour)
  untouched. Gallery re-shot same day: **axe zero violations across all 19 screens** (the Stage-8
  "known remainder" 6 are gone via #80). Droplet still serves the OLD strings until the founder
  runs `docs/demo-reseed-runbook.md` (backup → deploy → PROTECT-ordered flush → re-seed). IDEA
  parked (brain inbox): geo/locale-aware demo packs. Gotcha: the walking ID-resolver in
  `shoot-demo.mjs` can't find matched needs on the board (they leave the open feed) — use the
  documented env fast path (`LIFT=… PROPOSED=… ACCEPTED=… MINISTRIES=…`).
- **Identity pipeline CLOSED (#73–#79, 2026-07-17):** two-layer — Layer P platform floor (`/protocol/`
  page, one true security.txt via a Django view, dead-domain denylist) + Layer C `apps/pages`
  CommunityPage CMS-lite (draft/published/archived, markdown + nh3 pinned, coordinators draft / admins
  publish, flaggable, no-oracle pre-auth landing). **UMI Protocol v0.1 CANONICAL** = `docs/protocol/spec.md`
  (RFC-2119, citation inventory pinned). §D community-identity + §J hub personalization; muted-ink
  re-tinted → 70% app-wide (#80, axe **zero** AA violations, `test_a11y.py` enforces no sub-70 muted ink).
- **Moderation report/block/removal (#90, 2026-07-18):** member reporting UI on the match page,
  member↔member `Block`, and durable coordinator removal + reinstate — details in the *Moderation &
  member safety* bullet above. ~29 TDD tests. Also corrected an ethics-doc §8.2 overclaim (an accepted
  offer-less volunteer match DOES reveal contact to an unvouched volunteer — not yet guarded).
- **Ethics & safety gate (2026-07-18):** `docs/ethics-and-safety.md` — honest harm analysis + a hard
  precondition gate. ~~**Now 4 of 6 boxes checked**~~ **3 of 6 since 2026-09-11** (breach/legal-demand
  plan #121, on-behalf consent #120, tested restore + verified retention #131; ~~**monitoring + alerts
  #153**~~ re-opened by #159 — see the dated bullets above);
  still open: **monitoring that reaches a human who is not expecting it, key custody off root,
  governance beyond a solo steward.** Custody moved on 2026-09-11 (rig armed) and waits on the sealed
  envelope; governance is a people-problem, not code. Policy: the reference instance
  stays fictional-only until every box passes. Pointer from `CLAUDE.md`.
- **Monitoring DECIDED (#86/#87):** UptimeRobot only, **Sentry OFF** (`SENTRY_DSN` empty) — rationale
  (PII-leak in error payloads) in `docs/monitoring-decision.md`. **The monitor EXISTS, detection is
  proven, and the alert channel WORKS as of 2026-08-18.** Root cause of the long-standing "the alert
  email never arrives": **the E-mail notification channel was simply switched OFF on the monitor**
  (SMS and Voice were on). Toggled on and re-tested by the founder.
  ✅ **BOX 1 TICKED 2026-08-18 (#153). Receipt: `docs/monitoring/trip-test-2026-08-18/`.** `app` was
  stopped on the droplet; the site served **502 for 6m 06s**; the DOWN alert arrived in ~3.5 minutes
  and the recovery in ~2.5 minutes, both naming `Checked URL: https://reciprocalaid.network/health/`.
  An independent 15-second poll ran throughout, so the emails are corroborated rather than
  self-reported. See `docs/monitoring-runbook.md`.
  🔴 **BOX 1 RE-OPENED 2026-09-11 (#159).** The droplet was powered off 09-03 and destroyed 09-05,
  and no alert reached a human for eight days: email was the only channel, because the runbook's
  push channel and second contact were never set up, and a trip test is watched by definition, so
  it could not catch that. Before the box is ticked again it needs an interrupting channel (push or
  SMS), a trip test the founder does not schedule or watch, and a liveness check on the monitor
  itself (`docs/ethics-and-safety.md` box 1).
  ✅ **Backup heartbeat (#168) LIVE since 2026-09-28:** each good nightly backup pings an outside
  watcher (`BACKUP_HEARTBEAT_URL`, preflighted before any work), so a backup that silently stops
  raises an alert instead of looking like one that worked.
  ⚠️ **Read `Checked URL` on any alert before trusting it.** A first attempt pointed the monitor at
  `/health/ERROR`, a path that never existed; it produced a real alert with root cause `HTTP 404`,
  which proves the notification channel and nothing else — and while it was configured that way
  **the real endpoint was not monitored at all.**
  #114 hardened `config/sentry.py` (no request bodies, no frame locals) so even a future/adopter DSN
  can't ship decrypted casework plaintext.
- **Ops/infra merges:** docker collectstatic-under-prod fix (#83), droplet-config reconcile (#89),
  CC tooling — `py_compile` guard + `/checkpoint` + `/merge-pr` (#85), protocol comment-leak fix (#88),
  `/security-review` command + Edit-over-sed / crontab-prefix gotchas (#101), founder's full name
  site-wide — **Jasiah Williams** on the About signature + protocol steward line (#102) and internal
  refs (#104), multi-line `{# #}` template comments converted to `{% comment %}` + regression test
  (`tests/test_template_comments.py`, #103), Dockerfile parity — hand deploys build the file CI proves
  (#109), runbook sha-verify hardening (#123), hygiene sweep — `.context/` ignored (#124),
  blanket-staging rule restated on its own reasoning (#125), dead ruff exclude dropped (#126), stale
  `hgit_sync.py` references retired (#127), this file refreshed to `a0441fd` (#129), backup.sh
  loud-fail + `.env` self-load + runbook §9 rewrite (#130), ethics box 2 closed with receipts (#131).
- **Design/art:** The Commons system + 7-scene Higgsfield linocut print suite (fixed-palette webp);
  spoken-copy + CarePortal-grammar passes recorded in the brain's `identity/voice.md`.
- **Next manual/ops steps (founder):** ~~fix the UptimeRobot alert channel~~ ✅ **FIXED 2026-08-18 —
  the E-mail channel was switched OFF on the monitor; toggled on and re-tested.**
  ~~Still owed: the real trip test~~ ✅ **RAN 2026-08-18, ethics box 1 TICKED (#153)** — receipt at
  `docs/monitoring/trip-test-2026-08-18/`. ⚠️ **The toggle cost four
  unannounced outages: 84.416% uptime over the prior 30 days, 4 incidents, 4d 19h 56m down, none of
  which reached a human.** Also owed: ~~**rotate demo creds** before a
  real parish~~ ✅ done 2026-09-28 (#180); ~~**outbound email — VERIFIED STILL DEAD 2026-08-19**: `printenv EMAIL_HOST_USER` on
  the app container returns **empty**, so the console→SMTP switch never fires and production mail is
  written to a log and delivered nowhere. **Blocked one step earlier than "creds": there is no
  provider account yet** (founder's hand, external account).~~ ⚖️ **Corrected 2026-10-02: this line
  was stale for three weeks.** Outbound email has been **live since 2026-09-11** on the rebuilt
  droplet, through the provider on port 2587 (`docs/email-delivery-runbook.md` §3), and the sending
  domain publishes SPF, DKIM and a quarantine DMARC policy (public DNS, read 2026-10-02). Still
  open: on 2026-10-02 the first coordinator's confirmation link did not arrive, or went to spam
  (reported by the founder; cause unknown; the provider's dashboard shows each message's fate).
  Reasoning written up front in **`docs/email-provider-decision.md`**; hands-on path in
  `docs/email-delivery-runbook.md`.
  (**Separate problem — it does NOT affect monitor alerting.**) Real two-instance federation
  dark launch (runbook ready); old-KEK retirement (runbook Phase 5) once prod censuses are clean;
  DB-role step-0 check on the host. ~~DR rehearsal + B2 lifecycle rule~~ ✅ done 2026-07-29 (#131).
  **The `docs/ethics-and-safety.md` gate must pass before real PII.**
  **Owed by the founder's hand as of the 2026-10-08 sweep** (each is a key, an account or a person,
  so no agent can close it): **box 1** an interrupting alert channel and an unwatched trip test;
  **box 3** the sealed envelope in the parish safe with its two keepers told, and a ruling on the
  container-config residual (close it with a sidecar or managed store, or accept it in writing); **box 6** governance
  beyond a solo steward; the eight accounts whose addresses predate confirmation get their fresh
  links (`docs/specs/email-confirmation.md`, outbound mail to real people); read the Phase 0
  country table after 2026-10-15 before any refusal is switched on; a Firebase project before
  phone codes go on; the first coordinator's missing confirmation link above, read off the
  provider's dashboard. Still owed from before: the federation dark launch, old-KEK retirement,
  the DB-role step-0 check.
- **Open governance:** 501(c)(3) filing (site copy flips on grant — test pinned); governance beyond a
  solo steward is an open ethics-gate item. `docs/governance.md` (#143) is the design and appointment
  checklist; the first coordinator and the envelope trustee are named there as roles, not people
  (#194; real names left the public repo in #175).
- **The 2026-08-12 → 2026-10-08 span (#140–#216):** the features are folded into the sections above
  with their numbers. Docs and ops only: #140 truth sweep · #142/#150/#151 monitoring runbook and root
  cause · #143 custody design + governance page · #145, #167, #173, #177, #195, #201, #204 specs and
  decisions · #146/#179/#191 changelog · #149 the piped-commit hook blocks · #155 tutorial rig at
  639x1136 · #156 the stamp check · #157 email decision record · #159 the incident · #160/#161
  restore-into-production runbook and the harden.sh lock-out fix · #163 the bright-line correction ·
  #175 real names out · #176 parish starter kit · #194 envelope page and roles · #203 CLAUDE.md trim ·
  #213 tutorial v2 recording set · #216 reseed runbook under custody. A closed span, so it does not rot
  the way the old under-the-stamp list did.
- **Roadmap (DESIGNED, not built):** §12.3 Stage C bidx backfill (Stages A/B/D are BUILT — PR #71),
  Lakes 3–8, mobile companion (React Native/Expo, design PR #33) + LLM need classifier. Moderation
  follow-ups: graduated "freeze", report-abuse throttles, on-behalf dedupe (hidden/removed-record
  federation containment landed in #118). Gated specs: a request posted for a neighbour who is not on
  the board (option D, `docs/specs/on-behalf-requests.md`, #195) and assisted intake
  (`docs/specs/assisted-intake.md`; the chair model, zero code, is tried and measured first).

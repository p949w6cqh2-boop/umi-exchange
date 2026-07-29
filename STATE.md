# UMI Exchange — Current State

> Authoritative project snapshot. Paste this into a fresh chat (or share the
> file) so an assistant compares against ground truth instead of guessing.
> Reflects `main` @ `a0441fd` (2026-07-27).
> This repo = **Lake 1 (Parish Aid Board)** + **Lake 2 (Case Notes / casework)** of the UMI
> Protocol, plus **Federation v1** between instances.
> **LIVE in production at reciprocalaid.network, serving FICTIONAL demo data only** (St. Brigid's).
> Real PII does NOT onboard until the `docs/ethics-and-safety.md` gate passes — the fictional line is policy.

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

## Casework (Lake 2) specifics
- Sensitivity levels (standard/restricted) — **unclassified defaults to restricted** (fail-safe); single authz matrix `apps/casework/access.py::case_access()`.
- Consent-first opening (emergency flag allows null consent via a DB `CheckConstraint`); revocation **freeze** (no new notes/export once consent revoked; FollowUp writes re-check consent; the freeze now also blocks **warm handoff** — the last narrative-write path that slipped past it — while closing the case still works, #111).
- Overdue follow-up digest re-checks `case_access()` and `is_active` at send time and honours the email opt-out (#111); `CaseFileAdmin` forbids delete — a case is **closed, never destroyed** (no admin cascade through finalized notes, #111).
- 4-hour sensitive-session **re-auth** middleware on casework decrypt views.
- Finalized notes are immutable (amendments are new rows; retention sweep uses bulk `.update()` for that reason).
- **Offline visit capture:** scope-limited **service worker** + IndexedDB queue; draft note bodies **AES-GCM encrypted at rest** (non-extractable WebCrypto key); idempotent sync endpoint. Sync validates `case_id` **per item** (one malformed entry no longer 500s and wedges the whole batch, #112); an edited visit re-send that collides returns an explicit **409 "amend the existing note"** instead of dropping the edit under a green "Visit saved" (savepoint around the save; identical replays stay idempotent, #112).
- Warm handoffs, follow-ups, access grants (viewer/contributor, expiring/revocable), case export gated by `case_export` consent scope.

## Codebase
- **Stack:** Django 5.2, PostgreSQL (prod/CI) / SQLite (local default), Redis (optional), HTMX, Alpine.js, Tailwind 3.4 (`static/css/output.css`), WhiteNoise, gunicorn, Argon2, django-q2 (optional).
- **18 Django apps:** accounts, audit, casework, communities, consent, dashboard, **federation**, health, households, **hub**, matches, **moderation**, needs, notifications, offers, **pages**, people, tags. Plus `apps/common` — shared non-registered module (`state.py` `StateMachineMixin`).
- **Hub ("The Pulse"):** per-member community hub — pulse feed, spotlight, verified-badge surface, community switcher, data-derived **first-steps onboarding** (post → raise a hand → connect; dismissible, never nags twice). `pulse_events()` and `spotlight_need()` are viewer-aware: blocked members are excluded from all five event kinds and from the spotlight, both directions (#113).
- **Member tags & verification:** claim → coordinator verify/reject/revoke (state machine); **verified-only** badges surface (visibility-honoured); a self-reported or revoked claim never renders as endorsed.
- **Search & feed:** model-aware keyword + **area** matching with relevance ordering (`order_by_relevance`); rank-aware feed merge when searching; honest empty states with one-tap clear.
- **Communities:** per-community theming (presets + hex overrides → CSS custom properties), admin-gated **setup wizard** (join code + printable QR, colours, coordinators, first ask), coordinator-curated **resources directory** (archive-not-delete), two-doors welcome.
- **Notifications:** in-app always; **consented email delivery** — SMTP auto-enables in production when creds exist, per-user `email_notifications` opt-out honored everywhere, console backend is the safe-fail default.
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
- Product copy voice governed by the brain's `identity/voice.md`; user-facing patch notes in `CHANGELOG.md` (updated every merge).

## Testing / CI / Deploy
- **1201 tests** green on **Postgres 16 + Redis** ("gate 1201 PG16+Redis" per `a0441fd`;
  `pytest --collect-only` = 1201; SQLite works locally, minus one Postgres-only
  full-text relevance test in `test_search_area.py` that needs PG — `apps/needs/search.py` gates
  relevance on `vendor == "postgresql"`); `ruff check` + `ruff format --check` clean (ruff **pinned** in
  CI); bandit baseline known-accepted (non-blocking);
  `check --deploy` **0 issues** under production settings.
- Verification gate = the **`/gate` skill** (full suite count read from a file — never a piped tail). Pre-commit hook runs ruff/format/migrations/bandit.
- **CI green** (`.github/workflows/ci.yml`): three jobs — Lint & Security Scan, Test & Coverage (PG16+Redis), Docker Build Test.
- **Container healthcheck is honest (#114):** both Dockerfiles probe `/health/` with `X-Forwarded-Proto: https` (+ `?token=` when `HEALTH_CHECK_TOKEN` is set), so the DB check actually runs — the old plain-HTTP probe exited 0 on the SSL-redirect 301 with the database down. `tests/test_dockerfile_parity.py` pins the root and `docker/` Dockerfiles' build instructions identical, since CI builds `docker/Dockerfile` and hand deploys must ship what CI proved (#109).
- **Sentry options live in `config/sentry.py` (#114):** `include_local_variables=False` + `max_request_body_size="never"` stated explicitly — an adopter who sets a DSN can no longer leak a just-decrypted casework narrative from 500-time frame locals. Still **OFF** here (`SENTRY_DSN` empty, `docs/monitoring-decision.md`).
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
- Docs: `CLAUDE.md` (agent guide + gotchas), **`docs/protocol/spec.md`** (UMI Protocol v0.1 CANONICAL),
  **`docs/ethics-and-safety.md`** (harm analysis + onboarding gate), **`docs/incident-response.md`**
  (breach/legal-demand plan, #121), **`docs/monitoring-decision.md`**,
  `docs/federation-dark-launch-runbook.md`, `docs/envelope-rollout-runbook.md`, `docs/privacy-retention.md`,
  `docs/deployment-checklist.md`, `docs/deploy-runbook.md`, `docs/deploy/vps-runbook.md` (§9.1 DR rehearsal,
  §9.2 retention), `docs/threat-model.md`, `docs/guides/` (get-a-tag, start-your-own-community), `docs/INTEGRATION-PLAN.md`.

## NOT in this codebase (guard against scope creep)
Do not assume/reintroduce: Stripe billing, Twilio SMS, Chart.js dashboards, blog, scheduled email digests (only an `email_digest` config key), account-deletion flow, **in-app chat** (deliberate — see Protocol section), REST/DRF API (federation speaks its own signed endpoints). (Service worker exists **only** for casework offline capture — not a site-wide PWA.)

## Repo state / open items
- **LIVE IN PRODUCTION (2026-07-18):** reciprocalaid.network deployed and serving (apex + www 200, TLS).
  Overturns every older "nothing deployed" claim. Droplet `143.244.167.7`, hand-run docker compose
  (Caddy → gunicorn → postgres:16 + redis:7). Serves the **fictional St. Brigid's** demo
  (`seed_demo_parish`, DEBUG-only). **Demo creds must rotate before any real parish onboards.**
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
- **Ethics gate: 2 of 6 boxes CHECKED (2026-07-27).** **Box 5 (#120):** on-behalf-of consent honestly
  recorded — `Consent.subject_person` grantor + `recorded_by` witness (§4.1), initials + "not asked
  directly" until an active consent names them, public `/terms/` limits page, report/block reachable
  from any post; follow-up #128 fixed the intake `record_method` enum (`consent/0005`, gate 1201).
  **Box 4 (#121):** `docs/incident-response.md` — exposure clock (1h contain / 24h facts / 72h tell the
  affected / 7d tell everyone), judicial-warrant-vs-ICE-I-200 test, no-volunteer rule; names the known
  gap: **no scoped legal-hold switch exists** (the retention sweeps auto-delete; the only preserve today
  is stopping the scheduler). Guarded by `tests/test_incident_response_plan.py`. **Box 2 groundwork
  (#122, box still UNCHECKED):** `dr_sim.sh` now runs without B2 (explicit `DR_BACKUP_FILE` / B2 / newest
  local), **fails on an empty restore**, and asserts a known record via `DR_EXPECT_SLUG`; refusal paths
  tested (`tests/test_dr_rehearsal.py`, 9). §9.2 found the **B2 lifecycle rule does not exist** — remote
  backups accumulate unbounded, outliving crypto-shred, until the founder creates it.
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
  precondition gate. **Now 2 of 6 boxes checked** (breach/legal-demand plan #121, on-behalf consent #120
  — see the 2026-07-27 bullet above); still open: monitoring wired, tested backups + verified retention,
  key custody off root, governance beyond a solo steward. Policy: the reference instance
  stays fictional-only until every box passes. Pointer from `CLAUDE.md`.
- **Monitoring DECIDED (#86/#87):** UptimeRobot only, **Sentry OFF** (`SENTRY_DSN` empty) — rationale
  (PII-leak in error payloads) in `docs/monitoring-decision.md`. Founder still to create the monitor.
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
  `hgit_sync.py` references retired (#127).
- **Design/art:** The Commons system + 7-scene Higgsfield linocut print suite (fixed-palette webp);
  spoken-copy + CarePortal-grammar passes recorded in the brain's `identity/voice.md`.
- **Next manual/ops steps (founder):** create the UptimeRobot monitor; run the DR rehearsal on the
  droplet (`dr_sim.sh`, vps-runbook §9.1) and **create the B2 lifecycle rule — it does not exist, so
  remote backups currently accumulate unbounded** (§9.2, ethics box 2); **rotate demo creds** before a
  real parish; SMTP creds so consented email leaves the console backend; real two-instance federation
  dark launch (runbook ready); old-KEK retirement (runbook Phase 5) once prod censuses are clean;
  DB-role step-0 check on the host. **The `docs/ethics-and-safety.md` gate must pass before real PII.**
- **Open governance:** 501(c)(3) filing (site copy flips on grant — test pinned); governance beyond a
  solo steward is an open ethics-gate item.
- **Roadmap (DESIGNED, not built):** §12.3 Stage C bidx backfill (Stages A/B/D are BUILT — PR #71),
  Lakes 3–8, mobile companion (React Native/Expo, design PR #33) + LLM need classifier. Moderation
  follow-ups: graduated "freeze", report-abuse throttles, on-behalf dedupe (hidden/removed-record
  federation containment landed in #118).

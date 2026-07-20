# UMI Exchange — Current State

> Authoritative project snapshot. Paste this into a fresh chat (or share the
> file) so an assistant compares against ground truth instead of guessing.
> Reflects `main` @ `53d0356` (2026-07-18).
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
  feed/pulse/search, 404s for members; coordinators unhideable; reporter anonymous. **Report a member**
  from the match detail page (shown once identities are known, §8.2). **Member↔member `Block`**
  (member-initiated, preventative): blocks a future match (propose → **409**), hides the two from each
  other's feed + detail (**404**), does NOT recall contact already revealed by a past match (§3.6),
  and the blocked person is not notified; self-serve "blocked neighbours" unblock list. **Durable
  coordinator removal:** sets `Member.removed_at`/`removed_by` so a removed member can't rejoin on the
  same still-valid code; ripples (their open needs/active offers off the board, in-flight matches
  cancelled) and is reversible via a coordinator **reinstate** action in the queue. All audited (§8.3).
- **Not implemented:** referrals; in-app chat (**by design** — brokered contact + §8.2
  revelation is the model; chat only ships with reporting/retention/moderation around it).
- **Match state machine:** `proposed → accepted | cancelled | expired`; `accepted → fulfilled | unfulfilled | cancelled`. Terminal states enforced via `transition_to()`.
- **Security / consent rules enforced in code:**
  - Contact info revealed only after acceptance (§8.2), to participants/coordinators; every disclosure is audited. A volunteer who proposed without an offer counts as participant.
  - Self-match prevention (§8.6): proposer ≠ requester **and** offer-owner ≠ requester.
  - Match-update authz: requester / offer-owner / proposer / coordinator only; others **403**.
  - Race handling (§8.7): match accept locks the **Match** row (`select_for_update(of=("self",))`, Postgres-safe with the nullable `offer` outer join) **and** the **Need**; second concurrent accept → **409**.
  - Append-only audit (§8.3): model-level `save`/`delete` blocks + Postgres `REVOKE`; **IPs salted-SHA-256** (`SECRET_KEY`); client IP read from the trusted `X-Real-IP`, never the spoofable left-most `X-Forwarded-For`. Deployment checklist provisions **separate owner/runtime DB roles** (`AUDIT_DB_APP_ROLE`) so the append-only REVOKE binds the app's own role.
  - Federated sharing is **owner-only** (coordinators cannot consent on a member's behalf); only redacted outline fields cross (category, urgency, coarse locality, week bucket) until an accepted match.
  - Join/household codes via CSPRNG (`secrets`); health-check token compared in constant time.
  - Production **refuses to boot** on an insecure `SECRET_KEY` / empty `ENCRYPTION_KEY`.

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

## Casework (Lake 2) specifics
- Sensitivity levels (standard/restricted) — **unclassified defaults to restricted** (fail-safe); single authz matrix `apps/casework/access.py::case_access()`.
- Consent-first opening (emergency flag allows null consent via a DB `CheckConstraint`); revocation **freeze** (no new notes/export once consent revoked; FollowUp writes re-check consent).
- 4-hour sensitive-session **re-auth** middleware on casework decrypt views.
- Finalized notes are immutable (amendments are new rows; retention sweep uses bulk `.update()` for that reason).
- **Offline visit capture:** scope-limited **service worker** + IndexedDB queue; draft note bodies **AES-GCM encrypted at rest** (non-extractable WebCrypto key); idempotent sync endpoint.
- Warm handoffs, follow-ups, access grants (viewer/contributor, expiring/revocable), case export gated by `case_export` consent scope.

## Codebase
- **Stack:** Django 5.2, PostgreSQL (prod/CI) / SQLite (local default), Redis (optional), HTMX, Alpine.js, Tailwind 3.4 (`static/css/output.css`), WhiteNoise, gunicorn, Argon2, django-q2 (optional).
- **17 Django apps:** accounts, audit, casework, communities, consent, dashboard, **federation**, health, households, **hub**, matches, **moderation**, needs, notifications, offers, people, tags. Plus `apps/common` — shared non-registered module (`state.py` `StateMachineMixin`).
- **Hub ("The Pulse"):** per-member community hub — pulse feed, spotlight, verified-badge surface, community switcher, data-derived **first-steps onboarding** (post → raise a hand → connect; dismissible, never nags twice).
- **Member tags & verification:** claim → coordinator verify/reject/revoke (state machine); **verified-only** badges surface (visibility-honoured); a self-reported or revoked claim never renders as endorsed.
- **Search & feed:** model-aware keyword + **area** matching with relevance ordering (`order_by_relevance`); rank-aware feed merge when searching; honest empty states with one-tap clear.
- **Communities:** per-community theming (presets + hex overrides → CSS custom properties), admin-gated **setup wizard** (join code + printable QR, colours, coordinators, first ask), coordinator-curated **resources directory** (archive-not-delete), two-doors welcome.
- **Notifications:** in-app always; **consented email delivery** — SMTP auto-enables in production when creds exist, per-user `email_notifications` opt-out honored everywhere, console backend is the safe-fail default.
- **Rate limiting:** fixed-window limiter (`apps/accounts/ratelimit.py`); auth POSTs per trusted IP + per account; flag POSTs 10/hr per user.
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
- **≈1006 tests** green on **Postgres 16 + Redis** (CI; SQLite works locally, minus one Postgres-only
  full-text relevance test in `test_search_area.py` that needs PG — `apps/needs/search.py` gates
  relevance on `vendor == "postgresql"`); `ruff check` + `ruff format --check` clean (ruff **pinned** in
  CI; `hgit_sync.py` excluded via `pyproject.toml`); bandit baseline known-accepted (non-blocking);
  `check --deploy` **0 issues** under production settings.
- Verification gate = the **`/gate` skill** (full suite count read from a file — never a piped tail). Pre-commit hook runs ruff/format/migrations/bandit.
- **CI green** (`.github/workflows/ci.yml`): three jobs — Lint & Security Scan, Test & Coverage (PG16+Redis), Docker Build Test.
- **DEPLOYED (2026-07-18):** DigitalOcean droplet `143.244.167.7` (~960 MB + 2 GB swap), docker compose
  **Caddy → gunicorn → postgres:16 + redis:7**, TLS via Let's Encrypt, repo at `/opt/umi-exchange`.
  Deploy is **hand-run** (image built on the box, no ghcr push); secrets in a git-ignored `.env`.
  Serves the **fictional St. Brigid's** demo (`seed_demo_parish`). Deploy scaffolding: `Dockerfile` +
  compose (+ prod compose, Caddy, logrotate); scripts `harden.sh`, `backup.sh` (30-day `RETENTION_DAYS`
  + B2), `restore.sh`, `security_check.sh`; `docs/deployment-checklist.md` incl. **DB-role separation step 0**.
- Docs: `CLAUDE.md` (agent guide + gotchas), **`docs/protocol/spec.md`** (UMI Protocol v0.1 CANONICAL),
  **`docs/ethics-and-safety.md`** (harm analysis + onboarding gate), **`docs/monitoring-decision.md`**,
  `docs/federation-dark-launch-runbook.md`, `docs/envelope-rollout-runbook.md`, `docs/privacy-retention.md`,
  `docs/deployment-checklist.md`, `docs/threat-model.md`, `docs/guides/` (get-a-tag, start-your-own-community), `docs/INTEGRATION-PLAN.md`.

## NOT in this codebase (guard against scope creep)
Do not assume/reintroduce: Stripe billing, Twilio SMS, Chart.js dashboards, blog, scheduled email digests (only an `email_digest` config key), account-deletion flow, **in-app chat** (deliberate — see Protocol section), REST/DRF API (federation speaks its own signed endpoints). (Service worker exists **only** for casework offline capture — not a site-wide PWA.)

## Repo state / open items
- **LIVE IN PRODUCTION (2026-07-18):** reciprocalaid.network deployed and serving (apex + www 200, TLS).
  Overturns every older "nothing deployed" claim. Droplet `143.244.167.7`, hand-run docker compose
  (Caddy → gunicorn → postgres:16 + redis:7). Serves the **fictional St. Brigid's** demo
  (`seed_demo_parish`, DEBUG-only). **Demo creds must rotate before any real parish onboards.**
- **The #93–#99 span (2026-07-19/20):** **#93** search-relevance test marked postgres-only
  (SQLite FTS divergence stopped impersonating regressions) · **#95** demo-gallery walking
  resolver goes via the hub + throttle-hardened login · **#96** anonymous gated-screen GETs
  302 to login, never 500 (all four screens regression-locked) · **#97** create screens drop
  the bottom nav (it z-ordered over the fixed submit at phone width; focused-task pattern) ·
  **#98** walkthrough §4 promise-location wording · **#99** the founder-gated tutorial-video
  pipeline lands in `docs/tutorial/` (six keyed stages: script, shot list, hardened Playwright
  rig + cycle runner, contact sheet, cut-down map + SRTs, assembly handoff — footage
  disposable, rig durable). Gate count now **1012 on PG16**. Rig gotchas recorded: reduce-
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
- **Ethics & safety gate (2026-07-18):** `docs/ethics-and-safety.md` — honest harm analysis + a hard,
  **unchecked** precondition gate (monitoring wired, tested backups, key custody off root, breach/
  subpoena plan, on-behalf consent, governance beyond a solo steward). Policy: the reference instance
  stays fictional-only until every box passes. Pointer from `CLAUDE.md`.
- **Monitoring DECIDED (#86/#87):** UptimeRobot only, **Sentry OFF** (`SENTRY_DSN` empty) — rationale
  (PII-leak in error payloads) in `docs/monitoring-decision.md`. Founder still to create the monitor.
- **Ops/infra merges:** docker collectstatic-under-prod fix (#83), droplet-config reconcile (#89),
  CC tooling — `py_compile` guard + `/checkpoint` + `/merge-pr` (#85), protocol comment-leak fix (#88).
- **Design/art:** The Commons system + 7-scene Higgsfield linocut print suite (fixed-palette webp);
  spoken-copy + CarePortal-grammar passes recorded in the brain's `identity/voice.md`.
- **Next manual/ops steps (founder):** create the UptimeRobot monitor; **rotate demo creds** before a
  real parish; SMTP creds so consented email leaves the console backend; real two-instance federation
  dark launch (runbook ready); old-KEK retirement (runbook Phase 5) once prod censuses are clean;
  DB-role step-0 check on the host. **The `docs/ethics-and-safety.md` gate must pass before real PII.**
- **Open governance:** 501(c)(3) filing (site copy flips on grant — test pinned); governance beyond a
  solo steward is an open ethics-gate item.
- **Roadmap (DESIGNED, not built):** Person blind index (`person_name_bidx`, §12.3, PR #71 draft),
  Lakes 3–8, mobile companion (React Native/Expo, design PR #33) + LLM need classifier. Moderation
  follow-ups: federation-share revoke on removal, graduated "freeze", report-abuse throttles, on-behalf dedupe.

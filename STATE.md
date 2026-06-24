# UMI Exchange — Current State

> Authoritative project snapshot. Paste this into a fresh chat (or share the
> file) so an assistant compares against ground truth instead of guessing.
> Reflects `main` @ `f3b63fe` (2026-06-23).
> This repo = **Lake 1 (Parish Aid Board)** + **Lake 2 (Case Notes / casework)** of the UMI Protocol.

## Protocol & conformance
- **UMI Protocol v0.1 — Core ✅ + Casework ✅.** Next milestone: **Federation** (unbuilt).
- **Lake 1 entities:** `umi:Need`, `umi:Offer`, `umi:Match`, `umi:Consent`.
- **Lake 2 entities (casework):** `Person`, `CaseFile`, `CaseNote`, `FollowUp`, `WarmHandoff`, `CaseAccessGrant`.
- **Not implemented:** referrals, attestations, federation (a trust-badge UI placeholder exists with no model behind it).
- **Match state machine:** `proposed → accepted | cancelled | expired`; `accepted → fulfilled | unfulfilled | cancelled`. Terminal states enforced via `transition_to()`.
- **Security / consent rules enforced in code:**
  - Contact info revealed only after acceptance (§8.2), to participants/coordinators; every disclosure is audited.
  - Self-match prevention (§8.6): proposer ≠ requester **and** offer-owner ≠ requester.
  - Match-update authz: requester / offer-owner / proposer / coordinator only; others **403**.
  - Race handling (§8.7): match accept locks the **Match** row (`select_for_update(of=("self",))`, Postgres-safe with the nullable `offer` outer join) **and** the **Need**; second concurrent accept → **409**.
  - Append-only audit (§8.3): model-level `save`/`delete` blocks + Postgres `REVOKE`; **IPs salted-SHA-256** (`SECRET_KEY`); client IP read from the trusted `X-Real-IP`, never the spoofable left-most `X-Forwarded-For`.
  - Join/household codes via CSPRNG (`secrets`); health-check token compared in constant time.
  - Production **refuses to boot** on an insecure `SECRET_KEY` / empty `ENCRYPTION_KEY`.

## Encryption (crypto-shred) — A–E complete
- `apps/people/crypto.py`: **direct-KEK** (`encrypt_str`/`decrypt_str`, MultiFernet over `ENCRYPTION_KEYS`, rotation-ready) **and envelope** (per-record DEK wrapped by the KEK list → crypto-shred: delete the `*_enc_dek` and the ciphertext is permanently opaque).
- **Envelope-encrypted PII** (all migrated, dual-read → backfill → **Stage E** legacy-read removal all shipped — getters now **fail loud** on a DEK-less ciphertext):
  - `needs.Need.on_behalf_of` (read/write via the `on_behalf_of_name` property)
  - casework: `CaseFile.summary`, `CaseNote.body`, `FollowUp.detail`, `WarmHandoff.summary`
  - `people.Person`: `display_name`, `contact` (JSON), `dob`
- **Ops:** `rotate_keks` re-wraps every DEK under the new primary KEK (registry covers all fields). Census commands `casework_envelope_status` + `people_envelope_status` report empty/legacy/envelope/unreadable per field. **Old-KEK retirement is now unblocked** (all PII envelope-only). Full sequence: `docs/envelope-rollout-runbook.md`.

## Casework (Lake 2) specifics
- Sensitivity levels (standard/restricted); single authz matrix `apps/casework/access.py::case_access()`.
- Consent-first opening (emergency flag allows null consent via a DB `CheckConstraint`); revocation **freeze** (no new notes/export once consent revoked).
- 4-hour sensitive-session **re-auth** middleware on casework decrypt views.
- Finalized notes are immutable (amendments are new rows).
- **Offline visit capture:** scope-limited **service worker** + IndexedDB queue; draft note bodies are **AES-GCM encrypted at rest** (non-extractable WebCrypto key), decrypted only in-memory at sync; idempotent sync endpoint.
- Warm handoffs, follow-ups (re-gated by current `case_access()`), access grants (viewer/contributor, expiring/revocable), case export gated by `case_export` consent scope.

## Codebase
- **Stack:** Django 5.2, PostgreSQL (prod/CI) / SQLite (local default), Redis (optional), HTMX, Alpine.js, Tailwind (`static/css/output.css`), WhiteNoise, gunicorn, Argon2.
- **14 Django apps:** accounts, audit, communities, consent, dashboard, health, households, matches, needs, notifications, offers, **people**, **casework**, **tags** (member tags & verification). Plus `apps/common` — a shared, non-registered module (`state.py` `StateMachineMixin`), not counted as an app.
- **Member tags & verification:** `apps/tags` — members claim tags; coordinators verify/reject/revoke (state machine via `apps/common/state.py`); **verified-only** badges surface on feed + detail pages (visibility-honoured so coordinator-only tags never leak); Django admin queue. A self-reported claim never renders as endorsed.
- **Per-community theming:** 10 presets + per-community hex overrides via `Community.settings` → CSS custom properties.
- **Rate limiting:** fixed-window limiter (`apps/accounts/ratelimit.py`); auth POSTs limited per trusted IP + per account.
- **Optional:** django-q2 (ORM broker, no Redis required), 2FA (off by default).
- **Migrations:** all model apps; casework `0003`/`0004` (envelope DEK cols + backfill), people `0002`/`0003` (same). Backfills are batched, idempotent, resumable (`atomic=False`), reversible.

## Visual design — warm "parish atmosphere"
- Light themes only; default "parish": bg `#FDFBF7`, ink `#2C2A29`, primary green `#2B5E2B`, gold `#C49A3C`. Serif headings (Lora→Georgia, no external webfont), Open Sans body.
- Translucent blurred header; bulletin-style cards with green (need) / gold (offer) accents; green pill buttons; calm micro-interactions only (respect `prefers-reduced-motion`).
- Tailwind compiled to `static/css/output.css`; served via WhiteNoise manifest storage (**needs `collectstatic`**; `DEBUG=False` in prod).

## Testing / CI / Deploy
- **~310 tests passing** on **both SQLite and Postgres**; `ruff check` + `ruff format --check` clean; `check --deploy` **0 issues** under production settings. `make lint` / `make test`.
- CI (`.github/workflows/ci.yml`) runs lint + tests on **Postgres 16**. Deploy: `Dockerfile` + compose (+ prod compose, Caddy, logrotate); scripts `harden.sh`, `backup.sh`, `restore.sh`, `security_check.sh`.
- Docs: `CLAUDE.md` (agent guide), `docs/envelope-rollout-runbook.md`, `docs/prompt-inventory.md`, `docs/sandbox-report.md`, `docs/INTEGRATION-PLAN.md`.

## NOT in this codebase (guard against scope creep)
Do not assume/reintroduce: Stripe billing, Twilio SMS, Chart.js dashboards, blog, scheduled email digests (only an `email_digest` config key), account-deletion flow. (A PWA-style **service worker exists**, but **only** scoped to casework offline visit capture — not a site-wide PWA.)

## Repo state / open items
- All feature work merged to `main`: Lakes 1+2, envelope encryption A–E, the verified-flaw fixes (salted audit IP hash, X-Forwarded-For hardening, follow-up re-gating, audited household join, DB-bounded feed, `rotate_keks` skip-lock fix, `CheckConstraint condition=`, Postgres match-lock fix, offline-draft encryption), CLAUDE.md, envelope runbook.
- **Next manual/ops step:** old-KEK retirement (runbook Phase 5) once deployed + censuses confirmed clean in prod.
- **Open governance decision:** with crypto-shred shipped, the privacy policy can honour the §5.8 erasure promise (delete DEK) — state the real retention model.
- **Roadmap (DESIGNED, not built):** Federation (next conformance level), Person blind index (`person_name_bidx`, §12.3), Lakes 3–8, mobile (React Native) + LLM need classifier.
- Some stale remote branches may remain pending deletion.

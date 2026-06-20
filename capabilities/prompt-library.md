# Prompt Library — ready-to-send AGI prompts

> STATUS: 2026-06-18. Copy-paste prompts for the design/build AGI. After a result comes back,
> Claude Code does a verify-before-trust review + staged integration. See
> `projects/umi-exchange-roadmap.md` for status of each.

---
## P1 — Federation (design doc)
```
ROLE: lead protocol designer for UMI (repo umi-exchange, Django 5.2/Postgres/HTMX). Lakes 1+2
BUILT; all PII envelope-encrypted; conformance Core+Casework. Produce the FEDERATION design doc —
design only, no code.
SOURCES: UMI Protocol v1.0 + Lakes Operating Manual (cite sections; flag gaps as DESIGN DECISION).
BUILD ON: communities (Member/Community), needs/offers/matches (+ §8.2 contact-revelation, §8.7
locking), consent (gate sharing), audit (append-only emit, ≤32-char actions), people/crypto (envelope).
PRINCIPLES: consent not surveillance; standalone-first (federation opt-in per community AND per
record, default off; no central authority/shared DB); data minimization (only redacted, non-identifying
discovery; identity/contact post-accept only, §8.2 across instances); no PII in logs/audit.
MUST COVER: (1) cross-community discovery; (2) handshake/trust establishment (instance identity, key
exchange, mutual auth, signed+replay-protected requests — mTLS vs HTTP Message Signatures/JWS, pick one;
human link approval + revocation; full threat model); (3) consent propagation (new scope, consent
receipts, revocation→stop+notify+audit, crypto-shred across instances); (4) secure attribute exchange
(what crosses when, encryption in transit + envelope at rest, minimal disclosure, attestations).
ALSO: cross-instance match lifecycle + idempotency + unreachable-peer behavior; data model; wire
protocol/API + versioning; audit actions; abuse/failure modes; staged build plan (each stage shippable+
reversible, behind the opt-in flag, with verify gates); conformance mapping; open questions w/ defaults.
OUTPUT: one Markdown design doc + ASCII sequence diagrams (handshake + a cross-instance match) + data
model table; tag claims BUILT/DESIGNED/DECISION-NEEDED; DESIGN ONLY, stop for approval.
CONSTRAINTS: branch not main; nothing deployed; preserve §8.2/append-only audit/envelope; STOP before any schema change.
```

---
## P2 — Person blind index (§12.3)
```
ROLE: extend umi-exchange. Person PII is envelope-encrypted (display_name/contact/dob); no searchable
plaintext. TASK: add a BLIND INDEX so coordinators can look a person up by name WITHOUT decrypting
every row, without weakening encryption (UMI §12.3).
DESIGN: add Person.name_bidx (indexed, nullable) = keyed HMAC-SHA256 of the NORMALIZED name (casefold/
strip/collapse ws); equality only; store bytes, never the name. DEDICATED key BLIND_INDEX_KEY, SEPARATE
from ENCRYPTION_KEYS. Search = HMAC the query, filter name_bidx. Helper crypto.name_blind_index(value).
CRITICAL: set name_bidx in the display_name setter (sync), clear when name cleared; CRYPTO-SHRED must
ALSO null name_bidx (else name stays equality-testable post-erasure) — code + test. Not for authz.
ROLLOUT (mirror envelope A–D): A migration+index; B setter+helper+key (fail-closed if unset); C backfill
(decrypt via envelope→HMAC), batched/idempotent/resumable/reversible; D person_bidx_status census + tests
(exact match, normalization, no collision, shred nulls bidx, empty→null).
CONSTRAINTS: branch not main; no deploy; ruff+format; makemigrations --check; pytest on POSTGRES;
check --deploy 0; no plaintext name stored/logged; STOP before the backfill migration.
```

---
## P3 — Member tags & verification  (design APPROVED — see roadmap for the 5 fixes; this is the original prompt)
```
ROLE: extend umi-exchange (Member in apps/communities; trust-badge placeholder w/ no model). GOAL: member
tags (priest, deacon, SVdP, nurse, married, …) + verification "like Twitter's check", parish-adapted;
verified-vs-self-reported must be visually UNMISTAKABLE; verified "priest" is PUBLIC + accountable.
SAFETY: false authority claims can exploit the vulnerable → unverified labeled "self-reported", never
styled verified; every verify/revoke append-only audited; only authorized roles verify.
DESIGN-FIRST then stop: per-community Tag catalog (tier self_serve/coordinator_verified/admin_verified,
visibility, public_when_verified) + MemberTag state machine (self_claimed→pending→verified|rejected;
verified→revoked; +removed) via transition_to(); who-verifies matrix (admins-only for clergy); per-tag
visibility (public=community-members-only, logged-out see nothing); verification queue (filtration);
audit actions ≤32 chars, no PII; badge styles (verified/self-reported/pending).
CONSTRAINTS: branch not main; no deploy; verify on POSTGRES + check --deploy; tests for state machine/
authz/visibility/audit/public-priest/rate-limit; seed tags via signal or apps.get_model (no import cycle);
StateMachineMixin in a shared module; reuse apps/accounts/ratelimit.py; recompile output.css (never hand-edit).
```

---
## P4 — Sign-in hub
```
ROLE: extend umi-exchange (Django 5.2/HTMX/Tailwind; apps/dashboard has patterns). GOAL: a personalized
HUB after sign-in — the member's communities, quick actions (post need/offer, browse feed), open matches +
recent notifications, and their tags/verification status. Login-required view + HTMX partials; post-login
redirect; multi-community switch; reuse Member/Need/Offer/Match/Notification (read-only, bounded queries,
no new schema if avoidable); parish-atmosphere design + theme vars; mobile-first/accessible/reduced-motion.
Tests: renders for a member, requires auth, no cross-community leak.
CONSTRAINTS: branch not main; no deploy; ruff+format; makemigrations --check clean; pytest on Postgres; check --deploy 0.
```

---
## P5 — Graphic-design / UI polish
```
ROLE: extend umi-exchange. Tailwind compiled to static/css/output.css (NEVER hand-edit; recompile:
npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify). Parish atmosphere:
light themes, primary #2B5E2B, gold #C49A3C, serif headings (Lora→Georgia, no external webfont), calm
micro-interactions, per-community theming via CSS vars, 10 presets. GOAL: make it look noticeably nicer
WITHOUT breaking the design system/theming — typography, spacing, cards, buttons, empty states, forms,
mobile, landing + feed. Accessible (contrast/focus/reduced-motion), mobile-first, no external fonts/CDNs,
no view-logic changes (presentation only). Recompile output.css (show the command); pytest still green; check --deploy 0.
```

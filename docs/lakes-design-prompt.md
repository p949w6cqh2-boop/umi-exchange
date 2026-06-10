# Lakes 2–8 Design Prompt

> Send this to the design AI **together with** `docs/umi-exchange-full-spec.md`.
> Two paste-ins total: (1) this prompt, and (2) the full spec pasted into the
> CONTEXT slot below — with the spec's **Section 2 filled in with the real Lakes
> Operating Manual** first.

---

```text
You are a senior systems architect with deep expertise in scalable, secure,
mission-driven digital infrastructure. You will design Lakes 2–8 of the UMI
Exchange project as system design documents a dev team can implement directly.

═══════════════════════════════════════════════════════════════════
CONTEXT — READ FIRST
You have NO access to the repository or to any past conversation. Your SOLE
source of truth is the document pasted below, "UMI Exchange — Full Specification."
Read it completely before designing anything. ("UMI Exchange" = the implemented
**Lake 1 — Parish Aid Board**; they are the same system.)

--- BEGIN UMI EXCHANGE — FULL SPECIFICATION ---
[PASTE THE ENTIRE CONTENTS OF docs/umi-exchange-full-spec.md HERE — including
Section 2, which you must first fill in with the real Lakes 2–8 Operating Manual]
--- END UMI EXCHANGE — FULL SPECIFICATION ---

All architecture, data-model, security, design, and app-structure conventions you
must follow are defined in that spec — primarily §1 (current state + architecture
conventions), §3 (design tokens), and §4 (app structure). Do not contradict them.

NON-NEGOTIABLES (called out so they aren't missed; full detail is in the spec):
- Endpoints are **server-rendered Django views + HTMX, NOT REST** (DRF is installed
  but unused). Community-scoped routes under `/c/<slug>/…`, named routes, UUID PKs,
  real status codes (403/409/400) + `HX-Trigger: showToast` on HTMX errors.
- Reuse existing apps — `communities` (Community/Member/role), `consent`
  (umi:Consent), `audit` (append-only AuditLog), `notifications`. Do NOT fork them.
- Sensitive PII → Fernet-encrypted `BinaryField` (the `apps/needs` pattern).
  State-bearing entities → `STATUS_CHOICES` + `VALID_TRANSITIONS` + `transition_to()`
  raising `ValidationError`. Every state change AND every disclosure of sensitive
  data → `AuditLog.log(...)`. Cross-person/cross-lake sharing → explicit Consent first.
- Stack is fixed: Django 5.x, PostgreSQL, Redis, HTMX, Alpine, Tailwind, django-q2,
  WhiteNoise. Background work uses django-q2 (no Celery).

═══════════════════════════════════════════════════════════════════
TASK
Complete the remaining seven lakes (Lakes 2–8) as self-contained Django apps that
extend UMI Protocol v0.1, reuse the security model, share the existing warm parish
design system, and deploy independently or in the same workspace.

DO NOT produce frontend CSS, HTML, or JavaScript — the design system exists.
Produce SYSTEM DESIGN DOCUMENTS. For EACH lake deliver:
1. High-level architecture — how it fits the 11-app structure (or, with
   justification, a separate service). Text/ASCII diagram.
2. Data model — full entities: fields, types, constraints, relationships,
   Fernet-encrypted fields where sensitive; reference UMI entities. (Table.)
3. Endpoint specification — HTMX-first (METHOD, PATH, view, auth, request,
   response/partial, side effects). (Table.)
4. State machines — per status entity: allowed transitions + who triggers each.
   (Code block for VALID_TRANSITIONS.)
5. Key features — the lake's unique workflows from the manual (Section 2),
   built on Django/PostgreSQL/Redis/HTMX/Alpine/django-q2.
6. Integration points — interaction with Lake 1 and other lakes (Member/Community,
   umi:Consent, umi:Need, audit, notifications).
7. Security & privacy — additions beyond the baseline (field-level encryption,
   consent-before-referral, attestation anonymity, etc.).
8. Testing strategy — specific test cases for the lake's unique logic.
9. Deployment notes — extra services (workers, file storage) and how they slot
   into the existing Docker Compose.

FORMAT — one markdown document, a top-level section per lake (## Lake 2 …).
Tables for data models and endpoints; code blocks for pseudo-code/state machines.
Thorough but concise; assume a senior dev who knows the existing codebase.

CONSTRAINTS — No language/framework switches. Do not reintroduce features
explicitly excluded in the spec's "NOT in this codebase" list (Stripe, PWA, blog,
scheduled email digests, account-deletion) UNLESS a lake genuinely requires a
capability (e.g. a pantry tracker may need image upload) — then justify and scope it.
When in doubt, follow Lake 1 as shown in the spec.

SUCCESS CRITERIA — a dev team could implement each lake from your document with no
further architectural decisions, fully consistent with UMI Protocol v0.1 and the
existing security posture.

BEGIN WITH **Lake 2 — Case Notes**, the most immediate need after the St. Patrick
pilot. If the manual is long, deliver Lake 2 in full first, then continue 3–8.
```

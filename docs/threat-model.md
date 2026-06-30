# Pre-pilot threat model — application layer (Lakes 1 + 2)

> **Scope & posture.** This app holds the identities, locations, and case files of poor and vulnerable
> people. The risk is not only privacy — it is a person's **physical safety** (e.g. a DV survivor's
> location). This is a protective, design/audit pass on the **application** layer before St. Patrick goes
> live with real PII. It builds on — does not duplicate — the **network** layer
> ([`network-security-addendum.md`](network-security-addendum.md)) and the **dev/host** layer
> ([`umi_dev_security_protocol.md`](umi_dev_security_protocol.md)). No exploitation; analysis only.
>
> Verified against code: `apps/casework/access.py`, `config/settings/production.py`,
> `apps/casework/middleware.py`, `apps/audit/migrations/0002_append_only.py`, the per-view community
> filters, `apps/tags/views.py`, `apps/accounts/ratelimit.py`. SAST baseline: bandit + semgrep run in CI;
> current findings are 3 Low + 1 Medium, all pre-existing and benign (try/except/pass, dev bind-all, the
> insecure-key guard) — **no new** findings.

## 1. Attacker model — blast radius on ONE real vulnerable person

| Actor | What they can reach | Blast radius on a vulnerable member | Bounded by |
|---|---|---|---|
| **Malicious member** (same community) | Public feed, own needs/offers, match flow | Cannot read case files (`case_access`→NONE) or others' contact pre-match. Could *try* to lure via fake need/offer or a faked authority tag. | `case_access`, §8.2 contact-gate, verified-only tag styling |
| **Curious/malicious coordinator** | All **standard** case files in *their* community, member contacts via match oversight | **High**: can read every standard-case PII (names, narratives, locations) in their community. *Cannot* read **restricted** cases. | standard/restricted split, every case view audited, community scope |
| **Rogue admin** (their community) | Everything in their community incl. restricted cases; can verify clergy tags; change roles | **Severe within one community**: full PII + can mint a "verified clergy" badge. | append-only audit (can't erase the trail), community scope, no cross-community |
| **External unauth attacker** | Landing, `/auth/*`, `/health/` | Low — no PII without an account; brute-force gated. | Argon2, ratelimit, CSP/HSTS/CSRF, fail-fast prod, UUID ids |
| **Compromised host / DB** | DB at rest + the env | DB alone = opaque ciphertext (envelope; KEK not in DB/backups). **Host *with* the env KEK = full PII** — the worst case. | envelope/crypto-shred, KEK in env only, key-free backups |
| **Compromised dependency** (supply chain) | Whatever the app process can | Could exfiltrate decrypted PII in-process (it has the KEK at runtime). | pinned deps, bandit/semgrep/pip-audit in CI, tight CSP, no DRF surface |

## 2. Crown-jewel flows — where identity or LOCATION can leak

1. **Casework PII** (`CaseFile.summary`, `CaseNote.body`, `Person.display_name`/`contact`/`dob`, `FollowUp`, `WarmHandoff`) — envelope-encrypted; gated by `case_access()`; 4-hr re-auth.
2. **Match contact-revelation** (`Match.get_contact_info_for`, §8.2) — contact revealed **only** after an accepted match, to participants/coordinators; every reveal audited. Need/offer detail discloses contact to **coordinators only** (audited), members stay match-gated.
3. **Household / location data** — `neighborhood` (free text, "general area", shown publicly by design), household codes (CSPRNG). A DV survivor's *precise* location must never be entered; the form guidance says "general area, not your street address."
4. **Verified-authority (clergy) tags** — `admin_verified` tier; a verified "priest" is public + accountable. The lure risk is a predator *impersonating* verified clergy.

## 3. Control map — does each hold?

| Control | Holds? | Note / gap |
|---|---|---|
| Envelope crypto + crypto-shred + KEK in env only | ✅ | DB/backups are opaque without the env KEK; `backup.sh` excludes keys + has a key-guard. **Residual:** host-with-KEK = full PII (unavoidable for a working app — minimise host blast radius). |
| `case_access()` authz matrix + cross-community isolation | ✅ | Single source of truth; NONE if `member.community_id != case.community_id`. Coordinators get **standard** only; restricted = admin/assigned/opened. |
| Per-view community/queryset filters (IDOR) | ⚠️ mostly | matches/needs/offers/casework/tags/dashboard all scope `<pk>` to community + membership; consent scopes to `participant=user`. **Gap: no systematic test** asserting cross-community 404 for *every* object view (PR #9 fixed one — its siblings are guarded by convention, not a test). |
| `SensitiveSessionMiddleware` 4-hr re-auth | ✅ | Gates the `casework` namespace; sync returns 403 JSON; reauth/sw/manifest exempt. |
| Append-only audit (can't cover tracks) | ⚠️ | Postgres `REVOKE UPDATE/DELETE/TRUNCATE` from the app role + model-level guard. **Gap: only holds if the app's DB role is NOT a superuser/owner** (they ignore grants). Must verify the prod role. |
| Argon2 + ratelimit + CSPRNG codes + constant-time | ✅ | Argon2 hasher; auth POSTs rate-limited per trusted IP + account; join/household codes CSPRNG; health token constant-time. |
| X-Real-IP trust (not spoofable XFF) | ✅ | `ratelimit.client_ip` + audit read `HTTP_X_REAL_IP`, never the left-most XFF. Depends on Caddy setting X-Real-IP and the app not being directly reachable. |
| Safe-fail (no real email/SMS, no money, archive-not-delete) | ✅ | Notifications in-app; deletes are soft where they matter; crypto-shred not hard-delete. |
| Prod hardening (HSTS, CSP, secure cookies, fail-fast) | ✅ | `production.py`: fail-fast on insecure SECRET_KEY/empty ENCRYPTION_KEY; A+ headers; Sentry `send_default_pii=False`. |

## 4. Abuse cases (platform-as-weapon — risk + whether the control holds)

- **Predator self-claims verified clergy** to gain a victim's trust → **Control holds, with a caveat.** A self-claimed tag is `self_reported` and is *never* styled as verified; only `admin_verified`-tier (clergy) can be verified, and only an **admin** can do it (`tags/views.py` filters the queue so coordinators can't act on `admin_verified`); every verify/revoke is audited. *Caveat:* the control is only as strong as the UI never rendering self-reported as endorsed — **add an abuse-resistance test** (below) so a refactor can't regress it. Residual: a **rogue admin** can still mint a fake clergy badge (audited).
- **Fake needs/offers to harvest contact or locate a target** → **Mostly held.** Contact is §8.2-gated (no pre-match reveal), so a fake need can't directly harvest contact. It *can* solicit a reply/match. **Gap:** no rate-limit on need/offer/match creation → a member could mass-post to fish. → hardening.
- **Coordinator overreach beyond their community** → **Held** by `case_access`'s community check + per-view filters. Within their own community a coordinator legitimately sees all **standard** cases — so **DV/high-risk cases must be marked `restricted`** (admin/assigned only). → process control + a default-restricted prompt (hardening).
- **Enumeration** (members / communities / household codes) → Member/case ids are **UUIDs** (not enumerable). Community **slugs are guessable** (from name) but expose only membership-gated pages. **Join codes** are 8-char CSPRNG (~2.8e12), but **`/join/` redemption is NOT rate-limited** (verified — only `tags`/`casework` views call `rate_limit`) → brute-forceable given time/automation. → **must-fix**.
- **Mass-notification spam** → no per-actor cap on match-propose/notifications. → hardening (rate-limit).
- **Doxxing via aggregated public tags/feed** → feed shows display name + general neighborhood + verified tags by design. Aggregation risk is real but bounded to what a member opted to post; **precise location must never be collected** (form guidance). → guidance + review of any new public field.

## 5. The "city-scale" question — answered honestly

This is a **standalone Django app, not self-propagating** — there is no worm/lateral-spread surface. The real scale vectors are:

1. **Compromised deploy harvesting at community scale.** One compromised host *with the runtime KEK* can decrypt that instance's entire PII set. This is the dominant risk; mitigation is host hardening (dev/host doc) + minimising who/what holds the KEK + Sentry-without-PII + the audit trail.
2. **Multi-tenant isolation** if one instance serves several communities. The *only* thing standing between communities is `case_access`'s `community_id` check + every view's community filter. → the IDOR systematic test (below) is the guard that this never regresses.
3. **Federation** (cross-instance) is **DESIGNED, not built** — **confirmed not reachable** (only a docstring reference in `tags/models.py`; no federation view/URL/code path). It is the future cross-instance spread surface and **must stay gated/off until threat-modeled separately**; keep it code-absent until then.

## 6. Threat table

| Threat | Attacker | Asset | Existing control | Gap | Severity |
|---|---|---|---|---|---|
| Read others' case PII | malicious member | casework PII | `case_access`→NONE | — | Low (held) |
| Read all standard-case PII | curious coordinator | casework PII | standard/restricted split + audit | DV case not marked restricted | **High** |
| Mint fake "verified clergy" | rogue admin | trust/safety | audited; admin-only | admin is trusted by design | Med |
| Predator self-claims clergy | malicious member | victim trust | self-reported never verified; admin-only verify | no regression test | **High→Med** |
| Cross-community data access | member/coordinator | other community PII | `community_id` checks per view | no systematic IDOR test | **High** |
| Cover tracks (edit/delete audit) | rogue admin / compromised app | audit trail | DB `REVOKE` + model guard | only if app DB role ≠ superuser | **High** |
| Join-code brute force | external | community membership | 8-char CSPRNG | confirm `/join/` rate-limit | Med |
| Fish for contact via fake posts | malicious member | contact/location | §8.2 contact-gate | no create rate-limit | Med |
| Full PII exfiltration | compromised host/dep | all PII | envelope (KEK in env) | host w/ KEK = full read | **High** (infra) |

## 7. Prioritized hardening

**Must-fix before pilot**
1. **Verify the prod DB role is NOT a Postgres superuser/owner** of `audit_auditlog` — otherwise the append-only `REVOKE` is silently bypassable. Document the role + confirm with `\du` / a check.
2. **Add the systematic cross-community IDOR test** (enumerate every `<slug>/<pk>` view; assert a member of community A gets 404/403 on community B's object). Locks PR #9's fix against regression.
3. **Add rate-limiting on `/join/`** code redemption (verified absent — community + household join don't throttle) and on the casework **reauth OTP** (`ReauthView` checks the password with no visible throttle; the global auth rate-limit middleware covers `/auth/*`, not casework reauth).
4. **Operational: mark DV/high-risk cases `restricted`.** Add a visible prompt/default so a coordinator-readable **standard** case never holds a survivor's safety-critical location. (Coordinators see all standard cases by design.)
5. **Federation: verified not reachable** (DESIGNED-only; only a docstring mention) — keep it code-absent until it is separately threat-modeled.

**Later / defence-in-depth**
6. Rate-limit content creation (need/offer/match-propose) + notification fan-out (anti-spam/fishing).
7. Per-field "precise location" guard/validation on neighborhood (reject street-address-like input).
8. Periodic access-review of `CaseAccessGrant`s (expiry already enforced; surface stale grants).

## 8. Abuse-resistance tests to add

- **Cross-community IDOR (parametrised):** for each object route, a member of community A → 404/403 on community B's `pk`. (The #2 must-fix.)
- **Self-reported clergy never endorsed:** a `self_reported` clergy tag renders with the self-reported style, never the verified badge, anywhere it appears (feed + detail).
- **Clergy verification is admin-only:** a coordinator cannot verify an `admin_verified`-tier tag (queue filter + the action both reject).
- **Audit immutability under a non-superuser role:** UPDATE/DELETE on `audit_auditlog` raises (model) and is denied (DB) — assert against a non-superuser test role.
- **Restricted case excludes coordinators:** `case_access(coordinator, restricted_case) == NONE`; `== CONTRIBUTOR` only for admin/assigned/opened.
- **Contact stays gated:** `get_contact_info_for` returns None pre-acceptance; need/offer detail reveals contact to coordinators only, audited.
- **Join-code redemption is rate-limited:** N failed codes from one IP → throttled.

---

_Read-only audit. No control was disabled or exercised against any live system. Hand back for verify-before-trust; the must-fix list gates the pilot._

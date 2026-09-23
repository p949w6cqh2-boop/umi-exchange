# Spec: account recovery without email, and assisted access

> STATUS: **SPEC**, written 2026-09-23 on the founder's key. Decision recommended below;
> **BUILD happens on a separate key after the founder reads this.** No code in this PR.
>
> Origin: the founder has two people willing to coordinate at the pilot parish. One offered to
> help digitally; one offered to *"help put people in the system"* — in-person intake. His
> question was the plain one: **how does the second one make accounts for old parishioners,
> password and all?**
>
> Companion spec, deliberately NOT this one: **assisted account creation and posting on
> someone's behalf** → `assisted-intake.md`, unwritten. That half moves real people's data and
> waits on the ethics gate. §Not this spec says where the line is.

## The question

An account can be created today without an email address. `User.email` is
`blank=True, null=True` (`apps/accounts/models.py:11`) and the registration form labels it
*"Email (optional)"* — deliberately, because the protocol serves participants who have no email
and the founder refused a CAPTCHA for the same reason (`human-verification.md`, option B:
*"walls out exactly the members Father asked us to protect"*).

**But every recovery path we have is an email path.**

- Password reset — `apps/accounts/urls.py:45`, `PasswordResetView`, `email_template_name` set
- Username recovery — `apps/accounts/views.py:177`, `UsernameRecoveryView`, takes an address

So an account created without an email, by someone who then forgets their password, is
**permanently locked out.** The only repair is a superuser in Django `/admin/`. Verified
2026-09-23: `set_password` appears in exactly two places in the codebase —
`apps/accounts/forms.py:75` (the registration form, a user on themselves) and the demo seeder.
**No view lets one person set another's password.**

The people this hits are precisely the people the optional-email decision was made for.

## What the record already decided, before we asked

Two rulings exist in the repository. Neither was written for this question and both answer part
of it.

**1. `docs/protocol/spec.md §4.1 — "Coordinators MUST NOT consent on a member's behalf."**
Quoted inside `apps/consent/models.py`. This is not an open question and this spec does not
reopen it.

**2. `apps/needs/forms.py:14-21` already prescribes the shape of any on-behalf feature:**

> *"If Lake 1 ever needs posting on someone's behalf, it should be built with the same consent
> discipline as casework: a record naming THEM (`consent.subject_person`), and limited display
> until it exists."*

✅ And the consent model is ahead of both. `Consent.METHOD_CHOICES` already carries
`("verbal", "Verbal")`, and `subject_person` exists — per its own comment — *because most people
this app holds data about have no account at all.* Someone already designed for the person who
cannot click.

### 🔴 One thing the record gets wrong, and it matters here

`human-verification.md` (2026-08-11) sets this exact case aside:

> *"Companion concern from the same meeting, deliberately NOT this spec: a phone path for
> non-tech members (already served by coordinator on-behalf-of posting; ministry practice, not
> code)."*

**That deferral rested on a capability that does not exist.** The on-behalf field was removed
from `NeedForm` deliberately — it "was never rendered by `templates/needs/create.html`, so it
could only be reached by a hand-crafted POST." The column, its envelope property, the retention
sweep and `shred_on_behalf` remain **for legacy rows only.**

So the pastor's concern at the pilot-blessing meeting was deferred on a promise the code does
not keep. **Correcting that is the reason this spec exists now rather than later.** The removal
was right; the deferral that leaned on it was not.

## What already stands, verified in code 2026-09-23

1. **Email is genuinely optional** and the account works without it — sign in, look around, and
   with a coordinator vouch, join and post.
2. **A coordinator vouch already solves human-verification without email**
   (`VERIFIED_VIA_CHOICES`: `("coordinator", "Coordinator vouch")`). The in-person path exists
   and works. It is only *recovery* that has no non-email path.
3. **Audit is append-only.** `AuditLog.save()` raises on UPDATE (`apps/audit/models.py:30-33`),
   and `log()` hashes the IP through one shared source of truth.
4. **Rate limits**: register 3/min/IP (`apps/accounts/views.py:37`), login 5/min/IP.
5. **Argon2 + optional TOTP**, and a login that diverts to the token step rather than granting a
   session on a password alone.

## Options weighed

| Option | Serves | Costs | Verdict |
|---|---|---|---|
| **A. Add an email later** | anyone who gains an address after signing up | one form, one token; no new credential type | ✅ **Take.** Smallest build on the page and it shrinks the population every other option serves. |
| **B. Printed one-time recovery code** | the person who will never have an email | a bearer credential on paper | ✅ **Take**, with the mitigations in §Recommended. |
| **C. Coordinator-issued reset code** | the person who lost the paper too | hands coordinators account-takeover power | ⚠️ **Take, but only after the role split.** See the risk. |
| **D. Security questions / known facts** | same population as B | answers are guessable and shareable | ⛔ **Refuse.** In a parish the people who know your mother's maiden name are sitting in the pews. Strictly worse here than elsewhere. |
| **E. SMS recovery** | anyone with a phone | `User.phone` exists but unverified; DigitalOcean blocks outbound SMTP and SMS is a paid external dependency | ⛔ **Not now.** Revisit only if the parish asks and someone is paying. |
| **F. Do nothing; coordinators post on behalf** | nobody, today | the capability was removed; see the correction above | ⛔ **Unavailable.** This was the standing answer and it is not real. |

## Recommended design — A + B, then C behind the role split

### One credential model, four purposes

A single table: a secret tied to a user, **hashed at rest**, single-use, with a per-purpose
expiry. Serves recovery codes, coordinator resets, admin unlocks, and — later, in the companion
spec — claim links.

- `user` FK · `purpose` · `token_hash` (SHA-256, indexed) · `created_at` · `expires_at` ·
  `used_at` · `issued_by` (Member, `SET_NULL`) · `issued_by_label` (denormalized text, survives
  the issuer's deletion)
- Generation: `secrets.token_urlsafe`, rendered in readable groups (`K4M2-9XQ7-BT3W`), in an
  **unambiguous alphabet — no `0/O`, no `1/l/I`.** A person reads this off paper, possibly
  without their glasses.
- Verification: `hmac.compare_digest`. Never `==`.
- Redemption: atomic under `select_for_update`, `used_at` set inside the transaction, so two
  simultaneous redemptions cannot both succeed.
- **The plaintext is never stored, never logged, and never placed in an audit `details` blob.**

**Expiry per purpose — and the tradeoff is real, not eliminated:**

| Purpose | Expiry | Why |
|---|---|---|
| `recovery_code` | **none**, single-use, re-issuable | a short expiry is correct security and useless for a code in a wallet needed in eight months |
| `coordinator_reset` | 15 minutes | handed over in person; it should be dead before the person leaves the building |
| `admin_unlock` | 1 hour | last resort, always attended |
| `claim` | 30 days | companion spec only |

### A. Add an email later

- **Never write `User.email` unconfirmed.** It is `unique=True`; an unconfirmed write lets
  anyone squat an address they do not control.
- Carry the pending address inside the signed token. No migration needed.
- Reuse `send_verification_email` and `templates/emails/verify_email.txt`.
- Collision with an existing account → **the same generic response as success**, matching
  password reset and username recovery.
- 🔴 **Confirming an email MUST NOT overwrite `verified_via`.** An account verified
  `"coordinator"` stays `"coordinator"`. That vouch is a human act performed at church and the
  record of it is not ours to overwrite. If `verified_at` is null, confirming may set it to
  `"email"` — that is a first verification, not a replacement.

### B. Printed recovery code

- Issued at registration **when `email` is blank.** An account with an email already has two
  paths; a third bearer credential is net negative.
- Issued inside the same transaction as the account, so a failed issue never leaves an account
  with no recovery at all.
- Shown **exactly once**, on a print-friendly page: large type, plain words for what it is and
  where to keep it, and an explicit *"I have written this down"* before the page can be left.
- **Redemption starts a password reset. It never grants a session.** That is the mitigation for
  it being a bearer credential.
- On successful redemption, **immediately offer a fresh code** — otherwise the first recovery is
  also the last.
- Re-issuable from settings by a logged-in user who lost theirs.
- Redemption is rate-limited on **both** IP and username.

### C. Coordinator-issued reset — ⚠️ gated on the role split

Surface: the community settings page, beside the existing *"Vouch for a neighbour"* form
(`templates/communities/settings.html:187`). That is where coordinators already look.

🔴 **Do not copy `VouchMemberView` here.** It finds its target by `username__iexact` **alone**
(`apps/communities/views.py:750`) with no check that the target is in the coordinator's
community. That is tolerable for a vouch, which grants only verification. **It is not tolerable
for a password reset.** This path must require membership of a community the issuer actually
coordinates.

- The coordinator generates a 15-minute code and reads it aloud. **The coordinator never sees,
  sets, or learns the password.**
- The person redeems on their own device and chooses their own password.
- If the target has an email, **notify them that a coordinator issued a reset.** A quiet
  takeover path is the failure mode.
- Audited: both member ids and the community.
- Rate-limited **per coordinator**, which is what bounds a compromised coordinator account.

🔴 **The risk, plainly: this grants every coordinator the ability to take over any account in
their community.** They cannot do that today. Audit and notification are detection, not
prevention.

**Therefore C does not ship until `is_coordinator` is split.** That property is
`role in ("coordinator", "admin")` (`apps/communities/models.py:118`) and gates roughly ten
powers across five apps — moderation hide/remove/reinstate, role changes, vouching, hidden-need
visibility, coordinator page surfaces. There is no way today to grant reset without also
granting removal. **A narrow role is a precondition of C, not an enhancement to it.**

## Build notes (for the keyed implementation PRs)

- Accounts is at migration `0005_backfill_verified`; the credential table is `0006`.
- Reserve audit names now, before ten call sites invent ten spellings:
  `account.recovery_code.issued` · `account.recovery_code.redeemed` ·
  `account.reset.coordinator` · `account.unlock.admin`.
  ⚠️ **`AuditLog.action` is `varchar(32)`** and `log()` fails loud rather than truncating —
  count the characters on every name above.
- Purge expired rows by management command, **archive semantics: never delete a used row.** The
  audit trail depends on it.
- Accessibility is load-bearing, not a checkbox. The print page is for the person CAPTCHAs were
  rejected to protect. Extend `tests/test_a11y.py`.
- New test file `tests/test_recovery_credential.py`; extend `tests/test_auth_recovery.py` for
  the email-later path. `tests/test_audit_pii_hygiene.py` must pass **unchanged**.

## Not this spec

- **Coordinator-created accounts, claim links, and posting on someone's behalf** →
  `assisted-intake.md`, unwritten. Gated on the ethics gate
  (`ethics-and-safety.md`, currently 3 of 6) and on `spec.md §4.1`.
- **Splitting `is_coordinator`.** Named here as a precondition of option C; it is a
  communities-app change and deserves its own spec.
- **Closing Django `/admin/`.** An admin unlock path is designed above; it adds a better door
  and does not close the old one (`apps/accounts/admin.py:6`). Separate decision.
- 🔴 **Unrelated leak found during this spec's grounding pass, filed separately, not fixed here:**
  `RegistrationForm.clean_email` (`apps/accounts/forms.py:48-53`) raises *"This email is already
  in use."* That lets anyone test whether an address has an account — the exact enumeration that
  password reset and username recovery were built to refuse. **Registration contradicts both.**

## The measurement that should happen before the companion spec

Section B of the feature list — coordinator-created accounts — may not be needed at all.

The physical coordinator can already sit beside someone and let them register **on their own
hands, on the coordinator's phone**, with no email, and then vouch for them. Nothing needs to be
built for that.

**Before designing anything more: seat two or three people that way, and ask them a week later
whether they remember their username.** If they do, most of the companion spec is cancelled.
One week, no code, and it decides several PRs.

## Done-when

- [ ] An account with no email can recover access without a superuser.
- [ ] A recovery code's plaintext exists nowhere in the database, the logs, or the audit table.
- [ ] A coordinator can help someone regain access **without ever knowing their password.**
- [ ] Confirming a later-added email does not overwrite a `"coordinator"` verification.
- [ ] Every reset issued by one person for another is on the append-only audit log, with the
      community, and — where an address exists — notified to the account holder.
- [ ] `tests/test_audit_pii_hygiene.py` passes unchanged.
- [ ] Option C has not shipped, or `is_coordinator` has been split. Not both false.

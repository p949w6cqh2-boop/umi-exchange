# Spec: confirm an email before anything trusts it

> STATUS: **SPEC**, written 2026-09-26 on the founder's key. Decision recommended below;
> **BUILD happens on a separate key after the founder reads this.** No code in this PR.
>
> Origin: issue #172. Found by counting production immediately after #169 deployed. #169
> closed one door — account settings no longer writes an unconfirmed address. This spec is
> about every other door, and it turned out there are five.
>
> Companion to `account-recovery.md`. Read §A there first: it established the rule this spec
> generalises — **nothing unconfirmed is ever trusted.**

## The question

An email address on an account is used for things that assume the account holder owns it:
password reset, notifications, casework reminders. **Nothing in the codebase records whether they
do.** The address is trusted from the moment it is written.

## Measured in production, 2026-09-26 (integers only, no PII)

| Real (non-seeded) accounts with an email | **8** |
|---|---|
| email ever confirmed by clicking a link | **0** |
| `verified_via = "backfill"` (predate the gate) | 4 |
| never verified | 4 |
| real accounts with **no** email | 5 |

**Every real account with an email is trusting an address nobody has proven.** That is exposure,
not evidence of compromise — most people type their own address correctly.

Probable cause for the four unverified: they registered before production SMTP worked
(2026-09-11), so their link was written to a log file and never sent.

## Every consumer of `User.email`, read from code 2026-09-26

| # | Consumer | Where | What reaches a wrong address | Exposure today |
|---|---|---|---|---|
| 1 | **Password reset** | stock `PasswordResetView`, `apps/accounts/urls.py` | **a working link to take the account** | 🔴 **live, 8 accounts** |
| 2 | **Casework follow-up digest** | `apps/casework/tasks.py:63-69` | follow-up **titles** and **case short codes** — the sensitive lake's own words | 🟡 **zero today** (casework empty); **real the day the gate closes** |
| 3 | **Notifications** | `apps/notifications/adapter.py:50,93` | need and match titles, which are plaintext by design | 🔴 live |
| 4 | **Username recovery** | `apps/accounts/views.py:193` | the username | 🟡 low alone; half of a takeover |
| 5 | **Contact reveal on a match** | `apps/communities/models.py:129-130` | a neighbour is handed an address the member may not own | 🟡 wrong contact, not a leak |

📌 **Consumer 2 is the one worth reading twice.** Lake 2 was designed so that *"nothing decrypts in
email"* (§3.6, quoted at `tasks.py:58-61`) — and it holds. But follow-up **titles** are plaintext
free text written by coordinators, and they go to whatever address is on file. A coordinator who
mistyped their email at registration would mail *"Call Maria about the eviction hearing — due
Friday"* to a stranger. **Casework holds zero rows today, so this is a gate finding, not an
incident** — but it must be closed before the ethics gate reads 6 of 6, not after.

## Why this is not a filter on `verified_via`

The obvious fix — *only send to accounts where `verified_via == "email"`* — is wrong, for a reason
that is load-bearing in this codebase:

**`verified_via` answers *"how do we know this account is a human?"*** — and a coordinator vouch,
performed in person at church, is the *strongest* answer to that question. But a vouched account's
email may never have been proven. **#169 deliberately keeps `verified_via = "coordinator"`** when
such an account later confirms an email, because the vouch is a human act that is not ours to
overwrite.

So after #169, a confirmed email and an unconfirmed one can carry **identical** verification state.
**There is no field that means *this address is confirmed*.** The two questions — *is this a
person* and *does this person own this address* — were one column, and they are not one fact.

## Options weighed

| Option | Closes | Costs | Verdict |
|---|---|---|---|
| **A. Filter consumers on `verified_via == "email"`** | reset, partly | locks out every coordinator-vouched account with a real, confirmed email | ⛔ **Refuse.** Conflates the two questions this spec exists to separate. |
| **B. New field `email_confirmed_at`, set only by a clicked link** | all five, once consumers use it | one migration; a transition for the 8 | ✅ **Take.** |
| **C. B, plus registration stops writing the address until confirmed** (mirror #169) | all five **and** squatting at registration | changes the registration flow | ✅ **Take — B first, C in the same PR if it stays small.** |
| **D. Grandfather existing accounts as confirmed** | new accounts only | **leaves all 8 exactly as exposed as today** | ⛔ **Refuse.** It makes the measurement above permanent. |

## Recommended design — B, with C if it stays small

### One field

`User.email_confirmed_at = DateTimeField(null=True, blank=True)`

- **Set** only when a person clicks a link sent to that address: `VerifyEmailView` (registration)
  and `ConfirmAddEmailView` (#169).
- **Cleared** whenever `User.email` changes, **in `User.save()`**, not in each view. A rule that
  lives in the model cannot be forgotten by the next view that writes the column.
- **Independent of `verified_at` / `verified_via`.** Confirming an email never touches them except
  where #169 already sets a *first* verification. The vouch record stays exactly as it is.

### One accessor — the whole point

```python
@property
def deliverable_email(self):
    """The address, if and only if its owner has proven they read it. Otherwise None."""
    return self.email if self.email and self.email_confirmed_at else None
```

**Every consumer in the table above reads `deliverable_email`, never `email`.** Five call sites
today. The accessor exists so that the **sixth** — whoever writes it, whenever — cannot trust an
unproven address by accident. **A rule that each call site must remember is not a rule.**

A test enforces it: grep `apps/` for `.email` in any `send_mail` / `EmailMultiAlternatives` /
`recipient_list` / `to=` context and fail if it is not `deliverable_email`. Crude on purpose — the
failure it guards against is someone not knowing the accessor exists.

### Password reset specifically

A custom `PasswordResetForm.get_users()` that additionally requires `email_confirmed_at`.

🔴 **It must answer exactly like success for an unconfirmed address** — same page, same timing, no
mail. Anything else rebuilds the enumeration oracle #171 is about. Stock Django already answers
identically for an address with no account; this extends the same silence to an address that is
not proven.

### Username recovery

Same gate, same silence.

### Registration (option C)

Mirror #169: registration **does not write** the address. It carries it inside the signed
verification token and writes it — with `email_confirmed_at` — when the link is clicked.
`send_verification_email` gains a variant that takes the address explicitly rather than reading
`user.email`, which will be empty. **This also closes squatting at registration**: today anyone can
register with *your* address, and since `email` is `unique=True`, you can then never use it here.

## The transition — the eight real accounts

Gating on `email_confirmed_at` closes the hole **and removes password reset from all eight**, since
none has ever confirmed. That is the real cost, and it lands on real people.

**Recommended:**

1. Ship the field and the accessor, **backfilled NULL for everyone.** Honest: nobody has proven an
   address, so nobody is marked as having proven one.
2. **Send each of the eight a fresh confirmation link** — SMTP has worked since 09-11.
   ⛔ **That is an outbound email to real people and needs its own key.** This spec does not send
   anything.
3. **Until they click:** they can still sign in with their password; they just cannot *reset* it
   by email. The only person actually harmed is one who has **both** forgotten their password
   **and** not clicked — and that person reaches a human through `account-recovery.md` §C/§A4.
4. Show an unconfirmed address plainly on account settings: *"Not confirmed yet — we won't send
   anything here until you click the link we sent. [Resend]"*

⚖️ **The trade, stated so it is chosen and not discovered:** for a short window, eight people lose
self-service reset. In exchange, eight addresses stop being a way to take their accounts. The
recommendation takes that trade; the founder may not, and option D is the named alternative.

## Build notes (for the keyed implementation PR)

- Migration: one nullable `DateTimeField`. **No data migration** — NULL is the correct value for
  every existing row, which is the point.
- Accounts is at `0005_backfill_verified`; this is `0006` unless the recovery-credential table
  from `account-recovery.md` lands first.
- Clearing on change belongs in `User.save()`: compare against the stored row, and clear
  `email_confirmed_at` when the address differs. **Test it through a plain `ModelForm` save**, not
  through a view, because that is how the next caller will reach it.
- 🔴 **Consumer 2 is on the ethics-gate path.** Casework mail to an unproven address is a data-
  protection concern for the sensitive lake. It should be named in `ethics-and-safety.md` rather
  than left only here.
- Tests, and the ones that matter:
  - reset for an unconfirmed address sends nothing **and answers identically** to reset for a
    confirmed one
  - changing `User.email` through **any** path clears `email_confirmed_at`
  - confirming never alters `verified_via` on a coordinator-vouched account
  - the casework digest skips an unconfirmed address and **still creates the in-app notification**
    (the reminder must not be lost, only its email)
  - the crude grep guard fails when a new `send_mail` reads `.email` directly
  - `tests/test_audit_pii_hygiene.py` passes unchanged

## Not this spec

- **Sending the eight their links** — outbound email to real people, separate key.
- **Recovery for someone with no email at all** — `account-recovery.md` §B, the printed code.
- **Registration's "already in use" message** — issue #171. Option C would change the registration
  form anyway; the two should be sequenced so #171's fix is not written twice.

## Done-when

- [ ] `User.email_confirmed_at` exists and is set **only** by a clicked link.
- [ ] Changing the address through any path clears it — enforced in the model.
- [ ] All five consumers read `deliverable_email`; a test fails if a new one reads `.email`.
- [ ] Password reset and username recovery answer identically for an unconfirmed address.
- [ ] No coordinator vouch has been overwritten.
- [ ] The eight existing accounts have either confirmed or been given a working path to — **on the
      founder's key for the send.**
- [ ] Casework follow-up mail to an unproven address is named in `ethics-and-safety.md`.

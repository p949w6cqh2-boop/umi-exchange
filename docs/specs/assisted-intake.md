# Spec: assisted intake — accounts made with a coordinator's help

> STATUS: **SPEC**, written 2026-09-23 on the founder's key. ⛔ **GATED — NOT BUILDABLE YET.**
> Every feature here moves real people's data and the ethics gate reads **3 of 6**
> (`../ethics-and-safety.md`). **Nothing in this spec starts while that is true.**
>
> Companion to `account-recovery.md`, which covers the ungated half. Read that first — it carries
> the shared credential model this spec depends on, and the correction that explains why both
> specs exist now.
>
> 📌 **This spec may be cancelled by a measurement that costs one week and no code.** See
> §The experiment that comes first. Written anyway, because the design should be argued before
> the result arrives rather than improvised after it.

## The question

The pilot parish has a coordinator whose offered job is *"help put people in the system."* The
founder's question: **how does that person make an account for an old parishioner — password and
all?**

Today: **they cannot, and nothing is broken.** `set_password` exists in exactly two places in the
codebase and neither is a view (verified 2026-09-23). The coordinator's real move is to sit beside
the person and let them register on the coordinator's phone, **with their own hands.** Email is
optional, so no address is needed; a coordinator vouch then verifies them without one.

**That path exists, works, and requires zero code.** This spec exists for the case where it is not
enough — where the person cannot operate the form at all, even with someone beside them.

## The experiment that comes first

⛔ **Do not build any of this before running it.**

Seat two or three people under the chair model — their hands, coordinator's phone, no email,
coordinator vouches. **Ask them a week later whether they remember their username.**

- **If they do:** this spec is largely cancelled. What remains is `account-recovery.md` §B (the
  printed code) and the intake timing fix, both already specced and ungated.
- **If they do not:** the failure is *recall*, not *account creation*, and the fix is a printed card
  — still not this spec.
- **Only if the person cannot complete the form at all**, with help, does anything below get built.

**One week, zero PRs, and it decides several.** This ordering is the point: the cheapest experiment
is the one that might delete the expensive work.

## What the record already decided

**1. `../protocol/spec.md §4.1 — "Coordinators MUST NOT consent on a member's behalf."**
Non-negotiable and not reopened here.

**2. `apps/needs/forms.py:14-21` already prescribes the shape:**

> *"If Lake 1 ever needs posting on someone's behalf, it should be built with the same consent
> discipline as casework: a record naming THEM (`consent.subject_person`), and limited display
> until it exists."*

**3. ✅ The consent model already draws §4.1's line in its own schema, and this is the finding that
makes the spec tractable.** `Consent` carries **both**:

| Field | Meaning |
|---|---|
| `participant` / `subject_person` | **who consented** |
| `recorded_by` (Member, `PROTECT`) | **who wrote it down** |
| `method` | `verbal` · `written` · `digital` |

**Recording is not consenting.** A person who says yes out loud, whose coordinator records it with
`participant` = them, `recorded_by` = the coordinator, `method="verbal"`, has consented — and the
coordinator has not consented on their behalf. §4.1 is satisfied by construction.

That distinction is already in the database. This spec's job is to make intake use it correctly and
never collapse the two columns.

**4. Casework already shows the enforcement pattern.** `apps/casework/models.py:79` —
`cw_cf_consent_or_emergency` — is a **database constraint** requiring a consent row **or** an
explicitly named exception (`emergency_opened=True`). Not a view check. Not a form check. A
constraint. **Assisted intake copies this.**

## Options weighed

| Option | What the coordinator does | Verdict |
|---|---|---|
| **A. Chair model — status quo** | hands over the phone, person registers themselves, coordinator vouches | ✅ **Default. Zero code. Try this first and measure it.** |
| **B. Coordinator creates account + printed claim card** | creates a passwordless account; person claims later on their own device | ✅ **The recommendation, if A measurably fails.** |
| **C. Coordinator creates account and sets the password** | knows the person's password | ⛔ **Refuse.** A coordinator who knows a password can act as that person, and the audit log cannot tell the difference. |
| **D. No account at all — coordinator posts on their behalf** | person never has an account | ⚠️ **Deferred, not refused.** This was the standing answer and the capability was removed. Reviving it is a larger change to `Need` and its consent story than B, and it leaves the person unable to see or revoke anything themselves. |

## Recommended design — B, and only after A fails

### The account

- Created by a coordinator with `can_intake` (see `account-recovery.md` §C — **the role split is a
  precondition here too**).
- `user.set_unusable_password()`. **The account cannot be authenticated by anyone, including its
  creator, until claimed.** This is a Django built-in and it is the whole security model.
- Issued a `claim` credential from the shared model in `account-recovery.md` — hashed at rest,
  single-use, 30-day expiry.
- **The username is chosen by the coordinator and printed on the same card as the claim code.** The
  card is then the entire credential and the card must say so in plain words.

🔴 **Decision the founder owns — what an unclaimed account may do. Recommended: nothing.** Not
visible in the community, cannot be vouched, cannot hold a need, cannot receive an offer. **An
unclaimed account is a reservation, not a member.** The alternative — letting a coordinator post a
need for an unclaimed account — is option D wearing B's clothes, and it should be decided as D.

- Unclaimed after expiry → **archive, never delete** (`../../../umi-brain/trust/keyring.md`).

### The consent, and this is the load-bearing part

**Two distinct events. Both stored. Never merged.**

**Event 1 — at intake, in person.** The coordinator reads the consent text aloud; the person says
yes; the coordinator records it:

- `participant` = the new user · `recorded_by` = the coordinator Member · `method = "verbal"`
- `scope` = the minimum the account needs to exist, **not** a blanket grant
- `purpose` = plain words, the same words that were read aloud

⚖️ **This is a real consent under §4.1 — the person consented and the coordinator recorded it.**
It is also, in the founder's own standing terms, **an attestation about an event no one else
witnessed.** Both are true. The design does not need to resolve that, because of event 2.

**Event 2 — at claim, by the person's own hand.** When they claim the account they are shown what
was recorded and confirm it themselves. On confirmation the consent's `method` moves
`verbal → digital`.

**So `method` is the audit trail of how consent was obtained, and a consent still sitting at
`verbal` after claim is a visible, queryable state — not a silent one.**

- `status` already supports `revoked`. The person can revoke. They must be able to see it to
  revoke it, so the claim flow **shows the consent before asking them to confirm it.**

### Enforcement — a constraint, not a check

Mirror `cw_cf_consent_or_emergency`: **an assisted account may not reach any write door without an
active consent row.** Enforce at the database layer, the way casework does. A form check is not
enforcement; the casework constraint exists because somebody already learned that.

⛔ **There is no emergency exception here.** Casework has one because a person in crisis cannot
always consent first. **Account creation is never an emergency** — nobody needs an account at
3 a.m. to survive. Do not copy that half of the pattern.

### Provenance

`AccountProvenance` (specced in the build plan, `method="assisted"`): who created it, denormalized
as text so the record survives the coordinator's own deletion, and **visible to the account holder.**
A record saying *"a coordinator made this account"* that only staff can read is surveillance, not
provenance.

### The consent text itself

⛪ **Not an engineering artifact and it is not drafted here.** What someone agrees to when their
need goes on a parish board touches ministry and pastoral practice, and the founder's standing rule
is that such claims get a priest's read before they ship. **The words come from that conversation,
not from this file.**

## Build notes (for the keyed implementation PRs, after the gate closes)

- Depends on `account-recovery.md`'s credential model (`purpose="claim"`) and on the role split.
- Audit names to reserve: `account.created_assisted` · `account.claimed` ·
  `consent.recorded_verbal` · `consent.confirmed_by_subject`.
  ⚠️ `AuditLog.action` is `varchar(32)` and fails loud rather than truncating — **count the
  characters**; two of those four are close.
- `Consent.recorded_by` is `PROTECT`, so a coordinator Member with recorded consents **cannot be
  deleted.** That is correct and should be stated in the coordinator conversation, not discovered
  during one.
- `Person.linked_user` is a `OneToOneField`. 🔴 **Open question, not decided here:** if the parish
  already has a `Person` row for someone (casework, no account), does assisted intake link the new
  user to it? Linking joins two data worlds with different consent scopes. **Recommended: no link
  in v1**, and say so explicitly rather than leaving it to whoever writes the code.
- Tests: password unusable until claimed · creator cannot authenticate as them · claim is
  single-use · cross-community refused · **the DB constraint rejects a write-door action with no
  active consent** · revoke works · `method` transitions `verbal → digital` on claim and not before
  · provenance survives creator deletion · `tests/test_audit_pii_hygiene.py` passes unchanged.

## Not this spec

- **Posting on someone's behalf without an account** (option D). Larger change, weaker position for
  the subject, and it needs its own consent story. Deferred, not refused.
- **Splitting `is_coordinator`** — precondition, specced separately.
- **The consent text** — pastoral, see above.

## Done-when

- [ ] The chair-model experiment has been run and **failed**, on the record. *(If it succeeded,
      this spec closes unbuilt and that is a good outcome.)*
- [ ] The ethics gate reads 6 of 6.
- [ ] A coordinator can create an account and **cannot log into it**, proven by a test.
- [ ] No coordinator ever knows a member's password.
- [ ] Every assisted account has a consent row naming **the person** as participant and the
      coordinator only as `recorded_by`, enforced by a database constraint.
- [ ] The person has confirmed that consent with their own hand, and can see and revoke it.
- [ ] The account holder can see who created their account.

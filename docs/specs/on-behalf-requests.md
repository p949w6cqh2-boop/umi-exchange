# Spec: requests posted for a neighbor who is not on the board (option D)

> STATUS: **SPEC (DESIGNED), unbuilt**, written 2026-10-01 on the founder's key "7". ⛔ **GATED like
> `assisted-intake.md`:** it moves real people's information, and the ethics gate reads 3 of 6
> (`../ethics-and-safety.md`). Nothing here is switched on for a real neighbor before that reads 6 of 6.
> This is option D of `assisted-intake.md` §Options weighed, which that spec deferred, "not refused".

## Why now

The parish's first coordinator, named 2026-10-01, serves older neighbors who do not use a phone or
computer and will not start. Options A (they register with their own hands) and B (a claim card for
later) both assume the person will someday use a device. **For the people this coordinator serves,
some never will.** Today the board has no way to carry their request: the old on-behalf field was
removed because no screen showed it and the person named could not ask to have it removed
(`apps/needs/forms.py:14-22`).

## What the record already decided (not reopened)

- **"Coordinators MUST NOT consent on a member's behalf"** (`../protocol/spec.md` §4.1). Recording
  what a neighbor said out loud is not consenting for them.
- **The shape is prescribed:** "a record naming THEM (`consent.subject_person`), and limited display
  until it exists" (`apps/needs/forms.py:20-22`).
- **The consent model already supports it:** `Consent.subject_person` (a person with no account),
  `recorded_by` (the witness, never the grantor), `method` `verbal`/`written`
  (`apps/consent/models.py`), with a database constraint that exactly one grantor is named.
- **Enforcement is a database constraint, not a form check**, as casework does with
  `cw_cf_consent_or_emergency`. Unlike casework there is **no emergency exception**: posting a
  request is never an emergency.

## The design

### The records

| Record | What it holds |
|---|---|
| `Person` (existing) | The neighbor. Name encrypted with its own key, so it can be erased (crypto-shred). `created_in_community` = the parish. No account. |
| `Consent` (existing) | `subject_person` = the neighbor · `recorded_by` = the coordinator · `method` = `verbal` or `written` · `scope` = `["board_request"]` · `purpose` = the exact words read aloud. |
| `Need` (two new fields) | `on_behalf_person` and `on_behalf_consent`. A database constraint: one is set only if the other is, and the consent is active, names that person, and carries the scope. **The request itself stores no name.** |

The coordinator is the `requester`: the request is posted BY them FOR the neighbor, so every reply
and every match reaches the coordinator, who carries it to the neighbor in person or by phone.

### Who sees what

| Viewer | Sees |
|---|---|
| The public board and members | The request, "asked for a neighbor by a coordinator". **Never the name.** |
| A neighbor who offers help | Still no name. An accepted match connects them with the coordinator. |
| Coordinators of that parish | The name, because a consent naming the person exists, behind the same 4-hour re-authentication as casework's sensitive pages (`SensitiveSessionMiddleware`). |
| The neighbor | A **printed receipt**: what was recorded, the date, the coordinator's name, and how to withdraw. |

### Seeing and withdrawing without a device

Option D's real weakness (`assisted-intake.md`): the person "cannot see or revoke anything
themselves". The answers, all on paper and in person:

- **The receipt** above, handed over at the moment of consent.
- **Withdrawal through any coordinator or the parish office**, never only the coordinator who
  posted. That keeps the poster from being a gatekeeper, the same reason governance's complaint path
  does not route through the person complained about.
- **Withdrawing hides the request at once and erases the name** (crypto-shred), unless a legal hold
  covers it (`legal-hold.md`), in which case it is hidden and kept, and the steward is told.

### Retention

The name is erased a year after the person's last request closes, the same period as the on-behalf
names it replaces (`NEED_PII_RETENTION_DAYS`). A legal hold on the person, the need, or the parish
pauses that for exactly what it covers.

### Audit

Every post, consent and withdrawal is audited with **ids and scope only, never the name**
(`tests/test_audit_pii_hygiene.py`). Reserved actions, all within `AuditLog.action`'s 32
characters: `need.posted_on_behalf` (21) · `consent.recorded_for_person` (27) ·
`consent.withdrawn_for_person` (28).

## Decisions the founder owns (recommendations in bold)

1. Who may post for someone: **coordinators only in v1**, not intake helpers, whose role is
   deliberately narrow (#188).
2. Whether coordinators of the parish see the name or only initials: **the name, behind
   re-authentication**, because they are the ones who carry help to the door.
3. Verbal or written consent: **either, and the method is stored**, so a parish can require written.
4. The consent words and the receipt's words: **from the conversation with Father and the pastor**,
   with a priest's read before anything ships (standing rule). Not drafted here.

## Honest limits

- **A consent recorded by one coordinator is only as good as that coordinator.** The receipt, the
  withdrawal path that bypasses them, and the activity record make it checkable, not certain.
- **Consent under duress looks like consent** (`../ethics-and-safety.md`). No code fixes that.
- **A coordinator could invent a neighbor.** The build adds `need.posted_on_behalf` to the
  coordinator activity page (#189), so every request posted on behalf shows beside the name of the
  coordinator who posted it, where other coordinators can see it.

## Tests to write with the build

- The database refuses an on-behalf request with no consent, a revoked one, one naming another
  person, or one without the `board_request` scope.
- No public or member page ever renders the person's name (in the style of
  `tests/test_copy_matches_code.py`); an offerer never sees it, before or after a match.
- Only a coordinator of that parish can post on behalf; another parish is refused.
- Withdrawing hides the request and shreds the name; under a legal hold it hides and keeps.
- The retention sweep erases the name a year after the last request closes, and respects holds.
- `tests/test_audit_pii_hygiene.py` passes unchanged.

## Done-when

- [ ] The founder's four decisions above are made and written here.
- [ ] The consent and receipt words come back from the pastoral conversation.
- [ ] Built behind a setting that is off by default, with the tests above.
- [ ] The ethics gate reads 6 of 6 before the first real neighbor's request.

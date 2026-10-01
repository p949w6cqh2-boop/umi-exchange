# Spec: the scoped legal hold (ethics gate box 4's missing half)

> STATUS: **SPEC + BUILD in one PR**, written 2026-10-01 on the founder's key "3". Closes the
> known gap stated in `../incident-response.md` Part 2 and `../ethics-and-safety.md` box 4.

## The gap

Once a legal demand arrives, or a dispute is reasonably foreseeable, routine deletion of anything
relevant must stop. Deleting on schedule after that point can be treated as destroying evidence,
even when it is automatic. Until now the only way to stop it was to stop the whole scheduler, which
also suspended erasure for everyone **not** involved, people who are entitled to it.

## The design

A `LegalHold` row names a **scope**. Every automated deletion path excludes what an active hold
covers, so a sweep stays one query and held records are simply never selected.

| Scope | Covers |
|---|---|
| `case` | one `CaseFile`: its narrative, notes, follow-ups, handoffs |
| `person` | every case whose `subject_person` is them |
| `need` | one `Need`'s on-behalf name |
| `community` | every case and need in that community |
| `all` | every automated deletion in the codebase stops |

| Deletion path | Under a scoped hold | Under `all` |
|---|---|---|
| `shred_aged_cases` (7-year retention) | skips held cases | stops |
| `discard_stale_drafts` | skips drafts in held cases | stops |
| `shred_aged_need_pii` (1-year retention) | skips held needs | stops |
| `shred_on_behalf` (manual erasure) | **refuses** a held need | refuses |
| federation sweeps (shadows, contacts, event payloads) and polling, which deletes shadows a peer withdrew | not scoped in v1 | stop |
| `purge_recovery_credentials --apply` | not scoped | refuses |

- **Placing and releasing go through `manage.py legal_hold`**, by a named staff account, and each
  act is audited (`legal_hold.placed` / `legal_hold.released`) with the **scope only**.
- **The matter reference stays on the hold row and never enters the append-only audit log**, the
  same doctrine as `tests/test_audit_pii_hygiene.py`: free text in an unredactable table is a
  permanent liability.
- **A hold is never deleted.** Releasing stamps `released_at`, and the next sweep proceeds. The
  admin shows holds read-only; it cannot add, edit or delete them.
- **The database refuses a hold whose target does not match its scope** (a check constraint). A
  targetless hold would put a NULL into the hold subqueries, and SQL's `NOT IN (..., NULL)` is never
  true, so one bad row would quietly stop erasure for everyone.

## Honest limits, stated rather than hidden

- **Backups are not scoped.** Nightly dumps age out after 30 days locally (`scripts/backup.sh`)
  and by the B2 lifecycle rule. A dump holds everyone, so it cannot be held per record. **Under any
  hold, the steward pauses backup aging by hand** (stop the prune, suspend the B2 lifecycle rule)
  until a lawyer says otherwise. `incident-response.md` says so.
- **Federation is held only by `all`.** Scoping it to a community is v2, if federation ever runs
  in production.
- **The switch preserves; it does not decide.** Whether a hold is needed, and its scope, is a
  lawyer's call (`incident-response.md` Part 2, ⚖️).

## Using it

```bash
docker exec docker-app-1 python manage.py legal_hold place --scope person --id <uuid> \
    --reference "subpoena served 2026-10-03" --by <steward-username>
docker exec docker-app-1 python manage.py legal_hold list
docker exec docker-app-1 python manage.py legal_hold release <hold-uuid> --by <steward-username>
```

## Tests

`apps/casework/tests/test_legal_hold.py`:
- each scope spares exactly what it covers, and erasure continues for everything else;
- releasing lets the next run proceed;
- `all` stops every path;
- the manual erasure command refuses a held need;
- stale drafts in held cases are kept;
- place, list and release are audited without the reference;
- only staff can place a hold, and scope and target must agree, in the command and in the database;
- the admin can read holds but not change them.

`apps/federation/tests/test_polling.py`: a hold on everything pauses polling and its tombstone
deletes, and releasing it lets them run again.

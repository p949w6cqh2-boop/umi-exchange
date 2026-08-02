# Envelope Encryption — Rollout Runbook

> **STATUS 2026-08-01: rollout COMPLETE on the reference instance** — Stages A–E landed
> (see `STATE.md`). Kept as the runbook for any new deployment walking the same road.

The end-to-end sequence for moving PII from direct-KEK to **envelope** encryption
(per-record DEK wrapped by the KEK list → enables crypto-shred), and the gates that
must pass before each irreversible step. **Do the steps in order. Don't skip a gate.**

Scope of envelope-encrypted PII:
- `needs.Need.on_behalf_of`
- `casework`: `CaseFile.summary`, `CaseNote.body`, `FollowUp.detail`, `WarmHandoff.summary`
- `people.Person`: `display_name`, `contact` (JSON), `dob`

Two ideas that are **separate steps**, a release apart — do not conflate:
- **Stage E (code contract):** delete the legacy `decrypt_str` read branch from the getters; a DEK-less ciphertext then fails loud. No key changes.
- **Old-KEK retirement (ops):** `rotate_keks` re-wraps every DEK under the new primary KEK, then you drop the old key from `ENCRYPTION_KEYS`.

---

## Phase 1 — Deploy the expand (A–D) code

Already on `main`: needs + casework (A–D, PR #3) + Person (A–D, PR #5). Stage A–D is
expand-only and reversible.

- [ ] Deploy the current `main`.
- [ ] Ensure `ENCRYPTION_KEYS` (or legacy `ENCRYPTION_KEY`) **and** `BLIND_INDEX_KEY` (a dedicated secret, distinct from every encryption key) are set in the prod environment. (Production refuses to boot when either is missing or the blind-index key collides — by design.)

## Phase 2 — Migrate (adds DEK columns + backfills)

- [ ] `python manage.py migrate`
  - casework: `0003_envelope_dek_columns` → `0004_envelope_backfill`
  - people: `0002_person_envelope_dek_columns` → `0003_person_envelope_backfill`
- [ ] The `0004`/`0003` backfills are batched, idempotent, and resumable (`atomic = False`) — safe to re-run if interrupted.
- [ ] Reversible if needed: `migrate casework 0002` and `migrate people 0001` roll the backfill + columns back.

## Phase 3 — Verify the census is clean (the Stage E gate)

- [ ] `python manage.py casework_envelope_status` → every field `legacy=0, unreadable=0`
- [ ] `python manage.py people_envelope_status` → every field `legacy=0, unreadable=0`
- [ ] `python manage.py migrate_on_behalf_envelope --verify` → `legacy=0  unreadable=0` (the `needs.on_behalf_of` census; `needs` uses this `--verify` flag rather than a separate `*_status` command). If `legacy>0`, run `migrate_on_behalf_envelope` (no flag) to backfill, then re-verify.

`unreadable > 0` means a row a configured KEK can't decrypt — **stop and investigate**
(wrong/retired key) before going further. Note: casework's case-detail view reads
`Person.display_name`, so a DEK-less Person row would also fail there after Person Stage E —
Person's census must be clean before its contract.

## Phase 4 — Stage E contracts (one release later)

Only after Phase 3 is clean in **production**:

- [ ] casework Stage E — already merged on `main` (PR #4). Deploy it.
- [ ] Person Stage E — to be written once Phase 3 holds; merge + deploy it then.
- [ ] After deploy, re-run both `*_envelope_status` commands — still `legacy=0, unreadable=0`.

## Phase 5 — Old-KEK retirement (the actual key retirement)

Only after **all** PII is envelope-only (Phases 2–4 complete for needs + casework + Person):

- [ ] Add the new KEK as primary, keep the old one for unwrap:
      `ENCRYPTION_KEYS = [<new_key>, <old_key>]`
- [ ] `python manage.py rotate_keks` — re-wraps every envelope DEK under the new primary. (Covers all registered fields: needs, casework, Person.)
- [ ] Verify **all three** censuses still report `legacy=0, unreadable=0`: `casework_envelope_status`, `people_envelope_status`, and `migrate_on_behalf_envelope --verify` (needs). All PII — needs + casework + Person — must be envelope-only, or dropping the old KEK makes a legacy row unreadable.
- [ ] Drop the old key: `ENCRYPTION_KEYS = [<new_key>]`. Old KEK is retired.

---

## Rollback notes

- **Stage A–D:** `migrate <app> <prev>` reverses columns + backfill (reverse re-encrypts envelope → direct-KEK).
- **A Stage E contract:** straight PR revert restores dual-read; pair with `migrate <app> <prev>` only if you also need the data reverted.
- **Crypto-shred a record:** delete its `*_enc_dek` value → the ciphertext is permanently opaque even with the KEK.

## Quick reference

| Command | Purpose |
|---|---|
| `migrate` | apply DEK columns + backfill |
| `casework_envelope_status` / `people_envelope_status` | census: empty / legacy / envelope / unreadable per field |
| `migrate_on_behalf_envelope --verify` | the same census for `needs.on_behalf_of` (needs uses this flag, not a `*_status` command); `migrate_on_behalf_envelope` (no flag) backfills it |
| `rotate_keks` | re-wrap all DEKs under the new primary KEK |

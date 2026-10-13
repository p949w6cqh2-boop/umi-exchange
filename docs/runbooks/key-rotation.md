# Runbook — KEK rotation & data retention

How to rotate the master key (KEK) with **no downtime**, and the **actual** data-retention model.

> This runbook **extends** [`../envelope-rollout-runbook.md`](../envelope-rollout-runbook.md). The
> step-by-step rotation lives there as **Phase 5 — Old-KEK retirement** (don't duplicate it); this page
> explains *why it's zero-downtime* and *what retention really means*. Rotation is only safe once **all**
> PII is envelope-only (runbook Phases 2–4 complete for needs + casework + Person).

## No-downtime rotation — why it works

Field crypto uses **`MultiFernet`** over the ordered `ENCRYPTION_KEYS` list (`apps/people/crypto.py`):

- **Decrypt** succeeds with **any** key in the list.
- **Encrypt/re-wrap** always uses the **first** (primary) key.

So adding the new key as primary while keeping the old one creates an automatic **dual-read window** —
the app keeps serving throughout, because every existing DEK (wrapped under the old KEK) still decrypts,
while new writes use the new KEK. The sequence (full detail = runbook Phase 5):

1. `ENCRYPTION_KEYS = [<new>, <old>]` — new primary, old retained for unwrap. **← dual-read window opens.**
2. `python manage.py rotate_keks` — re-wraps **every** envelope DEK under the new primary (all registered
   fields: needs, casework, federation, Person). Batched/idempotent — safe to re-run. If it **ends with an
   error listing rows** (`app.Model.field <pk>`), no configured key opens those rows' DEKs (a row restored
   from an old dump, for instance). Every other row was re-wrapped. Keep the old KEK and find the key that
   opens them, or erase them, before step 4.
3. Verify all three censuses are clean (`casework_envelope_status`, `people_envelope_status`,
   `migrate_on_behalf_envelope --verify`): `legacy=0, unreadable=0`.
4. `ENCRYPTION_KEYS = [<new>]` — drop the old key. **← window closes; old KEK retired.**

**Do not drop the old key until step 3 is clean** — a DEK still wrapped under the old KEK becomes
permanently unreadable. The KEK is read from the environment only (`ENCRYPTION_KEYS` / legacy
`ENCRYPTION_KEY`); it is **never** written to the database, logs, or git.

## Retention model — the real one

Two mechanisms, deliberately different:

- **Append-only audit (kept).** `AuditLog` is immutable (model-level + Postgres `REVOKE` of
  `UPDATE/DELETE`) and **contains no PII** — dotted actions ≤32 chars, salted-SHA-256 IP hashes, ids
  only. It is retained as the accountability trail; there is nothing in it to erase.
- **PII erasure = crypto-shred.** To honour an erasure request, run **`python manage.py shred_person
  --person <uuid>`** for a casework subject, or **`shred_on_behalf --need <uuid>`** for the name on one
  need. Each nulls the per-record DEK *and* its ciphertext together, so the content is gone from the live
  database and unrecoverable *even with the KEK*, and `shred_person` also clears the name's blind index
  and shreds every case about the person. Both refuse under a legal hold, and `shred_person` refuses while a case about the
  person is still open (close it in the app first). This is how §5.8 erasure is actually delivered.
  **Never delete a `*_enc_dek` by hand** (corrected 2026-10-13): a ciphertext left without its DEK fails
  loud on every read (the case page returns a 500), and the blind index left behind keeps the erased name
  equality-testable.

### Erasure is not complete until backups age out

Crypto-shred deletes the DEK in the **live** database. A backup taken **before** the shred still contains
that wrapped DEK + ciphertext, and the KEK still exists in the environment — so restoring that backup
would resurrect the erased data. **Therefore an erasure is only fully complete once every backup
predating the shred has aged out** — locally after `RETENTION_DAYS` and remotely via the B2 lifecycle
rule (see `scripts/backup.sh`'s retention note). State this honestly to communities; don't promise
instantaneous §5.8 erasure while pre-shred backups still exist.

## Quick reference

| Action | Command / note |
|---|---|
| Open dual-read window | `ENCRYPTION_KEYS=[<new>,<old>]` (env only) |
| Re-wrap all DEKs | `python manage.py rotate_keks` |
| Confirm clean | `casework_envelope_status` · `people_envelope_status` · `migrate_on_behalf_envelope --verify` |
| Retire old KEK | `ENCRYPTION_KEYS=[<new>]` |
| Erase one person's PII | `python manage.py shred_person --person <uuid>` (crypto-shred) + wait out pre-shred backups |

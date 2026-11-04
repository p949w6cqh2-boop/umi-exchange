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
permanently unreadable. The KEK reaches the app from a read-only file on tmpfs (`UMI_SECRETS_FILE`,
since 2026-11-02); it is **never** written to the database, logs, or git.

## On this deployment: through the key rig

Each `ENCRYPTION_KEYS = ...` line above is one `encrypt` and one `deploy` of
`scripts/deploy-with-keys.sh`, from the steward's laptop. Every `deploy` recreates the app and the
worker, a few seconds of downtime, and leaves the database and Redis alone.

What each key costs to change:

| Key | What changing it does |
|---|---|
| `SECRET_KEY` | Signs everyone out (sessions last 24 hours anyway, `SESSION_COOKIE_AGE`). Kills reset and email-confirm links in flight (48 hours, `EMAIL_TOKEN_MAX_AGE`). Makes every browser unknown to the login throttle until its next sign-in. Drops any background job queued at that moment, because django-q signs its payloads with it. Audit IP hashes before and after can no longer be compared; nothing reads them across time. |
| `BLIND_INDEX_KEY` | Free only while `people.Person` is empty: `name_bidx` is keyed by it and it is not rotatable without re-indexing (`docs/deployment-checklist.md`). With real rows, leave it alone. |
| `ENCRYPTION_KEYS` | The dual-read sequence above. Nothing is signed out. |

The sequence:

1. **Look first, on the droplet.** `bright_line`, `rotate_keks --dry-run`, the three censuses, and
   how many jobs are queued. Take a fresh backup (`scripts/backup.sh`), which keeps the
   pre-rotation key file beside the dump.
2. **Stage on the laptop's tmpfs** (`/run/user/$(id -u)`), never in the repo and never printed:
   `ENCRYPTION_KEYS=<new>,<old>`, plus any other key being replaced.
3. **`encrypt`, then `deploy`.** `encrypt` proves the new file opens and keeps the previous one as
   `keys.env.age.<stamp>`.
4. **Confirm the app loaded the list, then re-wrap.** `rotate_keks --dry-run`, `rotate_keks`, the
   three censuses.
5. **Stage `<new>` alone, `encrypt`, `deploy`.** Confirm the app loaded one key and `/health/` is 200.
6. **Shred the staging file.**
7. **Keep the archived `keys.env.age.<stamp>` files** until the last backup taken before the rotation
   has aged out (`RETENTION_DAYS`, 30).
8. **Replace the key file in the sealed envelope** (`docs/envelope-instructions.md`). The identity
   has not changed, but the key file has, and a stale envelope is only discovered on the night it
   is needed.

A power cut on the laptop at any point is recoverable. The ciphertext is replaced atomically, so
after a reboot `deploy` runs again from whichever step the ciphertext has reached, and the staging
file can be rebuilt from it.

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

# Key custody design — separating the keys from the box

> STATUS: DESIGN, written 2026-08-11 for ethics-gate item "Key custody is separated from
> root and is not all held by one person." Not yet implemented; the box stays unchecked
> until the design below is real and rehearsed. Written for the pilot-parish timeline
> (parish board meeting Sept 15). Companion: `docs/governance.md`.
>
> The gate's own words: done when the key-encryption key no longer sits in a plaintext file
> beside the database under the same root account, so that compromising the host alone does
> not hand over the key, and when at least two distinct roles are required to reach it.

## Today, honestly

`ENCRYPTION_KEYS`, `BLIND_INDEX_KEY`, and `SECRET_KEY` live in a plaintext `.env` on the
same droplet as the PostgreSQL data they protect, readable by the same root account, held
by one person. Whoever gets the machine gets both the lock and the key. That is exactly
what the gate item says must end before real parishioners onboard.

## The design (v1 — smallest thing that honestly meets the words)

Three changes, in order:

1. **Keys encrypted at rest everywhere.** The live key material moves into an
   age-encrypted file (`secrets/keys.env.age`, sops-style single file). The droplet at
   rest holds only ciphertext. The repository never holds keys in any form; backups (B2)
   carry only ciphertext alongside the database dumps they already carry.

2. **Decrypt-at-deploy, from a different machine.** The age *identity* (private key) lives
   on the steward's laptop — never on the droplet. Deploys and restarts run a small wrapper
   from the laptop that decrypts the keys over SSH straight into the container environment.
   Compromising the droplet alone now yields ciphertext, not keys.

3. **Second role: the parish holds break-glass.** A sealed envelope goes into the parish
   office safe containing: a printed copy of the age identity, one page of plain-English
   instructions, and the succession note from `docs/governance.md`. Opening the envelope is
   a two-person act (pastor + one named trustee), is logged, and triggers immediate key
   rotation (`manage.py rotate_keks`) once a new steward is in place. Reaching the keys now
   requires either the steward's laptop OR two named parish people at the safe — at least
   two distinct roles, neither of which is "whoever roots the droplet."

## Named residuals (accepted, not hidden — the gate deserves honesty)

- **Process memory.** A running app must hold the KEK in memory. Full host compromise
  while the app is running can read process memory. No single-box design removes this;
  what the design removes is the at-rest plaintext and the survives-a-reboot copy.
- **Docker metadata.** Environment injected into a container is written by Docker into its
  container-config JSON on disk. v1 mitigates by injecting via an env-file on a tmpfs mount
  consumed at `up` time, but a residue in container metadata is possible depending on the
  compose path chosen at implementation. The implementation PR must state which path it
  took and what a root attacker can still read. If the residue cannot be closed, the honest
  fallback is a small secrets sidecar or a managed secret store — which changes the
  cost/subsidiarity math and is the steward's call, documented here when made.
- **Availability coupling.** The droplet can no longer restart the app unattended after a
  reboot; the steward's laptop (or the safe) is needed. For a parish notice-board this is
  an acceptable trade: hours of downtime are annoying; a silent key theft is a betrayal.
  The uptime monitor (monitoring runbook) makes the downtime loud.

## What implementation looks like (separate keyed PR, not this document)

- `scripts/deploy-with-keys.sh` (laptop side): age-decrypt → ssh → inject → `up -d` →
  shred local plaintext; refuses to run if the plaintext file would touch droplet disk.
- Remove key lines from the droplet `.env` (leaving non-secret config); add
  `secrets/keys.env.age`; document rotation: new KEK prepended to `ENCRYPTION_KEYS`,
  `rotate_keks`, retire old.
- A rehearsal (the restore-test pattern): decrypt-deploy once on a scratch box, then once
  on the droplet at a quiet hour; screenshots + date recorded here.
- Envelope prepared, sealed, dated, signed across the seal; placed in the safe with the
  pastor's knowledge; its existence recorded in `docs/governance.md`.

## Done-when checklist (tick the gate box only when ALL are true)

- [ ] No plaintext key material at rest on the droplet (verified by inspection).
- [ ] Deploy-from-laptop rehearsed on the real droplet.
- [ ] Sealed envelope in the parish safe; two named people know it exists and what it is.
- [ ] Rotation rehearsed once end-to-end after the change.
- [ ] Residuals section above updated to describe what was actually built.

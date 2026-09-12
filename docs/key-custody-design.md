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

## ✅ Third entry, 2026-09-11 (same night, after the fixes) — **THE RIG NOW WORKS, AND THE AVAILABILITY RESIDUAL IS DISPROVED**

Both defects below are fixed, and the rehearsal was re-run end to end against production.

**Proven, in this order, on the live droplet:**

1. Age identity generated on the steward's laptop, mode `600`, recipients file verified to match.
2. Key material encrypted; **round-trip decrypt compared byte-for-byte against the original**.
3. Key lines removed from the droplet `.env` (backup taken first).
4. `deploy` run from the laptop → keys decrypt locally, travel an ssh pipe into `/dev/shm`, merge
   with the key-free `.env`, container **force-recreated**, tmpfs shredded.
5. Site returned **200 on apex and `www`**, `/health/` reporting `db: ok, cache: ok`.
6. `check` clean · `.env` key lines **0** · `/dev/shm` **empty** · and the running container holds
   all three keys (87 / 45 / 45 bytes). **The keys exist only in container memory and in
   `keys.env.age` on the laptop.**

### ⭐ The availability residual is FALSE — corrected, not softened

§Named residuals says: *"The droplet can no longer restart the app unattended after a reboot; the
steward's laptop (or the safe) is needed."*

**Tested by rebooting production.** `uptime` returned `0 minutes`, all four containers came back
**unattended**, the app was healthy in ~30 seconds with **all three keys present**, and `.env` still
held none. Apex and `www` both 200.

**Why the design was wrong:** Docker stores a container's environment in its config and replays it
on restart. `restart: unless-stopped` therefore brings the app back with its keys intact from a disk
that holds none. Nobody had tested it.

📌 **The real limit, which is narrower and much better: keys survive RESTARTS, not RECREATES.** Any
`up -d` that rebuilds the container — a new image, a compose change, `--force-recreate` — needs the
steward's laptop. **That is a deploy-time dependency, not an uptime one.** The unattended 02:00
security-upgrade reboot is safe.

### Box 3 after tonight

- [x] No plaintext key material at rest on the droplet — `check` clean, `.env` = 0
- [x] **Deploy-from-laptop rehearsed on the real droplet**
- [x] Survives an unattended reboot — residual disproved by test
- [ ] **Sealed envelope in the parish safe; two named people know it exists** — needs the conversation
- [ ] Rotation rehearsed once end-to-end

🔴 **Until the envelope exists, the age identity is the ONLY copy of the keys, on one laptop.** That
costs nothing today — every table requiring them is empty — and it stops being true the moment real
casework lands. **No real parishioner data goes behind this key before the envelope is in the safe.**

---

## 🔴🔴 Second correction, 2026-09-11 (later the same night) — the rig does not merely sit unarmed, **IT HAS NEVER WORKED**

> ✅ **Both defects below are now FIXED** — see the entry above. This section is kept as the record
> of what was found and how, because the *reason* no test caught them is the durable lesson.

The correction below said the rig was built and never switched on. **Attempting to switch it on,
against the rebuilt production droplet, found two independent defects — either one fatal.** The
rehearsal did exactly the job a rehearsal exists for.

### Defect 1 — the decrypted keys are thrown away

`scripts/deploy-with-keys.sh`, the final line of `cmd_deploy`:

```bash
age -d -i "$IDENTITY" "$KEYS_AGE" | ssh "$DROPLET" "bash -s" <<< "$remote_script"
```

**The pipe and the here-string both claim ssh's stdin, and the here-string wins.** So `bash -s`
reads the *script* from stdin; the script's own first line, `cat > /dev/shm/umi-keys.env`, then
reads from that same, already-exhausted stream. **The plaintext from `age` is discarded entirely.**

Observed: the deploy failed with the script's own catch-all, `deploy failed — plaintext was confined
to the pipe and tmpfs`, which is true and says nothing about why.

**A working form** — pass the script as an argument so stdin stays free for the data:

```bash
age -d -i "$IDENTITY" "$KEYS_AGE" | ssh "$DROPLET" "bash -c $(printf '%q' "$remote_script")"
```

Proved in place: with this form the keys arrive, the merge happens, and the container recreates.

### Defect 2 — `--env-file` does not put anything in the container

This one survives fixing defect 1, and it is the design-level error.

```bash
docker compose --env-file /dev/shm/umi-full.env -f docker/docker-compose.prod.yml up -d app
```

**`--env-file` supplies variables for compose's own `${VAR}` substitution in the YAML. It does not
inject them into the container.** The app service takes its environment from `env_file: ../.env`,
and `docker/docker-compose.prod.yml` names only `DJANGO_SETTINGS_MODULE`, `DATABASE_URL` and
`REDIS_URL` in its `environment:` block — **`SECRET_KEY`, `ENCRYPTION_KEY` and `BLIND_INDEX_KEY` are
not there.**

So once the key lines are removed from `.env` — which the rig requires, and checks for — the app has
no keys at all. Observed, with the site 502 for about three minutes:

```
django.core.exceptions.ImproperlyConfigured: SECRET_KEY must be set to a unique
secret value in production; the insecure development default is not allowed.
```

Recovered from a `.env` backup taken before the migration. **Take that backup; it is the difference
between a three-minute outage and a night of one.**

**The fix this needs (NOT applied — it is a code change and wants tests):** add the three key names
to the app service's `environment:` block as `${SECRET_KEY}` etc., so the `--env-file` merge
actually reaches the container. Then re-run the rehearsal.

### Why no test caught either

`tests/test_deploy_with_keys.py` has eight tests. They cover `encrypt` round-trip, the refusals
(missing identity, missing ciphertext, missing recipients), `check` in both directions — and
`test_deploy_dry_run_plan_keeps_plaintext_in_tmpfs_and_shreds`, which asserts on **the text of the
dry-run plan.** ⚠️ **Nothing in the suite ever executes a deploy.** The plan string was correct;
the code that runs it was not, and the code that runs it is the whole rig.

📌 **The sharpened lesson, and it is narrower than "built ≠ armed": A DRY RUN THAT PRINTS THE RIGHT
PLAN IS EVIDENCE ABOUT THE PLAN, NOT ABOUT THE EXECUTION.** Both defects live in the two lines the
dry run deliberately skips.

### What the rehearsal DID close

- ✅ Age identity generated on the steward's laptop, mode `600`, recipients file verified to match.
- ✅ Key material encrypted to `~/.config/umi/keys.env.age`, **round-trip proven byte-for-byte**.
- ✅ `deploy-with-keys.sh check` confirmed clean against a droplet `.env` with the key lines removed.
- ❌ **Deploy-from-laptop is still owed.** It was attempted, and it failed.

⚠️ Also found: `UMI_DROPLET` still defaults to `root@143.244.167.7` — **a destroyed droplet whose IP
has returned to DigitalOcean's pool.** Every invocation must set it explicitly until that is fixed.

---

## 🔴 Status correction 2026-09-11 — BUILT, but never ARMED

Found while recovering from `docs/incidents/2026-09-05-droplet-destroyed.md`. On the steward's
laptop, **`~/.config/umi/` does not exist** — no `age-identity.txt`, no `age-recipients.txt`, and
no `keys.env.age` ciphertext anywhere on the machine. `age` and `age-keygen` are installed;
`scripts/deploy-with-keys.sh` has exactly one commit, the #147 build, and was never run.

**So the production droplet ran the pre-custody way — plaintext keys in `.env` — from #147 until it
was destroyed.** Every protection described above was designed, merged, tested in isolation, and
never switched on. The unticked checklist line *"Deploy-from-laptop rehearsed on the real droplet"*
was the only honest signal, and it was easy to read as a formality rather than as **the rig is off**.

📌 **Lesson, and it generalises past this rig: a merged implementation is not a live control.**
Between BUILT and ARMED there is a step that only a person can take, and nothing in this repo could
tell the difference. Where a control matters, its *armed* state needs a check that fails loudly —
not a checkbox in a design doc.

**No data was lost to this.** Every table requiring `ENCRYPTION_KEYS` was empty; see the incident.

⭐ **The rebuild is the owed rehearsal, and it is the cheapest one that will ever be available** —
a fresh host with nothing on it to lose. Generate the identity, encrypt the keys, deploy from the
laptop, and tick the rehearsal line for real.

## Implementation (BUILT 2026-08-12, keyed; rehearsal still owed)

- **`scripts/deploy-with-keys.sh` exists** (tests: `tests/test_deploy_with_keys.py`,
  skipped where `age` is absent). Three modes:
  - `encrypt <plaintext-env-file>` → age-encrypts to `$UMI_KEYS_AGE`
    (default `~/.config/umi/keys.env.age` — **outside the repo**; `secrets/` is
    gitignored as a brief staging spot). Refuses without a recipients file; tells the
    steward to shred the plaintext.
  - `deploy` → age-decrypts on the laptop and pipes STRAIGHT over ssh into droplet
    tmpfs (`/dev/shm`, `umask 077`, no scp, no laptop temp file), refuses if the droplet
    `.env` still carries plaintext key lines, merges tmpfs keys + key-free `.env` into
    `/dev/shm/umi-full.env`, runs the runbook's exact compose invocation from it, then
    shreds both tmpfs files. `DRY_RUN=1` prints the full remote plan without connecting.
  - `check` → proves the droplet `.env` (or `--local-file <f>`) holds no
    `ENCRYPTION_KEYS` / `BLIND_INDEX_KEY` / `SECRET_KEY` lines.
- **Path chosen for the container residue (the design's named question):** env-file merge
  in tmpfs, consumed at `up`. What a root attacker can still read: Docker writes the
  container's resolved environment into its container-config JSON
  (`/var/lib/docker/containers/<id>/config.v2.json`) for the LIFETIME OF THE CONTAINER —
  that residue is real and stays. It disappears only on container removal; it is not an
  at-rest survives-redeploy plaintext file, but a rooted host while the app exists can
  read the keys there (as it could read process memory). Closing it fully = a secrets
  sidecar / managed store — still deferred, still the steward's call, per the residuals
  section above.
- **Migration steps on the droplet (steward's hand, at the rehearsal):** compose the key
  lines into a scratch file → `encrypt` it → remove those lines from `/opt/umi-exchange/.env`
  → `deploy` → `check`. Rotation unchanged: new KEK prepended to `ENCRYPTION_KEYS` in the
  plaintext staging file, re-`encrypt`, `deploy`, `manage.py rotate_keks`, retire old.
- **Still owed before the gate box ticks (unchanged):** the rehearsal (scratch box, then
  droplet at a quiet hour, screenshots + date recorded here) and the sealed envelope in
  the parish safe (printed identity + plain-English instructions), recorded in
  `docs/governance.md`.

## Done-when checklist (tick the gate box only when ALL are true)

- [ ] No plaintext key material at rest on the droplet (verified by inspection).
- [ ] Deploy-from-laptop rehearsed on the real droplet.
- [ ] Sealed envelope in the parish safe; two named people know it exists and what it is.
- [ ] Rotation rehearsed once end-to-end after the change.
- [ ] Residuals section above updated to describe what was actually built.

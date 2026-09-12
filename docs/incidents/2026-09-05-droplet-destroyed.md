# Incident — the production droplet was destroyed, and nobody was told

> **Severity: total loss of the production host.** No parishioner harm: **casework held nothing at
> all** — `people_person`, `households_household`, every `casework_*` and every `federation_*` table
> was empty, verified by row count. No narrative, need, household or identity has ever been stored.
> This is a rebuild, not a betrayal.
>
> 🔴 **CORRECTION 2026-09-11, hours after this file was merged — recorded rather than quietly
> edited.** The original version of these three lines read: *"No parishioner harm: the board served
> **fictional demo data only**, which is exactly what the `docs/ethics-and-safety.md` bright line
> exists to guarantee. That line held."* **The last two sentences were wrong.** Reading the live
> `accounts_user` table during the rebuild showed roughly **seven real, working email addresses**
> among 22 rows — several the steward's own, at least three apparently other people's, and one with
> the shape of an automated signup. Account email is plaintext by design, so those were plaintext in
> the destroyed database and are plaintext in the restored one. **The bright line had already been
> crossed before this incident, and nobody had noticed.** See `docs/ethics-and-safety.md` Part 4.
>
> ⚖️ **It does not change this incident's severity** — an email address is not a casework note, and
> the disk was destroyed by the provider, not exfiltrated. **It does change what this document is
> allowed to claim**, and the agent that wrote it asserted "fictional demo data only" from the
> standing docs without ever querying the table. 📌 **An inherited claim repeated into an incident
> report is not a verified one.**
>
> Written 2026-09-11, during the recovery, from live evidence rather than memory.

## Timeline

| when | what | how we know |
|---|---|---|
| 2026-09-03 03:00 UTC | last successful nightly backup → B2 | object `umi-20260903-030001.sql.gz`, verified |
| 2026-09-03 | droplet **powered off** | DigitalOcean activity log ("8 days ago") — ATTESTED, panel read by the founder |
| 2026-09-05 | droplet **destroyed** | same activity log ("6 days ago") — ATTESTED |
| 2026-09-11 | outage discovered, by hand, while doing unrelated SMTP work | this session |

**Silent window: 8 days.** Not 3 — the founder's first estimate was 3, and the activity log
corrects it. Recorded as 8 because the log is the artifact and the recollection is not.

**Cause: a billing failure.** DigitalOcean powered the droplet off, then destroyed it on the
usual suspension schedule. ATTESTED (unverified): the founder reports the payment problem; the
destruction itself is visible in the panel.

## Why no human was told, which is the actual finding

`docs/monitoring-runbook.md` lists six steps. **Steps 2 and 4 are the only two never marked done:**

> **2. Install the UptimeRobot mobile app** — push notification is the "reaches a human within
> minutes" channel; **email alone can sit unread.** ← the channel that bypasses the broken email path
> **4. Alert contacts:** mobile push + email, both attached to the monitor.

Push was never configured. The monitor almost certainly fired into an inbox — the same inbox the
DigitalOcean billing warnings went to. **Two independent warning systems, one unwatched channel.**

🔴 **This is the second time this class of failure has happened, and box 1 already documents the
first.** In the 30 days before 2026-08-18: *84.416% uptime, 4 incidents, 4d 19h 56m down, not one
reached a human*, because the e-mail notification channel was switched off on the monitor.

**The difference matters.** Failure #1 was *alerting disabled*. Failure #2 is *alerting enabled and
not watched*. **The gate box cannot tell them apart**, because its proof — a 6-minute deliberate
trip test — is watched by definition. A test you are standing over cannot measure whether an alert
reaches you when you are not.

## What was lost, and what was not

**Lost:** the droplet, its disk, its `.env` (including `SECRET_KEY`, `ENCRYPTION_KEYS`,
`BLIND_INDEX_KEY` in plaintext), and 8 days of uptime.

**Not lost, all verified in this session:**

- **Every backup.** 23 nightly dumps, 08-12 → 09-03, unbroken, pulled from B2 and checked with
  `gzip -t`: **23 intact, 0 corrupt.** Newest restores to 5 communities, 16 members, 22 users,
  7 needs, 6 offers, 3 matches, schema current at migration 106.
- **All code and docs** — GitHub, untouched.
- **The whole mail configuration** — SPF, DKIM, MX, DMARC all still live in DNS.

**The encryption key is not a loss.** Every table whose columns require it is empty in the dump:
`people_person` 0, `households_household` 0, `casework_*` 0, `federation_*` 0. The board's real
content — community names, member display names, need titles and descriptions — is plaintext by
design (`docs/ethics-and-safety.md`) and restores without any key.

## Finding: the custody rig was built but never armed

`scripts/deploy-with-keys.sh` expects an age identity at `~/.config/umi/age-identity.txt`.
On the steward's laptop **that directory does not exist** — no identity, no recipients file, and no
`keys.env.age` ciphertext anywhere. `age` and `age-keygen` are installed; the rig was never run.
The script has exactly one commit, the #147 build.

**So the droplet was running the pre-custody way — plaintext keys in `.env` — right up to its
destruction.** Nothing was lost that the rig would have protected, because the rig was never on.
This matches `docs/key-custody-design.md`'s own unticked checklist item: *"Deploy-from-laptop
rehearsed on the real droplet."*

📌 **The rebuild is that owed rehearsal.** Fresh secrets, the rig armed, deploy-from-laptop done
once for real — on a host with nothing to lose. This is the cheapest moment this will ever have.

## A second exposure, found and closed during recovery

`reciprocalaid.network` continued to resolve to **143.244.167.7** for six days after the droplet
was destroyed. `whois` confirms that address returned to DigitalOcean's pool for reassignment to
another customer — who would then have received traffic for this domain.

**Closed 2026-09-11:** apex and `www` A records deleted; verified against the authoritative
nameserver (`dig @ns11.domaincontrol.com` returns empty). The `www` CNAME to the apex was
deliberately kept — it is correct config and follows automatically when a new A record is added.

⚠️ **Destroying a host is not finished until its DNS is repointed.** Nothing in the runbooks said
so before this incident.

## Corrective actions

| # | action | state |
|---|---|---|
| 1 | Pull every surviving backup off B2 before the lifecycle rule expires it | ✅ done — 23 files, `~/umi-backup-rescue/` |
| 2 | Delete stale A records | ✅ done, verified authoritative |
| 3 | **Untick ethics-gate box 1** — it asserts a property that just failed for 8 days | this PR |
| 4 | Add a *push* alert channel, and re-prove it with the founder not watching | ⬜ founder-hand |
| 5 | Rebuild the droplet per `docs/deploy/vps-runbook.md`, restore `umi-20260903` | ⬜ |
| 6 | Arm the custody rig during the rebuild; tick box 3's rehearsal line | ⬜ |
| 7 | Get the rescue copy onto a second physical location | ⬜ founder-hand |
| 8 | Fix the aws-CLI install docs — they assume Ubuntu/snap; the steward's laptop is Linux Mint, where snapd is blocked by policy | this PR |
| 9 | Fix the wrong default B2 region in `backup.sh`, `dr_sim.sh`, `project_map.txt` and `.env.example` | this PR |

### Finding 9, because it was about to bite the rebuild

`backup.sh`, `dr_sim.sh`, `docs/project_map.txt` **and `.env.example`** all carried
`https://s3.us-west-001.backblazeb2.com` as the default or example B2 endpoint. **The real bucket
is in `us-east-005`.** `.env.example` is the worst of the four, because it is the file a rebuild
copies from — and a rebuild is exactly what happens next. This never broke anything because the droplet's `.env` set `BACKUP_ENDPOINT`
explicitly and overrode the default — and **that `.env` died with the droplet.** The next person to
build a `.env` from the documented example would have got a silently non-uploading backup, or a
hard failure under `BACKUP_REQUIRE_REMOTE=1`, on a fresh host with no backup history to notice it
against.

Corrected to `us-east-005` in all three places, with a comment saying the region must match the
bucket. ⚠️ **The deeper smell is left standing and named: a backup script should refuse to guess a
region rather than substitute a different guess.** Making it fail loudly is a behaviour change with
tests attached and does not belong in an incident PR.

## What box 1 must require before it is ticked again

The current wording asks for an alert to **arrive**. That is not enough, and this incident is the
proof. It must also require that the alert **reaches a human who is not expecting it**:

- a channel that interrupts — push or SMS, not email alone;
- a trip test the founder does **not** schedule or watch for;
- and a periodic liveness check on the monitor itself, because a monitor that stops monitoring
  looks exactly like a service that never breaks.

**Detection working with alerting unwatched is worse than no monitoring, because it produces
confidence without coverage.** Box 1 has now taught that lesson twice.

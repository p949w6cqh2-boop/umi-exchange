# Incident — the server was switched off for a day and a half, and the keys came back by hand

> **Severity: the board was down for 34 hours 46 minutes. Nothing was lost from the disk, and
> there is no sign anything was exposed.** Same machine, same database, every volume present. One
> nightly backup is missing (2026-11-09), because the server was off when it was due.
>
> Written 2026-11-10 from the server's own journal and logs, the uptime monitor's API, and the
> steward's session log with the agent (which is not in this repository). Where a line rests on the
> steward's word and not on an artifact, it says ATTESTED.

## Timeline

All times UTC. Eastern is five hours behind.

| when | what | how we know |
|---|---|---|
| 11-08 03:00 | last nightly backup before the outage: complete, heartbeat sent | `/var/log/umi-backup.log` |
| 11-08 10:18:26 | server **shut down**, cleanly, by nobody here | `last -x` on the droplet |
| 11-08 ~10:23 | uptime monitor reads DOWN | UptimeRobot API, read 11-09 05:19: "DOWN, 18 h 56 min" |
| 11-08 20:33 | the outage **first enters the record**, raised by the agent about ten hours in, at the start of unrelated work | session log |
| 11-09 03:00 | the nightly backup **does not run** | no log line and no file for that night |
| 11-09 05:22 | steward: the hosting bill is overdue, and his health check and the backup alert had told him | ATTESTED, his words. When they told him was not asked then. It was asked on 11-12: see the last row |
| 11-09 20:59 | steward: the bill is paid | ATTESTED. No agent saw the provider's console |
| 11-09 21:01:19 | server **boots**, with nothing done from this side | `last -x`, `uptime -s` |
| 11-09 21:01:43 | Docker tries the app and the worker **once each**. Both fail on the key mount | Docker's journal: 2 `failed to start container`, none after |
| 11-09 21:04:37 → 21:05:01 | the key rig runs from the steward's laptop, exit 0 | the rig's output |
| 11-09 21:04:42 | the app starts. Site, `/health/` and login answer 200 | `docker inspect`, `curl` with a 404 control |
| 11-09 ~21:11 | monitor reads UP | UptimeRobot API |
| 11-10 03:00 | first nightly backup after: dump uploaded and verified, then **killed** at the key-file check. No heartbeat | backup log: `Terminated` |
| 11-10 03:33 → 03:44 | backups re-run by hand. Three complete, each with a heartbeat | backup log |
| 11-10 03:37 | `loginctl enable-linger root` | the linger file's timestamp |
| 11-12 ~01:16 | steward, asked for the first time: the alert reached his phone "at 5 am" (Eastern) on 11-08 and he was asleep. It was a Sunday, and he judged it could not be fixed until Monday | ATTESTED, his words, three days after. The monitor's own record puts DOWN at about 05:23 Eastern |

**Down: 34 h 46 min**, from the shutdown to the app starting. The monitor's own figure is two
minutes longer, because it checks every five minutes.

**Cause: a billing failure, for the second time.** ATTESTED (unverified): the steward reports the
hosting bill was overdue and that he paid it. What the server shows is consistent with that and
proves no more: a clean shutdown nobody here issued, and a boot nobody here issued two minutes
after he said he had paid. The first time, the provider destroyed the machine
(`2026-09-05-droplet-destroyed.md`). This time it kept the disk.

## What worked

- **Nothing was lost from the disk.** The ssh host key was unchanged, every Docker volume was
  present, 114 of 114 migrations were already applied, and the nightly dumps either side of the
  outage are 57,254 and 57,211 bytes. That is consistent with nothing lost. Row counts were not
  compared, so it is not proof.
- **The keys were where the design says they would be: nowhere on the server.** A restart clears
  them (`docs/key-custody-design.md`, Sixth entry). The server held ciphertext only, so a powered-off
  disk in a provider's hands for a day and a half held no key.
- **The rig's way back from a restart worked the first time it was needed for real.** Docker had
  left a directory where the key file belongs, which is the case the Seventh entry fixed without
  ever having seen it on this server. The rig cleared it and put the keys back in 24 seconds.
- **The time the design itself cost was 3 minutes 23 seconds,** from the server booting to the app
  starting. That is only because someone was at the laptop. With nobody there it is as long as
  nobody is there, and that is the trade the Sixth entry names.

## Finding 1: the record cannot show that an alert reached anyone

Detection worked, and that part is verified: the monitor read DOWN within about five minutes, and
its push contact was `Active` when the liveness check last looked (2026-11-10 03:00,
`scripts/monitor_liveness.sh`).

**What the record does not hold is the next step.** The outage entered the record ten hours in,
because an agent re-checked production at the start of a session about something else. The steward
then said his health check and the backup alert had told him. He was not asked when. The agent
wrote that night that "the alarm chain did its job", which is true of detection and of nothing
further.

This matters because of gate box 1 (`docs/ethics-and-safety.md`). Its open line asks for an alert
that reaches a person who is not expecting one, with the receipt being his own report of it before
anyone tells him. **A real, unannounced outage is the best test that line could have had, and it was
not recorded as one.** It is entered here as a gap measured, not as a pass.

From 11-08 20:33 the outage was known. The remaining 24 and a half hours were the bill, not the
alarm.

> ⚖️ **Added 2026-11-12, because he was asked and he answered. The paragraphs above are kept as
> they were written.** His words: *"i got an alert that works now but it was at 5 am and i was
> asleep"*, and *"It was on a sunday so i knew i couldnt fix it until that monday I wasnt worried at
> all."* ATTESTED (unverified): said three days after the outage, with nothing behind it except
> that it fits the monitor's own record of DOWN at about 05:23 Eastern.
>
> **What this changes.** The ten hours were not an alarm that failed to arrive. By his account an
> alert reached his phone that morning, and what followed was his decision to wait for Monday. So
> this finding's heading says too much: on his word, the record now holds that an alert arrived.
>
> **What it does not change.** It is still not box 1's receipt. That line asks for his report of
> the alert *before* anyone tells him, and the agent raised this outage first. When he first saw
> the alert after waking was not said. Box 1's line stays as it was.

## Finding 2: "a crash loop" was wrong

The Sixth entry and the rig's own comment both said that after a restart production would fail
"in a crash loop the uptime monitor sees". It does not loop.

Measured on this boot (Docker 29.8.0, restart policy `unless-stopped`): one start attempt for the
app and one for the worker, both at 21:01:43, both refused while mounting the key file, both left at
`Exited (127)`. Docker did not try again in the 2 minutes 54 seconds before the rig ran. Its own
documentation says why: a restart policy only applies once a container has started successfully.

So after a restart the app is **stopped and quiet**, not restarting and loud. What still makes it
loud is the monitor, and only the monitor. The proxy was up from 21:01:42, so the site was reachable
and the app was not. What the proxy answered in those three minutes was not read.

## Finding 3: the first backup after the outage was killed by a login

The 11-10 03:00 backup uploaded its dump, verified it, and then died with `Terminated` while
checking the key file. No heartbeat went out.

The server's journal has the whole chain:

1. The steward's laptop runs an hourly check that, since 2026-11-03, also logs in over ssh to read
   whether the server wants a restart. It logged in at 03:00:04 and out at 03:00:10.
2. `logind` stops a user's session manager 10 seconds after their last session closes.
3. The aws CLI on this server is a snap. A snap started while a session manager exists runs under
   it, even from cron.
4. At 03:00:20 the manager stopped and took the upload with it.

Two nights earlier no login overlapped, the upload ran under the system manager, and it finished.
So this was waiting for any night the laptop happened to be on at 03:00, and for any root login
that closed inside the backup's twenty seconds, an agent's included.

**Fix:** `loginctl enable-linger root`, which keeps the manager running whether or not anyone is
logged in. It is in the runbook now (`docs/deploy/vps-runbook.md` §9).

**How we know it holds,** counted from the journal on 2026-11-10:

| | root logins closed | times the manager was stopped | uploads killed by it |
|---|---|---|---|
| Before linger (6 h 36 min, from the boot) | 14 | 11 | 1 |
| After linger (17 h 3 min) | 39 | 0 | 0 |

All 42 runs of the aws CLI since the fix started under the manager that no longer stops.

⚖️ **What is not yet proven.** A backup started the way cron starts one, with the login that
started it closing at once, completed. But it finished in 9 seconds, inside the old 10-second
window, so it would have passed before the fix too. The table above is the proof. The first real
nightly run under linger is 2026-11-11 03:00 and had not happened when this was written.

## Finding 4: copies of `.env` that nobody was watching

Looking around `.env` on the server turned up four stale copies of it: two beside the live file
(`.env.save` and a dated `.env.bak-…`), and two in `/root` from before the custody rig. Each held
between 28 and all 31 of the live file's values, the off-site backup credential among them. The two
in `/root` also held app keys in plaintext, which is the subject of the correction now attached to
the done-when list in `docs/key-custody-design.md`.

All four were shredded on 2026-11-09. A sweep of the whole disk afterwards finds the live `.env`,
`.env.example`, and two empty mount stubs. The backup credential they held was replaced the same
night and the old one deleted, and the provider now refuses it.

## What was lost, and what was not

**Lost:** 34 hours 46 minutes, and the nightly backup of 2026-11-09.

**Not lost:** the disk, the database, the keys (the server's ciphertext copy and the laptop's are
the same file, and the key file put back equals the laptop's decrypt, both by hash), and every
earlier backup: 44 dumps off-site on 2026-11-10, each with its key file, the oldest from 10-12.

## Corrective actions

| # | action | state |
|---|---|---|
| 1 | Put the keys back with the rig | ✅ 11-09 21:05 |
| 2 | Re-run the killed backup | ✅ 11-10, three complete runs |
| 3 | Let root linger, on the server and in the runbook | ✅ server · runbook in this PR |
| 4 | Correct "crash loop" in the custody design and in the rig's comment | this PR |
| 5 | Record the first real restart under the tmpfs design (custody design, Eighth entry) | this PR |
| 6 | Remove the stale `.env` copies, and have the runbook set the mode and warn about them | ✅ server · runbook in this PR |
| 7 | Replace the backup credential those copies held | ✅ 11-09 and 11-10 |
| 8 | Next time, record when an alert reaches the steward and what he did (box 1) | ⬜ for next time. For this outage he was asked on 11-12: Finding 1's note |
| 9 | Decide what stops a third billing outage | ⬜ steward's call |

On 9: nothing in this repository can make a bill get paid. Both outages so far began there, and the
first one cost the machine. It is listed so that it is a decision and not a surprise.

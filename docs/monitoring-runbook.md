# Monitoring runbook — turning the decided posture ON

> STATUS: runbook written 2026-08-11 (pilot-parish push; ethics-gate item 1 is now the
> build's critical path). The POSTURE is already decided and is not re-decided here:
> **Option C — local structured logs + UptimeRobot, Sentry off** (`docs/monitoring-decision.md`,
> Jasiah 2026-07-18). This runbook is the hands-on-keyboard path to the gate box:
>
> > *"Monitoring and alerts are wired. Done when the uptime pinger is live against `/health/`
> > and a silent error or outage produces a real alert to a human within minutes, proven by
> > deliberately tripping it once and watching the alert arrive."* — `docs/ethics-and-safety.md`, Part 3
>
> Account creation and the trip test are founder-hand steps (external account; a real, brief
> production outage). An agent prepared this document; an agent must not perform those steps.

## What exists already (verified in code, 2026-08-11)

- `GET /health/` (`apps/health/views.py`, wired in `config/urls.py:14`) returns
  `{"status": "ok", "db": "ok", ...}` with **200**, or **503** when the database check fails —
  so a plain HTTP monitor catches both "box down" and "app up but database broken."
- Optional `HEALTH_CHECK_TOKEN` env guards the endpoint (constant-time compare). The
  2026-07-18 decision confirmed the endpoint is currently public and returns 200 tokenless.
  If a token is ever set, the monitor URL must become `/health/?token=<value>` **the same day**,
  or the monitor will alert on 403 forever (that failure is loud, not silent — acceptable).
- ~~One stale docstring: `apps/health/views.py` mentions "Uptime Kuma".~~ **Fixed 2026-08-17.**
  The same pass swept the whole repo for the contradiction and found it was not one line but four
  surfaces: `docs/monitoring.md` described a self-hosted Kuma stack as the posture,
  `docs/deployment-checklist.md` told the deployer to set up Kuma, and `README.md` advertised both
  the Kuma profile and Sentry. All now point at `docs/monitoring-decision.md`. The opt-in
  `uptime-kuma` service in `docker/docker-compose.prod.yml` was **left in place, not deleted**, and
  is documented as not-the-posture.

## ✅ COMPLETE. The trip test ran 2026-08-18 and the gate box is ticked.

**Receipt: `docs/monitoring/trip-test-2026-08-18/`** — both alert screenshots, the timeline, and an
independent agent-side poll of `/health/` that corroborates the emails.

**Measured on the day: 6m 06s of real downtime, DOWN alert in ~3.5 minutes, recovery alert in
~2.5 minutes.** Both inside the gate's "within minutes."

This runbook was written 2026-08-11 as a from-scratch path; steps 1 to 4 are kept only as reference
for a rebuild or a second instance. **Step 5 carries two corrections that only surfaced by running
it — read them before repeating this on another instance.**

**Monitor as measured 2026-08-18:** HTTP/S on `https://reciprocalaid.network/health/`, keyword
`exists ok`, 5-minute interval, monitor id `803538525`. The endpoint returns
`{"status": "ok", "db": "ok", "cache": "ok"}`, HTTP 200 in ~0.29s.

### ROOT CAUSE OF "the alert email never arrives", found 2026-08-18

**The E-mail notification channel was switched OFF on the monitor.** SMS and Voice were on;
E-mail and Push were off. **No email was ever going to arrive.** Toggled on, saved, re-tested by
the founder — the test notification now lands. Nothing was broken; a setting was off.

🔴 **CORRECTION TO THIS FILE, recorded rather than quietly edited.** An earlier version of this
section (merged in PR #150) stated the likely cause was *"outbound mail still on the console
backend."* **That was wrong.** UptimeRobot sends alerts from **its own infrastructure** to the
founder's inbox; it never touches this application's mail backend. The app's console-backend mail
issue is a real and separate problem and has nothing to do with monitor alerting. **Anyone
debugging an alerting gap here should look at the monitor's notification channels first, not at
Django's email settings.**

### 🔴 What this cost, and why the box exists

**Last 30 days at the time of the fix: 84.416% uptime, 4 incidents, 4d 19h 56m down — and not one
of them reached a human.** Last 7 days were clean at 100%. The monitor detected every incident and
announced none of them, because of the toggle above. **That is the concrete argument for this gate
box**, and it belongs in the record.

⚠️ **Unverified, worth checking:** SMS and Voice were enabled and pointed at the founder's number
throughout those four incidents. If neither reached him, the free tier likely does not deliver them
(both are normally paid features). **Compare call/text history against the incident dates before
relying on either channel.**

### What still has to happen before the box is ticked

**A test notification is NOT a trip test.** The gate's wording is *"a silent error or outage
produces a real alert to a human within minutes, proven by deliberately tripping it once and
watching the alert arrive."* **Go to step 5.** That step is the founder's hands: it is a real,
brief production outage.

## The founder's hand-list (written from scratch; see the note above for where to start)

1. **Create the UptimeRobot account** — free tier, founder email, strong password in the
   password manager, 2FA on. (External account: founder-only step by the keyring.) ✅ **done**
2. **Install the UptimeRobot mobile app** and sign in — push notification is the "reaches a
   human within minutes" channel; email alone can sit unread. **← the channel that bypasses the
   broken email path; do this one.**
   🔴 **STILL NOT DONE, and on 2026-09-11 it cost the production droplet.** This step and step 4
   are the only two in this runbook never marked done. The droplet was powered off 09-03 and
   destroyed 09-05; nobody was told for eight days, because email was the only channel and the
   sentence above — *"email alone can sit unread"* — turned out to be exactly right.
   **`docs/incidents/2026-09-05-droplet-destroyed.md`.** Ethics-gate box 1 is re-opened until an
   interrupting channel exists and has been proven with the founder not watching for it.
3. **Create the monitor:** ✅ **done — exists, detection proven**
   - Type: HTTP(S) · URL: `https://reciprocalaid.network/health/` · Interval: 5 minutes.
   - Keyword variant (preferred if offered on free tier): alert when the response does NOT
     contain `"status": "ok"` — catches a 200 that isn't actually healthy.
   - SSL/domain expiry alerts: ON (the decision record names this explicitly).
4. **Alert contacts:** mobile push + email, both attached to the monitor. No Slack/webhook
   third parties — the decision's data-dignity posture is "nothing leaves the box" and a
   pinger only ever sees the health JSON, never parishioner data.
5. **The trip test (the gate's own proof — a real alert, not a dry run):** ✅ **DONE 2026-08-18.**
   **Receipt: `docs/monitoring/trip-test-2026-08-18/`.**
   - Pick a quiet minute (the board serves fictional data; there is no parishioner harm today).
   - On the droplet (`157.230.185.124` since the 2026-09-11 rebuild; this line named the destroyed
     `143.244.167.7` until 2026-10-08, an address now back in DigitalOcean's pool). `stop`/`start`
     keep the same container, so under key custody the app comes back with its keys; never swap
     them for `up`. Connect first, as a paste of its own (pasted with the lines after it, those
     lines run on the laptop once you leave the droplet; `docs/deploy-runbook.md`):
     ```bash
     ssh root@157.230.185.124
     ```
     At the `root@umi-droplet` prompt:
     ```bash
     cd /opt/umi-exchange
     docker compose --env-file .env -f docker/docker-compose.prod.yml stop app
     ```
     Wait through one full check interval plus retry (~6–11 minutes). The alert must arrive.
     ```bash
     docker compose --env-file .env -f docker/docker-compose.prod.yml start app
     docker compose --env-file .env -f docker/docker-compose.prod.yml ps app   # want "healthy"
     ```
     Confirm the recovery alert arrives too.
   - Screenshot both alerts. Those screenshots are the receipt the gate box cites.

   🔧 **Two corrections to this step, both found by running it (2026-08-18).**
   - **The service is `app`, not `web`.** Earlier versions of this step said `stop web`. **There
     has never been a `web` service** — `docker/docker-compose.prod.yml` defines `app`, `db`,
     `redis`, `caddy`, `uptime-kuma`. The command as written simply failed.
   - **`-f docker/docker-compose.prod.yml` is required.** Without it compose reads the dev file
     and does not act on the production stack at all. `--env-file .env` is also required, per the
     deploy runbook, or compose starts with missing env.
   - **Stop `app`, not `caddy`.** With Caddy up and `app` down the site returns a clean **502**,
     which is exactly the signal the monitor should catch. Stopping Caddy instead kills TLS, so the
     monitor records a connection failure and the evidence is muddier.

   ⚠️ **Changing the monitor's URL to a bogus path is NOT this test, and it was tried first.**
   Pointing the monitor at `/health/ERROR` produces a real alert with root cause `HTTP 404`, which
   proves the notification channel and nothing else. **The gate asks for two things at once** —
   the pinger live against `/health/` *and* a real failure producing an alert. A bogus path
   satisfies neither clause, and while it is configured that way **the real endpoint is not being
   monitored at all.** Read the `Checked URL` field on any alert before trusting it.
6. **Only after the alert actually arrived:** tick the gate box in `docs/ethics-and-safety.md`
   (separate commit, founder's merge), citing the date and where the screenshots live.
   ✅ **Done 2026-08-18** — box ticked, citing `docs/monitoring/trip-test-2026-08-18/`.

## Watching the watcher — `scripts/monitor_liveness.sh` (built 2026-11-02)

**The third of the three things box 1 now requires before it can be ticked again:** *"a periodic
liveness check on the monitor itself."* `scripts/monitor.sh` watches the app; until now nothing
watched the monitor, which is the exact gap that produced **84.416% uptime, 4 incidents, 4d 19h
56m down and zero humans reached** while detection was working perfectly.

It asserts the whole chain through the UptimeRobot API, and fails loudly — non-zero exit — on any
break:

| # | What it asserts | The failure it catches |
|---|---|---|
| 1 | the API answers at all | a revoked or expired key is a dead control |
| 2 | the monitor exists and is **not paused** | a paused monitor detects nothing, silently |
| 3 | ≥1 alert contact is **attached** | detection that tells nobody (runbook step 4 skipped) |
| 4 | ≥1 attached contact is **active** — UptimeRobot status `2` and nothing else (`0` not activated, `1` **paused**) | 🔴 **the actual production failure** — contacts attached, channel paused |
| 5 | ≥1 active contact is **interrupting** | e-mail-only, which is why the box re-opened |

~~**Run it from cron on the host, beside `monitor.sh`.**~~ ⚖️ **It runs from the steward's LAPTOP,
not the droplet** (his call "a", 2026-11-03). It talks to UptimeRobot, not to the server, so
production holds no third-party key, and the check keeps running even if the droplet is gone.

🔴 **The first version was a false green, caught on its first real run, 2026-11-03.** It read
contact status from `getMonitors`, which does not return it, and counted "no answer" as on. It also
treated status `1`, **paused**, as on. It printed `LIVENESS OK` while the live account read:

```
Reciprocal Aid Network: 3 attached — type=8 not-activated · type=14 not-activated · type=2 paused
NO ACTIVE ALERT CONTACT: every channel on 'Reciprocal Aid Network' is paused, not activated or unknown
```

That second block is the fixed script's verdict on the same account. **Every attached channel was
off.** Its fixtures had been the response shape that was *expected*; they are now the shapes
measured that night, and that exact state is a regression test.

**Configuration.** `UPTIMEROBOT_API_KEY` is required — **without it the script exits 2 and says
so**, because a liveness check that is silently unconfigured is the very defect class it exists to
catch. ~~A read-only monitor-specific key is enough.~~ ⚖️ **It needs the account's Read-Only API
key** (it starts `ur`). On/off lives in `getAlertContacts`, and a monitor-specific key (`m…`) may
call `getMonitors` only, so it can never see whether a contact is on; the script refuses it by
name. The API base is `UPTIMEROBOT_API_BASE` (default `https://api.uptimerobot.com/v2`, which
UptimeRobot now labels its legacy API — if it is retired, this fails loudly). `ALERT_WEBHOOK_URL` is shared with `monitor.sh`;
without it failures go to stderr for cron to mail. The key is written to a `0600` temp file rather
than passed as an argument, so it is not readable via `ps`, and it is never printed.

⚠️ **Calibration owed on the first real run.** `UMI_NON_INTERRUPTING_TYPES` defaults to `2 5`
(E-mail, Web-Hook) — **the two types this repo can cite**. UptimeRobot's numeric type for *mobile
push* is not documented here and was not guessed, so the script **prints every contact type and
status it saw**. Read that line on the first run against the real account and confirm the push
contact's type is outside the non-interrupting list. ✅ **Calibrated 2026-11-03** against the live
account: attached types `8` and `14` (not activated; probably pro-SMS and voice, which UptimeRobot's
docs call deprecated — unverified), `2` e-mail (paused), and an unattached type `12` (paused).
📌 **Narrowing** that list — counting another
type as interrupting — is the direction that can quietly re-open box 1; record the reason in the box.

🔴 **This does not tick box 1, and it is not the trip test.** It proves the alerting chain is
*wired*; only an outage the founder does not schedule or watch for proves an alert *arrives*.
Box 1 needs all three: an interrupting channel (step 2 of the hand-list, founder's), this check,
and that unannounced trip.

## What this deliberately does not do

- No Sentry, no hosted error aggregation — decided and documented; `SENTRY_DSN` stays empty.
- No agent-created accounts, no agent-run outages: both steps are founder-hand by the keyring
  (external service; deliberate production downtime).
- ~~No new code. The endpoint already exists and already fails loudly on a dead database.~~
  ⚖️ **Amended 2026-11-02:** still true of the health endpoint, which is unchanged. It stopped
  being true of the runbook as a whole when `scripts/monitor_liveness.sh` was added above.

## Ongoing posture (after the box is ticked)

- The monitor is part of deploy verification: after any deploy, glance that the monitor is
  still green (the deploy runbook's last step already says "verify the site responds" — the
  monitor is the standing version of that glance).
- If `/health/` gains a token, update the monitor URL the same day (see above).
- Revisit self-hosted GlitchTip ONLY if real error blind spots appear — per the decision
  record, not before.

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

## ⚠️ SETUP IS DONE. ONLY THE TRIP TEST REMAINS (step 5).

**Founder-confirmed 2026-08-17/18.** The account exists, the monitor exists, detection is proven,
and **the alert channel now works.** This runbook was written 2026-08-11 as a from-scratch path;
steps 1 to 4 are kept only as reference for a rebuild or a second instance.

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
3. **Create the monitor:** ✅ **done — exists, detection proven**
   - Type: HTTP(S) · URL: `https://reciprocalaid.network/health/` · Interval: 5 minutes.
   - Keyword variant (preferred if offered on free tier): alert when the response does NOT
     contain `"status": "ok"` — catches a 200 that isn't actually healthy.
   - SSL/domain expiry alerts: ON (the decision record names this explicitly).
4. **Alert contacts:** mobile push + email, both attached to the monitor. No Slack/webhook
   third parties — the decision's data-dignity posture is "nothing leaves the box" and a
   pinger only ever sees the health JSON, never parishioner data.
5. **The trip test (the gate's own proof — a real alert, not a dry run):**
   - Pick a quiet minute (the board serves fictional data; there is no parishioner harm today).
   - On the droplet: `docker compose --env-file .env stop web` (the compose invocation is the
     one recorded in the deploy runbook). Wait through one full check interval plus retry
     (~6–11 minutes). The push notification must arrive on the phone.
   - `docker compose --env-file .env start web` — confirm the recovery notification arrives too.
   - Screenshot both notifications. Those screenshots are the receipt the gate box cites.
6. **Only after the alert actually arrived:** tick the gate box in `docs/ethics-and-safety.md`
   (separate commit, founder's merge), citing the date and where the screenshots live.

## What this deliberately does not do

- No Sentry, no hosted error aggregation — decided and documented; `SENTRY_DSN` stays empty.
- No agent-created accounts, no agent-run outages: both steps are founder-hand by the keyring
  (external service; deliberate production downtime).
- No new code. The endpoint already exists and already fails loudly on a dead database.

## Ongoing posture (after the box is ticked)

- The monitor is part of deploy verification: after any deploy, glance that the monitor is
  still green (the deploy runbook's last step already says "verify the site responds" — the
  monitor is the standing version of that glance).
- If `/health/` gains a token, update the monitor URL the same day (see above).
- Revisit self-hosted GlitchTip ONLY if real error blind spots appear — per the decision
  record, not before.

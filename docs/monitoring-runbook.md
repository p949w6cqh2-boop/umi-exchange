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

## ⚠️ START AT STEP 4 — steps 1 and 3 are already done

**Founder-confirmed 2026-08-17: the UptimeRobot account exists, the monitor exists, and detection
is proven.** This runbook was written 2026-08-11 as a from-scratch path and, merged as-is, it would
send you to redo finished work.

**The actual open half is the alert channel: the alert email never arrives** (`STATE.md`, next
manual/ops steps). So ethics box 1 is **not** a setup job. It is one working alert away, and the
box wants a *delivered* alert, not a configured monitor.

**Do this:** step **4** (alert contacts, and find out why delivery fails), then step **5** (the trip
test, which is the gate's own proof). Steps 1 to 3 are reference for a rebuild or a second instance.

**Likely root cause, worth checking first:** `STATE.md` lists "SMTP creds so consented email leaves
the console backend" in the same breath. That is the same failure the board already had once, where
the code said the mail was sent and the inbox never saw it. **If outbound mail is still on the
console backend, no alert email can arrive no matter how the monitor is configured** — and a push
notification to the mobile app would sidestep it entirely, which is why step 2 matters more than it
looks.

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

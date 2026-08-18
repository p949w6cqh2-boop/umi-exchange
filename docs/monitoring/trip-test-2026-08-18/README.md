# Trip test — 2026-08-18

> **This directory is the receipt cited by ethics-gate box 1** ("Monitoring and alerts are wired")
> in `docs/ethics-and-safety.md`, and by step 5 of `docs/monitoring-runbook.md`.
>
> The gate's wording: *"Done when the uptime pinger is live against `/health/` and a silent error
> or outage produces a real alert to a human within minutes, proven by deliberately tripping it
> once and watching the alert arrive."*

## What was done

A real, deliberate production outage. On the droplet:

```bash
docker compose --env-file .env -f docker/docker-compose.prod.yml stop app
# ... wait for the DOWN alert, screenshot it ...
docker compose --env-file .env -f docker/docker-compose.prod.yml start app
```

Stopping `app` while Caddy stays up makes the site return **502 Bad Gateway** — a real failure of
the real service at the real URL, which is what the gate asks for.

The board serves **fictional demo data only** (St. Brigid's), so there was no parishioner harm.

## Timeline

Two independent records, taken from different vantage points.

| # | time (EDT) | time (UTC) | source | event |
|---|---|---|---|---|
| 1 | 18:34:08 | 22:34:08 | agent poll | baseline, `/health/` **200** |
| 2 | 18:37:42 | 22:37:42 | agent poll | **DOWN** — `/health/` **502** |
| 3 | ~18:41 | ~22:41 | **UptimeRobot email** | `Monitor is DOWN: Reciprocal Aid Network` → `01-down-alert.png` |
| 4 | 18:43:48 | 22:43:48 | agent poll | **RECOVERED** — `/health/` **200** |
| 5 | ~18:46 | ~22:46 | **UptimeRobot email** | `Monitor is UP: Reciprocal Aid Network` → `02-recovery-alert.png` |

**Total downtime: 6 minutes 6 seconds.**
**Alert latency: ~3.5 minutes to the DOWN alert, ~2.5 minutes to the recovery alert.**

Both are comfortably inside the gate's "within minutes."

The agent-side rows are an independent 15-second poll of the public `/health/` endpoint, running
throughout. They are not derived from the emails, so the two records corroborate rather than
restate each other.

## What the screenshots show

**`01-down-alert.png`** — the DOWN alert.
- Subject `Monitor is DOWN: Reciprocal Aid Network`, from `alert@uptimerobot.com`, **6:41 PM**
- **`Checked URL: https://reciprocalaid.network/health/`** ← the real endpoint
- Service reported down in N. Virginia, USA

**`02-recovery-alert.png`** — the recovery alert.
- Subject `Monitor is UP: Reciprocal Aid Network`, **6:46 PM**
- **`Checked URL: https://reciprocalaid.network/health/`**
- **`Root cause: HTTP 502 - Bad Gateway`** ← matches the independently observed 502 exactly

## What they deliberately do NOT show, and why

**Both images are cropped to the message pane.** Removed: the browser chrome and address bar (the
Gmail URLs contain message identifiers), the Gmail sidebar, the account avatar, the OS taskbar, and
all other browser tabs. **This repository is public.** Nothing was altered inside the message pane;
the crop only removes surrounding chrome. A black bar was never used — the crop does the whole job,
so nothing in these images has been painted over.

**`Hello p949w6cqh2-boop`** is kept on purpose. It is the founder's public GitHub username and it
ties the alert to the right account.

⚠️ **`01-down-alert.png` does not show the `Root cause` field** — the message was not scrolled far
enough before the screenshot was taken, so the field label is visible but its value is below the
fold. **The value is not missing from the record**: `02-recovery-alert.png` carries
`HTTP 502 - Bad Gateway` for the same incident, and the agent poll independently recorded the 502.
Saying so rather than re-cropping to hide the gap.

⚠️ **The collapsed message at the top of each screenshot is an EARLIER, DIFFERENT alert** (6:24 PM
and 6:25 PM, showing "Ashburn, USA"). It is from a first attempt that did **not** satisfy this gate
— see below. It is left in frame because cropping it out would be tidying the evidence.

## The first attempt, recorded because it failed

An earlier attempt the same evening produced a real alert that **did not satisfy this gate**. The
monitor's URL had been changed to `https://reciprocalaid.network/health/ERROR`, a path that has
never existed, and the resulting alert's root cause was `HTTP 404 - Not Found`. The service itself
never went down.

**That proved the notification channel and nothing more.** The gate asks for two things at once —
the pinger live against `/health/` *and* a real failure producing an alert — and pointing the
monitor at a bogus path satisfies neither clause honestly. It also meant that, while it was
configured that way, **the real endpoint was not being monitored at all.**

The URL was restored to `/health/` before the trip above, which is why the `Checked URL` field in
both screenshots is the field worth reading first.

## Related

- `docs/monitoring-runbook.md` — the hands-on path, step 5 is this test
- `docs/monitoring-decision.md` — why UptimeRobot and why Sentry stays off
- `docs/ethics-and-safety.md` — the gate this receipt closes

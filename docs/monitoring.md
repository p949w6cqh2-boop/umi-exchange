# Monitoring & Alerts

> **The posture is decided and is not re-decided here: `docs/monitoring-decision.md`,
> Option C — external UptimeRobot pinger + structured local logs, Sentry off, no aggregation
> SaaS at prototype stage (Jasiah, 2026-07-18).**
>
> **This page previously described a self-hosted Uptime Kuma container and contradicted that
> decision.** Corrected 2026-08-17. The reason it mattered: `docs/ethics-and-safety.md` Part 3
> ticks the monitoring box when *"a silent error or outage produces a real alert to a human within
> minutes"* — if the docs disagree about which system raises that alert, the box is ambiguous on
> the day it gets ticked.
>
> **The hands-on setup path lives in `docs/monitoring-runbook.md`, not here.** This page is the map
> of what covers which signal.

Health, TLS-cert-expiry, and disk alerting. **We do not add a second stack** (no
Prometheus/Grafana, no self-hosted uptime container alongside the external pinger).

## What runs where

| Signal | Covered by | How |
|---|---|---|
| Container health (db, **app**) | Docker `healthcheck` in `docker/docker-compose.prod.yml` | `restart: unless-stopped` + `depends_on: condition: service_healthy`. The **app** healthcheck was added (it had none); it probes `/health/`. |
| Public URL up + **TLS cert expiry** | **UptimeRobot** (external, free tier) | An HTTP(S) monitor on `https://<domain>/health/`, 5-minute interval, with SSL/domain expiry alerts on. External by design: a pinger that runs on the same droplet cannot tell you the droplet is down. |
| **Host disk** (+ a backstop health/cert check) | `scripts/monitor.sh` via cron | An external pinger cannot see the host's filesystem; this script can. |

**Why external and not self-hosted:** the decision record's reasoning is subsidiarity and data
dignity. UptimeRobot only ever sees the `/health/` JSON, which carries no parishioner data, and it
costs nothing. A self-hosted monitor on the same ~960 MB droplet shares the failure it is supposed
to report.

## 1. The external pinger (UptimeRobot)

**Setup is a founder-hand step and is written out in `docs/monitoring-runbook.md`** — account,
mobile app, monitor, alert contacts, and the trip test the ethics gate requires. Do not duplicate
those steps here; one runbook, one source.

⚠️ **`docker/docker-compose.prod.yml` still carries an opt-in `uptime-kuma` service behind
`profiles: ["monitoring"]`.** It does **not** start with a normal `docker compose up` and it is
**not** the decided posture. It is left in place rather than deleted so the option survives if the
decision is ever revisited. **Do not start it as part of gate work** — running both would leave two
systems claiming the same box.

## 2. Host monitor (disk + backstop health/cert) — cron

`scripts/monitor.sh` checks the app health endpoint, the TLS cert expiry, and host disk,
and alerts when a threshold trips. Add to the host crontab:

```cron
*/5 * * * * ALERT_WEBHOOK_URL=https://hooks.example/… CERT_HOST=exchange.example.org:443 /opt/umi-exchange/scripts/monitor.sh
```

Env (all optional, with defaults):

| Var | Default | Meaning |
|---|---|---|
| `HEALTH_URL` | `http://localhost:8000/health/` | endpoint probed for 2xx |
| `CERT_HOST` | _(unset → skip)_ | `host:443` for TLS-expiry check |
| `CERT_MIN_DAYS` | `14` | alert if the cert expires within this many days |
| `DISK_PATH` | `/` | filesystem to watch |
| `DISK_MAX_PCT` | `85` | alert at/above this disk % |
| `ALERT_WEBHOOK_URL` | _(unset → stderr→cron email)_ | webhook for the **host disk** alert only; unset falls back to cron-emailed stderr |

The script never exits non-zero on a tripped check — alerting is via the webhook (or
cron-emailed stderr), and one failing check never suppresses the others.

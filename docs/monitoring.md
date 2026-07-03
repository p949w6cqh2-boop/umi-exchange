# Monitoring & Alerts

Health, TLS-cert-expiry, and disk alerting — built on the monitoring **already in the
prod compose** (Uptime Kuma + Docker healthchecks). We do **not** add a second stack
(no Prometheus/Grafana alongside Kuma).

## What runs where

| Signal | Covered by | How |
|---|---|---|
| Container health (db, **app**) | Docker `healthcheck` in `docker/docker-compose.prod.yml` | `restart: unless-stopped` + `depends_on: condition: service_healthy`. The **app** healthcheck was added (it had none); it probes `/health/`. |
| Public URL up + **TLS cert expiry** | **Uptime Kuma** | An HTTP(S) monitor on `https://<domain>/health/`. Kuma alerts on downtime **and** N days before the cert expires (built-in). |
| **Host disk** (+ a self-hosted health/cert check) | `scripts/monitor.sh` via cron | Kuma can't see the host's disk from its container; this script can. |

## 1. Enable Uptime Kuma (already in the compose, opt-in)

```bash
docker compose -f docker/docker-compose.prod.yml --profile monitoring up -d uptime-kuma
```

Then in the Kuma UI (`:3001`) create:
- **Monitor → HTTP(s)** → `https://<your-domain>/health/`, interval 60s. Enable
  **"Certificate Expiry Notification"** (alerts ~14 days out). This covers **health + cert-expiry**.
- A **notification** (email / Slack / Discord / webhook) attached to the monitor.
- *(optional)* **Monitor → Push** for the disk heartbeat — point `ALERT_WEBHOOK_URL` (below) at its push URL.

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
| `ALERT_WEBHOOK_URL` | _(unset → stderr→cron email)_ | Slack/Discord/Kuma-push webhook |

The script never exits non-zero on a tripped check — alerting is via the webhook (or
cron-emailed stderr), and one failing check never suppresses the others.

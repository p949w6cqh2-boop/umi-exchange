# Error-monitoring & uptime: decision record

> STATUS: **DECISION PENDING (Jasiah).** Recommendation below is sourced where marked and
> CST-analytical where marked. Context: UMI Exchange in production on a ~960 MB DigitalOcean
> droplet, prototype stage, budget-sensitive, handling vulnerable community members' PII.
> Produced from a fan-out, adversarially-verified research pass (24 sources, 25 claims verified,
> 22 confirmed / 3 refuted), 2026-07-18.

## TL;DR

**At prototype stage, error-aggregation SaaS is not yet warranted.** Start with **structured local
logs (already in `config/settings/production.py`) + an external uptime pinger (UptimeRobot)** — the
most *subsidiary* (smallest, most local) and *data-dignifying* option: zero cost, zero parishioner-PII
egress. **Leave `SENTRY_DSN` empty.** If/when aggregated error tracking genuinely becomes necessary,
**self-host GlitchTip — not Sentry** — with PII capture disabled. Never send this app's error payloads
to a hosted third-party aggregator.

## The three options

| | (A) Sentry hosted | (B) GlitchTip | (C) Local logs + UptimeRobot |
|---|---|---|---|
| **Self-host on 960 MB?** | ❌ Impossible — 16 GB RAM min; installer hard-fails < ~16 GB [1] | ✅ Fits — 256–512 MB documented [1] (co-residency caveat below) | ✅ Already running |
| **Cost** | Free = 5k errors/mo, **1 user**, 30-day retention; cheapest paid $26/mo [2] | Free = 1k events/mo, **unlimited users**; self-host = $0 license [2] | $0 |
| **Licensing** | Source-available **FSL** (not OSI open-source; converts to Apache/MIT after 2 yrs; no competing use) [3] | **MIT** — genuinely open source, Sentry-API-compatible (change only the DSN) [4] | n/a |
| **PII egress** | Ships error payloads off-box (US default; EU residency available) [6] | Off-box only if *hosted*; self-host keeps it on your box [5] | **None leaves the box** |
| **Data-dignity risk** | SDK captures stack-trace locals + breadcrumbs → can leak PII **even with `send_default_pii=False`** [5] | **Same risk** — reuses Sentry SDKs [5] | No aggregation, no capture |

## The data-dignity crux (the decisive fact) [5]

Sentry's Python SDK captures **the values of local variables inside stack traces** and records
**breadcrumbs** (prior log statements + DB queries). Any of these can hold parishioner PII (names,
emails, addresses). This capture is **not** gated by `send_default_pii` — it's governed by
`include_local_variables` (defaults **True**) and separate breadcrumb-scrubbing options. So
`send_default_pii=False` alone does **not** prevent PII from being sent.

Because **GlitchTip reuses the same Sentry SDKs**, self-hosting it does not remove this leak — it only
ensures the (possibly-unscrubbed) PII stays on the parish's own box instead of travelling to a third
party. The only real protections are: **keep the data local** + set `include_local_variables=False` +
scrub breadcrumbs.

## Catholic Social Teaching lens (analytical, not source-backed)

- **Subsidiarity** — favor the smallest, most local solution that works. A local log file honors this
  more than any SaaS. Of the aggregators, only GlitchTip is even self-hostable on this hardware.
- **Data dignity of the vulnerable** — the strongest posture is *not shipping error data off-box at all*.
  Every hosted aggregator (Sentry US/EU, or GlitchTip hosted) ships payloads that can carry parishioner
  PII. Keeping it local (logs, or self-hosted GlitchTip) best respects the person.
- **Stewardship** — don't over-build. A one-maintainer prototype likely doesn't need an aggregation
  cluster yet.

These principles converge: **for this context, prefer local-only now; self-hosted GlitchTip later.**

## Recommendation for THIS context

1. **Now:** structured local logs (already configured) + **UptimeRobot** (HTTPS `/health/`, 5-min,
   SSL-expiry alert — confirmed public 200, no token). Leave Sentry off.
2. **Later, only if real blind spots appear** (e.g. silent 500s nobody sees): **self-host GlitchTip**
   (MIT, Sentry-API-compatible → the existing `sentry-sdk` + `SENTRY_DSN` wiring works unchanged),
   with `include_local_variables=False` and breadcrumb scrubbing regardless of backend.
3. **Avoid:** any hosted aggregator for this sensitive, vulnerable-population data.

## Honest caveats (from the research)

- **Vendor/corporate-ethics dimension: UNSUPPORTED.** No sourced claims about Sentry's VC-backing or
  either project's labor/business practices survived verification. Any CST *vendor-ethics* judgment
  here is unsubstantiated — decide that dimension on your own knowledge.
- **Option C is analysis, not sourced.** No verified data on UptimeRobot's current free-tier limits or
  an empirical logs-vs-aggregation comparison. The "start logs-only" call is CST/subsidiarity reasoning.
- **Co-residency reality.** GlitchTip's 256–512 MB figures assume a *dedicated* box. Your 960 MB droplet
  already runs Django + Postgres + Redis, so free RAM for a co-hosted GlitchTip may be well under 512 MB.
  GlitchTip 5.2's Postgres-only mode helps but wasn't tested in this exact scenario — a second small VPS
  may be needed, which changes the cost/subsidiarity math.
- **Pricing/licensing volatility.** Figures are 2026-current but change. Sentry moved BSL→**FSL** on
  2023-11-17 (the "BSL" label is stale; both are source-available/non-OSI). GlitchTip's ~$5 nonprofit
  tier was a single unverified note — confirm eligibility directly.

## Sources

1. Self-host RAM — GlitchTip install docs; `develop.sentry.dev/self-hosted`; `getsentry/self-hosted` #3298
2. Pricing — `glitchtip.com/pricing`; `sentry.io/pricing`
3. Sentry licensing (FSL) — `blog.sentry.io/introducing-the-functional-source-license`; `.../relicensing-sentry`
4. GlitchTip licensing (MIT) — `gitlab.com/glitchtip/glitchtip-backend` LICENSE + README; contribute docs
5. PII capture — `docs.sentry.io/platforms/python/data-management/sensitive-data`, `.../data-collected`, `.../configuration/options`
6. EU residency — `sentry.io/trust/privacy`

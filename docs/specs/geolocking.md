# Spec: geolocking — gate who can SIGN UP by region, not who can READ

> STATUS: **SPEC**, written 2026-09-26 on the founder's key. Decision recommended below;
> **BUILD happens on a separate key after the founder reads this.** No code in this PR.
>
> Origin, his words: *"this is a good opportunity to start geolocking"* → *"the great chinese
> firewall."* So: restrict access by the visitor's country, at the network's edge of this app.
> (An earlier reading — geo-aware demo LANGUAGE, `inbox/idea-demo-locale-packs.md` in the brain —
> was wrong and is not this spec.)

## The question

Real people have registered here (13 non-seeded accounts, `bright_line`, 2026-09-26), and **nobody
knows where they came from.** The pilot is one US parish; in-person intake starts in November. A
region gate would cut casual sign-ups from anywhere else.

**The Great Firewall blocks reading. That is the one part of the analogy this spec recommends
against** — see Option A.

## What is true today, read from code 2026-09-26

- **The trusted client IP already exists.** `apps/accounts/ratelimit.py:26` `client_ip()` reads
  only `X-Real-IP`, which Caddy **overwrites on every request** (`docker/Caddyfile.prod:28`), and
  never the client-supplied `X-Forwarded-For`. So a visitor cannot spoof their country by header.
  A geo gate reuses this — one source of IP truth, same as rate limiting and audit.
- **The path-scoping pattern already exists.** `RATELIMIT_AUTH_PATHS` (`config/settings/base.py:279`)
  names the auth endpoints a middleware throttles. A geo gate mirrors it.
- **No GeoIP dependency exists.** This is a new database file and a new small library.
- 🔴 **Where past sign-ups came from cannot be measured.** IPs are stored only as salted hashes,
  deliberately (§8.3, the audit design). That is correct and it means **the problem this gate would
  solve is currently a guess.** Phase 0 below measures it before anything is blocked.

## The honest limits, stated before the design

- **A VPN defeats it in one click.** So does a residential proxy, which is what serious bots use.
  **This is a speed bump against casual out-of-region sign-ups, not a wall** — the same honest
  label the keyring uses for `rule-guards.sh`.
- **IP geolocation is wrong sometimes** — mobile carriers route through other states or countries,
  corporate networks exit elsewhere. Some real neighbours will be misplaced.
- **The founder travels.** Anything that gates *login* or *admin* can lock him out of his own
  deployment from abroad.

## Options weighed

| Option | Blocks | Costs | Verdict |
|---|---|---|---|
| **A. Whole-site block** (the literal Great Firewall) | everything from outside the region | **Every parish outside the region is cut off from the demo, the landing page and the open-source link** — the site's own *"any community can run its own"* becomes unreadable to the communities it names. The demo was first written for an Irish parish. | ⛔ **Recommend against as the default.** Available as a flag if he decides otherwise. |
| **B. Gate account creation + admin login** | new sign-ups and admin attempts from outside | international visitors can browse but not register | ✅ **Recommend.** Protects the membership; leaves the mission readable. |
| **C. Gate all auth** (login, reset too) | also existing members abroad | a real member travelling cannot sign in or reset | ⚠️ Not recommended — punishes the people the gate exists to protect. |
| **D. At the edge** (Cloudflare, or a Caddy GeoIP plugin) | same as B, before the app | Cloudflare = moving DNS + a new account (his hand) + proxying all traffic; Caddy needs a custom build | ⏸ Later, if volume ever justifies it. App middleware reuses `client_ip()` and is testable today. |
| **E. SSH / droplet firewall** | network access to the host | **lockout risk when he travels**, and it does not touch the app | ⛔ Out of scope — separate decision. |

## Recommended design — measure, then gate B

### Phase 0 — measure for two weeks, block nothing

A middleware in **count mode** on the gated paths: look up the country, **increment an aggregate
counter per country, store nothing else.** No IP stored, no per-request log line pairing an IP with
a country. A management command prints the table.

**Why first:** *"a story that fits the curve is not a cause"* (the brain, 2026-09-22). If two weeks
shows every sign-up is from the US, the gate is optional. If it shows a stream from elsewhere, the
gate has a receipt.

### Phase 1 — the gate

- **Paths:** `GEO_GATED_PATHS`, default `("/auth/register/",)`. Admin login is a **separate opt-in**
  (`GEO_GATE_ADMIN`), because gating it can lock the founder out while travelling.
- **Allow list:** `GEO_ALLOWED_COUNTRIES` from the environment (ISO codes, e.g. `US`).
  🔴 **Empty means OFF — and the codebase default is empty.** UMI is meant to be self-hosted by any
  community anywhere. A parish in Kenya running its own copy must not inherit a US-only lock. **The
  lock belongs to this deployment's `.env`, never to the code.**
- **Blocked request → a plain page, not a silent drop:**
  *"Sign-up here is open to [region] during our pilot. Anyone can run their own board — it's free
  and open source."* with the self-hosting link. Someone outside the region is exactly the person
  the project invites to run their own; the refusal should say so.
- **Fail OPEN.** Missing, unreadable or out-of-date database → allow, and log loudly. **A broken
  lookup must never lock out real people**; the gate is a speed bump, and a speed bump that breaks
  closed is an outage.
- **Unknown country** (private address, lookup miss) → allow.
- **Privacy:** the country is looked up in memory, used for one decision, and dropped. Never stored
  beside an IP; never logged beside an IP. Coarse, request-time, country-level — the posture
  `inbox/idea-demo-locale-packs.md` already said passes the ethics bar.

### The database

| Source | Licence | Account needed | Verdict |
|---|---|---|---|
| **DB-IP "IP to Country Lite"** | CC BY 4.0, monthly `.mmdb` | **none** | ✅ **Recommend** — attribution line on the about page |
| MaxMind GeoLite2-Country | free, EULA | **yes** — an account and licence key, his hand | fallback |

Read with the small `maxminddb` library (pure Python). Refresh monthly: a management command that
downloads and atomically swaps the file, run by host cron. **A stale file still works** — countries
rarely move — which is part of why fail-open is safe.

## Build notes (for the keyed implementation PRs)

- Middleware placement: **after** the rate-limit middleware, so a blocked region still counts
  against the per-IP throttle.
- `client_ip()` is the only IP source. Do not read `X-Forwarded-For`.
- Tests: an allowed country passes · a blocked one gets the plain page · **empty allow list = gate
  off** · missing database = allowed + logged · unknown country = allowed · a spoofed
  `X-Forwarded-For` changes nothing · **no IP is written anywhere** (extend
  `tests/test_audit_pii_hygiene.py`) · Phase 0 stores only per-country integers.
- `ethics-and-safety.md` should name the gate and its fail-open rule, since it processes location.

## Not this spec

- **Blocking reading** (Option A) — recommended against; one flag if he wants it anyway.
- **SSH / droplet firewall** — separate decision, lockout risk.
- **Cloudflare** — only if volume ever justifies moving DNS.
- **Geo-aware demo language** — a different idea, parked in the brain's inbox.

## Done-when

- [ ] Phase 0 has run two weeks and the per-country table is recorded.
- [ ] With `GEO_ALLOWED_COUNTRIES` unset, nothing is gated — proven by a test.
- [ ] With it set, an out-of-region sign-up gets the plain page and the self-host link.
- [ ] A missing database blocks no one.
- [ ] No IP is stored or logged beside a country.
- [ ] The public pages — landing, demo, source link — load from anywhere.

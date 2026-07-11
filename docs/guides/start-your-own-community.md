# How to start your own UMI community

*There are two doors, depending on how much you want to own. Most people want
the first one.*

> The water is everywhere; nobody owns the pipes. UMI is built so any parish,
> chapter, or neighbourhood can run its own board — on somebody's existing
> server or on your own.

## Door 1 — Start a community on an existing UMI site (five minutes)

If a UMI site is already running (say, your diocese or a neighbouring parish
hosts one), you don't need a server. You need an account and a name.

1. **Sign up** on that site (email is optional — a username is enough).
2. After signing in you'll land on the welcome page with **two cards: join a
   community, or start one**. Pick **Start a community**.
3. Give it its **name** ("St. Patrick Parish") — you become its first
   **admin** (coordinator).
4. The community gets a private **join code**. Share it the way you'd share
   anything parish-only: the bulletin, the sacristy corkboard, a QR code in
   the narthex. Anyone with the code can join; nobody without it can even see
   the board.
5. From **Settings** you can add more coordinators as trusted helpers step up,
   set up need/offer **categories** that fit your community, and reset the
   join code any time it leaks too far.

That's genuinely all. Your community's board, needs, offers, matches, and
member list are scoped to your community — other communities on the same
server never see them.

## Door 2 — Host your own UMI (own the pipes)

If you want your parish's data on your parish's server — or there's no UMI
near you — you can run the whole thing yourself. It's a standard, small
self-hosted web app: Docker, one Postgres database, a bit of patience.

The honest path, start to finish, is already written down:

- **`docs/st-patrick-playbook.md`** — the 90-day pilot playbook: server setup
  in weeks 1–2, coordinator onboarding, quiet launch, full-parish opening,
  and how to decide afterwards whether it earned its place. Written for a
  real parish, reusable for yours.
- **`docs/deployment-checklist.md`** — the technical checklist (environment,
  secrets, backups, health checks).
- **`scripts/harden.sh`** and **`docs/umi_dev_security_protocol.md`** — the
  security hardening that should run before real names enter the system.

The short version of week one:

1. A small VPS (2 GB is plenty to start), a domain, Docker.
2. Clone the repository, copy the example environment file, set real secrets
   (the app **refuses to boot** on placeholder keys — that's deliberate).
3. `docker compose up`, run migrations, create your admin account.
4. Confirm the health check is green and backups run.
5. Create your community (Door 1, steps 3–5, on your own site).

## Which door?

| | Door 1 — existing site | Door 2 — self-host |
|---|---|---|
| Time to first need posted | minutes | a weekend |
| Technical skill | none | comfortable with a server |
| Who holds the data | the hosting instance | you |
| Cost | free | ~a small VPS |

Start with Door 1 if you can. Door 2 is always open later — and one day,
federation lets self-hosted communities share needs across parish lines
without giving up their own keys.

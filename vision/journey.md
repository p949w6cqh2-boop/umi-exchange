# What We Had vs What We're Getting — the journey

> STATUS: confirmed arc, 2026-06-17. The story of how the architecture changed, and why.
> Tags: **BUILT** (in code) · **DESIGNED** (spec only) · **IDEA**.

## The shift in one line
From **one cathedral** (a single central platform that owns everything) → to **a constellation
of lakes** (independent tools that each work alone and connect *with consent*). Nobody owns the pipes.

## What we HAD — the cathedral
- A single grand **Reciprocal Aid Network**: one monolithic platform meant to do everything, centrally.
- Implied a central authority and a central data store — the thing people would have to *come to*.
- Naming was muddy ("usermegadatainfrastructure"; "UMI Exchange" used for the whole thing).
- Problem: a cathedral is one big build, one owner, one honeypot of data — the opposite of
  "the poor are not a market; they're neighbours," and a single point of capture/failure.

## The pivot — the Lakes Strategy
- **UMI = United Moral Infrastructure**, an open *protocol*, not a product.
- **Lakes Strategy**: many independent tools ("lakes"). Each works standalone; any two can
  connect *with consent, not surveillance*. "You can lead people to water but can't make them
  drink — so build lakes all around them."
- **R.A.N. (Reciprocal Aid Network)** is re-cast as the *reference implementation*, not the empire.
- Naming fixed (see `what-is-umi.md`): `umi-exchange` = the repo for **Lake 1**, not the umbrella.

## What we're GETTING — the current state
- **Lake 1 — Parish Aid Board** (`umi-exchange`): needs/offers/matches with dignity, consent,
  contact-revelation, append-only audit. → **BUILT**.
- **Lake 2 — Case Notes / casework**: privacy-first intake for aid workers. → **BUILT**.
- **Envelope encryption / crypto-shred** across all PII (needs + casework + Person), Stages A–E. → **BUILT**.
- **Conformance:** Core ✅ + Casework ✅. **Federation** (lakes talking with consent) → **DESIGNED**, next.
- **Lakes 3–8** (Skills Directory, Pantry Tracker, Shepherd, Volunteer Hub, Community Insights,
  Referral Bridge) → **DESIGNED**.
- **First community:** St. Patrick (the pilot / beachhead → diocese later).
- **The Brain** (this repo): the portable markdown OS that runs the protocol across tools. → being built.

## Why it matters (the invariants we carry forward)
- **Consent, not surveillance** — at the protocol level (Federation) and the personal level (`connections/`).
- **Crypto-shred over hoarding** — delete a key, not a promise. The poor are not a data market.
- **Trust is a setup, not a feeling** — the keyring: no key = no capability; if it can, assume it
  will → safe-fail (see `../trust/keyring.md`).
- **Lakes over cathedrals** — independent, portable, no central owner; plain files, any tool.

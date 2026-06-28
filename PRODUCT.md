# Product

## Register

product

## Users

Two roles inside a community (a Catholic parish, a secular mutual-aid group, a disaster-relief
network, a timebank):

- **Members** — neighbours who post a need ("an ask") or an offer, usually on a phone, often in a
  hurry or a hard moment. Low friction is everything; many are not tech-fluent, some are vulnerable.
- **Coordinators / admins** — trusted volunteers who match needs to offers, verify members, and (in
  casework) hold sensitive situations with care.

The job: ask for help, or give it, and get connected to a neighbour — without exposure, judgment,
or bureaucracy.

## Product Purpose

UMI Exchange coordinates **reciprocal mutual aid** so a community can give and receive with dignity.
It is a reference implementation of the **UMI Protocol v0.1** that any community can self-host and
re-skin. Success is concrete: a need met by a neighbour; contact shared only after both sides agree;
nothing surveilled; erasure honoured. Guiding ethos — *"the poor are not a market; they are
neighbours,"* and *"consent, not surveillance."*

## Brand Personality

Warm · human · dignified. A **digital town well**, not a SaaS dashboard — a place people gather to
give and receive. Calm and inviting; never corporate, never churchy. Voice: plain, kind, few words.
It should feel like a parish noticeboard you trust, not an app that is extracting from you.

## Anti-references

- **Generic SaaS** — cards-everywhere, hero-metric template, gradient accents, cold blue-gray neutrals.
- **"Charity portal" coldness** or savior framing — recipients are neighbours, not cases to process.
- **Churchy skin** — heavy religious clip-art or ornamentation (the platform is parish-friendly *and*
  fully secular; warmth comes from craft, not iconography).
- **Surveillance / data-broker dashboards** — anything that reads as extracting or monitoring people.

## Design Principles

1. **Neighbours, not a market.** Every screen treats people as people — dignity over metrics, no
   growth-hacky dark patterns, no engagement bait.
2. **Consent, not surveillance.** Reveal the minimum the exchange needs; contact only after mutual
   agreement; crypto-shred honours erasure. The UI never asks for more than the moment requires.
3. **People scan, they don't read.** One clear focal point per screen, one obvious action, few words.
   Glanceable beats comprehensive.
4. **Warm and human.** A town well — cream paper, water-teal, gold warmth. Inviting, calm, dignified.
5. **Re-skinnable for any community.** Theming is first-class; one community's identity is never
   hardcoded into another's.

## Accessibility & Inclusion

- **WCAG 2.1 AA**, contrast verified (primary teal 6.03:1 on cream; warm ink 13.6:1; white-on-teal
  button 6.23:1).
- **Light theme only** by design — ink stays dark across every per-community preset, so legibility is
  safe regardless of the chosen hue.
- **`prefers-reduced-motion`** honoured (fades only, no movement).
- **≥44px touch targets**, mobile-first, progressive enhancement (core flows work without JS; HTMX +
  Alpine enhance rather than gate).

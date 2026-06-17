# What is UMI? — Names, meaning, vision

> STATUS: confirmed by Jasiah, 2026-06-12. This node standardizes the (previously messy) naming.

## The canonical names (use these everywhere)
- **UMI Protocol** = **United Moral Infrastructure** — the open standard.
- **Lakes Strategy** = the architecture — a constellation of independent tools ("lakes") that each work alone and can connect with consent.
- **Reciprocal Aid Network (R.A.N.)** = our reference implementation (hosted + self-hostable).
- **Parish Aid Board** = Lake 1, the first lake. Its codebase = `umi-exchange`.

> Older/loose names to retire in new work: "usermegadatainfrastructure", ambiguous "UMI Exchange = the whole thing." `umi-exchange` is the **repo name for Lake 1**, not the umbrella.

## What it's for (Jasiah's words)
> "In five years, any community — a parish, a timebank, a refugee network — can spin up its own mutual-aid tool using the UMI Protocol, and those tools can talk to each other **with consent, not surveillance**. The water is everywhere; nobody owns the pipes. **The poor are not a market; they're neighbours.**"

## What a reciprocal aid network is
A community where members both **give and receive** (needs ↔ offers), matched with dignity, consent, and privacy — the opposite of one-directional charity or data-harvesting "mutual aid" platforms. Blueprint: **Acts 4:32–37**.

## The eight lakes (from the Lakes Complete Operating Manual v1.0)
1. **Parish Aid Board** — reciprocal needs/offers/matches. → BUILT (`umi-exchange`).
2. **Case Notes** — privacy-first intake & casework for aid workers (SVdP, etc.). → **BUILT** (`umi-exchange`, `apps/casework`): case files, sensitivity + consent gating, 4-hour sensitive-session re-auth, offline visit capture, append-only audit.
3. **Skills Directory** — community capacity / skill-sharing. DESIGNED.
4. **Pantry Tracker** — inventory & distribution for food pantries. DESIGNED.
5. **Shepherd** — end-to-end encrypted pastoral messaging. DESIGNED.
6. **Volunteer Hub** — scheduling/coordination. DESIGNED.
7. **Community Insights** — privacy-first analytics / funder reports. DESIGNED.
8. **Referral Bridge** — closed-loop referrals between orgs. DESIGNED.

> Conformance levels (manual): **Core → Casework → Federation**. `umi-exchange` is at
> **Core ✅ + Casework ✅** today (Lakes 1+2 built, plus envelope crypto-shred for all PII).
> Next milestone = **Federation**. Lakes 3–8 remain DESIGNED.

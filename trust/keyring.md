# The Keyring — what an agent may and may not do

> STATUS: confirmed by Jasiah, 2026-06-12. THIS NODE IS LOAD-BEARING.
> Principle (Jasiah): "I don't decide what it does. I decide what it *can* do. No key = no capability.
> If it can, assume it will — so engineer every worst case to be a safe-fail:
> archive not delete, draft not send, read not edit."

## ✅ Always allowed (no approval needed)
- **Read** anything — code, docs, the protocol spec, the manual.
- **Draft** changes — code, tests, docs — on a **branch** or as a proposal.
- **Propose** designs, refactors, new features, analysis.

## 🔒 Never without explicit approval (must ask first)
- **Push to `main`** — always use a branch + PR, or at minimum ask.
- **Send anything external** — real email, SMS, notifications.
- **Delete data** — even test data; no destructive migrations.
- **Spend money** — cloud credits, paid API keys, anything billable.
- **Touch live parish data** — St. Patrick or any real community.

## In one line
> Agents may **propose, draft, and analyse**. They may **not deploy, bill, or delete.** That boundary is the keyring.

## Safe-fail defaults (how to honor "if it can, assume it will")
- Prefer **archive over delete**, **draft over send**, **read over edit**, **branch over main**.
- More autonomy is **earned** through visibility, monitoring, battle-testing — "more autonomy = more watching."
- If unsure whether something needs a key → **treat it as needing one and ask.**

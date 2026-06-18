# Connections — the map (C2)

> STATUS: **DRAFT** by Claude Code, 2026-06-17, assembled from the repos + our conversation.
> Jasiah to verify/correct. Real names of people & parishes live in `inbox/private.md`
> (keyring rule — sensitive personal data stays out of git); this node uses **roles**.

## Does it change? — static vs live
The blueprint's C2 question. Decide per source:
- **Static → ingest** (plain markdown, right here): who's who, tool roles, the 8 lakes, project structure, the keyring.
- **Live → pull fresh every time, never cache**: repo/git state (`umi-exchange/STATE.md`), CI status, prod census output (`*_envelope_status`), deploy/cert health.
> "Markdown + an index takes you surprisingly far. No database needed at the start."

## The graph
```mermaid
graph TD
  J["Jasiah — Founder & Steward"]

  subgraph Agents["AI tools (who does what — see projects/stack.md)"]
    CC["Claude Code — repo+git agent (this brain is its router)"]
    CH["Claude chat — strategy / research"]
    PA["Prompting AI — drafts AGI prompts"]
    AG["Antigravity — local editor / manual testing"]
  end

  subgraph Worlds["Worlds / projects"]
    UX["umi-exchange (repo)"]
    UB["umi-brain (this)"]
  end

  subgraph Lakes["Lakes inside umi-exchange"]
    L1["Lake 1 Parish Aid Board — BUILT"]
    L2["Lake 2 Case Notes — BUILT"]
    L38["Lakes 3–8 — DESIGNED"]
  end

  subgraph Community["Who it serves"]
    PR["Parish / pastor (→ private.md)"]
    SV["SVdP coordinator (→ private.md)"]
    VOL["Volunteers"]
    NB["Neighbours (give ↔ receive)"]
  end

  subgraph Ext["External systems"]
    GH["GitHub — source of truth / CI"]
    DEP["Prod host + Caddy (TLS)"]
    BK["Backups (Backblaze B2 — planned)"]
  end

  J --> CC & CH & PA & AG
  CC --> UX & UB
  AG --> UX
  UB -. routes/knows .-> UX
  UX --> L1 & L2 & L38
  L1 & L2 --> Community
  L1 -. "Federation (DESIGNED)" .-> L38
  UX --> GH --> DEP
  DEP --> BK
  NB <--> VOL
```

## People & roles  (specifics → `inbox/private.md`)
- **Founder / Steward** — Jasiah (decides what the tools *can* do).
- **Parish pastor** and **SVdP coordinator** — the St. Patrick pilot stakeholders (names in private.md).
- **Volunteers / neighbours** — the give↔receive participants Lake 1 serves.

## Tooling links
- Tool roles & the prompting workflow → `projects/stack.md`.
- The lakes & conformance ladder → `vision/what-is-umi.md`.
- What an agent may do with any connection → `trust/keyring.md`.

## Open (Jasiah to fill)
- Other real people in the network (advisors, collaborators, diocese contacts)?
- Which external services are live vs planned (B2? domain/DNS? monitoring)?

# Stack & Tools — who does what

> STATUS: confirmed by Jasiah, 2026-06-12.

## The tool map
| Tool | Job (where it starts / stops) |
|---|---|
| **Antigravity** | Main AI-powered editor, runs locally. Write code, test, debug. |
| **Claude Code** | Repo-aware agent (has git). Generate/refactor code, run tests, fix, manage branches. *(This brain is its router.)* |
| **Claude chat (web/phone)** | Strategy, research, gap analysis, big-picture talk-throughs. |
| **Terminal** | git, Docker, migrations, running tests, deploying (manual). |
| **GitHub** | Source of truth, CI/CD. |
| **Lakes Complete Operating Manual (PDF)** | The spec / anchor for Lakes 2–8. |
| **A separate "prompting" AI** | Helps author prompts. |

## The promoting/prompting workflow
1. Jasiah writes a prompt (11-section template) →
2. feeds it to **Claude Code** →
3. gets code →
4. **tests** (terminal / Antigravity) →
5. **commits**.

## Projects ("worlds") tracked by this brain
| Project | Status | Where |
|---|---|---|
| **Lake 1 — Parish Aid Board** | BUILT, live-ready | repo `umi-exchange` (main green, ~200 tests on SQLite + Postgres) |
| **Lake 2 — Case Notes / casework** | **BUILT** | `umi-exchange/apps/casework` (merged to main) |
| **Envelope encryption (crypto-shred)** | **BUILT, A–E complete** | `umi-exchange`: needs + casework + Person PII; dual-read → backfill → Stage E contracts all shipped. Old-KEK retirement now unblocked. |
| **Lakes 3–8 designs + UMI v1.0** | DESIGNED (AGI output, unverified-to-built) | PDF: `umilakesdesignv1` |
| **umi-brain** | being built (git-tracked as of 2026-06-17) | this repo |

> Next conformance milestone: **Federation**. See `umi-exchange/docs/envelope-rollout-runbook.md`
> for the deploy → migrate → census → Stage E → KEK-retirement sequence.

> Source-of-truth rule: every node/claim is tagged **BUILT / DESIGNED / IDEA**. Designs are not facts.

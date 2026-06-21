# UMI Agent Setup Guide — bloat-free, Keyring-aligned

> STATUS: 2026-06-21. How to configure the local Claude Code environment for UMI without context
> bloat, with the Keyring trust model enforced. Principle: **context is a cache, not a database.**
> Part 5 is the step-by-step MANUAL tutorial (the things only you can do on your machine).

## 1. Research — how $1M+ ARR SaaS teams run agents
- **MCP schema tax is real:** every connected MCP injects its full tool schema into *every* message,
  used or not — easily 30–50% of the window before you type. Mitigate with **Tool Search** (deferred
  schemas, ~47% token cut), **project-scoping**, and monitoring via `/context` + `/doctor` (warns
  >25k tokens/MCP). Rule: if you can't explain your setup in two minutes, it's too messy.
- **Hooks over memory:** never trust the model to "remember" to test — enforce with pre-commit + CI.
- **Tool scoping:** general tools (docs) global; stateful/dangerous tools (DB) workspace-scoped.

## 2. Context strategy
| | umi-brain/CLAUDE.md | umi-exchange/CLAUDE.md |
|---|---|---|
| Role | Global router (pointers, vision, Keyring) | Local ground truth (stack, commands, gotchas) |
| Never holds | code specifics, schemas | vision, ephemeral state |

**Trash vs Fact test:** a *fact* needs a migration or an architectural decision to change; *trash*
changes by tomorrow on its own (current bug, branch name, "just installed X"). Trash never enters
any CLAUDE.md. **GC routines:** `/brain-refresh` (brain) + `/audit-context` (code docs) — both
propose-only drafts. **Amnesia defense:** the `~/.claude/CLAUDE.md` import + SessionStart hook force
the markdown to load every session; the window is disposable, `/clear` is the cache flush.

## 3. MCP & plugin blueprint (keep the global footprint tiny)
**MCPs vs Skills have opposite cost:** MCP = full schema every message (expensive idle); Skill/plugin
= metadata only, body loads on demand (≈free idle). So:
- **Tier A — Skills/plugins (global, cheap):** Superpowers (TDD, debugging, subagent code-review) via
  `/plugin` — NOT an MCP.
- **Tier B — Global MCPs (ruthlessly short):** Context7 (live Django/crypto/Tailwind docs).
- **Tier C — Project MCPs (umi-exchange `.mcp.json` only):** GitHub MCP (token via env var,
  read-only); DBHub → **local/CI Postgres, `--readonly`** (DBHub supports SQLite too, but inspect
  Postgres because SQLite ignores `select_for_update`). Misconfig guard: DSN from env, whitelist dev
  DB in TOML, read-only, never prod.
- Make Playwright **on-demand/project-scoped** (heavy), not always-on global.

## 4. Commands & routines (correct names)
- `/model` → `sonnet` (4.6, fast), `opus` (4.8, hard builds), `fable` (5, longest tasks); pair with
  `/effort` (low…max). GLM 5.2 via Z.ai for cheap routine passes.
- `/compact` preserves facts mid-task; prefer `/clear` between *unrelated* tasks (full flush).
- There is **no `/insight`**. `/insights` analyses *your own session usage*, not code. For read-only
  code analysis use **Plan mode** (Shift+Tab).
- Custom commands live in `<repo>/.claude/commands/*.md`. Built for UMI: `audit-context`,
  `prep-feature` (in umi-exchange), `brain-refresh` (in this brain, `cadence/`).
- Enforcement: pre-commit (`ruff` + `makemigrations --check`) + CI on Postgres 16 are the real
  anti-hallucination gates; SessionStart hook defeats amnesia.

## 5. MANUAL SETUP TUTORIAL — do these by hand (in order)
> Assumes repos side by side, e.g. `~/code/umi-brain` + `~/code/umi-exchange`. Replace paths/usernames.

**A. Sync this brain locally**
```bash
cd ~/code/umi-brain
git remote add exchange <your-umi-exchange-remote-url>   # one-time
git pull exchange umi-brain-export                        # pulls bootstrap, /brain-refresh, this guide
```

**B. Make every session load the brain** — create `~/.claude/CLAUDE.md`:
```
@/home/<you>/code/umi-brain/CLAUDE.md
@/home/<you>/code/umi-brain/trust/keyring.md
```

**C. SessionStart hook + (optional) GLM/effort** — `~/.claude/settings.json` (merge, don't overwrite):
```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume|clear",
        "hooks": [ { "type": "command",
          "command": "git -C /home/<you>/code/umi-brain pull --quiet 2>/dev/null; cat /home/<you>/code/umi-brain/capabilities/session-bootstrap.md" } ] }
    ]
  }
}
```
To run GLM 5.2 instead of your Claude subscription, add an `"env"` block (base URL + auth token +
model mapping + `_SUPPORTED_CAPABILITIES` so `max` effort shows) — see chat/notes. Leave it out to
stay on the Claude subscription. `CLAUDE_CODE_EFFORT_LEVEL: "max"` persists max effort.

**D. Install the custom commands** (copy each prompt body into `~/.claude/commands/` to make it global,
or keep them per-repo under `<repo>/.claude/commands/` — already committed there):
- `umi-exchange/.claude/commands/audit-context.md`, `prep-feature.md`
- brain: `cadence/brain-refresh.md` → copy to `~/.claude/commands/brain-refresh.md`

**E. MCPs (only what you need):**
```bash
claude mcp add --scope user context7 -- npx -y @upstash/context7-mcp     # global docs
# inside umi-exchange (project scope → .mcp.json):
claude mcp add --scope project github -- npx -y @modelcontextprotocol/server-github   # token via env var
claude mcp add --scope project dbhub  -- npx -y @bytebase/dbhub --readonly --dsn "$UMI_LOCAL_PG_DSN"
```
Then `/plugin` → install Superpowers. Run `/doctor` to confirm you're under the 25k MCP token warning.

**F. Verify** — open a fresh session in umi-exchange and ask:
"What are the four C's, the keyring one-liner, and the current in-flight task?" Brain answers = wired.

**G. Run the UI polish** — on a branch, after reading the corrected spec:
```
Read docs/ui-polish-spec.md and execute it. Presentation only; use var(--umi-*), enhance the
existing .umi-* classes (don't fork), keep reduced-motion. Recompile output.css, run pytest -q.
Branch, do not push to main. Report what changed.
```

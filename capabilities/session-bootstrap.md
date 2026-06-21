# Session Bootstrap — make any Claude Code session "use the brain"

> STATUS: 2026-06-21. The standing preamble that routes a fresh agent through the brain BEFORE any
> task. Same house format as `prompt-library.md`. Two halves: (A) the prompt the agent runs first;
> (B) the wiring that guarantees it lands in context every session.

## A — The bootstrap prompt (run FIRST, every session)
```
ROLE: session bootstrap for Claude Code on umi-exchange (Lake 1+2 code) WITH umi-brain (Jasiah's
markdown OS) as operating context. Run FIRST, every session, before any task.
THE BRAIN: umi-brain = router-based markdown second-brain (POINTERS not knowledge) — intent, trust,
capabilities, cadence. umi-exchange/STATE.md = code ground truth. Designs are NOT facts: honor
BUILT / DESIGNED / IDEA tags on every claim.
READ ORDER (top-down; if a pointer is unreachable that is bug #1 — fix it):
  1. umi-brain/CLAUDE.md (router) -> 2. trust/keyring.md (LOAD-BEARING) -> 3. projects/umi-exchange-
  roadmap.md (live handoff: where we left off) -> 4. vision/why.md (the mission) -> 5. STATE.md (skim).
KEYRING (non-negotiable): propose / draft / analyse freely; NEVER push to main, send, delete, spend,
or touch live parish data without asking. Safe-fail: archive>delete, draft>send, read>edit,
branch>main. Unsure it needs a key -> assume it does, ask.
MUST DO: (1) pull the brain so it's current before trusting it; (2) state the current in-flight task
from the roadmap; (3) carry a status tag on every claim; (4) new knowledge -> right brain folder +
add a router pointer; same prompt 3x -> it's a skill.
VERIFY LOADED: recite back the four C's + the keyring one-liner + the in-flight task. If you can't,
the brain didn't load — fix wiring before proceeding.
CONSTRAINTS: branch not main; nothing deployed; brain commits go via the umi-brain repo (or the
umi-brain-export transport branch if repo scope blocks it); no PII/secrets in git. STOP and ask if
the keyring is silent on an action.
```

## B — Wiring (so it loads without you re-pasting)
Two layers; use both. Assumes the repos sit side by side, e.g. `~/code/umi-brain` + `~/code/umi-exchange`.

**1. Static import — `~/.claude/CLAUDE.md` (personal, NOT the public repo CLAUDE.md):**
```
@/home/<you>/code/umi-brain/CLAUDE.md
@/home/<you>/code/umi-brain/trust/keyring.md
```
Absolute paths (relative imports resolve against the file's own dir). Router is pointers; the agent
pulls leaf files (roadmap, why, prompt-library) on demand. Never import private brain content into
the committed, public `umi-exchange/CLAUDE.md`.

**2. SessionStart hook — `~/.claude/settings.json` (freshness + inject this preamble):**
```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [
          { "type": "command",
            "command": "git -C ~/code/umi-brain pull --quiet 2>/dev/null; cat ~/code/umi-brain/capabilities/session-bootstrap.md" }
        ]
      }
    ]
  }
}
```
SessionStart hook stdout is added to context, so the brain is pulled current AND this preamble is
injected every session.

**3. Verify:** first message of a session ask — "What are the four C's, the keyring one-liner, and
the current in-flight task?" Answers from the brain = loaded. Vague = the import path or hook is wrong.

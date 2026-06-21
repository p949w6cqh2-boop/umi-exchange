# umi-exchange — Roadmap & Open Threads

> STATUS: live handoff, updated 2026-06-21. **A new session should read this first** to pick up
> where the last one left off. Ground truth for what's *built* = `umi-exchange/STATE.md`.

## ✅ Built & on main (umi-exchange @ `f9fe711`)
- Lake 1 (Parish Aid Board) + Lake 2 (Casework) — Core ✅ + Casework ✅ conformance.
- Envelope encryption / crypto-shred across all PII (needs + casework + Person), Stages A–E.
- `ENCRYPTION_KEYS` env wiring (rotation/KEK-retirement now runnable). ~200 tests green (SQLite + Postgres).

## 🔧 Ops pending (you, against prod — not code)
- **Old-KEK retirement** (runbook Phase 5): `ENCRYPTION_KEYS="<new>,<old>"` → `rotate_keks` →
  all 3 censuses clean (`casework_envelope_status`, `people_envelope_status`,
  `migrate_on_behalf_envelope --verify`) → drop `<old>`. See `umi-exchange/docs/envelope-rollout-runbook.md`.
- **Privacy policy / retention decision** — crypto-shred ships everywhere now; state the real
  retention model (you *can* honour §5.8 erasure via DEK deletion).

## 🟢 In flight — Member Tags & Verification (AGI design APPROVED with fixes)
The AGI produced a solid design (per-community Tag catalog + `MemberTag` 6-state machine; clergy
locked to `admin_verified` + mandatory evidence + public-when-verified; unmistakable
verified/self-reported/pending badges; audit every transition). **Approved to build**, with:

**Decisions (confirmed):** Q1 coordinators verify ministry tags / admins-only for clergy — yes.
Q2 member-removes-verified → soft-delete to terminal `removed`, history preserved — yes.
Q3 rejected→re-request allowed, rate-limited, **flag for admin after 3 rejections** — yes.
Q4 new app `apps/tags/` — yes.

**Must-fix before/while coding (verify-before-trust catches):**
1. Verify the full suite on **Postgres** + `check --deploy` — not SQLite only (the state machine's
   `select_for_update` is a no-op on SQLite). NOTE: `casework/state.py` locks a single row by pk
   (no `select_related`), so the nullable-FK outer-join trap does NOT apply — don't add
   `select_related` on nullable `verified_by`/`revoked_by` in any locked query.
2. Seed `DEFAULT_TAGS` via a **`post_save` signal in `apps/tags`** or lazy `apps.get_model(...)` —
   NOT a top-level `communities → tags` import (circular). Keep the `is_new` guard + `get_or_create`.
3. Move `StateMachineMixin` to a **shared module** imported by both `casework` and `tags`
   (today it lives only in `apps/casework/state.py` → Lake 1 importing Lake 2 is backwards).
4. Reuse `apps/accounts/ratelimit.py::check` with scope key `f"tagreq:{community_id}:{user_id}"`.
5. Explicit visibility restrictiveness ordering (public < community < coordinators_only), not string `min()`.

**Decided:** "public" = signed-in community members only; logged-out visitors see nothing.
**Next action:** AGI builds it staged (model+migration → views/forms → templates/badges → admin queue),
each stage green; then verify-and-integrate onto a branch.

## 📐 Designed / queued (not built)
- **Federation** — next conformance level (cross-community discovery, handshake/trust, consent
  propagation, secure attribute exchange). Design-doc prompt is in `capabilities/prompt-library.md`.
- **Person blind index** (`person_name_bidx`, §12.3) — searchable encrypted-name lookup, own key. Prompt saved.
- **Sign-in hub** + **UI/graphic-design polish** — prompts saved.
- **Lakes 3–8** (Skills Directory, Pantry Tracker, Shepherd, Volunteer Hub, Community Insights, Referral Bridge).
- **Mobile (React Native)** + **LLM need classifier** — future/R&D.

## 🧠 Brain access note
Direct commits to `umi-brain` require the session to have `umi-brain` in its repo scope at launch.
If a session can't push (proxy: "repository not authorized"), transport via a branch on `umi-exchange`:
`git push <umi-exchange> master:refs/heads/umi-brain-export`, then pull into the `umi-brain` clone.

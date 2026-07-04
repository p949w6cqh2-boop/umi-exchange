# Sign-in Hub — Design

> Status: DESIGNED (approved 2026-06-23). Target: `umi-exchange`, branch `feature/signin-hub`.
> A personalized landing shown immediately after sign-in. Read-only aggregation over BUILT apps;
> no new schema. STOP before merge (per feature brief).

## Goal
One calm, scannable landing right after sign-in that shows a member their world in the focused
community: their communities (with a switcher when there are several), quick actions, open matches,
recent notifications, and their own tags/verification status.

## Scope (YAGNI)
**In:** a login-required hub view + HTMX partials, set as the post-login redirect; multi-community
awareness; four read-only panels; parish-atmosphere styling; accessibility to WCAG-AA.
**Out (explicitly not building):** any new model/migration, write actions on the hub itself
(actions are links to existing create/feed views), cross-community aggregation dashboards,
notifications-per-community filtering (notifications are user-global by schema — see Data notes),
real-time updates/polling.

## Architecture

### Placement — new `apps/hub` app (view-only, no models)
Mirrors how `apps/dashboard` is a pure aggregator over other apps. A dedicated app keeps the
boundary clean and the query logic isolated/testable, and avoids growing the already-large
`apps/communities/views.py`. Contents:

- `apps/hub/views.py` — `HubResolverView`, `HubView`
- `apps/hub/selectors.py` — bounded, read-only query helpers (the only place that touches the ORM)
- `apps/hub/urls.py` — `app_name = "hub"`
- `templates/hub/index.html`, `templates/hub/_hub_body.html`, panel partials
- `apps/hub/tests/` (or `tests/test_hub_*.py`, matching repo convention)
- No `models.py` content, no migrations.

### Routing — Approach A: `/hub/<slug>/` + a thin `/hub/` resolver
- **`/hub/` → `HubResolverView`** (`LoginRequiredMixin`), the new `LOGIN_REDIRECT_URL`. Resolves
  which community to focus, then **redirects**:
  - **0** active memberships → redirect to `/join/` (preserve onboarding).
  - **1** active membership → redirect to `/hub/<slug>/` ("straight in").
  - **many** → redirect to the **last-visited** hub slug from the session if it is still a valid
    active membership, else the **most-recently-joined** active membership
    (`Member.objects.filter(user=…, is_active=True).order_by("-joined_at").first()`).
    **Gotcha:** `Member.id` is a **UUID**, so "most recent" must order by `joined_at` — never by pk.
- **`/hub/<slug>/` → `HubView`** (`LoginRequiredMixin`, `TemplateView`):
  - Gate: load the active `Member` for `(request.user, slug)`; **404 if none**. This membership gate
    *is* the cross-community isolation boundary.
  - Side effect: set `session["hub:last_slug"] = slug`.
  - Render: if `request.htmx`, render `templates/hub/_hub_body.html` only; else the full
    `templates/hub/index.html` (which `{% include %}`s the same body). This lets the switcher swap
    the body via HTMX while full-page loads and no-JS both work.

Rationale for A over alternatives: it satisfies "many → switcher / one → straight in" literally, is
bookmarkable, keeps no hidden state, and matches the established `/c/<slug>/…` slug-scoping
convention. (Rejected: single `/hub/` + session "active community" — hidden state, not bookmarkable,
fights HTMX push-url; aggregated all-communities — contradicts the switcher and gets noisy.)

### Data flow
```
login → /hub/ (resolver) → /hub/<slug>/ (membership gate) → selectors (bounded) → render
switch community → hx-get /hub/<other-slug>/ + hx-push-url → swap #hub-body  (plain <a> fallback)
```

## Components & data (read-only, bounded — mirror the feed's cap pattern)

`apps/hub/selectors.py` exposes small, independently-testable helpers. Each takes already-resolved
objects (no view logic), uses `select_related` where it crosses a FK, and applies an explicit cap.

| Panel | Selector | Reads | Bound |
|---|---|---|---|
| Communities / switcher | `member_communities(user)` | active `Member` rows for the user, `select_related("community")` | all (a user's memberships are few) |
| Quick actions | *(none — static links)* | builds `community-feed`, `need-create`, `offer-create` URLs from the focused slug | n/a |
| Open matches | `open_matches_for(member)` | `Match` where `need.requester == member` **OR** `offer.offerer == member` **OR** `proposed_by == member`, `status in {proposed, accepted}`, `need.community == focused`; `select_related("need", "offer")` | slice `[:50]`, newest first |
| Recent notifications | `recent_notifications(user)` | `Notification.objects.filter(recipient=user).order_by("-created_at")` | slice `[:8]` |
| Tags / verification | `own_tags(member)` | `MemberTag.objects.filter(member=member).select_related("tag")`, **all statuses** | all (a member's tags are few) |

**Data notes (load-bearing):**
- `Notification.recipient` is a **User**, with no community FK → notifications are inherently
  **user-global**. The panel therefore spans all the member's communities and will be **labelled**
  as such, so it never reads as community-scoped. Per-community filtering would need a schema change
  → out of scope.
- "Open matches" reuses the participant rules already enforced in `apps/matches`; the hub only
  *reads* them. Terminal/other statuses are excluded so the panel stays "what needs my attention."
- Tags panel uses the member's **own** tags at all statuses (their verified/pending/rejected/
  self-reported), reusing `templates/tags/_badge.html`. This is distinct from the shared-surface
  `verified_badges_for` (verified-only) — the member may see their own pending/rejected state.

## Settings change
`config/settings/base.py`: `LOGIN_REDIRECT_URL = "/join/"` → `"/hub/"`. Any existing test asserting
the old post-login `/join/` redirect is updated to expect `/hub/` (the resolver then forwards a
member with one community onward, so end-to-end behavior for a single-community member is preserved).

## Error handling & edge cases
- Not authenticated → `LoginRequiredMixin` → `/auth/login/`.
- `/hub/<slug>/` for a non-member or inactive membership → **404** (no existence leak).
- `/hub/<slug>/` for a non-existent community → 404.
- Stale `session["hub:last_slug"]` (membership left/deactivated) → resolver falls back to
  most-recent membership.
- Empty panels (no matches / no notifications / no tags) → calm empty states, never errors.

## Presentation & accessibility
- Extends `base.html`; uses the `--umi-*` theme vars and `.umi-*` classes from
  `docs/ui-polish-spec.md`. Mobile-first; calm transitions only, gated on `prefers-reduced-motion`.
- Semantic landmarks (`<main>`, headed `<section>` per panel), a labelled community switcher
  (`aria-current` on the focused community), visible focus states.
- Verification: axe/WCAG-AA audit on the rendered hub; Playwright walk-through of multi-community
  switching.

## Testing (maps to the brief's required tests)
1. **Renders for a member** — authenticated single-community member gets the hub (200) with their
   panels populated.
2. **Requires auth** — anonymous request to `/hub/` and `/hub/<slug>/` redirects to login.
3. **Only that member's data** — matches/tags shown belong to the member; notifications filtered to
   `recipient=user`.
4. **No cross-community leak** — `/hub/<slug>/` 404s for a user who is not an active member of that
   community; a member of A sees no B data when focused on A.
5. Resolver branching: 0 → `/join/`, 1 → straight to `/hub/<slug>/`, many → last-visited else
   most-recent.
6. Selector bounds: open-matches cap and notification slice respected.
7. HTMX: `/hub/<slug>/` with the HTMX header returns the body partial only.

## Verification gate (from the feature brief)
`ruff check` + `ruff format --check`; `makemigrations --check` (**aim: no new migration**);
`bandit` + `semgrep --baseline-commit main` (no new findings); `pytest` on Postgres; `check --deploy`
0 issues. Then `/audit-context`. **Branch not main; STOP before merge.**

## Build sequence (for the plan)
1. App skeleton (`apps/hub`, urls include, `LOGIN_REDIRECT_URL`) + resolver with its branching tests.
2. `selectors.py` with per-selector unit tests (bounds, isolation).
3. `HubView` + templates (full page + body partial) + render/auth/isolation tests.
4. Switcher (HTMX + fallback) + HTMX-partial test.
5. Styling pass (`--umi-*`), then a11y (axe) + Playwright switch walk.
6. Verification gate + `/audit-context`.

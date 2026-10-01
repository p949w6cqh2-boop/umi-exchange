# Spec: a narrow role — the intake helper (vouch, and nothing else yet)

> STATUS: **SPEC + BUILD in one PR**, written 2026-09-30 on the founder's key ("work on roadmap").
> Build plan item **C11** (brain `projects/coordinator-features-buildplan-2026-09-23.md`). Named as
> a precondition in `account-recovery.md` §C and `assisted-intake.md`.

## The problem, measured on `main` `d4f5f01d`

`Member.is_coordinator` is `role in ("coordinator", "admin")` (`apps/communities/models.py:118`).
The field note that opened this stream: a physical coordinator needs to **vouch** for neighbors
they meet at church, and the only way to give them that is the coordinator role — which also hands
them the moderation queue, member removal and reinstatement, hidden-need visibility, the contact
reveal on every match, tag verification, the resource directory, community pages, the federation
oversight view, standard-sensitivity casework, and the community settings page with its join codes.

The build plan counted "ten call sites." **The real count is about forty** — `is_coordinator` and
raw `role__in=("coordinator", "admin")` checks across moderation, communities, needs, offers,
matches, pages, federation, tags, casework and dashboard, plus six templates. Inventory: §Appendix.

## Recommended design — ADDITIVE, not a rewrite

The build plan proposed replacing every `is_coordinator` call site with a named capability
(`can_moderate`, `can_see_hidden`, …) in the same PR. **Recommended instead: add a role that
appears in none of those checks, and give it exactly one capability.**

| | Rewrite every call site (plan step 4) | Add a role outside every check (this spec) |
|---|---|---|
| Sites touched | ~40, each a privilege decision | **2** (the vouch view + a new vouch page) |
| Failure if one is missed | a coordinator locked out of their job, or a helper handed a power | **none**: a missed site treats the helper as a plain member, which is the intent |
| What the helper can do | whatever the capability map says | vouch; everything else exactly as a member |

The asymmetry is the argument: under the additive design **every existing check already excludes
the new role**, because every one of them names `coordinator` and `admin` explicitly. The safe
default is the one that happens without touching anything.

The capability refactor is still worth doing once a second narrow role exists, and it is recorded
under §Not this spec.

### What changes

1. `Member.ROLE_CHOICES` gains `("intake", "Intake helper")`. `max_length=15` fits. Migration is
   choices-only; **no data changes**, every member keeps their role.
2. `Member.can_vouch` — `role in ("coordinator", "admin", "intake")`. The only new capability.
3. `is_coordinator` is **unchanged** and **must never gain `"intake"`** — a comment on the property
   says so, and a test pins it.
4. `VouchMemberView` gates on `can_vouch` instead of `is_coordinator`. After a vouch it returns the
   helper to the page they came from; a helper cannot load community settings.
5. **New page `/c/<slug>/vouch/`** (`member-vouch-page`), for anyone with `can_vouch`: the same vouch
   form, alone, with plain words about what vouching means. Linked in the header for helpers (the
   header link to Community Settings stays coordinator-only).
6. Role changes stay **admin-only** — already true (`CommunitySettingsView`, `change_role` checks
   `is_admin`). A helper cannot promote anyone, themselves included.
7. The role dropdown on community settings shows the new option (it reads `ROLE_CHOICES`) with one
   line of plain text: an intake helper can vouch for neighbors and nothing else.
8. `member.role_changed` is already audited with from/to; the new value flows through unchanged.

### Tests (the load-bearing ones)

- A helper **can** vouch, from the new page.
- A helper gets the **same answer as a plain member** on every coordinator surface: community
  settings, moderation queue, hide/remove/reinstate, dashboard, hidden needs and offers, resource
  curation, tag verification, federation oversight. One parametrized test, member vs helper.
- `is_coordinator` is False for a helper (pins item 3).
- A helper cannot change a role.
- Every existing test passes unchanged.

## Amended 2026-09-30: the helper also gets the sign-up helper (B8)

His B8 ruling (2026-09-30) approved a sign-up page "for coordinators and helpers". So
`IntakeRegisterView` (`/c/<slug>/intake/register/`) gates on **`can_vouch`**, not `is_coordinator`.
The helper's whole power set is now: **vouch, and help a neighbor sign up.** Unchanged and tested:
**no `can_reset`** (a helper never touches a password), no settings, no moderation, no hidden
content. The settings page, the vouch page and the CHANGELOG say so in plain words.

## ⚖️ Decisions that are his

1. **The name.** Today the role only vouches; "intake" describes the gated half (B), not what it
   does now. Alternatives: *Greeter*, *Vouching helper*, *Welcome helper*. The stored value can stay
   `intake` whatever the label says. Built with the label **"Intake helper"** per the plan.
2. **Per-community, like every role.** A helper in parish A has no standing in parish B.
3. **The vouch reach, unchanged from today:** `VouchMemberView` finds the target by username across
   the whole board, not within the community (`account-recovery.md` §C names this). Tolerable for a
   vouch, which grants only verification; it matters more now that more people can vouch.

## Not this spec

- **`can_intake`** — reserved for `assisted-intake.md` §B, gated on the ethics gate (3 of 6).
- **The capability refactor** (named properties replacing `is_coordinator` at each site) — do it
  when a second narrow role is needed, as its own PR with its own review pass.
- **`templates/base.html:85`** checks `member.role in 'admin coordinator'` — a **substring** test on
  a string. It excludes `intake` correctly, but a future role named `coord` or `admin2` would pass.
  Flagged, not changed here.

## Appendix — coordinator checks on `main` `d4f5f01d` (none changed by this spec)

`apps/moderation/views.py` 104, 126, 175, 187, 304 · `apps/communities/views.py` 183, 222, 412, 750
(→ `can_vouch`) · `apps/needs/views.py` 69, 87, 169 · `apps/offers/views.py` 63, 79, 142 ·
`apps/matches/views.py` 59, 88, 162, 184, 253, 275 · `apps/matches/models.py` 186 ·
`apps/pages/views.py` 37, 123, 161, 220, 249, 292 · `apps/federation/views.py` 833, 851, 853, 997 ·
`apps/federation/outbox.py` 311 · `apps/tags/views.py` 201, 246, 290, 327 · `apps/tags/models.py`
210, 366 · `apps/casework/access.py` 17, 32, 36, 86, 90 · `apps/casework/forms.py` 84, 195 ·
`apps/dashboard/views.py` 50, 152 · templates: `base.html:85`, `moderation/queue.html:43`,
`communities/resources.html` 32/50/54, `federation/matches.html:86`, `tags/my_tags.html:170`,
`needs/detail.html:46`, `offers/detail.html:20`, `community_pages/editor.html:77`,
`community_pages/tombstone.html:10`.

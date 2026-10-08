# Spec: "Who did what" — the coordinator activity page

> ✅ **BUILT and live since 2026-10-01 (#189, production `42fd75eb`).** *(Status line updated
> 2026-10-08; it had kept saying "SPEC + BUILD in one PR" after the merge.)*
>
> STATUS: **SPEC + BUILD in one PR**, written 2026-09-30 on the founder's pick (build plan **C13**,
> brain `projects/coordinator-features-buildplan-2026-09-23.md`). The detection half that any future
> coordinator-issued reset (A2) needs before it ships.

## What it is

`/c/<slug>/activity/` — coordinators and admins of **this** community see every vouch, role change,
removal, reinstatement, moderation step, resource, page and settings change in it, newest first, with
the name of the person who did it. Paginated (50), filterable by a start date. Linked from community
settings. Same gate as the dashboard.

## The decision that differs from the build plan

The plan proposed a nullable `community` column on `AuditLog`, backfilled. **Not built, because the
backfill cannot happen:** `AuditLog` is append-only — `save()` refuses UPDATE and Postgres revokes
UPDATE from the app's role (`audit/migrations/0002_append_only.py`). A new column would only fill
for events after the deploy, so the page would start empty and stay blind to history.

**Built instead: scope through what each row already names, in one database query**
(`apps/audit/coordinator_activity.py`):

| Actions | Tied to the community through |
|---|---|
| `community.updated / theme_set / identity_set` | `resource_id` = the community |
| `member.role_changed / removed / reinstated` | `resource_id` ∈ its members |
| `resource.added / archived` | `resource_id` ∈ its resources |
| `flag.resolved / dismissed` | `resource_id` ∈ its flags |
| `content.hidden / unhidden` | `resource_id` ∈ its needs, offers, pages |
| `page.*` | `resource_id` ∈ its pages |
| `tag.verified / rejected / revoked` | `resource_id` ∈ tags of its members |
| `user.vouched` | `details.community` = its slug (already recorded) |

No schema change, no migration on the audit table, full history from day one.

## What never reaches the page

- **An allow-list, not a deny-list.** Only the actions above. `member.blocked` / `unblocked` (a
  member's private act — "they aren't told") and `flag.created` (who reported whom) are excluded
  by construction, and a new action stays off until someone decides it belongs.
- **Only chosen fields.** Who (their display name in this community), what (a plain label), a short
  subject (the member affected, the vouched username, a tag slug, a resource category), and when.
  **Never** the raw `details` blob, the IP hash, or an email. Content titles are not shown.
- **Never another community's rows.** Tested per scope, including a vouch in a neighboring parish.

## Honest limits

- A community's rows are found through its CURRENT members, resources, pages and tags. Actions on a
  row that no longer exists (a hard-deleted resource) drop off. The codebase archives rather than
  deletes these, so the gap is small, but it is not zero.
- The actor is named by their CURRENT display name here; someone who left shows as "a former member".
- The intake-helper role (C11, separate PR) needs nothing extra: its vouches are `user.vouched` rows.

## Tests

`tests/test_coordinator_activity.py`: member 403 · anonymous → login · coordinator and admin 200 ·
settings links to it · every action family shown with its actor · newest first · another community's
rows never shown · private acts and reports never shown · no email, no IP hash, no raw details ·
50 per page · date filter · a real vouch through the real view appears.

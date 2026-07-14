# Demo-readiness triage — 2026-07-14

38 screens × 2 widths audited (four personas, seeded St. Brigid's + empty St. Kevin's +
edge fixtures). Severity-ordered. Fix batches: COPY → VISUAL → STATES, gated each.

## SEV-1 — a priest would wince
1. **Raw "403 Forbidden" white page** when a member opens the setup guide or moderation
   queue by URL. No `templates/403.html` exists. (STATES)
2. **Raw Django debug 404** (yellow technical page) on any typo'd URL while the demo server
   runs with DEBUG on — and the seed requires DEBUG on. Fix: `DEBUG` env override in
   development settings so the demo runs seeded with DEBUG off; document in the walkthrough.
   (STATES; one settings line, no view logic)
3. **Consent page reads like legalese**: "My Consents" / empty state "No consent records."
   (COPY/STATES)

## SEV-2 — visibly rough
4. **Em-dashes across 14 app templates (25 instances)** — the mission-page ban never reached
   app copy (notifications empty state, resources blurb, need detail, matches, tags…). (COPY)
5. **Title-Case buttons and headings cluster**: "Accept Match", "Mark Fulfilled", "Update
   Need", "Save Changes", "Change Password", "Set Up 2FA", "Send Reset Link", "Account
   Settings", "Verification Queue", "My Tags", "My Consents", technology page's "Built With
   Proven Technology". Voice = sentence case. (COPY)
6. **Dashboard case-speak**: "No stale needs! All inquiries are being addressed." ("inquiries",
   chirp "!"), "Avg Time to Match 0.0" reads dev-flavored when there's nothing to average. (COPY)
7. **Account page dev strings**: protocol/conformance/version block reads like a spec sheet
   inside member settings. (COPY)
8. **Custom-color inputs in community settings render as two unlabeled black swatches** (empty
   `<input type=color>` defaults). Label them and default to the current theme colours. (VISUAL)

## SEV-3 — polish
9. Hub greeting uses the full display name ("Welcome back, Nuala Doyle.") — first name is
   warmer. (COPY)
10. 500 page: "An unexpected error occurred and the team has been told." — passive, and a
    parish has no "team". (COPY)
11. Settings join-code confirm: "This will invalidate the current join code and QR." —
    "invalidate" is a dev word. (COPY)
12. "Copied!" chirp on the join-code button → "Copied". (COPY)
13. Tag queue empty state coldish: "No pending verification requests." (STATES)
14. Seed success message says "marta / demo-parish (coordinator)" — Marta is the admin. (COPY)

## Verified fine (no action)
- why-umi comparison table scrolls at 390px (`overflow-x-auto` + `min-w`); long names and the
  no-description need render cleanly; register error states are human; 404 page already warm;
  moderation-queue empty state already excellent; join/create with threshold print sit well;
  connect ceremony (fulfilled match) is the strongest screen in the app.
- Prints sit well on every surface they appear on (hub wash, spotlight, resources, join/create,
  match ceremony, mission pages).

## Listed, not built (functional gaps out of scope)
- `community-leave` is POST-only; a GET shows a raw 405. No real GET path exists in the UI.
- Empty board state could carry an inline "Post the first ask" button (buttons exist in the
  header; inline CTA would be nicer).
- Timeline timestamps on matches show exact clock times; relative ("today") would be warmer —
  needs a template filter, borderline logic, deferred.

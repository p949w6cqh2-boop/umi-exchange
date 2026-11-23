# Vouch before a volunteer sees the asker's contact

> STATUS: **BUILT on branch `fix/vouch-before-volunteer-reveal`, not merged.** The founder's key "17"
> (2026-11-22), answering the question raised at the parish meeting: *"the safety risk between people
> meeting up"* (brain: `projects/field-notes-2026-11-22-safety-question.md`).

## The gap, in the project's own words
`docs/ethics-and-safety.md` §"The stranger at the door" said: *"When a volunteer proposes on a need
without a standing offer, accepting that match still reveals the asker's contact to a person the board
has not vouched for. The §8.2 rule does not yet guard this, and closing it, for example by requiring a
vouch on higher-risk categories, is on the build list."*

## The rule
On a match with **no standing offer** (a volunteer proposed it), the asker's email or phone reaches the
volunteer **only if this community has vouched for them**: a `communities.Vouch` row for the match's
community, or a role there that vouches for others (`Member.can_vouch`: coordinator, admin, intake).
Otherwise the volunteer sees the asker's name, marked `vouch_pending`, and the page says a coordinator
can put them in touch. That is a bare-name reveal, so the coordinators are told on accept (the notice
from #242), and a coordinator makes the introduction.

## Why a vouch is held per community, not on the account
The account already carries `User.verified_via`, and `"coordinator"` there means someone vouched. It
cannot carry this rule. **Any coordinator can vouch for any account on the site** (`VouchMemberView`,
kept on purpose by the founder's call of 2026-10-13, *because* "being verified only unlocks joining and
posting"), and **anyone signed in can create a community and be its admin.** So a stranger could vouch
for themselves in a community nobody else is in, then carry that mark into a real parish and receive
askers' numbers there. A vouch now unlocks contact only in the community it was made in, and the
founder's 2026-10-13 reasoning still holds: the site-wide mark unlocks nothing new.
`tests/test_vouch_before_volunteer_reveal.py` holds both routes shut, and both tests fail on a mutant
that trusts either one (checked 2026-11-22).

## The vouch door had to change too
`VouchMemberView` stopped at *"already verified"* for anyone verified by email or backfill, which is
nearly every account. Under this rule that would have held their reveals forever. It now records a
`Vouch` for this community whatever the account's verification, keeps how they were first verified,
audits `user.vouched` with `previously` for an account that was already verified, and says so if this
community has already vouched for them. The vouch page and the settings form say what a vouch now does.

## Calls made by the agent, for the founder to check
1. **All categories, not "higher-risk first".** The app has no risk flag on a category (only
   `coordinators_only_contact`, which already keeps the asker's number from the helper for Communion at
   home), and nearly every ask on the board ends in meeting: a ride, a visit, a repair at home. One
   word narrows it later with a category flag.
2. **Held only when it withholds something.** An asker who shares no channel, or who has left, keeps
   the box's usual line, so the page never blames a vouch for what the asker chose.
3. **No backfill.** Vouches made before this change live only on the account and in the audit log, so
   they do not count here, and those neighbours need vouching again in their community. The
   alternative, deriving rows from the audit log in a migration, writes to live data on deploy.
4. ⚠️ **The intended consequence:** once deployed, a volunteer with no standing offer stops receiving
   an asker's details until their community vouches for them. Production has real accounts; how many
   volunteer matches that touches was not read.

## Unchanged
Matches with a standing offer · what the asker sees · the coordinators' oversight view · the audit of
every reveal (§8.3) · who may vouch and the limits on vouching.

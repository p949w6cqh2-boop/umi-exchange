# Vouch before a helper sees the asker's contact

> STATUS: **BUILT on branch `fix/vouch-before-volunteer-reveal`, not merged.** The founder's key "17"
> (2026-11-22), answering the question raised at the parish meeting: *"the safety risk between people
> meeting up"* (brain: `projects/field-notes-2026-11-22-safety-question.md`). Widened the same night
> to every helper by his **"17a"** (below).

## The gap, in the project's own words
`docs/ethics-and-safety.md` §"The stranger at the door" said: *"When a volunteer proposes on a need
without a standing offer, accepting that match still reveals the asker's contact to a person the board
has not vouched for. The §8.2 rule does not yet guard this, and closing it, for example by requiring a
vouch on higher-risk categories, is on the build list."*

## The rule
On any accepted match, **offer or not**, the asker's email or phone reaches the helper **only if this
community has vouched for them**: a `communities.Vouch` row for the match's community, or a role there
that vouches for others (`Member.can_vouch`: coordinator, admin, intake). Otherwise the helper sees the
asker's name, marked `vouch_pending`, and the page says a coordinator can put them in touch. That is a
bare-name reveal, so the coordinators are told on accept (the notice from #242), and a coordinator
makes the introduction.

## Why offers too: his 17a (2026-11-22)
The rule was first built for offer-less volunteers only, the route the ethics doc named. The automated
security review then found the way around it, confirmed in `MatchProposeView`: a member may propose any
offer they own in the community, with no check on its category or on when it was posted, so an
unvouched stranger could post an offer, propose it, and receive the asker's details one step later.
Three ways were put to him (every helper · a standing offer must predate the ask · keep it named), and
he keyed **17a, every helper**. `test_an_unvouched_offerer_does_not_get_the_askers_contact` holds it.

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
   home), and nearly every ask on the board ends in meeting: a ride, a visit, a repair at home.
2. **Held only when it withholds something.** An asker who shares no channel, or who has left, keeps
   the box's usual line, so the page never blames a vouch for what the asker chose.
3. **No backfill.** Vouches made before this change live only on the account and in the audit log, so
   they do not count here, and those neighbours need vouching again in their community. The
   alternative, deriving rows from the audit log in a migration, writes to live data on deploy.

## ⚠️ What changes for people once deployed
- **Every helper, offerers included, stops receiving an asker's details until their community vouches
  for them in person.** Until then a coordinator introduces. Production has real accounts; how many
  matches that touches was not read.
- **The live demo parish has no `Vouch` rows** (the model is new), so its helpers will see names only
  until one of its coordinators vouches for them, or until the runbook's reseed runs
  (`docs/demo-reseed-runbook.md` §3, his hands), because `seed_demo_parish` now vouches every demo
  member in their own parish (`test_each_parish_vouches_for_its_own_members_only`). The recording
  rig's scratch databases get the same, so filmed connect moments still open on a phone number.
- Not changed by this: a helper's own details still reach the asker as the helper chose them on the
  offer. An asker needs no vouch to see them.

## Unchanged
What the asker sees · the coordinators' oversight view · the audit of every reveal (§8.3) · who may
vouch and the limits on vouching.

# Ethics & Safety — the harm analysis and the hard gate

> STATUS: policy + risk register, written 2026-07-18. This is the "why and how careful" layer that
> sits above the security docs, not a replacement for them. Where a technical claim appears here, it
> is checked against the code and cited, and anything the code does not enforce is named as a gap.
> Companion docs it points to rather than repeats: `docs/protocol/spec.md` (the normative protocol),
> `docs/threat-model.md` (application layer), `docs/network-security-addendum.md` (infrastructure),
> `docs/umi_dev_security_protocol.md` (dev/host), `docs/privacy-retention.md` (the retention schedule),
> `docs/monitoring-decision.md` (monitoring posture), `docs/incident-response.md` (what we do when
> data is exposed or someone official demands it), and `SECURITY.md` (how to report a hole).

## Why this document exists

UMI is live now, and the reference instance serves made-up people. That is the only reason this can
be written calmly instead of in a panic. Before a single real person's information is entered, we owe
them an honest account of what could go wrong, who could be hurt, and what has to be true first. This
document is that account, and it ends in a checklist that has to pass before any real community
onboards. The checklist is unchecked on purpose. Nothing here is finished.

---

## Part 1 — What this system is: a map of vulnerability

Most software holds preferences and purchases. UMI holds something heavier. By design it is an index
of who in a community is struggling, with what, and where they can be found. A mutual-aid board knows
who asked for food, or a ride to chemotherapy, or help after a partner left. The casework side knows
more, and keeps it for years.

That is not a flaw to be fixed. It is the point of the tool, and it is exactly what makes the tool
dangerous. A shopping app that leaks its database embarrasses people. A tool like this that leaks its
database exposes the people least able to absorb the exposure, and it does so as a single tidy list
that says, in effect, here are the vulnerable people and here is how to reach them. Some of those
people are hiding from someone. Some of them are one disclosure away from losing a job, a home, or a
custody arrangement. The stakes are not measured in inconvenience.

So the honest framing is this. The harm surface today is close to zero, because the only people in the
database are fictional. The moment the first real person is entered, the harm surface becomes real and
does not shrink again. Everything in Part 3 is meant to be true before that moment, not after it.

---

## Part 2 — The assessment

Five questions, answered for UMI specifically rather than in the abstract.

### 1. Who is harmed, and when

- **The vulnerable data subject.** The neighbour who asked for help is the person with the most to
  lose from a breach. Their need is recorded, and on the casework side their story is kept.
- **The third party who never signed up.** When a need is raised on someone else's behalf, that
  person's name is stored, and they did nothing to consent to it. See the consent section below, and
  gate item 5. Today their name is encrypted, but no one asked them.
- **The abuse survivor, at the moment of connection.** The protocol reveals contact details only after
  a match is accepted (§8.2), and that restraint is real and enforced. But acceptance is exactly the
  moment a survivor's location or contact can reach the wrong person if a coordinator account is
  compromised or a helper is not who they claim. The peak moment of the system is also its most
  sensitive one.
- **The coordinator.** The person doing the recording carries knowledge about their neighbours and the
  liability that comes with it. A tool that makes recording easy also makes over-recording easy.
- **The digitally excluded.** The neighbour without a phone or the confidence to use one is served by
  a coordinator speaking for them, which is humane and also the exact point where consent gets thin.

The timing matters as much as the list. Every harm above is theoretical while the data is fictional
and becomes concrete with the first real entry.

### 2. Who this actually benefits, interrogated

It is worth being suspicious of our own good intentions.

- **Today, the main beneficiary is the project.** The live instance proves the thing works. That is a
  real benefit to us and close to zero benefit to any actual person in need, because there are no
  actual people in it yet. We should not confuse a working demo with help delivered.
- **Reciprocity can flatter the giver.** "Iron sharpens iron" is true, and it can also become a story
  the comfortable tell themselves while the person receiving help stays the object of it. The design
  fights this by never naming helpers in public, but the pull is real and worth naming.
- **The already-connected benefit most.** Whoever is closest to a coordinator, most comfortable
  online, and best able to describe their need in a form gets served first. A tool for the margins can
  quietly serve the center.
- **Name who will want the data later.** Not everyone who wants this database will be a neighbour. An
  immigration enforcement request, a subpoena in a custody or eviction fight, a data broker, a future
  owner of the project who did not make its promises. Building the list creates the thing they want.
  Part 3 exists partly because of them.

### 3. Consent

The consent architecture is genuinely strong in places, and it is honest to say so and equally honest
to name where it stops.

**What the code enforces.** Any disclosure beyond a community's own boundary has to be a single,
member-owned action, and on the federation sharing path only the person whose record it is can share
it (`apps/federation/views.py`). Emergency case-opening without consent is not a loophole: it is
flagged, it requires a written justification, it is written to the audit log with the justification
itself redacted, and a database constraint refuses to store a case that is neither consented nor
flagged as an emergency (`apps/casework/models.py`, §3.7–§3.8). A member can revoke consent, which
freezes the case and sends delete-requests to any instance it was shared with (`apps/consent/views.py`,
§3.6/§3.9). These are real mechanisms, not promises on a page.

**Where consent is thinner than the promise.**

- **A coordinator records the consent, and the record now says so.** The protocol says coordinators
  must not consent for a member (§4.1). Until 2026-07-27 the casework intake violated that outright:
  because `Consent.participant` could only be a user, a subject with no account was recorded with the
  *coordinator* standing in as the grantor. The subject could not see it and could not revoke it.
  A consent row can now name a person who holds no account (`consent.subject_person`), with the
  coordinator recorded separately as `recorded_by` — a witness, not the grantor — and the person who
  wrote it down can withdraw it on their behalf. What remains, and cannot be fixed in code, is that a
  verbal yes across a table is still only as good as the coordinator who heard it. A rushed or
  well-meaning volunteer can still record consent that was never really given.
- **The on-behalf-of third party is asked, or shown less.** A person named in someone else's case has
  their name stored encrypted and shreddable. Until 2026-07-27 no consent or attestation was ever
  captured from them, and their full decrypted name was nonetheless the case page's heading. Now a
  case shows only initials, with a line saying plainly that the person has not been asked directly,
  until a consent naming *them* exists (`apps/casework/access.py:subject_display`). Lake 1's
  unrendered on-behalf field, which could only be reached by a hand-crafted POST and which no screen
  ever displayed, has been removed. The protocol requires the name be encrypted (§1) and is silent on
  asking the person; the gate is not.
- **Consent under duress looks like consent.** There is no code concept of duress. Consent given by
  someone who felt they had no choice is recorded identically to consent given freely. A tool cannot
  fix this on its own, but it should not pretend the record proves the freedom.

### 4. What we should exit or unlearn

Habits that served the build and will hurt real people if they carry over.

- **Ship-it urgency.** The reflex that got the instance live is the wrong reflex for onboarding real
  PII. Speed is a virtue in a prototype and a hazard next to a survivor's address.
- **"The code enforces the promise, so we're safe."** The code enforces a lot, and it does not enforce
  everything the marketing of it might imply. Member display names, account emails and phone numbers,
  and the free-text titles and descriptions of needs are stored in plain columns, not encrypted
  (`apps/communities/models.py`, `apps/accounts/models.py`, `apps/needs/models.py`). The
  key-encryption key lives in a file on the same machine as the database. Enforcement is partial, and
  believing it is total is its own risk.
- **Solo custody.** One person holding root, the keys, and the authority to say no is efficient and
  fragile. It is fine for fictional data and disqualifying for real data. See gate items 3 and 6.
- **More features equals more good.** Every feature that stores or reveals more is a larger map of
  vulnerability. Sometimes the ethical move is to build less.

### 5. What futures this could foreclose

- **The good of the data simply not existing.** The safest record is the one never made. Every design
  choice that records more forecloses the version of UMI that held less and was safer for it.
- **The unlogged, relational version.** Before this was software it was neighbours knowing neighbours,
  and that version left no breachable trail. Digitizing it buys coordination and spends
  deniability. That trade should be made on purpose, not by default.
- **Premature canonicalization.** The protocol is stamped v0.1, and freezing a v0.1 too hard can lock
  in the assumptions of the people who happened to build it first. A frozen standard is hard to
  correct later.
- **The trust needed to ever scale.** One bad breach, especially one that hurt a survivor, would end
  the project's ability to earn the trust it needs to be worth building. The future where UMI matters
  is the one it can lose in a single afternoon.

### Beyond the data: scams, strangers, and the meeting

The harms above are about the record. Two more harms live in the use of the board itself, and they
are the ones a real community will hit first. Real solidarity carries these risks, and the honest job
is not to sanitize them away but to make them informed and traceable.

**The board as a target for scammers.** An open, anonymous, money-moving marketplace is a scammer's
natural habitat, and UMI is deliberately none of those things. A Member is an identity within one
community (§1); people join a community through a coordinator and a join code, not through an
anonymous global feed. That closed-by-community shape is the single biggest defense, and it is a
choice to protect, not a feature to loosen. Two commitments follow from it. First, reputation is a
human vouching, meaning coordinator verification and member tags (`apps/tags`), not public stars or
reviews, because reviews get gamed and they shame the person receiving help. Second, and this is
policy, no money ever moves through the platform. UMI brokers a connection, not a transaction. The
moment the board handles a payment it becomes a fraud target and a money-transmission problem, and it
stops being a noticeboard. A neighbour can now report the person they were matched with, block a
neighbour so the two are never matched and are hidden from each other, and a coordinator can durably
remove an abuser (their content leaves the board and their in-flight matches are cancelled) and
reinstate someone later. What is still on the build list: a graduated freeze that is softer than a
full removal, dedupe of repeated on-behalf spam, and throttles against weaponized reporting.

**The stranger at the door.** Some exchanges end with two people meeting in person, and sometimes at a
home. This will happen, and it cannot be engineered away, because people meeting is the whole point.
The protective posture is informed consent plus an audit trail plus no false promise of safety, never
pretend-vetting. The floor is already enforced: contact is revealed only after a match is accepted,
only to the participants and coordinators, and every reveal is logged (§8.2), with only coarse
locality crossing a boundary before that. On top of that floor, the load-bearing commitment is a
plain statement, made in the terms and at the moment of connection: UMI brokers introductions between
neighbours, and it does not vet people, run background checks, supervise meetings, or guarantee
anyone's safety. That sentence is honest and it is protective, because it is the difference between
introducing two neighbours and vouching for a stranger. One design default supports it: lean toward a
neutral or public handoff rather than a home address, especially for higher-risk categories. And one
gap has to be named honestly. When a volunteer proposes on a need without a standing offer, accepting
that match still reveals the asker's contact to a person the board has not vouched for. The §8.2 rule
does not yet guard this, and closing it, for example by requiring a vouch on higher-risk categories,
is on the build list. A neighbour who chooses to open their door has real agency; the tool's duty is
to make sure the choice was made knowingly, the reveal was logged, and safety was never oversold.

---

## Part 3 — The gate

**No real community with real PII onboards until ALL of the following are true.** They are unchecked
because they are not yet true. Each item names how you know it is done.

- [ ] **Monitoring and alerts are wired.** Done when the uptime pinger is live against `/health/` and a
  silent error or outage produces a real alert to a human within minutes, proven by deliberately
  tripping it once and watching the alert arrive. The posture is already decided
  (`docs/monitoring-decision.md`); this item is about it actually being on.

- [x] **Backups are tested with a real restore, and the retention promise is verified.** Done when a
  backup made by `scripts/backup.sh` has been restored into a scratch database and its contents
  checked, and the 30-day retention (`RETENTION_DAYS` plus the B2 lifecycle rule) is confirmed to work,
  meaning old backups actually disappear on schedule. An untested backup is a guess, not a safety net,
  and unbounded backups quietly defeat crypto-shred.
  **Tooling ready 2026-07-27; the box stays open because nobody has run it yet.** `scripts/dr_sim.sh`
  already existed and already refuses to touch prod, but it was referenced in **zero** documents, could
  only pull from B2 (so an instance without a bucket could not rehearse at all), and **passed on a row
  count of zero** — an empty restore reported success. It now restores from an explicit file, B2, or
  the newest local backup; fails when the restore has no communities or members; asserts a known
  community via `DR_EXPECT_SLUG`; and is written up in `docs/deploy/vps-runbook.md` §9.1 with the
  retention check in §9.2. Guarded by `tests/test_dr_rehearsal.py`.
  **What closes it is a person running it**, on the droplet, and pasting the output: the rehearsal
  itself, and confirmation that old backups actually disappear — locally *and* in B2, where
  `backup.sh` deletes nothing and relies on a bucket lifecycle rule that must be created by hand and
  **does not exist yet**.
  **✅ CLOSED 2026-07-29 — run by the founder on the droplet, output pasted and agent-verified.**
  The rehearsal ran **twice** into a scratch database: (1) newest local backup — restore succeeded,
  `migrate` applied the pending `consent.0005` (the backup honestly predated that evening's deploy
  migration), then `migrate --check` exit 0; (2) the **first-ever B2 object**
  (`umi-backups/umi-20260729-194609.sql.gz`), pulled back down and restored — 5 communities,
  16 members, `st-brigids` present, `migrate --check` exit 0 first try. Retention: local prune
  observed live; the B2 lifecycle rule now exists and was verified by
  `aws s3api get-bucket-lifecycle-configuration` (Expiration 30 days, prefix `umi-backups/`,
  Status Enabled — matches `RETENTION_DAYS`). Found and fixed on the way, because the box was
  honest: **B2 had never been provisioned** (creds empty since deploy; zero off-box copies existed
  until this night), **no backup cron existed** (installed 2026-07-29, append-form), and
  `backup.sh` could skip the remote leg silently (**#130**: creds now self-load from `.env`,
  partial config is a hard error, `BACKUP_REQUIRE_REMOTE=1` makes a local-only night exit red).
  That caveat is now closed: `dr_sim.sh` gained a **docker mode** (`DR_DOCKER=1`) that routes psql
  and `manage.py` through `docker compose exec`, so the script runs on the dockerized droplet
  itself rather than being executed by hand through the containers. Docker mode carries a guard
  host mode does not need — inside the db container `localhost` IS the production server, so the
  database *name* is the only separation, and it refuses a target matching either `DATABASE_URL`
  or `POSTGRES_DB`. Guarded by 5 new cases in `tests/test_dr_rehearsal.py` (14 total). Stated
  precisely: the guards and the host path are tested end to end; the docker restore path itself
  has only been verified as far as every command it builds resolving on the droplet (compose file
  found, `exec -T db psql` → 16.14, `exec -T app` sees `manage.py`, db publishes no port). **The
  box does not move until a docker-mode rehearsal is actually run there.**

- [ ] **Key custody is separated from root and is not all held by one person.** Done when the
  key-encryption key no longer sits in a plaintext file beside the database under the same root
  account, so that compromising the host alone does not hand over the key, and when at least two
  distinct roles are required to reach it. Today the key and the data it protects live on the same
  machine, which means whoever gets the machine gets both.

- [x] **There is a written incident, breach, and legal-request response plan.** Done when a document
  exists that names who is notified and within what timebox when data is exposed, who decides to refuse
  an overbroad or unlawful demand for data (including a subpoena or an ICE request) and by what path
  that refusal is made, and how affected neighbours are told. It also has to cover a meeting that goes
  wrong in person and a report of a scammer or an abuser on the board: who a neighbour tells, who can
  freeze or remove that account, and what the coordinator does next. The refusal and escalation paths
  have to be explicit and decided in advance, because they will be needed on the worst possible day.
  **Written 2026-07-27: `docs/incident-response.md`.** It names the roles and admits all of them are
  one person today; gives the exposure clock (immediate → 1h containment → 24h facts → 72h tell the
  affected → 7d tell everyone) and a draft letter in the board's own voice; sets out the four kinds of
  paper someone can arrive with and what each actually compels, with the judge-signature test for
  telling a judicial warrant from an ICE Form I-200; gives a holding sentence for whoever is standing
  there; puts the refusal decision with the steward, in writing, never on the spot. Guarded by
  `tests/test_incident_response_plan.py`.
  **Two things it does not pretend:** the sections marked ⚖️ need a lawyer before they are relied on,
  and **there is no scoped legal-hold switch in the code** — suspending the deletion sweeps to
  preserve evidence today means stopping the scheduler by hand, which also suspends erasure for
  people who are not involved and are entitled to it.

- [x] **The consent flow honestly handles the on-behalf-of third party, and the board states its own
  limits.** Done when a need or case that names a person who is not a user either captures a real path
  to their attestation or consent, or visibly limits what is stored and shown about them until they can
  consent, closing the §1/§4.1 gap in code rather than only in policy. Done, too, when the terms and
  the connect screen say plainly that UMI brokers introductions and does not vet people, run background
  checks, supervise meetings, or guarantee safety, and when reporting or blocking a member is possible
  from the board itself.
  **Closed 2026-07-27.** Both routes, not one: `Consent.subject_person` lets a record name a person
  who holds no account, with `recorded_by` naming the coordinator as witness rather than grantor
  (ending the §4.1 violation), and `access.subject_display` shows only initials plus a plain line —
  *"this person has not been asked directly"* — until a consent naming them exists. The terms page at
  `/terms/` and the connect screen both carry the sentence, the accept dialog carries it *before*
  contact is exchanged, and report/block now hang off need and offer detail with the block list linked
  from settings and the moderation queue from the dashboard. Evidence:
  `apps/casework/tests/test_onbehalf_consent.py` (16) and `tests/test_board_states_its_limits.py` (10).
  What this does **not** fix: a verbal yes is still only as good as the volunteer who heard it.

- [ ] **Governance extends beyond a solo steward.** Done when more than one person holds real authority
  over the live instance, meaning access to the data, custody of the keys, and the power to refuse a
  demand, with a written path for succession and for removing someone who abuses the trust. One person
  as the entire trust boundary is not governance, it is a single point of failure with good
  intentions.

---

## Part 4 — The bright line

**The reference instance at reciprocalaid.network serves fictional demo data only, and it stays that
way until every box in Part 3 is checked.** The current demo is the fictional St. Brigid's parish. The
first real person's information does not enter the live system before the gate is met, and the demo
credentials are rotated before any real community is onboarded.

This is policy, not a preference. The line between fictional and real data is the whole safety story
right now, and it stays bright. If you are unsure whether an action would cross it, treat it as
crossing it and stop.

---

## What this document claims, in one honest paragraph

Enforced today, and checked against the code: envelope encryption with crypto-shred over the
subject-of-care identity fields, casework narratives, on-behalf-of names, and federation payloads; an
append-only audit log that stores IP addresses only as salted hashes; owner-only consent on the
federation sharing path; and an emergency case-opening path that is flagged, justified, audited, and
constrained at the database. Not yet true, and named here as gaps: coordinators can record consent on
a member's behalf in casework; on-behalf-of third parties are never asked to consent; consent under
duress is indistinguishable from free consent; revoking consent does not itself shred data; the
key-encryption key sits beside the data with no separate custody; several fields including member
names and account contact details remain in plaintext; and the operational posture, one machine, one
person, untested backups, no written breach or refusal plan, is not yet ready for real people. The
gate in Part 3 is the list of what has to change first.

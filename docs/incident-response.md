# Incident, breach & legal demands — what we do on the worst day

> STATUS: policy, written 2026-07-27 to close gate item 4 of `docs/ethics-and-safety.md`. It names
> who is told, in what time, who decides to refuse an unlawful demand for data, and how affected
> neighbours are told. Companion docs it points to rather than repeats: `docs/threat-model.md`
> (what can go wrong at the application layer), `docs/privacy-retention.md` (what we keep and for
> how long), `docs/network-security-addendum.md` (the infrastructure), `SECURITY.md` (how someone
> reports a hole to us).
>
> **This is not legal advice.** It is a plan written by the people who run this board so that
> nobody has to invent one under pressure. The sections marked ⚖️ **need a lawyer's review before
> they are relied on** in a real incident. Everything else is safe to adopt today.

## Why this document exists

The people whose data this system holds are poor and vulnerable neighbours. Some of them are
plausibly undocumented. Some are leaving someone dangerous. The day a demand arrives, or a laptop
goes missing, is the day it becomes clear whether the promises in `docs/ethics-and-safety.md` were
real or decorative.

Decisions made in advance are decisions made calmly. A frightened volunteer at a door at 7am, with
someone official-looking holding a piece of paper, should not be improvising policy. They should be
reading a script they have seen before.

---

## Part 0 — Who is who

Today, **one person holds every one of these roles**: Jasiah Williams, the steward.

That is the honest state, and it is exactly what gate item 6 exists to fix. Until it is fixed, this
plan has a single point of failure with good intentions, and everyone using it should know that.

| Role | What it means | Who holds it today |
|---|---|---|
| **Steward** | Final say on refusing a demand; speaks for the project | Jasiah Williams |
| **Data custodian** | Root on the droplet, access to the database | Jasiah Williams |
| **Key holder** | Holds the key-encryption key | Jasiah Williams |
| **Coordinator** | Volunteer inside a community; sees that community's board and their granted cases | per community |

**Interim rule while one person holds all of it:** no coordinator, and no volunteer, is ever the
person who answers a legal demand. Their whole job in that moment is *Part 2, step 1* — say the
holding sentence and call the steward. Nothing else is asked of them, and nothing else is permitted.

---

## Part 1 — Data was exposed

### What counts

Any of these, whether or not anyone acted on it: a database dump or backup leaving our control; the
key-encryption key being exposed; an account taken over; a coordinator seeing case records they were
never granted; a laptop or phone with an open session lost or stolen; a bug that showed one
neighbour another neighbour's private information.

**When in doubt, treat it as exposure.** The cost of over-reacting is an awkward email. The cost of
under-reacting is someone getting hurt and finding out later that we knew.

### The clock

| When | What happens |
|---|---|
| **Immediately** | Whoever noticed tells the steward. Any hour. There is no "wait until morning". |
| **Within 1 hour** | Stop the bleeding: revoke sessions, rotate the key, take the instance offline. Availability is worth less than containment. |
| **Within 1 hour** | **Freeze deletion.** See Part 2's legal-hold section — the automated sweeps must not run over evidence. |
| **Within 24 hours** | Write down what is known: what data, whose, how, when it started, whether it is closed. Facts only, no speculation. |
| **Within 72 hours** | Tell the affected neighbours (below). ⚖️ Some jurisdictions require a specific window and specific wording; this 72 hours is our own floor, not a legal maximum. |
| **Within 7 days** | Tell the whole community what happened, even those unaffected, and what changed because of it. |

### Telling the people it happened to

Plainly, in the voice the rest of this board uses. Not a legal notice. Say what happened, what of
theirs was involved, what we have done, what they might want to do, and that they can ask us
anything. Name a person, not an office.

> We need to tell you about something that went wrong on our side.
>
> On [date] we found that [plain description]. Your [what] was among the information involved.
> We [what we did] as soon as we knew, at [time].
>
> What this means for you: [concrete]. What we would suggest: [concrete, or "nothing you need to do"].
>
> We are sorry. You trusted this board with something and we did not hold it well enough.
> If you want to talk to a person about it, reply to this and you will get me, not a form.
>
> — [name]

**Never**: "out of an abundance of caution", "we take your privacy seriously", "no evidence of
misuse". If there is no evidence of misuse, say we do not know, because we do not.

⚖️ **Needs a lawyer:** US breach-notification duties are a state-by-state patchwork, and data about
health, immigration status, or minors can carry extra duties. Before a real breach notification goes
out, a lawyer should see it. That review does not delay the containment steps above.

---

## Part 2 — Someone official asks for data

### The four kinds of paper, and what each one actually compels

This is the most important table in this document. Read it before you need it.

| What arrives | Who signed it | What it compels |
|---|---|---|
| **A request** — an email, a phone call, an officer asking | nobody | **Nothing.** You may say no. You do not need a reason. |
| **An ICE administrative warrant** (Form I-200, I-205) | a DHS immigration officer | **Does not authorise entry into a private space, and does not compel us to hand over records.** It looks official and is not a judicial warrant. |
| **A subpoena** | often a lawyer or a clerk, not a judge | A legal process with deadlines, and one that can be **objected to or moved to quash**. It is not an order to comply on the spot. |
| **A judicial warrant / court order** | a **judge or magistrate**, with a **court named at the top** | Real compulsion, within the four corners of what it describes. |

**How to tell in ten seconds.** Look at the signature line and the top of the page. A judicial
warrant names a *court* and is signed by a *judge* or *magistrate*. An administrative warrant is
signed by an "Authorized Immigration Officer" or similar. If no judge signed it, it is not a
judicial warrant, whatever the word "warrant" on it suggests.

A nonprofit may designate which of its areas are public and which are private, and an administrative
warrant does not let anyone cross into the private ones without consent. Consent is the thing they
are usually asking for. It can be declined.

### The first five minutes — for whoever is standing there

1. **Be polite. Do not consent. Do not obstruct.** Do not block, touch, lie to, or argue with
   anyone. Do not hand over a laptop, a phone, a password, or a file.
2. **Say the holding sentence,** and nothing more:
   > "I'm not the person who can answer that. I'm not consenting to anything and I'm not refusing
   > anything — I'm going to call the person who handles this. Please wait here."
3. **Call the steward.** Immediately, whatever the hour.
4. **Ask for a copy of the paper**, or photograph it. If they will not give one, write down the
   agency, names, badge numbers, time, and what was said.
5. **Do not delete anything.** Not a file, not a message, not a record. See the next section.

### Who decides to refuse

**The steward decides. Nobody else, and never on the spot.**

A refusal is made in writing, by the steward or a lawyer, citing the specific reason — the demand is
overbroad, is not signed by a judge, seeks material we do not hold, or seeks material protected from
disclosure. It is not made by silence, by delay, or by a volunteer improvising at a door.

If the steward cannot be reached, the answer is the holding sentence, repeated. **Waiting is always
a permitted answer.** Nothing is lost by making someone come back with a judge's signature.

### ⚠️ Stop the deletion sweeps — this one is a trap

This board deletes on a schedule, by design, as a privacy feature. `docs/privacy-retention.md` sets
it out and these jobs enforce it:

`needs-shred-aged-pii` · `casework-shred-aged-cases` · `casework-stale-draft-cleanup` ·
`needs-expire-stale` · `matches-expiry-sweep` · `federation-sweep-contacts` ·
`federation-sweep-event-payloads` · `federation-sweep-shadows` — plus backups ageing out at
`RETENTION_DAYS` and the B2 lifecycle rule.

**Once a legal demand arrives, or litigation is reasonably foreseeable, routine deletion of anything
that might be relevant must stop.** Deleting on schedule after that point can be treated as
destruction of evidence — sanctionable *even when it is automatic and unintentional*, because the
duty attaches as soon as the matter is objectively foreseeable, not when a court says so.

Routine retention and a legal hold are different things. The first is a policy that runs on a timer.
The second is a reactive instruction that overrides it.

**What to do:** the steward stops the scheduled jobs (`django-q` schedules, and the backup cron)
before anything else, and writes down the time they were stopped and why. They stay stopped until a
lawyer says otherwise.

> **Known gap, stated plainly:** there is no legal-hold switch in this codebase today. Stopping the
> sweeps means stopping the scheduler by hand, which also stops deletion for people who are *not*
> involved and are entitled to it. A real hold needs to be scoped to the affected records. That is
> not built. Until it is, the honest move is the blunt one — stop everything, and un-stop it as soon
> as the scope is known.

### What we can and cannot produce

Case narratives, subject identities and on-behalf-of names are envelope-encrypted, and records past
their retention window are **crypto-shredded** — the per-record key is destroyed, so the ciphertext
cannot be read by us or by anyone else. That is a design property, not a defence, and the difference
matters:

- Data shredded **before** any demand or foreseeable dispute: gone in the ordinary course. Say so
  plainly, and be able to show the schedule that did it.
- Data shredded **after**: this is the trap above. Do not let it happen.

⚖️ **Needs a lawyer:** everything in Part 2. The distinctions here are accurate as general
information and are not a substitute for counsel on a specific demand. **Find that lawyer before
you need one** — a name in a phone, not a search at 7am.

---

## Part 3 — A meeting went wrong

Someone met a neighbour through this board and was hurt, threatened, robbed, or frightened.

1. **Their safety first.** If there is danger now, that is what emergency services are for. This
   board is not an emergency service and never claims to be — the terms at `/terms/` say so.
2. **They tell a coordinator, or use the report control** on the neighbour's ask or offer, or on
   their match.
3. **The coordinator can act immediately**, and does not need permission: hide the content, and
   remove the member (`apps/moderation` — removal cancels in-flight matches, takes their posts off
   the board, and is reversible by a coordinator, never a silent delete).
4. **The person harmed can block** that neighbour themselves, from the same screens. Blocking is
   preventative and is never announced to the person blocked.
5. **The steward is told within 24 hours**, and records it — what happened, what was done. Free
   text about the incident does **not** go into the append-only audit log, which cannot be corrected
   or erased.
6. **We do not investigate, mediate, or adjudicate.** We are not equipped to, and pretending
   otherwise would be its own harm. We remove, we document, and we point to people who are equipped.

We never tell the person who was reported who reported them.

---

## Part 4 — A scammer or an abuser on the board

Including — especially — a coordinator.

- **Any member** is reported and removed as in Part 3.
- **A coordinator** cannot be removed by the ordinary moderation path: `FlagResolveView` refuses
  coordinator and admin targets by design, so that one bad actor cannot purge the people watching
  them. **A coordinator is removed by an admin, or by the steward.** If the coordinator in question
  is the only coordinator, the steward acts directly.
- **If the steward is the problem**, there is no path today. That is the plainest statement of why
  gate item 6 is not optional, and it should stay written here, unhidden, until it is fixed.
- Where a pattern suggests deliberate exploitation of vulnerable people rather than one bad
  interaction, the steward tells the parish or sponsoring body, and considers whether it belongs
  with the police. ⚖️ Reporting duties may attach where a vulnerable adult or a minor is involved.

---

## What has to happen before this document is worth its paper

1. **A lawyer reads Part 1 and Part 2.** Ideally one who has acted for an immigrant-serving
   nonprofit. Get the name now.
2. **A second person exists** who can hold a role in Part 0. Everything here degrades to "call one
   man" until then (gate item 6).
3. **A scoped legal hold is built**, so preservation does not mean switching off other people's
   right to erasure (the known gap above).
4. **Someone reads the holding sentence out loud once**, so the first time is not the real time.

---

*This document is a promise about behaviour under pressure. If we find we cannot keep a part of it,
the honest response is to change it here, not to quietly fail it in the moment.*

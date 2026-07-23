# The UMI Protocol

**Version 0.1 — CANONICAL (keyed by the steward, 2026-07-14)**
United Moral Infrastructure · Steward: Jasiah Williams, United Moral Infrastructure (a nonprofit being
established as a 501(c)(3))

License: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). You may share and adapt this
document with attribution.

> **Status: CANONICAL v0.1.** This document was written *from* the reference implementation
> (`umi-exchange`): the citations throughout the codebase predate any written specification, so
> the specification was recovered from the behavior the code already enforces, then read and
> keyed by the steward. Section numbers are FIXED to
> [`citation-inventory.md`](citation-inventory.md) — 60 sections, 529 citations — so every
> existing reference resolves. **Change control:** this text is frozen at v0.1; any future edit
> ships as a new version keyed by the steward. [derived] markers record which intents were
> confirmed from design documents at the key (all confirmed, 2026-07-14); reserved sections
> remain non-normative for v0.1.

---

## §0 — Purpose, scope, and how to read this document

The UMI Protocol defines how a community coordinates **reciprocal aid** — neighbours asking,
neighbours answering — with dignity, consent, and privacy, and how independent instances may
connect with each other by consent rather than surveillance. UMI is the infrastructure ("the
pipes"); each community is the water. This document is the standard; `umi-exchange` is its
reference implementation, and anyone may implement the protocol independently.

**Requirement keywords** — MUST, MUST NOT, SHOULD, SHOULD NOT, MAY — are used per
[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

**Protocol versus implementation (the load-bearing distinction).** This specification governs
*wire behavior, data semantics, privacy invariants, and state machines*. It does NOT mandate an
implementation. Django, HTMX, Alpine, PostgreSQL, the specific cryptographic library, the HTML
templates — these are the reference implementation's **choices**, and a conforming implementation
MAY choose differently. When this document names a mechanism (for example "MultiFernet over a KEK
list"), it is describing the reference implementation as an existence proof; the normative
requirement is the *property* (rotation-ready authenticated encryption with per-record
crypto-shred), not the library.

**Conformance levels.** An implementation claims one or more levels; each level requires the
sections listed in [§13](#13--conformance). **Core** (§1, §6–§8, §10, §12) — the reciprocal aid
board. **Casework** (adds §3) — privacy-first intake and case records. **Federation** (adds §2,
§4.1, §5, §9, §11) — consented connection between instances. Each level MUST fully satisfy every
section it names; partial conformance MUST NOT be claimed.

---

## §1 — Entities

The Core entities are `Need` (an ask), `Offer`, `Match`, and `Consent`. A `Community` scopes them
all; a `Member` is a person's identity within one community, distinct from the authentication
`User` (this distinction is normative and load-bearing for §8.6).

- A `Need` MUST belong to exactly one community and carry a requester (a Member), a category, an
  urgency, a status, and an expiry.
- Personally identifying free-text on a Need (for example, the name of a third party a need is
  raised on behalf of) MUST be stored encrypted per §12, never in plaintext columns.
- A `Match` binds a Need to an Offer (or to a volunteering proposer with no standing Offer) and
  moves only through its state machine (§6).

**§1.4–§1.6 — Need classification** *[derived; DESIGNED, non-normative for v0.1]*. A need MAY
carry a classification (type, urgency inference, routing hints). The reference implementation
treats this as a future capability (`docs/design/mobile-companion-and-classifier.md`); it is
reserved here and imposes no requirement at v0.1.

---

## §2 — Identity and federation links *(Federation level)*

*[derived from `docs/federation-design.md`; verified against `apps/federation`.]*

- An instance has a stable cryptographic identity. Two instances connect only through a
  **pairwise, human-approved link** (§2.2): a one-time pairing code plus key-thumbprint
  verification, approved on both sides, with a bounded time-to-live.
- §2.3 — A link records the remote community's stable identifier and public key; nothing is
  shared by the mere existence of a link (link establishment is Stage A: identity only).
- §2.5 — A `Person` (the casework subject, distinct from Member and User) is never federated;
  Person identity is local to its instance.

---

## §3 — Casework and consent state *(Casework level)*

*[verified against `apps/casework`, `apps/consent`, `apps/people`.]*

- §3.2 — Sensitive case data MUST be encrypted at rest per §12.
- §3.5 — Entities with a lifecycle MUST change state only through an explicit transition function;
  invalid transitions MUST be refused (the reference implementation raises a `TransitionConflict`,
  surfaced as HTTP 409).
- §3.6 — **Consent revocation freeze (normative).** When a subject's consent is revoked, the
  implementation MUST stop new writes against that consent (no new notes, no export) and MUST
  re-check consent on any deferred or follow-up write. Revocation MUST take effect immediately for
  new actions; already-exchanged information is not retroactively recalled (it is treated the way
  a past conversation is).
- §3.7–§3.8 — Case opening MAY use an emergency override that permits a null consent at creation
  (a database-level constraint allows this only under the override flag); consent MUST then be
  regularized.
- §3.11 — Deployment MUST provision separate database roles so the append-only audit REVOKE
  (§8.3) binds the application's own runtime role.

---

## §4 — Consent semantics *(Core; §4.1 also Federation)*

- §4.1 — **One-action consent (normative).** Any disclosure beyond a community's own boundary
  MUST be an explicit, single, member-owned action. Coordinators MUST NOT consent on a member's
  behalf. Only a redacted outline (category, urgency, coarse locality, a coarse time bucket) MAY
  cross a boundary before an accepted match; names and contact details MUST NOT.
- §4.2–§4.3 — A consent record names its grantee, its scope (an explicit set of fields), its
  purpose, and its state; a scope check MUST verify that every requested field is within the
  granted scope.
- §4.4 — **Retention (the rule is protocol; the values are policy).** Aged data MUST be shed on
  a schedule, by crypto-shred (§12), not merely hidden, and the schedule MUST be bounded and
  published. The specific values are each implementation's POLICY, not protocol constants; as the
  existence proof, the reference implementation sheds aged-need PII at 365 days, closed casework
  at 7 years, and revealed contact snapshots at 72 hours. A conforming implementation MUST publish
  its actual retention and MUST NOT claim a retention it does not enforce.

---

## §5 — Federated sharing, discovery, and attestations *(Federation level)*

*[derived from `docs/federation-design.md`; verified against `apps/federation`.]*

- A member-owned share (§4.1) publishes only the redacted outline to linked communities.
- §5.4 — An instance MAY answer a signed, capability-gated **attestation** query about a member
  claim (for example, a verified tag). A self-reported claim MUST NOT be presented as verified.
- §5.8 — *[reserved]* A 72-hour hard-erasure target is named in design; the honest path is
  crypto-shred (§12). Until a conforming erasure is shipped, an implementation MUST state its
  actual retention rather than claim §5.8.

---

## §6 — Matching

- A Match moves `proposed → accepted | cancelled | expired`, and `accepted → fulfilled |
  unfulfilled | cancelled`. Terminal states MUST be enforced by the transition function (§3.5).
- §6.3 — *[Federation]* Cross-instance match state is re-synced by a signed GET of the authority
  instance's signed match state; item failures MUST NOT roll back siblings (§9.1).

---

## §7 — Self-match boundary

- §7 — An implementation MUST prevent self-matching across BOTH identity axes: the proposer's
  Member and the underlying User. For federated matches, a **blind self-match token** MUST allow
  the authority to detect a self-match without learning the counterpart's identity.

---

## §8 — The exchange (the peak) *(Core)*

- §8.2 — **Contact revelation (normative; the most-cited rule in the system).** Contact
  information MUST be revealed only after a match is accepted, and only to the match's
  participants and the community's coordinators. A volunteer who proposed without a standing Offer
  counts as a participant. Every disclosure MUST be audited (§8.3). No party outside this set MUST
  be able to obtain contact information through the match.
- §8.3 — **Append-only audit (normative).** The audit log MUST refuse UPDATE and DELETE at the
  application layer AND at the database layer (a REVOKE of UPDATE/DELETE/TRUNCATE on the audit
  table from the runtime role). Client IP MUST be stored as a salted hash, never raw, and MUST be
  read from the trusted reverse-proxy header, never the spoofable left-most `X-Forwarded-For`.
  Audit actions MUST be short (the reference implementation caps at 32 characters) and MUST NOT
  contain PII.
- §8.6 — **Self-match prevention (normative).** Proposer MUST NOT equal requester, and offer-owner
  MUST NOT equal requester, checked on both Member and User identity (§7).
- §8.7 — **Concurrency (normative).** A match acceptance MUST lock the contended rows so a second
  concurrent acceptance fails cleanly (the reference implementation locks the Match and Need rows
  and returns HTTP 409 on the loser). Contended writes MUST NOT double-accept.

---

## §9 — Federated delivery *(Federation level)*

*[derived from `docs/federation-design.md`; verified against `apps/federation`.]*

- §9.1 — Delivery is per-item: each item is its own transaction; one item's failure MUST NOT roll
  back its siblings.
- §9.2 — A discovery/query signature MUST bind the request's parameters, so a captured signature
  cannot be replayed against different parameters.
- §9.3 — Outbound federation events MUST be queued inside the transaction that owns the state
  change they describe, and idempotent replays MUST re-carry their side effects.

---

## §10 — Board operation *(Core)*

*[verified against `apps/needs`, `apps/accounts`, `apps/people`.]*

- §10.1–§10.2 — Search and feed MUST be community-scoped; a query MUST NOT return another
  community's content.
- Authentication endpoints MUST be rate-limited (the reference implementation throttles register
  and login per trusted IP).
- §10.6 — Needs and offers MUST expire on a schedule.
- §10.7 — Expiry and erasure of PII-bearing records MUST use crypto-shred (§12), not a soft hide.

---

## §11 — Rate and retention caps *(Federation level)*

- §11 — Federation endpoints MUST enforce per-peer wire caps (a bounded number of requests per
  period). Retention numbers for federated artifacts (shadow-record TTL, contact retention) MUST
  be bounded and published (values [derived]: shadow TTL 7 days; contact retention terminal on
  the local rule).

---

## §12 — Encryption and crypto-shred *(Core)*

*[verified against `apps/people/crypto.py`.]*

- §12.1 — Encrypted state transitions MUST go through the state machine (§3.5).
- §12.2 — **Envelope encryption (normative).** PII fields MUST be encrypted with a per-record data
  key (DEK) that is itself wrapped by an environment-level key (KEK) list supporting rotation.
  Reading or writing an encrypted field MUST occur only through its model property; raw ciphertext
  columns MUST NOT be read or written directly. **Crypto-shred**: deleting a record's PII MUST null
  BOTH the ciphertext AND its wrapped DEK, rendering the record permanently unrecoverable, so that
  a shred is a true erasure and any census of encrypted fields stays clean.
- §12.3 — **Blind index** *[reserved; DESIGNED, non-normative for v0.1]*. A deterministic keyed
  index over a name field, for equality lookup without decryption, is named in design and drafted
  in a gated branch. It imposes no requirement at v0.1; when shipped it becomes normative under a
  new version.

---

## §13 — Conformance

An implementation MUST satisfy every section named by each level it claims.

| Level | Requires |
|---|---|
| **Core** | §0, §1, §6, §7, §8, §10, §12 |
| **Casework** | Core + §3 |
| **Federation** | Core + §2, §4.1, §5, §9, §11 |

`§4` consent semantics beyond §4.1 apply wherever consent is recorded. Reserved sections
(§1.4–§1.6, §5.8, §12.3) impose no requirement at v0.1. An implementation claiming a level MUST
NOT claim it on partial satisfaction.

---

## Appendix A — Non-normative: future directions

Need classification (§1.4–§1.6), hard-timed erasure (§5.8), and the blind index (§12.3) are
directions the reference implementation is moving toward, not requirements of v0.1. Lakes beyond
the board and casework (a skills directory, a pantry tracker, pastoral messaging, and others) are
future protocol surfaces and are out of scope for this version.

## Appendix B — Non-normative: reference implementation notes

The reference implementation is `umi-exchange`: Django 5.2, PostgreSQL, Redis, HTMX, Alpine,
Tailwind, WhiteNoise, Argon2. These are choices, not requirements (§0). The traceability table
([`traceability.md`](traceability.md)) maps each normative requirement above to the code and tests
that enforce it in the reference implementation.

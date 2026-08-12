# Governance — more than one person, written down

> STATUS: DESIGN + appointment checklist, written 2026-08-11 for ethics-gate item
> "Governance extends beyond a solo steward." Written to be read aloud at a parish board
> meeting. The box ticks when the people below actually hold what this page says they
> hold — not when the page merges.
>
> The gate's own words: done when more than one person holds real authority over the live
> instance — access to the data, custody of the keys, and the power to refuse a demand —
> with a written path for succession and for removing someone who abuses the trust.

## The roles (names to be appointed; titles are the design)

| Role | Who (pilot) | What they actually hold |
|---|---|---|
| **Steward** | Jasiah (founder) | Runs the software: deploys, admin seat, key custody day-to-day. |
| **Pastor** | the parish pastor | The ministry's authority: can HALT the board outright, names and removes coordinators and the steward's ministry mandate, co-holds refusal power. |
| **Keeper of the envelope** | parish office (pastor + one named trustee, e.g. the Sister) | Break-glass custody of the sealed key envelope (see `docs/key-custody-design.md`). Two-person act to open, always logged. |
| **Coordinators** | named parishioners, gathered by the steward at the pastor's request | Day-to-day care: propose matches, see accepted connections for safety, freeze/remove an account that harms someone (every act on the audit record). |

That table, filled with real names, is the whole point: after it is filled, no single
person is the entire trust boundary — including the founder.

## The powers, explicitly

- **Halt.** The pastor can order the board paused for the parish at any time, no technical
  skill required: one phone call to the steward, and the deploy runbook's stop command. If
  the steward is unreachable, the envelope path exists.
- **Refuse.** An overbroad or unlawful demand for data (subpoena, immigration enforcement,
  bulk requests) is refused by the path already written in `docs/incident-response.md` —
  the steward and the pastor decide together, counsel is engaged before any data moves,
  and affected neighbours are told. Neither the steward alone nor the pastor alone hands
  over data.
- **Freeze.** A coordinator or the steward can freeze an account that is scamming or
  harming someone (incident-response covers the in-person-harm path). Freezes are audited
  and reviewed by the pastor at the next board meeting.
- **Complain past the steward.** A parishioner who has a problem WITH the steward or the
  software goes to the pastor or the parish office directly — a path that does not route
  through the person being complained about. The pastor can act on it (see Remove).

## Succession and removal

- **If the steward is gone** (illness, departure, anything): the envelope + the runbooks
  are the hand-over. A successor technologist appointed by the pastor opens the envelope
  (two-person act), rotates keys the same week (`rotate_keks`), and takes the steward seat.
  The software is AGPL and self-hosted precisely so the parish is never hostage to one
  person.
- **If the steward abuses the trust**: the pastor removes the ministry mandate (that is
  his authority, not a technical act), the envelope path + key rotation revoke technical
  hold, and the audit log — which refuses UPDATE and DELETE by design — is the record of
  what was done. The same applies in miniature to a coordinator: named by the pastor,
  removable by the pastor, every sensitive act they took is on the record.

## Appointment checklist (done-when for the gate box)

- [ ] Pastor's halt + refusal roles stated to him in these words and accepted (Sept 15
      board meeting is the natural moment).
- [ ] Envelope sealed and in the safe; keeper(s) named in writing.
- [ ] At least one coordinator beyond the steward appointed and holding a real coordinator
      seat on the live instance.
- [ ] This page updated with the real names and the date; incident-response cross-checked
      so the names match there too.
- [ ] Then, and only then: tick the governance box in `docs/ethics-and-safety.md`
      (separate commit, steward's merge, pastor informed).

# Privacy & Retention Policy — internal source of truth

> STATUS: policy set by Jasiah 2026-07-11 ("retention yes" on the proposed defaults).
> Public plain-language version: `/privacy/` (`templates/pages/privacy.html`).
> Rule for both documents: **a promise only belongs here if code enforces it.**

## The schedule (all BUILT unless tagged)

| Data | Kept | Then | Enforced by |
|---|---|---|---|
| Erasure request (§5.8) | — | crypto-shred within 30 days + account deactivated | envelope DEK deletion (built); the 30-day SLA is operational (coordinator/admin action) |
| `Need.on_behalf_of` on terminal needs (fulfilled/closed/expired) | 12 months | crypto-shred, both columns | `apps.needs.tasks.shred_aged_need_pii`, DAILY |
| Casework narrative on closed cases (summary, emergency justification, notes, follow-ups, handoffs) | 7 years from `closed_at` | crypto-shred, both columns; consent revocation freezes the case immediately (built, §3.9) | `apps.casework.tasks.shred_aged_cases`, DAILY |
| Federation contact payloads | fulfilled + 72 h | crypto-shred both sides | federation retention sweep (built, Stage C) |
| Local match contact | not stored | reveal renders live from the member's own profile; nothing separate to shred | by construction |
| Backups | 30 days (`RETENTION_DAYS`, `scripts/backup.sh`) | aged out locally + B2 lifecycle rule; after age-out a shred is absolute | backup.sh + B2 bucket rule |
| Audit log | kept indefinitely | PII-free by design; IPs stored as salted hashes only | `apps.audit` emit discipline + append-only REVOKE |

## Notes

- **Both envelope columns are nulled** (ciphertext AND DEK), not the DEK alone:
  Stage E getters fail loud on ciphertext-without-DEK, and the envelope censuses
  (`casework_envelope_status`, `migrate_on_behalf_envelope --verify`) count that
  state as unreadable/error. Nulling both keeps reads returning `None` and the
  censuses clean. The privacy effect is identical (content unrecoverable).
- **Bulk `.update()` in the casework shred is deliberate** — finalized notes
  refuse `save()` edits by design; a policy shred is not an edit. One audit row
  per case with PII-free counts.
- Free-text titles/descriptions of needs and offers are member-authored,
  community-visible content and are **not** in the shred schedule; they fall
  under account erasure instead. (DESIGNED: revisit if a pilot shows titles
  carrying third-party PII.)
- The public page and this doc must change together; the mission-page tests pin
  the public copy's key claims.

# UMI Protocol v0.1 — traceability

> Each normative requirement in [`spec.md`](spec.md) → the code and tests that enforce it in the
> reference implementation. This is the evidence that the spec documents *implemented behavior*,
> not aspiration. Rows marked **[derived]** rest on design docs verified against code, awaiting
> the steward's confirmation of intent; unmarked rows are directly verified. Full citation
> evidence: [`citation-inventory.md`](citation-inventory.md).

| § | Requirement | Enforced by | Tested by |
|---|---|---|---|
| §1 | Member ≠ User identity | `apps/communities/models.py` (Member), `apps/accounts/models.py` (User) | `tests/test_matches.py` (self-match) |
| §3.5 | State only via transition fn; invalid → 409 | `apps/common/state.py::StateMachineMixin`; `apps/matches/models.py::transition_to` | `tests/test_matches.py` |
| §3.6 | Consent revocation freeze | `apps/casework` consent gating; `apps/consent` | `apps/casework/tests/` (revocation) |
| §3.11 | Separate DB roles for audit REVOKE | `manage.py restrict_audit_permissions`; `docs/deployment-checklist.md` | deploy check |
| §4.1 | One-action, member-owned share; coordinators cannot consent for a member | `apps/federation/sharing.py`; `apps/federation/views.py`; `apps/casework/views.py` (intake records `subject_person` + `recorded_by`, never the coordinator as grantor); `apps/consent/models.py` | `apps/federation/tests/`; `apps/casework/tests/test_onbehalf_consent.py` |
| §4.2–4.3 | Consent scope check | `apps/consent/models.py::Consent.covers()` | `apps/consent/tests/` |
| §4.4 | Retention crypto-shred sweeps (365d/7y/72h) | retention sweep tasks; `docs/privacy-retention.md` | retention tests |
| §5.4 | Attestation query; self-reported ≠ verified | `apps/federation` attestations; `apps/tags/models.py` | `apps/tags/tests/`, `apps/federation/tests/` |
| §6 | Match state machine terminal enforcement | `apps/matches/models.py::transition_to` | `tests/test_matches.py` |
| §6.3 | Signed re-sync GET | `apps/federation/client.py:163` | `apps/federation/tests/test_outbox.py` |
| §7 | Blind self-match token (federation) | `apps/federation` proposal token | `apps/federation/tests/` |
| §8.2 | Contact revealed only post-accept, to participants+coordinators, audited | `apps/matches/views.py`; `apps/audit/services.py::emit` | `tests/test_matches.py`, `tests/test_views.py` |
| §8.3 | Append-only audit (app + DB REVOKE); salted-SHA-256 IP; trusted X-Real-IP | `apps/audit/models.py`; `apps/audit/migrations/0002_append_only.py`; `apps/audit/services.py` | `tests/test_audit*.py` |
| §8.6 | Self-match prevention on Member AND User | `apps/matches/views.py:52-61` | `tests/test_matches.py` |
| §8.7 | Accept locks contended rows; 409 on loser | `apps/matches/views.py` (`select_for_update(of=("self",))`) | `tests/test_matches.py` (concurrency) |
| §9.1 | Per-item transaction, no sibling rollback | `apps/federation` SyncView `_one` | `apps/federation/tests/test_outbox.py:397` |
| §9.2 | Signature binds query params | `apps/federation/crypto.py:204` | `apps/federation/tests/` |
| §9.3 | Outbox queued in owning txn; idempotent replays re-carry effects | `apps/federation/outbox.py` | `apps/federation/tests/test_outbox.py` |
| §10.1–2 | Community-scoped search/feed | `apps/needs/views.py`, `apps/communities/views.py` | `tests/test_search*.py` |
| §10 | Auth endpoints rate-limited | `apps/accounts/ratelimit.py` | `apps/accounts/tests/` |
| §10.6–7 | Scheduled expiry via crypto-shred | expiry tasks; `apps/people/crypto.py` | retention/expiry tests |
| §11 | Per-peer wire caps | `apps/federation/views.py:43` | `apps/federation/tests/` |
| §12.2 | Envelope encryption; property-only access; crypto-shred nulls ciphertext+DEK | `apps/people/crypto.py` (`envelope_encrypt_str`, `encrypt_str`) | `apps/people/tests/`, `apps/casework/tests/` |
| §12.3 | Blind index — RESERVED, non-normative v0.1 | `person_name_bidx` (DESIGNED, gated PR) | n/a |

**Rows that are [derived]** (design-doc-attested, verified against code, steward confirms intent
at key): §2.x, §4.1 boundary field list, §4.4 exact values, §5.x, §6.3, §7 token, §9.x, §11
values. All §8 and §12.2 rows are directly verified — the core of the system.

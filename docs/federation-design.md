# UMI Federation — Design Document (v1)

> **STATUS: DESIGNED — nothing in this document is built.** No code, no migrations, no wire
> endpoints exist. Federation is confirmed **not reachable** in the current codebase (the only
> reference is a comment in `apps/tags/models.py:25`); the pre-pilot threat model
> (`docs/threat-model.md`, PR #32) requires it stay code-absent until separately threat-modeled —
> **this document is that threat model + design.** Implementation starts only after Jasiah approves
> the staged plan at the end.
>
> Tags used throughout: **BUILT** (exists in code today, cited), **DESIGNED** (specified here,
> unbuilt), **DECISION-NEEDED** (Jasiah must choose; recommended default given).
>
> **Decision log:** 2026-07-02 — Jasiah answered all 8 open questions (§13): **every recommended
> default accepted.** Former DECISION-NEEDED items below are marked DECIDED with the chosen option.

## 0. Sources and citation discipline

The UMI Protocol v1.0 and the Lakes Operating Manual are **not in this repo** (`docs/` carries only
`umi_dev_security_protocol.md`, `network-security-addendum.md`, and generated/design docs). This
document therefore cites a protocol/manual section **only where the code or a present doc already
cites it** — the verified inventory: §8.2 / §8.3 / §8.6 / §8.7 (matches, needs, offers views +
templates), §10.1 (audit emitter), §10.2 (consent grantee + `covers()`), §10.5 + Manual §5.6
(rate limiting), §10.6 (expiry), §10.7 + §12.2 (crypto-shred / envelope), §12.1 (state-machine
mixin), §12.3 (blind index, unbuilt), Manual §5.3 (4-hour re-auth), Manual §5.8 (72-hour erasure,
cited in `docs/INTEGRATION-PLAN.md:59`), and the casework design §3.x family. Every other rule in
this document is marked **DESIGN DECISION (not in sources)** with a proposed default. No section
numbers are invented.

## 1. Principles and the built reality this design stands on

**Principles (non-negotiable):** consent, not surveillance; nobody owns the pipes. Standalone-first
— every community works fully without federation. Opt-in **per community AND per record**, default
OFF. No central authority, no shared database: sovereign instances, peer-to-peer; any directory is
optional and untrusted. Data minimization: only redacted, non-identifying data is discoverable;
identity/contact follow §8.2 across instances; no PII in logs or audit rows.

**What exists to build on (all BUILT, verified in code):**

| Capability | Where | Reused for |
|---|---|---|
| Match state machine `proposed→accepted→fulfilled/…` with `VALID_TRANSITIONS` + `transition_to()` | `apps/matches/models.py:22-108` | cross-instance match rides the same machine |
| §8.6 self-match prevention (Member **and** User identity) | `apps/matches/views.py:52-61` | boundary problem in §7 below |
| §8.7 pessimistic locking + 409 (`select_for_update(of=("self",))` on Match, lock on Need, double-accept guard) | `apps/matches/views.py:143-187` | home-of-need is the lock authority |
| §8.2 contact shape `Member.contact_dict(pref)`; reveal gated to `accepted/fulfilled` participants + coordinators | `apps/communities/models.py:119-127`, `apps/matches/models.py:116-163` | the only contact payload that ever crosses |
| Consent model with `grantee_type="community"`, nullable `grantee_id`, JSON `scope`, `covers()` (§10.2) | `apps/consent/models.py:9-70` | federated-share consent; `covers()` gets its **first enforcement call site** |
| Append-only audit, `emit(action ≤32 chars, resource, …)`, salted-SHA256 IP hashes (§10.1) | `apps/audit/services.py:37-48`, `apps/audit/models.py:13-40` | every cross-instance event, both sides |
| Envelope encryption: per-record DEK wrapped by env-level MultiFernet KEK; paired `BinaryField` + property; crypto-shred nulls ciphertext+DEK (§12.2/§10.7) | `apps/people/crypto.py`, `apps/needs/models.py:31-80`, `shred_on_behalf.py:33-36` | shadow records on a receiver are envelope-encrypted **under the receiver's keys** |
| Hand-rolled JSON wire pattern: `SyncView` — `json.loads(request.body)`, batch cap 50, HTTP-200 envelope with per-item `status`, `client_uuid` unique-constraint idempotency + IntegrityError re-fetch | `apps/casework/views.py:582-662`, `apps/casework/models.py:177` | the federation wire protocol copies this exactly; **no DRF** (removed PR #16; zero `rest_framework` imports) |
| Fixed-window rate limiting `check()` / `rate_limit()` on Django cache (§10.5/Manual §5.6) | `apps/accounts/ratelimit.py:26-106` | per-link throttles |
| Tag verification tiers `self_serve / coordinator_verified / admin_verified` + audited state machine | `apps/tags/models.py:41-45,103-363` | attestations (§5.4) are derived from MemberTag — **no new badge model** |
| django-q2 (ORM broker, works without Redis) | `config/settings/base.py:59-64` | outbound delivery queue + retries |
| StateMachineMixin (§12.1 seed) | `apps/common/state.py` | FederationLink / FederatedShare state machines |

**What does NOT exist:** any outbound HTTP client (grep across `apps/`+`config/`+`scripts/` finds
zero `requests`/`httpx`/`urllib` call sites — email via Django core mail is the only egress); any
instance-level identity or keypair; any `visibility`/sharing field on Need/Offer; audit of consent
revocation (`ConsentRevokeView`, `apps/consent/views.py:24-32`, writes **no audit row** today).
Federation introduces all four — the revocation-audit gap gets fixed as part of Stage B.

---

## 2. Pillar 1 — Cross-community discovery (DESIGNED)

### 2.1 Topology: pull, peer-to-peer, directory optional
- **Pull, not push** (DESIGN DECISION, not in sources): a peer polls
  `GET /federation/v1/discovery` on each active link (default every 15 min via django-q2).
  Rationale: push requires the receiver to accept unsolicited writes (larger authz surface);
  pull means an unreachable peer degrades to "stale listings", never to data loss; and the
  home instance serves only what is currently shared — revocation is effective at the next poll
  *and* is pushed best-effort (§4.3).
- **Pure P2P by default.** A link is a pairwise, human-approved relationship (§3). No directory
  is required for any federation function.
- **Optional directory (deferred, Stage E):** a plain HTTPS host serving signed instance documents
  (the same `/.well-known/umi-federation` payload, JWS-signed by each instance). It holds **only
  non-identifying instance entries** (base URL, public key, locality label, capability list) —
  never needs/offers, never people. Instances run fully without it; it can vouch for nothing
  (key pinning still happens at human approval time).

### 2.2 What is discoverable vs never exposed
Per shared record, the discovery payload is exactly:

| Field | Source | Redaction rule |
|---|---|---|
| `kind` | `"need"` or `"offer"` | — |
| `remote_uuid` | new random UUID minted per share (NOT the local pk) | unlinkable to local ids |
| `category` | `Category` slug/label (BUILT: FK on Need/Offer, `apps/needs/models.py:24`) | slugs only |
| `urgency` | Need only (`low/medium/high/critical`, `apps/needs/models.py:11`) | as-is |
| `locality` | **community-level** coarse label set by the admin in federation settings | never `Need.neighborhood` (free text, de-anonymizing — stays local) |
| `freshness` | ISO week bucket of `created_at` | day precision withheld |
| `radius_km` | Offer only (`apps/offers/models.py:25`) | as-is (already coarse) |

**NEVER in discovery:** `title`, `description` (free text is de-anonymizing), requester/offerer
identity, `display_name`, contact fields, `on_behalf_of` (envelope-encrypted PII), `neighborhood`,
member counts, or any per-person data. Titles cross only at the proposal phase (§5.2), contact only
post-accept (§5.3, §8.2).

### 2.3 Opt-in, default OFF (load-bearing containment)
1. **Instance level:** `FEDERATION_ENABLED = False` Django setting. When False, the federation app
   registers no URLs — the surface is absent, matching the threat model's "keep it code-absent"
   posture as closely as a built feature can (routes-absent).
2. **Community level:** `Community.settings["federation"]["enabled"] = false` default (settings is
   an existing JSONField, `apps/communities/models.py:50` — no migration needed for the toggle).
   Admin-only UI (mirrors `CommunitySettingsView` gate, `apps/communities/views.py:179-190`).
3. **Record level:** new `share_scope` field on Need and Offer, default `"local"`; the creation
   forms show a "share beyond this community" checkbox **only** when the community has federation
   enabled and at least one active link exists. Sharing additionally requires a Consent (§4.1).
   A record is discoverable to a given peer only if: instance ✓ AND community ✓ AND record ✓ AND
   link active ✓ AND consent active ✓.

---

## 3. Pillar 2 — Handshake and trust (DESIGNED)

### 3.1 Instance identity
- Each instance holds one **Ed25519 keypair** (DESIGN DECISION). Private key lives in the
  environment beside `ENCRYPTION_KEYS`, validated at boot by the production fail-fast block
  (pattern: `config/settings/production.py:19-29`). Public key is published as a JWK; the
  **instance id = RFC 7638 JWK thumbprint**.
- `GET /.well-known/umi-federation` (public, unauthenticated, cacheable) returns the **instance
  document**: `{"umi_federation": "1", "instance_id": <thumbprint>, "jwk": {...}, "capabilities":
  ["discovery","match","attestation"], "software": {"name": "umi-exchange", "version": ...},
  "locality": <coarse label>, "contact": <admin route, not a person>}` — self-signed (JWS,
  `alg: Ed25519`).

### 3.2 mTLS vs HTTP Message Signatures vs JWS — evaluation and recommendation
Weighted by **operator burden**: the operator is a parish tech volunteer (UFW + Tailscale level —
`docs/network-security-addendum.md` targets exactly this persona), typically behind a reverse
proxy with Let's Encrypt.

| Option | Security fit | Operator burden | Library reality (Context7-checked 2026-07-02) |
|---|---|---|---|
| **mTLS** | strong mutual auth at transport | **sinks self-hosters**: client-cert issuance/renewal/revocation on both sides, reverse-proxy passthrough config, CA hygiene — a cert lapse silently severs aid links | n/a (proxy-level) |
| **HTTP Message Signatures (RFC 9421)** | right shape (signs method/path/headers/body) | moderate | **no maintained Python implementation surfaced** — dependency risk too high to anchor a protocol on |
| **JWS signed envelope (recommend)** | equivalent guarantees when the signed claims bind method+URL+body digest+time+nonce | zero beyond env keys — TLS stays ordinary Let's Encrypt server-auth | `joserfc` (authlib family): Ed25519 OKP keys, `jws.serialize_compact`/`deserialize_compact` with fully-specified `alg: "Ed25519"` (RFC 9864 name; `EdDSA` deprecated), JWK import/export — depends only on `cryptography`, already pinned `>=42.0` in `requirements.txt` |

**Recommendation: JWS envelope over TLS.** Every federation request (except `/.well-known`) carries
`X-UMI-Signature: <JWS compact>` whose payload is:

```json
{"iss": "<sender instance_id>", "aud": "<receiver instance_id>",
 "iat": 1730000000, "jti": "<uuid4 nonce>",
 "htm": "POST", "htu": "https://peer.example/federation/v1/proposals",
 "digest": "sha256:<base64 of request-body hash>"}
```

Receiver verification order: TLS ok (transport) → `aud` is me → `iss` maps to an **active**
FederationLink and the signature verifies against the **pinned** JWK → `iat` within ±300 s →
`jti` unseen (cache `fed:jti:<iss>:<jti>` with 600 s timeout — same fixed-window cache
infrastructure as `apps/accounts/ratelimit.py:46-56`) → body digest matches. Any failure → 403
`{"error": "bad_signature"}` + `emit("fed.sig_rejected", link, details={"reason": ...})` — no
retry hint. This is replay-protected, MITM-protected (TLS + digest binding), and impersonation-
protected (key pinned at human approval, §3.3). **New runtime dependency: `joserfc`** — justified
under the no-new-deps rule as the only maintained JOSE implementation; single transitive dep
(`cryptography`, already present). Fallback if rejected: raw Ed25519 via `cryptography` with a
hand-rolled envelope — more code we own, same primitives. **DECIDED 2026-07-02: add `joserfc`.**

### 3.3 Handshake — human approval on both sides, always

```text
Instance A (admin Alice)                        Instance B (admin Bob)
------------------------                        ----------------------
1. Alice: "Add peer" → enters B's base URL
2. A GET /.well-known/umi-federation  ───────►  serves instance doc (public)
3. A verifies doc self-signature; shows Bob's
   instance_id THUMBPRINT + locality to Alice
4. Alice confirms → A stores FederationPeer
   (pending) + mints pairing_code (8 chars,
   CSPRNG — same recipe as Community.join_code,
   apps/communities/models.py:32-36)
5. A POST /federation/v1/handshake ──────────►  B stores inbound request as
   {instance doc A, pairing_code_hash,           FederationPeer(pending) —
    requested_communities: [locality labels]}    NOTHING is shared yet
6.        == OUT-OF-BAND: Alice phones/emails Bob the pairing code and they
             read each other's key thumbprints aloud (MITM/impersonation kill) ==
7. Bob: admin UI "Approve peer" → enters code;
   B verifies hash, pins A's JWK        ◄─────  link B→A: active
8. B POST /federation/v1/handshake/confirm ──►  A verifies (signed with B's key
                                                 A already fetched+displayed),
                                                 pins B's JWK; link A→B: active
9. Both sides: emit("fed.link_approved", link, user=<approving admin>)
```

- Each side's link approval is a **manual admin action** (role gate = `member.is_admin`, the
  existing pattern at `apps/communities/views.py:243-246`). No auto-federation, ever.
- **Link state machine** (StateMachineMixin, §12.1): `pending → active → suspended ⇄ active`,
  `pending/active/suspended → revoked` (terminal). `suspended` stops all traffic but keeps keys
  (operator pause / incident response); `revoked` requires a fresh handshake to resume.
  Revocation is unilateral, effective immediately on the revoking side (inbound sigs from that
  peer 403), and notified best-effort: `POST /federation/v1/links/revoke` (signed) so the far
  side flips too. Both sides `emit("fed.link_revoked", link)`.
- **Key rotation:** peer publishes new JWK in its instance doc signed by the OLD key +
  `POST /links/rekey` (signed old key, body carries new JWK). Receiver requires admin
  re-confirmation of the new thumbprint in the UI (DESIGN DECISION: human-in-the-loop on rekey,
  because silent rotation is what a key thief would do).

### 3.4 Threat model (inherits `docs/threat-model.md` PR #32; federation is its "city-scale" spread vector)

Containment posture carried over and made **load-bearing**: default-OFF at three levels (§2.3),
per-link human approval (§3.3), data minimization (§2.2), short-TTL shadows (§4.4). The pre-pilot
must-fix list stays binding: federation ships only after must-fix #1 (audit-table role) and #4
(DV→restricted) are operationally confirmed, and PR #34 (join throttle + IDOR suite) is merged.

| Threat | Scenario | Mitigations (all DESIGNED unless noted) |
|---|---|---|
| **Malicious peer (approved, then hostile)** | harvests discovery to profile a community; probes proposals | minimization (§2.2 — no identity/free-text pre-accept); per-link rate limits (§10); per-record consent; suspend/revoke + audit trail both sides; §8.2 gate means at most the contact dicts of members who accepted a match with *that* peer are ever exposed |
| **Compromised peer (key theft / server takeover)** | replays or mints signed requests; reads shadows it legitimately received | replay: `jti` + `iat` window (§3.2); blast radius = whatever that link already had — bounded by TTL'd shadows, no bulk export endpoint, batch caps (50, mirroring `SyncView`); revoke link → immediate 403; receipts (§4.2) let the home side prove what was and wasn't consented |
| **Instance impersonation** | fake "St. Mary's" instance | key pinned at approval after out-of-band thumbprint read-back (§3.3 step 6); `aud` binding stops forwarding a signed request to a third instance |
| **Replay** | captured request re-sent | `jti` nonce cache + ±300 s `iat` + body digest (§3.2) |
| **MITM** | TLS strip / proxy tamper | HTTPS mandatory (HSTS preload already in `production.py`); signature covers method+URL+body digest, so even a TLS-terminating middlebox can't alter payloads undetected |
| **Exfiltration at scale ("city-scale" harvest)** | one compromised hub drains many parishes | there is no hub — pairwise links only; each link is human-approved, rate-limited, minimized; a peer never holds bulk PII, only redacted discovery rows + post-accept contact dicts under ITS OWN envelope keys with TTL |
| **Spam / DoS** | proposal floods, discovery hammering | per-link fixed-window throttles (§10) on top of per-IP; unauthenticated surface is only `/.well-known` (cacheable) + `handshake` (5/hr/IP); batch caps; `suspended` state |
| **Sybil** | many fake instances request links | admin approval per link IS the Sybil filter in v1 (no transitive trust, no directory-derived trust); directory (Stage E) signs entries but explicitly vouches for nothing |
| **Malicious content in-band** | XSS via shared category/title at proposal | all inbound strings length-capped + validated against local choices (the `SyncView` pattern: whitelist against `KIND_CHOICES` etc., `apps/casework/views.py:617-630`); templates autoescape (Django default); titles rendered as text, never HTML |

---

## 4. Pillar 3 — Consent propagation (DESIGNED)

### 4.1 A federation scope on the existing Consent (§10.2 — no new consent model)
- Sharing a record creates/reuses a `Consent` row: `participant` = the requester/offerer's user,
  `grantee_type="community"` (existing enum, `apps/consent/models.py:17-25`), `grantee_id` = the
  **peer community's remote UUID**, `granted_to` = peer's display label, `scope=["federated_share"]`
  (new conventional scope value in the existing JSON list), `method="digital"`, optional
  `expires_at`.
- Enforcement wires `Consent.covers(grantee_type="community", grantee_id=<peer>,
  scopes=("federated_share",))` (`apps/consent/models.py:60`) into the share path — the first
  real call site of `covers()` in the codebase (today it has none — noted in §1).
- UX: the share checkbox on the Need/Offer form IS the digital consent capture (one action,
  recorded as a Consent row + `emit("fed.share_created", share, user=...)`).

### 4.2 Signed consent receipts — consent travels with the record
Every shared record carries a **consent receipt**: a JWS (home instance key) over
`{"receipt_id": uuid, "consent_id": uuid, "record": "<kind>:<remote_uuid>",
"scope": ["federated_share"], "granted_at": ..., "expires_at": ...|null,
"home": "<instance_id>", "peer": "<instance_id>"}`.
The receiver verifies it against the pinned home JWK before persisting any shadow row
(invalid/missing → item-level `{"status":"error","error":"receipt_invalid"}` +
`emit("fed.receipt_invalid", link)`), stores the JWS string beside the shadow, and can later
**prove** what it holds was consented — and the home side can prove exactly what it granted.

### 4.3 Revocation — stop, notify, audit both sides; erasure is cooperative
On revoke at home (participant clicks revoke — existing `ConsentRevokeView` flow,
`apps/consent/views.py:24-32`, extended):
1. Consent → `revoked` (BUILT behavior) **+ new audit** `emit("fed.share_revoked", share, ...)` —
   and, independent of federation, revocation of ANY consent starts emitting (fixes the audit gap
   named in §1).
2. All FederatedShares under that consent → `revoked`; the record disappears from the next
   discovery response immediately (pull model, §2.1).
3. Home queues a **signed delete-request**: `POST /federation/v1/consent/revocations`
   `{"receipt_id": ..., "record": ..., "reason": "consent_revoked"}` with django-q2 retry/backoff
   (§9.3). `emit("fed.consent_revoke_sent", share)`.
4. Peer, on receipt: verifies signature → **SHOULD crypto-shred** the shadow row (null ciphertext
   + wrapped DEK — the exact `shred_on_behalf` recipe, `apps/needs/management/commands/
   shred_on_behalf.py:33-36`) → `emit("fed.consent_revoke_received", shadow)` +
   `emit("fed.shadow_shredded", shadow)` → replies `{"status":"shredded"}`. Home records the ack
   in the share row.

**Stated plainly: cross-instance erasure is best-effort, not guaranteed.** A shadow on the
receiver is encrypted **under the receiver's KEK/DEK** (that is the correct sovereignty design —
otherwise the home instance could remotely destroy a peer's database), so home-side crypto-shred
(§10.7/§12.2) cannot reach it, and a hostile receiver can simply keep data. This is unlike local
crypto-shred, which IS guaranteed. The design **compensates** rather than pretends:

### 4.4 Compensations for the erasure gap
- **Minimize:** pre-accept, a peer never holds more than §2.2's redacted row — worthless to keep.
- **Short TTL:** every shadow row carries `expires_at` (default **7 days**, DESIGN DECISION) and a
  daily django-q2 sweep shreds expired shadows (`emit("fed.shadow_expired", ...)`) — the same
  scheduled-sweep shape as `expire_stale_proposals` (§10.6, `apps/matches/tasks.py`). Active
  matches refresh their shadow's TTL while the match is live.
- **Re-fetch over persist:** UI renders remote listings from the freshest poll; nothing inbound is
  treated as durable. Post-accept contact dicts are held only while the match is `accepted` and
  shredded on `fulfilled/unfulfilled/cancelled` + grace (72 h, echoing the Manual §5.8 erasure
  horizon cited in `docs/INTEGRATION-PLAN.md:59` — DESIGN DECISION to reuse that number).
- **Compliance = protocol conformance:** a peer that fails to honor delete-requests is suspended
  by its human admins; receipts + both-side audit make the failure provable.

---

## 5. Pillar 4 — Secure attribute exchange (DESIGNED)

### 5.1 Phase table — exactly which attributes cross, when

| Phase | Crosses the wire | Never crosses |
|---|---|---|
| **Discovery** | §2.2 redacted row + consent receipt id | identity, contact, title, description, neighborhood |
| **Proposal** | `title` (≤200 chars, text-rendered), category, urgency, proposer's **community** label, blind self-match token (§7), idempotency key | proposer identity/contact; description stays home (DECISION-NEEDED below) |
| **Accept** | §8.2 payload BOTH directions: `Member.contact_dict(pref)` output only (`display_name`, `preference`, conditional `email`/`phone` — `apps/communities/models.py:119-127`), wrapped in a signed envelope; stored envelope-encrypted under receiver keys | anything beyond `contact_dict`; `on_behalf_of`; case data (Lake 2 NEVER federates in v1) |
| **Fulfill / terminal** | status event + optional rating (coordinator-only field, `apps/matches/models.py` `rating`) — **numeric only, no notes** | `Match.notes` free text stays home |

**DECIDED 2026-07-02 (default accepted): `description` does NOT cross at proposal time.** The
proposing side sees title+category+urgency only; the parties exchange specifics after accept via
their revealed contact channel (matches how §8.2 works locally: the platform brokers
introductions, not conversations). The rejected alternative (description crosses, capped 2000
chars) raised utility and de-anonymization risk together.

### 5.2 §8.2 across instances — the invariant, restated
Identity and contact information cross the instance boundary **only** after a match reaches
`accepted`, only between the matched parties (plus coordinator oversight below), and only in the
`contact_dict` shape. The gate lives on the **home instance of each party** — each side releases
its own member's contact, so a compromised peer cannot pull contact it wasn't granted by a real
accept event signed by the other side. Coordinator oversight carries over: coordinators of the two
matched communities can view the disclosed dicts for their side's matches, audited with the
existing dotted names (`need.contact_disclosed` / `offer.contact_disclosed`,
`apps/needs/views.py:81-87`, `apps/offers/views.py:73-79`) plus `fed.contact_disclosed` for the
cross-instance release itself.

### 5.3 At rest on the receiver
Post-accept contact payloads and any enriched shadow content are stored via the **paired
BinaryField + property** envelope pattern (`payload_enc` + `payload_enc_dek`,
`crypto.envelope_encrypt_json` — `apps/people/crypto.py:133-141`), under the **receiver's** KEK.
Rationale: sovereignty + the receiver's existing `rotate_keks` / census / shred tooling applies to
federated data with zero new crypto code. In transit: TLS + the JWS envelope (§3.2).

### 5.4 Attestations — built on `apps.tags`, no new badge model
A peer may request attestation of a proposal: "is this offerer's `clergy` tag verified?" The home
instance answers with a signed claim derived from the BUILT MemberTag machine
(`apps/tags/models.py:103-363`): `{"tag": "<slug>", "tier": "<self_serve|coordinator_verified|
admin_verified>", "status": "verified", "verified_at": ...}` — signed, ephemeral (TTL 24 h),
**bound to the match id** (not a portable credential), and revealing nothing else about the member.
`evidence_note` (verification justification text) NEVER crosses. Self-claimed tags are answered
`"status": "self_claimed"` — the receiving UI must style them exactly as unverified, preserving
the clergy-impersonation control from the threat model. Stage D; capability-gated
(`"attestation"` in the instance doc).

---

## 6. Cross-instance match lifecycle (DESIGNED)

### 6.1 Authority: home-of-need holds the lock
The need's home instance is the **single authority** for match state — because §8.7's discipline
is pessimistic row locking (`select_for_update`, `apps/matches/views.py:143-152`), and locks
cannot span instances. The offer's home holds a mirror that converges to the authority's state.
A cross-instance match on the authority side is a normal `Match` row (`offer=None`, exactly the
BUILT "direct volunteer" shape, `apps/matches/models.py:140-142`) plus a `FederatedMatch` sidecar
carrying the remote references — the local state machine, transition validation, and 409
discipline are reused untouched.

### 6.2 Sequence — proposal through acceptance

```text
Instance B (offer home; Bob's member          Instance A (need home = AUTHORITY;
"remote responder")                            Alice's member = requester)
-----------------------------------           ------------------------------------
1. member browses federated listings
   (shadow rows from discovery pull)
2. POST /federation/v1/proposals ────────────► verify JWS + link + consent receipt
   {need: <remote_uuid>, proposal_uuid,        still shared? need.status=="open"?
    title/category of the offer,               blind token ≠ requester's (§7)
    blind_token, attestation_ref?}             ├─ no → 200 {status:"rejected",
                                               │         reason:"gone"|"self_match"}
                                               └─ yes:
                                                 transaction.atomic():
                                                   lock Need (§8.7 pattern)
                                                   Match.objects.create(offer=None,
                                                     proposed_by=<fed proxy, §6.4>)
                                                   + FederatedMatch(link, proposal_uuid,
                                                     remote_offer_uuid)
                                                 emit("fed.proposal_received", fmatch)
3. ◄──────────────────────────────────────────  200 {status:"created",
                                                     match_uuid: <fed match uuid>}
   B mirrors: ShadowMatch(proposed)
   emit("fed.proposal_sent", fmatch)
4. Requester reviews on A (normal UI;
   listing marked "from <peer community>")
5. Requester accepts → A runs the BUILT §8.7
   accept path: select_for_update on Match +
   Need, double-accept guard (409 if raced),
   transition_to("accepted") cascades need
   status (models.py:73-80)
6. A queues signed event ────────────────────► (outbox, §9.3)
   POST B /federation/v1/matches/<uuid>/events
   {event_uuid, event:"accepted",
    contact: <requester contact_dict, §8.2>}
7. B: verify, idempotency on event_uuid;
   mirror → accepted; store contact envelope-
   encrypted; reveal to ITS §8.2 audience only
8. B responds ────────────────────────────────► {status:"applied",
   {contact: <responder contact_dict>}            ...}  → A stores/reveals same rules
   Both sides: emit("fed.contact_disclosed", fmatch, details={"direction": ...})
9. fulfill/cancel/expire: same signed event flow, authority = A;
   B may REQUEST cancel ("responder withdrew") — A applies it under its lock.
```

### 6.3 Idempotency, conflicts, unreachable peers
- **Idempotency keys everywhere:** `proposal_uuid` and `event_uuid` are client-minted UUIDs with
  a DB unique constraint per link — the exact `client_uuid` contract from offline sync
  (`apps/casework/models.py:177`; pre-check + `IntegrityError` re-fetch,
  `apps/casework/views.py:600-652`). Replays return `{"status":"duplicate", ...}` with the
  original result.
- **Conflict = the existing 409 discipline:** a proposal against a just-matched need → item
  status `rejected/gone` (maps to the local double-accept guard,
  `apps/matches/views.py:172-174`); an event that's invalid for the mirror's current state →
  409 semantics carried as `{"status":"conflict", "authoritative_state": "<status>"}` and the
  mirror **re-syncs to the authority** (`GET /federation/v1/matches/<uuid>` returns the signed
  authoritative state). Authority never yields; mirrors converge.
- **Unreachable peer:** outbound events sit in a django-q2 outbox with exponential backoff
  (1 min → 4 h cap, 72 h give-up, DESIGN DECISION) + `emit("fed.peer_unreachable", link)` on
  first failure per episode. The authority's local state is never blocked by a dead peer —
  a match can be accepted, fulfilled, expired entirely offline; the mirror catches up on
  delivery or on its next poll. If a link dies mid-match (`revoked`), local coordinators are
  notified and the match is cancellable locally (normal §8.7 path).

### 6.4 The proxy-member question — DECIDED 2026-07-02: option (a)
`Match.proposed_by` is `FK(Member, CASCADE)` NOT NULL (`apps/matches/models.py`). A remote
proposer has no local Member. Options:
- **(a) Recommended:** per-link **system Member** (`role="member"`, `is_active=False`, user = a
  per-link service account, `display_name = "<peer community> (federated)"`) — additive, no
  schema change to Match, existing queries/templates keep working; FederatedMatch carries the
  real remote attribution.
- (b) `proposed_by` nullable + `proposed_via_link` FK — cleaner semantics, but a schema change on
  a BUILT hot table and every `proposed_by` consumer needs a null path. STOP-worthy migration.
**DECIDED: (a)** — no schema change to Match; revisit only if Stage C review surfaces a blocker.

---

## 7. Self-match across instances — DECIDED 2026-07-02: blind token + backstop (§8.6 is not dropped at the boundary)

**The tension:** §8.6 (BUILT, `apps/matches/views.py:52-61`) blocks self-matching by comparing
Member **and** User identity — but §8.2 hides identity across instances until post-accept, and
sovereign instances share no user table. Both checks are literally impossible pre-accept with the
data federation is allowed to move.

**DECIDED: blind commitment token (ON when derivable), post-accept detection as the backstop.**
- At link establishment both sides derive a **pairing pepper** for the link:
  `HKDF(shared_info = sorted(instance_id_A, instance_id_B) + link_uuid)` — public inputs, but the
  token below never leaves signed channels, and the pepper's job is only to make tokens
  link-scoped (rainbow tables built for one link are useless on another).
- Each side computes, for a participating member with a usable anchor:
  `blind_token = HMAC-SHA256(pepper, lowercase(user.email))` — email is the only cross-instance
  identity anchor that exists in the schema (`AUTH_USER_MODEL.email`; phone optional). Token
  crosses at proposal time (§6.2 step 2). The need's home compares the proposer token against the
  requester's token: equal → reject `{"status":"rejected","reason":"self_match"}` — mirroring the
  local §8.6 rejection (which returns 400, `apps/matches/views.py:56`).
- **Privacy property:** a token reveals nothing about a non-matching member (HMAC with per-link
  pepper; peer cannot brute-force emails at scale through it without already holding candidate
  emails — and per-link rate limits cap oracle abuse). Equal tokens reveal exactly one bit — the
  same bit §8.6 must reveal to function.
- **Coverage honesty:** members with no email (email is optional — the standalone-script gotcha
  in the brain notes `create()` leaves it NULL) get **no token**; the edge rides the backstop:
  on accept, when contact dicts cross (§8.2 both directions), each home compares the revealed
  email/phone against its own party's; a hit → auto-flag, `emit("fed.selfmatch_detected",
  fmatch)`, coordinator notification, match auto-cancelled via the normal machine.
- **Alternative (rejected as default):** accept the rare edge entirely post-accept (no token).
  Simpler, but it knowingly ships a §8.6 regression at the boundary; the token is cheap and
  fails safe to the backstop.

---

## 8. Data model (all DESIGNED — new app `apps/federation`)

All PKs UUID (matches every Lake-1 model + audit's `resource_id` UUIDField expectation,
`apps/audit/models.py`). All new tables additive; zero changes to existing tables except
`Need.share_scope` / `Offer.share_scope` (CharField, default `"local"` — additive with default).

| Entity | Key fields (type → target) | Encrypted | TTL |
|---|---|---|---|
| **FederationPeer** — a known instance | `base_url` URLField unique · `instance_id` Char(64) unique (JWK thumbprint) · `jwk` JSONField (pinned public key) · `label` Char(200) · `locality` Char(100) · `capabilities` JSONField · `status` pending/active/blocked · `approved_by` FK→communities.Member SET_NULL · timestamps | no (public material) | — |
| **FederationLink** — pairwise, community-scoped relationship (StateMachineMixin) | `peer` FK→FederationPeer CASCADE · `community` FK→Community CASCADE · `remote_community_uuid` UUID · `remote_community_label` Char(200) · `status` pending/active/suspended/revoked + VALID_TRANSITIONS (§3.3) · `pairing_code_hash` Char(64) (salted SHA-256 — the DeviceToken/audit-IP recipe) · `pairing_pepper` BinaryField (§7) · `approved_by` FK→Member SET_NULL · `approved_at` · `revoked_at` · unique_together (peer, community, remote_community_uuid) | pepper is secret material (BinaryField, not exported) | — |
| **FederatedShare** — outbound grant, one record→one link | `link` FK CASCADE · `need` FK→needs.Need CASCADE null · `offer` FK→offers.Offer CASCADE null (exactly one set — CheckConstraint) · `consent` FK→consent.Consent **PROTECT** · `remote_uuid` UUID unique (minted alias, §2.2) · `receipt_jws` TextField · `status` active/revoked/expired · `revoke_acked_at` DateTime null | no (redacted by construction) | follows record expiry |
| **ShadowListing** — inbound discovery row (need or offer) | `link` FK CASCADE · `kind` need/offer · `remote_uuid` UUID · `category_slug` Char(100) · `urgency` Char(10) blank · `locality` Char(100) · `freshness` Char(10) · `radius_km` Int null · `receipt_jws` TextField · `fetched_at` · `expires_at` | no PII by construction | **7 d default**, sweep-shredded (§4.4) |
| **FederatedMatch** — sidecar on the authority + mirror | `match` OneToOne→matches.Match CASCADE null (authority side) · `link` FK CASCADE · `role` authority/mirror · `proposal_uuid` UUID · `remote_match_uuid` UUID null · `mirror_status` Char(12) (mirror side) · `contact_payload_enc` + `contact_payload_dek` BinaryFields · `contact_expires_at` · unique_together (link, proposal_uuid) | **contact payload envelope-encrypted under local KEK** (§5.3) | contact blob shredded at terminal + 72 h (§4.4) |
| **FederationEvent** — outbox/inbox for delivery + idempotency | `link` FK CASCADE · `direction` out/in · `event_uuid` UUID · `kind` Char(32) · `payload` JSONField (PII-free for `out` at rest? — see note) · `state` pending/sent/acked/failed/applied/duplicate · `attempts` SmallInt · `next_attempt_at` · unique_together (link, event_uuid) | **note:** accepted-events carry contact dicts → outbox payload for those is envelope-encrypted (`payload_enc`/`payload_dek`) and shredded on ack | give-up 72 h |
| *(existing)* `Need.share_scope` / `Offer.share_scope` | Char(10) `local`/`federated`, default `local`, indexed with status | — | — |

Relations recap: Community 1—n FederationLink n—1 FederationPeer; Need/Offer 1—n FederatedShare
n—1 Consent; Match 1—1 FederatedMatch n—1 FederationLink; everything auditable via `emit()`
(UUID pks fit `resource_id`).

## 9. Wire protocol / API (DESIGNED)

### 9.1 Style — the SyncView contract, verbatim
Hand-rolled Django views + `JsonResponse` (**no DRF** — removed in PR #16; the RN design doc
PR #33 already re-committed to this pattern). Every rule below is the BUILT `SyncView` contract
(`apps/casework/views.py:582-662`) applied to federation: `json.loads(request.body)` with
`400 {"error":"invalid JSON"}`; batch arrays capped at **50**; top-level HTTP 200 envelope with
per-item `status` (`created` / `duplicate` / `applied` / `conflict` / `rejected` / `error` +
`error` code); field whitelisting against local choices; length caps on every string.

### 9.2 Endpoints (all under `federation/v1/`, all JWS-verified per §3.2 except the first)

| Endpoint | Auth | Purpose / body sketch |
|---|---|---|
| `GET /.well-known/umi-federation` | none (public, cacheable) | instance document (§3.1) |
| `POST /federation/v1/handshake` | self-signed doc + pairing code | link request (§3.3); 5/hr/IP |
| `POST /federation/v1/handshake/confirm` | signed | complete pairing |
| `GET /federation/v1/discovery?since=<iso>&cursor=` | signed | `{"listings": [≤50 rows §2.2], "next": cursor|null}`; deltas since last poll incl. tombstones `{"remote_uuid":..., "gone": true}` |
| `POST /federation/v1/proposals` | signed | `{"proposals": [{proposal_uuid, need_remote_uuid, offer: {title≤200, category_slug, radius_km?}, blind_token?, attestation_ref?}]}` → per-item `created/duplicate/rejected(gone|self_match|not_shared)` |
| `POST /federation/v1/matches/<uuid>/events` | signed | `{"events": [{event_uuid, event: accepted|cancel_requested|fulfilled|unfulfilled|expired, contact?: contact_dict}]}` → `applied/duplicate/conflict{authoritative_state}` |
| `GET /federation/v1/matches/<uuid>` | signed | signed authoritative state (mirror re-sync) |
| `POST /federation/v1/consent/revocations` | signed | `{"revocations": [{receipt_id, record, reason}]}` → `shredded/unknown` (§4.3) |
| `POST /federation/v1/links/revoke` · `/links/rekey` | signed | link lifecycle (§3.3) |
| `POST /federation/v1/attestations/query` | signed, capability-gated | §5.4 |

Error model: transport/auth failures are HTTP `400/403/409/429` with `{"error": "<code>"}`
(codes: `invalid_json`, `bad_signature`, `link_suspended`, `replayed`, `rate_limited` — the 429
carries `Retry-After`, reusing `_too_many`, `apps/accounts/ratelimit.py:60-71`); item-level
outcomes ride the 200 envelope. **Versioning/capability negotiation:** path-versioned (`/v1/`) +
`"umi_federation": "1"` and `capabilities` in the instance doc; a request for an absent
capability → `403 {"error": "capability_unsupported"}`. v2 negotiation = intersection of
advertised versions (DESIGN DECISION).

### 9.3 Outbound client — DECIDED 2026-07-02: option (a), stdlib
No outbound HTTP exists in the repo (§1). Options: **(a) Recommended:** stdlib
`urllib.request` wrapped in one module (`apps/federation/client.py`) — explicit 10 s timeouts,
1 MB response cap, TLS default verification, no redirects, retries owned by the django-q2 outbox
(§6.3) — honors the no-new-runtime-deps rule; federation's needs are small (signed JSON POST/GET).
(b) `httpx` — nicer API, HTTP/2, one more dep to justify. Default: (a).

## 10. Audit — dotted actions (§10.1; all ≤32 chars, verified against `emit()`'s hard cap)

`fed.link_requested` · `fed.link_approved` · `fed.link_suspended` · `fed.link_revoked` ·
`fed.link_rekeyed` · `fed.share_created` · `fed.share_revoked` · `fed.discovery_served` ·
`fed.proposal_sent` · `fed.proposal_received` · `fed.match_event_sent` ·
`fed.match_event_received` · `fed.contact_disclosed` · `fed.consent_revoke_sent` ·
`fed.consent_revoke_received` · `fed.shadow_shredded` · `fed.shadow_expired` ·
`fed.selfmatch_detected` · `fed.peer_unreachable` · `fed.receipt_invalid` · `fed.sig_rejected` ·
`fed.attestation_served`

Each row records (emit's fixed shape, `apps/audit/services.py:37-48`): actor user (or NULL =
system/peer), action, `resource_type` (auto: `federationlink`, `federatedshare`,
`federatedmatch`, `shadowlisting`…), resource UUID, salted-hashed IP, and a **PII-free `details`
dict** — enums/uuids/counts only (`{"link": ..., "peer": <instance_id>, "reason": "gone"}`),
never titles, names, contact, tokens, or JWS material. Cross-instance actions are audited **on
both sides** by construction (each side emits its own row on send/receive). Convention (matches
the Lake-1 sweep): emit in the **view/task layer**, not model signals.

## 11. Abuse & failure modes → mitigations (beyond §3.4)

| Mode | Handling |
|---|---|
| Discovery scraping via many links | per-link throttles + per-record consent + admin dashboards of `fed.discovery_served` volume; suspend is one click |
| Proposal spam to one need | proposals per need per link capped (default 3 open; `rejected/duplicate` after) + `fed.proposal_received` volume visible to coordinators |
| Rate limits (reuse `apps.accounts.ratelimit` — `rl_check` per-object pattern from tags, `apps/tags/views.py:92`) | `fed-handshake` 5/hr/IP · `fed-discovery` 60/hr/link · `fed-proposals` 30/hr/link · `fed-events` 120/hr/link · `fed-revocations` 60/hr/link (defaults; DESIGN DECISION) |
| Partial batch failure | per-item envelope (§9.1) — item failures never roll back siblings; each item is its own transaction (SyncView `_one` shape) |
| Outbox stuck / peer dead | backoff → 72 h give-up → `failed` + coordinator notification + `fed.peer_unreachable`; link auto-`suspended` after 7 days unreachable (DESIGN DECISION) |
| Clock skew breaking `iat` | ±300 s window; docs instruct NTP (chrony) — the ops runbook owns this |
| KEK rotation vs shadows | shadows/outbox use the same envelope API → `rotate_keks` + census cover them with zero new tooling (extend census to `federation_envelope_status`) |
| Postgres-only behaviors | `select_for_update` paths already Postgres-gated in CI (the brain's DB gotcha); federation tests must run the full-Postgres gate like everything else |

## 12. Staged build plan (each stage independently shippable + reversible, all behind default-OFF flags)

Gate for every stage: `ruff check` + `ruff format --check` · `makemigrations --check` ·
`bandit` + `semgrep --baseline-commit main` (no new findings) · full `pytest` on **Postgres** ·
`manage.py check --deploy` = 0. Plus: no stage weakens a BUILT guarantee; all migrations additive;
**STOP for approval before any migration ships** (standing rule).

- **A — Identity & links (no data flows).** `apps/federation` app: Peer/Link models, instance
  keypair + `/.well-known` doc, handshake + admin approve/suspend/revoke UI, JWS
  verify/sign module, audit events, rate limits. Reversible: `FEDERATION_ENABLED=False` removes
  every route; models are inert. *Tests:* handshake happy/evil paths, signature/replay/skew
  rejection, state machine.
- **B — Outbound consent + discovery (read-only exposure).** `share_scope` fields + share UI
  gated on Consent capture (`covers()` wired); consent receipts; discovery endpoint + poller +
  ShadowListing w/ TTL sweep; revocation propagation + shred handler; **consent-revocation audit
  gap fixed** (every revoke now emits, federated or not). Reversible: unshare-all command +
  flag off; peers' shadows die by TTL even if we vanish.
- **C — Cross-instance matching.** Proposals endpoint, proxy-member (§6.4a), FederatedMatch +
  events outbox/inbox, §8.7-locked accept on authority, §8.2 contact exchange encrypted at rest,
  blind-token self-match check + post-accept backstop, mirror re-sync, coordinator surfaces.
  Reversible: capability `match` withdrawn from instance doc → peers stop proposing; open
  federated matches cancellable locally.
- **D — Attestations.** §5.4 on `apps.tags`. Reversible: capability flag.
- **E — Ops & (optional) directory.** Federation section in the census/monitoring docs
  (extend the existing **UptimeRobot** monitors + `monitor.sh`, per the ops brief and
  `docs/monitoring-decision.md` — don't stand up new stacks); retention sweeps dashboards; the
  untrusted signed directory, if wanted at all.

**Conformance mapping — DESIGN DECISION (manual not in repo):** per the brain's canonical summary
(`umi-brain/vision/what-is-umi.md`): Core ✅ + Casework ✅ are BUILT; the manual's **Federation
level** is claimed only when Stages A–C are green in production between ≥2 real instances with
default-OFF verified. **v1 in-scope:** pillars 1–4, cross-instance matches, revocation
propagation. **v1 deferred:** directory, Lake-2/casework data (never in v1), multi-hop/transitive
sharing (never — pairwise only), attestation portability beyond a single match, federated search
ranking, media.

## 13. Open questions — ANSWERED (2026-07-02, Jasiah: all recommended defaults accepted)

1. **joserfc dependency** (§3.2) — **DECIDED: add `joserfc`** (only maintained JOSE implementation;
   sole transitive dep `cryptography` already pinned). Justify in `requirements.txt` comment.
2. **Self-match blind token** (§7) — **DECIDED: token + backstop.** HMAC email-commitment crosses
   at proposal when derivable; post-accept detection covers the no-email edge.
3. **Description at proposal** (§5.1) — **DECIDED: stays home.** Title+category+urgency only until
   accept.
4. **Proxy member vs nullable `proposed_by`** (§6.4) — **DECIDED: proxy member (a).** No schema
   change to Match; revisit only on a Stage C blocker.
5. **Retention numbers** (§4.4, §11) — **CONFIRMED: shadow TTL 7 d · contact retention terminal
   + 72 h · unreachable auto-suspend 7 d.**
6. **Outbound client** (§9.3) — **DECIDED: stdlib `urllib.request` module** (`apps/federation/
   client.py`; 10 s timeouts, 1 MB cap, no redirects, retries in the django-q2 outbox). No httpx.
7. **Locality label** (§2.2) — **DECIDED: free-text admin label**, UI-warned "coarse only — never
   an address". Controlled vocabulary (diocese/deanery) deferred.
8. **Directory** (Stage E) — **DECIDED: deferred entirely from v1.** Pure pairwise P2P.

---

*DESIGN ONLY — decisions locked 2026-07-02; no code or migrations accompany this document. Next
step: **Stage A implementation brief** through the L8 lane (plan → TDD → gate → PR), per
`agents.md`; the ready-to-send prompt is saved in the brain's `capabilities/prompt-library.md`
(P6). Stage A's migration still STOPs for approval before it ships, per the standing rule.*

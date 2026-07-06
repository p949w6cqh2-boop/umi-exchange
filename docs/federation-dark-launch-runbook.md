# Federation Dark-Launch Runbook — two real instances, quietly

> **STATUS: BUILT process, REHEARSED 2026-07-06.** The full lifecycle below (handshake → share →
> discovery → proposal → accept → §8.2 contact exchange → fulfilled → retention grace) was executed
> between two real instances over real signed HTTP on 2026-07-06, with every expected `fed.*` audit
> action verified on both sides. This runbook turns that rehearsal into the production procedure.
>
> **A "dark launch" means:** `FEDERATION_ENABLED=1` on exactly two production instances, one
> human-approved link between them, one or two consenting records shared — no announcement, no
> member comms, coordinators watching the audit log. Per `federation-design.md` §12, the manual's
> **Federation conformance level** is claimed only after Stages A–C run green in production between
> ≥2 real instances with default-OFF verified everywhere else.

## 0. Do-not-start gates

- [ ] Threat-model must-fix **#1** confirmed on BOTH instances: the app's Postgres role is NOT
      owner/superuser of `audit_auditlog` (else append-only is bypassable). `docs/threat-model.md`.
- [ ] Threat-model must-fix **#4** decision recorded (DV/high-risk casework default `restricted`) —
      casework never federates, but the pilot posture should be settled before widening surface.
- [ ] Both instances healthy on the ops baseline: Uptime Kuma green, `backup.sh` current,
      `manage.py check --deploy` = 0 issues.

## 1. Per-instance prerequisites

| Requirement | Why |
|---|---|
| HTTPS behind Caddy with the exact public hostname | signatures bind `htu` = `SITE_URL` + path; a hostname mismatch 400s every request |
| **Redis (`REDIS_URL`) — required, not optional** | `jti` replay cache must be shared across workers (prod fail-fasts on LocMemCache); sessions also ride it |
| Postgres 16, `ENCRYPTION_KEY(S)` set | shadows/outbox/contact payloads are envelope-encrypted |
| NTP (chrony) running | signed requests carry `iat` ±300 s; skew = `fed.sig_rejected: bad_iat` |
| `django-q2` qcluster running | discovery poll (15 min), outbox delivery (1 min), retention sweeps + auto-suspend (daily) |

## 2. Enable federation (each instance)

```bash
# 1) mint the instance identity (once) — store the JWK ONLY in the env, never in git
python manage.py federation_keygen        # → FEDERATION_PRIVATE_KEY

# 2) environment
FEDERATION_ENABLED=1
FEDERATION_PRIVATE_KEY='<private JWK from keygen>'
SITE_URL=https://exchange.parish-a.example      # EXACT public base URL
FEDERATION_LOCALITY="Dublin-North"              # coarse label only — never an address

# 3) restart, then register the schedules once
python manage.py shell -c "from apps.federation.tasks import register_schedule; register_schedule()"
```

Verify: `GET https://<instance>/.well-known/umi-federation` returns a signed instance document;
`manage.py check --deploy` still reports 0; the admin Federation page (Community Settings →
Federation) shows this instance's key thumbprint.

## 3. The handshake ceremony (two humans, one phone call)

Roles: **Admin A** (St. Patrick) and **Admin B** (the peer). Both open
`c/<community>/federation/` and keep the page visible — it shows their **own key thumbprint**.

1. Admin B enters A's base URL → **Fetch & request**. A one-time **12-character pairing code**
   appears in a toast. **⚠ Write it down immediately — it is shown exactly once and the toast
   auto-dismisses in a few seconds** (UX follow-up filed: pin it to the page).
2. **Phone call (the MITM kill, §3.3):** B reads A the pairing code AND B's thumbprint; A reads
   back the thumbprint shown in A's *Inbound requests* panel. **They must match verbatim.** Any
   mismatch → stop, revoke, investigate.
3. Admin A enters the code → **Verify & approve**. The signed confirm activates the link on both
   sides automatically. Both pages now show the link **Active**.
4. Verify in the audit log (both sides): `fed.link_requested` + `fed.link_approved`.

## 4. Share the pilot record (current UI gap — shell step)

There is **no member-facing share UI yet** (flagged follow-up slice). For the dark launch, share
one consenting member's need via shell on its home instance:

```bash
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> from apps.consent.models import Consent
>>> from apps.federation import sharing
>>> from apps.federation.models import FederationLink
>>> from apps.needs.models import Need
>>> user = get_user_model().objects.get(username="<the consenting member>")
>>> link = FederationLink.objects.get(status="active")
>>> need = Need.objects.get(pk="<need uuid>")
>>> Consent.objects.create(participant=user, granted_to=link.remote_community_label,
...     grantee_type="community", grantee_id=link.remote_community_uuid,
...     scope=["federated_share"], purpose="Dark-launch pilot share", method="verbal")
>>> sharing.share_record(need, link, actor_user=user)
```

The member's **verbal consent must be real** — record who consented and when in the consent row.
Only redacted fields ever cross at this stage (category, urgency, coarse locality, week bucket).

## 5. Drive the lifecycle (the rehearsed checklist)

On the **offer-side** instance, after the next 15-minute poll (or
`shell -c "from apps.federation.tasks import poll_all_active_links; poll_all_active_links()"`):

| Step | Where | Verify |
|---|---|---|
| Shadow appears | offer side: feed → "Beyond this community →" | card shows peer pill + category/urgency/locality; **no names, no free text** |
| Offer to help | same page, picker | only the member's own active offers listed |
| Proposal crosses | automatic on send | need side audit: `fed.proposal_received`; match appears with proposer "<peer> (federated)" |
| Accept | need side: requester's match page → Accept (consent modal states contact will be shared) | within ~1 min (outbox): offer side `fed.match_event_received`, both sides `fed.contact_disclosed` |
| Contact visible | offer side: "Across communities"; need side: match detail | each party sees ONLY the other's `contact_dict`; every render audited (`read match_contact`) |
| Fulfil | need side match page | offer side mirror flips Fulfilled; offer released to `fulfilled`; `contact_expires_at` set BOTH sides (72 h shred grace) |
| Retention | after 72 h (daily sweep) | `fed.contact_shredded` both sides; contact gone from both UIs |

## 6. Watch during the launch

- `fed.sig_rejected` (reason `bad_iat` → NTP; `bad_htu` → SITE_URL/proxy mismatch).
- `fed.peer_unreachable` — backoff runs 1 min → 4 h; after 7 days unreachable the link
  **auto-suspends** (`fed.link_suspended`, coordinators notified; Resume is one click and resets
  the episode).
- Volume sanity: per-peer caps are discovery 60/h · proposals 30/h · revocations 60/h ·
  events 120/h · sync 120/h — a pilot should never approach them.

## 7. Rollback (safe-fail, any time)

1. **Pause:** suspend the link (either side) — all traffic stops immediately, keys kept.
2. **Sever:** revoke the link — terminal; cascades this link's shares to revoked and cancels
   in-flight federated matches locally; peer's shadows die by tombstone/TTL (≤7 d).
3. **Vanish:** `FEDERATION_ENABLED=0` + restart — every federation route disappears.
   **Retention sweeps keep running with the flag off** — stored contact still shreds on schedule.
4. Cross-instance erasure is cooperative by design (§4.3): a revoked share also sends a signed
   delete-request; verify the peer's `fed.shadow_shredded` if you need it now rather than at TTL.

## 8. Rehearsal evidence (2026-07-06, two local instances, real HTTP)

Handshake via both admin UIs (pairing code + thumbprint read-back) · share + consent + signed
receipt · discovery poll persisted 1 redacted shadow (receipt verified before persist) · proposal
crossed with blind token · authority match accepted through the consent modal · outbox delivered
`accepted` (encrypted payload shredded on ack) · contact exchanged **both directions** and
rendered on both UIs · fulfilled propagated; offer released to `fulfilled`; 72 h grace set both
sides. Audit trail on the need side: `fed.link_requested/approved`, `fed.share_created`,
`fed.discovery_served`, `fed.proposal_received`, `fed.match_event_sent`, `fed.contact_disclosed`.
Offer side: `fed.link_requested/approved`, `fed.proposal_sent`, `fed.match_event_received`,
`fed.contact_disclosed`.

**Known gaps carried into the pilot:** no share UI (shell step above); the one-time pairing-code
toast should become a pinned panel; local multi-instance rehearsals must use separate browser
profiles (cookies ignore ports).

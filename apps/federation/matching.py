"""
Cross-instance matching — authority side (Stage C slice 1, §6/§7).
A peer proposes against a Need we shared; we create the local AUTHORITATIVE
Match (the need's home holds the §8.7 lock, decision §6.1) plus a FederatedMatch
sidecar. §8.6 self-matching is preserved across the boundary by a blind token
(§7); the proxy member (decision §6.4a) stands in for the remote proposer with
no schema change to Match.
"""

import hmac

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.audit.services import emit
from apps.communities.models import Member

from . import client as client_mod
from . import crypto
from .models import FederatedMatch, FederatedShare

# M-4: max concurrent non-terminal (proposed/accepted) proposals against one
# Need from one link. Mechanism is the guard below; the NUMBER is a product call
# (§11 suggests 3) — flagged for Jasiah, not silently authoritative.
MAX_OPEN_PROPOSALS_PER_NEED_PER_LINK = 3


def get_proxy_member(link):
    """Per-link system Member representing the remote proposer (§6.4a):
    inactive, role 'member', a dedicated service user — real attribution lives
    on the FederatedMatch. No change to Match.proposed_by's NOT-NULL FK."""
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(
        username=f"fed-proxy-{link.pk}", defaults={"email": "", "is_active": False}
    )
    member, _ = Member.objects.get_or_create(
        user=user,
        community=link.community,
        defaults={
            "role": "member",
            "is_active": False,
            "display_name": f"{link.remote_community_label or 'Peer'} (federated)",
        },
    )
    return member


def _is_requester_self_match(need, link, incoming_token) -> bool:
    """True iff the proposer's blind token equals the requester's — the same
    human on both sides (§8.6 across instances). No token / no email ⇒ can't
    decide here; the post-accept backstop (Stage C2) covers that edge."""
    if not incoming_token or not link.pairing_pepper:
        return False
    email = getattr(need.requester.user, "email", "") or ""
    if not email:
        return False
    # Constant-time (L-1): consistent with crypto.codes_match. The equality bit
    # is disclosed by design (the response says "self_match"), but compare in
    # constant time anyway so the comparison itself leaks nothing.
    return hmac.compare_digest(crypto.blind_token(bytes(link.pairing_pepper), email), str(incoming_token))


def receive_proposal(peer, *, need_remote_uuid, proposal_uuid, blind_token=None) -> dict:
    """Handle one inbound proposal. Idempotent on (link, proposal_uuid)."""
    from apps.needs.models import Need

    # link__status="active" is load-bearing: revoking/suspending a link only
    # flips FederationLink.status (no cascade to its shares), so without this a
    # revoked link's still-"active" share would keep accepting proposals — the
    # exact containment the threat model relies on ("revoke link → immediate
    # 403"). Mirrors DiscoveryView's already-correct share query.
    share = (
        FederatedShare.objects.filter(
            link__peer=peer, link__status="active", remote_uuid=need_remote_uuid, status="active"
        )
        .select_related("need", "link")
        .first()
    )
    if share is None or share.need_id is None:
        return {"status": "rejected", "reason": "not_shared"}
    link = share.link

    existing = FederatedMatch.objects.filter(link=link, proposal_uuid=proposal_uuid).first()
    if existing:
        return {"status": "duplicate", "match_uuid": str(existing.match_id)}

    from apps.matches.models import Match

    try:
        with transaction.atomic():
            need = Need.objects.select_for_update().get(pk=share.need_id)
            if need.status != "open":
                return {"status": "rejected", "reason": "gone"}
            if _is_requester_self_match(need, link, blind_token):
                return {"status": "rejected", "reason": "self_match"}
            # M-4: cap concurrent non-terminal proposals per (need, link) so one
            # peer can't flood a single Need with authoritative Matches.
            open_count = FederatedMatch.objects.filter(
                link=link, match__need=need, match__status__in=("proposed", "accepted")
            ).count()
            if open_count >= MAX_OPEN_PROPOSALS_PER_NEED_PER_LINK:
                return {"status": "rejected", "reason": "too_many_open"}
            match = Match.objects.create(need=need, offer=None, proposed_by=get_proxy_member(link))
            fmatch = FederatedMatch.objects.create(
                match=match, link=link, role="authority", proposal_uuid=proposal_uuid
            )
    except IntegrityError:
        # Concurrent duplicate on (link, proposal_uuid) — return the winner.
        existing = FederatedMatch.objects.filter(link=link, proposal_uuid=proposal_uuid).first()
        if existing:
            return {"status": "duplicate", "match_uuid": str(existing.match_id)}
        raise

    emit("fed.proposal_received", fmatch, details={"link": str(link.pk)})
    return {"status": "created", "match_uuid": str(match.id)}


class _CancelConflictError(Exception):
    def __init__(self, state):
        self.state = state
        super().__init__(state)


def apply_cancel_request(fmatch, *, event_uuid):
    """Mirror → authority (§6.2 step 9): the responder withdrew (or the §7
    backstop fired on their side). Applied under the §8.7 lock; the outcome
    echoes back to the mirror as a `cancelled` event via the outbox. A match
    already terminal answers `conflict` + the authoritative state."""
    from apps.matches.models import Match
    from apps.needs.models import Need

    from . import outbox
    from .models import FederationEvent

    if FederationEvent.objects.filter(link=fmatch.link, event_uuid=event_uuid).exists():
        return {"status": "duplicate"}
    try:
        with transaction.atomic():
            FederationEvent.objects.create(
                link=fmatch.link,
                direction="in",
                event_uuid=event_uuid,
                kind="cancel_requested",
                state="applied",
                payload={"match_uuid": str(fmatch.match_id)},
            )
            match = Match.objects.select_for_update(of=("self",)).select_related("need").get(pk=fmatch.match_id)
            match.need = Need.objects.select_for_update().get(pk=match.need_id)
            if match.status not in ("proposed", "accepted"):
                raise _CancelConflictError(match.status)  # rolls the event row back too
            match.transition_to("cancelled")
            # Inside the transaction: the echo commits with the cancel, so a
            # crash can't strand the mirror waiting for an event that never
            # queued (§6.2 step 9).
            outbox.queue_match_event(match, "cancelled", fmatch=fmatch)
    except IntegrityError:
        return {"status": "duplicate"}
    except _CancelConflictError as conflict:
        return {"status": "conflict", "authoritative_state": conflict.state}
    emit("fed.match_event_received", fmatch, details={"event": "cancel_requested", "link": str(fmatch.link_id)})
    return {"status": "applied"}


def remote_contact_for(match):
    """The stored §8.2 dict of the remote counterpart for an authority-side
    federated match (or None). Flag-gated; decrypts via the model property —
    reveal audiences stay exactly the local §8.2 gate's business."""
    from django.conf import settings

    if not getattr(settings, "FEDERATION_ENABLED", False):
        return None
    fmatch = FederatedMatch.objects.filter(match=match, role="authority").first()
    return fmatch.contact_payload if fmatch else None


def serve_attestation_query(peer, *, match_uuid, tag_slug):
    """§5.4, serving side: answer whether OUR party on this federated match
    holds the tag verified. Derived from the BUILT MemberTag machine; pending/
    rejected/revoked/absent all read "none" (claim nothing); self-claimed is
    labelled exactly that. evidence_note never leaves this instance."""
    from django.db.models import Q

    from apps.tags.models import MemberTag, Tag

    from . import crypto as fed_crypto

    fmatch = (
        FederatedMatch.objects.filter(link__peer=peer, link__status="active")
        .filter(Q(role="authority", match__pk=match_uuid) | Q(role="mirror", remote_match_uuid=match_uuid))
        .select_related("link", "offer__offerer", "match__need__requester")
        .first()
    )
    if fmatch is None:
        return {"status": "unknown_match"}
    if fmatch.role == "mirror":
        member = fmatch.offer.offerer if fmatch.offer_id else None
    else:
        member = fmatch.match.need.requester
    if member is None:
        return {"status": "unknown_match"}

    tag = Tag.objects.filter(community_id=fmatch.link.community_id, slug=str(tag_slug)[:50]).first()
    mt = MemberTag.objects.filter(member=member, tag=tag).first() if tag else None
    if mt is not None and mt.status == "verified":
        status = "verified"
    elif mt is not None and mt.status == "self_claimed":
        status = "self_claimed"
    else:
        status = "none"  # pending/rejected/revoked/absent claim nothing
    token = fed_crypto.build_attestation(
        tag_slug=str(tag_slug)[:50],
        status=status,
        tier=tag.tier if tag else "",
        verified_at=mt.verified_at.isoformat() if mt is not None and mt.verified_at and status == "verified" else None,
        match_uuid=match_uuid,
        peer_instance_id=peer.instance_id,
    )
    emit(
        "fed.attestation_served",
        fmatch,
        details={"tag": str(tag_slug)[:50], "status": status, "link": str(fmatch.link_id)},
    )
    return {"status": status, "attestation": token}


def request_attestation(fmatch, tag_slug):
    """§5.4, asking side: query the party's home and VERIFY the returned
    claim (pinned key, audience, TTL, tag + match binding). Returns a dict
    with status verified/self_claimed/none/unsupported/unavailable."""
    import json as _json

    from . import crypto as fed_crypto

    peer = fmatch.link.peer
    if "attestation" not in (peer.capabilities or []):
        return {"status": "unsupported"}
    match_uuid = str(fmatch.match_id if fmatch.role == "authority" else fmatch.remote_match_uuid)
    payload = {"queries": [{"match_uuid": match_uuid, "tag": str(tag_slug)[:50]}]}
    url = client_mod.attestations_url(peer.base_url)
    signature = fed_crypto.sign_request("POST", url, _json.dumps(payload).encode(), aud=peer.instance_id)
    try:
        resp = client_mod.post_attestations(peer.base_url, payload, {"X-UMI-Signature": signature})
    except client_mod.FederationClientError:
        return {"status": "unavailable"}
    results = resp.get("results") if isinstance(resp, dict) else None
    first = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    token = first.get("attestation")
    try:
        claims = fed_crypto.verify_attestation(str(token or ""), peer.jwk, aud=fed_crypto.my_instance_id())
    except fed_crypto.FederationAuthError:
        return {"status": "unavailable"}
    if claims.get("tag") != str(tag_slug)[:50] or claims.get("match_uuid") != match_uuid:
        return {"status": "unavailable"}  # claim not about what we asked
    return {
        "status": str(claims.get("status", "none")),
        "tier": str(claims.get("tier", "")),
        "verified_at": claims.get("verified_at"),
    }

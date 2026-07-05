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

"""
Cross-instance matching — mirror side (Stage C2, §6.2/§6.3).
The offer's home proposes against a peer's shadow listing and then CONVERGES
on the authority's state: the need's home holds the §8.7 lock (§6.1); this
side never decides a match's fate, it applies signed events (views.py routes
them here) and re-syncs on conflict. §8.2: our responder's contact leaves
only in the reply to a verified `accepted` event from the authority.
"""

import json
import uuid

from django.db import transaction
from django.utils import timezone

from apps.audit.services import emit

from . import client as client_mod
from . import crypto
from .models import FederatedMatch

# The wire proposal carries only §5.1 phase-table fields: title, category,
# radius. Description/identity/contact stay home until post-accept.
PROPOSAL_TITLE_CAP = 200


class ProposalError(Exception):
    """Sending refused locally, or rejected by the authority (`reason`)."""


def send_proposal(shadow, offer, *, actor_user):
    """Propose `offer` against a peer's shadow need (§6.2 step 2). Returns the
    mirror FederatedMatch; idempotent per (link, need, offer) while the
    previous proposal is non-terminal. v1 keeps agency with the offerer: only
    the offer's owner may send it across the boundary (the H-2 rule, without
    the coordinator-brokering exception for now)."""
    link = shadow.link
    if link.status != "active":
        raise ProposalError("link is not active")
    if shadow.kind != "need":
        raise ProposalError("can only propose against a need listing")
    if offer.community_id != link.community_id:
        raise ProposalError("offer does not belong to the link's community")
    if offer.status != "active":
        raise ProposalError("offer is not active")
    if offer.offerer.user_id != actor_user.id:
        raise ProposalError("only the offer's owner can propose it to a peer")

    existing = (
        FederatedMatch.objects.filter(
            link=link,
            role="mirror",
            offer=offer,
            remote_need_uuid=shadow.remote_uuid,
        )
        .exclude(mirror_status__in=("fulfilled", "unfulfilled", "cancelled", "expired"))
        .first()
    )
    if existing:
        return existing

    proposal_uuid = uuid.uuid4()
    item = {
        "proposal_uuid": str(proposal_uuid),
        "need_remote_uuid": str(shadow.remote_uuid),
        "offer": {
            "title": offer.title[:PROPOSAL_TITLE_CAP],
            "category": offer.category.name,
            "radius_km": offer.radius,
        },
    }
    email = (getattr(offer.offerer.user, "email", "") or "").strip()
    if link.pairing_pepper and email:
        item["blind_token"] = crypto.blind_token(bytes(link.pairing_pepper), email)

    payload = {"proposals": [item]}
    url = client_mod.proposals_url(link.peer.base_url)
    signature = crypto.sign_request("POST", url, json.dumps(payload).encode(), aud=link.peer.instance_id)
    try:
        resp = client_mod.post_proposals(link.peer.base_url, payload, {"X-UMI-Signature": signature})
    except client_mod.FederationClientError as e:
        emit("fed.peer_unreachable", link, details={"peer": link.peer.instance_id, "error": str(e)[:100]})
        raise ProposalError("peer unreachable") from e

    results = resp.get("results") if isinstance(resp, dict) else None
    first = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    status = first.get("status")
    if status not in ("created", "duplicate"):
        raise ProposalError(str(first.get("reason", "rejected"))[:50])
    try:
        remote_match_uuid = uuid.UUID(str(first.get("match_uuid", "")))
    except (ValueError, TypeError):
        remote_match_uuid = None

    fmatch = FederatedMatch.objects.create(
        link=link,
        role="mirror",
        proposal_uuid=proposal_uuid,
        remote_match_uuid=remote_match_uuid,
        remote_need_uuid=shadow.remote_uuid,
        mirror_status="proposed",
        offer=offer,
    )
    emit(
        "fed.proposal_sent",
        fmatch,
        user=actor_user,
        details={"link": str(link.pk), "peer": link.peer.instance_id},
    )
    return fmatch


# ── converging on the authority (§6.3) ───────────────

MIRROR_TERMINAL = ("fulfilled", "unfulfilled", "cancelled", "expired")


def apply_match_event(fmatch, *, event_uuid, kind, contact=None):
    """Apply one signed authority event to this mirror. Idempotent on
    (link, event_uuid); an event invalid for the mirror's current state
    answers `conflict` and triggers a re-sync — the authority never yields,
    the mirror converges (§6.3)."""
    from django.db import IntegrityError

    from apps.matches.models import Match

    from .models import FederationEvent

    if kind not in ("accepted",) + MIRROR_TERMINAL:
        return {"status": "error", "error": "invalid_event"}
    if FederationEvent.objects.filter(link=fmatch.link, event_uuid=event_uuid).exists():
        return {"status": "duplicate"}
    if kind not in Match.VALID_TRANSITIONS.get(fmatch.mirror_status, []):
        _try_resync(fmatch)
        return {"status": "conflict", "state": fmatch.mirror_status}
    try:
        with transaction.atomic():
            FederationEvent.objects.create(
                link=fmatch.link,
                direction="in",
                event_uuid=event_uuid,
                kind=kind,
                state="applied",
                payload={"match_uuid": str(fmatch.remote_match_uuid or "")},
            )
            result = _apply_mirror_state(fmatch, kind, contact)
    except IntegrityError:
        return {"status": "duplicate"}
    emit("fed.match_event_received", fmatch, details={"event": kind, "link": str(fmatch.link_id)})
    return result


def _apply_mirror_state(fmatch, new_status, contact=None):
    """Set the mirror's state + the §8.2/§4.4 side effects. Shared by the
    event path and re-sync (which carries no contact)."""
    from . import outbox

    result = {"status": "applied"}
    offer = fmatch.offer
    if new_status == "accepted":
        clean = outbox.sanitize_contact(contact) if isinstance(contact, dict) else {}
        if offer is not None and clean and outbox.contact_matches_user(clean, offer.offerer.user):
            # §7 backstop, mirror side: same human — never store or release
            # contact; ask the authority to cancel via the outbox.
            emit("fed.selfmatch_detected", fmatch, details={"side": "mirror", "link": str(fmatch.link_id)})
            outbox.queue_cancel_request(fmatch)
            outbox.notify_coordinators(
                fmatch.link.community,
                "Federated match flagged",
                "A cross-community match was flagged: the requester appears to be the same "
                "person as the responder (§8.6). A cancel was requested automatically.",
            )
        else:
            if clean:
                fmatch.contact_payload = clean
                emit("fed.contact_disclosed", fmatch, details={"direction": "inbound", "link": str(fmatch.link_id)})
            if offer is not None:
                # §8.2 both directions: our responder's dict rides the reply,
                # released only against this verified accepted event.
                result["contact"] = offer.offerer.contact_dict(offer.contact_pref)
                emit("fed.contact_disclosed", fmatch, details={"direction": "outbound", "link": str(fmatch.link_id)})
                if offer.status == "active":
                    # single-use across the boundary (the §8.7 offer guard)
                    offer.status = "matched"
                    offer.save(update_fields=["status", "updated_at"])
        fmatch.mirror_status = "accepted"
        fmatch.save(update_fields=["mirror_status", "contact_payload_enc", "contact_payload_dek"])
    else:
        fmatch.mirror_status = new_status
        fmatch.contact_expires_at = timezone.now() + timezone.timedelta(hours=outbox.CONTACT_GRACE_HOURS)
        fmatch.save(update_fields=["mirror_status", "contact_expires_at"])
        if offer is not None and offer.status == "matched":
            offer.status = "fulfilled" if new_status == "fulfilled" else "active"
            offer.save(update_fields=["status", "updated_at"])
    return result


def resync_mirror(fmatch):
    """Pull the authority's signed state and converge (§6.3). Returns the
    authoritative status applied (or already held), None on failure. The
    snapshot is applied regardless of local ordering — it IS the truth."""
    link = fmatch.link
    match_uuid = str(fmatch.remote_match_uuid or "")
    if not match_uuid:
        return None
    url = client_mod.match_url(link.peer.base_url, match_uuid)
    signature = crypto.sign_request("GET", url, b"", aud=link.peer.instance_id)
    try:
        data = client_mod.get_match(link.peer.base_url, match_uuid, {"X-UMI-Signature": signature})
    except client_mod.FederationClientError as e:
        emit("fed.peer_unreachable", link, details={"peer": link.peer.instance_id, "error": str(e)[:100]})
        return None
    token = data.get("match") if isinstance(data, dict) else None
    try:
        payload = crypto.verify_match_state(str(token or ""), link.peer.jwk)
    except crypto.FederationAuthError:
        emit("fed.sig_rejected", link.peer, details={"reason": "bad_match_state"})
        return None
    status = str(payload.get("status", ""))
    if payload.get("match_uuid") != match_uuid or status not in ("proposed",) + ("accepted",) + MIRROR_TERMINAL:
        return None
    if status in ("proposed", fmatch.mirror_status):
        return status  # already converged (or nothing to apply)
    _apply_mirror_state(fmatch, status, contact=None)
    emit("fed.match_event_received", fmatch, details={"event": f"resync:{status}"[:32], "link": str(link.pk)})
    return status


def _try_resync(fmatch):
    """Best-effort — a failed re-sync just waits for the next event/poll."""
    import logging

    try:
        resync_mirror(fmatch)
    except Exception:  # noqa: BLE001  # nosec B110 — never let re-sync break the wire response
        logging.getLogger(__name__).exception("mirror re-sync failed")

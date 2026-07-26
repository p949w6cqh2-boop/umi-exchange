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
    if offer.moderation_hidden:
        # A hidden offer is off the local board; sending it abroad would put its
        # title on a peer instance, outside this community's moderation reach.
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


def apply_match_event(fmatch, *, event_uuid, kind, contact=None, resync_budget=None):
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
        return _duplicate_result(fmatch, kind)
    if kind not in Match.VALID_TRANSITIONS.get(fmatch.mirror_status, []):
        # Bounded: 50 conflicting events in one POST must not become 50 blocking
        # outbound fetches (see ResyncBudget).
        _try_resync(fmatch, budget=resync_budget)
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
        return _duplicate_result(fmatch, kind)
    emit("fed.match_event_received", fmatch, details={"event": kind, "link": str(fmatch.link_id)})
    return result


def _duplicate_result(fmatch, kind):
    """§6.3 replay answer. For a replayed `accepted` whose original reply may
    have been lost mid-crash, re-attach the responder dict — same verified
    peer, same match, same §8.2 audience; the dict is deterministic."""
    result = {"status": "duplicate"}
    offer = fmatch.offer
    if (
        kind == "accepted"
        and offer is not None
        and fmatch.mirror_status in ("accepted", "fulfilled")
        and offer.status in ("matched", "fulfilled")
    ):
        result["contact"] = offer.offerer.contact_dict(offer.contact_pref)
    return result


def _offer_held_elsewhere(fmatch, offer) -> bool:
    """True if a DIFFERENT live match is holding this offer — its `matched`
    status is not ours to release."""
    from apps.matches.models import Match

    if Match.objects.filter(offer=offer, status="accepted").exists():
        return True
    return (
        FederatedMatch.objects.filter(offer=offer, role="mirror", mirror_status="accepted")
        .exclude(pk=fmatch.pk)
        .exists()
    )


def _apply_mirror_state(fmatch, new_status, contact=None, *, include_contact=True):
    """Set the mirror's state + the §8.2/§4.4 side effects, under the offer's
    row lock (caller supplies the transaction). Shared by the event path and
    re-sync — re-sync passes include_contact=False: a snapshot moves no
    contact, so nothing may be stored, released, or audited as disclosed."""
    from apps.offers.models import Offer

    from . import outbox

    result = {"status": "applied"}
    offer = None
    if fmatch.offer_id is not None:
        # §8.7 across the boundary: serialize with local accepts of this offer.
        offer = Offer.objects.select_for_update().get(pk=fmatch.offer_id)
        fmatch.offer = offer
    if new_status == "accepted":
        clean = outbox.sanitize_contact(contact) if isinstance(contact, dict) else {}
        selfmatch = offer is not None and clean and outbox.contact_matches_user(clean, offer.offerer.user)
        # Accepted applies exactly once (atomic + idempotency), so a non-active
        # offer here always means someone ELSE holds it now (§8.7).
        unavailable = offer is None or offer.status != "active"
        if selfmatch or unavailable:
            # Never exchange: the same human on both sides (§7 backstop), or
            # the offer was committed/withdrawn locally in the meantime (§8.7)
            # — ask the authority to cancel; contact neither stored nor sent.
            if selfmatch:
                emit("fed.selfmatch_detected", fmatch, details={"side": "mirror", "link": str(fmatch.link_id)})
            reason = "self_match" if selfmatch else "offer_unavailable"
            outbox.queue_cancel_request(fmatch)
            outbox.notify_coordinators(
                fmatch.link.community,
                "Federated match flagged",
                "A cross-community match accept could not complete "
                f"({'same person on both sides — §8.6' if selfmatch else 'the offer is no longer available'}). "
                "A cancel was requested automatically.",
            )
            result["reason"] = reason
            # Deliberately NOT setting mirror_status='accepted' here. Nothing was
            # exchanged: contact was withheld and a cancel queued. _duplicate_result
            # re-derives disclosure from (mirror_status, offer.status) alone, so
            # marking a refusal 'accepted' made the §6.3 lost-ack replay hand the
            # peer the very contact this branch just refused (#12).
        else:
            if clean and include_contact:
                fmatch.contact_payload = clean
                emit("fed.contact_disclosed", fmatch, details={"direction": "inbound", "link": str(fmatch.link_id)})
            if offer is not None:
                if include_contact:
                    # §8.2 both directions: our responder's dict rides the
                    # reply, released only against this verified accepted event.
                    result["contact"] = offer.offerer.contact_dict(offer.contact_pref)
                    emit(
                        "fed.contact_disclosed",
                        fmatch,
                        details={"direction": "outbound", "link": str(fmatch.link_id)},
                    )
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
        if offer is not None and offer.status == "matched" and not _offer_held_elsewhere(fmatch, offer):
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
    with transaction.atomic():  # _apply_mirror_state locks the offer row
        _apply_mirror_state(fmatch, status, contact=None, include_contact=False)
    emit("fed.match_event_received", fmatch, details={"event": f"resync:{status}"[:32], "link": str(link.pk)})
    return status


class ResyncBudget:
    """How many synchronous re-syncs one inbound request may perform.

    resync_mirror makes a blocking outbound get_match (10s). MatchEventsView
    loops up to 50 events, and a peer that stalls its own get_match while POSTing
    a batch of state-invalid events could keep every gunicorn worker busy — the
    conflict path writes no FederationEvent, so there is no per-item cost to
    throttle it. One re-sync per request is enough for §6.3 convergence: the
    snapshot it fetches covers the whole match, not one event.
    """

    def __init__(self, limit=1):
        self.remaining = limit

    def spend(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


def _try_resync(fmatch, budget=None):
    """Best-effort — a failed re-sync just waits for the next event/poll."""
    import logging

    if budget is not None and not budget.spend():
        return
    try:
        resync_mirror(fmatch)
    except Exception:  # noqa: BLE001  # nosec B110 — never let re-sync break the wire response
        logging.getLogger(__name__).exception("mirror re-sync failed")

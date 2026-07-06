"""
Outbound sharing service (Stage B, §4.1): opt a local Need/Offer into
discovery on a link — gated by an active participant Consent covering
`federated_share` for the peer community. This is the FIRST real caller of
Consent.covers() (§10.2). No PII is stored on the share row; a signed consent
receipt (§4.2) is attached for the receiver to verify.
"""

import json

from django.db import transaction
from django.utils import timezone

from apps.audit.services import emit
from apps.consent.models import Consent

from . import client as client_mod
from . import crypto
from .models import FederatedShare

FEDERATED_SHARE_SCOPE = "federated_share"


class ShareError(Exception):
    """Sharing refused (no covering consent, inactive link, wrong owner …)."""


def _record_owner_user(record):
    """The participant whose consent gates sharing this record."""
    if hasattr(record, "requester_id"):  # Need
        return record.requester.user
    return record.offerer.user  # Offer


def find_share_consent(record, link):
    """An active Consent from the record owner covering federated_share to the
    link's peer community, or None. Uses covers() as the authorization check."""
    owner = _record_owner_user(record)
    for consent in Consent.objects.filter(participant=owner, status="active", grantee_type="community"):
        if consent.covers(
            grantee_type="community", grantee_id=link.remote_community_uuid, scopes=(FEDERATED_SHARE_SCOPE,)
        ):
            return consent
    return None


@transaction.atomic
def share_record(record, link, *, actor_user):
    """Advertise `record` (Need or Offer) on `link`. Raises ShareError unless
    the link is active and an active covering consent exists. Idempotent per
    (link, record) — returns the existing active share if already shared."""
    if link.status != "active":
        raise ShareError("link is not active")
    if record.community_id != link.community_id:
        raise ShareError("record does not belong to the link's community")

    field = "need" if hasattr(record, "requester_id") else "offer"
    existing = FederatedShare.objects.filter(link=link, status="active", **{field: record}).first()
    if existing:
        return existing

    consent = find_share_consent(record, link)
    if consent is None:
        raise ShareError("no active consent covering federated_share for this peer community")

    share = FederatedShare(link=link, consent=consent, **{field: record})
    share.receipt_jws = crypto.build_consent_receipt(
        consent_id=consent.pk,
        record_ref=f"{field}:{share.remote_uuid}",
        scope=[FEDERATED_SHARE_SCOPE],
        granted_at=consent.granted_at.isoformat(),
        expires_at=consent.expires_at.isoformat() if consent.expires_at else None,
        peer_instance_id=link.peer.instance_id,
    )
    share.save()

    if record.share_scope != "federated":
        record.share_scope = "federated"
        record.save(update_fields=["share_scope", "updated_at"])

    emit(
        "fed.share_created",
        share,
        user=actor_user,
        details={"link": str(link.pk), "kind": field, "peer": link.peer.instance_id},
    )
    return share


def revoke_share(share, *, actor_user):
    """Stop advertising a share and send the peer a signed delete-request (§4.3).
    The share leaves our discovery feed immediately; the delete-request asks the
    peer to shred its shadow now rather than wait for TTL/tombstone. Best-effort:
    a dead peer drops it on its next poll anyway (tombstone)."""
    if share.status != "active":
        return share
    share.status = "revoked"
    share.revoked_at = timezone.now()
    share.save(update_fields=["status", "revoked_at"])
    emit("fed.share_revoked", share, user=actor_user, details={"link": str(share.link_id)})
    _send_revocation(share)
    return share


def _send_revocation(share):
    """Notify the peer to shred its shadow of this share. Cross-instance erasure
    is COOPERATIVE, not guaranteed (§4.3) — we ask; the peer SHOULD honor it, and
    the record has already left our feed regardless."""
    link = share.link
    kind = "need" if share.need_id else "offer"
    payload = {
        "revocations": [
            {"remote_uuid": str(share.remote_uuid), "record": f"{kind}:{share.remote_uuid}", "reason": "revoked"}
        ]
    }
    url = client_mod.revocations_url(link.peer.base_url)
    signature = crypto.sign_request("POST", url, json.dumps(payload).encode(), aud=link.peer.instance_id)
    try:
        client_mod.post_revocation(link.peer.base_url, payload, {"X-UMI-Signature": signature})
        emit("fed.consent_revoke_sent", share, details={"link": str(link.pk)})
    except client_mod.FederationClientError as e:
        # The peer will tombstone the row on its next poll; no local blocking.
        emit("fed.peer_unreachable", link, details={"peer": link.peer.instance_id, "error": str(e)[:100]})


def revoke_shares_for_consent(consent, *, actor_user):
    """Revoke every active federated share gated by a consent — the 'revoke at
    home → sharing stops + notify peer' trigger (§4.3). Returns the count."""
    n = 0
    for share in FederatedShare.objects.filter(consent=consent, status="active").select_related("link__peer"):
        revoke_share(share, actor_user=actor_user)
        n += 1
    return n


def share_panel(record, member):
    """Context for the owner's 'Share beyond this community' panel on a
    need/offer detail page, or None when the panel is hidden (flag off, not
    the owner, or no active links). The panel is the §4.1 consent-capture
    surface: one action = digital Consent + FederatedShare + signed receipt."""
    from django.conf import settings

    from .models import FederationLink

    if not getattr(settings, "FEDERATION_ENABLED", False) or member is None:
        return None
    is_need = hasattr(record, "requester_id")
    owner_user_id = record.requester.user_id if is_need else record.offerer.user_id
    if owner_user_id != member.user_id:
        return None
    links = list(
        FederationLink.objects.filter(community_id=record.community_id, status="active").select_related("peer")
    )
    if not links:
        return None
    field = "need" if is_need else "offer"
    shares = {s.link_id: s for s in FederatedShare.objects.filter(status="active", **{field: record})}
    return {
        "record": record,
        "kind": field,
        "rows": [{"link": link, "share": shares.get(link.pk)} for link in links],
    }

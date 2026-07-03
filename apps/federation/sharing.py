"""
Outbound sharing service (Stage B, §4.1): opt a local Need/Offer into
discovery on a link — gated by an active participant Consent covering
`federated_share` for the peer community. This is the FIRST real caller of
Consent.covers() (§10.2). No PII is stored on the share row; a signed consent
receipt (§4.2) is attached for the receiver to verify.
"""

from django.db import transaction
from django.utils import timezone

from apps.audit.services import emit
from apps.consent.models import Consent

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
    """Stop advertising a share (local side of §4.3). Slice-2 adds the signed
    delete-request to the peer; here it disappears from discovery immediately."""
    if share.status != "active":
        return share
    share.status = "revoked"
    share.revoked_at = timezone.now()
    share.save(update_fields=["status", "revoked_at"])
    emit("fed.share_revoked", share, user=actor_user, details={"link": str(share.link_id)})
    return share

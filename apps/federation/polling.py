"""
Inbound discovery poller (Stage B slice 2, §2.1 pull / §4.4 compensation).
Pull a peer's redacted feed and mirror it into short-TTL ShadowListings.
Nothing here is durable: rows are refreshed each poll, tombstoned when they
leave the peer's feed, and swept when their TTL lapses (apps/federation/tasks).
"""

import uuid
from datetime import timedelta

from django.utils import timezone

from apps.audit.services import emit

from . import client as client_mod
from . import crypto
from .models import ShadowListing

SHADOW_TTL = timedelta(days=7)  # §4.4 default
MAX_ROWS = 500


def poll_link(link) -> int:
    """Fetch `link`'s peer feed and upsert ShadowListings. Returns the number
    of live rows after the poll. Unreachable peer → audited, no rows changed."""
    url = client_mod.discovery_url(link.peer.base_url)
    signature = crypto.sign_request("GET", url, b"", aud=link.peer.instance_id)
    try:
        data = client_mod.get_discovery(link.peer.base_url, {"X-UMI-Signature": signature})
    except client_mod.FederationClientError as e:
        emit("fed.peer_unreachable", link, details={"peer": link.peer.instance_id, "error": str(e)[:100]})
        return 0

    listings = data.get("listings") if isinstance(data, dict) else None
    if not isinstance(listings, list):
        return 0

    now = timezone.now()
    seen = set()
    for row in listings[:MAX_ROWS]:
        if not isinstance(row, dict) or row.get("kind") not in ("need", "offer"):
            continue
        try:
            remote_uuid = uuid.UUID(str(row.get("remote_uuid", "")))
        except (ValueError, TypeError):
            continue
        # M-3: verify the signed consent receipt (§4.2) against the peer's
        # published key BEFORE persisting a shadow. A missing/tampered receipt
        # means we can't prove the share was consented — skip it (and let the
        # tombstone below drop any stale shadow for this uuid).
        receipt = str(row.get("receipt_jws", ""))
        try:
            crypto.verify_consent_receipt(receipt, link.peer.jwk)
        except crypto.FederationAuthError:
            emit("fed.receipt_invalid", link, details={"remote_uuid": str(remote_uuid)})
            continue
        seen.add(remote_uuid)
        radius = row.get("radius_km")
        ShadowListing.objects.update_or_create(
            link=link,
            remote_uuid=remote_uuid,
            defaults={
                "kind": row["kind"],
                "category": str(row.get("category", ""))[:100],
                "urgency": str(row.get("urgency", ""))[:10],
                "locality": str(row.get("locality", ""))[:100],
                "freshness": str(row.get("freshness", ""))[:10],
                "radius_km": radius if isinstance(radius, int) and not isinstance(radius, bool) else None,
                "receipt_jws": receipt,
                "expires_at": now + SHADOW_TTL,
            },
        )
    # Tombstone: a row that dropped out of the peer's feed (revoked/expired
    # there) disappears here immediately — re-fetch over persist (§4.4).
    ShadowListing.objects.filter(link=link).exclude(remote_uuid__in=seen).delete()
    return len(seen)

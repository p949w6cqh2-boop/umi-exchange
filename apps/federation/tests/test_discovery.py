"""Discovery endpoint (§2.1 pull) + redaction (§2.2): signed access, PII-free rows."""

import json

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import sharing
from apps.needs.models import Need
from apps.offers.models import Offer

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

DISCOVERY_URL_PATH = "/federation/v1/discovery"


def _site_url():
    from django.conf import settings

    return settings.SITE_URL.rstrip("/") + DISCOVERY_URL_PATH


def _shared_need(world, link):
    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="SENSITIVE title never crosses",
        description="free text never crosses",
        urgency="high",
        neighborhood="12 Oak St",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer Board",
        grantee_type="community",
        grantee_id=link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    sharing.share_record(need, link, actor_user=world.admin_u)
    return need


def test_discovery_requires_signature(client, fed_settings, active_link):
    resp = client.get(DISCOVERY_URL_PATH)
    assert resp.status_code == 403
    assert resp.json()["error"] == "bad_signature"


def test_discovery_returns_only_redacted_rows(client, fed_settings, remote, active_link, world):
    _shared_need(world, active_link)
    sig = remote.sign("GET", _site_url(), b"", fed_settings.instance_id)
    resp = client.get(DISCOVERY_URL_PATH, HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    body = resp.content.decode()
    listings = resp.json()["listings"]
    assert len(listings) == 1
    row = listings[0]
    # §2.2 shape only.
    assert set(row) == {"kind", "remote_uuid", "category", "locality", "freshness", "urgency"}
    assert row["kind"] == "need"
    assert row["category"] == "Food"
    # NOTHING identifying crossed.
    for leak in ("SENSITIVE", "free text", "12 Oak St", str(world.plain.id), "Sam"):
        assert leak not in body
    assert AuditLog.objects.filter(action="fed.discovery_served").exists()


def test_discovery_excludes_revoked_and_local_only(client, fed_settings, remote, active_link, world):
    need = _shared_need(world, active_link)
    share = need.federated_shares.get()
    sharing.revoke_share(share, actor_user=world.admin_u)
    sig = remote.sign("GET", _site_url(), b"", fed_settings.instance_id)
    resp = client.get(DISCOVERY_URL_PATH, HTTP_X_UMI_SIGNATURE=sig)
    assert resp.json()["listings"] == []


def test_discovery_scoped_to_requesting_peer(client, fed_settings, remote, active_link, world):
    """A share on this peer's link must not appear to a DIFFERENT signed peer."""
    _shared_need(world, active_link)
    from joserfc.jwk import OKPKey

    from apps.federation.models import FederationPeer
    from apps.federation.tests.conftest import body_digest, rfc7638_thumbprint

    other_key = OKPKey.generate_key("Ed25519")
    other_pub = other_key.as_dict(private=False)
    other_id = rfc7638_thumbprint(other_pub)
    FederationPeer.objects.create(
        base_url="https://other.example", instance_id=other_id, jwk=other_pub, status="active"
    )

    import time as _t
    import uuid as _u

    from joserfc import jws

    claims = {
        "iss": other_id,
        "aud": fed_settings.instance_id,
        "iat": int(_t.time()),
        "jti": str(_u.uuid4()),
        "htm": "GET",
        "htu": _site_url(),
        "digest": body_digest(b""),
    }
    sig = jws.serialize_compact({"alg": "Ed25519"}, json.dumps(claims).encode(), other_key, algorithms=["Ed25519"])
    resp = client.get(DISCOVERY_URL_PATH, HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    assert resp.json()["listings"] == []  # not this peer's share


def test_offer_redaction_shape(client, fed_settings, remote, active_link, world):
    cat = Category.objects.create(community=world.community, name="Rides")
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="secret",
        radius=10,
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer Board",
        grantee_type="community",
        grantee_id=active_link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    sharing.share_record(offer, active_link, actor_user=world.admin_u)
    sig = remote.sign("GET", _site_url(), b"", fed_settings.instance_id)
    row = client.get(DISCOVERY_URL_PATH, HTTP_X_UMI_SIGNATURE=sig).json()["listings"][0]
    assert set(row) == {"kind", "remote_uuid", "category", "locality", "freshness", "radius_km"}
    assert row["kind"] == "offer"
    assert row["radius_km"] == 10

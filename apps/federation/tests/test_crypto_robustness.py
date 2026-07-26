"""
Federation crypto + robustness (bug-hunt batch 13, #19 #30 #31 #32) — the last
four of the hunt. All default-OFF: fix-before-enabling, none currently firing.

#19 verify_instance_document verifies the signature with the JWK embedded in the
    JWS *header* and checks instance_id == thumbprint(that key) — but never checks
    that the *payload's* jwk is the same key. Callers pin doc["jwk"]. So a peer
    could self-sign with K_evil (instance_id = thumbprint(K_evil)) while putting a
    third party's public key in the payload, and we would pin a key that peer
    cannot sign with — breaking the instance_id == thumbprint(jwk) invariant every
    inbound trust decision rests on.

#30 apply_match_event answers a state-invalid event with a synchronous outbound
    get_match (10s timeout) inside the inbound request, and MatchEventsView loops
    up to 50 events. A peer that stalls its own get_match keeps every worker busy.

#31 HandshakeView assigns status only when constructing a NEW peer. An already-
    active peer asking to link a SECOND community got its pairing material stamped
    and a {"status": "pending"} reply, while peer.status stayed "active" — and both
    approval surfaces filter on status="pending". The request appeared in no
    admin's list and could never be approved: a permanently un-completable
    handshake, with the caller told to wait for an approval that cannot happen.

#32 verify_signed_request json.loads the JWS payload segment inside a try, then
    calls .get() on it OUTSIDE — and json.loads can return a scalar. AttributeError
    is not FederationAuthError, so the wire views (which catch only the latter)
    return 500 rather than 403. Same shape in verify_instance_document, reachable
    unauthenticated via HandshakeView.
"""

import json
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone
from joserfc import jws
from joserfc.jwk import OKPKey

from apps.federation import crypto, mirror
from apps.federation.crypto import FederationAuthError
from apps.federation.models import FederatedMatch, FederationLink, FederationPeer

from .conftest import b64url, rfc7638_thumbprint

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


def _scalar_jws(payload_scalar=42):
    """A syntactically valid 3-segment token whose payload decodes to a scalar."""
    header = b64url(json.dumps({"alg": "Ed25519", "typ": "JWT"}).encode())
    body = b64url(json.dumps(payload_scalar).encode())
    return f"{header}.{body}.{b64url(b'not-a-real-signature')}"


# ------------------------------------------------------------------------ #32
def test_scalar_jws_payload_is_rejected_not_crashed():
    """FederationAuthError, never AttributeError — the wire views only catch the
    former, so anything else becomes an unauthenticated 500."""
    with pytest.raises(FederationAuthError):
        crypto.verify_signed_request(_FakeRequest(_scalar_jws()))


def test_scalar_jws_payload_returns_403_not_500(client, fed_settings, active_link):
    resp = client.get("/federation/v1/discovery", HTTP_X_UMI_SIGNATURE=_scalar_jws())

    assert resp.status_code == 403
    assert resp.json()["error"] == "bad_signature"


def test_scalar_instance_document_is_rejected_not_crashed():
    """The same shape on the unauthenticated handshake path."""
    with pytest.raises(FederationAuthError):
        crypto.verify_instance_document(_scalar_jws())


class _FakeRequest:
    def __init__(self, token):
        self.headers = {"X-UMI-Signature": token}
        self.method = "GET"
        self.body = b""
        self.META = {}


# ------------------------------------------------------------------------ #19
def _instance_document(signing_key, *, payload_jwk=None, instance_id=None):
    """A signed instance document. payload_jwk defaults to the signing key —
    passing a different one is the attack."""
    pub = signing_key.as_dict(private=False)
    payload = {
        "umi_federation": "1",
        "instance_id": instance_id or rfc7638_thumbprint(pub),
        "jwk": payload_jwk if payload_jwk is not None else pub,
        "base_url": "https://peer.example",
        "capabilities": [],
    }
    return jws.serialize_compact(
        {"alg": "Ed25519", "jwk": pub}, json.dumps(payload).encode(), signing_key, algorithms=["Ed25519"]
    )


def test_instance_document_rejects_a_payload_jwk_that_is_not_the_signing_key():
    """Self-signed with K_evil, but advertising a third party's key. Verification
    would pass and callers would pin a key this peer cannot sign with."""
    mine = OKPKey.generate_key("Ed25519")
    someone_else = OKPKey.generate_key("Ed25519").as_dict(private=False)

    with pytest.raises(FederationAuthError):
        crypto.verify_instance_document(_instance_document(mine, payload_jwk=someone_else))


def test_instance_document_rejects_a_missing_payload_jwk():
    """Omitting it entirely must be a clean rejection, not a KeyError 500."""
    mine = OKPKey.generate_key("Ed25519")
    pub = mine.as_dict(private=False)
    payload = {"umi_federation": "1", "instance_id": rfc7638_thumbprint(pub), "base_url": "https://peer.example"}
    token = jws.serialize_compact(
        {"alg": "Ed25519", "jwk": pub}, json.dumps(payload).encode(), mine, algorithms=["Ed25519"]
    )

    with pytest.raises(FederationAuthError):
        crypto.verify_instance_document(token)


def test_instance_document_accepts_a_consistent_document():
    """The guard must not reject honest peers."""
    mine = OKPKey.generate_key("Ed25519")

    doc = crypto.verify_instance_document(_instance_document(mine))

    assert doc["instance_id"] == rfc7638_thumbprint(mine.as_dict(private=False))


# ------------------------------------------------------------------------ #30
def test_conflicting_events_do_not_fan_out_one_sync_fetch_each(monkeypatch, fed_settings, active_link, world):
    """A batch of state-invalid events must not become a batch of blocking 10s
    outbound fetches — that is the worker-exhaustion lever."""
    fmatch = FederatedMatch.objects.create(
        link=active_link, role="mirror", mirror_status="cancelled", proposal_uuid=uuid.uuid4()
    )
    calls = []
    monkeypatch.setattr(mirror, "resync_mirror", lambda fm: calls.append(fm.pk))

    budget = mirror.ResyncBudget()
    for _ in range(50):
        result = mirror.apply_match_event(fmatch, event_uuid=uuid.uuid4(), kind="fulfilled", resync_budget=budget)
        assert result["status"] == "conflict"

    assert len(calls) <= 1, f"50 conflicting events triggered {len(calls)} synchronous re-syncs"


def test_a_single_conflict_still_resyncs(monkeypatch, fed_settings, active_link, world):
    """§6.3 convergence must survive the bound: the first conflict still syncs."""
    fmatch = FederatedMatch.objects.create(
        link=active_link, role="mirror", mirror_status="cancelled", proposal_uuid=uuid.uuid4()
    )
    calls = []
    monkeypatch.setattr(mirror, "resync_mirror", lambda fm: calls.append(fm.pk))

    mirror.apply_match_event(fmatch, event_uuid=uuid.uuid4(), kind="fulfilled", resync_budget=mirror.ResyncBudget())

    assert len(calls) == 1


def test_events_endpoint_bounds_resyncs_across_the_whole_batch(
    monkeypatch, client, fed_settings, remote, active_link, world
):
    """The bound must be applied by the view, not left to callers."""
    fmatch = FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        mirror_status="cancelled",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
    )
    calls = []
    monkeypatch.setattr(mirror, "resync_mirror", lambda fm: calls.append(fm.pk))

    body = json.dumps({"events": [{"event_uuid": str(uuid.uuid4()), "event": "fulfilled"} for _ in range(50)]}).encode()
    url_path = f"/federation/v1/matches/{fmatch.remote_match_uuid}/events"
    from django.conf import settings as dj_settings

    sig = remote.sign("POST", dj_settings.SITE_URL.rstrip("/") + url_path, body, fed_settings.instance_id)
    resp = client.post(url_path, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)

    assert resp.status_code == 200
    assert len(calls) <= 1, f"one POST caused {len(calls)} blocking outbound fetches"


# ------------------------------------------------------------------------ #31
def _second_community(world):
    from apps.communities.models import Community, Member

    community = Community.objects.create(name="St. Brigid's", slug="st-brigids", created_by=world.admin_u)
    Member.objects.create(
        user=world.admin_u, community=community, role="admin", display_name="Father Tom", is_active=True
    )
    return community


def test_second_community_request_from_an_active_peer_reaches_an_admin(client, fed_settings, active_link, world):
    """An active peer asking to link a second community must be approvable, not
    stamped invisibly onto the peer row and answered 'pending' forever."""
    second = _second_community(world)
    peer = active_link.peer
    peer.pairing_salt = "salt-abc"
    peer.pairing_hash = "hash-abc"
    peer.pairing_expires_at = timezone.now() + timezone.timedelta(hours=1)
    peer.target_community_slug = second.slug
    peer.requested_communities = [{"uuid": str(uuid.uuid4()), "label": "Their Second Board"}]
    peer.save()
    client.force_login(world.admin_u)

    resp = client.get(reverse("federation_admin:settings", args=[second.slug]))

    assert resp.status_code == 200
    assert peer in list(resp.context["inbound_peers"]), "the request must appear to the target community's admin"


def test_an_already_linked_community_does_not_relist_the_peer(client, fed_settings, active_link, world):
    """The widened list must not resurface a peer already linked here."""
    peer = active_link.peer
    peer.pairing_salt = "salt-abc"
    peer.pairing_hash = "hash-abc"
    peer.pairing_expires_at = timezone.now() + timezone.timedelta(hours=1)
    peer.target_community_slug = world.community.slug
    peer.save()
    client.force_login(world.admin_u)

    resp = client.get(reverse("federation_admin:settings", args=[world.community.slug]))

    assert peer not in list(resp.context["inbound_peers"])


def test_a_pending_peer_still_lists(client, fed_settings, world):
    """The original behaviour is untouched."""
    peer = FederationPeer.objects.create(
        base_url="https://newpeer.example",
        instance_id="new-peer-instance-id",
        jwk={"kty": "OKP", "crv": "Ed25519", "x": "abc"},
        label="New Peer",
        status="pending",
        pairing_salt="s",
        pairing_hash="h",
        pairing_expires_at=timezone.now() + timezone.timedelta(hours=1),
        target_community_slug=world.community.slug,
    )
    client.force_login(world.admin_u)

    resp = client.get(reverse("federation_admin:settings", args=[world.community.slug]))

    assert peer in list(resp.context["inbound_peers"])
    assert not FederationLink.objects.filter(peer=peer).exists()

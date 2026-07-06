"""
Stage D — attestations (§5.4): a peer asks the party's HOME instance whether
a tag is verified; the answer is a signed, match-bound, 24h-TTL claim derived
from the BUILT MemberTag machine. Self-claimed must read as unverified;
evidence_note never crosses; no portable credentials.
"""

import json
import time
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.utils import timezone
from joserfc import jws

from apps.communities.models import Category
from apps.federation.models import FederatedMatch
from apps.offers.models import Offer
from apps.tags.models import MemberTag, Tag

pytestmark = pytest.mark.django_db

ATTEST_PATH = "/federation/v1/attestations/query"


@pytest.fixture
def attest_world(fed_settings, active_link, world):
    """Mirror-side home: Bob (offerer) holds tags; the peer (authority) asks
    about him via the fmatch it addresses by its own match uuid."""
    cat = Category.objects.create(community=world.community, name="Food")
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="I can drive",
        expires_at=timezone.now() + timedelta(days=30),
    )
    fmatch = FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=uuid.uuid4(),
        mirror_status="accepted",
        offer=offer,
    )
    clergy, _ = Tag.objects.get_or_create(
        community=world.community,
        slug="clergy",
        defaults={"label": "Clergy", "category": "authority", "tier": "admin_verified"},
    )
    clergy.tier = "admin_verified"
    clergy.save(update_fields=["tier"])
    nurse, _ = Tag.objects.get_or_create(
        community=world.community,
        slug="nurse",
        defaults={"label": "Nurse", "category": "professional", "tier": "coordinator_verified"},
    )
    mt = MemberTag.objects.create(member=world.plain, tag=clergy, status="verified", verified_at=timezone.now())
    MemberTag.objects.create(member=world.plain, tag=nurse, status="self_claimed")
    return SimpleNamespace(world=world, link=active_link, fmatch=fmatch, offer=offer, clergy=clergy, nurse=nurse, mt=mt)


def _post_query(client, remote, fed_settings, queries):
    body = json.dumps({"queries": queries}).encode()
    sig = remote.sign("POST", dj_settings.SITE_URL.rstrip("/") + ATTEST_PATH, body, fed_settings.instance_id)
    return client.post(ATTEST_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)


# ── serving side (the party's home) ─────────────────────────────


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_verified_tag_returns_signed_bound_claim(client, fed_settings, remote, attest_world):
    from apps.federation import crypto as fed_crypto

    resp = _post_query(
        client,
        remote,
        fed_settings,
        [{"match_uuid": str(attest_world.fmatch.remote_match_uuid), "tag": "clergy"}],
    )
    assert resp.status_code == 200
    item = resp.json()["results"][0]
    assert item["status"] == "verified"
    payload = jws.deserialize_compact(
        item["attestation"],
        __import__("joserfc").jwk.OKPKey.import_key(fed_crypto.public_jwk()),
        algorithms=["Ed25519"],
    ).payload
    claims = json.loads(payload)
    assert claims["tag"] == "clergy" and claims["status"] == "verified"
    assert claims["tier"] == "admin_verified"
    assert claims["match_uuid"] == str(attest_world.fmatch.remote_match_uuid)  # bound, not portable
    assert claims["exp"] - claims["iat"] == 24 * 3600
    # the verifier accepts it
    verified = fed_crypto.verify_attestation(item["attestation"], fed_crypto.public_jwk(), aud=remote.instance_id)
    assert verified["status"] == "verified"
    # justification text NEVER crosses
    assert "evidence" not in resp.content.decode()
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(action="fed.attestation_served").exists()


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_self_claimed_reads_as_self_claimed(client, fed_settings, remote, attest_world):
    item = _post_query(
        client, remote, fed_settings, [{"match_uuid": str(attest_world.fmatch.remote_match_uuid), "tag": "nurse"}]
    ).json()["results"][0]
    assert item["status"] == "self_claimed"  # UI must style exactly as unverified


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_pending_rejected_or_absent_reads_none(client, fed_settings, remote, attest_world):
    attest_world.mt.status = "pending"
    attest_world.mt.save(update_fields=["status"])
    results = _post_query(
        client,
        remote,
        fed_settings,
        [
            {"match_uuid": str(attest_world.fmatch.remote_match_uuid), "tag": "clergy"},
            {"match_uuid": str(attest_world.fmatch.remote_match_uuid), "tag": "veteran"},
        ],
    ).json()["results"]
    assert results[0]["status"] == "none"  # pending claims nothing
    assert results[1]["status"] == "none"  # no such tag/claim


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_unknown_match_and_signature_required(client, fed_settings, remote, attest_world):
    item = _post_query(client, remote, fed_settings, [{"match_uuid": str(uuid.uuid4()), "tag": "clergy"}]).json()[
        "results"
    ][0]
    assert item["status"] == "unknown_match"
    resp = client.post(ATTEST_PATH, data=b"{}", content_type="application/json")
    assert resp.status_code == 403


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_capability_gate(client, fed_settings, remote, attest_world, settings):
    settings.FEDERATION_CAPABILITIES = ["discovery", "match"]  # attestation withdrawn (§12 D rollback)
    resp = _post_query(
        client, remote, fed_settings, [{"match_uuid": str(attest_world.fmatch.remote_match_uuid), "tag": "clergy"}]
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "capability_unsupported"


def test_instance_document_advertises_capabilities(fed_settings):
    from apps.federation import crypto as fed_crypto

    doc = fed_crypto.verify_instance_document(fed_crypto.build_instance_document())
    assert "attestation" in doc["capabilities"] and "match" in doc["capabilities"]


def test_expired_attestation_rejected(fed_settings):
    from apps.federation import crypto as fed_crypto

    now = int(time.time())
    stale = {
        "tag": "clergy",
        "status": "verified",
        "tier": "admin_verified",
        "match_uuid": str(uuid.uuid4()),
        "home": fed_crypto.my_instance_id(),
        "aud": "someone",
        "iat": now - 90000,
        "exp": now - 3600,
    }
    token = jws.serialize_compact(
        {"alg": "Ed25519"}, json.dumps(stale).encode(), fed_crypto.load_instance_key(), algorithms=["Ed25519"]
    )
    with pytest.raises(fed_crypto.FederationAuthError):
        fed_crypto.verify_attestation(token, fed_crypto.public_jwk(), aud="someone")


# ── asking side ─────────────────────────────────────────────────


def test_request_attestation_roundtrip(attest_world, monkeypatch):
    """The asking home verifies the returned claim against the pinned peer
    key and cross-checks tag + match binding."""
    from joserfc.jwk import OKPKey

    from apps.federation import crypto as fed_crypto
    from apps.federation import matching

    peer = attest_world.link.peer
    peer.capabilities = ["discovery", "match", "attestation"]
    peer.save(update_fields=["capabilities"])
    remote_key = OKPKey.generate_key("Ed25519")
    peer.jwk = remote_key.as_dict(private=False)
    peer.save(update_fields=["jwk"])

    now = int(time.time())
    claims = {
        "tag": "clergy",
        "status": "verified",
        "tier": "admin_verified",
        "verified_at": "2026-07-01T00:00:00Z",
        "match_uuid": str(attest_world.fmatch.remote_match_uuid),
        "home": "peer",
        "aud": fed_crypto.my_instance_id(),
        "iat": now,
        "exp": now + 3600,
    }
    token = jws.serialize_compact({"alg": "Ed25519"}, json.dumps(claims).encode(), remote_key, algorithms=["Ed25519"])
    monkeypatch.setattr(
        "apps.federation.matching.client_mod.post_attestations",
        lambda base_url, payload, headers: {
            "results": [
                {"match_uuid": claims["match_uuid"], "tag": "clergy", "status": "verified", "attestation": token}
            ]
        },
    )
    result = matching.request_attestation(attest_world.fmatch, "clergy")
    assert result["status"] == "verified" and result["tier"] == "admin_verified"


def test_request_attestation_rejects_tampered_or_unsupported(attest_world, monkeypatch):
    from apps.federation import matching

    peer = attest_world.link.peer
    peer.capabilities = []  # peer doesn't offer attestation
    peer.save(update_fields=["capabilities"])
    assert matching.request_attestation(attest_world.fmatch, "clergy")["status"] == "unsupported"

    peer.capabilities = ["attestation"]
    peer.save(update_fields=["capabilities"])
    monkeypatch.setattr(
        "apps.federation.matching.client_mod.post_attestations",
        lambda *a, **k: {"results": [{"tag": "clergy", "status": "verified", "attestation": "not.a.token"}]},
    )
    assert matching.request_attestation(attest_world.fmatch, "clergy")["status"] == "unavailable"


# ── coordinator UI ──────────────────────────────────────────────


@pytest.fixture
def authority_attest(authority_match, world):
    return authority_match


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_coordinator_can_ask_and_sees_result(client, authority_attest, world, monkeypatch):
    Tag.objects.get_or_create(
        community=world.community,
        slug="clergy",
        defaults={"label": "Clergy", "category": "authority", "tier": "admin_verified"},
    )
    monkeypatch.setattr(
        "apps.federation.views.matching.request_attestation",
        lambda fmatch, tag: {"status": "verified", "tier": "admin_verified", "verified_at": "2026-07-01"},
    )
    client.force_login(world.admin_u)
    url = f"/c/{world.community.slug}/federation/matches/{authority_attest.fmatch.pk}/attest"
    html = client.get(url, {"tag": "clergy"}).content.decode()
    assert "Verified by their community" in html

    monkeypatch.setattr(
        "apps.federation.views.matching.request_attestation", lambda fmatch, tag: {"status": "self_claimed"}
    )
    html = client.get(url, {"tag": "clergy"}).content.decode()
    assert "Self-reported only" in html


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_attest_control_is_coordinator_only(client, authority_attest, world):
    client.force_login(world.plain_u)
    url = f"/c/{world.community.slug}/federation/matches/{authority_attest.fmatch.pk}/attest"
    assert client.get(url, {"tag": "clergy"}).status_code == 404

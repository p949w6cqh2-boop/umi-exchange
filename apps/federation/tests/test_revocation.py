"""Revocation propagation (Stage B slice 3, §4.3): stop + notify + shred."""

import json
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import sharing
from apps.federation.client import FederationClientError
from apps.federation.models import ShadowListing
from apps.needs.models import Need

pytestmark = pytest.mark.django_db

REVOCATIONS_PATH = "/federation/v1/consent/revocations"


def _revocations_url():
    from django.conf import settings

    return settings.SITE_URL.rstrip("/") + REVOCATIONS_PATH


@pytest.fixture
def shared_need(fed_settings, active_link, world):
    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="x",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer",
        grantee_type="community",
        grantee_id=active_link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    return need, sharing.share_record(need, active_link, actor_user=world.admin_u)


# ── Outbound: revoke → notify peer ──


def test_revoke_share_sends_signed_delete_request(shared_need, world, monkeypatch):
    _need, share = shared_need
    captured = {}
    monkeypatch.setattr(
        "apps.federation.sharing.client_mod.post_revocation",
        lambda base_url, payload, headers: captured.update(payload=payload, headers=headers) or {"results": []},
    )
    sharing.revoke_share(share, actor_user=world.admin_u)
    share.refresh_from_db()
    assert share.status == "revoked"
    assert captured["payload"]["revocations"][0]["remote_uuid"] == str(share.remote_uuid)
    assert "X-UMI-Signature" in captured["headers"]
    assert AuditLog.objects.filter(action="fed.consent_revoke_sent").exists()


def test_revoke_share_survives_unreachable_peer(shared_need, world, monkeypatch):
    _need, share = shared_need

    def boom(*a, **k):
        raise FederationClientError("down")

    monkeypatch.setattr("apps.federation.sharing.client_mod.post_revocation", boom)
    sharing.revoke_share(share, actor_user=world.admin_u)
    share.refresh_from_db()
    assert share.status == "revoked"  # local revoke still succeeds
    assert AuditLog.objects.filter(action="fed.peer_unreachable").exists()


def test_revoke_shares_for_consent(shared_need, world, monkeypatch):
    _need, share = shared_need
    monkeypatch.setattr("apps.federation.sharing.client_mod.post_revocation", lambda *a, **k: {"results": []})
    assert sharing.revoke_shares_for_consent(share.consent, actor_user=world.admin_u) == 1
    share.refresh_from_db()
    assert share.status == "revoked"


def test_consent_revoke_view_cascades_to_shares(shared_need, world, monkeypatch, client, settings):
    settings.FEDERATION_ENABLED = True
    _need, share = shared_need
    monkeypatch.setattr("apps.federation.sharing.client_mod.post_revocation", lambda *a, **k: {"results": []})
    client.force_login(world.plain_u)  # the need's requester = the consent participant
    resp = client.post(reverse("consent-revoke", kwargs={"pk": share.consent.pk}))
    assert resp.status_code == 302
    share.refresh_from_db()
    assert share.status == "revoked"
    assert AuditLog.objects.filter(action="fed.share_revoked").exists()


# ── Inbound: peer asks us to shred our shadow ──


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_inbound_revocation_shreds_matching_shadow(client, fed_settings, remote, active_link):
    ru = uuid.uuid4()
    ShadowListing.objects.create(
        link=active_link, kind="need", remote_uuid=ru, expires_at=timezone.now() + timezone.timedelta(days=7)
    )
    body = json.dumps({"revocations": [{"remote_uuid": str(ru), "record": f"need:{ru}", "reason": "revoked"}]}).encode()
    sig = remote.sign("POST", _revocations_url(), body, fed_settings.instance_id)
    resp = client.post(REVOCATIONS_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "shredded"
    assert not ShadowListing.objects.filter(remote_uuid=ru).exists()
    assert AuditLog.objects.filter(action="fed.consent_revoke_received").exists()
    assert AuditLog.objects.filter(action="fed.shadow_shredded").exists()


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_inbound_revocation_unknown_uuid(client, fed_settings, remote, active_link):
    body = json.dumps({"revocations": [{"remote_uuid": str(uuid.uuid4())}]}).encode()
    sig = remote.sign("POST", _revocations_url(), body, fed_settings.instance_id)
    resp = client.post(REVOCATIONS_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "unknown"


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_inbound_revocation_requires_signature(client, fed_settings, active_link):
    resp = client.post(REVOCATIONS_PATH, data=b"{}", content_type="application/json")
    assert resp.status_code == 403


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_inbound_revocation_only_shreds_own_peers_shadow(client, fed_settings, remote, active_link, world):
    """A peer must not be able to shred a shadow sourced from a DIFFERENT peer."""
    from apps.federation.models import FederationLink, FederationPeer

    other_peer = FederationPeer.objects.create(
        base_url="https://other.example", instance_id="other-thumbprint", jwk={}, status="active"
    )
    other_link = FederationLink.objects.create(
        peer=other_peer, community=world.community, remote_community_uuid=uuid.uuid4(), status="active"
    )
    ru = uuid.uuid4()
    ShadowListing.objects.create(
        link=other_link, kind="need", remote_uuid=ru, expires_at=timezone.now() + timezone.timedelta(days=7)
    )
    body = json.dumps({"revocations": [{"remote_uuid": str(ru)}]}).encode()
    sig = remote.sign("POST", _revocations_url(), body, fed_settings.instance_id)  # signed by `remote`, not other_peer
    resp = client.post(REVOCATIONS_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)
    assert resp.json()["results"][0]["status"] == "unknown"
    assert ShadowListing.objects.filter(remote_uuid=ru).exists()  # untouched

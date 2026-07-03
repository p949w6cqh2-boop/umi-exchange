"""Wire endpoints: /.well-known/umi-federation, handshake, handshake/confirm."""

import json
import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.federation import crypto
from apps.federation.models import FederationLink, FederationPeer

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

CONFIRM_URL = "http://testserver/federation/v1/handshake/confirm"


def post_json(client, path, payload, **extra):
    data = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    return client.post(path, data=data, content_type="application/json", **extra)


class TestWellKnown:
    def test_serves_signed_instance_document(self, client, fed_settings, db):
        resp = client.get("/.well-known/umi-federation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["umi_federation"] == "1"
        payload = crypto.verify_instance_document(data["document"])
        assert payload["instance_id"] == fed_settings.instance_id

    def test_flag_off_view_guard_404s(self, client, settings, db):
        settings.FEDERATION_ENABLED = False
        assert client.get("/.well-known/umi-federation").status_code == 404


def handshake_payload(remote, community_uuid=None):
    code = crypto.mint_pairing_code()
    salt = uuid.uuid4().hex
    return code, {
        "document": remote.instance_document(),
        "pairing": {"salt": salt, "hash": crypto.remote_code_hash(code, salt)},
        "community": {"uuid": str(community_uuid or uuid.uuid4()), "label": "Their Parish Board"},
    }


class TestInboundHandshake:
    def test_happy_path_creates_pending_peer(self, client, fed_settings, remote, db):
        code, payload = handshake_payload(remote)
        resp = post_json(client, "/federation/v1/handshake", payload, HTTP_X_REAL_IP="10.1.1.1")
        assert resp.status_code == 200
        assert resp.json() == {"status": "pending"}
        p = FederationPeer.objects.get(instance_id=remote.instance_id)
        assert p.status == "pending"
        assert p.jwk == remote.jwk
        assert p.pairing_hash and p.pairing_salt
        assert p.requested_communities[0]["label"] == "Their Parish Board"
        assert AuditLog.objects.filter(action="fed.link_requested", resource_type="federationpeer").exists()

    def test_invalid_json_400(self, client, fed_settings, db):
        resp = post_json(client, "/federation/v1/handshake", "not json{", HTTP_X_REAL_IP="10.1.1.2")
        assert resp.status_code == 400
        assert resp.json() == {"error": "invalid JSON"}

    def test_oversized_body_400(self, client, fed_settings, remote, db):
        _, payload = handshake_payload(remote)
        payload["community"]["label"] = "x" * 20000
        resp = post_json(client, "/federation/v1/handshake", payload, HTTP_X_REAL_IP="10.1.1.3")
        assert resp.status_code == 400

    def test_bad_document_signature_400(self, client, fed_settings, remote, db):
        _, payload = handshake_payload(remote)
        payload["document"] = remote.instance_document(tamper=True)
        resp = post_json(client, "/federation/v1/handshake", payload, HTTP_X_REAL_IP="10.1.1.4")
        assert resp.status_code == 400
        assert resp.json() == {"error": "bad_document"}
        assert not FederationPeer.objects.exists()

    def test_repeat_request_updates_not_duplicates(self, client, fed_settings, remote, db):
        for ip in ("10.1.1.5", "10.1.1.6"):
            _, payload = handshake_payload(remote)
            assert post_json(client, "/federation/v1/handshake", payload, HTTP_X_REAL_IP=ip).status_code == 200
        assert FederationPeer.objects.filter(instance_id=remote.instance_id).count() == 1

    def test_throttled_after_five_per_hour_per_ip(self, client, fed_settings, remote, db):
        ip = "10.9.9.9"
        for _ in range(5):
            _, payload = handshake_payload(remote)
            assert post_json(client, "/federation/v1/handshake", payload, HTTP_X_REAL_IP=ip).status_code in (200, 400)
        _, payload = handshake_payload(remote)
        assert post_json(client, "/federation/v1/handshake", payload, HTTP_X_REAL_IP=ip).status_code == 429


class TestConfirm:
    @pytest.fixture
    def pending_link(self, world, peer):
        """A-side state right after initiating: pending link with a local code hash."""
        self.code = crypto.mint_pairing_code()
        return FederationLink.objects.create(
            peer=peer,
            community=world.community,
            requested_by_us=True,
            pairing_code_hash=crypto.local_code_hash(self.code),
            pairing_expires_at=timezone.now() + timezone.timedelta(hours=24),
        )

    def _confirm(self, client, fed_settings, remote, body: dict, sig=None):
        raw = json.dumps(body).encode()
        sig = sig or remote.sign("POST", CONFIRM_URL, raw, fed_settings.instance_id)
        return client.post(
            "/federation/v1/handshake/confirm", data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig
        )

    def test_happy_path_activates_link(self, client, fed_settings, remote, world, peer, pending_link):
        body = {"code": self.code, "community": {"uuid": str(uuid.uuid4()), "label": "Peer Board"}}
        resp = self._confirm(client, fed_settings, remote, body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["community"]["uuid"] == str(world.community.id)
        pending_link.refresh_from_db()
        peer.refresh_from_db()
        assert pending_link.status == "active"
        assert str(pending_link.remote_community_uuid) == body["community"]["uuid"]
        assert pending_link.remote_community_label == "Peer Board"
        assert len(bytes(pending_link.pairing_pepper)) == 32
        assert pending_link.pairing_code_hash == ""  # consumed
        assert peer.status == "active"
        assert AuditLog.objects.filter(action="fed.link_approved", resource_type="federationlink").exists()

    def test_wrong_code_403(self, client, fed_settings, remote, pending_link):
        body = {"code": "WRONGCODE111", "community": {"uuid": str(uuid.uuid4()), "label": "x"}}
        resp = self._confirm(client, fed_settings, remote, body)
        assert resp.status_code == 403
        assert resp.json() == {"error": "bad_pairing"}
        pending_link.refresh_from_db()
        assert pending_link.status == "pending"

    def test_expired_code_403(self, client, fed_settings, remote, pending_link):
        FederationLink.objects.filter(pk=pending_link.pk).update(
            pairing_expires_at=timezone.now() - timezone.timedelta(minutes=1)
        )
        body = {"code": self.code, "community": {"uuid": str(uuid.uuid4()), "label": "x"}}
        assert self._confirm(client, fed_settings, remote, body).status_code == 403

    def test_replay_403(self, client, fed_settings, remote, pending_link):
        raw_body = {"code": self.code, "community": {"uuid": str(uuid.uuid4()), "label": "Peer Board"}}
        raw = json.dumps(raw_body).encode()
        sig = remote.sign("POST", CONFIRM_URL, raw, fed_settings.instance_id)
        first = client.post(
            "/federation/v1/handshake/confirm", data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig
        )
        assert first.status_code == 200
        second = client.post(
            "/federation/v1/handshake/confirm", data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig
        )
        assert second.status_code == 403
        assert second.json() == {"error": "replayed"}

    def test_unsigned_403(self, client, fed_settings, remote, pending_link):
        resp = post_json(client, "/federation/v1/handshake/confirm", {"code": self.code})
        assert resp.status_code == 403
        assert resp.json() == {"error": "bad_signature"}
        assert (
            AuditLog.objects.filter(action="fed.sig_rejected").count() == 0
        )  # unknown sender → no resource to hang it on

    def test_unknown_iss_403(self, client, fed_settings, remote, world, db):
        body = {"code": "ANYCODE00000", "community": {"uuid": str(uuid.uuid4()), "label": "x"}}
        raw = json.dumps(body).encode()
        sig = remote.sign("POST", CONFIRM_URL, raw, fed_settings.instance_id)  # remote has no peer row
        resp = client.post(
            "/federation/v1/handshake/confirm", data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig
        )
        assert resp.status_code == 403

    def test_sig_rejected_audited_for_known_peer(self, client, fed_settings, remote, peer, pending_link):
        body = {"code": self.code, "community": {"uuid": str(uuid.uuid4()), "label": "x"}}
        raw = json.dumps(body).encode()
        sig = remote.sign("POST", CONFIRM_URL, raw, "wrong-audience")
        client.post(
            "/federation/v1/handshake/confirm", data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig
        )
        assert AuditLog.objects.filter(action="fed.sig_rejected", resource_type="federationpeer").exists()

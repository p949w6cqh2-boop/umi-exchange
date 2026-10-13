"""
A pending peer passes no signature check but the one that finishes linking (the founder's call,
2026-10-13, bug hunt L64).

Any anonymous handshake creates a pending peer, and verify_signed_request accepted every peer
that was not blocked, so a server that had only knocked passed the signature check on every
federation endpoint. Each data query also asks for an active link, so it got nothing back, but
the signature check is the door and it should not open for a stranger. Now only the handshake
confirm (the signed step that activates a link we asked for) accepts a pending peer.
"""

import json
import uuid

import pytest
from django.conf import settings

from apps.audit.models import AuditLog
from apps.federation.models import FederationLink

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

MATCH = uuid.uuid4()
ENDPOINTS = [
    ("GET", "/federation/v1/discovery", b""),
    ("POST", "/federation/v1/consent/revocations", b"{}"),
    ("POST", "/federation/v1/proposals", b"{}"),
    ("POST", f"/federation/v1/matches/{MATCH}/events", b"{}"),
    ("GET", f"/federation/v1/matches/{MATCH}", b""),
    ("POST", "/federation/v1/attestations/query", b"{}"),
]


def _call(client, remote, fed_settings, method, path, body):
    sig = remote.sign(method, settings.SITE_URL.rstrip("/") + path, body, fed_settings.instance_id)
    if method == "GET":
        return client.get(path, HTTP_X_UMI_SIGNATURE=sig)
    return client.post(path, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS, ids=[e[1].split("/")[3] for e in ENDPOINTS])
def test_a_pending_peer_is_refused(client, fed_settings, remote, peer, method, path, body):
    assert peer.status == "pending"
    resp = _call(client, remote, fed_settings, method, path, body)

    assert resp.status_code == 403
    assert resp.json()["error"] == "not_approved"
    row = AuditLog.objects.get(action="fed.sig_rejected", resource_id=peer.pk)
    assert row.details == {"reason": "peer_pending"}


def test_an_active_peer_still_passes(client, fed_settings, remote, active_link):
    resp = _call(client, remote, fed_settings, "GET", "/federation/v1/discovery", b"")
    assert resp.status_code == 200


def test_a_pending_peer_can_still_finish_a_link_we_asked_for(client, fed_settings, remote, peer, world):
    from apps.federation import crypto

    link = FederationLink.objects.create(
        peer=peer,
        community=world.community,
        status="pending",
        requested_by_us=True,
        pairing_code_hash=crypto.local_code_hash("ABCD-2345"),
    )
    body = json.dumps({"code": "ABCD-2345", "community": {"uuid": str(uuid.uuid4()), "label": "Peer Board"}}).encode()
    resp = _call(client, remote, fed_settings, "POST", "/federation/v1/handshake/confirm", body)

    assert resp.status_code == 200, resp.content
    link.refresh_from_db()
    peer.refresh_from_db()
    assert link.status == "active"
    assert peer.status == "active"

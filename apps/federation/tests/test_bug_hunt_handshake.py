"""2026-10 bug hunt lead (verified): anyone could overwrite a peer's handshake.

An instance document is public (/.well-known) and binds no audience or time, so the handshake,
anonymous by design, took any replay of it as the peer itself: anyone could overwrite a pending
or active peer's pairing salt and hash, its requested community and its target community. That
spoils a real pairing and lists a request the peer never made. A handshake must now be signed
by the key its document names, for our audience and URL, once (the §3.2 claims every other
signed request carries).
"""

import uuid

import pytest
from django.core.cache import cache
from joserfc.jwk import OKPKey

from apps.federation import crypto
from apps.federation.models import FederationPeer
from apps.federation.tests.conftest import HANDSHAKE_PATH, signed_handshake

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


@pytest.fixture(autouse=True)
def _fresh_throttle():
    cache.clear()  # 5 handshakes an hour per IP


def _payload(remote):
    code = crypto.mint_pairing_code()
    salt = uuid.uuid4().hex
    return {
        "document": remote.instance_document(),
        "pairing": {"salt": salt, "hash": crypto.remote_code_hash(code, salt)},
        "community": {"uuid": str(uuid.uuid4()), "label": "Their Parish Board"},
    }


def _unsigned(client, payload):
    import json

    return client.post(HANDSHAKE_PATH, data=json.dumps(payload), content_type="application/json")


def test_an_unsigned_handshake_is_refused(client, fed_settings, remote):
    resp = _unsigned(client, _payload(remote))

    assert resp.status_code == 403
    assert not FederationPeer.objects.exists()


@pytest.mark.parametrize("status", ["pending", "active"])
def test_a_replayed_document_cannot_overwrite_a_peers_pairing(client, fed_settings, remote, peer, status):
    peer.status = status
    peer.pairing_salt, peer.pairing_hash = "real-salt", "real-hash"
    peer.save()

    resp = _unsigned(client, _payload(remote))  # the public document, replayed by someone else

    assert resp.status_code == 403
    peer.refresh_from_db()
    assert (peer.pairing_salt, peer.pairing_hash) == ("real-salt", "real-hash")


def test_a_handshake_signed_by_another_key_is_refused(client, fed_settings, remote):
    stranger = OKPKey.generate_key("Ed25519")

    resp = signed_handshake(client, remote, fed_settings, _payload(remote), key_override=stranger)

    assert resp.status_code == 403
    assert not FederationPeer.objects.exists()


def test_a_signed_handshake_is_accepted(client, fed_settings, remote):
    resp = signed_handshake(client, remote, fed_settings, _payload(remote))

    assert resp.status_code == 200
    assert FederationPeer.objects.get(instance_id=remote.instance_id).pairing_hash


def test_the_same_signed_handshake_cannot_be_replayed(client, fed_settings, remote, settings):
    import json

    payload = _payload(remote)
    raw = json.dumps(payload).encode()
    sig = remote.sign("POST", settings.SITE_URL.rstrip("/") + HANDSHAKE_PATH, raw, fed_settings.instance_id)

    first = client.post(HANDSHAKE_PATH, data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)
    again = client.post(
        HANDSHAKE_PATH, data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig, HTTP_X_REAL_IP="10.3.3.3"
    )

    assert first.status_code == 200
    assert again.status_code == 403


def test_we_sign_the_handshakes_we_send(client, fed_settings, world, remote, monkeypatch):
    import json

    from django.urls import reverse
    from joserfc import jws

    from apps.federation import views as fed_views

    monkeypatch.setattr(fed_views.client_mod, "fetch_instance_document", lambda base_url: remote.instance_document())
    sent = {}

    def fake_post(base_url, payload, headers):
        sent.update(payload=payload, headers=headers)
        return {"status": "pending"}

    monkeypatch.setattr(fed_views.client_mod, "post_handshake", fake_post)
    client.force_login(world.admin_u)

    client.post(
        reverse("federation_admin:settings", kwargs={"slug": world.community.slug}),
        {"action": "initiate", "base_url": "https://peer.example"},
    )

    token = sent["headers"]["X-UMI-Signature"]
    claims = json.loads(
        jws.deserialize_compact(token, OKPKey.import_key(fed_settings.jwk), algorithms=["Ed25519"]).payload
    )
    assert claims["aud"] == remote.instance_id
    assert claims["htu"] == "https://peer.example" + HANDSHAKE_PATH
    assert claims["digest"] == crypto.request_body_digest(json.dumps(sent["payload"]).encode())

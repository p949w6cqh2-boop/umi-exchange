"""
Stage C2 — the match-events wire endpoint (§6.2 steps 6-9, §6.3) and the
signed authoritative-state re-sync. Wire tests sign as the remote peer so
they pin the contract, not the implementation (the conftest pattern).
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

from apps.audit.models import AuditLog
from apps.federation.models import FederatedMatch, FederationEvent

pytestmark = pytest.mark.django_db


def _events_path(match_uuid):
    return f"/federation/v1/matches/{match_uuid}/events"


def _url(path):
    return dj_settings.SITE_URL.rstrip("/") + path


def _post_events(client, remote, fed_settings, match_uuid, events):
    body = json.dumps({"events": events}).encode()
    sig = remote.sign("POST", _url(_events_path(match_uuid)), body, fed_settings.instance_id)
    return client.post(_events_path(match_uuid), data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)


@pytest.fixture
def mirror_fmatch(fed_settings, active_link, world):
    """A mirror-side FederatedMatch as send_proposal leaves it."""
    from apps.communities.models import Category
    from apps.offers.models import Offer

    active_link.pairing_pepper = b"1" * 32
    active_link.save(update_fields=["pairing_pepper"])
    world.plain_u.email = "bob@example.test"
    world.plain_u.save(update_fields=["email"])
    cat = Category.objects.create(community=world.community, name="Food")
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="I can shop",
        contact_pref="email",
        expires_at=timezone.now() + timedelta(days=30),
    )
    fmatch = FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=uuid.uuid4(),
        mirror_status="proposed",
        offer=offer,
    )
    return SimpleNamespace(fmatch=fmatch, offer=offer, link=active_link, responder=world.plain)


ACCEPT_CONTACT = {"display_name": "Maria", "preference": "email", "email": "maria@peer.test"}


# ── mirror side: authority events land here ─────────────────────


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_accepted_event_applies_and_exchanges_contact(client, fed_settings, remote, mirror_fmatch):
    resp = _post_events(
        client,
        remote,
        fed_settings,
        mirror_fmatch.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "accepted", "contact": ACCEPT_CONTACT}],
    )
    assert resp.status_code == 200
    item = resp.json()["results"][0]
    assert item["status"] == "applied"
    # §8.2 both directions: our responder's dict rides the reply
    assert item["contact"]["email"] == "bob@example.test"

    fm = mirror_fmatch.fmatch
    fm.refresh_from_db()
    assert fm.mirror_status == "accepted"
    assert fm.contact_payload["email"] == "maria@peer.test"
    assert b"maria@peer.test" not in bytes(fm.contact_payload_enc)
    mirror_fmatch.offer.refresh_from_db()
    assert mirror_fmatch.offer.status == "matched"  # single-use across the boundary
    assert AuditLog.objects.filter(action="fed.match_event_received").exists()
    assert AuditLog.objects.filter(action="fed.contact_disclosed").count() == 2  # in + out


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_event_replay_returns_duplicate(client, fed_settings, remote, mirror_fmatch):
    eid = str(uuid.uuid4())
    events = [{"event_uuid": eid, "event": "accepted", "contact": ACCEPT_CONTACT}]
    first = _post_events(client, remote, fed_settings, mirror_fmatch.fmatch.remote_match_uuid, events)
    second = _post_events(client, remote, fed_settings, mirror_fmatch.fmatch.remote_match_uuid, events)
    assert first.json()["results"][0]["status"] == "applied"
    assert second.json()["results"][0]["status"] == "duplicate"
    assert FederationEvent.objects.filter(direction="in", event_uuid=eid).count() == 1


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_terminal_event_starts_contact_grace_and_releases_offer(client, fed_settings, remote, mirror_fmatch):
    _post_events(
        client,
        remote,
        fed_settings,
        mirror_fmatch.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "accepted", "contact": ACCEPT_CONTACT}],
    )
    resp = _post_events(
        client,
        remote,
        fed_settings,
        mirror_fmatch.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "cancelled"}],
    )
    assert resp.json()["results"][0]["status"] == "applied"
    fm = mirror_fmatch.fmatch
    fm.refresh_from_db()
    assert fm.mirror_status == "cancelled"
    assert fm.contact_expires_at is not None  # §4.4: terminal + 72 h grace
    assert fm.contact_expires_at > timezone.now() + timedelta(hours=71)
    mirror_fmatch.offer.refresh_from_db()
    assert mirror_fmatch.offer.status == "active"  # released for local matching again


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_mirror_backstop_blocks_self_match_contact(client, fed_settings, remote, mirror_fmatch):
    """§7 backstop, mirror side: the requester's revealed contact IS our
    responder. No contact stored, none returned, cancel requested."""
    contact = {"display_name": "B", "preference": "email", "email": "BOB@example.test"}
    resp = _post_events(
        client,
        remote,
        fed_settings,
        mirror_fmatch.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "accepted", "contact": contact}],
    )
    item = resp.json()["results"][0]
    assert item["status"] == "applied"
    assert "contact" not in item
    fm = mirror_fmatch.fmatch
    fm.refresh_from_db()
    assert fm.contact_payload is None
    assert AuditLog.objects.filter(action="fed.selfmatch_detected").exists()
    assert FederationEvent.objects.filter(direction="out", kind="cancel_requested").exists()


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_out_of_order_event_conflicts_and_resyncs(client, fed_settings, remote, mirror_fmatch, monkeypatch):
    resynced = []
    monkeypatch.setattr("apps.federation.mirror.resync_mirror", lambda fm: resynced.append(fm.pk))
    resp = _post_events(
        client,
        remote,
        fed_settings,
        mirror_fmatch.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "fulfilled"}],  # while still proposed
    )
    item = resp.json()["results"][0]
    assert item["status"] == "conflict"
    assert resynced == [mirror_fmatch.fmatch.pk]


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_events_require_signature_and_known_match(client, fed_settings, remote, mirror_fmatch):
    resp = client.post(
        _events_path(mirror_fmatch.fmatch.remote_match_uuid), data=b"{}", content_type="application/json"
    )
    assert resp.status_code == 403
    resp = _post_events(
        client, remote, fed_settings, uuid.uuid4(), [{"event_uuid": str(uuid.uuid4()), "event": "accepted"}]
    )
    assert resp.status_code == 404


# ── authority side: mirror may request a cancel ─────────────────


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_cancel_requested_applies_under_authority_lock(client, fed_settings, remote, authority_match):
    resp = _post_events(
        client,
        remote,
        fed_settings,
        authority_match.match.id,
        [{"event_uuid": str(uuid.uuid4()), "event": "cancel_requested"}],
    )
    assert resp.json()["results"][0]["status"] == "applied"
    authority_match.match.refresh_from_db()
    assert authority_match.match.status == "cancelled"
    # the authority echoes the outcome back through the outbox (§6.2 step 9)
    assert FederationEvent.objects.filter(direction="out", kind="cancelled").exists()


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_cancel_requested_on_terminal_match_conflicts(client, fed_settings, remote, authority_match):
    authority_match.match.transition_to("accepted")
    authority_match.match.transition_to("fulfilled")
    resp = _post_events(
        client,
        remote,
        fed_settings,
        authority_match.match.id,
        [{"event_uuid": str(uuid.uuid4()), "event": "cancel_requested"}],
    )
    item = resp.json()["results"][0]
    assert item["status"] == "conflict"
    assert item["authoritative_state"] == "fulfilled"


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_authority_rejects_mirror_only_events(client, fed_settings, remote, authority_match):
    """A peer must not be able to drive OUR authoritative state with
    accepted/fulfilled events — the lock lives here (§6.1)."""
    resp = _post_events(
        client,
        remote,
        fed_settings,
        authority_match.match.id,
        [{"event_uuid": str(uuid.uuid4()), "event": "accepted", "contact": ACCEPT_CONTACT}],
    )
    item = resp.json()["results"][0]
    assert item["status"] == "error"
    authority_match.match.refresh_from_db()
    assert authority_match.match.status == "proposed"


# ── signed authoritative state + mirror re-sync (§6.3) ──────────


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_match_sync_returns_signed_authoritative_state(client, fed_settings, remote, authority_match):
    from apps.federation import crypto as fed_crypto

    path = f"/federation/v1/matches/{authority_match.match.id}"
    sig = remote.sign("GET", _url(path), b"", fed_settings.instance_id)
    resp = client.get(path, HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    token = resp.json()["match"]
    payload = fed_crypto.verify_match_state(token, fed_crypto.public_jwk())
    assert payload["match_uuid"] == str(authority_match.match.id)
    assert payload["status"] == "proposed"


def test_resync_mirror_converges_to_authority(mirror_fmatch, remote, monkeypatch):
    from apps.federation import mirror as mirror_mod

    state = {
        "match_uuid": str(mirror_fmatch.fmatch.remote_match_uuid),
        "status": "cancelled",
        "iat": int(time.time()),
    }
    token = jws.serialize_compact({"alg": "Ed25519"}, json.dumps(state).encode(), remote.key, algorithms=["Ed25519"])
    monkeypatch.setattr(
        "apps.federation.mirror.client_mod.get_match", lambda base_url, match_uuid, headers: {"match": token}
    )
    assert mirror_mod.resync_mirror(mirror_fmatch.fmatch) == "cancelled"
    mirror_fmatch.fmatch.refresh_from_db()
    assert mirror_fmatch.fmatch.mirror_status == "cancelled"


def test_resync_rejects_tampered_state(mirror_fmatch, remote, monkeypatch):
    from joserfc.jwk import OKPKey

    from apps.federation import mirror as mirror_mod

    wrong_key = OKPKey.generate_key("Ed25519")
    state = {
        "match_uuid": str(mirror_fmatch.fmatch.remote_match_uuid),
        "status": "cancelled",
        "iat": int(time.time()),
    }
    token = jws.serialize_compact({"alg": "Ed25519"}, json.dumps(state).encode(), wrong_key, algorithms=["Ed25519"])
    monkeypatch.setattr(
        "apps.federation.mirror.client_mod.get_match", lambda base_url, match_uuid, headers: {"match": token}
    )
    assert mirror_mod.resync_mirror(mirror_fmatch.fmatch) is None
    mirror_fmatch.fmatch.refresh_from_db()
    assert mirror_fmatch.fmatch.mirror_status == "proposed"  # untouched

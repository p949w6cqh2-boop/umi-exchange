"""
Stage C2 — mirror side (§6.2): sending proposals against a peer's shadow
listing and converging the mirror on the authority's state.
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def mirror_world(fed_settings, active_link, world):
    """The mirror instance's view: a peer's need shadow + a local active Offer
    owned by world.plain (the would-be responder)."""
    from apps.communities.models import Category
    from apps.federation.models import ShadowListing
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
    shadow = ShadowListing.objects.create(
        link=active_link,
        kind="need",
        remote_uuid=uuid.uuid4(),
        category="Food",
        urgency="high",
        locality="Peerville",
        freshness="2026-W27",
        expires_at=timezone.now() + timedelta(days=7),
    )
    return SimpleNamespace(link=active_link, offer=offer, shadow=shadow, responder=world.plain)


def _created_response(payload):
    item = payload["proposals"][0]
    return {"results": [{"proposal_uuid": item["proposal_uuid"], "status": "created", "match_uuid": str(uuid.uuid4())}]}


def test_send_proposal_creates_mirror_fmatch(mirror_world, monkeypatch):
    from apps.federation import crypto, mirror

    calls = {}

    def fake_post(base_url, payload, headers):
        calls["payload"] = payload
        calls["headers"] = headers
        return _created_response(payload)

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", fake_post)
    fmatch = mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)

    assert fmatch.role == "mirror" and fmatch.mirror_status == "proposed"
    assert fmatch.offer_id == mirror_world.offer.id
    assert fmatch.remote_need_uuid == mirror_world.shadow.remote_uuid
    assert fmatch.remote_match_uuid is not None

    item = calls["payload"]["proposals"][0]
    assert item["need_remote_uuid"] == str(mirror_world.shadow.remote_uuid)
    assert item["offer"]["title"] == "I can shop"
    # §7: blind token derived from the offerer's email under the link pepper
    assert item["blind_token"] == crypto.blind_token(b"1" * 32, "bob@example.test")
    assert "X-UMI-Signature" in calls["headers"]
    # PII never crosses at proposal time
    assert "bob@example.test" not in str(calls["payload"])
    assert AuditLog.objects.filter(action="fed.proposal_sent").exists()


def test_send_proposal_is_idempotent_per_shadow_offer(mirror_world, monkeypatch):
    from apps.federation import mirror

    posts = []

    def fake_post(base_url, payload, headers):
        posts.append(payload)
        return _created_response(payload)

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", fake_post)
    first = mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)
    second = mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)
    assert first.pk == second.pk
    assert len(posts) == 1


def test_send_proposal_rejected_raises(mirror_world, monkeypatch):
    from apps.federation import mirror
    from apps.federation.models import FederatedMatch

    def fake_post(base_url, payload, headers):
        item = payload["proposals"][0]
        return {"results": [{"proposal_uuid": item["proposal_uuid"], "status": "rejected", "reason": "gone"}]}

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", fake_post)
    with pytest.raises(mirror.ProposalError, match="gone"):
        mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)
    assert not FederatedMatch.objects.exists()


def test_send_proposal_requires_active_link(mirror_world, monkeypatch):
    from apps.federation import mirror

    called = []
    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", lambda *a, **k: called.append(1))
    mirror_world.link.transition_to("suspended")
    mirror_world.shadow.link.refresh_from_db()
    with pytest.raises(mirror.ProposalError):
        mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)
    assert not called


def test_send_proposal_requires_own_active_offer(mirror_world, world, monkeypatch):
    from apps.federation import mirror

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", lambda *a, **k: {"results": []})
    # not the offerer
    with pytest.raises(mirror.ProposalError):
        mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=world.admin_u)
    # offer no longer active
    mirror_world.offer.status = "matched"
    mirror_world.offer.save(update_fields=["status"])
    with pytest.raises(mirror.ProposalError):
        mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)


def test_send_proposal_without_email_omits_token(mirror_world, monkeypatch):
    from apps.federation import mirror

    mirror_world.responder.user.email = ""
    mirror_world.responder.user.save(update_fields=["email"])
    calls = {}

    def fake_post(base_url, payload, headers):
        calls["payload"] = payload
        return _created_response(payload)

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", fake_post)
    mirror.send_proposal(mirror_world.shadow, mirror_world.offer, actor_user=mirror_world.responder.user)
    assert "blind_token" not in calls["payload"]["proposals"][0]

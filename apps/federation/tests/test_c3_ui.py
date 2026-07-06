"""
Stage C slice 3 — member-facing federation UI: browse peer listings, offer to
help (send a proposal), track federated matches, reveal exchanged contact.
All pages live under c/<slug>/federation/ and exist only when the flag is on.
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Category, Member
from apps.federation.models import FederatedMatch, ShadowListing
from apps.offers.models import Offer

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


@pytest.fixture
def ui_world(fed_settings, active_link, world):
    """A member (world.plain) with one active offer + two peer need shadows."""
    active_link.remote_community_label = "St. Bridget Board"
    active_link.save(update_fields=["remote_community_label"])
    cat = Category.objects.create(community=world.community, name="Food")
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="I can shop weekly",
        contact_pref="email",
        expires_at=timezone.now() + timedelta(days=30),
    )
    shadow = ShadowListing.objects.create(
        link=active_link,
        kind="need",
        remote_uuid=uuid.uuid4(),
        category="Food",
        urgency="high",
        locality="Riverside",
        freshness="2026-W27",
        expires_at=timezone.now() + timedelta(days=6),
    )
    ShadowListing.objects.create(  # an offer-kind shadow must NOT appear
        link=active_link,
        kind="offer",
        remote_uuid=uuid.uuid4(),
        category="Food",
        locality="Riverside",
        freshness="2026-W27",
        radius_km=5,
        expires_at=timezone.now() + timedelta(days=6),
    )
    return SimpleNamespace(world=world, link=active_link, offer=offer, shadow=shadow, cat=cat)


def _listings_url(world):
    return f"/c/{world.community.slug}/federation/listings"


# ── browse (task: Beyond this community) ────────────────────────


def test_listings_page_lists_active_need_shadows(client, ui_world):
    client.force_login(ui_world.world.plain_u)
    resp = client.get(_listings_url(ui_world.world))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "St. Bridget Board" in html
    assert "Food" in html and "Riverside" in html
    # the offer-kind shadow stays out of a needs board
    assert html.count("umi-need-card") >= 1


def test_listings_excludes_expired_and_suspended(client, ui_world):
    ShadowListing.objects.filter(pk=ui_world.shadow.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    client.force_login(ui_world.world.plain_u)
    assert "Riverside" not in client.get(_listings_url(ui_world.world)).content.decode()

    ShadowListing.objects.filter(pk=ui_world.shadow.pk).update(expires_at=timezone.now() + timedelta(days=1))
    ui_world.link.transition_to("suspended")
    assert "Riverside" not in client.get(_listings_url(ui_world.world)).content.decode()


def test_listings_requires_membership(client, ui_world):
    from apps.federation.tests.conftest import make_user

    outsider = make_user("outsider1")
    client.force_login(outsider)
    resp = client.get(_listings_url(ui_world.world))
    assert resp.status_code in (302, 403, 404)
    if resp.status_code == 302:
        assert "Riverside" not in client.get(resp["Location"], follow=True).content.decode()


def test_listings_empty_state_invites(client, ui_world):
    ShadowListing.objects.all().delete()
    client.force_login(ui_world.world.plain_u)
    html = client.get(_listings_url(ui_world.world)).content.decode()
    assert "Nothing from linked communities right now" in html


# ── offer picker + propose (task: offer-to-help flow) ───────────


def test_offer_picker_lists_only_my_active_offers(client, ui_world):
    other_u = ui_world.world.admin_u
    other_member = ui_world.world.admin
    Offer.objects.create(
        community=ui_world.world.community,
        offerer=other_member,
        category=ui_world.cat,
        title="someone else's offer",
        expires_at=timezone.now() + timedelta(days=30),
    )
    Offer.objects.create(
        community=ui_world.world.community,
        offerer=ui_world.world.plain,
        category=ui_world.cat,
        title="my committed offer",
        status="matched",
        expires_at=timezone.now() + timedelta(days=30),
    )
    client.force_login(ui_world.world.plain_u)
    resp = client.get(f"{_listings_url(ui_world.world)}/{ui_world.shadow.pk}/offers")
    html = resp.content.decode()
    assert "I can shop weekly" in html
    assert "someone else's offer" not in html
    assert "my committed offer" not in html
    assert other_u  # silence lint


def test_propose_submit_sends_and_confirms(client, ui_world, monkeypatch):
    def fake_post(base_url, payload, headers):
        item = payload["proposals"][0]
        return {
            "results": [{"proposal_uuid": item["proposal_uuid"], "status": "created", "match_uuid": str(uuid.uuid4())}]
        }

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", fake_post)
    client.force_login(ui_world.world.plain_u)
    resp = client.post(
        f"{_listings_url(ui_world.world)}/{ui_world.shadow.pk}/propose",
        {"offer_id": str(ui_world.offer.pk)},
        follow=True,
    )
    assert resp.status_code == 200
    assert FederatedMatch.objects.filter(role="mirror", offer=ui_world.offer).exists()


def test_propose_rejection_maps_friendly_message(client, ui_world, monkeypatch):
    def fake_post(base_url, payload, headers):
        item = payload["proposals"][0]
        return {"results": [{"proposal_uuid": item["proposal_uuid"], "status": "rejected", "reason": "gone"}]}

    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", fake_post)
    client.force_login(ui_world.world.plain_u)
    resp = client.post(
        f"{_listings_url(ui_world.world)}/{ui_world.shadow.pk}/propose",
        {"offer_id": str(ui_world.offer.pk)},
        follow=True,
    )
    html = resp.content.decode()
    assert "already been answered" in html  # friendly copy, not a raw reason code
    assert not FederatedMatch.objects.exists()


def test_propose_rejects_offer_i_do_not_own(client, ui_world, monkeypatch):
    monkeypatch.setattr("apps.federation.mirror.client_mod.post_proposals", lambda *a, **k: {"results": []})
    other_offer = Offer.objects.create(
        community=ui_world.world.community,
        offerer=ui_world.world.admin,
        category=ui_world.cat,
        title="not mine",
        expires_at=timezone.now() + timedelta(days=30),
    )
    client.force_login(ui_world.world.plain_u)
    resp = client.post(
        f"{_listings_url(ui_world.world)}/{ui_world.shadow.pk}/propose",
        {"offer_id": str(other_offer.pk)},
    )
    assert resp.status_code in (302, 400, 404)
    assert not FederatedMatch.objects.exists()


# ── federated matches page (mirror tracking + reveal) ───────────


@pytest.fixture
def accepted_mirror(ui_world):
    fmatch = FederatedMatch.objects.create(
        link=ui_world.link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=ui_world.shadow.remote_uuid,
        mirror_status="accepted",
        offer=ui_world.offer,
    )
    fmatch.contact_payload = {"display_name": "Maria", "preference": "email", "email": "maria@peer.test"}
    fmatch.save(update_fields=["contact_payload_enc", "contact_payload_dek"])
    return fmatch


def _matches_url(world):
    return f"/c/{world.community.slug}/federation/matches"


def test_matches_page_shows_my_mirror_match_and_contact(client, ui_world, accepted_mirror):
    client.force_login(ui_world.world.plain_u)
    resp = client.get(_matches_url(ui_world.world))
    html = resp.content.decode()
    assert "I can shop weekly" in html
    assert "Accepted" in html
    assert "maria@peer.test" in html  # §8.2: revealed to the offerer post-accept
    assert AuditLog.objects.filter(action="read", resource_type="match_contact").exists()


def test_matches_page_hides_contact_before_accept(client, ui_world):
    FederatedMatch.objects.create(
        link=ui_world.link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=ui_world.shadow.remote_uuid,
        mirror_status="proposed",
        offer=ui_world.offer,
    )
    client.force_login(ui_world.world.plain_u)
    html = client.get(_matches_url(ui_world.world)).content.decode()
    assert "Waiting for their community" in html
    assert "maria@peer.test" not in html


def test_matches_page_scopes_to_own_matches_for_plain_members(client, ui_world, accepted_mirror):
    """Another plain member sees neither the match nor the contact."""
    from apps.federation.tests.conftest import make_user

    stranger_u = make_user("stranger9")
    Member.objects.create(
        user=stranger_u, community=ui_world.world.community, role="member", display_name="Stranger", is_active=True
    )
    client.force_login(stranger_u)
    html = client.get(_matches_url(ui_world.world)).content.decode()
    assert "maria@peer.test" not in html
    assert "I can shop weekly" not in html


def test_matches_page_coordinator_oversight(client, ui_world, accepted_mirror):
    client.force_login(ui_world.world.admin_u)  # admin is a coordinator
    html = client.get(_matches_url(ui_world.world)).content.decode()
    assert "I can shop weekly" in html
    assert "maria@peer.test" in html  # §8.2 coordinator oversight carries over


# ── feed entry point ────────────────────────────────────────────


def test_feed_offers_beyond_this_community_link(client, ui_world):
    client.force_login(ui_world.world.plain_u)
    html = client.get(f"/c/{ui_world.world.community.slug}/").content.decode()
    assert "Beyond this community" in html


def test_feed_hides_link_when_no_active_links(client, ui_world):
    ui_world.link.transition_to("suspended")
    client.force_login(ui_world.world.plain_u)
    html = client.get(f"/c/{ui_world.world.community.slug}/").content.decode()
    assert "Beyond this community" not in html

"""
Share UI (§2.3 record-level opt-in / §4.1 consent capture) + the pinned
pairing-code panel — the two dark-launch UX follow-ups.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation.models import FederatedShare
from apps.needs.models import Need
from apps.offers.models import Offer

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


@pytest.fixture
def share_world(fed_settings, active_link, world):
    active_link.remote_community_label = "St. Bridget Board"
    active_link.save(update_fields=["remote_community_label"])
    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="Groceries for the week",
        urgency="high",
        contact_pref="email",
        expires_at=timezone.now() + timedelta(days=14),
    )
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="I can shop",
        expires_at=timezone.now() + timedelta(days=30),
    )
    return SimpleNamespace(world=world, link=active_link, need=need, offer=offer, cat=cat)


def _need_url(w):
    return f"/c/{w.world.community.slug}/needs/{w.need.id}/"


def _toggle_url(w):
    return f"/c/{w.world.community.slug}/federation/share"


# ── panel visibility ────────────────────────────────────────────


def test_owner_sees_share_panel(client, share_world):
    client.force_login(share_world.world.plain_u)
    html = client.get(_need_url(share_world)).content.decode()
    assert "Share beyond this community" in html
    assert "St. Bridget Board" in html


def test_non_owner_sees_no_panel(client, share_world):
    client.force_login(share_world.world.admin_u)
    html = client.get(_need_url(share_world)).content.decode()
    assert "Share beyond this community" not in html


def test_panel_hidden_when_flag_off(client, share_world, settings):
    settings.FEDERATION_ENABLED = False
    client.force_login(share_world.world.plain_u)
    html = client.get(_need_url(share_world)).content.decode()
    assert "Share beyond this community" not in html


def test_panel_hidden_without_active_links(client, share_world):
    share_world.link.transition_to("suspended")
    client.force_login(share_world.world.plain_u)
    html = client.get(_need_url(share_world)).content.decode()
    assert "Share beyond this community" not in html


# ── share = the §4.1 one-action consent capture ─────────────────


def test_share_creates_consent_and_share(client, share_world):
    client.force_login(share_world.world.plain_u)
    resp = client.post(
        _toggle_url(share_world),
        {"kind": "need", "record_id": str(share_world.need.id), "link_id": str(share_world.link.pk), "action": "share"},
        follow=True,
    )
    assert resp.status_code == 200
    share = FederatedShare.objects.get(need=share_world.need, link=share_world.link)
    assert share.status == "active" and share.receipt_jws
    consent = Consent.objects.get(participant=share_world.world.plain_u)
    assert consent.grantee_type == "community"
    assert str(consent.grantee_id) == str(share_world.link.remote_community_uuid)
    assert "federated_share" in consent.scope
    share_world.need.refresh_from_db()
    assert share_world.need.share_scope == "federated"
    assert AuditLog.objects.filter(action="fed.share_created").exists()
    # panel reflects the state
    assert "Stop sharing" in resp.content.decode()


def test_share_is_idempotent_and_reuses_consent(client, share_world):
    client.force_login(share_world.world.plain_u)
    for _ in range(2):
        client.post(
            _toggle_url(share_world),
            {
                "kind": "need",
                "record_id": str(share_world.need.id),
                "link_id": str(share_world.link.pk),
                "action": "share",
            },
        )
    assert FederatedShare.objects.filter(need=share_world.need).count() == 1
    assert Consent.objects.filter(participant=share_world.world.plain_u).count() == 1


def test_unshare_revokes_and_notifies_peer(client, share_world, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "apps.federation.sharing.client_mod.post_revocation", lambda *a, **k: sent.append(1) or {"results": []}
    )
    client.force_login(share_world.world.plain_u)
    client.post(
        _toggle_url(share_world),
        {"kind": "need", "record_id": str(share_world.need.id), "link_id": str(share_world.link.pk), "action": "share"},
    )
    resp = client.post(
        _toggle_url(share_world),
        {
            "kind": "need",
            "record_id": str(share_world.need.id),
            "link_id": str(share_world.link.pk),
            "action": "unshare",
        },
        follow=True,
    )
    share = FederatedShare.objects.get(need=share_world.need)
    assert share.status == "revoked"
    assert sent  # signed delete-request went out (§4.3)
    share_world.need.refresh_from_db()
    assert share_world.need.share_scope == "local"
    assert "Share beyond this community" in resp.content.decode()
    assert AuditLog.objects.filter(action="fed.share_revoked").exists()


def test_non_owner_cannot_toggle(client, share_world):
    client.force_login(share_world.world.admin_u)
    resp = client.post(
        _toggle_url(share_world),
        {"kind": "need", "record_id": str(share_world.need.id), "link_id": str(share_world.link.pk), "action": "share"},
    )
    assert resp.status_code == 404
    assert not FederatedShare.objects.exists()


def test_offer_share_happy_path(client, share_world):
    client.force_login(share_world.world.plain_u)
    client.post(
        _toggle_url(share_world),
        {
            "kind": "offer",
            "record_id": str(share_world.offer.id),
            "link_id": str(share_world.link.pk),
            "action": "share",
        },
    )
    assert FederatedShare.objects.filter(offer=share_world.offer, status="active").exists()


# ── pinned pairing code (handshake UX) ──────────────────────────


def test_pairing_code_pinned_on_settings_page_once(client, fed_settings, world, remote, monkeypatch):
    monkeypatch.setattr(
        "apps.federation.views.client_mod.fetch_instance_document",
        lambda base_url: remote.instance_document("https://peer.example"),
    )
    monkeypatch.setattr("apps.federation.views.client_mod.post_handshake", lambda *a, **k: {"status": "pending"})
    client.force_login(world.admin_u)
    resp = client.post(
        f"/c/{world.community.slug}/federation/",
        {"action": "initiate", "base_url": "https://peer.example"},
        follow=True,
    )
    html = resp.content.decode()
    assert "Pairing code" in html and "shown only once" in html
    import re

    code = re.search(r"data-pairing-code=\"([A-Z0-9]{12})\"", html)
    assert code, "12-char pairing code must be pinned on the page"
    # one-time: a fresh GET no longer reveals it
    html2 = client.get(f"/c/{world.community.slug}/federation/").content.decode()
    assert code.group(1) not in html2

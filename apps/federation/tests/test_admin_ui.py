"""Community-admin federation page: gate + link lifecycle actions."""

import uuid

import pytest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.federation import views as fed_views
from apps.federation.models import FederationLink, FederationPeer

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


def page(world):
    return reverse("federation_admin:settings", kwargs={"slug": world.community.slug})


def _live_share(world, link):
    """A live FederatedShare on `link` (minimal — no crypto), for cascade tests."""
    from django.utils import timezone

    from apps.communities.models import Category
    from apps.consent.models import Consent
    from apps.federation.models import FederatedShare
    from apps.needs.models import Need

    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="x",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    consent = Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer",
        grantee_type="community",
        grantee_id=uuid.uuid4(),
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    return FederatedShare.objects.create(link=link, need=need, consent=consent, status="active")


@pytest.fixture
def active_link(world, peer):
    link = FederationLink.objects.create(peer=peer, community=world.community, requested_by_us=True)
    link.transition_to("active")
    return link


class TestGate:
    def test_admin_sees_page(self, client, fed_settings, world):
        client.force_login(world.admin_u)
        resp = client.get(page(world))
        assert resp.status_code == 200
        assert fed_settings.instance_id in resp.content.decode()

    def test_plain_member_redirected(self, client, fed_settings, world):
        client.force_login(world.plain_u)
        assert client.get(page(world)).status_code == 302


class TestActions:
    def test_suspend_and_resume(self, client, fed_settings, world, active_link):
        client.force_login(world.admin_u)
        resp = client.post(page(world), {"action": "suspend", "link_id": str(active_link.pk)})
        assert resp.status_code == 302
        active_link.refresh_from_db()
        assert active_link.status == "suspended"
        assert AuditLog.objects.filter(action="fed.link_suspended", user=world.admin_u).exists()
        client.post(page(world), {"action": "resume", "link_id": str(active_link.pk)})
        active_link.refresh_from_db()
        assert active_link.status == "active"

    def test_revoke(self, client, fed_settings, world, active_link):
        client.force_login(world.admin_u)
        client.post(page(world), {"action": "revoke", "link_id": str(active_link.pk)})
        active_link.refresh_from_db()
        assert active_link.status == "revoked"
        assert AuditLog.objects.filter(action="fed.link_revoked", user=world.admin_u).exists()

    def test_revoke_cascades_live_shares_to_revoked(self, client, fed_settings, world, active_link):
        """C2 defense-in-depth: revoking a link also revokes its live shares, so
        they can't be served/matched even if a call site forgets link__status."""
        share = _live_share(world, active_link)
        client.force_login(world.admin_u)

        client.post(page(world), {"action": "revoke", "link_id": str(active_link.pk)})

        share.refresh_from_db()
        assert share.status == "revoked"
        assert share.revoked_at is not None

    def test_suspend_leaves_shares_active(self, client, fed_settings, world, active_link):
        """Suspend is a temporary pause — the link__status gate stops serving,
        and resume restores the shares, so their status is deliberately left."""
        share = _live_share(world, active_link)
        client.force_login(world.admin_u)

        client.post(page(world), {"action": "suspend", "link_id": str(active_link.pk)})

        share.refresh_from_db()
        assert share.status == "active"

    def test_initiate_creates_pending_link_and_shows_code(self, client, fed_settings, world, remote, monkeypatch):
        monkeypatch.setattr(
            fed_views.client_mod, "fetch_instance_document", lambda base_url: remote.instance_document(base_url)
        )
        posted = {}
        monkeypatch.setattr(
            fed_views.client_mod,
            "post_handshake",
            lambda base_url, payload: posted.update(payload) or {"status": "pending"},
        )
        client.force_login(world.admin_u)
        resp = client.post(page(world), {"action": "initiate", "base_url": "https://peer.example"}, follow=True)
        assert resp.status_code == 200
        link = FederationLink.objects.get(community=world.community, requested_by_us=True)
        assert link.status == "pending"
        assert link.peer.instance_id == remote.instance_id
        assert link.pairing_code_hash
        assert "pairing" in posted and posted["pairing"]["hash"]
        # the one-time code is surfaced to the admin exactly once
        assert "pairing code" in resp.content.decode().lower()
        assert AuditLog.objects.filter(action="fed.link_requested", user=world.admin_u).exists()

    def test_approve_inbound_activates_and_confirms(self, client, fed_settings, world, remote, monkeypatch):
        from apps.federation import crypto

        code = crypto.mint_pairing_code()
        salt = uuid.uuid4().hex
        peer = FederationPeer.objects.create(
            base_url="https://peer.example",
            instance_id=remote.instance_id,
            jwk=remote.jwk,
            label="Peer Parish",
            status="pending",
            pairing_salt=salt,
            pairing_hash=crypto.remote_code_hash(code, salt),
            requested_communities=[{"uuid": str(uuid.uuid4()), "label": "Their Board"}],
        )
        confirmed = {}
        monkeypatch.setattr(
            fed_views.client_mod,
            "post_confirm",
            lambda base_url, payload, headers: (
                confirmed.update(payload)
                or {"status": "active", "community": {"uuid": str(uuid.uuid4()), "label": "Their Board"}}
            ),
        )
        client.force_login(world.admin_u)
        resp = client.post(page(world), {"action": "approve", "peer_id": str(peer.pk), "code": code})
        assert resp.status_code == 302
        link = FederationLink.objects.get(peer=peer, community=world.community)
        assert link.status == "active"
        peer.refresh_from_db()
        assert peer.status == "active"
        assert confirmed["code"] == code
        assert AuditLog.objects.filter(action="fed.link_approved", user=world.admin_u).exists()

    def test_approve_wrong_code_does_not_activate(self, client, fed_settings, world, remote):
        from apps.federation import crypto

        salt = uuid.uuid4().hex
        peer = FederationPeer.objects.create(
            base_url="https://peer.example",
            instance_id=remote.instance_id,
            jwk=remote.jwk,
            status="pending",
            pairing_salt=salt,
            pairing_hash=crypto.remote_code_hash("REALCODE0000", salt),
            requested_communities=[{"uuid": str(uuid.uuid4()), "label": "Their Board"}],
        )
        client.force_login(world.admin_u)
        client.post(page(world), {"action": "approve", "peer_id": str(peer.pk), "code": "WRONGCODE000"})
        assert not FederationLink.objects.filter(peer=peer).exists()

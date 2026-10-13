"""2026-10 bug hunt, batch 5 (federation; dormant in production, fixed before anyone turns it on).

#17  Removing (or now losing) a member cancelled their federated matches without telling the peer
     or arming the contact-retention shred; a helper's mirror match was never withdrawn either.
#18  Re-linking after a revoke was impossible: the peer's confirm hit the old revoked row's unique
     key and answered 500.
#19  An active peer's request to link a second community was listed, but approving it was a 404.
#20  An accept whose contact was shredded while its link was suspended went out with no contact on
     resume: the peer sent its helper's contact back and the exchange was one-sided.
L59  "Resume" activated a pending link the peer never confirmed.
L60  A malformed id in a federation admin or member POST was a 500.
L63  Revoking a link left its records marked shared ("federated") with nothing shared.
"""

import json
import uuid

import pytest
from django.conf import settings as dj_settings
from django.urls import reverse
from django.utils import timezone

from apps.federation import crypto, mirror, outbox
from apps.federation import views as fed_views
from apps.federation.models import FederatedMatch, FederationEvent, FederationLink
from apps.moderation.services import leave_community, remove_member

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


def _accept(authority_match):
    authority_match.match.transition_to("accepted")
    outbox.queue_match_event(authority_match.match, "accepted")
    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Helper abroad", "email": "helper@peer.example"}
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek"])
    return FederationEvent.objects.get(direction="out", kind="accepted")


# ── #17: removal and leaving tell the peer ─────────────────────


@pytest.mark.parametrize("how", ["removed", "left"])
def test_losing_the_requester_tells_the_peer_and_arms_the_contact_shred(authority_match, world, how):
    _accept(authority_match)

    if how == "removed":
        remove_member(world.plain, by=world.admin)
    else:
        leave_community(world.plain)

    assert FederationEvent.objects.filter(direction="out", kind="cancelled").exists()
    authority_match.fmatch.refresh_from_db()
    assert authority_match.fmatch.contact_expires_at is not None  # the §4.4 shred will now find it


def _mirror_for(world, link, offer, status):
    return FederatedMatch.objects.create(
        link=link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=uuid.uuid4(),
        mirror_status=status,
        offer=offer,
    )


def _offer(world, status="active"):
    from apps.communities.models import Category
    from apps.offers.models import Offer

    cat = Category.objects.create(community=world.community, name="Rides")
    return Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="Rides to appointments",
        status=status,
        expires_at=timezone.now() + timezone.timedelta(days=30),
    )


@pytest.mark.parametrize("status", ["proposed", "accepted"])
def test_a_helper_who_leaves_asks_the_authority_to_cancel(fed_settings, world, active_link, status):
    offer = _offer(world, status="matched" if status == "accepted" else "active")
    fm = _mirror_for(world, active_link, offer, status)

    leave_community(world.plain)

    ev = FederationEvent.objects.get(direction="out", kind="cancel_requested")
    assert ev.payload["match_uuid"] == str(fm.remote_match_uuid)


def test_an_accept_arriving_after_the_helper_left_shares_nothing(fed_settings, world, active_link):
    offer = _offer(world)
    fm = _mirror_for(world, active_link, offer, "proposed")
    leave_community(world.plain)

    result = mirror.apply_match_event(
        fm, event_uuid=uuid.uuid4(), kind="accepted", contact={"display_name": "Asker", "email": "a@peer.example"}
    )

    assert "contact" not in result
    fm.refresh_from_db()
    assert fm.mirror_status != "accepted" and fm.contact_payload is None


# ── #18: re-linking after a revoke ─────────────────────────────

CONFIRM_PATH = "/federation/v1/handshake/confirm"


def _confirm(client, remote, fed_settings, code, remote_uuid):
    body = json.dumps({"code": code, "community": {"uuid": str(remote_uuid), "label": "Their Board"}}).encode()
    sig = remote.sign("POST", dj_settings.SITE_URL.rstrip("/") + CONFIRM_PATH, body, fed_settings.instance_id)
    return client.post(CONFIRM_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)


def _pending_outbound(world, peer, code):
    return FederationLink.objects.create(
        peer=peer,
        community=world.community,
        status="pending",
        requested_by_us=True,
        pairing_code_hash=crypto.local_code_hash(code),
        pairing_expires_at=timezone.now() + timezone.timedelta(hours=1),
    )


def test_relinking_after_a_revoke_activates_the_new_link(client, fed_settings, world, peer, remote):
    remote_uuid = uuid.uuid4()
    FederationLink.objects.create(
        peer=peer, community=world.community, remote_community_uuid=remote_uuid, status="revoked"
    )
    code = crypto.mint_pairing_code()
    fresh = _pending_outbound(world, peer, code)

    resp = _confirm(client, remote, fed_settings, code, remote_uuid)

    assert resp.status_code == 200
    fresh.refresh_from_db()
    assert fresh.status == "active"


def test_a_confirm_that_would_duplicate_a_live_link_is_a_409_not_a_500(client, fed_settings, world, peer, remote):
    remote_uuid = uuid.uuid4()
    FederationLink.objects.create(
        peer=peer, community=world.community, remote_community_uuid=remote_uuid, status="active"
    )
    code = crypto.mint_pairing_code()
    fresh = _pending_outbound(world, peer, code)

    resp = _confirm(client, remote, fed_settings, code, remote_uuid)

    assert resp.status_code == 409
    fresh.refresh_from_db()
    assert fresh.status == "pending"


# ── #19: a second community from an active peer ───────────────


def test_approving_a_second_community_from_an_active_peer_creates_the_link(
    client, fed_settings, world, active_link, remote, monkeypatch
):
    from apps.communities.models import Community, Member

    second = Community.objects.create(name="St. Anne", slug="st-anne", created_by=world.admin_u)
    Member.objects.create(user=world.admin_u, community=second, role="admin", display_name="Father Tom")
    peer = active_link.peer
    code = crypto.mint_pairing_code()
    salt = uuid.uuid4().hex
    peer.pairing_salt = salt
    peer.pairing_hash = crypto.remote_code_hash(code, salt)
    peer.pairing_expires_at = timezone.now() + timezone.timedelta(hours=1)
    peer.target_community_slug = second.slug
    peer.requested_communities = [{"uuid": str(uuid.uuid4()), "label": "Their Second Board"}]
    peer.save()
    monkeypatch.setattr(fed_views.client_mod, "post_confirm", lambda *a, **k: {"status": "active"})
    client.force_login(world.admin_u)

    resp = client.post(
        reverse("federation_admin:settings", kwargs={"slug": second.slug}),
        {"action": "approve", "peer_id": str(peer.pk), "code": code},
    )

    assert resp.status_code == 302
    assert FederationLink.objects.get(peer=peer, community=second).status == "active"
    peer.refresh_from_db()
    assert peer.status == "active" and not peer.pairing_hash  # consumed


# ── #20: an accept shredded while its link was suspended ───────


def _capture_posts(monkeypatch):
    sent = []

    def fake_post(base_url, match_uuid, payload, headers):
        item = payload["events"][0]
        sent.append(item)
        return {"results": [{"event_uuid": item["event_uuid"], "status": "applied"}]}

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", fake_post)
    return sent


def _suspend_and_resume(link):
    link.transition_to("suspended")
    outbox.shred_link_event_payloads(link)
    link.refresh_from_db()
    link.transition_to("active")


def test_an_accept_shredded_while_suspended_still_carries_the_contact(authority_match, monkeypatch):
    ev = _accept(authority_match)
    _suspend_and_resume(authority_match.link)
    sent = _capture_posts(monkeypatch)

    outbox.deliver_due_events()

    assert sent and sent[0]["event"] == "accepted"
    assert sent[0]["contact"]["email"] == "maria@example.test"
    ev.refresh_from_db()
    assert ev.state == "acked" and ev.payload_enc is None  # rebuilt for the send, never stored again


def test_a_stale_accept_is_dropped_when_the_match_moved_on(authority_match, monkeypatch):
    ev = _accept(authority_match)
    _suspend_and_resume(authority_match.link)
    match = authority_match.match
    match.refresh_from_db()
    match.transition_to("cancelled")
    outbox.queue_match_event(match, "cancelled")
    sent = _capture_posts(monkeypatch)

    outbox.deliver_due_events()

    assert [item["event"] for item in sent] == ["cancelled"]
    ev.refresh_from_db()
    assert ev.state == "failed"


# ── L59, L60, L63: link admin and member edges ─────────────────


def test_resume_does_not_activate_a_pending_link(client, fed_settings, world, peer):
    code = crypto.mint_pairing_code()
    link = _pending_outbound(world, peer, code)
    client.force_login(world.admin_u)

    client.post(
        reverse("federation_admin:settings", kwargs={"slug": world.community.slug}),
        {"action": "resume", "link_id": str(link.pk)},
    )

    link.refresh_from_db()
    assert link.status == "pending"


@pytest.mark.parametrize("action,field", [("approve", "peer_id"), ("suspend", "link_id"), ("revoke", "link_id")])
def test_a_malformed_id_on_the_link_page_is_a_404(client, fed_settings, world, action, field):
    client.force_login(world.admin_u)
    resp = client.post(
        reverse("federation_admin:settings", kwargs={"slug": world.community.slug}),
        {"action": action, field: "not-a-uuid", "code": "X"},
    )
    assert resp.status_code == 404


def test_a_malformed_record_id_on_share_is_a_404(client, fed_settings, world, active_link):
    client.force_login(world.plain_u)
    resp = client.post(
        reverse("federation_admin:share-toggle", kwargs={"slug": world.community.slug}),
        {"kind": "need", "record_id": "not-a-uuid", "link_id": str(active_link.pk), "action": "share"},
    )
    assert resp.status_code == 404


def test_revoking_a_link_unmarks_records_with_nothing_left_shared(client, authority_match, world):
    need = authority_match.need
    need.refresh_from_db()
    assert need.share_scope == "federated"
    client.force_login(world.admin_u)

    client.post(
        reverse("federation_admin:settings", kwargs={"slug": world.community.slug}),
        {"action": "revoke", "link_id": str(authority_match.link.pk)},
    )

    need.refresh_from_db()
    assert need.share_scope == "local"

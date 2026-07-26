"""
Federation containment (bug-hunt batch 12, #12 #13 #20 + the picker/send_proposal
miss the batch-7 reviews turned up).

Federation is default-OFF and not in production, so none of these are firing —
they are fix-before-enabling. Every one is about the same thing: something that
must not cross a community boundary, crossing it.

#12 _apply_mirror_state set mirror_status='accepted' even in the refusal branch
    (local offer unavailable / self-match), where it deliberately withholds
    contact and queues a cancel. _duplicate_result re-derives disclosure from
    (mirror_status, offer.status) alone — so a replayed accepted event, the
    lost-ack retry §6.3 exists for, handed the peer the responder's name+email
    that pass 1 had just refused, on a match simultaneously being cancelled.

#13 DiscoveryView filtered shares on link/share status only, never the underlying
    record. A removed member's need (moderation_hidden=True, status still open)
    kept appearing in a peer's discovery feed indefinitely, and receive_proposal
    gated only on need.status — so a peer could propose against it and get a real
    authoritative Match a coordinator could accept, triggering the §8.2 contact
    exchange the hide was meant to prevent.

+1  The same hole on the way out: FederatedOfferPickerView listed the member's own
    offers with no moderation_hidden filter and send_proposal never checked it, so
    a coordinator-hidden offer could be pushed across a link with its title. Not
    one of the hunt's 35 — found while reviewing batch 7's local twin.

#20 Contact PII in the outbox outlived the link. queue_match_event puts the
    requester's contact on the accepted event's envelope-encrypted payload; both
    clears sit behind deliver_due_events' link__status='active' filter, so
    suspending or revoking a link froze that row 'pending' forever, decryptable
    under the instance KEK — defeating the crypto-shred guarantee. The sweep must
    therefore be flag-independent: disabling federation must not strand PII.
"""

import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import matching, mirror, outbox, sharing
from apps.federation.models import FederatedMatch, FederationEvent, ShadowListing
from apps.needs.models import Need
from apps.offers.models import Offer

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

DISCOVERY_URL_PATH = "/federation/v1/discovery"


def _site_url():
    from django.conf import settings

    return settings.SITE_URL.rstrip("/") + DISCOVERY_URL_PATH


def _category(world):
    return Category.objects.create(community=world.community, name="Food")


def _shared_need(world, link, **over):
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=_category(world),
        title="Ask that must stop crossing",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
        **over,
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer Board",
        grantee_type="community",
        grantee_id=link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    sharing.share_record(need, link, actor_user=world.admin_u)
    return need


def _listings(client, fed_settings, remote):
    sig = remote.sign("GET", _site_url(), b"", fed_settings.instance_id)
    resp = client.get(DISCOVERY_URL_PATH, HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    return resp.json()["listings"]


# ------------------------------------------------------------------------ #13
def test_discovery_stops_advertising_a_hidden_need(client, fed_settings, remote, active_link, world):
    need = _shared_need(world, active_link)
    assert len(_listings(client, fed_settings, remote)) == 1, "shared and live: advertised"

    Need.objects.filter(pk=need.pk).update(moderation_hidden=True)

    assert _listings(client, fed_settings, remote) == [], "a hidden ask must stop crossing immediately"


def test_discovery_stops_advertising_a_closed_need(client, fed_settings, remote, active_link, world):
    need = _shared_need(world, active_link)
    Need.objects.filter(pk=need.pk).update(status="matched")

    assert _listings(client, fed_settings, remote) == []


def test_discovery_still_advertises_a_live_need(client, fed_settings, remote, active_link, world):
    """The guard must not empty the feed."""
    _shared_need(world, active_link)

    assert len(_listings(client, fed_settings, remote)) == 1


def test_receive_proposal_refuses_a_hidden_need(fed_settings, active_link, world):
    """Even if a stale peer still holds the listing, no authoritative Match."""
    need = _shared_need(world, active_link)
    share = need.federated_shares.get()
    Need.objects.filter(pk=need.pk).update(moderation_hidden=True)

    result = matching.receive_proposal(
        active_link.peer,
        need_remote_uuid=str(share.remote_uuid),
        proposal_uuid=str(uuid.uuid4()),
        blind_token="peer-token-abc",
    )

    assert result["status"] == "rejected"
    assert result["reason"] == "gone"
    assert not FederatedMatch.objects.filter(link=active_link, role="authority").exists()


def test_receive_proposal_still_accepts_a_live_need(fed_settings, active_link, world):
    need = _shared_need(world, active_link)
    share = need.federated_shares.get()

    result = matching.receive_proposal(
        active_link.peer,
        need_remote_uuid=str(share.remote_uuid),
        proposal_uuid=str(uuid.uuid4()),
        blind_token="peer-token-abc",
    )

    assert result["status"] == "created"


# ------------------------------------------------------- +1 (outbound twin)
def _shadow(active_link):
    return ShadowListing.objects.create(
        link=active_link,
        remote_uuid=uuid.uuid4(),
        kind="need",
        category="Food",
        locality="Peer Town",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=3),
    )


def _own_offer(world, *, title="Hidden offer that must not cross", **over):
    return Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=_category(world),
        title=title,
        status="active",
        expires_at=timezone.now() + timezone.timedelta(days=30),
        **over,
    )


def test_send_proposal_refuses_a_hidden_offer(fed_settings, active_link, world):
    shadow = _shadow(active_link)
    offer = _own_offer(world, moderation_hidden=True)

    with pytest.raises(mirror.ProposalError):
        mirror.send_proposal(shadow, offer, actor_user=world.plain_u)

    assert not FederatedMatch.objects.filter(link=active_link, role="mirror").exists()


def test_offer_picker_hides_a_hidden_offer(client, fed_settings, active_link, world):
    shadow = _shadow(active_link)
    _own_offer(world, moderation_hidden=True)
    client.force_login(world.plain_u)

    resp = client.get(reverse("federation_admin:listing-offers", args=[world.community.slug, shadow.pk]))

    assert resp.status_code == 200
    assert "Hidden offer that must not cross" not in resp.content.decode()


# ------------------------------------------------------------------------ #12
def _mirror_fmatch(active_link, offer, *, offer_status):
    Offer.objects.filter(pk=offer.pk).update(status=offer_status)
    offer.refresh_from_db()
    return FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        offer=offer,
        mirror_status="proposed",
        proposal_uuid=uuid.uuid4(),
    )


def test_refused_accept_leaves_no_disclosable_state(fed_settings, active_link, world):
    """The offer was committed locally in the meantime: contact is withheld and a
    cancel queued. The stored state must not read as 'disclosure happened'."""
    offer = _own_offer(world, title="Offer held elsewhere")
    fmatch = _mirror_fmatch(active_link, offer, offer_status="matched")

    from django.db import transaction

    with transaction.atomic():
        result = mirror._apply_mirror_state(fmatch, "accepted", contact={"name": "Peer Person"})

    assert "contact" not in result, "pass 1 withholds"
    assert result["reason"] == "offer_unavailable"
    fmatch.refresh_from_db()
    assert fmatch.mirror_status != "accepted", "a refusal is not an acceptance"


def test_replayed_refused_accept_does_not_disclose_contact(fed_settings, active_link, world):
    """The lost-ack retry (§6.3) must answer the same refusal, not hand over the
    responder's name+email pass 1 just protected."""
    offer = _own_offer(world, title="Offer held elsewhere")
    fmatch = _mirror_fmatch(active_link, offer, offer_status="matched")

    from django.db import transaction

    with transaction.atomic():
        mirror._apply_mirror_state(fmatch, "accepted", contact={"name": "Peer Person"})
    fmatch.refresh_from_db()
    replay = mirror._duplicate_result(fmatch, "accepted")

    assert "contact" not in replay, "a replay must not disclose what the original refused"


def test_replayed_successful_accept_still_re_attaches_contact(fed_settings, active_link, world):
    """§6.3's actual purpose must survive: a genuine accept's lost ack still
    re-sends the responder dict on replay."""
    offer = _own_offer(world, title="Offer that is available")
    fmatch = _mirror_fmatch(active_link, offer, offer_status="active")

    from django.db import transaction

    with transaction.atomic():
        result = mirror._apply_mirror_state(fmatch, "accepted", contact={"name": "Peer Person"})
    fmatch.refresh_from_db()
    replay = mirror._duplicate_result(fmatch, "accepted")

    assert "contact" in result, "the successful path still discloses"
    assert fmatch.mirror_status == "accepted"
    assert "contact" in replay


# ------------------------------------------------------------------------ #20
def _pending_accepted_event(active_link, *, age_hours=0):
    ev = FederationEvent(
        link=active_link,
        direction="out",
        event_uuid=uuid.uuid4(),
        kind="accepted",
        payload={"match_uuid": str(uuid.uuid4()), "event": "accepted"},
        next_attempt_at=timezone.now(),
    )
    ev.secret_payload = {"contact": {"name": "Requester Name", "email": "requester@example.test"}}
    ev.save()
    if age_hours:
        FederationEvent.objects.filter(pk=ev.pk).update(created_at=timezone.now() - timezone.timedelta(hours=age_hours))
    return ev


def test_revoking_a_link_shreds_pending_contact_payloads(fed_settings, active_link, world):
    """Revoke freezes delivery forever — the PII must not freeze with it."""
    ev = _pending_accepted_event(active_link)
    assert ev.payload_enc is not None

    outbox.shred_link_event_payloads(active_link)

    ev.refresh_from_db()
    assert ev.payload_enc is None
    assert ev.payload_dek is None


def test_sweep_shreds_a_stale_event_payload_even_on_a_dead_link(fed_settings, active_link, world):
    """Flag-independent and status-independent: turning federation off, or a link
    going dark, must never strand decryptable contact PII."""
    ev = _pending_accepted_event(active_link, age_hours=100)
    active_link.status = "suspended"
    active_link.save(update_fields=["status"])

    shredded = outbox.sweep_stale_event_payloads()

    ev.refresh_from_db()
    assert shredded == 1
    assert ev.payload_enc is None


def test_sweep_leaves_a_fresh_pending_payload_alone(fed_settings, active_link, world):
    """A live delivery in its retry window still needs its payload."""
    ev = _pending_accepted_event(active_link, age_hours=1)

    assert outbox.sweep_stale_event_payloads() == 0
    ev.refresh_from_db()
    assert ev.payload_enc is not None


def test_sweep_runs_with_federation_disabled(fed_settings, active_link, world, settings):
    """The retention guarantee cannot be conditional on the feature flag."""
    ev = _pending_accepted_event(active_link, age_hours=100)
    settings.FEDERATION_ENABLED = False

    from apps.federation import tasks

    assert tasks.sweep_stale_event_payloads() == 1
    ev.refresh_from_db()
    assert ev.payload_enc is None

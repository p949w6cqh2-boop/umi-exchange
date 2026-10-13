"""
A proposal from another community tells the asker, as a local one does (the founder's call,
2026-10-13).

A local proposal sends the asker a "match proposed" note (in-app, and email if they opted in), but
receive_proposal sent nothing, so the asker might not learn of a federated proposal until they
opened their ask. Now it sends the same note, naming the community it comes from and what it
offers. A duplicate or refused proposal sends nothing.
"""

import uuid

import pytest
from django.utils import timezone

from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import matching, sharing
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


@pytest.fixture
def shared(fed_settings, active_link, world):
    from apps.needs.models import Need

    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="groceries",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer",
        grantee_type="community",
        grantee_id=active_link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    return need, sharing.share_record(need, active_link, actor_user=world.admin_u)


def _receive(share, proposal_uuid=None, **kw):
    return matching.receive_proposal(
        share.link.peer,
        need_remote_uuid=share.remote_uuid,
        proposal_uuid=proposal_uuid or uuid.uuid4(),
        link=share.link,
        **kw,
    )


def test_the_asker_is_told_like_a_local_proposal(shared, world):
    need, share = shared
    res = _receive(share, offer_title="Fresh bread and soup", offer_category="Meals")

    note = Notification.objects.get(recipient=world.plain_u, type="match_proposed")
    assert note.title == "Peer Board (federated) proposed a match on your need 'groceries'"
    assert note.body == "They offer: Fresh bread and soup. View the match to accept or decline."
    assert note.link == f"/c/{world.community.slug}/matches/{res['match_uuid']}/"


def test_without_a_title_the_note_still_goes(shared, world):
    _need, share = shared
    _receive(share)

    note = Notification.objects.get(recipient=world.plain_u, type="match_proposed")
    assert note.body == "View the match to accept or decline."


def test_a_duplicate_sends_nothing_more(shared, world):
    _need, share = shared
    pid = uuid.uuid4()
    _receive(share, proposal_uuid=pid, offer_title="Tea")
    assert _receive(share, proposal_uuid=pid, offer_title="Tea")["status"] == "duplicate"

    assert Notification.objects.filter(recipient=world.plain_u, type="match_proposed").count() == 1


def test_a_refused_proposal_sends_nothing(shared, world):
    need, share = shared
    need.status = "matched"
    need.save(update_fields=["status"])

    assert _receive(share, offer_title="Tea")["reason"] == "gone"
    assert not Notification.objects.filter(recipient=world.plain_u).exists()

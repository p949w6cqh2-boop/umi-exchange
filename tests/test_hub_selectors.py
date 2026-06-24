import pytest

from apps.hub import selectors
from tests.conftest import (
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def test_member_communities_only_active_newest_first():
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    inactive = MemberFactory(user=user, community=CommunityFactory(), is_active=False)
    result = selectors.member_communities(user)
    assert inactive not in result
    assert set(result) == {a, b}


def test_open_matches_includes_participant_roles_excludes_others():
    community = CommunityFactory()
    me = MemberFactory(community=community)
    other = MemberFactory(community=community)
    my_need = NeedFactory(community=community, requester=me)
    as_requester = MatchFactory(need=my_need, proposed_by=other, status="proposed")
    my_offer = OfferFactory(community=community, offerer=me)
    other_need = NeedFactory(community=community, requester=other)
    as_offerer = MatchFactory(need=other_need, offer=my_offer, proposed_by=other, status="accepted")
    as_proposer = MatchFactory(
        need=NeedFactory(community=community, requester=other), proposed_by=me, status="proposed"
    )
    not_mine = MatchFactory(
        need=NeedFactory(community=community, requester=other), proposed_by=other, status="proposed"
    )
    result = selectors.open_matches_for(me)
    ids = {m.pk for m in result}
    assert {as_requester.pk, as_offerer.pk, as_proposer.pk} <= ids
    assert not_mine.pk not in ids


def test_open_matches_excludes_terminal_status():
    community = CommunityFactory()
    me = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=me)
    MatchFactory(need=need, proposed_by=me, status="fulfilled")
    assert selectors.open_matches_for(me) == []


def test_open_matches_excludes_other_communities():
    me_a = MemberFactory(community=CommunityFactory())
    # same user, different community
    me_b = MemberFactory(user=me_a.user, community=CommunityFactory())
    need_b = NeedFactory(community=me_b.community, requester=me_b)
    MatchFactory(need=need_b, proposed_by=me_b, status="proposed")
    # focused on A → B's match must not appear
    assert selectors.open_matches_for(me_a) == []


def test_open_matches_respects_cap():
    community = CommunityFactory()
    me = MemberFactory(community=community)
    for _ in range(selectors.OPEN_MATCHES_CAP + 5):
        MatchFactory(
            need=NeedFactory(community=community, requester=me),
            proposed_by=me,
            status="proposed",
        )
    assert len(selectors.open_matches_for(me)) == selectors.OPEN_MATCHES_CAP


def test_recent_notifications_only_recipient_capped():
    from apps.notifications.models import Notification

    user = UserFactory()
    other = UserFactory()
    for i in range(selectors.RECENT_NOTIFICATIONS_CAP + 3):
        Notification.objects.create(recipient=user, type="match_proposed", title=f"n{i}")
    Notification.objects.create(recipient=other, type="match_proposed", title="not yours")
    result = selectors.recent_notifications(user)
    assert len(result) == selectors.RECENT_NOTIFICATIONS_CAP
    assert all(n.recipient_id == user.id for n in result)


def test_own_tags_only_this_member_all_statuses():
    from apps.tags.models import MemberTag, Tag

    community = CommunityFactory()
    me = MemberFactory(community=community)
    other = MemberFactory(community=community)
    tag = Tag.objects.create(community=community, slug="driver", label="Driver")
    mine = MemberTag.objects.create(member=me, tag=tag, status="self_claimed")
    theirs = MemberTag.objects.create(member=other, tag=tag, status="verified")
    result = selectors.own_tags(me)
    assert mine in result
    assert theirs not in result

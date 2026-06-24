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
    import datetime

    from django.utils import timezone

    from apps.communities.models import Member

    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    inactive = MemberFactory(user=user, community=CommunityFactory(), is_active=False)
    # joined_at is auto_now_add; force deterministic values to assert -joined_at order
    Member.objects.filter(pk=a.pk).update(joined_at=timezone.now() - datetime.timedelta(days=2))
    Member.objects.filter(pk=b.pk).update(joined_at=timezone.now())
    result = selectors.member_communities(user)
    assert inactive not in result
    assert [m.pk for m in result] == [b.pk, a.pk]  # active only, newest (b) first


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


def test_open_matches_excludes_match_outside_member_community():
    # `me` is a participant (proposer) of a match whose need is in ANOTHER
    # community. Member-identity alone would include it, so this isolates the
    # need__community scope guard — the "no cross-community leak" constraint.
    # (Delete that filter and only THIS test fails.)
    me = MemberFactory(community=CommunityFactory())
    other_community = CommunityFactory()
    other_member = MemberFactory(community=other_community)
    need_elsewhere = NeedFactory(community=other_community, requester=other_member)
    MatchFactory(need=need_elsewhere, proposed_by=me, status="proposed")
    assert selectors.open_matches_for(me) == []


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
    # sort_order pins the expected ordering: Cook (0) before Driver (1)
    tag_driver = Tag.objects.create(community=community, slug="driver", label="Driver", sort_order=1)
    tag_cook = Tag.objects.create(community=community, slug="cook", label="Cook", sort_order=0)
    mine_claimed = MemberTag.objects.create(member=me, tag=tag_driver, status="self_claimed")
    mine_verified = MemberTag.objects.create(member=me, tag=tag_cook, status="verified")
    theirs = MemberTag.objects.create(member=other, tag=tag_driver, status="verified")
    result = selectors.own_tags(me)
    # all of the member's OWN tags surface regardless of status; others' excluded
    assert mine_claimed in result
    assert mine_verified in result  # non-default status still surfaces
    assert theirs not in result
    # ordered by tag.sort_order then label
    assert [mt.pk for mt in result] == [mine_verified.pk, mine_claimed.pk]

"""Member-to-member block — preventative and member-initiated.

A neighbour can decide not to be matched with or shown another neighbour. A
block stops future matches between the two and hides each from the other on the
board. It is NOT a recall: contact already revealed by a past accepted match is
not taken back (§3.6 mental model). The blocked person is not told.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.matches.models import Match
from apps.moderation.models import Block
from apps.moderation.services import is_blocked_between
from apps.notifications.models import Notification
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def pair():
    community = CommunityFactory()
    a = MemberFactory(community=community, role="member", display_name="Ada")
    b = MemberFactory(community=community, role="member", display_name="Ben")
    return community, a, b


class TestBlockHelper:
    def test_is_blocked_between_is_symmetric(self, pair):
        community, a, b = pair
        assert is_blocked_between(a, b) is False
        Block.objects.create(community=community, blocker=a, blocked=b)
        assert is_blocked_between(a, b) is True
        assert is_blocked_between(b, a) is True  # a blocked b, but neither can reach the other


class TestProposeGuard:
    def test_blocked_neighbour_cannot_propose_their_offer_on_your_need(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=a, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=b, category=cat, status="active")
        Block.objects.create(community=community, blocker=a, blocked=b)
        resp = _login(b).post(
            reverse("match-propose", kwargs={"slug": community.slug}),
            {"need_id": str(need.pk), "offer_id": str(offer.pk)},
        )
        assert resp.status_code == 409
        assert Match.objects.count() == 0

    def test_you_cannot_propose_onto_a_blocked_neighbours_need(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        # b's need, a's offer; a blocked b, so a can't volunteer onto b's need either
        need = NeedFactory(community=community, requester=b, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=a, category=cat, status="active")
        Block.objects.create(community=community, blocker=a, blocked=b)
        resp = _login(a).post(
            reverse("match-propose", kwargs={"slug": community.slug}),
            {"need_id": str(need.pk), "offer_id": str(offer.pk)},
        )
        assert resp.status_code == 409
        assert Match.objects.count() == 0

    def test_unrelated_neighbours_can_still_propose(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=a, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=b, category=cat, status="active")
        # no block
        resp = _login(b).post(
            reverse("match-propose", kwargs={"slug": community.slug}),
            {"need_id": str(need.pk), "offer_id": str(offer.pk)},
        )
        assert resp.status_code == 302
        assert Match.objects.count() == 1


class TestFeedHiding:
    def test_blocked_pair_are_hidden_from_each_others_feed(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        NeedFactory(community=community, requester=a, category=cat, status="open", title="Ada needs a lift")
        NeedFactory(community=community, requester=b, category=cat, status="open", title="Ben needs bread")
        Block.objects.create(community=community, blocker=a, blocked=b)

        a_feed = _login(a).get(reverse("community-feed", kwargs={"slug": community.slug})).content
        b_feed = _login(b).get(reverse("community-feed", kwargs={"slug": community.slug})).content
        assert b"Ben needs bread" not in a_feed  # a doesn't see b
        assert b"Ada needs a lift" not in b_feed  # b doesn't see a (symmetric)

    def test_unblocked_neighbour_still_sees_both(self, pair):
        community, a, b = pair
        c = MemberFactory(community=community, role="member", display_name="Cleo")
        cat = CategoryFactory(community=community)
        NeedFactory(community=community, requester=a, category=cat, status="open", title="Ada needs a lift")
        NeedFactory(community=community, requester=b, category=cat, status="open", title="Ben needs bread")
        Block.objects.create(community=community, blocker=a, blocked=b)
        c_feed = _login(c).get(reverse("community-feed", kwargs={"slug": community.slug})).content
        assert b"Ada needs a lift" in c_feed
        assert b"Ben needs bread" in c_feed


class TestDetailGating:
    def test_blocked_neighbour_cannot_open_your_need_detail(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        a_need = NeedFactory(community=community, requester=a, category=cat, status="open")
        Block.objects.create(community=community, blocker=a, blocked=b)
        # b tries to open a's need
        resp = _login(b).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": a_need.pk}))
        assert resp.status_code == 404
        # and a can't open b would-be content either (symmetric) — use an offer
        b_offer = OfferFactory(community=community, offerer=b, category=cat, status="active")
        resp2 = _login(a).get(reverse("offer-detail", kwargs={"slug": community.slug, "pk": b_offer.pk}))
        assert resp2.status_code == 404


class TestPreventativeNotRecall:
    def test_block_does_not_cancel_or_unreveal_an_existing_match(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=a, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=b, category=cat, status="active")
        match = MatchFactory(need=need, offer=offer, proposed_by=b, status="proposed")
        match.transition_to("accepted")
        # a blocks b AFTER contact was already revealed by the accepted match
        Block.objects.create(community=community, blocker=a, blocked=b)
        match.refresh_from_db()
        assert match.status == "accepted"  # not recalled
        assert match.get_contact_info_for(a) is not None  # past disclosure stands (§3.6)


class TestBlockViews:
    def test_member_can_block_and_blocked_is_not_notified(self, pair):
        community, a, b = pair
        resp = _login(a).post(reverse("moderation:block", kwargs={"slug": community.slug}), {"blocked_id": str(b.pk)})
        assert resp.status_code in (302, 200)
        assert Block.objects.filter(blocker=a, blocked=b).exists()
        assert AuditLog.objects.filter(action="member.blocked").exists()
        assert not Notification.objects.filter(recipient=b.user).exists()  # the blocked person is not told

    def test_cannot_block_yourself(self, pair):
        community, a, b = pair
        _login(a).post(reverse("moderation:block", kwargs={"slug": community.slug}), {"blocked_id": str(a.pk)})
        assert not Block.objects.filter(blocker=a, blocked=a).exists()

    def test_unblock_removes_the_block(self, pair):
        community, a, b = pair
        Block.objects.create(community=community, blocker=a, blocked=b)
        _login(a).post(reverse("moderation:unblock", kwargs={"slug": community.slug}), {"blocked_id": str(b.pk)})
        assert not Block.objects.filter(blocker=a, blocked=b).exists()
        assert AuditLog.objects.filter(action="member.unblocked").exists()

    def test_cannot_block_across_communities(self, pair):
        community, a, b = pair
        outsider = MemberFactory(community=CommunityFactory(), role="member")
        resp = _login(a).post(
            reverse("moderation:block", kwargs={"slug": community.slug}), {"blocked_id": str(outsider.pk)}
        )
        assert resp.status_code == 404
        assert not Block.objects.filter(blocker=a, blocked=outsider).exists()


class TestBlockList:
    def test_member_sees_their_blocks_with_an_unblock_control(self, pair):
        community, a, b = pair
        Block.objects.create(community=community, blocker=a, blocked=b)
        resp = _login(a).get(reverse("moderation:blocks", kwargs={"slug": community.slug}))
        assert resp.status_code == 200
        assert b"Ben" in resp.content  # the blocked neighbour is listed
        assert reverse("moderation:unblock", kwargs={"slug": community.slug}).encode() in resp.content

    def test_list_shows_only_your_own_blocks(self, pair):
        community, a, b = pair
        c = MemberFactory(community=community, role="member", display_name="Cleo")
        Block.objects.create(community=community, blocker=b, blocked=c)  # b's block, not a's
        resp = _login(a).get(reverse("moderation:blocks", kwargs={"slug": community.slug}))
        assert b"Cleo" not in resp.content


class TestCounterpart:
    def test_counterpart_is_the_other_participant(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=a, category=cat)
        offer = OfferFactory(community=community, offerer=b, category=cat)
        match = MatchFactory(need=need, offer=offer, proposed_by=b)
        assert match.counterpart_member_for(a) == b
        assert match.counterpart_member_for(b) == a
        assert match.counterpart_member_for(MemberFactory(community=community)) is None


class TestMatchDetailSafetyControls:
    def _accepted(self, community, a, b):
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=a, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=b, category=cat, status="active")
        match = MatchFactory(need=need, offer=offer, proposed_by=b, status="proposed")
        match.transition_to("accepted")
        return match

    def test_participant_sees_report_and_block_after_accept(self, pair):
        community, a, b = pair
        match = self._accepted(community, a, b)
        content = (
            _login(a).get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.pk})).content.decode()
        )
        assert reverse("moderation:block", kwargs={"slug": community.slug}) in content
        assert reverse("moderation:flag", kwargs={"slug": community.slug}) in content
        assert str(b.pk) in content  # the counterpart is the block/report target

    def test_no_block_control_before_accept(self, pair):
        community, a, b = pair
        cat = CategoryFactory(community=community)
        need = NeedFactory(community=community, requester=a, category=cat, status="open")
        offer = OfferFactory(community=community, offerer=b, category=cat, status="active")
        match = MatchFactory(need=need, offer=offer, proposed_by=b, status="proposed")
        content = (
            _login(a).get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.pk})).content.decode()
        )
        # Identities aren't revealed pre-accept (§8.2), so no report/block control yet.
        assert reverse("moderation:block", kwargs={"slug": community.slug}) not in content

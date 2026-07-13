"""P2 — first-run guidance: data-derived first-steps card, honest empty
states, and the owner's what-happens-next hint. No schema, no tracking —
progress is read from what the member has actually done."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.hub import selectors
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
)

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def world():
    community = CommunityFactory()
    member = MemberFactory(community=community, role="member")
    other = MemberFactory(community=community, role="member")
    category = CategoryFactory(community=community)
    return community, member, other, category


class TestFirstStepsSelector:
    def test_fresh_member_has_all_steps_open(self, world):
        community, member, other, category = world
        steps = selectors.first_steps(member)
        assert steps == {"posted": False, "offered": False, "connected": False}

    def test_posting_checks_the_first_step(self, world):
        community, member, other, category = world
        NeedFactory(community=community, requester=member, category=category)
        assert selectors.first_steps(member)["posted"] is True

    def test_offering_and_connecting_check_their_steps(self, world):
        community, member, other, category = world
        their_need = NeedFactory(community=community, requester=other, category=category)
        MatchFactory(need=their_need, proposed_by=member, status="accepted")
        steps = selectors.first_steps(member)
        assert steps["offered"] is True and steps["connected"] is True

    def test_card_retires_when_everything_is_done(self, world):
        community, member, other, category = world
        NeedFactory(community=community, requester=member, category=category)
        their_need = NeedFactory(community=community, requester=other, category=category)
        MatchFactory(need=their_need, proposed_by=member, status="accepted")
        assert selectors.first_steps(member) is None


class TestHubCard:
    def test_fresh_member_sees_first_steps(self, world):
        community, member, other, category = world
        resp = _login(member).get(reverse("hub:community", kwargs={"slug": community.slug}))
        assert b"Your first steps" in resp.content
        assert b"Put something on the board" in resp.content

    def test_finished_member_sees_no_card(self, world):
        community, member, other, category = world
        NeedFactory(community=community, requester=member, category=category)
        their_need = NeedFactory(community=community, requester=other, category=category)
        MatchFactory(need=their_need, proposed_by=member, status="accepted")
        resp = _login(member).get(reverse("hub:community", kwargs={"slug": community.slug}))
        assert b"Your first steps" not in resp.content


class TestEmptyStates:
    def test_filtered_board_offers_to_clear_filters(self, world):
        community, member, other, category = world
        resp = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug}), {"q": "zebra-unicorn"})
        assert b"matches those filters" in resp.content
        assert b"Clear filters" in resp.content

    def test_unfiltered_empty_board_keeps_first_use_copy(self, world):
        community, member, other, category = world
        resp = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert b"No needs or offers yet" in resp.content

    def test_notifications_empty_state_explains_what_lands_here(self, world):
        community, member, other, category = world
        resp = _login(member).get(reverse("notification-list"))
        assert b"it lands here" in resp.content


class TestOwnerHint:
    def test_owner_sees_what_happens_next(self, world):
        community, member, other, category = world
        need = NeedFactory(community=community, requester=member, category=category)
        resp = _login(member).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk}))
        assert b"You&#x27;ll get a notification" in resp.content or b"You'll get a notification" in resp.content

    def test_visitor_does_not_see_the_owner_hint(self, world):
        community, member, other, category = world
        need = NeedFactory(community=community, requester=member, category=category)
        resp = _login(other).get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk}))
        assert b"You&#x27;ll get a notification" not in resp.content
        assert b"You'll get a notification" not in resp.content

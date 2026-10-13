"""
A block between a member and a coordinator (the founder's call, 2026-10-13, bug hunt L1).

A block is symmetric: the two people stop seeing each other's posts and are never matched. It
had no coordinator exemption, so a member could take themselves out of one coordinator's
oversight: their posts left that coordinator's feed and the post pages 404ed, while the dashboard
still linked to them. The call: coordinators keep oversight. A coordinator still sees every post
in a community they coordinate, the way they already see posts hidden by moderation. The two are
still never matched, the member still never sees the coordinator's posts, and the coordinator gets
no contact reveal for the person they share a block with (another coordinator still does).
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.moderation.models import Block
from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def board():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    coord = MemberFactory(community=community, role="coordinator", display_name="Cora")
    other_coord = MemberFactory(community=community, role="coordinator", display_name="Otto")
    member = MemberFactory(community=community, display_name="Mabel")
    need = NeedFactory(community=community, requester=member, category=cat, title="Mabel needs a lift on Tuesday")
    offer = OfferFactory(community=community, offerer=member, category=cat, title="Mabel can mend coats")
    coord_offer = OfferFactory(community=community, offerer=coord, category=cat, title="Cora drives on Tuesdays")
    return community, cat, coord, other_coord, member, need, offer, coord_offer


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


def _block(community, blocker, blocked):
    return Block.objects.create(community=community, blocker=blocker, blocked=blocked, reason="")


@pytest.mark.parametrize("member_blocks", [True, False], ids=["member-blocks-coordinator", "coordinator-blocks-member"])
def test_coordinator_still_sees_the_members_posts(board, member_blocks):
    community, _cat, coord, _other, member, need, offer, _coord_offer = board
    if member_blocks:
        _block(community, member, coord)
    else:
        _block(community, coord, member)
    c = _client(coord)

    feed = c.get(reverse("community-feed", kwargs={"slug": community.slug})).content.decode()
    assert need.title in feed
    assert offer.title in feed
    assert c.get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk})).status_code == 200
    assert c.get(reverse("offer-detail", kwargs={"slug": community.slug, "pk": offer.pk})).status_code == 200


def test_member_still_does_not_see_the_coordinators_posts(board):
    community, _cat, coord, _other, member, _need, _offer, coord_offer = board
    _block(community, member, coord)
    m = _client(member)

    feed = m.get(reverse("community-feed", kwargs={"slug": community.slug})).content.decode()
    assert coord_offer.title not in feed
    assert m.get(reverse("offer-detail", kwargs={"slug": community.slug, "pk": coord_offer.pk})).status_code == 404


def test_a_plain_neighbour_block_is_unchanged(board):
    community, cat, _coord, _other, member, need, _offer, _coord_offer = board
    neighbour = MemberFactory(community=community, display_name="Ned")
    _block(community, member, neighbour)
    n = _client(neighbour)

    feed = n.get(reverse("community-feed", kwargs={"slug": community.slug})).content.decode()
    assert need.title not in feed
    assert n.get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk})).status_code == 404


def test_blocked_coordinator_gets_no_contact_reveal_and_no_offer_buttons(board):
    community, _cat, coord, _other, member, need, offer, coord_offer = board
    _block(community, member, coord)
    c = _client(coord)

    r = c.get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk}))
    assert r.context["show_contact"] is False
    body = r.content.decode()
    # The page would list the coordinator's own offer under a Propose Match button that the
    # propose view then refuses. The pair is never matched, so the section is not shown.
    assert coord_offer.title not in body
    assert reverse("match-propose", kwargs={"slug": community.slug}) not in body

    r = c.get(reverse("offer-detail", kwargs={"slug": community.slug, "pk": offer.pk}))
    assert r.context["show_contact"] is False
    assert not AuditLog.objects.filter(action__in=("need.contact_disclosed", "offer.contact_disclosed")).exists()


def test_another_coordinator_keeps_the_contact_reveal(board):
    community, _cat, coord, other, member, need, _offer, _coord_offer = board
    _block(community, member, coord)
    o = _client(other)

    r = o.get(reverse("need-detail", kwargs={"slug": community.slug, "pk": need.pk}))
    assert r.status_code == 200
    assert r.context["show_contact"] is True


def test_the_pair_is_still_never_matched(board):
    community, _cat, coord, _other, member, need, _offer, coord_offer = board
    _block(community, member, coord)
    c = _client(coord)

    r = c.post(
        reverse("match-propose", kwargs={"slug": community.slug}),
        {"need_id": str(need.pk), "offer_id": str(coord_offer.pk)},
    )
    assert r.status_code == 409
    assert not need.matches.exists()

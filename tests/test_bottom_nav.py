"""Mobile thumb-reach bar: renders for signed-in members, carries the four
core destinations + the elevated post action, marks the current tab, and
survives slug-less pages via a session fallback. Desktop hiding is CSS
(sm:hidden) and out of scope for a server test."""

import pytest
from django.test import Client
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def world():
    community = CommunityFactory()
    member = MemberFactory(community=community, role="member")
    return community, member


def test_bar_renders_for_a_member_with_the_core_destinations(world):
    community, member = world
    resp = _login(member).get(reverse("hub:community", kwargs={"slug": community.slug}))
    body = resp.content.decode()
    assert "umi-bottomnav" in body
    for label in (">Hub<", ">Board<", ">Alerts<", ">You<"):
        assert label in body
    assert reverse("need-create", kwargs={"slug": community.slug}) in body
    assert reverse("offer-create", kwargs={"slug": community.slug}) in body


def test_current_tab_is_marked(world):
    community, member = world
    resp = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug}))
    body = resp.content.decode()
    # the Board tab carries aria-current on the feed page
    assert 'aria-current="page"' in body
    assert "is-active" in body


def test_bar_survives_a_slugless_page_via_session(world):
    community, member = world
    client = _login(member)
    # visit a community page first so the fallback slug is stamped
    client.get(reverse("community-feed", kwargs={"slug": community.slug}))
    # then a slug-less page — the bar should still resolve its links
    resp = client.get(reverse("notification-list"))
    body = resp.content.decode()
    assert "umi-bottomnav" in body
    assert reverse("hub:community", kwargs={"slug": community.slug}) in body


def test_no_bar_for_anonymous_visitors():
    resp = Client().get(reverse("landing"))
    assert "umi-bottomnav" not in resp.content.decode()

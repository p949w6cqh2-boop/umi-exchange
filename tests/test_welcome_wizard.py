"""P5 — the setup wizard: creating a community lands its founder on a guided
page (share code → theme → coordinators → first post) with data-derived
checkmarks. Admin-only, revisitable, skippable."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.communities.models import Community
from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory, UserFactory

pytestmark = pytest.mark.django_db


def _login(user):
    c = Client()
    c.force_login(user)
    return c


def test_creating_a_community_lands_on_the_wizard():
    user = UserFactory()
    resp = _login(user).post(reverse("community-create"), {"name": "St. Monica", "visibility": "private"})
    community = Community.objects.get(name="St. Monica")
    assert resp.status_code == 302
    assert resp.url == reverse("community-welcome", kwargs={"slug": community.slug})


@pytest.fixture
def world():
    community = CommunityFactory()
    admin = MemberFactory(community=community, role="admin")
    member = MemberFactory(community=community, role="member")
    return community, admin, member


def test_wizard_shows_the_join_code_to_the_admin(world):
    community, admin, member = world
    resp = _login(admin.user).get(reverse("community-welcome", kwargs={"slug": community.slug}))
    assert resp.status_code == 200
    assert community.join_code.encode() in resp.content
    assert b"is ready." in resp.content


def test_wizard_is_admin_only(world):
    community, admin, member = world
    assert _login(member.user).get(reverse("community-welcome", kwargs={"slug": community.slug})).status_code == 403
    outsider = MemberFactory(community=CommunityFactory(), role="admin")
    assert _login(outsider.user).get(reverse("community-welcome", kwargs={"slug": community.slug})).status_code == 404


def test_posted_step_flips_with_the_first_ask(world):
    community, admin, member = world
    url = reverse("community-welcome", kwargs={"slug": community.slug})
    assert _login(admin.user).get(url).context["steps"]["posted"] is False
    NeedFactory(community=community, requester=member, category=CategoryFactory(community=community))
    assert _login(admin.user).get(url).context["steps"]["posted"] is True


def test_theme_post_round_trips_back_to_the_wizard(world):
    community, admin, member = world
    welcome = reverse("community-welcome", kwargs={"slug": community.slug})
    resp = _login(admin.user).post(
        reverse("community-settings", kwargs={"slug": community.slug}),
        {"action": "set_theme", "theme": "ocean", "next": welcome},
    )
    assert resp.status_code == 302 and resp.url == welcome
    community.refresh_from_db()
    assert community.settings["theme"] == "ocean"
    assert _login(admin.user).get(welcome).context["steps"]["themed"] is True


def test_theme_next_never_leaves_the_site(world):
    community, admin, member = world
    resp = _login(admin.user).post(
        reverse("community-settings", kwargs={"slug": community.slug}),
        {"action": "set_theme", "theme": "ocean", "next": "//evil.example/phish"},
    )
    assert resp.status_code == 302
    assert resp.url == reverse("community-settings", kwargs={"slug": community.slug})

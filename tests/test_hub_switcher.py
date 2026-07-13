import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_switcher_lists_only_my_communities(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    CommunityFactory(name="Gamma")  # not a membership
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": a.community.slug}))
    body = resp.content.decode()
    assert "Alpha" in body and "Beta" in body
    assert "Gamma" not in body


def test_switcher_marks_focused_community(client):
    import re

    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": a.community.slug}))
    body = resp.content.decode()
    # Scope to the switcher nav: the mobile bottom nav (_bottom_nav.html) also
    # emits aria-current="page" for the active section, so a whole-body count is
    # not the switcher's to make.
    switcher = re.search(r'<nav\b[^>]*class="[^"]*umi-switcher[^"]*"[^>]*>(.*?)</nav>', body, re.S)
    assert switcher, "switcher nav not found in response"
    region = switcher.group(1)
    # exactly one community is marked current, and it is the focused one (Alpha)
    assert region.count('aria-current="page"') == 1
    marked = re.search(r'<a\b[^>]*aria-current="page"[^>]*>(.*?)</a>', region, re.S)
    assert marked and "Alpha" in marked.group(1)


def test_switch_to_other_membership_renders_that_community(client):
    user = UserFactory()
    MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    b = MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": b.community.slug}), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert "Beta" in resp.content.decode()

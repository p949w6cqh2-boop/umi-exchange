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
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": a.community.slug}))
    assert 'aria-current="page"' in resp.content.decode()


def test_switch_to_other_membership_renders_that_community(client):
    user = UserFactory()
    MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    b = MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": b.community.slug}), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert "Beta" in resp.content.decode()

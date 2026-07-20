"""The mobile bottom nav stays off focused-task screens.

At phone width the fixed nav z-ordered over the create forms' fixed submit strip
(tab links intercepted the whole strip — the primary action was unclickable), and
its tabs sat one mis-tap from discarding a half-filled form. Task screens drop
the tab bar; browsing screens keep it.
"""

import pytest
from django.test import Client
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def member_client():
    community = CommunityFactory()
    member = MemberFactory(community=community, role="member")
    member.user.set_password("pw")
    member.user.save()
    client = Client(SERVER_NAME="127.0.0.1")
    client.force_login(member.user)
    return client, community


def test_create_screens_drop_the_bottom_nav(member_client):
    client, community = member_client
    for url_name in ("need-create", "offer-create"):
        resp = client.get(reverse(url_name, args=[community.slug]))
        assert resp.status_code == 200
        assert b"umi-bottomnav" not in resp.content, f"{url_name}: nav must not cover the submit strip"


def test_browsing_screens_keep_the_bottom_nav(member_client):
    client, community = member_client
    resp = client.get(reverse("community-feed", args=[community.slug]))
    assert resp.status_code == 200
    assert b"umi-bottomnav" in resp.content, "the board keeps the thumb bar"

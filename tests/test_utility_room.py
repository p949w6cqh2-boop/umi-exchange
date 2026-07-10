"""Phase 3 "Utility Room" — the workaday surfaces (dashboard, settings,
notifications, consents, households) join the Commons token idiom:
no legacy gray-*/blue-* utilities on rendered pages, umi-card shells,
serif headings. Palette guards mirror tests/test_members_day.py."""

import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db

LEGACY = ("text-gray-", "bg-gray-", "text-blue-6", "border-l-blue-")


@pytest.fixture
def member(db):
    return MemberFactory(user=UserFactory(), community=CommunityFactory())


@pytest.fixture
def admin_member(db):
    return MemberFactory(user=UserFactory(), community=CommunityFactory(), role="admin")


def _body(client, member, url):
    client.force_login(member.user)
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.content.decode()


def _assert_tokened(body):
    for cls in LEGACY:
        assert cls not in body, f"legacy utility {cls!r} still rendered"


def test_dashboard_tokened(client, admin_member):
    body = _body(
        client,
        admin_member,
        reverse("community-dashboard", args=[admin_member.community.slug]),
    )
    _assert_tokened(body)
    assert "umi-card" in body


def test_notifications_list_tokened(client, member):
    body = _body(client, member, reverse("notification-list"))
    _assert_tokened(body)


def test_consent_list_tokened(client, member):
    body = _body(client, member, reverse("consent-list"))
    _assert_tokened(body)


def test_account_settings_tokened(client, member):
    body = _body(client, member, reverse("account-settings"))
    _assert_tokened(body)


def test_community_settings_tokened(client, admin_member):
    body = _body(
        client,
        admin_member,
        reverse("community-settings", args=[admin_member.community.slug]),
    )
    _assert_tokened(body)


def test_household_create_tokened(client, member):
    body = _body(client, member, reverse("household-create"))
    _assert_tokened(body)
    assert "umi-card" in body


def test_household_join_tokened(client, member):
    body = _body(client, member, reverse("household-join"))
    _assert_tokened(body)
    assert "umi-card" in body

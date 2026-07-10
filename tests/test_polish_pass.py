"""Phase 4 "Finishing Coat" — auth-flow pages, create forms, the technology
page, and shared components shed the last legacy gray-*/blue-* utilities.
Casework, federation, and email templates are deliberately out of scope."""

import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db

LEGACY = ("text-gray-", "bg-gray-", "text-blue-6", "border-blue-")


@pytest.fixture
def member(db):
    return MemberFactory(user=UserFactory(), community=CommunityFactory())


def _assert_tokened(body):
    for cls in LEGACY:
        assert cls not in body, f"legacy utility {cls!r} still rendered"


@pytest.mark.parametrize("name", ["password_reset", "password_reset_done", "technology"])
def test_public_pages_tokened(client, name):
    resp = client.get(reverse(name))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


@pytest.mark.parametrize("name", ["password_change", "password_change_done"])
def test_password_change_pages_tokened(client, member, name):
    client.force_login(member.user)
    resp = client.get(reverse(name))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


@pytest.mark.parametrize("urlname", ["need-create", "offer-create"])
def test_create_forms_tokened(client, member, urlname):
    client.force_login(member.user)
    resp = client.get(reverse(urlname, args=[member.community.slug]))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


def test_recent_notifications_partial_tokened(client, member):
    client.force_login(member.user)
    resp = client.get(reverse("notifications-recent"))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


def test_my_tags_page_tokened(client, member):
    client.force_login(member.user)
    resp = client.get(reverse("tags:my-tags", kwargs={"slug": member.community.slug}))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())

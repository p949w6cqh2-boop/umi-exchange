"""Follow-up joining C11 (intake helper) and B8 (sign-up helper): an intake helper can use the sign-up
helper, his B8 ruling 2026-09-30 ("coordinators and helpers"), and still can never touch a password.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import RecoveryCredential, User
from tests.factories import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    from django.core.cache import cache

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_ENABLED = False
    cache.clear()


@pytest.fixture
def parish():
    return CommunityFactory()


def _as(member):
    client = Client()
    client.force_login(member.user)
    return client


def _fields(username):
    return {"username": username, "email": "", "password": "Str0ng-pass-word!", "password_confirm": "Str0ng-pass-word!"}


def test_intake_helper_can_sign_up_a_neighbor(parish):
    helper = MemberFactory(community=parish, role="intake")
    url = reverse("intake-register", kwargs={"slug": parish.slug})
    client = _as(helper)
    assert client.get(url).status_code == 200
    resp = client.post(url, _fields("walkin"))
    assert resp.status_code == 200
    assert User.objects.filter(username="walkin").exists()
    assert client.session["_auth_user_id"] == str(helper.user.pk)


def test_helper_page_links_back_to_vouching_not_settings(parish):
    helper = MemberFactory(community=parish, role="intake")
    body = _as(helper).get(reverse("intake-register", kwargs={"slug": parish.slug})).content.decode()
    assert reverse("member-vouch-page", kwargs={"slug": parish.slug}) in body
    assert reverse("community-settings", kwargs={"slug": parish.slug}) not in body


def test_vouch_page_points_to_the_sign_up_helper(parish):
    helper = MemberFactory(community=parish, role="intake")
    body = _as(helper).get(reverse("member-vouch-page", kwargs={"slug": parish.slug})).content.decode()
    assert reverse("intake-register", kwargs={"slug": parish.slug}) in body


def test_intake_helper_still_cannot_issue_a_reset(parish):
    helper = MemberFactory(community=parish, role="intake")
    MemberFactory(community=parish, role="member", user=UserFactory(username="lost"))
    assert helper.can_reset is False
    resp = _as(helper).post(reverse("member-reset", kwargs={"slug": parish.slug}), {"username": "lost"})
    assert resp.status_code == 403
    assert not RecoveryCredential.objects.filter(purpose="coordinator_reset").exists()


def test_plain_member_still_cannot_sign_anyone_up(parish):
    member = MemberFactory(community=parish, role="member")
    url = reverse("intake-register", kwargs={"slug": parish.slug})
    assert _as(member).post(url, _fields("nope")).status_code == 403
    assert not User.objects.filter(username="nope").exists()

"""Regression tests for the 2026-07-13 adversarial bug-hunt — Lake-1 / accounts Batch-1:

- Registration enforces password strength (AUTH_PASSWORD_VALIDATORS were unset).
- The password-reset POST is covered by the auth rate-limit middleware.
- MatchUpdateView returns 400 (not 500) when `notes` trips the injection validator.
- The community feed ignores a malformed ?category= instead of 500-ing.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


def _login(user):
    c = Client()
    c.force_login(user)
    return c


def test_registration_rejects_weak_password(client):
    resp = client.post(
        reverse("register"),
        {"username": "weakling", "email": "", "password": "1", "password_confirm": "1"},
    )
    assert resp.status_code == 200  # form re-rendered with errors, not a redirect
    assert not User.objects.filter(username="weakling").exists()


def test_registration_accepts_strong_password(client):
    resp = client.post(
        reverse("register"),
        {"username": "sturdy", "email": "", "password": "Str0ng-p4ss!x9", "password_confirm": "Str0ng-p4ss!x9"},
    )
    assert resp.status_code in (301, 302)  # created + logged in + redirected
    assert User.objects.filter(username="sturdy").exists()


def test_password_reset_path_is_rate_limited():
    assert "/auth/password/reset/" in settings.RATELIMIT_AUTH_PATHS


def test_match_update_rejects_script_notes_with_400_not_500():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community, is_active=True)
    offerer = MemberFactory(community=community, is_active=True)
    need = NeedFactory(community=community, requester=requester, category=category, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")

    client = _login(requester.user)
    resp = client.post(
        reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}),
        {"status": "accepted", "notes": "onclick=alert(1)"},
    )
    assert resp.status_code == 400
    match.refresh_from_db()
    assert match.status == "proposed"  # the status change did not slip through


def test_feed_ignores_malformed_category_param():
    community = CommunityFactory()
    member = MemberFactory(community=community, is_active=True)
    client = _login(member.user)
    resp = client.get(reverse("community-feed", kwargs={"slug": community.slug}) + "?category=not-a-uuid")
    assert resp.status_code == 200

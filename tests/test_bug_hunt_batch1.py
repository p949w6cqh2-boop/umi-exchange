"""Regression tests for the 2026-07-13 adversarial bug-hunt — Lake-1 / accounts Batch-1:

- Registration enforces password strength (AUTH_PASSWORD_VALIDATORS were unset).
- The password-reset POST is covered by the auth rate-limit middleware.
- MatchUpdateView returns 400 (not 500) when `notes` trips the content validator.
  (Since the 2026-10 bug hunt that is the word list only: script-looking text is kept and
  shown escaped, like every other free-text field.)
- The community feed ignores a malformed ?category= instead of 500-ing.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from tests.conftest import register_payload

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
    # Distinct IP: register is throttled 3/min/IP and the fixed window is shared
    # suite-wide, so same-minute register POSTs from other test files can 429 this
    # one depending on suite timing (house gotcha: rotate REMOTE_ADDR).
    resp = client.post(
        reverse("register"),
        register_payload(username="weakling", email="", password="1", password_confirm="1"),
        REMOTE_ADDR="10.44.1.1",
    )
    assert resp.status_code == 200  # form re-rendered with errors, not a redirect
    assert not User.objects.filter(username="weakling").exists()


def test_registration_accepts_strong_password(client):
    resp = client.post(
        reverse("register"),
        register_payload(username="sturdy", email="", password="Str0ng-p4ss!x9", password_confirm="Str0ng-p4ss!x9"),
        REMOTE_ADDR="10.44.1.2",
    )
    # Created + logged in. With no email, success is the one-time recovery-code page (A1,
    # docs/specs/account-recovery.md §B) rather than a redirect.
    assert resp.status_code == 200
    assert "accounts/recovery_code.html" in [t.name for t in resp.templates]
    assert User.objects.filter(username="sturdy").exists()


def test_password_reset_path_is_rate_limited():
    assert "/auth/password/reset/" in settings.RATELIMIT_AUTH_PATHS


def _proposed_match():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community, is_active=True)
    offerer = MemberFactory(community=community, is_active=True)
    need = NeedFactory(community=community, requester=requester, category=category, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")
    return community, requester, match


def test_match_update_rejects_refused_notes_with_400_not_500():
    community, requester, match = _proposed_match()

    client = _login(requester.user)
    resp = client.post(
        reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}),
        {"status": "accepted", "notes": "Pick up my prescription drugs"},
    )
    assert resp.status_code == 400
    match.refresh_from_db()
    assert match.status == "proposed"  # the status change did not slip through


def test_match_update_keeps_script_looking_notes_and_shows_them_escaped():
    community, requester, match = _proposed_match()
    url = reverse("match-update", kwargs={"slug": community.slug, "pk": match.id})

    client = _login(requester.user)
    assert client.post(url, {"status": "accepted"}).status_code == 302
    resp = client.post(url, {"status": "fulfilled", "notes": "<b onclick=alert(1)>see you at 5</b>"})
    assert resp.status_code == 302
    match.refresh_from_db()
    assert match.status == "fulfilled"
    assert match.notes == "<b onclick=alert(1)>see you at 5</b>"
    html = client.get(reverse("match-detail", args=[community.slug, match.id])).content.decode()
    assert "&lt;b onclick=alert(1)&gt;see you at 5&lt;/b&gt;" in html
    assert "<b onclick" not in html


def test_feed_ignores_malformed_category_param():
    community = CommunityFactory()
    member = MemberFactory(community=community, is_active=True)
    client = _login(member.user)
    resp = client.get(reverse("community-feed", kwargs={"slug": community.slug}) + "?category=not-a-uuid")
    assert resp.status_code == 200

"""Abuse-resistance regression tests (threat model §8 — the pre-pilot must-fixes
that are pure application code).

* **Join-code redemption is rate-limited** — community (``/join/``) and
  household (``/join/household/join/``) redemption throttle per user, so an
  authenticated account cannot brute-force the 8-char CSPRNG code space.
* **Cross-community IDOR (systematic):** every community-scoped object route
  refuses an actor from another community — at every role. The per-view
  filters are convention; this parametrised suite turns the convention into a
  contract so a refactor cannot quietly drop one.

The rest of §8's prescribed suite already exists elsewhere and is deliberately
not re-tested here: audit immutability (tests/test_audit.py), restricted-case
exclusion (apps/casework/tests/test_access_403.py), self-reported-never-
endorsed (tests/test_tags_display.py), coordinator-cannot-verify-clergy
(tests/test_tags_views.py), contact gating (tests/test_matches.py +
tests/test_audit_sweep.py).
"""

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.communities.models import Member
from apps.households.models import Household
from apps.tags.models import MemberTag, Tag

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
    UserFactory,
)


@pytest.fixture(autouse=True)
def _clear_ratelimit_cache():
    """The limiter is a cache-backed fixed window; clear it around every test
    so counters never bleed across tests."""
    cache.clear()
    yield
    cache.clear()


def login(user):
    c = Client()
    c.force_login(user)
    return c


# ──────────────────────────────────────────────────────────────────────
# Join-code redemption throttle (threat model must-fix #3)
# ──────────────────────────────────────────────────────────────────────
class TestCommunityJoinThrottle:
    JOIN_LIMIT = 10  # per user per hour

    def test_wrong_codes_throttle_after_limit(self, db):
        user = UserFactory()
        c = login(user)
        for i in range(self.JOIN_LIMIT):
            resp = c.post(reverse("community-join"), {"join_code": "WRONGCODE"})
            assert resp.status_code == 200, f"attempt {i + 1} inside the window should re-render, not throttle"
        resp = c.post(reverse("community-join"), {"join_code": "WRONGCODE"})
        assert resp.status_code == 429
        assert resp["Retry-After"]

    def test_throttle_is_per_user(self, db):
        exhausted, fresh = UserFactory(), UserFactory()
        c1 = login(exhausted)
        for _ in range(self.JOIN_LIMIT + 1):
            resp = c1.post(reverse("community-join"), {"join_code": "WRONGCODE"})
        assert resp.status_code == 429, "exhausted user should be throttled"
        resp = login(fresh).post(reverse("community-join"), {"join_code": "WRONGCODE"})
        assert resp.status_code == 200, "another user must not inherit the throttle"

    def test_valid_join_within_limit_succeeds(self, db):
        user = UserFactory()
        community = CommunityFactory()
        resp = login(user).post(reverse("community-join"), {"join_code": community.join_code})
        assert resp.status_code == 302
        assert Member.objects.filter(user=user, community=community).exists()

    def test_get_form_is_never_throttled(self, db):
        user = UserFactory()
        c = login(user)
        for _ in range(self.JOIN_LIMIT + 1):
            c.post(reverse("community-join"), {"join_code": "WRONGCODE"})
        assert c.get(reverse("community-join")).status_code == 200


class TestHouseholdJoinThrottle:
    JOIN_LIMIT = 10  # per user per hour

    def test_wrong_codes_throttle_after_limit(self, db):
        user = UserFactory()
        c = login(user)
        for i in range(self.JOIN_LIMIT):
            resp = c.post(reverse("household-join"), {"household_code": "WRONGCODE"})
            assert resp.status_code == 200, f"attempt {i + 1} inside the window should re-render, not throttle"
        resp = c.post(reverse("household-join"), {"household_code": "WRONGCODE"})
        assert resp.status_code == 429

    def test_valid_join_within_limit_succeeds(self, db):
        user = UserFactory()
        household = Household.objects.create(name="The Finches", created_by=UserFactory())
        resp = login(user).post(reverse("household-join"), {"household_code": household.join_code})
        assert resp.status_code == 302


# ──────────────────────────────────────────────────────────────────────
# Cross-community IDOR (threat model must-fix #2)
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture
def world_b(db):
    """The victim community and one of every community-scoped object."""
    community = CommunityFactory()
    member = MemberFactory(community=community, role="member")
    category = CategoryFactory(community=community)
    need = NeedFactory(community=community, requester=member, category=category)
    offer = OfferFactory(community=community, offerer=member, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=member)
    tag = Tag.objects.get(community=community, slug="homeowner")  # seeded catalog
    membertag = MemberTag.objects.create(member=member, tag=tag, status="pending")
    return {
        "community": community,
        "need": need,
        "offer": offer,
        "match": match,
        "membertag": membertag,
    }


@pytest.fixture
def community_a(db):
    return CommunityFactory()


# (route name, key into world_b, HTTP method, POST body) — every pk-carrying,
# community-scoped route outside casework (casework has its own 403 suite).
# match-update needs a valid status: the view rejects a malformed body with
# 400 *before* resolving community/member, and the point here is to exercise
# the community guard, not the input validation.
OBJECT_ROUTES = [
    ("need-detail", "need", "get", None),
    ("need-delete", "need", "post", None),
    ("offer-detail", "offer", "get", None),
    ("offer-delete", "offer", "post", None),
    ("match-detail", "match", "get", None),
    ("match-update", "match", "post", {"status": "accepted"}),
    ("tags:request-verify", "membertag", "post", None),
    ("tags:remove", "membertag", "post", None),
    ("tags:verify", "membertag", "post", None),
    ("tags:reject", "membertag", "post", None),
    ("tags:revoke", "membertag", "post", None),
]

ROLES = ["member", "coordinator", "admin"]


def _attacker(community, role):
    return MemberFactory(community=community, role=role)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("name,obj_key,method,data", OBJECT_ROUTES)
class TestCrossCommunityIDOR:
    def test_foreign_pk_under_own_slug_refused(self, community_a, world_b, name, obj_key, method, data, role):
        """Community A's slug + community B's pk: the object must be unreachable."""
        attacker = _attacker(community_a, role)
        url = reverse(name, kwargs={"slug": community_a.slug, "pk": world_b[obj_key].pk})
        resp = getattr(login(attacker.user), method)(url, data or {})
        assert resp.status_code in (403, 404), f"{role} reached {name} across communities: {resp.status_code}"

    def test_foreign_slug_refused(self, community_a, world_b, name, obj_key, method, data, role):
        """Community B's own URL: an actor from community A must be refused."""
        attacker = _attacker(community_a, role)
        url = reverse(name, kwargs={"slug": world_b["community"].slug, "pk": world_b[obj_key].pk})
        resp = getattr(login(attacker.user), method)(url, data or {})
        assert resp.status_code in (403, 404), f"{role} reached {name} across communities: {resp.status_code}"


def test_match_update_unknown_pk_is_404_not_500(community_a, db):
    """A member's stale link / typo'd match id must 404, not crash: the view's
    locked lookup is a bare ``.get(pk=…)``, and an unknown pk must not surface
    as a server error."""
    import uuid

    member = MemberFactory(community=community_a, role="member")
    url = reverse("match-update", kwargs={"slug": community_a.slug, "pk": uuid.uuid4()})
    resp = login(member.user).post(url, {"status": "accepted"})
    assert resp.status_code == 404


# Slug-only community pages: an admin of community A (the strongest
# cross-community probe) must not reach community B's pages.
PAGE_ROUTES = [
    ("community-feed", "get"),
    ("community-dashboard", "get"),
    ("dashboard-export", "get"),
    ("community-settings", "get"),
]


@pytest.mark.parametrize("name,method", PAGE_ROUTES)
def test_foreign_admin_refused_on_community_pages(community_a, world_b, name, method):
    """follow=True: settings legitimately 302s non-staff to the community feed
    — what matters is that the redirect chain also ends refused, so no
    community page is reachable directly or via bounce."""
    attacker = _attacker(community_a, "admin")
    url = reverse(name, kwargs={"slug": world_b["community"].slug})
    resp = getattr(login(attacker.user), method)(url, follow=True)
    assert resp.status_code in (403, 404), f"foreign admin reached {name}: {resp.status_code}"

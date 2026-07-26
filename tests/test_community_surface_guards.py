"""
Community-surface regressions (bug-hunt batch 4, #7 #18 #33 #35).

#7  templates/communities/feed.html interpolated Community.name straight into an
    inline onsubmit JS string. HTML autoescape turns ' into &#x27;, which the
    parser entity-decodes back to a live quote before the handler compiles as
    JS — so a community named `'+alert(1)+'` is stored XSS against any member
    who clicks "Leave this community" (CSP carries 'unsafe-inline').
#18 JoinCodeQRView authorised on role='admin' with no is_active=True, and
    leaving preserves the role. An admin who left kept serving the live join-code
    PNG — rotation by the remaining admin no longer locked them out.
#33 umi_context stamped session['hub:last_slug'] for whatever slug the resolver
    matched, with no membership check, overwriting the value HubView writes only
    after one. One authenticated GET of a foreign /c/<slug>/ (which 404s, and the
    404 page renders the nav) repointed the mobile bottom nav at four URLs that
    all 404 for that member, persistently.
#35 Moderation POST bodies fed a raw id into a UUID pk lookup; a non-UUID string
    raises django.core.exceptions.ValidationError, which get_object_or_404 does
    not catch (only DoesNotExist), so it escaped as a 500 instead of a 404.
"""

import re

import pytest
from django.test import Client
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


def _onsubmit(body):
    """The leave-form's onsubmit attribute, as the browser would receive it."""
    match = re.search(r'onsubmit="([^"]*)"', body)
    assert match, "the feed's leave form should carry an onsubmit confirm"
    return match.group(1)


# ------------------------------------------------------------------------- #7
def test_leave_confirm_escapes_community_name_for_javascript():
    """A community name that breaks out of the JS string must land escaped for
    the JS context, not merely HTML-escaped (&#x27; decodes back to a quote)."""
    community = CommunityFactory(name="'+alert(1)+'", slug="xss-community")
    member = MemberFactory(community=community, role="member")

    body = _client(member).get(reverse("community-feed", args=[community.slug])).content.decode()
    attr = _onsubmit(body)

    assert "alert(1)" in attr, "the name should still be shown to the member"
    assert "&#x27;" not in attr, "an HTML entity decodes back to a live quote inside the handler"
    assert "\\u0027" in attr, "the quote must be escaped for the JavaScript string"


# ------------------------------------------------------------------------ #18
def test_left_admin_cannot_fetch_the_join_code_qr():
    """Leaving is soft (is_active=False, role preserved) — the QR must refuse."""
    community = CommunityFactory()
    leaver = MemberFactory(community=community, role="admin")
    MemberFactory(community=community, role="admin")  # so the leaver isn't the last admin
    client = _client(leaver)

    left = client.post(reverse("community-leave", args=[community.slug]))
    assert left.status_code == 302
    leaver.refresh_from_db()
    assert leaver.is_active is False and leaver.role == "admin"

    resp = client.get(reverse("join-code-qr", args=[community.slug]))
    assert resp.status_code == 403


def test_active_admin_still_fetches_the_join_code_qr():
    """The guard must not lock out the admins who are still here."""
    community = CommunityFactory()
    admin = MemberFactory(community=community, role="admin")

    resp = _client(admin).get(reverse("join-code-qr", args=[community.slug]))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/png"


def test_join_code_qr_404s_for_an_inactive_community():
    """Parity with every sibling gate: a closed community serves nothing."""
    community = CommunityFactory(is_active=False)
    admin = MemberFactory(community=community, role="admin")

    resp = _client(admin).get(reverse("join-code-qr", args=[community.slug]))
    assert resp.status_code == 404


# ------------------------------------------------------------------------ #33
@pytest.fixture
def two_communities():
    alpha = CommunityFactory(slug="alpha-parish")
    bravo = CommunityFactory(slug="bravo-parish")
    member = MemberFactory(community=alpha, role="member")
    return alpha, bravo, member


def test_foreign_slug_does_not_repoint_the_saved_hub_slug(two_communities):
    alpha, bravo, member = two_communities
    client = _client(member)
    client.get(reverse("hub:community", args=[alpha.slug]))
    assert client.session["hub:last_slug"] == alpha.slug

    resp = client.get(reverse("community-feed", args=[bravo.slug]))
    assert resp.status_code == 404

    assert client.session["hub:last_slug"] == alpha.slug


def test_bottom_nav_on_a_foreign_page_points_at_the_members_own_community(two_communities):
    alpha, bravo, member = two_communities
    client = _client(member)
    client.get(reverse("hub:community", args=[alpha.slug]))

    body = client.get(reverse("community-feed", args=[bravo.slug])).content.decode()

    assert f"/c/{bravo.slug}/" not in body, "the nav must not offer a community they can't reach"
    assert f"/c/{alpha.slug}/" in body, "it should fall back to their own community"


def test_own_slug_still_updates_the_saved_hub_slug():
    """The fallback stays fresh for the communities a member does belong to."""
    first = CommunityFactory(slug="first-parish")
    second = CommunityFactory(slug="second-parish")
    member = MemberFactory(community=first, role="member")
    MemberFactory(community=second, user=member.user, role="member")
    client = _client(member)

    client.get(reverse("community-feed", args=[first.slug]))
    assert client.session["hub:last_slug"] == first.slug
    client.get(reverse("community-feed", args=[second.slug]))
    assert client.session["hub:last_slug"] == second.slug


# ------------------------------------------------------------------------ #35
@pytest.fixture
def moderation_world():
    community = CommunityFactory()
    member = MemberFactory(community=community, role="member")
    coordinator = MemberFactory(community=community, role="coordinator")
    return community, member, coordinator


def test_malformed_blocked_id_returns_404_not_500(moderation_world):
    community, member, _ = moderation_world
    resp = _client(member).post(reverse("moderation:block", args=[community.slug]), {"blocked_id": "junk"})
    assert resp.status_code == 404


def test_empty_blocked_id_returns_404_not_500(moderation_world):
    community, member, _ = moderation_world
    resp = _client(member).post(reverse("moderation:block", args=[community.slug]), {})
    assert resp.status_code == 404


def test_malformed_unblock_id_returns_404_not_500(moderation_world):
    community, member, _ = moderation_world
    resp = _client(member).post(reverse("moderation:unblock", args=[community.slug]), {"blocked_id": "junk"})
    assert resp.status_code == 404


def test_malformed_flag_target_id_returns_404_not_500(moderation_world):
    community, member, _ = moderation_world
    resp = _client(member).post(
        reverse("moderation:flag", args=[community.slug]),
        {"target_type": "need", "target_id": "junk", "reason": "spam", "detail": ""},
    )
    assert resp.status_code == 404


def test_malformed_reinstate_member_id_returns_404_not_500(moderation_world):
    community, _, coordinator = moderation_world
    resp = _client(coordinator).post(reverse("moderation:reinstate", args=[community.slug]), {"member_id": "junk"})
    assert resp.status_code == 404

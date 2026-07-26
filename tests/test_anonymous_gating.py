"""A signed-out visitor hitting a gated screen gets the login door, never a 500.

Regression for the settings hole: CommunitySettingsView's dispatch queried
Member with request.user before LoginRequiredMixin could act, so an
AnonymousUser reached the FK filter and blew up. The other gated screens
already guard; the parametrize keeps the whole class locked.
"""

import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory

pytestmark = pytest.mark.django_db

GATED = [
    ("community-settings", "settings"),
    ("moderation:queue", "moderation queue"),
    ("tags:queue", "tag verification queue"),
    ("pages:manage", "page manager"),
    ("community-dashboard", "coordinator dashboard"),
    ("dashboard-export", "dashboard CSV export"),
]


@pytest.mark.parametrize("url_name,label", GATED)
def test_anonymous_visitor_is_sent_to_login_not_500(client, url_name, label):
    community = CommunityFactory()
    resp = client.get(reverse(url_name, args=[community.slug]))
    assert resp.status_code == 302, f"{label}: anonymous GET must redirect, got {resp.status_code}"
    assert "/auth/login/" in resp["Location"], f"{label}: redirect must land on the login door"


@pytest.mark.parametrize("url_name,label", GATED)
def test_anonymous_visitor_cannot_tell_a_real_slug_from_a_missing_one(client, url_name, label):
    """The no-oracle rule: an existing community and a missing one must answer a
    signed-out probe identically, or the status difference enumerates which slugs
    (including private communities) exist. The dashboard broke this with a 500-vs-404
    split — its dispatch queried Member with AnonymousUser before LoginRequiredMixin
    ran, exactly the settings hole this file's docstring records."""
    CommunityFactory()  # at least one real community in the DB
    resp = client.get(reverse(url_name, args=["no-such-community"]))
    assert resp.status_code == 302, f"{label}: missing slug must answer like a real one, got {resp.status_code}"
    assert "/auth/login/" in resp["Location"]

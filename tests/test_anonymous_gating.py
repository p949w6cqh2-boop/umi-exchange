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
]


@pytest.mark.parametrize("url_name,label", GATED)
def test_anonymous_visitor_is_sent_to_login_not_500(client, url_name, label):
    community = CommunityFactory()
    resp = client.get(reverse(url_name, args=[community.slug]))
    assert resp.status_code == 302, f"{label}: anonymous GET must redirect, got {resp.status_code}"
    assert "/auth/login/" in resp["Location"], f"{label}: redirect must land on the login door"

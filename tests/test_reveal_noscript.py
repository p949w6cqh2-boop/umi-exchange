"""Design lane #4 — reveals are enhancement-only (visible without JS) and the
connect ceremony carries its peak-moment markup. The hidden state is gated on
a .js class set pre-paint, so no-JS / headless / a failed observer all show
the section. CSS behavior is verified live; here we pin the load-bearing
markup so it can't silently regress."""

import pytest
from django.test import Client
from django.urls import reverse

from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


def test_js_class_is_set_pre_paint():
    body = Client().get(reverse("landing")).content.decode()
    # the class is added in <head> before any content paints
    assert 'classList.add("js")' in body
    head = body.split("</head>")[0]
    assert 'classList.add("js")' in head


def test_reveal_script_has_the_load_failsafe():
    body = Client().get(reverse("landing")).content.decode()
    # reveals add .is-revealed (never hide), and a load-time sweep catches
    # anything an observer missed so a section can't ship blank
    assert "is-revealed" in body
    assert "revealAll" in body


def test_connect_ceremony_carries_peak_markup():
    community = CommunityFactory()
    requester = MemberFactory(community=community, role="member")
    helper = MemberFactory(community=community, role="member")
    requester.user.email = "maria@example.org"
    requester.user.save()
    need = NeedFactory(
        community=community,
        requester=requester,
        category=CategoryFactory(community=community),
        contact_pref="any",
    )
    match = MatchFactory(need=need, proposed_by=helper, offer=None, status="accepted")
    body = _login(helper).get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.pk})).content.decode()
    assert "umi-ceremony" in body
    assert "umi-ceremony__scene" in body
    assert body.count("umi-ceremony__line") >= 2
    assert "You&rsquo;re connected." in body

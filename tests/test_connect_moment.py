"""P4 — the connect moment pays off: a channel-less contact never renders as
a bare name (the 2026-07-11 rehearsal finding), and new asks default to a
reachable preference."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.needs.models import Need
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory

pytestmark = pytest.mark.django_db


def test_new_needs_default_to_reachable_contact():
    assert Need._meta.get_field("contact_pref").default == "any"


@pytest.fixture
def accepted_match():
    community = CommunityFactory()
    requester = MemberFactory(community=community, role="member")
    helper = MemberFactory(community=community, role="member")
    need = NeedFactory(
        community=community,
        requester=requester,
        category=CategoryFactory(community=community),
        contact_pref="in_app",
    )
    match = MatchFactory(need=need, proposed_by=helper, offer=None, status="accepted")
    return community, requester, helper, need, match


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


def test_channel_less_contact_gets_the_graceful_line(accepted_match):
    community, requester, helper, need, match = accepted_match
    resp = _login(helper).get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.pk}))
    body = resp.content.decode()
    assert "arrange things through the community" in body
    assert "Reach out kindly" in body


def test_contact_with_email_shows_the_email_not_the_fallback(accepted_match):
    community, requester, helper, need, match = accepted_match
    requester.user.email = "maria@example.org"
    requester.user.save()
    Need.objects.filter(pk=need.pk).update(contact_pref="any")
    resp = _login(helper).get(reverse("match-detail", kwargs={"slug": community.slug, "pk": match.pk}))
    body = resp.content.decode()
    assert "maria@example.org" in body
    assert "arrange things through the community" not in body

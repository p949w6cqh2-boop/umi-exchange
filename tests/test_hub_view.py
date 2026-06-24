import pytest
from django.urls import reverse

from tests.conftest import (
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _hub_url(community):
    return reverse("hub:community", kwargs={"slug": community.slug})


def test_renders_panels_for_member(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    need = NeedFactory(community=m.community, requester=m, title="Ride to clinic")
    MatchFactory(need=need, proposed_by=m, status="proposed")
    client.force_login(user)
    resp = client.get(_hub_url(m.community))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Ride to clinic" in body
    assert "Post a need" in body  # quick action label


def test_requires_auth(client):
    m = MemberFactory(community=CommunityFactory())
    resp = client.get(_hub_url(m.community))
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


def test_no_cross_community_match_leak(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    need_b = NeedFactory(community=b.community, requester=b, title="Secret B need")
    MatchFactory(need=need_b, proposed_by=b, status="proposed")
    client.force_login(user)
    resp = client.get(_hub_url(a.community))  # focused on A
    assert "Secret B need" not in resp.content.decode()


def test_htmx_returns_body_partial_only(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    client.force_login(user)
    resp = client.get(_hub_url(m.community), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    # HTMX gets the bare body partial: its content is present, but NOT the
    # base-template chrome nor the #hub-body wrapper (that lives in index.html,
    # whose innerHTML this partial replaces on swap).
    assert b"<html" not in resp.content
    assert b"Quick actions" in resp.content  # body partial rendered
    assert b'id="hub-body"' not in resp.content  # wrapper is in index.html, not the partial

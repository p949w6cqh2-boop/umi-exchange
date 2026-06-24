import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


def _login(client, user):
    client.force_login(user)


def test_hub_requires_auth(client):
    resp = client.get("/hub/")
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


def test_hub_community_requires_auth(client):
    community = CommunityFactory()
    resp = client.get(reverse("hub:community", kwargs={"slug": community.slug}))
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


def test_zero_memberships_redirects_to_join(client):
    user = UserFactory()
    _login(client, user)
    resp = client.get("/hub/")
    assert resp.status_code == 302
    assert resp.url == "/join/"


def test_one_membership_goes_straight_in(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    resp = client.get("/hub/")
    assert resp.status_code == 302
    assert resp.url == reverse("hub:community", kwargs={"slug": m.community.slug})


def test_many_memberships_use_last_visited(client):
    user = UserFactory()
    MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    session = client.session
    session["hub:last_slug"] = b.community.slug
    session.save()
    resp = client.get("/hub/")
    assert resp.url == reverse("hub:community", kwargs={"slug": b.community.slug})


def test_many_memberships_fallback_most_recent(client):
    user = UserFactory()
    from apps.communities.models import Member

    older = MemberFactory(user=user, community=CommunityFactory())
    newer = MemberFactory(user=user, community=CommunityFactory())
    # joined_at is auto_now_add; force a deterministic order via update()
    import datetime

    from django.utils import timezone

    Member.objects.filter(pk=older.pk).update(joined_at=timezone.now() - datetime.timedelta(days=2))
    Member.objects.filter(pk=newer.pk).update(joined_at=timezone.now())
    _login(client, user)
    resp = client.get("/hub/")
    assert resp.url == reverse("hub:community", kwargs={"slug": newer.community.slug})


def test_stale_last_slug_falls_back(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    session = client.session
    session["hub:last_slug"] = "a-community-they-left"
    session.save()
    resp = client.get("/hub/")
    assert resp.url == reverse("hub:community", kwargs={"slug": m.community.slug})


def test_hub_community_404_for_non_member(client):
    user = UserFactory()
    other = CommunityFactory()  # user is NOT a member
    _login(client, user)
    resp = client.get(reverse("hub:community", kwargs={"slug": other.slug}))
    assert resp.status_code == 404


def test_hub_community_renders_for_member(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    resp = client.get(reverse("hub:community", kwargs={"slug": m.community.slug}))
    assert resp.status_code == 200

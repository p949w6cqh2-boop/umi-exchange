"""Phase 2 "Member's Day" — the logged-in journey must look, not read:
threshold scene at join/create, hub crown, tokened notices, exchange ceremony.

Scenes are asserted via their unique grain-filter ids (g-*) because the
Parish Linocut header comments are {% comment %} blocks and never render."""

import pytest
from django.urls import reverse

from tests.conftest import (
    CommunityFactory,
    MemberFactory,
    NeedFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def homeless_client(client):
    """Logged-in user who belongs to no community yet — the threshold audience."""
    user = UserFactory()
    client.force_login(user)
    return client


@pytest.fixture
def member(db):
    return MemberFactory(user=UserFactory(), community=CommunityFactory())


@pytest.fixture
def member_client(client, member):
    client.force_login(member.user)
    return client


class TestHubCrown:
    def test_hub_masthead_carries_well_wash(self, member_client, member):
        body = member_client.get(
            reverse("hub:community", kwargs={"slug": member.community.slug})
        ).content.decode()
        assert 'id="g-well"' in body

    def test_hub_empty_pulse_shows_vignette_not_bare_text(self, member_client, member):
        # A fresh member IS a pulse event (member_joined) — backdate the join
        # past the pulse window so the empty branch actually renders.
        from datetime import timedelta

        from django.utils import timezone

        type(member).objects.filter(pk=member.pk).update(
            joined_at=timezone.now() - timedelta(days=90)
        )
        body = member_client.get(
            reverse("hub:pulse", kwargs={"slug": member.community.slug})
        ).content.decode()
        assert "umi-vignette" in body  # quiet community → empty-state branch

    def test_hub_empty_spotlight_shows_vignette(self, member_client, member):
        body = member_client.get(
            reverse("hub:community", kwargs={"slug": member.community.slug})
        ).content.decode()
        assert 'id="g-carry"' in body  # no open needs → spotlight empty state


class TestThreshold:
    def test_join_page_carries_threshold_scene(self, homeless_client):
        body = homeless_client.get(reverse("community-join")).content.decode()
        assert 'id="g-thresh"' in body

    def test_create_page_carries_threshold_scene(self, homeless_client):
        body = homeless_client.get(reverse("community-create")).content.decode()
        assert 'id="g-thresh"' in body

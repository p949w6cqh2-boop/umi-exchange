"""
Stage 4 — Django admin registration for Tag + MemberTag.

Coordinators/admins manage the tag catalog and review the verification queue
through the Django admin. These tests assert the models are registered and the
changelists actually load (which catches a misconfigured list_display /
list_filter — those 500 on render) and are queue-aware (filterable by status).
"""

import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse

from apps.tags.models import MemberTag, Tag

from .conftest import CommunityFactory, MemberFactory, UserFactory


@pytest.fixture
def community(db):
    return CommunityFactory()


@pytest.fixture
def admin_client(db):
    user = UserFactory()
    user.is_staff = True
    user.is_superuser = True
    user.save()
    c = Client()
    c.force_login(user)
    return c


class TestTagsAdmin:
    def test_tag_is_registered(self):
        assert admin.site.is_registered(Tag)

    def test_membertag_is_registered(self):
        assert admin.site.is_registered(MemberTag)

    def test_tag_changelist_loads(self, admin_client, community):
        # 13 default tags are seeded for the community
        resp = admin_client.get(reverse("admin:tags_tag_changelist"))
        assert resp.status_code == 200

    def test_membertag_changelist_loads(self, admin_client, community):
        member = MemberFactory(community=community)
        tag = Tag.objects.get(community=community, slug="svdp-member")
        MemberTag.objects.create(member=member, tag=tag, status="pending")
        resp = admin_client.get(reverse("admin:tags_membertag_changelist"))
        assert resp.status_code == 200

    def test_membertag_is_queue_aware_filter_by_status(self, admin_client, community):
        member = MemberFactory(community=community)
        tag = Tag.objects.get(community=community, slug="svdp-member")
        MemberTag.objects.create(member=member, tag=tag, status="pending")
        resp = admin_client.get(reverse("admin:tags_membertag_changelist") + "?status=pending")
        assert resp.status_code == 200

    def test_membertag_admin_filters_include_status_and_tier(self):
        ma = admin.site._registry[MemberTag]
        assert "status" in ma.list_filter
        assert "tag__tier" in ma.list_filter

    def test_tag_admin_filters_include_tier_and_active(self):
        ma = admin.site._registry[Tag]
        assert "tier" in ma.list_filter
        assert "is_active" in ma.list_filter

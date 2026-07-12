"""P6 — the resources directory: coordinator-curated help beyond the board.
Members read, coordinators add and archive (never delete), everything
community-scoped and audited."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.communities.models import Resource
from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    community = CommunityFactory()
    coordinator = MemberFactory(community=community, role="coordinator")
    member = MemberFactory(community=community, role="member")
    return community, coordinator, member


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


def _url(community):
    return reverse("community-resources", kwargs={"slug": community.slug})


def test_member_sees_the_directory_grouped(world):
    community, coordinator, member = world
    Resource.objects.create(
        community=community,
        title="County legal aid",
        url="https://legal.example",
        category="legal",
        added_by=coordinator,
        blurb="Free consults Tuesdays.",
    )
    resp = _login(member).get(_url(community))
    assert resp.status_code == 200
    assert b"County legal aid" in resp.content
    assert b"Legal aid" in resp.content
    assert b"Free consults Tuesdays." in resp.content


def test_foreign_member_cannot_see_it(world):
    community, coordinator, member = world
    outsider = MemberFactory(community=CommunityFactory(), role="member")
    assert _login(outsider).get(_url(community)).status_code == 404


def test_coordinator_adds_a_resource_audited(world):
    community, coordinator, member = world
    resp = _login(coordinator).post(
        _url(community),
        {
            "action": "add",
            "title": "Food pantry",
            "url": "https://pantry.example",
            "category": "food",
            "blurb": "Wednesdays 4-6.",
        },
    )
    assert resp.status_code == 302
    resource = Resource.objects.get(title="Food pantry")
    assert resource.community == community and resource.is_active
    assert AuditLog.objects.filter(action="resource.added", resource_id=resource.pk).exists()


def test_plain_member_cannot_curate(world):
    community, coordinator, member = world
    resp = _login(member).post(
        _url(community), {"action": "add", "title": "X", "url": "https://x.example", "category": "other"}
    )
    assert resp.status_code == 403
    assert Resource.objects.count() == 0


def test_bad_url_is_refused(world):
    community, coordinator, member = world
    _login(coordinator).post(
        _url(community), {"action": "add", "title": "Nope", "url": "javascript:alert(1)", "category": "other"}
    )
    assert Resource.objects.count() == 0


def test_archive_hides_but_keeps_the_row(world):
    community, coordinator, member = world
    resource = Resource.objects.create(
        community=community,
        title="Old link",
        url="https://old.example",
        category="other",
        added_by=coordinator,
    )
    _login(coordinator).post(_url(community), {"action": "archive", "resource_id": resource.pk})
    resource.refresh_from_db()
    assert resource.is_active is False
    assert b"Old link" not in _login(member).get(_url(community)).content
    assert AuditLog.objects.filter(action="resource.archived", resource_id=resource.pk).exists()

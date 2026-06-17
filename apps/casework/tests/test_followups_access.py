"""8.3: MyFollowUpsView must re-gate by current case access.

A follow-up assigned to a member is not, by itself, authorization to see the
case behind it — access can be revoked or expire after assignment. The "my
follow-ups" list must therefore drop any follow-up whose case the member can
no longer access.
"""

import datetime

import pytest
from django.utils import timezone

from apps.casework.models import FollowUp


@pytest.mark.django_db
def test_followups_mine_hides_cases_member_cannot_access(world, auth, u):
    # Assign an open follow-up on a standard case to a plain member who has no
    # access to that case (not assignee/opener, not a coordinator, no grant).
    FollowUp.objects.create(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.plain,
        title="Check in re: utility bill",
        due_date=timezone.localdate() + datetime.timedelta(days=1),
        status="open",
    )

    client = auth(world.plain_u)
    resp = client.get(u("followups-mine"))
    assert resp.status_code == 200
    # The follow-up is assigned to them, but they have no case access → excluded.
    assert list(resp.context["items"]) == []


@pytest.mark.django_db
def test_followups_mine_shows_accessible_cases(world, auth, u):
    # Same follow-up, but assigned to the case's own coordinator (who has access).
    fu = FollowUp.objects.create(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="Check in re: utility bill",
        due_date=timezone.localdate() + datetime.timedelta(days=1),
        status="open",
    )

    client = auth(world.coord_u)
    resp = client.get(u("followups-mine"))
    assert resp.status_code == 200
    assert [x.id for x in resp.context["items"]] == [fu.id]

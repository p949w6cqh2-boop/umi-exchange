"""M-5 regression: the offline visit manifest is reauth-exempt, so it must not
let a coordinator enumerate the whole community caseload. It should list only
cases the member has a concrete tie to — assigned, opened, or an active
contributor grant — not every standard-sensitivity case in the community."""

import pytest

from apps.casework.models import CaseAccessGrant, CaseFile

pytestmark = pytest.mark.django_db


def _standard_case_owned_by(world, member):
    return CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=member,
        assigned_to=member,
        consent=world.consent,
        sensitivity="standard",
    )


def test_manifest_excludes_community_case_without_tie(world, auth, u):
    # A standard case owned entirely by another coordinator; the requester has
    # no assignment, did not open it, holds no grant. Pre-fix, the community-wide
    # "all standard cases" rule leaked it into the manifest.
    other_case = _standard_case_owned_by(world, world.coordinator2)

    resp = auth(world.coord_u).get(u("visit-manifest"))
    codes = {c["code"] for c in resp.json()["cases"]}

    assert world.case.short_code in codes  # assigned to the requester → present
    assert other_case.short_code not in codes  # no tie → absent


def test_manifest_includes_case_with_active_grant(world, auth, u):
    # The fix must not over-restrict: an explicit contributor grant still counts.
    other_case = _standard_case_owned_by(world, world.coordinator2)
    CaseAccessGrant.objects.create(
        case=other_case,
        member=world.coordinator,
        role="contributor",
        granted_by=world.admin,
        reason="covering shift",
    )

    resp = auth(world.coord_u).get(u("visit-manifest"))
    codes = {c["code"] for c in resp.json()["cases"]}

    assert other_case.short_code in codes  # granted → present

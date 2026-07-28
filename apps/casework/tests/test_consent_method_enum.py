"""
Every consent method the intake form offers must be a value the Consent model
allows. The bug (flagged in PR #120's commit): the form offered "paper" while
Consent.METHOD_CHOICES allows verbal/written/digital, and `objects.create()`
never calls full_clean() — so a coordinator picking "Paper (filed)" stored an
invalid enum inside the consent instrument itself.
"""

import pytest
from django.utils import timezone

from apps.casework.forms import CaseCreateForm
from apps.consent.models import Consent

pytestmark = pytest.mark.django_db

VALID_METHODS = {value for value, _ in Consent.METHOD_CHOICES}
OFFERED = [value for value, _ in CaseCreateForm.base_fields["record_method"].choices]


def test_every_offered_record_method_is_a_valid_consent_method():
    assert set(OFFERED) <= VALID_METHODS, (
        f"the intake form offers {sorted(set(OFFERED) - VALID_METHODS)}, "
        "which Consent.METHOD_CHOICES does not allow — objects.create() will "
        "store it unvalidated"
    )


@pytest.mark.parametrize("method", OFFERED)
def test_recorded_consent_stores_a_valid_method(world, auth, u, method):
    """Whatever option the coordinator picks, the stored instrument must carry
    a method the model actually allows."""
    client = auth(world.coord_u)
    resp = client.post(
        u("create"),
        {
            "new_person_name": "Padraig Byrne",
            "consent_mode": "record",
            "record_method": method,
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
        },
    )
    assert resp.status_code == 302, "the intake must succeed, or this proves nothing"
    consent = Consent.objects.latest("granted_at")
    assert consent.method == method
    assert consent.method in VALID_METHODS

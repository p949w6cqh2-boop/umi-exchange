"""Threat-model must-fix #4 (Jasiah Williams's go, 2026-07-11): a case that nobody
explicitly classifies must land RESTRICTED, not standard — coordinators read
all standard-case PII by design, so the unsafe default was the leak."""

from apps.casework.forms import CaseCreateForm
from apps.casework.models import CaseFile


def test_unclassified_case_defaults_to_restricted(world):
    case = CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        consent=world.consent,
    )
    assert case.sensitivity == CaseFile.SENS_RESTRICTED


def test_intake_form_preselects_restricted():
    assert CaseCreateForm.base_fields["sensitivity"].initial == "restricted"

"""
Recording consent on a case opened in an emergency (the founder's call, 2026-10-13, bug hunt L26).

The emergency path opens a case with no consent (a database constraint allows a null consent only
under the emergency flag), and the spec says consent MUST then be regularized (§3.7-3.8). The case
page asked for it ("Regularize consent as soon as possible") but nothing in the product could do
it, so an emergency case stayed outside the §3.6 freeze for good: a person who later withdrew their
consent could not stop new notes on it. Now an admin, or the coordinator handling the case, records
the consent from the case page with the same choices as opening a case: the person's own digital
consent, or verbal or paper consent written down against them. From then on the freeze applies.
"""

import pytest

from apps.audit.models import AuditLog
from apps.casework.models import CaseFile
from apps.consent.models import Consent

pytestmark = pytest.mark.django_db

NOTE = {"kind": "visit", "occurred_at": "2026-10-12T10:00", "location_kind": "home", "body": "Visit."}


@pytest.fixture
def emergency(world):
    case = CaseFile(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        sensitivity=CaseFile.SENS_STANDARD,
        consent=None,
        emergency_opened=True,
    )
    case.emergency_justification = "At the door at night, no time for paperwork."
    case.save()
    return case


def test_the_case_page_offers_the_form_to_whoever_can_record_it(world, emergency, auth, u):
    page = auth(world.coord_u).get(u("detail", pk=emergency.pk)).content.decode()
    assert u("consent", pk=emergency.pk) in page

    other = auth(world.coord2_u).get(u("detail", pk=emergency.pk)).content.decode()
    assert u("consent", pk=emergency.pk) not in other  # can read the case, can't record its consent
    assert "An admin or the coordinator handling this case can record it." in other


def test_the_assignee_attaches_the_persons_own_digital_consent(world, emergency, auth, u):
    r = auth(world.coord_u).post(
        u("consent", pk=emergency.pk), {"consent_mode": "existing", "existing_consent": str(world.consent.pk)}
    )
    assert r.status_code == 302
    emergency.refresh_from_db()
    assert emergency.consent_id == world.consent.pk
    assert emergency.emergency_opened is True  # how it was opened stays on record
    row = AuditLog.objects.get(action="case.consent_recorded", resource_id=emergency.pk)
    assert row.details == {"mode": "existing"}


def test_an_admin_writes_down_verbal_consent_against_the_person(world, emergency, auth, u):
    world.person.linked_user = None
    world.person.save(update_fields=["linked_user"])
    r = auth(world.admin_u).post(
        u("consent", pk=emergency.pk), {"consent_mode": "record", "record_method": "verbal", "include_export": "on"}
    )
    assert r.status_code == 302
    emergency.refresh_from_db()
    consent = emergency.consent
    assert consent.subject_person_id == world.person.pk and consent.participant_id is None
    assert consent.recorded_by_id == world.admin.pk  # the witness, never the grantor
    assert consent.method == "verbal"
    assert consent.scope == ["case_records", "case_export"]
    assert AuditLog.objects.get(action="case.consent_recorded").details == {"mode": "record", "method": "verbal"}


def test_once_recorded_a_withdrawal_freezes_the_case(world, emergency, auth, u):
    auth(world.coord_u).post(
        u("consent", pk=emergency.pk), {"consent_mode": "existing", "existing_consent": str(world.consent.pk)}
    )
    Consent.objects.filter(pk=world.consent.pk).update(status="revoked")

    r = auth(world.coord_u).post(u("note-create", pk=emergency.pk), NOTE)
    assert r.status_code == 403
    assert emergency.notes.count() == 0


@pytest.mark.parametrize("who", ["coord2_u", "plain_u"])
def test_nobody_else_can_record_it(world, emergency, auth, u, who):
    r = auth(getattr(world, who)).post(
        u("consent", pk=emergency.pk), {"consent_mode": "existing", "existing_consent": str(world.consent.pk)}
    )
    assert r.status_code == 403
    emergency.refresh_from_db()
    assert emergency.consent_id is None


def test_a_case_that_has_its_consent_is_refused(world, auth, u):
    r = auth(world.admin_u).post(u("consent", pk=world.case.pk), {"consent_mode": "record", "record_method": "verbal"})
    assert r.status_code == 409
    world.case.refresh_from_db()
    assert world.case.consent_id == world.consent.pk


def test_the_same_checks_as_opening_a_case(world, emergency, auth, u):
    c = auth(world.coord_u)
    # Someone else's consent, a missing method, and the emergency choice itself are each refused.
    stranger = Consent.objects.create(
        participant=world.plain_u,
        granted_to=world.community.name,
        scope=["case_records"],
        purpose="Casework tests",
        method="digital",
    )
    r = c.post(u("consent", pk=emergency.pk), {"consent_mode": "existing", "existing_consent": str(stranger.pk)})
    assert r.status_code == 400  # only the person's own consents are offered
    r = c.post(u("consent", pk=emergency.pk), {"consent_mode": "record"})
    assert r.status_code == 400
    assert "How was consent given?" in r.content.decode()
    r = c.post(u("consent", pk=emergency.pk), {"consent_mode": "emergency"})
    assert r.status_code == 400
    emergency.refresh_from_db()
    assert emergency.consent_id is None

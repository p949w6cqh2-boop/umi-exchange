"""
The on-behalf-of third party (ethics gate box 5, docs/ethics-and-safety.md:217-223).

Every Person a coordinator records has no account — `Person.linked_user` is never
assigned anywhere in production code — so every casework subject is a third party
who never agreed to any of this. Three things were wrong:

1. `Consent.participant` was a hard User FK, so a non-user could not be the grantor.
   Intake put the COORDINATOR in as participant, which is the exact thing the
   project's own protocol forbids (docs/protocol/spec.md §4.1: "Coordinators MUST
   NOT consent on a member's behalf"). The subject could never see or revoke it.
2. The `custom["on_behalf_person_id"]` breadcrumb was written and read nowhere.
3. The full decrypted legal name of that non-consenting person was the case page
   heading, while every list correctly used initials.

The fix takes both routes the gate allows: record the consent honestly against the
person it is about, AND keep what is shown minimal until such a record exists.
"""

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.casework import access
from apps.casework.models import CaseFile
from apps.consent.models import Consent
from apps.people.models import Person

pytestmark = pytest.mark.django_db


def _stranger(world, name="Bernadette Okonkwo"):
    """A person with no account — which is every person the app actually records."""
    person = Person(created_in_community=world.community, created_by=world.coordinator)
    person.display_name = name
    person.save()
    return person


def _case_for(world, person, **over):
    fields = {
        "community": world.community,
        "subject_person": person,
        "opened_by": world.coordinator,
        "assigned_to": world.coordinator,
        "sensitivity": CaseFile.SENS_STANDARD,
        # no consent yet; the model constraint requires one or the other
        "emergency_opened": True,
    }
    fields.update(over)
    return CaseFile.objects.create(**fields)


# ---------------------------------------------------------------- the model
def test_a_consent_can_name_a_person_who_has_no_account(world):
    person = _stranger(world)

    consent = Consent.objects.create(
        subject_person=person,
        recorded_by=world.coordinator,
        granted_to=world.community.name,
        grantee_type="community",
        grantee_id=world.community.id,
        scope=["case_records"],
        purpose="Case records",
        method="verbal",
    )

    assert consent.participant_id is None
    assert consent.subject_person_id == person.id
    assert consent.recorded_by_id == world.coordinator.id
    assert consent.is_currently_active()


def test_a_consent_cannot_name_both_a_user_and_a_person(world):
    """Exactly one grantor. Both set means we do not know whose consent this is."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Consent.objects.create(
            participant=world.subject_u,
            subject_person=_stranger(world),
            granted_to=world.community.name,
            purpose="Case records",
        )


def test_a_consent_must_name_someone(world):
    with pytest.raises(IntegrityError), transaction.atomic():
        Consent.objects.create(granted_to=world.community.name, purpose="Case records")


def test_subject_label_never_leaks_the_decrypted_name(world):
    person = _stranger(world, name="Bernadette Okonkwo")
    consent = Consent.objects.create(
        subject_person=person,
        recorded_by=world.coordinator,
        granted_to=world.community.name,
        purpose="Case records",
    )

    assert "Bernadette" not in consent.subject_label
    assert consent.subject_label == person.initials


# --------------------------------------------------------------- the intake
def test_intake_never_records_the_coordinator_as_the_grantor(world, auth, u):
    """The §4.1 regression. A coordinator writing down what a neighbour told them
    is a witness, not the person consenting."""
    client = auth(world.coord_u)

    resp = client.post(
        u("create"),
        {
            "new_person_name": "Bernadette Okonkwo",
            "new_person_contact": "555-0142",
            "consent_mode": "record",
            "record_method": "verbal",
            "summary": "Needs help with a utility bill.",
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
        },
    )

    assert resp.status_code == 302, "the intake must succeed, or this test proves nothing"
    consent = Consent.objects.latest("granted_at")
    assert consent.participant_id is None, "the coordinator must not stand in as the grantor"
    assert consent.participant_id != world.coord_u.id
    assert consent.subject_person is not None
    assert consent.recorded_by_id == world.coordinator.id, "but we do record who wrote it down"
    assert consent.method == "verbal", "the verbal instrument is what actually happened"


def test_intake_still_names_a_real_user_when_the_subject_has_an_account(world, auth, u):
    """The correct path stays correct: someone with an account consents for themselves."""
    client = auth(world.coord_u)

    resp = client.post(
        u("create"),
        {
            "person": str(world.person.id),
            "consent_mode": "record",
            # the intake form offers only verbal/paper — "digital" is reserved for
            # a person acting for themselves, which a coordinator cannot do.
            "record_method": "verbal",
            "summary": "Follow-up.",
            "sensitivity": "standard",
            "intake_date": timezone.localdate().isoformat(),
        },
    )

    assert resp.status_code == 302
    consent = Consent.objects.latest("granted_at")
    assert consent.participant_id == world.subject_u.id
    assert consent.subject_person_id is None


# -------------------------------------------------------------- the display
def test_a_case_shows_only_initials_until_the_subject_has_spoken(world, auth, u):
    person = _stranger(world, name="Bernadette Okonkwo")
    case = _case_for(world, person)

    body = auth(world.coord_u).get(u("detail", pk=case.pk)).content.decode()

    assert "Bernadette Okonkwo" not in body, "a name nobody consented to is not a page heading"
    assert person.initials in body
    assert "has not been asked" in body, "and the page says plainly why the name is short"


def test_a_case_shows_the_full_name_once_consent_names_that_person(world, auth, u):
    person = _stranger(world, name="Bernadette Okonkwo")
    consent = Consent.objects.create(
        subject_person=person,
        recorded_by=world.coordinator,
        granted_to=world.community.name,
        grantee_type="community",
        grantee_id=world.community.id,
        scope=["case_records"],
        purpose="Case records",
        method="verbal",
    )
    case = _case_for(world, person, consent=consent, emergency_opened=False)

    body = auth(world.coord_u).get(u("detail", pk=case.pk)).content.decode()

    assert "Bernadette Okonkwo" in body
    assert "has not been asked" not in body


def test_a_revoked_consent_takes_the_name_back_down(world, auth, u):
    """Consent withdrawn is consent gone — the display must follow, not lag."""
    person = _stranger(world, name="Bernadette Okonkwo")
    consent = Consent.objects.create(
        subject_person=person,
        recorded_by=world.coordinator,
        granted_to=world.community.name,
        scope=["case_records"],
        purpose="Case records",
        method="verbal",
    )
    case = _case_for(world, person, consent=consent, emergency_opened=False)
    consent.status = "revoked"
    consent.revoked_at = timezone.now()
    consent.save(update_fields=["status", "revoked_at"])

    body = auth(world.coord_u).get(u("detail", pk=case.pk)).content.decode()

    assert "Bernadette Okonkwo" not in body


def test_a_linked_user_is_shown_by_name(world, auth, u):
    """Someone with an account speaks for themselves; nothing is withheld."""
    case = _case_for(world, world.person, consent=world.consent, emergency_opened=False)

    body = auth(world.coord_u).get(u("detail", pk=case.pk)).content.decode()

    assert "Maria Garcia" in body


# ------------------------------------------------------- the recorder can act
def _recorded_consent(world):
    return Consent.objects.create(
        subject_person=_stranger(world),
        recorded_by=world.coordinator,
        granted_to=world.community.name,
        grantee_type="community",
        grantee_id=world.community.id,
        scope=["case_records"],
        purpose="Case records",
        method="verbal",
    )


def test_the_coordinator_who_recorded_a_consent_can_see_it(world, auth):
    """It names nobody with an account, so without this it appears in no list at
    all — a consent no one can find is a consent no one can withdraw."""
    consent = _recorded_consent(world)

    body = auth(world.coord_u).get("/consent/").content.decode()

    assert str(consent.id)[:8] in body or consent.subject_person.initials in body


def test_the_recorder_can_withdraw_it_on_their_behalf(world, auth):
    consent = _recorded_consent(world)

    resp = auth(world.coord_u).post(f"/consent/{consent.id}/revoke/")

    assert resp.status_code == 302
    consent.refresh_from_db()
    assert consent.status == "revoked"
    assert not consent.is_currently_active()


def test_a_stranger_cannot_withdraw_someone_elses_recorded_consent(world, auth):
    consent = _recorded_consent(world)

    resp = auth(world.plain_u).post(f"/consent/{consent.id}/revoke/")

    assert resp.status_code == 404
    consent.refresh_from_db()
    assert consent.status == "active"


def test_subject_display_is_the_single_judgement(world):
    """The rule lives in access.py with the rest of the authorization matrix."""
    stranger = _stranger(world, name="Bernadette Okonkwo")
    limited = access.subject_display(_case_for(world, stranger))

    assert limited["limited"] is True
    assert "Bernadette" not in limited["label"]

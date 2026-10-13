"""2026-10 bug hunt, casework access (four findings, each red before its fix).

1. The open-case form listed every Person in the community, so a coordinator locked out of a
   restricted case could pick its subject, open a standard case on them and read the name.
2. The case list showed the full decrypted name where subject_display() allows only initials.
3. A revoked consent froze notes, follow-ups and handoffs, but access grants could still be
   added, widening who can read a case the subject has withdrawn from.
4. A follow-up could be assigned to a member with no access to the case: they were notified
   with its title and could never open, complete or bump it.
"""

from datetime import date

from django.utils import timezone

from apps.casework.models import CaseAccessGrant, CaseFile, FollowUp
from apps.notifications.models import Notification
from apps.people.models import Person


def _person(world, name, by):
    p = Person(created_in_community=world.community, created_by=by)
    p.display_name = name
    p.save()
    return p


def _restricted_case_by_admin(world, name="Dana Survivor"):
    person = _person(world, name, world.admin)
    case = CaseFile.objects.create(
        community=world.community,
        subject_person=person,
        opened_by=world.admin,
        assigned_to=world.admin,
        sensitivity=CaseFile.SENS_RESTRICTED,
        emergency_opened=True,
    )
    return person, case


# ── 1. The open-case form only offers people the opener may already see ──


def test_person_picker_hides_the_subject_of_a_restricted_case_the_opener_cannot_open(world, auth, u):
    person, case = _restricted_case_by_admin(world)
    client = auth(world.coord2_u)
    assert client.get(u("detail", pk=case.pk)).status_code == 403

    resp = client.get(u("create"))
    assert resp.status_code == 200
    assert person.pk not in set(resp.context["form"].fields["person"].queryset.values_list("pk", flat=True))
    # world.person's only case is standard, so it stays selectable for a coordinator.
    assert world.person.pk in set(resp.context["form"].fields["person"].queryset.values_list("pk", flat=True))


def test_a_handcrafted_post_cannot_open_a_case_on_that_person(world, auth, u):
    person, _ = _restricted_case_by_admin(world)
    client = auth(world.coord2_u)
    before = CaseFile.objects.count()

    resp = client.post(
        u("create"),
        {
            "person": str(person.pk),
            "sensitivity": "standard",
            "intake_date": date.today().isoformat(),
            "consent_mode": "emergency",
            "emergency_justification": "Needs help tonight, will regularize.",
        },
    )

    assert CaseFile.objects.count() == before
    assert b"Dana Survivor" not in resp.content


def test_an_admin_still_sees_every_person(world, auth, u):
    person, _ = _restricted_case_by_admin(world)
    resp = auth(world.admin_u).get(u("create"))
    assert person.pk in set(resp.context["form"].fields["person"].queryset.values_list("pk", flat=True))


# ── 2. The case list shows what subject_display allows ──


def test_case_list_shows_initials_for_a_subject_who_has_not_spoken_for_themselves(world, auth, u):
    person = _person(world, "Rosa Delgado", world.coordinator)
    CaseFile.objects.create(
        community=world.community,
        subject_person=person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        sensitivity=CaseFile.SENS_STANDARD,
        emergency_opened=True,
    )
    resp = auth(world.coord_u).get(u("list"))
    assert resp.status_code == 200
    assert b"Rosa Delgado" not in resp.content
    assert person.initials.encode() in resp.content
    # A subject who holds the account speaks for themselves: full name stays.
    assert b"Maria Garcia" in resp.content


# ── 3. No new access while consent is revoked ──


def _revoke(consent):
    consent.status = "revoked"
    consent.revoked_at = timezone.now()
    consent.save()


def test_no_access_grant_while_consent_is_revoked(world, auth, u):
    _revoke(world.consent)
    for user in (world.coord_u, world.admin_u):  # the assignee, then an admin
        resp = auth(user).post(
            u("grant-create", pk=world.case.pk),
            {"member": str(world.plain.pk), "role": "viewer", "reason": "Helping with the visit"},
        )
        assert resp.status_code == 403
    assert not CaseAccessGrant.objects.filter(case=world.case).exists()


# ── 4. A follow-up goes only to someone who can open the case ──


def _restricted_case_for_coordinator(world):
    world.case.sensitivity = CaseFile.SENS_RESTRICTED
    world.case.save(update_fields=["sensitivity"])
    return world.case


def _followup(client, u, case, assignee):
    return client.post(
        u("followup-create", pk=case.pk),
        {"title": "Check in re: utility bill", "due_date": date.today().isoformat(), "assigned_to": str(assignee.pk)},
    )


def test_follow_up_cannot_go_to_a_member_without_case_access(world, auth, u):
    case = _restricted_case_for_coordinator(world)
    client = auth(world.coord_u)

    resp = _followup(client, u, case, world.coordinator2)

    assert resp.status_code == 400
    assert not FollowUp.objects.filter(case=case).exists()
    assert not Notification.objects.filter(recipient=world.coord2_u, type="followup_assigned").exists()


def test_follow_up_reaches_them_once_access_is_granted(world, auth, u):
    case = _restricted_case_for_coordinator(world)
    CaseAccessGrant.objects.create(
        case=case, member=world.coordinator2, role="viewer", granted_by=world.coordinator, reason="Covering visits"
    )
    resp = _followup(auth(world.coord_u), u, case, world.coordinator2)
    assert resp.status_code in (200, 302)
    assert FollowUp.objects.filter(case=case, assigned_to=world.coordinator2).exists()

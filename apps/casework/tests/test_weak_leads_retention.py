"""2026-10 bug hunt, weaker leads: retention and erasure (L15, L16, L17, L27), verified and fixed.

L16  A Person was never shredded. The privacy page promises crypto-shred on request, but no command
     erased one, the 7-year sweep left the subject's name, contact and date of birth (and the name's
     blind index) in place, and the runbook's advice, "delete the record's *_enc_dek", left
     ciphertext without a key: a 500 on the case page, with the erased name still equality-testable.
     Now `shred_person` erases one person and every case about them, and the sweep erases a subject
     once their last case ages out. Both honour legal holds.
L15  The one-year need sweep only matched envelope rows, so a legacy direct-KEK on-behalf name
     (ciphertext, no DEK) was never shredded.
L17  A grant's reason is plain text, and it was copied into the grantee's notification and never
     shredded; nor were follow-up titles or the notifications that repeat them. The form now asks
     for no names or circumstances, the notification leaves the reason out, and a shred blanks them.
L27  One DEK that could not be re-wrapped aborted rotate_keks, leaving every later row under the
     old key with nothing naming the row. Now the run goes on, names each row it could not rotate,
     and fails at the end so the old key is not retired.
"""

import uuid
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.conf import settings as dj_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.casework.models import CaseAccessGrant, CaseFile, CaseNote, FollowUp, WarmHandoff
from apps.casework.tasks import CASE_RETENTION_DAYS, ERASED, shred_aged_cases
from apps.holds.models import LegalHold
from apps.needs.models import Need
from apps.needs.tasks import NEED_PII_RETENTION_DAYS, shred_aged_need_pii
from apps.notifications.models import Notification
from apps.people import crypto
from apps.people.erasure import ErasureRefusedError, shred_person
from apps.people.models import Person

pytestmark = pytest.mark.django_db


def _fill(case, world):
    """Everything a case says about its subject, encrypted and plain."""
    case.summary = "Eviction hearing on the 14th"
    case.save()
    note = CaseNote(case=case, author=world.coordinator)
    note.body = "Visited Maria; the landlord changed the locks."
    note.save()
    fu = FollowUp(
        case=case,
        created_by=world.coordinator,
        assigned_to=world.coordinator2,
        title="Call Maria about the eviction hearing",
        due_date=timezone.localdate(),
    )
    fu.detail = "She prefers mornings."
    fu.save()
    ho = WarmHandoff(case=case, from_member=world.coordinator, to_member=world.coordinator2)
    ho.summary = "Maria is frightened of the landlord."
    ho.save()
    CaseAccessGrant.objects.create(
        case=case, member=world.plain, role="viewer", granted_by=world.coordinator, reason="Maria's eviction"
    )
    link = reverse("casework:detail", kwargs={"slug": world.community.slug, "pk": case.pk})
    Notification.objects.create(
        recipient=world.plain_u, type="case_grant", title="Access granted", body="Viewer access: eviction", link=link
    )
    Notification.objects.create(
        recipient=world.coord2_u,
        type="followup_assigned",
        title=f"Follow-up on case {case.short_code}",
        body="Call Maria about the eviction hearing",
        link="/followups/",
    )
    Notification.objects.create(
        recipient=world.coord2_u,
        type="followup_overdue",
        title="1 overdue follow-up(s)",
        body=f"Call Maria about the eviction hearing (case {case.short_code})",
        link="/followups/",
    )
    return note, fu, ho


def _close(case, *, days_ago=0):
    CaseFile.objects.filter(pk=case.pk).update(
        status=CaseFile.STATUS_CLOSED, closed_at=timezone.now() - timedelta(days=days_ago)
    )


def _second_case(world, **kw):
    return CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
        sensitivity=CaseFile.SENS_STANDARD,
        **kw,
    )


def _identity_gone(person):
    p = Person.objects.get(pk=person.pk)
    return (
        p.display_name_enc is None
        and p.display_name_enc_dek is None
        and p.contact_enc is None
        and p.contact_enc_dek is None
        and p.dob_enc is None
        and p.dob_enc_dek is None
        and p.name_bidx is None
    )


def _assert_case_erased(case, note, fu, ho):
    case = CaseFile.objects.get(pk=case.pk)
    assert case.summary_enc is None and case.summary_enc_dek is None
    assert CaseNote.objects.get(pk=note.pk).body_enc is None
    fu = FollowUp.objects.get(pk=fu.pk)
    assert fu.detail_enc is None and fu.title == ERASED
    assert WarmHandoff.objects.get(pk=ho.pk).summary_enc is None
    assert not CaseAccessGrant.objects.filter(case=case).exclude(reason="").exists()
    leftovers = Notification.objects.filter(body__icontains="eviction")
    assert not leftovers.exists(), list(leftovers.values_list("type", flat=True))


# ── L16: erasing one person ────────────────────────────────────


def test_shred_person_erases_the_identity_and_every_case_about_them(world, auth, u):
    world.person.dob = "1961-04-02"
    world.person.save()
    note, fu, ho = _fill(world.case, world)
    _close(world.case)

    shred_person(world.person)

    assert _identity_gone(world.person)
    assert not Person.objects.by_name("Maria Garcia", community=world.community).exists()
    _assert_case_erased(world.case, note, fu, ho)
    row = AuditLog.objects.get(action="person.shredded", resource_id=world.person.pk)
    assert row.details == {"reason": "erasure_request", "cases": 1}
    assert AuditLog.objects.filter(action="case.erasure_shredded", resource_id=world.case.pk).count() == 1
    # The case page still opens: nulling ciphertext and key together reads as nothing, not a 500.
    assert auth(world.admin_u).get(u("detail", pk=world.case.pk)).status_code == 200


def test_shred_person_also_erases_records_merged_into_theirs(world):
    _close(world.case)
    duplicate = Person(created_in_community=world.community, created_by=world.coordinator, merged_into=world.person)
    duplicate.display_name = "Maria Garcia"
    duplicate.save()

    shred_person(world.person)

    assert _identity_gone(duplicate)
    assert AuditLog.objects.filter(action="person.shredded", resource_id=duplicate.pk).exists()


def test_an_erased_person_is_not_offered_at_intake(world):
    from apps.casework.forms import CaseCreateForm

    _close(world.case)
    shred_person(world.person)
    form = CaseCreateForm(world.community, world.admin)
    assert world.person not in form.fields["person"].queryset


def test_shred_person_refuses_while_a_case_about_them_is_open(world):
    with pytest.raises(ErasureRefusedError, match=world.case.short_code):
        shred_person(world.person)
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"


@pytest.mark.parametrize("scope", ["all", "person", "case", "community"])
def test_shred_person_refuses_under_a_legal_hold(world, scope):
    _fill(world.case, world)
    _close(world.case)
    target = {"person": {"person": world.person}, "case": {"case": world.case}}.get(scope, {})
    if scope == "community":
        target = {"community": world.community}
    LegalHold.objects.create(scope=scope, reference="matter 2026-10-13", **target)

    with pytest.raises(ErasureRefusedError, match="legal hold"):
        shred_person(world.person)
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"
    assert CaseFile.objects.get(pk=world.case.pk).summary == "Eviction hearing on the 14th"
    assert not AuditLog.objects.filter(action="person.shredded").exists()


def test_the_command_erases_and_reports(world):
    _close(world.case)
    out = StringIO()
    call_command("shred_person", "--person", str(world.person.pk), stdout=out)
    assert "shredded" in out.getvalue()
    assert _identity_gone(world.person)


def test_the_command_refuses_unknown_and_held_people(world):
    with pytest.raises(CommandError, match="Unknown person"):
        call_command("shred_person", "--person", str(uuid.uuid4()))
    with pytest.raises(CommandError, match="Unknown person"):
        call_command("shred_person", "--person", "not-a-uuid")
    _close(world.case)
    LegalHold.objects.create(scope="person", person=world.person, reference="matter")
    with pytest.raises(CommandError, match="legal hold"):
        call_command("shred_person", "--person", str(world.person.pk))
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"


def test_the_runbook_no_longer_says_to_delete_a_dek_by_hand():
    runbook = (Path(dj_settings.BASE_DIR) / "docs/runbooks/key-rotation.md").read_text()
    assert "delete the record's `*_enc_dek`" not in runbook
    assert "shred_person" in runbook


# ── L16: the 7-year sweep erases the subject ───────────────────


def test_the_sweep_erases_the_subject_once_their_last_case_ages_out(world):
    _fill(world.case, world)
    _close(world.case, days_ago=CASE_RETENTION_DAYS + 1)

    shred_aged_cases()

    assert _identity_gone(world.person)
    assert AuditLog.objects.filter(action="person.retention_shredded", resource_id=world.person.pk).count() == 1
    shred_aged_cases()  # idempotent
    assert AuditLog.objects.filter(action="person.retention_shredded").count() == 1


def test_the_sweep_keeps_the_subject_while_another_case_about_them_is_live(world):
    _close(world.case, days_ago=CASE_RETENTION_DAYS + 1)
    _second_case(world)  # open
    shred_aged_cases()
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"


def test_the_sweep_keeps_the_subject_of_a_recently_closed_case(world):
    _close(world.case, days_ago=CASE_RETENTION_DAYS + 1)
    second = _second_case(world)
    _close(second, days_ago=30)
    shred_aged_cases()
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"


@pytest.mark.parametrize("scope", ["person", "community"])
def test_the_sweep_keeps_a_held_subject(world, scope):
    _close(world.case, days_ago=CASE_RETENTION_DAYS + 1)
    target = {"person": world.person} if scope == "person" else {"community": world.community}
    LegalHold.objects.create(scope=scope, reference="matter", **target)
    shred_aged_cases()
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"


# ── L15 ────────────────────────────────────────────────────────


def test_an_aged_legacy_on_behalf_name_is_shredded(world):
    from tests.conftest import CategoryFactory

    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=CategoryFactory(community=world.community),
        title="Ride to the clinic",
        urgency="medium",
        status="fulfilled",
        expires_at=timezone.now() + timedelta(days=30),
    )
    # A row written before envelope encryption: ciphertext under the KEK, no DEK.
    Need.objects.filter(pk=need.pk).update(
        on_behalf_of=crypto.encrypt_str("Rosa Diaz"),
        on_behalf_of_dek=None,
        updated_at=timezone.now() - timedelta(days=NEED_PII_RETENTION_DAYS + 1),
    )
    assert Need.objects.get(pk=need.pk).on_behalf_of_name == "Rosa Diaz"

    shred_aged_need_pii()

    assert Need.objects.get(pk=need.pk).on_behalf_of is None


# ── L17 ────────────────────────────────────────────────────────


def test_the_grant_notification_leaves_the_reason_out(world, auth, u):
    resp = auth(world.coord_u).post(
        u("grant-create", pk=world.case.pk),
        {"member": str(world.plain.pk), "role": "viewer", "reason": "Maria's eviction hearing"},
    )
    assert resp.status_code == 302
    sent = Notification.objects.get(recipient=world.plain_u, type="case_grant")
    assert "eviction" not in sent.body
    assert "viewer" in sent.body.lower()


def test_the_grant_form_asks_for_no_names(world, auth, u):
    page = auth(world.coord_u).get(u("detail", pk=world.case.pk)).content.decode()
    assert "no names or circumstances" in page


def test_the_sweep_blanks_the_plain_text_about_a_case(world):
    note, fu, ho = _fill(world.case, world)
    other = _second_case(world)
    untouched = Notification.objects.create(
        recipient=world.coord2_u,
        type="followup_assigned",
        title=f"Follow-up on case {other.short_code}",
        body="Bring the lease paperwork",
        link="/followups/",
    )
    _close(world.case, days_ago=CASE_RETENTION_DAYS + 1)

    shred_aged_cases()

    _assert_case_erased(world.case, note, fu, ho)
    assert Notification.objects.get(pk=untouched.pk).body == "Bring the lease paperwork"


def test_the_sweep_finds_a_case_whose_only_detail_is_plain_text(world):
    fu = FollowUp.objects.create(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=world.coordinator,
        title="Call Maria about the eviction hearing",
        due_date=timezone.localdate(),
    )
    _close(world.case, days_ago=CASE_RETENTION_DAYS + 1)
    shred_aged_cases()
    assert FollowUp.objects.get(pk=fu.pk).title == ERASED


# ── L27 ────────────────────────────────────────────────────────


def test_one_unwrappable_dek_does_not_strand_every_later_row(world, make_note, settings):
    old = settings.ENCRYPTION_KEY
    # A note whose DEK is wrapped under a key that is no longer configured
    # (e.g. a row restored from a dump taken before an earlier rotation).
    settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    poisoned = make_note(body="restored from an old dump")
    settings.ENCRYPTION_KEYS = []
    good = make_note(body="ordinary note")

    new = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new, old]  # runbook: the dual-read window
    out, err = StringIO(), StringIO()
    with pytest.raises(CommandError, match="1 DEK wrap"):
        call_command("rotate_keks", stdout=out, stderr=err)
    assert f"casework.CaseNote.body_enc_dek {poisoned.pk}" in err.getvalue()

    settings.ENCRYPTION_KEYS = [new]  # every other row was re-wrapped
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"
    assert CaseNote.objects.get(pk=good.pk).body == "ordinary note"


def test_a_bad_federation_row_does_not_leave_people_unrotated(world, settings):
    from apps.federation.models import FederationEvent, FederationLink, FederationPeer

    old = settings.ENCRYPTION_KEY
    peer = FederationPeer.objects.create(instance_id="zz-lead-27", jwk={}, label="Peer")
    link = FederationLink.objects.create(peer=peer, community=world.community, requested_by_us=True)
    settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]  # written under a stray key
    ev = FederationEvent(link=link, direction="out", event_uuid=uuid.uuid4(), kind="match.contact")
    ev.secret_payload = {"phone": "555-0100"}
    ev.save()
    settings.ENCRYPTION_KEYS = []

    new = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new, old]
    with pytest.raises(CommandError):
        call_command("rotate_keks", stdout=StringIO(), stderr=StringIO())

    settings.ENCRYPTION_KEYS = [new]
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"


def test_a_clean_rotation_still_succeeds(world, settings):
    old = settings.ENCRYPTION_KEY
    new = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new, old]
    out = StringIO()
    call_command("rotate_keks", stdout=out)
    assert "Total:" in out.getvalue()
    settings.ENCRYPTION_KEYS = [new]
    assert Person.objects.get(pk=world.person.pk).display_name == "Maria Garcia"

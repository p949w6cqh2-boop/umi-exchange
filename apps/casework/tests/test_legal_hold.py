"""Scoped legal hold (docs/specs/legal-hold.md; ethics gate box 4).

Before this, preserving evidence meant stopping the whole scheduler, which also suspended erasure
for everyone NOT involved. A hold now names a scope, and every automated deletion path skips only
what that scope covers. Releasing a hold lets the next run proceed.
"""

import datetime
import io

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.casework.models import CaseFile, CaseNote
from apps.casework.tasks import CASE_RETENTION_DAYS, shred_aged_cases
from apps.holds.models import LegalHold
from apps.needs.models import Need
from apps.needs.tasks import NEED_PII_RETENTION_DAYS, shred_aged_need_pii

pytestmark = pytest.mark.django_db


def _age_and_close(case, days=CASE_RETENTION_DAYS + 1):
    case.summary = "Sensitive family situation"
    case.save()
    note = CaseNote(case=case, author=case.opened_by)
    note.body = "Visited the family; details are sensitive."
    note.save()
    CaseFile.objects.filter(pk=case.pk).update(
        status=CaseFile.STATUS_CLOSED, closed_at=timezone.now() - datetime.timedelta(days=days)
    )


def _second_case(world, person=None):
    return CaseFile.objects.create(
        community=world.community,
        subject_person=person or world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
        sensitivity=CaseFile.SENS_STANDARD,
    )


def _shredded(case):
    return CaseFile.objects.get(pk=case.pk).summary_enc is None


def _hold(scope, **target):
    return LegalHold.objects.create(scope=scope, reference="matter 2026-10-01", **target)


def _aged_need(world):
    from tests.conftest import CategoryFactory

    need = Need(
        community=world.community,
        requester=world.plain,
        category=CategoryFactory(community=world.community),
        title="Ride to the clinic",
        urgency="medium",
        status="fulfilled",
        expires_at=timezone.now() + datetime.timedelta(days=30),
    )
    need.on_behalf_of_name = "Rosa Diaz"
    need.save()
    Need.objects.filter(pk=need.pk).update(
        updated_at=timezone.now() - datetime.timedelta(days=NEED_PII_RETENTION_DAYS + 1)
    )
    return need


# ── Scopes ─────────────────────────────────────────────────────


def test_a_case_hold_spares_that_case_and_only_that_case(world):
    other = _second_case(world)
    _age_and_close(world.case)
    _age_and_close(other)
    _hold(LegalHold.SCOPE_CASE, case=world.case)
    shred_aged_cases()
    assert not _shredded(world.case)
    assert _shredded(other)  # erasure continues for everyone not covered


def test_a_person_hold_spares_every_case_about_them(world):
    other = _second_case(world)
    _age_and_close(world.case)
    _age_and_close(other)
    _hold(LegalHold.SCOPE_PERSON, person=world.person)
    shred_aged_cases()
    assert not _shredded(world.case) and not _shredded(other)


def test_a_community_hold_spares_its_cases_and_needs(world):
    _age_and_close(world.case)
    need = _aged_need(world)
    _hold(LegalHold.SCOPE_COMMUNITY, community=world.community)
    shred_aged_cases()
    shred_aged_need_pii()
    need.refresh_from_db()
    assert not _shredded(world.case)
    assert need.on_behalf_of_dek is not None


def test_a_need_hold_spares_the_need_and_blocks_the_manual_erasure_command(world):
    need = _aged_need(world)
    _hold(LegalHold.SCOPE_NEED, need=need)
    shred_aged_need_pii()
    need.refresh_from_db()
    assert need.on_behalf_of_dek is not None
    with pytest.raises(CommandError, match="legal hold"):
        call_command("shred_on_behalf", "--need", str(need.pk))
    need.refresh_from_db()
    assert need.on_behalf_of_dek is not None


def test_releasing_a_hold_lets_the_next_run_proceed(world):
    _age_and_close(world.case)
    hold = _hold(LegalHold.SCOPE_CASE, case=world.case)
    shred_aged_cases()
    assert not _shredded(world.case)
    LegalHold.objects.filter(pk=hold.pk).update(released_at=timezone.now())
    shred_aged_cases()
    assert _shredded(world.case)


def test_a_hold_on_everything_stops_every_automated_deletion(world):
    from apps.federation.tasks import sweep_expired_contacts, sweep_expired_shadows, sweep_stale_event_payloads

    _age_and_close(world.case)
    need = _aged_need(world)
    _hold(LegalHold.SCOPE_ALL)
    assert "Legal hold" in shred_aged_cases()
    assert "Legal hold" in shred_aged_need_pii()
    assert sweep_expired_shadows() == 0 and sweep_expired_contacts() == 0 and sweep_stale_event_payloads() == 0
    out = io.StringIO()
    call_command("purge_recovery_credentials", "--apply", stdout=out)
    assert "Legal hold" in out.getvalue()
    need.refresh_from_db()
    assert not _shredded(world.case) and need.on_behalf_of_dek is not None


def test_with_no_hold_nothing_changes(world):
    _age_and_close(world.case)
    shred_aged_cases()
    assert _shredded(world.case)


def test_stale_drafts_in_a_held_case_are_kept(world):
    from apps.casework.tasks import discard_stale_drafts

    note = CaseNote(case=world.case, author=world.coordinator)
    note.body = "draft"
    note.save()
    CaseNote.objects.filter(pk=note.pk).update(updated_at=timezone.now() - datetime.timedelta(hours=80))
    _hold(LegalHold.SCOPE_CASE, case=world.case)
    discard_stale_drafts()
    note.refresh_from_db()
    assert note.status == CaseNote.STATUS_DRAFT


# ── The steward's command ──────────────────────────────────────


def test_place_list_release_are_audited_without_the_reference(world):
    world.admin_u.is_staff = True
    world.admin_u.save()
    out = io.StringIO()
    call_command(
        "legal_hold", "place", "--scope", "case", "--id", str(world.case.pk),
        "--reference", "Subpoena served on the parish office", "--by", world.admin_u.username, stdout=out,
    )  # fmt: skip
    hold = LegalHold.objects.get()
    assert hold.is_active and hold.case_id == world.case.pk and hold.placed_by == world.admin_u
    listing = io.StringIO()
    call_command("legal_hold", "list", stdout=listing)
    assert str(hold.id) in listing.getvalue()
    call_command("legal_hold", "release", str(hold.id), "--by", world.admin_u.username, stdout=io.StringIO())
    hold.refresh_from_db()
    assert not hold.is_active and hold.released_by == world.admin_u
    rows = AuditLog.objects.filter(action__in=["legal_hold.placed", "legal_hold.released"])
    assert rows.count() == 2
    assert all("Subpoena" not in str(r.details) for r in rows)  # the reference never enters the audit log


def test_only_staff_can_place_a_hold(world):
    with pytest.raises(CommandError, match="staff"):
        call_command(
            "legal_hold", "place", "--scope", "all", "--reference", "x", "--by", world.plain_u.username,
        )  # fmt: skip
    assert not LegalHold.objects.exists()


def test_scope_and_target_must_agree(world):
    world.admin_u.is_staff = True
    world.admin_u.save()
    with pytest.raises(CommandError):
        call_command("legal_hold", "place", "--scope", "case", "--reference", "x", "--by", world.admin_u.username)
    with pytest.raises(CommandError):
        call_command(
            "legal_hold", "place", "--scope", "all", "--id", "anything", "--reference", "x",
            "--by", world.admin_u.username,
        )  # fmt: skip


def test_the_database_refuses_a_hold_whose_target_does_not_match_its_scope(world):
    """A targetless hold would put a NULL into the hold subqueries and quietly stop erasure for
    everyone, so the database itself refuses one (review finding, 2026-10-01)."""
    from django.db import IntegrityError, transaction

    for bad in (
        {"scope": LegalHold.SCOPE_CASE},
        {"scope": LegalHold.SCOPE_ALL, "case": world.case},
        {"scope": LegalHold.SCOPE_CASE, "case": world.case, "community": world.community},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            LegalHold.objects.create(reference="x", **bad)
    assert not LegalHold.objects.exists()


def test_a_target_that_is_not_a_uuid_is_a_clean_error(world):
    world.admin_u.is_staff = True
    world.admin_u.save()
    with pytest.raises(CommandError, match="No case matches"):
        call_command(
            "legal_hold", "place", "--scope", "case", "--id", "not-a-uuid", "--reference", "x",
            "--by", world.admin_u.username,
        )  # fmt: skip
    with pytest.raises(CommandError, match="No active hold"):
        call_command("legal_hold", "release", "not-a-uuid", "--by", world.admin_u.username)


def test_admin_shows_holds_but_cannot_edit_or_delete_them(world, client):
    world.admin_u.is_staff = True
    world.admin_u.is_superuser = True
    world.admin_u.save()
    hold = _hold(LegalHold.SCOPE_ALL)
    client.force_login(world.admin_u)
    assert client.get("/admin/holds/legalhold/").status_code == 200
    assert client.get("/admin/holds/legalhold/add/").status_code == 403
    assert client.post(f"/admin/holds/legalhold/{hold.pk}/delete/", {"post": "yes"}).status_code == 403
    assert LegalHold.objects.filter(pk=hold.pk).exists()

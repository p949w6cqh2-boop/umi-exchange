"""M-6 regression: finalizing/discarding a note must re-check case_access, not
just note authorship. A contributor whose access is revoked (grant pulled or
case reclassified) between drafting and finalizing must not be able to commit
or discard the note on a stale session."""

import pytest
from django.utils import timezone

from apps.casework.models import CaseAccessGrant, CaseNote

pytestmark = pytest.mark.django_db


def _grant(world, member, *, role="contributor", revoked=False):
    return CaseAccessGrant.objects.create(
        case=world.case,
        member=member,
        role=role,
        granted_by=world.coordinator,
        reason="temporary access for test",
        revoked_at=timezone.now() if revoked else None,
    )


def test_finalize_blocked_after_case_access_revoked(world, auth, u, make_note):
    grant = _grant(world, world.plain)  # plain member gains contributor access
    note = make_note(author=world.plain, status="draft")  # ... drafts a note
    grant.revoked_at = timezone.now()  # ... then access is revoked
    grant.save(update_fields=["revoked_at"])

    resp = auth(world.plain_u).post(u("note-finalize", pk=world.case.pk, note_id=note.pk))

    assert resp.status_code == 403
    note.refresh_from_db()
    assert note.status == CaseNote.STATUS_DRAFT  # never finalized


def test_discard_blocked_after_case_access_revoked(world, auth, u, make_note):
    grant = _grant(world, world.plain)
    note = make_note(author=world.plain, status="draft")
    grant.revoked_at = timezone.now()
    grant.save(update_fields=["revoked_at"])

    resp = auth(world.plain_u).post(u("note-discard", pk=world.case.pk, note_id=note.pk))

    assert resp.status_code == 403
    note.refresh_from_db()
    assert note.status == CaseNote.STATUS_DRAFT  # never discarded (not hidden)


def test_finalize_still_works_with_active_access(world, auth, u, make_note):
    """Regression guard: the new check must not block an author who retains
    contributor access."""
    _grant(world, world.plain)
    note = make_note(author=world.plain, status="draft")

    resp = auth(world.plain_u).post(u("note-finalize", pk=world.case.pk, note_id=note.pk))

    assert resp.status_code in (200, 302)
    note.refresh_from_db()
    assert note.status == CaseNote.STATUS_FINAL

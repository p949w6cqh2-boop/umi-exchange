"""
Casework consent + access guards (bug-hunt batch 6a, #14 #15 #22).

#14 CaseAssignView.post gated only on admin-or-current-assignee. Unlike every
    other narrative-write path (note create/amend/visit/sync/follow-up all call
    _consent_frozen), it had no revocation-freeze check — yet it writes
    WarmHandoff.summary, which is envelope-encrypted subject narrative, and
    reassigns the case, widening read access. After a subject revoked consent
    (§3.6 freeze), a coordinator whose note-create was correctly 403'd could
    still push acute narrative into a new encrypted handoff.

#15 followup_overdue_digest selected overdue follow-ups purely by assigned_to —
    no case_access() re-check (both sibling views re-check, with comments) and no
    assigned_to__is_active filter — and called send_mail directly, bypassing the
    email_notifications opt-out. An assignee who left, was removed by moderation,
    or whose grant was revoked kept receiving a daily notification + email naming
    the follow-up title, due date and case short_code, with no way to stop it.

#22 CaseFileAdmin defined no has_delete_permission (every sibling ModelAdmin
    does). Admin delete drives Django's Collector: bulk SQL, no per-object
    delete()/save() guard, and only a mutable django_admin_log row. One click
    hard-deleted a case plus its finalized (immutable) notes, follow-ups,
    handoffs and grants — around the A7 immutability guard and the tamper-evident
    audit that crypto-shred rests on.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.casework.models import CaseAccessGrant, CaseFile, FollowUp, WarmHandoff
from apps.casework.tasks import followup_overdue_digest
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def _revoke_consent(world):
    world.consent.status = "revoked"
    world.consent.revoked_at = timezone.now()
    world.consent.save(update_fields=["status", "revoked_at"])


# ------------------------------------------------------------------------ #14
def test_warm_handoff_blocked_when_consent_revoked(world, auth, u):
    """The freeze is about new subject narrative. A handoff summary is exactly
    that, and it also hands a new coordinator read access."""
    _revoke_consent(world)
    client = auth(world.coord_u)

    resp = client.post(
        u("assign", pk=world.case.pk),
        {"to_member": str(world.coordinator2.pk), "summary": "She is at her sister's this week."},
    )

    assert resp.status_code == 403
    assert not WarmHandoff.objects.filter(case=world.case).exists(), "no encrypted summary may be written"
    world.case.refresh_from_db()
    assert world.case.assigned_to_id == world.coordinator.id, "and no new read access granted"


def test_warm_handoff_allowed_while_consent_is_active(world, auth, u):
    """The guard must not break the ordinary handoff."""
    client = auth(world.coord_u)

    resp = client.post(
        u("assign", pk=world.case.pk),
        {"to_member": str(world.coordinator2.pk), "summary": "She is at her sister's this week."},
    )

    assert resp.status_code == 302
    assert WarmHandoff.objects.filter(case=world.case, to_member=world.coordinator2).exists()
    world.case.refresh_from_db()
    assert world.case.assigned_to_id == world.coordinator2.id


# ------------------------------------------------------------------------ #15
def _overdue_followup(world, assignee):
    return FollowUp.objects.create(
        case=world.case,
        created_by=world.coordinator,
        assigned_to=assignee,
        title="Check in re: utility bill",
        due_date=timezone.localdate() - timedelta(days=3),
        status="open",
    )


def test_digest_skips_an_assignee_whose_grant_was_revoked(world):
    """Access is re-checked at send time, not assumed from the assignment."""
    grant = CaseAccessGrant.objects.create(
        case=world.case, member=world.plain, role="contributor", granted_by=world.admin, reason="temporary cover"
    )
    _overdue_followup(world, world.plain)
    grant.revoked_at = timezone.now()
    grant.save(update_fields=["revoked_at"])

    sent = followup_overdue_digest()

    assert sent == 0
    assert not Notification.objects.filter(recipient=world.plain_u, type="followup_overdue").exists()
    assert mail.outbox == []


def test_digest_skips_an_assignee_who_is_no_longer_an_active_member(world):
    """Left the community, or removed by moderation — either way, is_active=False."""
    _overdue_followup(world, world.coordinator2)
    world.coordinator2.is_active = False
    world.coordinator2.save(update_fields=["is_active"])

    sent = followup_overdue_digest()

    assert sent == 0
    assert not Notification.objects.filter(recipient=world.coord2_u, type="followup_overdue").exists()
    assert mail.outbox == []


def test_digest_honours_the_email_opt_out(world):
    """In-app still lands; the email does not. Consent, not surveillance."""
    _overdue_followup(world, world.coordinator)
    world.coord_u.email_notifications = False
    world.coord_u.save(update_fields=["email_notifications"])

    sent = followup_overdue_digest()

    assert sent == 1
    assert Notification.objects.filter(recipient=world.coord_u, type="followup_overdue").exists()
    assert mail.outbox == [], "an assignee who opted out of email must not be emailed"


def test_digest_still_reaches_the_assignee_who_has_access(world):
    """The guards must not silence the one justified digest."""
    _overdue_followup(world, world.coordinator)

    sent = followup_overdue_digest()

    assert sent == 1
    assert Notification.objects.filter(recipient=world.coord_u, type="followup_overdue").exists()
    assert len(mail.outbox) == 1
    assert "overdue follow-up" in mail.outbox[0].subject


# ------------------------------------------------------------------------ #22
def test_casefile_admin_delete_is_forbidden(world, client):
    """A case is closed, never destroyed — finalized notes are immutable (A7)
    and the audit trail is append-only. Admin delete honours neither."""
    from django.contrib.auth import get_user_model

    superuser = get_user_model().objects.create_superuser(
        username="root", email="root@example.test", password="pw-Str0ng!pass"
    )
    client.force_login(superuser)
    url = reverse("admin:casework_casefile_delete", args=[world.case.pk])

    assert client.get(url).status_code == 403
    assert client.post(url, {"post": "yes"}).status_code == 403
    assert CaseFile.objects.filter(pk=world.case.pk).exists()


def test_casefile_admin_change_page_offers_no_delete(world, client):
    """The button is gone too, not just the endpoint."""
    from django.contrib.auth import get_user_model

    superuser = get_user_model().objects.create_superuser(
        username="root2", email="root2@example.test", password="pw-Str0ng!pass"
    )
    client.force_login(superuser)

    body = client.get(reverse("admin:casework_casefile_change", args=[world.case.pk])).content.decode()

    # submit_line.html's link specifically — the raw_id widgets render an
    # icon-deletelink.svg on this page whatever the permission says.
    assert 'class="deletelink"' not in body

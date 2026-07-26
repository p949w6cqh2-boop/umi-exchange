"""
django-q2 tasks (design §3.6/§3.11): the one justified digest — overdue
follow-ups, daily, plaintext titles only (nothing decrypts in email).

Register once:
    python manage.py shell -c "from apps.casework.tasks import register_schedule; register_schedule()"
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from apps.audit.services import emit
from apps.common.state import TransitionConflict

from . import access
from .models import FollowUp
from .notify import notify

logger = logging.getLogger(__name__)


def followup_overdue_digest():
    """One in-app notification + one email per assignee per day, listing
    plaintext titles + due dates. Idempotent within a calendar day."""
    from apps.notifications.models import Notification

    today = timezone.localdate()
    overdue = (
        FollowUp.objects.filter(status="open", due_date__lt=today, assigned_to__is_active=True)
        .select_related("assigned_to__user", "case__community")
        .order_by("due_date")
    )
    by_assignee: dict = {}
    for fu in overdue:
        # Re-check access at send time, as both sibling views do: an assignment
        # made weeks ago is not standing authorization. A revoked or expired
        # grant, a case turned restricted, or a membership that ended (filtered
        # above) must stop the digest — otherwise someone who lost the case keeps
        # receiving its title, due date and short_code daily, with no way to stop it.
        if access.case_access(fu.assigned_to, fu.case) <= access.NONE:
            continue
        by_assignee.setdefault(fu.assigned_to, []).append(fu)

    sent = 0
    for member, items in by_assignee.items():
        user = member.user
        if Notification.objects.filter(recipient=user, type="followup_overdue", created_at__date=today).exists():
            continue  # idempotence: already digested today
        slug = items[0].case.community.slug
        link = reverse("casework:followups-mine", kwargs={"slug": slug})
        lines = [f"• {fu.title} — due {fu.due_date} (case {fu.case.short_code})" for fu in items[:20]]
        body = "\n".join(lines)
        notify(user, "followup_overdue", title=f"{len(items)} overdue follow-up(s)", body=body, link=link)
        # Honour the email opt-out, the way NotificationAdapter does on every other
        # send. Kept as a direct send_mail rather than routed through the adapter:
        # the adapter re-brands the subject "[UMI] …", and Lake 2's mail is
        # deliberately "[Case Notes]" with a plaintext-only body (§3.6 — nothing
        # decrypts in email).
        if user.email and getattr(user, "email_notifications", True):
            try:
                send_mail(
                    subject=f"[Case Notes] {len(items)} overdue follow-up(s)",
                    message=body + f"\n\nOpen your queue: {link}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception:  # email must never break the task
                logger.exception("followup digest email failed")
        sent += 1
    return sent


def discard_stale_drafts():
    """Discard case-note drafts untouched for >72h (design §3.11). Per-row via the
    state machine (draft -> discarded) so each is audited and the model's delete()
    guard is respected — never a bulk queryset.update() (skips the machine + audit).
    System event (user=None), PII-free details. Idempotent: only acts on drafts
    past the window, so re-runs are no-ops."""
    from .models import CaseNote

    cutoff = timezone.now() - timezone.timedelta(hours=72)
    stale = CaseNote.objects.filter(status=CaseNote.STATUS_DRAFT, updated_at__lt=cutoff)
    discarded = 0
    for note in stale.iterator():
        try:
            note.transition_to(CaseNote.STATUS_DISCARDED)
        except TransitionConflict:
            continue  # raced (edited/finalized meanwhile) — leave for the next run
        emit("note.draft_expired", note, user=None, details={"reason": "stale_draft_72h"})
        discarded += 1
    return f"Discarded {discarded} stale draft note(s)"


def register_schedule():
    from django_q.models import Schedule

    Schedule.objects.update_or_create(
        name="casework-shred-aged-cases",
        defaults={
            "func": "apps.casework.tasks.shred_aged_cases",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="casework-followup-digest",
        defaults={
            "func": "apps.casework.tasks.followup_overdue_digest",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )
    Schedule.objects.update_or_create(
        name="casework-stale-draft-cleanup",
        defaults={
            "func": "apps.casework.tasks.discard_stale_drafts",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )


# Retention policy (Jasiah Williams's yes, 2026-07-11): closed cases keep their
# encrypted narrative for seven years, then it is crypto-shredded.
CASE_RETENTION_DAYS = 7 * 365


def shred_aged_cases():
    """Crypto-shred the narrative of cases closed more than seven years ago.

    Nulls BOTH envelope columns (ciphertext + DEK) on the case summary, the
    emergency justification, and every note/follow-up/handoff body, so reads
    return None and `casework_envelope_status` stays clean. Bulk `.update()`
    is deliberate: finalized notes block `save()` edits by design, and this
    is a policy action, not an edit — one audit row per case (PII-free
    counts), not per note. Idempotent: a fully shredded case no longer
    matches the content filter.
    """
    from datetime import timedelta

    from django.db.models import Q

    from .models import CaseFile

    cutoff = timezone.now() - timedelta(days=CASE_RETENTION_DAYS)
    aged = (
        CaseFile.objects.filter(status=CaseFile.STATUS_CLOSED, closed_at__lt=cutoff)
        .filter(
            Q(summary_enc__isnull=False)
            | Q(emergency_justification_enc__isnull=False)
            | Q(notes__body_enc__isnull=False)
            | Q(followups__detail_enc__isnull=False)
            | Q(handoffs__summary_enc__isnull=False)
        )
        .distinct()
    )
    count = 0
    for case in aged:
        details = {
            "policy": "retention_7y",
            "notes": case.notes.filter(body_enc__isnull=False).update(body_enc=None, body_enc_dek=None),
            "followups": case.followups.filter(detail_enc__isnull=False).update(detail_enc=None, detail_enc_dek=None),
            "handoffs": case.handoffs.filter(summary_enc__isnull=False).update(summary_enc=None, summary_enc_dek=None),
        }
        CaseFile.objects.filter(pk=case.pk).update(
            summary_enc=None,
            summary_enc_dek=None,
            emergency_justification_enc=None,
            emergency_justification_enc_dek=None,
        )
        emit("case.retention_shredded", case, details=details)
        count += 1
    return f"Retention-shredded {count} aged closed cases"

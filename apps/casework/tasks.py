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
        slug = items[0].case.community.slug
        link = reverse("casework:followups-mine", kwargs={"slug": slug})
        # Idempotence per community (the link names it): per person, someone coordinating in two
        # communities only ever heard about one of them (2026-10 bug hunt, L21).
        if Notification.objects.filter(
            recipient=user, type="followup_overdue", created_at__date=today, link=link
        ).exists():
            continue
        lines = [f"• {fu.title} — due {fu.due_date} (case {fu.case.short_code})" for fu in items[:20]]
        body = "\n".join(lines)
        notify(user, "followup_overdue", title=f"{len(items)} overdue follow-up(s)", body=body, link=link)
        # Honour the email opt-out, the way NotificationAdapter does on every other
        # send. Kept as a direct send_mail rather than routed through the adapter:
        # the adapter re-brands the subject "[UMI] …", and Lake 2's mail is
        # deliberately "[Case Notes]" with a plaintext-only body (§3.6 — nothing
        # decrypts in email).
        # PROVEN addresses only (#172). Nothing decrypts here, but follow-up TITLES are
        # coordinator-written plaintext — "Call Maria about the eviction hearing" — so a
        # typo'd coordinator address would mail case detail to a stranger. The in-app
        # notify() above still lands; only the email is withheld.
        if user.deliverable_email and getattr(user, "email_notifications", True):
            try:
                send_mail(
                    subject=f"[Case Notes] {len(items)} overdue follow-up(s)",
                    message=body + f"\n\nOpen your queue: {link}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[user.deliverable_email],
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
    from apps.holds.services import everything_held, held_cases_q

    from .models import CaseFile, CaseNote

    if everything_held():
        return "Legal hold in force on everything: no draft was discarded"
    cutoff = timezone.now() - timezone.timedelta(hours=72)
    stale = CaseNote.objects.filter(status=CaseNote.STATUS_DRAFT, updated_at__lt=cutoff).exclude(
        case__in=CaseFile.objects.filter(held_cases_q())
    )
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

# What a shredded follow-up title reads afterwards. Titles are plain text by design (the overdue
# digest mails them), so a shred overwrites them; there is no key to destroy.
ERASED = "Erased"

CASEWORK_NOTIFICATION_TYPES = (
    "case_assigned",
    "handoff_pending",
    "followup_assigned",
    "followup_overdue",
    "case_grant",
)


def _case_notifications(case):
    """Casework notifications about a case: those linking to it, and the follow-up ones, which
    name it by its short code."""
    from django.db.models import Q

    from apps.notifications.models import Notification

    code = case.short_code
    return Notification.objects.filter(type__in=CASEWORK_NOTIFICATION_TYPES).filter(
        Q(link__contains=str(case.pk)) | Q(title__contains=code) | Q(body__contains=f"(case {code})")
    )


def _has_content_q():
    """Cases that still say something about their subject: an encrypted field not yet shredded, or
    plain text not yet overwritten. A shredded case matches none of it, so sweeps are idempotent."""
    from django.db.models import Q

    from .models import CaseAccessGrant, CaseNote, FollowUp, WarmHandoff

    return (
        Q(summary_enc__isnull=False)
        | Q(emergency_justification_enc__isnull=False)
        | Q(pk__in=CaseNote.objects.filter(body_enc__isnull=False).values("case"))
        | Q(pk__in=FollowUp.objects.filter(Q(detail_enc__isnull=False) | ~Q(title=ERASED)).values("case"))
        | Q(pk__in=WarmHandoff.objects.filter(summary_enc__isnull=False).values("case"))
        | Q(pk__in=CaseAccessGrant.objects.exclude(reason="").values("case"))
    )


def shred_case_content(case):
    """Shred everything a case says about its subject; return PII-free counts for the audit row.
    Shared by the seven-year sweep and a person's erasure (apps/people/erasure.py).

    Nulls BOTH envelope columns (ciphertext + DEK) on the case summary, the emergency
    justification, and every note/follow-up/handoff body, so reads return None and
    `casework_envelope_status` stays clean. Bulk `.update()` is deliberate: finalized notes block
    `save()` edits by design, and this is a policy action, not an edit.

    Plain text about the subject goes in the same pass (2026-10 bug hunt, L17): follow-up titles
    ("Call Maria about the eviction hearing"), grant reasons, and the notification bodies that
    repeat them. Before, all of it outlived the shred.
    """
    from .models import CaseFile

    details = {
        "notes": case.notes.filter(body_enc__isnull=False).update(body_enc=None, body_enc_dek=None),
        "followups": case.followups.filter(detail_enc__isnull=False).update(detail_enc=None, detail_enc_dek=None),
        "handoffs": case.handoffs.filter(summary_enc__isnull=False).update(summary_enc=None, summary_enc_dek=None),
        "followup_titles": case.followups.exclude(title=ERASED).update(title=ERASED),
        "grant_reasons": case.grants.exclude(reason="").update(reason=""),
        "notifications": _case_notifications(case).exclude(body="").update(body=""),
    }
    CaseFile.objects.filter(pk=case.pk).update(
        summary_enc=None,
        summary_enc_dek=None,
        emergency_justification_enc=None,
        emergency_justification_enc_dek=None,
    )
    return details


def shred_aged_cases():
    """Shred cases closed more than seven years ago, then erase the people they were about.

    One audit row per case (PII-free counts), not per note. Idempotent: a fully shredded case no
    longer matches the content filter, and an erased person no longer matches the identity one.
    """
    from datetime import timedelta

    from apps.holds.services import everything_held, held_cases_q

    from .models import CaseFile

    if everything_held():  # legal hold on everything (docs/specs/legal-hold.md)
        return "Legal hold in force on everything: no case was shredded"
    cutoff = timezone.now() - timedelta(days=CASE_RETENTION_DAYS)
    aged = (
        CaseFile.objects.filter(status=CaseFile.STATUS_CLOSED, closed_at__lt=cutoff)
        .exclude(held_cases_q())
        .filter(_has_content_q())
    )
    count = 0
    for case in aged:
        emit("case.retention_shredded", case, details={"policy": "retention_7y", **shred_case_content(case)})
        count += 1
    people = _erase_aged_subjects(cutoff)
    return f"Retention-shredded {count} aged closed cases and erased {people} person record(s)"


def _erase_aged_subjects(cutoff):
    """Erase a subject once every case about them has aged out (2026-10 bug hunt, L16): the sweep
    shredded what the cases said and kept whom they were about. A person with any case still open,
    closed within the window, or held, keeps their record; so does one with no case at all."""
    from django.db import transaction
    from django.db.models import Q

    from apps.holds.services import held_persons_q
    from apps.people.erasure import identity_present_q, shred_identity
    from apps.people.models import Person

    from .models import CaseFile

    live = CaseFile.objects.exclude(Q(status=CaseFile.STATUS_CLOSED, closed_at__lt=cutoff)).values("subject_person")
    due = (
        Person.objects.filter(pk__in=CaseFile.objects.values("subject_person"))
        .exclude(pk__in=live)
        .exclude(held_persons_q())
        .filter(identity_present_q())
    )
    count = 0
    for pk in due.values_list("pk", flat=True):
        with transaction.atomic():
            # Re-checked under the row lock: a case opened for them since the query above wins.
            person = due.select_for_update().filter(pk=pk).first()
            if person is None:
                continue
            shred_identity(person)
            emit("person.retention_shredded", person, details={"policy": "retention_7y"})
        count += 1
    return count

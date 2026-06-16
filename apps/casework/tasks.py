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

from .models import FollowUp
from .notify import notify

logger = logging.getLogger(__name__)


def followup_overdue_digest():
    """One in-app notification + one email per assignee per day, listing
    plaintext titles + due dates. Idempotent within a calendar day."""
    from apps.notifications.models import Notification

    today = timezone.localdate()
    overdue = (
        FollowUp.objects.filter(status="open", due_date__lt=today)
        .select_related("assigned_to__user", "case__community")
        .order_by("due_date")
    )
    by_assignee: dict = {}
    for fu in overdue:
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
        if user.email:
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


def register_schedule():
    from django_q.models import Schedule

    Schedule.objects.update_or_create(
        name="casework-followup-digest",
        defaults={
            "func": "apps.casework.tasks.followup_overdue_digest",
            "schedule_type": Schedule.DAILY,
            "repeats": -1,
        },
    )

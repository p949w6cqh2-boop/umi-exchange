"""
One-command federation ops readout (§12 Stage E): link health, outbox depth,
retention debt, shadow volume. Human text by default; --json for monitor.sh /
UptimeRobot keyword checks. PII-free by construction — counts and hours only.

  python manage.py federation_status [--json]
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Federation health/retention summary (counts only, no PII)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="machine-readable output")

    def handle(self, *args, **opts):
        from apps.federation.models import FederatedMatch, FederationEvent, FederationLink, ShadowListing

        now = timezone.now()
        pending = FederationEvent.objects.filter(direction="out", state="pending")
        oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
        data = {
            "enabled": bool(getattr(settings, "FEDERATION_ENABLED", False)),
            "capabilities": list(getattr(settings, "FEDERATION_CAPABILITIES", [])),
            "links": {
                "active": FederationLink.objects.filter(status="active").count(),
                "suspended": FederationLink.objects.filter(status="suspended").count(),
                "unreachable": FederationLink.objects.filter(status="active", unreachable_since__isnull=False).count(),
            },
            "outbox": {
                "pending": pending.count(),
                "failed": FederationEvent.objects.filter(direction="out", state="failed").count(),
                "oldest_pending_hours": round((now - oldest).total_seconds() / 3600, 1) if oldest else 0,
            },
            "retention": {
                "contacts_awaiting_shred": FederatedMatch.objects.filter(
                    contact_payload_enc__isnull=False, contact_expires_at__isnull=False
                ).count(),
                "contacts_overdue_shred": FederatedMatch.objects.filter(
                    contact_payload_enc__isnull=False, contact_expires_at__lt=now
                ).count(),
            },
            "shadows": {"live": ShadowListing.objects.filter(expires_at__gt=now).count()},
        }
        if opts["json"]:
            self.stdout.write(json.dumps(data))
            return

        links, outbox, ret = data["links"], data["outbox"], data["retention"]
        self.stdout.write(f"federation enabled: {data['enabled']}  capabilities: {','.join(data['capabilities'])}")
        self.stdout.write(
            f"links: {links['active']} active ({links['unreachable']} unreachable), {links['suspended']} suspended"
        )
        self.stdout.write(
            f"outbox: {outbox['pending']} pending (oldest {outbox['oldest_pending_hours']}h), {outbox['failed']} failed"
        )
        self.stdout.write(
            f"retention: {ret['contacts_awaiting_shred']} contacts in grace, "
            f"{ret['contacts_overdue_shred']} overdue for shred"
        )
        self.stdout.write(f"shadows: {data['shadows']['live']} live")
        problems = []
        if links["unreachable"]:
            problems.append("unreachable link(s) — §11 auto-suspend after 7 days")
        if ret["contacts_overdue_shred"]:
            problems.append("overdue contact shreds — is the daily sweep (qcluster) running?")
        if outbox["failed"]:
            problems.append("failed outbox rows — peer gave up after 72h; mirror re-syncs on return")
        for p in problems:
            self.stderr.write(self.style.WARNING(f"⚠ {p}"))
        if not problems:
            self.stdout.write(self.style.SUCCESS("federation healthy"))

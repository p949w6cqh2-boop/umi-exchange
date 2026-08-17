"""Backfill: accounts that predate the human-verification gate are verified.

The spec's own instruction (docs/specs/human-verification.md build notes): existing
accounts are fictional demo data, and the pilot parish starts clean — nothing gained by
locking the demo out of its own board. Reverse restores the unverified state.
"""

from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(verified_at__isnull=True).update(verified_at=timezone.now(), verified_via="backfill")


def unfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(verified_via="backfill").update(verified_at=None, verified_via="")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_human_verification"),
    ]

    operations = [
        migrations.RunPython(backfill, unfill),
    ]

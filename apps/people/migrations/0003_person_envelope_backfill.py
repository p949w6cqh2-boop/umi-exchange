"""Stage C — backfill Person PII from direct-KEK to envelope encryption.

Thin wrapper; logic + reversal live in apps/people/envelope_backfill.py so
they're importable by the census command and tests. Non-atomic for batch-wise
resumability. Requires ENCRYPTION_KEYS/ENCRYPTION_KEY at run time (fail-closed).
"""

from django.db import migrations

from apps.people.envelope_backfill import forward_func, reverse_func


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("people", "0002_person_envelope_dek_columns"),
    ]

    operations = [
        migrations.RunPython(forward_func, reverse_func),
    ]

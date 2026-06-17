"""Stage C — backfill casework PII from direct-KEK to envelope encryption.

Thin wrapper; logic + reversal live in apps/casework/envelope_backfill.py so
they're importable by the census command and tests. Non-atomic for batch-wise
resumability. Requires ENCRYPTION_KEYS/ENCRYPTION_KEY at run time (fail-closed).

Renumber + repoint if your casework app has migrations beyond 0003.
"""

from django.db import migrations

from apps.casework.envelope_backfill import forward_func, reverse_func


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("casework", "0003_envelope_dek_columns"),
    ]

    operations = [
        migrations.RunPython(forward_func, reverse_func),
    ]

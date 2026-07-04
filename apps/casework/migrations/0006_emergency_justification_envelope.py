"""H-1 — encrypt CaseFile.emergency_justification at rest (plaintext → envelope).

Phase 1 of 2 (additive + backfill). The plaintext column is dropped in the
SEPARATE following migration (0007), never in the same migration that backfills
— so an operator can apply this, confirm `casework_envelope_status` shows the
new field as envelope>0 / unreadable=0, and only then apply the drop.

Non-atomic for batch-wise resumability. Requires ENCRYPTION_KEYS/ENCRYPTION_KEY
at run time (fail-closed).
"""

from django.db import migrations, models

from apps.casework.envelope_backfill import (
    backfill_emergency_justification,
    reverse_emergency_justification,
)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("casework", "0005_casenote_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="casefile",
            name="emergency_justification_enc",
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="casefile",
            name="emergency_justification_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(backfill_emergency_justification, reverse_emergency_justification),
    ]

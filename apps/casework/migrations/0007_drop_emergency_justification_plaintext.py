"""H-1 phase 2 of 2 — drop the plaintext emergency_justification column.

SEPARATE from the backfill (0006) on purpose. Production order: apply 0006,
run `casework_envelope_status` and confirm CaseFile.emergency_justification_enc
shows envelope>0 / unreadable=0, THEN apply this migration. Do not apply both
in one unattended `migrate` on real data without that census check in between.

Reversing this re-adds the (empty) plaintext column; reversing 0006 then
repopulates it from the envelope ciphertext.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("casework", "0006_emergency_justification_envelope"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="casefile",
            name="emergency_justification",
        ),
    ]

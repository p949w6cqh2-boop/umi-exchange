"""Stage A — additive per-record DEK columns for casework envelope encryption.

Zero rows touched, zero downtime. Reversible. If your casework app has
migrations beyond 0002, renumber this file and repoint the dependency.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("casework", "0002_widen_audit_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="casefile",
            name="summary_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="casenote",
            name="body_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="followup",
            name="detail_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="warmhandoff",
            name="summary_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
    ]

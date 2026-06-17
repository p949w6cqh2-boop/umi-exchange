"""Stage A — additive per-record DEK columns for Person envelope encryption.

Zero rows touched, reversible. Mirrors the casework envelope rollout. No
blind index here (person_name_bidx / §12.3 is a separate enhancement with its
own key and is deliberately out of scope).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("people", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="display_name_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="person",
            name="contact_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="person",
            name="dob_enc_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
    ]

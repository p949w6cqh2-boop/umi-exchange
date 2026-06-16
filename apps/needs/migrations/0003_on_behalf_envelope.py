"""§12.2 stage 1 — additive DEK column. Zero rows touched, zero downtime.

Numbered after the §10.4 FTS migration; if your needs app is elsewhere in
its sequence, renumber and repoint as before.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("needs", "0002_fulltext_search"),
    ]

    operations = [
        migrations.AddField(
            model_name="need",
            name="on_behalf_of_dek",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
    ]

"""§10.1 — widen AuditLog.action to varchar(32) for dotted event names.

Renumbered to 0003 (the bundle shipped this as 0002, which collides with this
repo's existing 0002_append_only). Legacy create/read/update/delete values
remain valid.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0002_append_only"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(max_length=32),
        ),
    ]

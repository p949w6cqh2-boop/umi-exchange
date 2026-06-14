"""
A1: widen audit_auditlog.action from varchar(10) to varchar(32) so dotted
casework events fit (design §10.1, accepted assumption A1).

Postgres-only DDL via RunPython (SQLite doesn't enforce VARCHAR length, so
this is a no-op there and the test suite is unaffected). The apps.audit code
is untouched; existing rows remain valid. Reverse is a deliberate no-op —
shrinking back would truncate or fail on the new event names.
"""
from django.db import migrations


def widen_action_column(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    AuditLog = apps.get_model("audit", "AuditLog")
    table = AuditLog._meta.db_table
    schema_editor.execute(
        f'ALTER TABLE "{table}" ALTER COLUMN "action" TYPE varchar(32)'
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("casework", "0001_initial"),
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(widen_action_column, noop),
    ]

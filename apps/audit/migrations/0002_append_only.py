"""
Enforce the append-only audit log at the database level (UMI Protocol 8.3).

On PostgreSQL this revokes UPDATE/DELETE/TRUNCATE on the audit table from the
application's database role, so even raw queries (or a compromised app) cannot
rewrite history. INSERT and SELECT remain. The application role is taken from
settings.AUDIT_DB_APP_ROLE (falls back to the configured DATABASES user).

On non-PostgreSQL backends (e.g. SQLite in development/CI) this is a no-op;
model-level enforcement in AuditLog.save()/delete() still applies there.
"""

from django.conf import settings
from django.db import migrations


def _app_role():
    role = getattr(settings, "AUDIT_DB_APP_ROLE", None)
    if not role:
        role = settings.DATABASES.get("default", {}).get("USER") or ""
    return role


def revoke_mutations(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    role = _app_role()
    if not role:
        return  # No explicit role to target; skip rather than guess.
    schema_editor.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_auditlog FROM "{role}";')


def grant_mutations(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    role = _app_role()
    if not role:
        return
    schema_editor.execute(f'GRANT UPDATE, DELETE, TRUNCATE ON TABLE audit_auditlog TO "{role}";')


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(revoke_mutations, grant_mutations),
    ]

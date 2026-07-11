"""Management command to restrict audit log table permissions in PostgreSQL."""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Revoke UPDATE/DELETE/TRUNCATE on audit_auditlog for the runtime app DB role."

    def handle(self, *args, **options):
        # Same resolution as audit migration 0002: the explicit runtime role
        # wins — revoking from the connection's own user is meaningless when
        # that user owns the table (owners can re-grant; superusers ignore ACLs).
        role = getattr(settings, "AUDIT_DB_APP_ROLE", "") or connection.settings_dict.get("USER", "umi")
        with connection.cursor() as cursor:
            try:
                cursor.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_auditlog FROM "{role}";')
                self.stdout.write(self.style.SUCCESS(f"Revoked UPDATE/DELETE/TRUNCATE on audit_auditlog for {role}."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not restrict permissions: {e}"))
                self.stdout.write("Run this command on a connection that owns the table (e.g. the migration role).")

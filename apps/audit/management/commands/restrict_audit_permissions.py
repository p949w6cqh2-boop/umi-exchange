"""Management command to restrict audit log table permissions in PostgreSQL."""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Revoke UPDATE and DELETE on audit_auditlog for the app DB user."

    def handle(self, *args, **options):
        db_user = connection.settings_dict.get("USER", "umi")
        with connection.cursor() as cursor:
            try:
                cursor.execute(f"REVOKE UPDATE, DELETE ON audit_auditlog FROM {db_user};")
                self.stdout.write(self.style.SUCCESS(f"Revoked UPDATE/DELETE on audit_auditlog for {db_user}."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not restrict permissions: {e}"))
                self.stdout.write("Run this command as a PostgreSQL superuser.")

"""Purge expired, never-used one-time credentials. Dry run unless --apply.

Used rows are never touched — they are the record that a recovery happened
(docs/specs/account-recovery.md §Build notes: archive semantics, never delete a used row).
"""

from django.core.management.base import BaseCommand

from apps.accounts.credentials import purgeable


class Command(BaseCommand):
    help = "Delete expired one-time credentials that were never used (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually delete. Without it, only count.")

    def handle(self, *args, **options):
        rows = purgeable()
        count = rows.count()
        from apps.holds.services import everything_held

        if options["apply"] and everything_held():
            self.stdout.write("Legal hold in force on everything: nothing was purged.")
            return
        if not options["apply"]:
            self.stdout.write(f"DRY RUN: {count} expired unused credential(s) would be purged. Re-run with --apply.")
            return
        rows.delete()
        self.stdout.write(f"Purged {count} expired unused credential(s). Used credentials are kept.")

"""Download this month's DB-IP country database and swap it in atomically.

Run monthly from host cron. A failed download or a file that does not open as a database leaves
the current one in place; and since the gate fails open, even a missing file blocks no one.
DB-IP "IP to Country Lite" is CC BY 4.0: the about page carries the attribution while it is in use.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts import geo


class Command(BaseCommand):
    help = "Refresh the GeoIP country database at GEO_DB_PATH (DB-IP Lite, monthly)."

    def add_arguments(self, parser):
        parser.add_argument("--month", help="YYYY-MM to fetch (default: this month, UTC)")
        parser.add_argument("--dest", help="Where to write (default: settings.GEO_DB_PATH)")

    def handle(self, *args, **options):
        dest = options.get("dest") or settings.GEO_DB_PATH
        if not dest:
            raise CommandError("GEO_DB_PATH is not set and no --dest was given.")
        month = options.get("month") or timezone.now().strftime("%Y-%m")
        try:
            size = geo.download_database(month, dest)
        except Exception as exc:  # report, keep the old file (download_database never swaps on failure)
            raise CommandError(f"refresh failed for {month}, the current file was kept: {exc}") from exc
        geo.reset_cache()  # drop the cached reader so the next lookup opens the new file
        self.stdout.write(f"GeoIP database for {month} installed at {dest} ({size} bytes).")

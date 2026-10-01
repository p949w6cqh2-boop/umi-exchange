"""Print geolocking Phase 0's table: sign-up attempts per country (docs/specs/geolocking.md)."""

from django.core.management.base import BaseCommand

from apps.accounts.models import GeoSignupCount


class Command(BaseCommand):
    help = "Show sign-up attempts per country (aggregate integers only; no IPs exist to show)."

    def handle(self, *args, **options):
        rows = list(GeoSignupCount.objects.order_by("-count", "country"))
        if not rows:
            self.stdout.write("No sign-up attempts counted yet. (Is GEO_COUNT on, with GEO_DB_PATH set?)")
            return
        total = sum(r.count for r in rows)
        self.stdout.write(f"{'country':<8}{'attempts':>9}  first seen → last seen")
        for r in rows:
            label = "unknown" if r.country == "--" else r.country
            self.stdout.write(f"{label:<8}{r.count:>9}  {r.first_seen:%Y-%m-%d} → {r.last_seen:%Y-%m-%d}")
        self.stdout.write(f"{'total':<8}{total:>9}")

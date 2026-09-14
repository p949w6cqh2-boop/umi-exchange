"""bright_line — measure the ethics bright line instead of asserting it.

docs/ethics-and-safety.md Part 4 said "fictional demo data only" for weeks while roughly
seven of twenty-two accounts carried real, working email addresses. Nothing counted. The
correction on 2026-09-12 wrote: "a bright line needs a check, not a sentence." This is the
check, in two halves that are deliberately treated differently:

  REGISTRATIONS are reported, never failed on. They are already non-zero, and a check that is
  permanently red teaches its reader to ignore it — an anti-control. The number is context for
  the human reading the weekly pull.

  SENSITIVE ROWS are failed on. Every model in the people, households, casework and federation
  apps must have zero rows until the gate closes; that is the line's actual content ("no real
  person's casework, need, household or identity enters the live system"). Zero today, so the
  check is green today, and it goes red on the real violation and nothing else. Exit code 2.

Counts only. This command never prints a username, an address, or a name — it runs against
production and its output lands in a ledger.

Usage (read-only, on the droplet):
    docker compose --env-file .env -f docker/docker-compose.prod.yml exec -T app \\
        python manage.py bright_line
"""

import sys

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

# The seed (seed_demo_parish) leaves exactly one fingerprint on the accounts it creates.
SEED_EMAIL_SUFFIX = "@demo.invalid"

# Every model in these apps must be empty while the gate is open. Derived from the app
# registry at runtime so a new casework table is counted without anyone editing this file.
SENSITIVE_APPS = ("people", "households", "casework", "federation")

EXIT_CROSSED = 2


class Command(BaseCommand):
    help = "Count registrations and sensitive rows against the ethics bright line (counts only, no PII)."

    def handle(self, *args, **options):
        user_model = get_user_model()

        total = user_model.objects.count()
        seeded = user_model.objects.filter(email__iendswith=SEED_EMAIL_SUFFIX).count()
        other_qs = user_model.objects.exclude(email__iendswith=SEED_EMAIL_SUFFIX)
        other = other_qs.count()
        other_with_email = other_qs.exclude(email__isnull=True).exclude(email="").count()
        other_without = other - other_with_email

        per_app = {}
        for label in SENSITIVE_APPS:
            per_app[label] = sum(m.objects.count() for m in apps.get_app_config(label).get_models())
        sensitive = sum(per_app.values())

        self.stdout.write(
            f"accounts       {total:>3}   seeded ({SEED_EMAIL_SUFFIX}) {seeded} · "
            f"other {other} ({other_with_email} with email, {other_without} without)"
        )
        self.stdout.write(f"sensitive rows {sensitive:>3}   " + " · ".join(f"{k} {v}" for k, v in per_app.items()))

        if sensitive:
            self.stdout.write(
                self.style.ERROR(
                    f"BRIGHT LINE: CROSSED — {sensitive} sensitive row(s) exist while the gate is open. "
                    "docs/ethics-and-safety.md Part 4."
                )
            )
            sys.exit(EXIT_CROSSED)

        self.stdout.write(self.style.SUCCESS("BRIGHT LINE: HOLDING — no sensitive rows"))

"""Re-run the §G pipeline over every page's content_md — for renderer pin bumps
or allowlist changes. Render normally happens on save; this is the sweep."""

from django.core.management.base import BaseCommand

from apps.pages.models import CommunityPage


class Command(BaseCommand):
    help = "Re-render content_html for every community page (renderer pin bump / allowlist change)."

    def handle(self, *args, **options):
        count = 0
        for page in CommunityPage.objects.all().iterator():
            page.save(update_fields=["content_html", "updated_at"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"re-rendered {count} page(s)"))

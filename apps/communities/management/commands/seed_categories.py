"""Management command to seed default categories for a community."""

from django.core.management.base import BaseCommand, CommandError

from apps.communities.models import DEFAULT_CATEGORIES, Category, Community


class Command(BaseCommand):
    help = "Seed default categories for a community. Usage: manage.py seed_categories <slug>"

    def add_arguments(self, parser):
        parser.add_argument("slug", type=str, help="Community slug to add categories to.")

    def handle(self, *args, **options):
        slug = options["slug"]
        try:
            community = Community.objects.get(slug=slug)
        except Community.DoesNotExist:
            raise CommandError(f"Community '{slug}' not found.")

        existing = set(community.categories.values_list("name", flat=True))
        created = 0
        for i, (icon, name) in enumerate(DEFAULT_CATEGORIES):
            if name not in existing:
                Category.objects.create(community=community, name=name, icon=icon, sort_order=i)
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created} categories for '{community.name}' ({len(existing)} already existed)."
            )
        )

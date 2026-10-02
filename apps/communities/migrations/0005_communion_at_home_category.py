"""Communion at home: a category the first coordinator asked for (2026-10-02), for homebound
parishioners asking for a minister to bring them communion.

Added to every community that exists today, all of them parishes. Deliberately NOT added to
DEFAULT_CATEGORIES, which every new community gets, including groups that are not parishes.
Reversing leaves the rows where they are: archive, never delete.
"""

from django.db import migrations

NAME = "Communion at home"
ICON = "✝️"  # Latin cross
SORT_ORDER = 9  # with "Other"; the name sorts it just before


def add_communion_at_home(apps, schema_editor):
    Community = apps.get_model("communities", "Community")
    Category = apps.get_model("communities", "Category")
    for community in Community.objects.all():
        Category.objects.get_or_create(
            community=community, name=NAME, defaults={"icon": ICON, "sort_order": SORT_ORDER}
        )


class Migration(migrations.Migration):
    dependencies = [
        ("communities", "0004_member_role_intake"),
    ]

    operations = [
        migrations.RunPython(add_communion_at_home, migrations.RunPython.noop),
    ]

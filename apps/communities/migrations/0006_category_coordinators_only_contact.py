"""Coordinators-only contact for a category, and Communion at home marked with it: the founder's
decision 2026-10-02 (docs/specs/phone-codes.md, decision 4). A homebound parishioner's number
stays with the coordinators who arrange the visit; the matched helper never sees it.
Reversing leaves the flag where it is: archive, never delete."""

from django.db import migrations, models


def mark_communion_at_home(apps, schema_editor):
    Category = apps.get_model("communities", "Category")
    Category.objects.filter(name="Communion at home").update(coordinators_only_contact=True)


class Migration(migrations.Migration):
    dependencies = [
        ("communities", "0005_communion_at_home_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="coordinators_only_contact",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_communion_at_home, migrations.RunPython.noop),
    ]

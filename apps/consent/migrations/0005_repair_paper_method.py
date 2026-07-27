"""Repair consents stored with method="paper".

The casework intake form offered a "paper" option while METHOD_CHOICES allows
verbal/written/digital, and objects.create() never validates choices — so any
coordinator who picked "Paper (filed)" stored an invalid enum. A paper form is
written consent; rewrite the stored value to match what actually happened.
"""

from django.db import migrations


def repair_paper(apps, schema_editor):
    Consent = apps.get_model("consent", "Consent")
    Consent.objects.filter(method="paper").update(method="written")


class Migration(migrations.Migration):
    dependencies = [
        ("consent", "0004_move_onbehalf_breadcrumb"),
    ]

    operations = [
        migrations.RunPython(repair_paper, migrations.RunPython.noop),
    ]

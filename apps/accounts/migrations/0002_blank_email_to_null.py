"""Convert legacy empty-string emails to NULL.

Before the User.clean()/save() null-coercion fix, an email-less registration
stored email="" (AbstractUser.clean normalizes None to ""). At most one such
row can exist per database (unique constraint) — it blocks every subsequent
email-less signup until converted. "" and NULL both mean "no email", so this
is a semantic no-op; reverse is a no-op.
"""

from django.db import migrations


def blank_email_to_null(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(email="").update(email=None)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(blank_email_to_null, migrations.RunPython.noop),
    ]

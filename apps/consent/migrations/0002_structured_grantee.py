"""§10.2 — structured grantee fields + backfill.

Backfill rule (per design): where granted_to exactly equals the name of a
community AND that name is unique across communities, set grantee_id to it.
Ambiguous or unmatched labels stay NULL (legacy, label-era) — covers()
treats them as valid for their declared type.

Renumber + repoint dependencies if consent has migrations beyond 0001.
"""
from django.db import migrations, models


def backfill_grantee_ids(apps, schema_editor):
    Consent = apps.get_model("consent", "Consent")
    Community = apps.get_model("communities", "Community")

    by_name = {}
    for cid, name in Community.objects.values_list("id", "name"):
        by_name.setdefault(name, []).append(cid)
    unique = {name: ids[0] for name, ids in by_name.items() if len(ids) == 1}

    for consent in Consent.objects.filter(grantee_id__isnull=True).iterator():
        community_id = unique.get(consent.granted_to)
        if community_id:
            consent.grantee_id = community_id
            consent.save(update_fields=["grantee_id"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("consent", "0001_initial"),
        ("communities", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="consent",
            name="grantee_type",
            field=models.CharField(
                choices=[("community", "Community"),
                         ("organization", "Organization"),
                         ("member", "Member"), ("other", "Other")],
                default="community", max_length=20),
        ),
        migrations.AddField(
            model_name="consent",
            name="grantee_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="consent",
            index=models.Index(fields=["grantee_type", "grantee_id"],
                               name="consent_grantee_idx"),
        ),
        migrations.RunPython(backfill_grantee_ids, noop),
    ]

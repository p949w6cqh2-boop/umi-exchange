import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("communities", "0001_initial"),
        ("households", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Person",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("display_name_enc", models.BinaryField(blank=True, null=True)),
                ("contact_enc", models.BinaryField(blank=True, null=True)),
                ("dob_enc", models.BinaryField(blank=True, null=True)),
                ("custom", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="persons_created", to="communities.member")),
                ("created_in_community", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="persons", to="communities.community")),
                ("household", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="persons", to="households.household")),
                ("linked_user", models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="person_record", to=settings.AUTH_USER_MODEL)),
                ("merged_into", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="merge_sources", to="people.person")),
            ],
            options={"db_table": "people_person"},
        ),
        migrations.AddIndex(
            model_name="person",
            index=models.Index(fields=["created_in_community"],
                               name="people_person_comm_idx"),
        ),
        migrations.AddIndex(
            model_name="person",
            index=models.Index(fields=["household"],
                               name="people_person_hh_idx"),
        ),
    ]

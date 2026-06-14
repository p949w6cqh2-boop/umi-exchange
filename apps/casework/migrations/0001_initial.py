import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("people", "0001_initial"),
        ("communities", "0001_initial"),
        ("consent", "0001_initial"),
        ("needs", "0001_initial"),
        ("matches", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseFile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("status", models.CharField(
                    choices=[("open", "Open"), ("monitoring", "Monitoring"),
                             ("closed", "Closed")],
                    default="open", max_length=12)),
                ("sensitivity", models.CharField(
                    choices=[("standard", "Standard"),
                             ("restricted", "Restricted")],
                    default="standard", max_length=12)),
                ("emergency_opened", models.BooleanField(default=False)),
                ("emergency_justification", models.TextField(blank=True, default="")),
                ("primary_needs", models.JSONField(blank=True, default=list)),
                ("intake_date", models.DateField(
                    default=django.utils.timezone.localdate)),
                ("physical_ref", models.CharField(blank=True, default="",
                                                  max_length=100)),
                ("summary_enc", models.BinaryField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("custom", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_to", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="cases_assigned", to="communities.member")),
                ("community", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="case_files", to="communities.community")),
                ("consent", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="case_files", to="consent.consent")),
                ("opened_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="cases_opened", to="communities.member")),
                ("subject_person", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="case_files", to="people.person")),
            ],
            options={"db_table": "casework_case_file",
                     "ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="CaseNote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("kind", models.CharField(
                    choices=[("visit", "Home visit"), ("call", "Phone call"),
                             ("office", "Office visit"), ("aid", "Aid given"),
                             ("handoff", "Handoff"), ("system", "System")],
                    default="visit", max_length=10)),
                ("occurred_at", models.DateTimeField(
                    default=django.utils.timezone.now)),
                ("duration_minutes", models.PositiveSmallIntegerField(
                    blank=True, null=True)),
                ("location_kind", models.CharField(
                    choices=[("home", "Home"), ("office", "Office"),
                             ("phone", "Phone"), ("other", "Other")],
                    default="home", max_length=10)),
                ("actions", models.JSONField(blank=True, default=list)),
                ("aid_value_cents", models.PositiveIntegerField(blank=True,
                                                                null=True)),
                ("aid_currency", models.CharField(default="USD", max_length=3)),
                ("body_enc", models.BinaryField(blank=True, null=True)),
                ("status", models.CharField(
                    choices=[("draft", "Draft"), ("final", "Final"),
                             ("discarded", "Discarded")],
                    default="draft", max_length=10)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("client_uuid", models.UUIDField(blank=True, null=True,
                                                 unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("amends", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="amendments", to="casework.casenote")),
                ("author", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="case_notes", to="communities.member")),
                ("case", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="notes", to="casework.casefile")),
                ("co_visitor", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="co_visited_notes", to="communities.member")),
                ("related_match", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="case_notes", to="matches.match")),
                ("related_need", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="case_notes", to="needs.need")),
            ],
            options={"db_table": "casework_case_note",
                     "ordering": ["-occurred_at"]},
        ),
        migrations.CreateModel(
            name="FollowUp",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("detail_enc", models.BinaryField(blank=True, null=True)),
                ("due_date", models.DateField()),
                ("status", models.CharField(
                    choices=[("open", "Open"), ("done", "Done"),
                             ("cancelled", "Cancelled")],
                    default="open", max_length=10)),
                ("done_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assigned_to", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="followups_assigned", to="communities.member")),
                ("case", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="followups", to="casework.casefile")),
                ("created_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="followups_created", to="communities.member")),
                ("source_note", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="followups", to="casework.casenote")),
            ],
            options={"db_table": "casework_follow_up", "ordering": ["due_date"]},
        ),
        migrations.CreateModel(
            name="WarmHandoff",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("summary_enc", models.BinaryField(blank=True, null=True)),
                ("status", models.CharField(
                    choices=[("pending", "Pending"),
                             ("acknowledged", "Acknowledged")],
                    default="pending", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("case", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="handoffs", to="casework.casefile")),
                ("from_member", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="handoffs_sent", to="communities.member")),
                ("to_member", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="handoffs_received", to="communities.member")),
            ],
            options={"db_table": "casework_warm_handoff",
                     "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CaseAccessGrant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False,
                                        primary_key=True, serialize=False)),
                ("role", models.CharField(
                    choices=[("viewer", "Viewer"),
                             ("contributor", "Contributor")],
                    default="viewer", max_length=12)),
                ("reason", models.CharField(max_length=200)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="grants", to="casework.casefile")),
                ("granted_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="case_grants_given", to="communities.member")),
                ("member", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="case_grants", to="communities.member")),
            ],
            options={"db_table": "casework_access_grant"},
        ),
        # ---- indexes ----
        migrations.AddIndex(model_name="casefile", index=models.Index(
            fields=["community", "status"], name="cw_cf_comm_status_idx")),
        migrations.AddIndex(model_name="casefile", index=models.Index(
            fields=["assigned_to", "status"], name="cw_cf_assignee_idx")),
        migrations.AddIndex(model_name="casefile", index=models.Index(
            fields=["subject_person"], name="cw_cf_subject_idx")),
        migrations.AddIndex(model_name="casefile", index=models.Index(
            fields=["community", "sensitivity"], name="cw_cf_sens_idx")),
        migrations.AddIndex(model_name="casenote", index=models.Index(
            fields=["case", "-occurred_at"], name="cw_note_case_time_idx")),
        migrations.AddIndex(model_name="casenote", index=models.Index(
            fields=["author", "status"], name="cw_note_author_idx")),
        migrations.AddIndex(model_name="followup", index=models.Index(
            fields=["assigned_to", "status", "due_date"],
            name="cw_fu_assignee_idx")),
        migrations.AddIndex(model_name="followup", index=models.Index(
            fields=["case", "status"], name="cw_fu_case_idx")),
        migrations.AddIndex(model_name="followup", index=models.Index(
            fields=["due_date", "status"], name="cw_fu_due_idx")),
        migrations.AddIndex(model_name="warmhandoff", index=models.Index(
            fields=["to_member", "status"], name="cw_ho_to_status_idx")),
        migrations.AddIndex(model_name="caseaccessgrant", index=models.Index(
            fields=["member"], name="cw_grant_member_idx")),
        # ---- constraints ----
        migrations.AddConstraint(
            model_name="casefile",
            constraint=models.CheckConstraint(
                check=(models.Q(("consent__isnull", False))
                       | models.Q(("emergency_opened", True))),
                name="cw_cf_consent_or_emergency"),
        ),
        migrations.AddConstraint(
            model_name="caseaccessgrant",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True)),
                fields=("case", "member"),
                name="cw_grant_one_active_per_member"),
        ),
    ]

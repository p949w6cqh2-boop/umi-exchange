from django.contrib import admin

from .models import CaseAccessGrant, CaseFile, CaseNote, FollowUp, WarmHandoff


@admin.register(CaseFile)
class CaseFileAdmin(admin.ModelAdmin):
    list_display = (
        "short_code",
        "community",
        "status",
        "sensitivity",
        "assigned_to",
        "intake_date",
        "emergency_opened",
        "updated_at",
    )
    list_filter = ("status", "sensitivity", "emergency_opened", "community")
    search_fields = ("id", "physical_ref")
    raw_id_fields = ("subject_person", "opened_by", "assigned_to", "consent")
    readonly_fields = ("id", "created_at", "updated_at", "closed_at", "summary_enc")
    date_hierarchy = "intake_date"

    def has_delete_permission(self, request, obj=None):
        # A case is closed, never destroyed. Admin delete drives Django's
        # Collector: bulk SQL that never calls each child's delete()/save()
        # guard, so it would cascade through finalized (immutable, A7) notes,
        # follow-ups, handoffs and grants — and record it only in the mutable
        # django_admin_log, not the append-only audit that crypto-shred rests on.
        return False


@admin.register(CaseNote)
class CaseNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "case", "kind", "status", "author", "occurred_at", "aid_value_cents")
    list_filter = ("kind", "status")
    search_fields = ("id", "case__id", "client_uuid")
    raw_id_fields = ("case", "author", "co_visitor", "amends", "related_need", "related_match")

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status == CaseNote.STATUS_FINAL:
            # Finalized notes are fully read-only in admin too (A7).
            return [f.name for f in self.model._meta.fields]
        return ("id", "created_at", "finalized_at", "body_enc")

    def has_delete_permission(self, request, obj=None):
        # Model guard blocks non-drafts anyway; reflect it in the UI.
        return bool(obj and obj.status == CaseNote.STATUS_DRAFT)


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "assigned_to", "due_date", "status")
    list_filter = ("status",)
    raw_id_fields = ("case", "created_by", "assigned_to", "source_note")
    readonly_fields = ("id", "created_at", "done_at", "detail_enc")


@admin.register(WarmHandoff)
class WarmHandoffAdmin(admin.ModelAdmin):
    list_display = ("case", "from_member", "to_member", "status", "created_at", "acknowledged_at")
    list_filter = ("status",)
    raw_id_fields = ("case", "from_member", "to_member")
    readonly_fields = ("id", "created_at", "acknowledged_at", "summary_enc")


@admin.register(CaseAccessGrant)
class CaseAccessGrantAdmin(admin.ModelAdmin):
    list_display = ("case", "member", "role", "granted_by", "expires_at", "revoked_at", "created_at")
    list_filter = ("role",)
    raw_id_fields = ("case", "member", "granted_by")
    readonly_fields = ("id", "created_at")

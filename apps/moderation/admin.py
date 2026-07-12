from django.contrib import admin

from .models import Flag


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ("community", "target_type", "reason", "status", "created_at", "resolved_by")
    list_filter = ("status", "reason", "target_type")
    readonly_fields = ("id", "created_at")

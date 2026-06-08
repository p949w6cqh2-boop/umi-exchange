"""Audit admin — read-only. No create/edit/delete."""

from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action", "resource_type", "resource_id"]
    list_filter = ["action", "resource_type"]
    search_fields = ["resource_id", "user__username"]
    readonly_fields = ["id", "user", "action", "resource_type", "resource_id", "details", "ip_hash", "timestamp"]
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

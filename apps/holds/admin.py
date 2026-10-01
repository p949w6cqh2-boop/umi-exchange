"""Read-only visibility for staff. Placing and releasing go through `manage.py legal_hold`, which
audits each act; the admin cannot edit or delete a hold."""

from django.contrib import admin

from .models import LegalHold


@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = ("scope", "reference", "placed_at", "released_at")
    list_filter = ("scope",)
    readonly_fields = [f.name for f in LegalHold._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

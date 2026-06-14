from django.contrib import admin

from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """PII-safe admin: shows codes, never decrypted names."""
    list_display = ("short_code", "created_in_community", "linked_user",
                    "household", "created_at")
    list_filter = ("created_in_community",)
    search_fields = ("id",)
    readonly_fields = ("id", "created_at", "display_name_enc", "contact_enc", "dob_enc")
    exclude = ()

    def has_delete_permission(self, request, obj=None):
        return False  # merge, never delete (design §2.5)

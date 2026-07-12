from django.contrib import admin

from .models import Flag


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ("__str__", "community", "reporter", "status", "resolution", "created_at")
    list_filter = ("status", "reason", "resolution")
    readonly_fields = ("id", "community", "reporter", "need", "offer", "member", "reason", "detail", "created_at")
    ordering = ("-created_at",)

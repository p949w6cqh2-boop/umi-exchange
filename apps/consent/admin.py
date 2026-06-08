"""Consent admin — registered for coordinator oversight."""

from django.contrib import admin

from .models import Consent


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ["participant", "granted_to", "status", "method", "granted_at"]
    list_filter = ["status", "method"]
    readonly_fields = ["id", "granted_at"]
    search_fields = ["participant__username", "granted_to"]

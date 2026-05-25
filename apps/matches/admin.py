from django.contrib import admin

from .models import Match


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["id", "need", "status", "proposed_at", "accepted_at", "fulfilled_at"]
    list_filter = ["status"]

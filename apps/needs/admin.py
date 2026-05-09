from django.contrib import admin
from .models import Need

@admin.register(Need)
class NeedAdmin(admin.ModelAdmin):
    list_display = ["title", "community", "urgency", "status", "created_at"]
    list_filter = ["status", "urgency"]

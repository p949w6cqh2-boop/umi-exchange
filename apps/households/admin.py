from django.contrib import admin
from .models import Household

@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name", "join_code", "created_by", "created_at"]
    readonly_fields = ["id", "join_code"]

from django.contrib import admin
from .models import Offer

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ["title", "community", "status", "created_at"]
    list_filter = ["status"]

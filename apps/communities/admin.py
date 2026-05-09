from django.contrib import admin
from .models import Community, Member, Category

@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "join_code", "visibility", "is_active", "created_at"]
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ["display_name", "community", "role", "is_active", "joined_at"]
    list_filter = ["role", "is_active"]

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["icon", "name", "community", "sort_order", "is_active"]

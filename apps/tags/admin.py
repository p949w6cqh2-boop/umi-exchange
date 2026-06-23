"""Django admin for the tag catalog (Tag) and the verification queue (MemberTag)."""

from django.contrib import admin

from .models import MemberTag, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "community",
        "category",
        "tier",
        "default_visibility",
        "public_when_verified",
        "is_active",
        "sort_order",
    )
    list_filter = ("tier", "category", "is_active", "public_when_verified", "community")
    search_fields = ("label", "slug", "community__name")
    ordering = ("community", "sort_order", "label")
    list_select_related = ("community",)


@admin.register(MemberTag)
class MemberTagAdmin(admin.ModelAdmin):
    list_display = (
        "tag",
        "member",
        "status",
        "tier",
        "visibility",
        "rejection_count",
        "requested_at",
        "verified_by",
    )
    # Queue-aware: filter to pending (the verification queue), by tier, etc.
    list_filter = ("status", "tag__tier", "tag__category")
    search_fields = ("member__display_name", "tag__label", "tag__slug")
    ordering = ("-requested_at",)
    list_select_related = ("tag", "member", "verified_by")
    raw_id_fields = ("member", "tag", "verified_by", "revoked_by")
    readonly_fields = ("requested_at", "verified_at", "revoked_at")

    @admin.display(description="Tier", ordering="tag__tier")
    def tier(self, obj):
        return obj.tag.get_tier_display()

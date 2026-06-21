"""
Seed default tags when a new Community is created.

Uses a post_save signal with apps.get_model to avoid a circular
communities → tags import.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="communities.Community")
def seed_default_tags(sender, instance, created, **kwargs):
    """Create the DEFAULT_TAGS catalog entries for a newly created community."""
    if not created:
        return

    # Late import to avoid circular dependency (communities ↔ tags).
    from .models import DEFAULT_TAGS, Tag

    for i, (slug, label, icon, category, tier, public_when_verified, default_visibility) in enumerate(DEFAULT_TAGS):
        Tag.objects.get_or_create(
            community=instance,
            slug=slug,
            defaults={
                "label": label,
                "icon": icon,
                "category": category,
                "tier": tier,
                "public_when_verified": public_when_verified,
                "default_visibility": default_visibility,
                "sort_order": i,
            },
        )

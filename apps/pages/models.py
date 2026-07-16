"""Coordinator-authored community pages (§C): draft → published → archived,
never deleted; a published page is never edited in place — a live fix goes
back through draft, and the priest signs again."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from apps.common.state import StateMachineMixin

from .render import render_page_html


class CommunityPageQuerySet(models.QuerySet):
    def member_visible(self, community):
        """member-visible ⇔ published ∧ not hidden (§C)."""
        return self.filter(community=community, status="published", moderation_hidden=False)

    def pre_auth_visible(self, community):
        """pre-auth ⇔ member-visible ∧ on landing ∧ community not private ∧ active (§C).
        Unlisted stays reachable — the link is the capability."""
        if community.visibility == "private" or not community.is_active:
            return self.none()
        return self.member_visible(community).filter(show_on_landing=True)


class CommunityPage(StateMachineMixin, models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]
    VALID_TRANSITIONS = {
        "draft": {"published", "archived"},
        "published": {"draft", "archived"},
        "archived": {"draft"},  # archived pages come back as drafts, never straight to live
    }
    TRANSITION_TIMESTAMPS = {"published": "published_at", "archived": "archived_at"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="pages")
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="draft")
    content_md = models.TextField(blank=True)
    content_html = models.TextField(blank=True, editable=False)  # nh3 is the ONLY writer (§G)
    show_on_landing = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    moderation_hidden = models.BooleanField(default=False)

    created_by = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="pages_created")
    updated_by = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="pages_updated"
    )
    published_by = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="pages_published"
    )

    published_at = models.DateTimeField(null=True, blank=True)
    first_published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CommunityPageQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "title"]
        indexes = [models.Index(fields=["community", "status", "show_on_landing"])]
        constraints = [
            # Archived rows release their slug (§C) — the promise belongs to the living.
            models.UniqueConstraint(
                fields=["community", "slug"],
                condition=~Q(status="archived"),
                name="uniq_live_page_slug_per_community",
            )
        ]

    def __str__(self):
        return f"{self.community.slug}/p/{self.slug} ({self.status})"

    def save(self, *args, **kwargs):
        # Links are promises: the slug froze at first publish (§C).
        if self.pk and self.first_published_at:
            old_slug = type(self).objects.filter(pk=self.pk).values_list("slug", flat=True).first()
            if old_slug is not None and old_slug != self.slug:
                raise ValidationError("This page's link froze when it was first published. Links are promises.")
        self.content_html = render_page_html(self.content_md)
        super().save(*args, **kwargs)

    def publish(self, by):
        """Records the signature; ONLY-admins-publish is enforced at the view (§F)."""
        self.published_by = by
        if self.first_published_at is None:
            from django.utils import timezone

            self.first_published_at = timezone.now()
        return self.transition_to("published", extra_update_fields=("published_by", "first_published_at"))

    def restore(self):
        """archived → draft — but never by silently taking a slug back (§C)."""
        with transaction.atomic():
            taken = (
                type(self)
                .objects.select_for_update(of=("self",))
                .filter(community=self.community, slug=self.slug)
                .exclude(pk=self.pk)
                .exclude(status="archived")
                .exists()
            )
            if taken:
                raise ValidationError(
                    "Another page lives at this address now. Rename that page first, or start a new draft."
                )
            return self.transition_to("draft")

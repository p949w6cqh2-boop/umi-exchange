"""Offer model — umi:Offer entity."""

import uuid

from django.db import models
from django.utils import timezone


class Offer(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("matched", "Matched"),
        ("fulfilled", "Fulfilled"),
        ("withdrawn", "Withdrawn"),
    ]
    CONTACT_CHOICES = [("in_app", "In-app"), ("email", "Email"), ("phone", "Phone"), ("any", "Any")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="offers")
    offerer = models.ForeignKey("communities.Member", on_delete=models.CASCADE, related_name="offers")
    category = models.ForeignKey("communities.Category", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    availability = models.JSONField(default=dict, blank=True)
    radius = models.IntegerField(null=True, blank=True, help_text="km; null=unlimited")
    contact_pref = models.CharField(max_length=10, default="in_app", choices=CONTACT_CHOICES)
    status = models.CharField(max_length=12, default="active", choices=STATUS_CHOICES)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    custom = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "offers_offer"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/c/{self.community.slug}/offers/{self.id}/"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=90)
        super().save(*args, **kwargs)

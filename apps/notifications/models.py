"""Notification model — in-app notifications with email adapter."""
import uuid
from django.conf import settings
from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = [
        ("match_proposed", "Match Proposed"), ("match_accepted", "Match Accepted"),
        ("match_fulfilled", "Match Fulfilled"), ("match_cancelled", "Match Cancelled"),
        ("need_expiring", "Need Expiring"), ("need_expired", "Need Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    channels_sent = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.type}] {self.title}"

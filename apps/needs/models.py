"""Need model — umi:Need entity. Includes Fernet encryption for on_behalf_of."""

import uuid

from cryptography.fernet import Fernet
from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone


class Need(models.Model):
    URGENCY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("matched", "Matched"),
        ("fulfilled", "Fulfilled"),
        ("closed", "Closed"),
        ("expired", "Expired"),
    ]
    CONTACT_CHOICES = [("in_app", "In-app"), ("email", "Email"), ("phone", "Phone"), ("any", "Any")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="needs")
    requester = models.ForeignKey("communities.Member", on_delete=models.CASCADE, related_name="needs")
    category = models.ForeignKey("communities.Category", on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    urgency = models.CharField(max_length=10, default="medium", choices=URGENCY_CHOICES)
    neighborhood = models.CharField(max_length=100, blank=True)
    contact_pref = models.CharField(max_length=10, default="in_app", choices=CONTACT_CHOICES)
    status = models.CharField(max_length=10, default="open", choices=STATUS_CHOICES)
    on_behalf_of = models.BinaryField(null=True, blank=True)
    expires_at = models.DateTimeField()
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    custom = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "needs_need"
        indexes = [
            models.Index(fields=["community", "status", "urgency"]),
            models.Index(fields=["expires_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/c/{self.community.slug}/needs/{self.id}/"

    def set_on_behalf_of(self, plaintext):
        if plaintext and django_settings.ENCRYPTION_KEY:
            f = Fernet(django_settings.ENCRYPTION_KEY.encode())
            self.on_behalf_of = f.encrypt(plaintext.encode())

    def get_on_behalf_of(self):
        if self.on_behalf_of and django_settings.ENCRYPTION_KEY:
            f = Fernet(django_settings.ENCRYPTION_KEY.encode())
            return f.decrypt(bytes(self.on_behalf_of)).decode()
        return None

    def save(self, *args, **kwargs):
        if not self.expires_at:
            days = self.community.auto_expire_days if self.community_id else 30
            self.expires_at = timezone.now() + timezone.timedelta(days=days)
        super().save(*args, **kwargs)

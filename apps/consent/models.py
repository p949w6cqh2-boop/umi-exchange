"""Consent model — umi:Consent entity. Present at Core for contact preferences; full UI at Extended."""
import uuid

from django.conf import settings
from django.db import models


class Consent(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("revoked", "Revoked"), ("expired", "Expired")]
    METHOD_CHOICES = [("verbal", "Verbal"), ("written", "Written"), ("digital", "Digital")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents_given")
    granted_to = models.CharField(max_length=200)  # Community name or org identifier
    scope = models.JSONField(default=list)  # ["display_name", "email", "phone", "need_history"]
    purpose = models.CharField(max_length=500)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="digital")
    status = models.CharField(max_length=10, default="active", choices=STATUS_CHOICES)
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    custom = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "consent_consent"

    def __str__(self):
        return f"Consent by {self.participant} to {self.granted_to} ({self.status})"

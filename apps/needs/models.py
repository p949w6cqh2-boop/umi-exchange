"""Need model — umi:Need entity. on_behalf_of uses envelope encryption (§12.2)
via apps.people.crypto; read/write only through the on_behalf_of_name property."""

import uuid

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
    # Reversible coordinator action (moderation queue) — never a delete.
    moderation_hidden = models.BooleanField(default=False)
    # Federation (Stage B): per-record opt-in, default OFF. "federated" makes a
    # REDACTED row discoverable to linked communities that carry an active
    # consent; identity/contact/free-text never cross (see apps/federation).
    SHARE_CHOICES = [("local", "This community only"), ("federated", "Discoverable by linked communities")]
    share_scope = models.CharField(max_length=10, default="local", choices=SHARE_CHOICES)
    on_behalf_of = models.BinaryField(null=True, blank=True)
    # §12.2 — per-need DEK, wrapped by the master KEK (MultiFernet).
    # NULL + ciphertext present ⇒ legacy direct-KEK row (dual-read, D3).
    on_behalf_of_dek = models.BinaryField(null=True, blank=True, editable=False)
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

    @property
    def on_behalf_of_name(self) -> str | None:
        """Plaintext accessor — the ONLY way code should read/write this.
        Reads both schemes; writes always envelope (per-need DEK)."""
        from apps.people import crypto

        if not self.on_behalf_of:
            return None
        if self.on_behalf_of_dek:
            return crypto.envelope_decrypt_str(self.on_behalf_of, self.on_behalf_of_dek)
        return crypto.decrypt_str(self.on_behalf_of)  # legacy direct-KEK row

    @on_behalf_of_name.setter
    def on_behalf_of_name(self, value):
        from apps.people import crypto

        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "on_behalf_of_name takes PLAINTEXT — a write site is still passing "
                "pre-encrypted bytes; remove its inline crypto."
            )
        if value in (None, ""):
            self.on_behalf_of = None
            self.on_behalf_of_dek = None
            return
        self.on_behalf_of, self.on_behalf_of_dek = crypto.envelope_encrypt_str(str(value).strip())

    def save(self, *args, **kwargs):
        if not self.expires_at:
            days = self.community.auto_expire_days if self.community_id else 30
            self.expires_at = timezone.now() + timezone.timedelta(days=days)
        super().save(*args, **kwargs)

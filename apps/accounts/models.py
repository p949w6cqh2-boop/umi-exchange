"""Custom User model. Email is optional (protocol: participants without email can use username-only)."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(blank=True, null=True, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    # Consent for email: on by default for anyone who gives an address, but
    # always honoured — a neighbour can turn off notification emails from
    # account settings and the adapter stops sending to them.
    email_notifications = models.BooleanField(default=True)

    # Human verification (docs/specs/human-verification.md, A+C build): unverified
    # accounts can sign in and look, but the four write doors (join/post/propose)
    # are soft-gated. Two exits — the email link, or a coordinator's in-person
    # vouch — plus "backfill" for accounts that predate the gate.
    VERIFIED_VIA_CHOICES = [
        ("email", "Email link"),
        ("coordinator", "Coordinator vouch"),
        ("backfill", "Pre-gate account"),
    ]
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_via = models.CharField(max_length=12, blank=True, default="", choices=VERIFIED_VIA_CHOICES)

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "username"

    @property
    def is_human_verified(self):
        return self.verified_at is not None

    class Meta:
        db_table = "accounts_user"

    def clean(self):
        # AbstractUser.clean() normalizes a missing email to "", which the
        # unique constraint treats as a value — the second email-less signup
        # would fail with "already exists". Absent email is stored as NULL.
        super().clean()
        self.email = self.email or None

    def save(self, *args, **kwargs):
        # Writes that skip full_clean (e.g. UserManager.create_user, which
        # also normalizes None to "") must not store "" either.
        self.email = self.email or None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

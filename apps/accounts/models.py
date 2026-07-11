"""Custom User model. Email is optional (protocol: participants without email can use username-only)."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(blank=True, null=True, unique=True)
    phone = models.CharField(max_length=20, blank=True)

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "username"

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

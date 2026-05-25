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

    def __str__(self):
        return self.username

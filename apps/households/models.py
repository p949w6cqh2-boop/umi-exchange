"""Household model: parishes think in families, not individuals."""

import secrets
import string
import uuid

from django.conf import settings
from django.db import models


def generate_household_code():
    """Household join token. Uses a CSPRNG so codes cannot be guessed/predicted."""
    chars = string.ascii_uppercase + string.digits
    return "H-" + "".join(secrets.choice(chars) for _ in range(6))


class Household(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True, help_text='e.g., "The Rodriguez Family"')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_households"
    )
    join_code = models.CharField(max_length=10, unique=True, default=generate_household_code)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "households_household"

    def __str__(self):
        return self.name or f"Household {self.join_code}"

    @property
    def member_count(self):
        return self.members.count()

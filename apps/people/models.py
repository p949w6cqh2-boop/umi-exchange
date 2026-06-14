"""
people.Person — the shared subject-of-care identity (umi:Person, design §2.5/§3.2).

A Person is frequently NOT an account-holding User (the elderly neighbor a
coordinator visits). No plaintext name column exists anywhere; lists render
the short code, and names decrypt only for authorized viewers.
"""
import uuid

from django.conf import settings
from django.db import models

from . import crypto


class Person(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 🔒 Fernet — no plaintext name/contact/DOB columns exist
    display_name_enc = models.BinaryField(null=True, blank=True)
    contact_enc = models.BinaryField(null=True, blank=True)  # JSON {phone,email,address}
    dob_enc = models.BinaryField(null=True, blank=True)

    linked_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="person_record",
    )
    household = models.ForeignKey(
        "households.Household", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="persons",
    )
    created_in_community = models.ForeignKey(
        "communities.Community", on_delete=models.PROTECT, related_name="persons",
    )
    created_by = models.ForeignKey(
        "communities.Member", on_delete=models.PROTECT, related_name="persons_created",
    )
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="merge_sources",
    )
    custom = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "people_person"
        indexes = [
            models.Index(fields=["created_in_community"], name="people_person_comm_idx"),
            models.Index(fields=["household"], name="people_person_hh_idx"),
        ]

    # ---- decrypt-on-access properties ----------------------------------
    @property
    def display_name(self) -> str | None:
        return crypto.decrypt_str(self.display_name_enc)

    @display_name.setter
    def display_name(self, value: str | None):
        self.display_name_enc = crypto.encrypt_str(value)

    @property
    def contact(self) -> dict | None:
        return crypto.decrypt_json(self.contact_enc)

    @contact.setter
    def contact(self, value: dict | None):
        self.contact_enc = crypto.encrypt_json(value)

    @property
    def dob(self) -> str | None:
        return crypto.decrypt_str(self.dob_enc)

    @dob.setter
    def dob(self, value: str | None):
        self.dob_enc = crypto.encrypt_str(value)

    # ---- safe, non-PII renderings --------------------------------------
    @property
    def short_code(self) -> str:
        return str(self.id)[:8].upper()

    @property
    def initials(self) -> str:
        """e.g. 'M.G.' — the only name-derived string that may be cached
        offline or shown in lists before authorization (design §3.6)."""
        name = self.display_name or ""
        parts = [p for p in name.split() if p]
        return ".".join(p[0].upper() for p in parts[:2]) + "." if parts else "—"

    def __str__(self):  # never leak the name in logs/admin reprs
        return f"Person {self.short_code}"

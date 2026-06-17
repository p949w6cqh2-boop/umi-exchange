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

    # 🔒 Fernet — no plaintext name/contact/DOB columns exist.
    # Envelope encryption: ciphertext + a per-record DEK (wrapped by the KEK
    # list) → enables crypto-shred. `*_enc_dek IS NULL` ⇒ legacy direct-KEK.
    display_name_enc = models.BinaryField(null=True, blank=True)
    display_name_enc_dek = models.BinaryField(null=True, blank=True, editable=False)
    contact_enc = models.BinaryField(null=True, blank=True)  # JSON {phone,email,address}
    contact_enc_dek = models.BinaryField(null=True, blank=True, editable=False)
    dob_enc = models.BinaryField(null=True, blank=True)
    dob_enc_dek = models.BinaryField(null=True, blank=True, editable=False)

    linked_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="person_record",
    )
    household = models.ForeignKey(
        "households.Household",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persons",
    )
    created_in_community = models.ForeignKey(
        "communities.Community",
        on_delete=models.PROTECT,
        related_name="persons",
    )
    created_by = models.ForeignKey(
        "communities.Member",
        on_delete=models.PROTECT,
        related_name="persons_created",
    )
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
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
    # Dual-read: envelope when a DEK is present, else legacy direct-KEK
    # (legacy branch removed in the Person Stage E contract once the prod
    # census shows legacy=0). Setters always envelope-write BOTH columns.
    @property
    def display_name(self) -> str | None:
        if not self.display_name_enc:
            return None
        if self.display_name_enc_dek:
            return crypto.envelope_decrypt_str(self.display_name_enc, self.display_name_enc_dek)
        return crypto.decrypt_str(self.display_name_enc)

    @display_name.setter
    def display_name(self, value: str | None):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError("display_name takes PLAINTEXT — a write site is passing pre-encrypted bytes.")
        if value in (None, ""):
            self.display_name_enc = None
            self.display_name_enc_dek = None
            return
        self.display_name_enc, self.display_name_enc_dek = crypto.envelope_encrypt_str(str(value))

    @property
    def contact(self) -> dict | None:
        if not self.contact_enc:
            return None
        if self.contact_enc_dek:
            return crypto.envelope_decrypt_json(self.contact_enc, self.contact_enc_dek)
        return crypto.decrypt_json(self.contact_enc)

    @contact.setter
    def contact(self, value: dict | None):
        if value in (None, "", {}, []):
            self.contact_enc = None
            self.contact_enc_dek = None
            return
        self.contact_enc, self.contact_enc_dek = crypto.envelope_encrypt_json(value)

    @property
    def dob(self) -> str | None:
        if not self.dob_enc:
            return None
        if self.dob_enc_dek:
            return crypto.envelope_decrypt_str(self.dob_enc, self.dob_enc_dek)
        return crypto.decrypt_str(self.dob_enc)

    @dob.setter
    def dob(self, value: str | None):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError("dob takes PLAINTEXT — a write site is passing pre-encrypted bytes.")
        if value in (None, ""):
            self.dob_enc = None
            self.dob_enc_dek = None
            return
        self.dob_enc, self.dob_enc_dek = crypto.envelope_encrypt_str(str(value))

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

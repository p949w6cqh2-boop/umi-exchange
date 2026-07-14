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


class PersonQuerySet(models.QuerySet):
    def by_name(self, name: str | None, *, community):
        """Exact-name lookup via the §12.3 blind index — equality only,
        normalization applied to the query. `community` is a REQUIRED kwarg:
        an unscoped Person lookup is the cross-community leak class the PR
        checklist bans, so scoping is the method's own job, not the caller's.
        Empty query matches nothing (rows without a name carry a NULL bidx,
        never an empty-string HMAC)."""
        bidx = crypto.name_blind_index(name)
        if bidx is None:
            return self.none()
        return self.filter(created_in_community=community, name_bidx=bidx)


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

    # §12.3 blind index: HMAC-SHA256(BLIND_INDEX_KEY, normalized name).
    # Equality lookups only (PersonQuerySet.by_name) — NEVER authorization.
    # Kept in sync by the display_name setter; crypto-shred MUST leave this
    # NULL or the erased name stays equality-testable. Not derivable from
    # the encryption keys — BLIND_INDEX_KEY is a separate secret.
    # ⚠ Bulk erasure bypasses the setter: any retention sweep that nulls
    # display_name_enc/_dek via queryset.update() (the needs/casework shred
    # idiom) MUST include name_bidx=None in the same update(), or the erased
    # name stays equality-testable. `person_bidx_status` reports such strays.
    name_bidx = models.BinaryField(null=True, blank=True, editable=False)

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

    objects = PersonQuerySet.as_manager()

    class Meta:
        db_table = "people_person"
        indexes = [
            models.Index(fields=["created_in_community"], name="people_person_comm_idx"),
            models.Index(fields=["household"], name="people_person_hh_idx"),
            models.Index(fields=["name_bidx"], name="people_person_name_bidx"),
        ]

    # ---- decrypt-on-access properties ----------------------------------
    # Envelope-only (Stage E): the legacy direct-KEK read branch was removed
    # after the prod census reported legacy=0. A populated ciphertext with no
    # DEK now fails loud. Setters always envelope-write BOTH columns.
    @property
    def display_name(self) -> str | None:
        if not self.display_name_enc:
            return None
        if not self.display_name_enc_dek:
            raise ValueError(
                "Person.display_name has ciphertext but no DEK — run the people 0003 "
                "envelope backfill and check `people_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.display_name_enc, self.display_name_enc_dek)

    @display_name.setter
    def display_name(self, value: str | None):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError("display_name takes PLAINTEXT — a write site is passing pre-encrypted bytes.")
        if value in (None, ""):
            # Clearing is also the crypto-shred path: null the bidx BEFORE any
            # key lookup so erasure never depends on BLIND_INDEX_KEY being set.
            self.display_name_enc = None
            self.display_name_enc_dek = None
            self.name_bidx = None
            return
        # Bidx FIRST — it can raise (missing/shared BLIND_INDEX_KEY), and a
        # raise must leave the instance untouched, never half-updated.
        bidx = crypto.name_blind_index(str(value))
        self.display_name_enc, self.display_name_enc_dek = crypto.envelope_encrypt_str(str(value))
        self.name_bidx = bidx

    @property
    def contact(self) -> dict | None:
        if not self.contact_enc:
            return None
        if not self.contact_enc_dek:
            raise ValueError(
                "Person.contact has ciphertext but no DEK — run the people 0003 "
                "envelope backfill and check `people_envelope_status`."
            )
        return crypto.envelope_decrypt_json(self.contact_enc, self.contact_enc_dek)

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
        if not self.dob_enc_dek:
            raise ValueError(
                "Person.dob has ciphertext but no DEK — run the people 0003 "
                "envelope backfill and check `people_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.dob_enc, self.dob_enc_dek)

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

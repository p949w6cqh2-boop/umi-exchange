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

    # Email OWNERSHIP, kept apart from human verification on purpose
    # (docs/specs/email-confirmation.md, issue #172). `verified_via` answers "is this a
    # human?" — and a coordinator vouch is the strongest answer to that while proving
    # nothing about any inbox. So an account can be fully verified and still carry an
    # address nobody has shown they read. Set ONLY when a person clicks a link sent to
    # the address; cleared by save() whenever the address changes without one.
    email_confirmed_at = models.DateTimeField(null=True, blank=True)
    # Phone OWNERSHIP, the same rule as email (docs/specs/phone-codes.md): set only when the
    # person types back a code sent to the number; cleared by save() whenever the number
    # changes without one. A code to get back in goes only to a proven number.
    phone_confirmed_at = models.DateTimeField(null=True, blank=True)

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "username"

    @property
    def is_human_verified(self):
        return self.verified_at is not None

    @property
    def deliverable_email(self):
        """The address, if and only if its owner has proven they read it; else None.

        EVERY sender reads this, never `.email` — password reset, username recovery,
        notifications, the casework digest, the contact reveal. A rule each call site
        must remember is not a rule: this exists so the next sender cannot trust an
        unproven address by accident, and tests/test_email_confirmation.py fails the
        build if one tries. The single exception is the confirmation link itself,
        which must go to the unproven address because proving it is the point.
        """
        return self.email if self.email and self.email_confirmed_at else None

    @property
    def deliverable_phone(self):
        """The number, if and only if its owner has proven it with a code; else None."""
        return self.phone if self.phone and self.phone_confirmed_at else None

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
        self._clear_confirmation_if_address_changed(kwargs)
        self._clear_phone_confirmation_if_number_changed(kwargs)
        super().save(*args, **kwargs)

    def _clear_phone_confirmation_if_number_changed(self, save_kwargs):
        """The phone twin of the rule below: a proof belongs to the number it proved."""
        update_fields = save_kwargs.get("update_fields")
        if update_fields is not None and "phone" not in update_fields:
            return
        if self._state.adding or self.pk is None:
            return
        prev = type(self).objects.filter(pk=self.pk).values("phone", "phone_confirmed_at").first()
        if prev is None or (prev["phone"] or "") == (self.phone or ""):
            return
        if self.phone_confirmed_at != prev["phone_confirmed_at"]:
            return  # the caller is writing a fresh proof for the new number
        self.phone_confirmed_at = None

    def _clear_confirmation_if_address_changed(self, save_kwargs):
        """A proof belongs to the address it proved. Changing the address WITHOUT a
        fresh confirmation clears it; changing it WITH one (ConfirmAddEmailView writes
        both in one save) keeps it.

        Enforced here rather than in each view because the next writer will not come
        through our views — an admin page, a ModelForm, a management command.
        Known bypass, stated rather than hidden: QuerySet.update() skips save(). None
        exists in apps/ today (checked 2026-09-26).
        """
        update_fields = save_kwargs.get("update_fields")
        if update_fields is not None and "email" not in update_fields:
            return  # the address is not being written; nothing to compare (every login lands here)
        if self._state.adding or self.pk is None:
            return  # a new row has no previous address to have proven
        prev = type(self).objects.filter(pk=self.pk).values("email", "email_confirmed_at").first()
        if prev is None or (prev["email"] or None) == self.email:
            return
        if self.email_confirmed_at != prev["email_confirmed_at"]:
            return  # the caller is writing a fresh proof for the new address
        self.email_confirmed_at = None
        if update_fields is not None and "email_confirmed_at" not in update_fields:
            save_kwargs["update_fields"] = [*update_fields, "email_confirmed_at"]

    def __str__(self):
        return self.username


class RecoveryCredential(models.Model):
    """One-time credential: a secret tied to a user, hashed at rest, single-use, per-purpose
    expiry (docs/specs/account-recovery.md §One credential model, F0-a).

    One table for every "hand someone a secret that lets them back in" path — the paper
    recovery code, the coordinator-read reset, the admin unlock, the claim link — so the
    properties are enforced once, in apps/accounts/credentials.py, not per feature.
    The plaintext is never stored: only its SHA-256.
    """

    PURPOSE_RECOVERY_CODE = "recovery_code"
    PURPOSE_COORDINATOR_RESET = "coordinator_reset"
    PURPOSE_ADMIN_UNLOCK = "admin_unlock"
    PURPOSE_CLAIM = "claim"
    PURPOSE_CHOICES = [
        (PURPOSE_RECOVERY_CODE, "Printed recovery code"),
        (PURPOSE_COORDINATOR_RESET, "Coordinator-issued reset"),
        (PURPOSE_ADMIN_UNLOCK, "Admin unlock"),
        (PURPOSE_CLAIM, "Account claim link"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_credentials")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    token_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # null = never (recovery_code only)
    used_at = models.DateTimeField(null=True, blank=True)
    # Set when a newer credential of the same purpose replaced this one before it was used —
    # re-issuing a lost paper code must kill the lost one, or "lost" means "still live".
    revoked_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Denormalized so the record still says who issued it after that Member row is gone.
    issued_by_label = models.CharField(max_length=150, blank=True, default="")
    # Why it was issued (the admin unlock's required reason). Kept HERE, on a row that can be
    # redacted, and never in the append-only audit log (tests/test_audit_pii_hygiene.py doctrine).
    note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "accounts_recovery_credential"
        indexes = [models.Index(fields=["user", "purpose"], name="recovery_cred_user_purpose")]

    def __str__(self):
        return f"{self.purpose} for {self.user_id}"


class GeoSignupCount(models.Model):
    """Geolocking Phase 0 (docs/specs/geolocking.md): sign-up ATTEMPTS per country.

    Integers only. No IP, no user, no request detail: the one question it answers is "where do
    sign-up attempts come from?", in aggregate. "--" is the bucket for unknown or unreadable.
    """

    country = models.CharField(max_length=2, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_geo_signup_count"
        ordering = ["-count"]

    def __str__(self):
        return f"{self.country}: {self.count}"

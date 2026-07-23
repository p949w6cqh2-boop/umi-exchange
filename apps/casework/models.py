"""
Lake 2 data model (design §3.3): CaseFile, CaseNote, FollowUp, WarmHandoff,
CaseAccessGrant. UUID PKs throughout; 🔒 fields are Fernet BinaryFields with
decrypt-on-access properties; state machines per §3.5 via StateMachineMixin.
"""

import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.people import crypto

from .state import StateMachineMixin


class CaseFile(StateMachineMixin, models.Model):
    STATUS_OPEN, STATUS_MONITORING, STATUS_CLOSED = "open", "monitoring", "closed"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_MONITORING, "Monitoring"), (STATUS_CLOSED, "Closed")]
    SENS_STANDARD, SENS_RESTRICTED = "standard", "restricted"
    SENSITIVITY_CHOICES = [(SENS_STANDARD, "Standard"), (SENS_RESTRICTED, "Restricted")]

    VALID_TRANSITIONS = {
        "open": {"monitoring", "closed"},
        "monitoring": {"open", "closed"},
        "closed": {"open"},  # reopen — admin only (enforced in view)
    }
    TRANSITION_TIMESTAMPS = {"closed": "closed_at"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.PROTECT, related_name="case_files")
    subject_person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="case_files")
    opened_by = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="cases_opened")
    assigned_to = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="cases_assigned"
    )

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_OPEN)
    # Restricted by default (threat-model must-fix #4, Jasiah Williams 2026-07-11):
    # coordinators read ALL standard-case PII by design, so an unclassified
    # case must fail safe. Intake consciously downgrades to standard.
    sensitivity = models.CharField(max_length=12, choices=SENSITIVITY_CHOICES, default=SENS_RESTRICTED)

    # Consent-first opening (§3.6): consent may be null ONLY with the
    # emergency flag — enforced by a DB CheckConstraint below.
    consent = models.ForeignKey(
        "consent.Consent", null=True, blank=True, on_delete=models.PROTECT, related_name="case_files"
    )
    emergency_opened = models.BooleanField(default=False)
    # Acute DV-safety narrative — envelope-encrypted at rest exactly like
    # summary/body/detail (H-1). Read/write only via the property below.
    emergency_justification_enc = models.BinaryField(null=True, blank=True)  # 🔒
    emergency_justification_enc_dek = models.BinaryField(null=True, blank=True, editable=False)

    primary_needs = models.JSONField(default=list, blank=True)
    intake_date = models.DateField(default=timezone.localdate)
    physical_ref = models.CharField(max_length=100, blank=True, default="")
    summary_enc = models.BinaryField(null=True, blank=True)  # 🔒
    summary_enc_dek = models.BinaryField(null=True, blank=True, editable=False)

    closed_at = models.DateTimeField(null=True, blank=True)
    custom = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "casework_case_file"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["community", "status"], name="cw_cf_comm_status_idx"),
            models.Index(fields=["assigned_to", "status"], name="cw_cf_assignee_idx"),
            models.Index(fields=["subject_person"], name="cw_cf_subject_idx"),
            models.Index(fields=["community", "sensitivity"], name="cw_cf_sens_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(consent__isnull=False) | models.Q(emergency_opened=True),
                name="cw_cf_consent_or_emergency",
            ),
        ]

    @property
    def summary(self) -> str | None:
        # Envelope-only (Stage E): the legacy direct-KEK read branch was removed
        # after the prod census reported legacy=0. A populated ciphertext with no
        # DEK is now a hard error, not a silent legacy read.
        if not self.summary_enc:
            return None
        if not self.summary_enc_dek:
            raise ValueError(
                f"{type(self).__name__}.summary has ciphertext but no DEK — run the "
                "0004 envelope backfill and check `casework_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.summary_enc, self.summary_enc_dek)

    @summary.setter
    def summary(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "summary takes PLAINTEXT — a write site is passing pre-encrypted bytes; remove its inline crypto."
            )
        if value in (None, ""):
            self.summary_enc = None
            self.summary_enc_dek = None
            return
        self.summary_enc, self.summary_enc_dek = crypto.envelope_encrypt_str(str(value))

    @property
    def emergency_justification(self) -> str | None:
        # Same envelope-only contract as summary: ciphertext without a DEK is a
        # hard error, not a silent read.
        if not self.emergency_justification_enc:
            return None
        if not self.emergency_justification_enc_dek:
            raise ValueError(
                f"{type(self).__name__}.emergency_justification has ciphertext but no DEK — run the "
                "0006 emergency_justification backfill and check `casework_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.emergency_justification_enc, self.emergency_justification_enc_dek)

    @emergency_justification.setter
    def emergency_justification(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "emergency_justification takes PLAINTEXT — a write site is passing pre-encrypted bytes; "
                "remove its inline crypto."
            )
        if value in (None, ""):
            self.emergency_justification_enc = None
            self.emergency_justification_enc_dek = None
            return
        self.emergency_justification_enc, self.emergency_justification_enc_dek = crypto.envelope_encrypt_str(str(value))

    @property
    def short_code(self) -> str:
        return str(self.id)[:8].upper()

    def consent_is_active(self) -> bool:
        c = self.consent
        if c is None:
            return False
        if getattr(c, "status", "active") != "active" or c.revoked_at:
            return False
        return not (c.expires_at and c.expires_at <= timezone.now())

    def __str__(self):
        return f"Case {self.short_code}"


class CaseNote(StateMachineMixin, models.Model):
    KIND_CHOICES = [
        ("visit", "Home visit"),
        ("call", "Phone call"),
        ("office", "Office visit"),
        ("aid", "Aid given"),
        ("handoff", "Handoff"),
        ("system", "System"),
    ]
    LOCATION_CHOICES = [("home", "Home"), ("office", "Office"), ("phone", "Phone"), ("other", "Other")]
    # Quick-tap actions — the 3-minute form (Manual §8.2, design §3.3)
    ACTIONS = [
        ("food_provided", "Food provided"),
        ("utility_referral", "Utility referral"),
        ("rent_assist", "Rent assistance"),
        ("prayer", "Prayer"),
        ("info_provided", "Information provided"),
        ("other", "Other"),
    ]

    STATUS_DRAFT, STATUS_FINAL, STATUS_DISCARDED = "draft", "final", "discarded"
    VALID_TRANSITIONS = {
        "draft": {"final", "discarded"},  # author only (enforced in view)
        "final": set(),  # immutable; amendments are new rows
        "discarded": set(),
    }
    TRANSITION_TIMESTAMPS = {"final": "finalized_at"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(CaseFile, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="case_notes")
    co_visitor = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="co_visited_notes"
    )

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="visit")
    occurred_at = models.DateTimeField(default=timezone.now)
    duration_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    location_kind = models.CharField(max_length=10, choices=LOCATION_CHOICES, default="home")
    actions = models.JSONField(default=list, blank=True)

    # Deliberately plaintext for aggregation (design §3.3): the bare number,
    # coordinator-scoped, without narrative. The narrative is encrypted.
    aid_value_cents = models.PositiveIntegerField(null=True, blank=True)
    aid_currency = models.CharField(max_length=3, default="USD")

    body_enc = models.BinaryField(null=True, blank=True)  # 🔒
    body_enc_dek = models.BinaryField(null=True, blank=True, editable=False)

    status = models.CharField(
        max_length=10,
        default=STATUS_DRAFT,
        choices=[("draft", "Draft"), ("final", "Final"), ("discarded", "Discarded")],
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    amends = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="amendments")

    client_uuid = models.UUIDField(null=True, blank=True, unique=True)  # offline idempotency
    related_need = models.ForeignKey(
        "needs.Need", null=True, blank=True, on_delete=models.SET_NULL, related_name="case_notes"
    )
    related_match = models.ForeignKey(
        "matches.Match", null=True, blank=True, on_delete=models.SET_NULL, related_name="case_notes"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # last-touched → drives the "stale draft" window

    class Meta:
        db_table = "casework_case_note"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["case", "-occurred_at"], name="cw_note_case_time_idx"),
            models.Index(fields=["author", "status"], name="cw_note_author_idx"),
        ]

    # ---- immutability guards (A7: model-level, mirroring the audit pattern)
    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            old_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if old_status == self.STATUS_FINAL:
                raise ValidationError("Finalized notes are immutable. Create an amendment instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.STATUS_DRAFT:
            raise ValidationError("Only draft notes can be deleted; use discard/amend.")
        return super().delete(*args, **kwargs)

    @property
    def body(self) -> str | None:
        # Envelope-only (Stage E): legacy direct-KEK read branch removed.
        if not self.body_enc:
            return None
        if not self.body_enc_dek:
            raise ValueError(
                "CaseNote.body has ciphertext but no DEK — run the 0004 envelope "
                "backfill and check `casework_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.body_enc, self.body_enc_dek)

    @body.setter
    def body(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "body takes PLAINTEXT — a write site is passing pre-encrypted bytes; remove its inline crypto."
            )
        if value in (None, ""):
            self.body_enc = None
            self.body_enc_dek = None
            return
        self.body_enc, self.body_enc_dek = crypto.envelope_encrypt_str(str(value))

    @property
    def aid_value_dollars(self) -> str | None:
        if self.aid_value_cents is None:
            return None
        return f"{self.aid_value_cents / 100:.2f}"

    @property
    def duplicate_suspects(self):
        """Computed live (no schema flag): same case + author within ±60 min —
        the manual-merge prompt of design §3.6."""
        if not self.occurred_at:
            return type(self).objects.none()
        window = timedelta(minutes=60)
        return (
            type(self)
            .objects.filter(
                case=self.case,
                author=self.author,
                occurred_at__gte=self.occurred_at - window,
                occurred_at__lte=self.occurred_at + window,
            )
            .exclude(pk=self.pk)
            .exclude(status=self.STATUS_DISCARDED)
        )

    def __str__(self):
        return f"Note {str(self.id)[:8]} ({self.kind}/{self.status})"


class FollowUp(StateMachineMixin, models.Model):
    VALID_TRANSITIONS = {
        "open": {"done", "cancelled"},  # assignee, creator, or admin
        "done": set(),
        "cancelled": set(),
    }
    TRANSITION_TIMESTAMPS = {"done": "done_at"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(CaseFile, on_delete=models.CASCADE, related_name="followups")
    created_by = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="followups_created")
    assigned_to = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="followups_assigned")

    # Plaintext BY DESIGN, coached non-sensitive ("Check in re: utility bill",
    # never a name) — the daily digest must render without decrypting (§3.6).
    title = models.CharField(max_length=200)
    detail_enc = models.BinaryField(null=True, blank=True)  # 🔒
    detail_enc_dek = models.BinaryField(null=True, blank=True, editable=False)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, default="open", choices=[("open", "Open"), ("done", "Done"), ("cancelled", "Cancelled")]
    )
    done_at = models.DateTimeField(null=True, blank=True)
    source_note = models.ForeignKey(
        CaseNote, null=True, blank=True, on_delete=models.SET_NULL, related_name="followups"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "casework_follow_up"
        ordering = ["due_date"]
        indexes = [
            models.Index(fields=["assigned_to", "status", "due_date"], name="cw_fu_assignee_idx"),
            models.Index(fields=["case", "status"], name="cw_fu_case_idx"),
            models.Index(fields=["due_date", "status"], name="cw_fu_due_idx"),
        ]

    @property
    def detail(self) -> str | None:
        # Envelope-only (Stage E): legacy direct-KEK read branch removed.
        if not self.detail_enc:
            return None
        if not self.detail_enc_dek:
            raise ValueError(
                "FollowUp.detail has ciphertext but no DEK — run the 0004 envelope "
                "backfill and check `casework_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.detail_enc, self.detail_enc_dek)

    @detail.setter
    def detail(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "detail takes PLAINTEXT — a write site is passing pre-encrypted bytes; remove its inline crypto."
            )
        if value in (None, ""):
            self.detail_enc = None
            self.detail_enc_dek = None
            return
        self.detail_enc, self.detail_enc_dek = crypto.envelope_encrypt_str(str(value))

    def __str__(self):
        return f"FollowUp {str(self.id)[:8]} ({self.status})"


class WarmHandoff(StateMachineMixin, models.Model):
    VALID_TRANSITIONS = {
        "pending": {"acknowledged"},  # to_member only (enforced in view)
        "acknowledged": set(),
    }
    TRANSITION_TIMESTAMPS = {"acknowledged": "acknowledged_at"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(CaseFile, on_delete=models.CASCADE, related_name="handoffs")
    from_member = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="handoffs_sent")
    to_member = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="handoffs_received")
    summary_enc = models.BinaryField(null=True, blank=True)  # 🔒
    summary_enc_dek = models.BinaryField(null=True, blank=True, editable=False)
    status = models.CharField(
        max_length=12, default="pending", choices=[("pending", "Pending"), ("acknowledged", "Acknowledged")]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "casework_warm_handoff"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["to_member", "status"], name="cw_ho_to_status_idx"),
        ]

    @property
    def summary(self) -> str | None:
        # Envelope-only (Stage E): the legacy direct-KEK read branch was removed
        # after the prod census reported legacy=0. A populated ciphertext with no
        # DEK is now a hard error, not a silent legacy read.
        if not self.summary_enc:
            return None
        if not self.summary_enc_dek:
            raise ValueError(
                f"{type(self).__name__}.summary has ciphertext but no DEK — run the "
                "0004 envelope backfill and check `casework_envelope_status`."
            )
        return crypto.envelope_decrypt_str(self.summary_enc, self.summary_enc_dek)

    @summary.setter
    def summary(self, value):
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(
                "summary takes PLAINTEXT — a write site is passing pre-encrypted bytes; remove its inline crypto."
            )
        if value in (None, ""):
            self.summary_enc = None
            self.summary_enc_dek = None
            return
        self.summary_enc, self.summary_enc_dek = crypto.envelope_encrypt_str(str(value))

    def __str__(self):
        return f"Handoff {str(self.id)[:8]} ({self.status})"


class CaseAccessGrant(models.Model):
    ROLE_CHOICES = [("viewer", "Viewer"), ("contributor", "Contributor")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(CaseFile, on_delete=models.CASCADE, related_name="grants")
    member = models.ForeignKey("communities.Member", on_delete=models.CASCADE, related_name="case_grants")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default="viewer")
    granted_by = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="case_grants_given")
    reason = models.CharField(max_length=200)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "casework_access_grant"
        indexes = [models.Index(fields=["member"], name="cw_grant_member_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "member"],
                condition=models.Q(revoked_at__isnull=True),
                name="cw_grant_one_active_per_member",
            ),
        ]

    @property
    def is_active(self) -> bool:
        if self.revoked_at:
            return False
        return not (self.expires_at and self.expires_at <= timezone.now())

    def __str__(self):
        return f"Grant {str(self.id)[:8]} ({self.role})"

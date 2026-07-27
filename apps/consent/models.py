"""Consent model — umi:Consent entity. Present at Core for contact preferences; full UI at Extended."""

import uuid

from django.conf import settings
from django.db import models


class Consent(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("revoked", "Revoked"), ("expired", "Expired")]
    METHOD_CHOICES = [("verbal", "Verbal"), ("written", "Written"), ("digital", "Digital")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # WHO consented. Exactly one of these is set (see the Meta constraint).
    #
    # `participant` is the ordinary case: a person with an account, speaking for
    # themselves. `subject_person` exists because most people this app holds data
    # about have no account at all — Person.linked_user is never assigned in the
    # running app, so every casework subject is a third party. Before this field
    # existed the only way to store their consent was to put the COORDINATOR in as
    # participant, which is precisely what the protocol forbids (docs/protocol/
    # spec.md §4.1, "Coordinators MUST NOT consent on a member's behalf") and left
    # the actual subject unable to see or revoke it.
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="consents_given", null=True, blank=True
    )
    subject_person = models.ForeignKey(
        "people.Person", on_delete=models.PROTECT, related_name="consents_about", null=True, blank=True
    )
    # WHO WROTE IT DOWN — a witness, never the grantor. Recording what a neighbour
    # said out loud is an honest act; standing in for them is not.
    recorded_by = models.ForeignKey(
        "communities.Member", on_delete=models.PROTECT, related_name="consents_recorded", null=True, blank=True
    )
    granted_to = models.CharField(max_length=200)  # Community name or org identifier

    # §10.2 — structured grantee: WHO holds this consent, checkably.
    # granted_to stays as the human-readable label (alias: .grantee_label).
    GRANTEE_TYPES = [
        ("community", "Community"),
        ("organization", "Organization"),
        ("member", "Member"),
        ("other", "Other"),
    ]
    grantee_type = models.CharField(max_length=20, choices=GRANTEE_TYPES, default="community")
    grantee_id = models.UUIDField(null=True, blank=True)
    scope = models.JSONField(default=list)  # ["display_name", "email", "phone", "need_history"]
    purpose = models.CharField(max_length=500)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="digital")
    status = models.CharField(max_length=10, default="active", choices=STATUS_CHOICES)
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    custom = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "consent_consent"
        indexes = [
            models.Index(fields=["grantee_type", "grantee_id"], name="consent_grantee_idx"),
            models.Index(fields=["subject_person"], name="consent_subject_person_idx"),
        ]
        constraints = [
            # Exactly one grantor. Both set means we do not know whose consent this
            # is; neither set means the record names nobody at all.
            models.CheckConstraint(
                condition=(
                    models.Q(participant__isnull=False, subject_person__isnull=True)
                    | models.Q(participant__isnull=True, subject_person__isnull=False)
                ),
                name="consent_exactly_one_grantor",
            ),
        ]

    def __str__(self):
        return f"Consent by {self.subject_label} to {self.granted_to} ({self.status})"

    @property
    def subject_label(self) -> str:
        """Who this consent is about, safe to render anywhere.

        Never the decrypted legal name: a Person's name is envelope-encrypted and
        belongs only on surfaces that pass case_access(). Initials are what the
        rest of the casework UI already uses in lists.
        """
        if self.participant_id:
            return self.participant.get_username()
        if self.subject_person_id:
            return self.subject_person.initials
        return "unknown"

    @property
    def is_on_behalf(self) -> bool:
        """True when the person this is about never had an account to consent with."""
        return self.subject_person_id is not None

    @property
    def grantee_label(self) -> str:
        return self.granted_to

    @grantee_label.setter
    def grantee_label(self, value: str):
        self.granted_to = value

    def is_currently_active(self) -> bool:
        from django.utils import timezone

        if self.status != "active" or self.revoked_at:
            return False
        return not (self.expires_at and self.expires_at <= timezone.now())

    def covers(self, *, grantee_type: str, grantee_id, scopes=()) -> bool:
        """The §10.2 authorization check: is this consent active, held by THIS
        grantee, and does its scope include every requested token? Legacy rows
        (grantee_id NULL, label-era) match on type alone."""
        if not self.is_currently_active():
            return False
        if self.grantee_type != grantee_type:
            return False
        if self.grantee_id and str(self.grantee_id) != str(grantee_id):
            return False
        return set(scopes) <= set(self.scope or [])

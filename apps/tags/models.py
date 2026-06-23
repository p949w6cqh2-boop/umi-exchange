"""
Member Tags & Verification — data model.

Tag:       per-community tag catalog (slug, label, category, tier, visibility).
MemberTag: assignment with a state machine (self_claimed → pending → verified |
           rejected; verified → revoked), evidence/justification, verified_by.

Safety-critical: false claims of authority (e.g. "priest") can exploit vulnerable
people. Verified tags are visually unmistakable from self-reported ones.
Every state change is append-only audited (AuditLog.log).
"""

import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

from apps.audit.models import AuditLog
from apps.common.state import StateMachineMixin

# ── Visibility ordering (explicit, per user requirement) ──────────────
# "public" = signed-in community members only; logged-out see nothing.
VISIBILITY_CHOICES = [
    ("public", "All community members"),
    ("community", "Community members"),  # same as public today; future: federation distinction
    ("coordinators_only", "Coordinators only"),
]
VISIBILITY_ORDER = {"public": 0, "community": 1, "coordinators_only": 2}


# ── Tag categories ────────────────────────────────────────────────────
CATEGORY_CHOICES = [
    ("authority", "Authority"),  # priest, deacon, religious
    ("ministry", "Ministry"),  # SVdP, lector, catechist, EM
    ("professional", "Professional"),  # nurse, contractor
    ("life_status", "Life Status"),  # homeowner, married, senior, veteran
    ("custom", "Custom"),
]

# ── Tag verification tiers ────────────────────────────────────────────
TIER_CHOICES = [
    ("self_serve", "Self-serve (no verification needed)"),
    ("coordinator_verified", "Coordinator or Admin verifies"),
    ("admin_verified", "Admin only verifies"),
]


class Tag(models.Model):
    """Per-community tag definition (the catalog)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="tags")
    slug = models.SlugField(max_length=50)
    label = models.CharField(max_length=80)
    icon = models.CharField(max_length=10, blank=True, default="")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="custom")
    tier = models.CharField(max_length=25, choices=TIER_CHOICES, default="self_serve")
    public_when_verified = models.BooleanField(
        default=False,
        help_text="If True, this tag is visible to ALL community members when verified.",
    )
    default_visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="community")
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tags_tag"
        unique_together = [("community", "slug")]
        ordering = ["sort_order", "label"]

    def __str__(self):
        return f"{self.icon} {self.label}".strip()


# ── Default tags seeded per community ─────────────────────────────────
DEFAULT_TAGS = [
    # (slug, label, icon, category, tier, public_when_verified, default_visibility)
    ("priest", "Priest", "⛪", "authority", "admin_verified", True, "public"),
    ("deacon", "Deacon", "⛪", "authority", "admin_verified", True, "public"),
    ("religious", "Religious (Sister/Brother)", "✝️", "authority", "admin_verified", True, "public"),
    ("svdp-member", "SVdP Member", "💚", "ministry", "coordinator_verified", True, "community"),
    ("eucharistic-minister", "Eucharistic Minister", "🍞", "ministry", "coordinator_verified", False, "community"),
    ("lector", "Lector", "📖", "ministry", "coordinator_verified", False, "community"),
    ("catechist", "Catechist", "📚", "ministry", "coordinator_verified", False, "community"),
    ("nurse", "Nurse / Medical", "🏥", "professional", "coordinator_verified", False, "coordinators_only"),
    (
        "licensed-contractor",
        "Licensed Contractor",
        "🔧",
        "professional",
        "coordinator_verified",
        False,
        "coordinators_only",
    ),
    ("homeowner", "Homeowner", "🏠", "life_status", "self_serve", False, "community"),
    ("married", "Married", "💍", "life_status", "self_serve", False, "community"),
    ("senior", "Senior (65+)", "🧓", "life_status", "self_serve", False, "community"),
    ("veteran", "Veteran", "🎖️", "life_status", "self_serve", False, "community"),
]


class MemberTag(StateMachineMixin, models.Model):
    """
    Assignment of a tag to a member, with verification state machine.

    State machine:
        self_claimed → pending | removed
        pending      → verified | rejected | removed
        verified     → revoked | removed
        rejected     → pending | removed
        revoked      → (terminal)
        removed      → (terminal)
    """

    STATUS_CHOICES = [
        ("self_claimed", "Self-claimed"),
        ("pending", "Pending verification"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
        ("revoked", "Revoked"),
        ("removed", "Removed"),
    ]

    VALID_TRANSITIONS = {
        "self_claimed": {"pending", "removed"},
        "pending": {"verified", "rejected", "removed"},
        "verified": {"revoked", "removed"},
        "rejected": {"pending", "removed"},
        "revoked": set(),  # terminal
        "removed": set(),  # terminal
    }

    TRANSITION_TIMESTAMPS = {
        "verified": "verified_at",
        "revoked": "revoked_at",
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey("communities.Member", on_delete=models.CASCADE, related_name="member_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="assignments")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="self_claimed")
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="community",
        help_text="Member's chosen visibility (cannot exceed tag's default).",
    )
    evidence_note = models.TextField(
        blank=True,
        default="",
        help_text="Justification for verification (no PII — e.g. 'confirmed at ordination 2019').",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    verified_by = models.ForeignKey(
        "communities.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tags_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "communities.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tags_revoked",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    rejection_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "tags_member_tag"
        unique_together = [("member", "tag")]
        indexes = [
            models.Index(fields=["tag", "status"], name="tags_mt_tag_status_idx"),
            models.Index(fields=["member", "status"], name="tags_mt_member_status_idx"),
        ]

    def __str__(self):
        return f"{self.member.display_name}: {self.tag.label} ({self.status})"

    # ── Visibility enforcement ────────────────────────────────────────

    def effective_visibility(self) -> str:
        """The strictest of the member's chosen visibility and the tag's default.
        Exception: public_when_verified overrides to 'public' when verified."""
        if self.tag.public_when_verified and self.status == "verified":
            return "public"
        tag_order = VISIBILITY_ORDER.get(self.tag.default_visibility, 0)
        member_order = VISIBILITY_ORDER.get(self.visibility, 0)
        # Higher order = more restrictive; take the more restrictive one
        effective_order = max(tag_order, member_order)
        for vis, order in VISIBILITY_ORDER.items():
            if order == effective_order:
                return vis
        return "coordinators_only"

    def is_visible_to(self, viewer_member) -> bool:
        """Check if this tag assignment is visible to the given member."""
        if viewer_member is None:
            return False
        # Owner always sees their own tags
        if viewer_member.id == self.member_id:
            return True
        eff = self.effective_visibility()
        if eff == "coordinators_only":
            return viewer_member.is_coordinator
        # "public" and "community" both mean: any active community member
        return True

    # ── Clean / validation ────────────────────────────────────────────

    def clean(self):
        super().clean()
        # Visibility cannot exceed tag's default (except public_when_verified override)
        if not (self.tag.public_when_verified and self.status == "verified"):
            tag_order = VISIBILITY_ORDER.get(self.tag.default_visibility, 0)
            member_order = VISIBILITY_ORDER.get(self.visibility, 0)
            if member_order < tag_order:
                raise ValidationError(
                    {"visibility": f"Cannot be more public than the tag's default ('{self.tag.default_visibility}')."}
                )

    # ── Domain methods ────────────────────────────────────────────────

    def claim(self, *, request=None):
        """Initial claim of a self-serve tag. Sets status based on tag tier."""
        if self.tag.tier == "self_serve":
            self.status = "self_claimed"
        else:
            self.status = "pending"
        self.save()
        action = "tag.claimed" if self.status == "self_claimed" else "tag.request_verify"
        AuditLog.log(
            self.member.user,
            action,
            "member_tag",
            self.id,
            details={"tag_slug": self.tag.slug, "status": self.status},
            request=request,
        )

    def verify(self, verifier, *, evidence_note="", request=None):
        """Verify a pending tag. Enforces tier-based authorization."""
        self._check_verifier_role(verifier)
        if self.tag.tier == "admin_verified" and not evidence_note:
            raise ValidationError("Admin-verified tags require an evidence note.")
        self.evidence_note = evidence_note or self.evidence_note
        self.transition_to("verified", extra_update_fields=("evidence_note",))
        type(self).objects.filter(pk=self.pk).update(verified_by=verifier)
        self.verified_by = verifier
        AuditLog.log(
            verifier.user,
            "tag.verified",
            "member_tag",
            self.id,
            details={"tag_slug": self.tag.slug, "verified_by": str(verifier.id)},
            request=request,
        )

    def reject(self, verifier, *, reason="", request=None):
        """Reject a pending tag request."""
        self._check_verifier_role(verifier)
        self.rejection_reason = reason
        self.rejection_count = (self.rejection_count or 0) + 1
        self.transition_to("rejected", extra_update_fields=("rejection_reason", "rejection_count"))
        AuditLog.log(
            verifier.user,
            "tag.rejected",
            "member_tag",
            self.id,
            details={
                "tag_slug": self.tag.slug,
                "reason": reason,
                "rejection_count": self.rejection_count,
            },
            request=request,
        )

    def revoke(self, revoker, *, reason="", request=None):
        """Revoke a verified tag."""
        self._check_verifier_role(revoker)
        self.revoked_by = revoker
        self.rejection_reason = reason
        self.transition_to("revoked", extra_update_fields=("rejection_reason",))
        # revoked_by is set via transition_to's extra fields mechanism;
        # we need to explicitly save it since it's an FK not in update_fields
        type(self).objects.filter(pk=self.pk).update(revoked_by=revoker)
        AuditLog.log(
            revoker.user,
            "tag.revoked",
            "member_tag",
            self.id,
            details={
                "tag_slug": self.tag.slug,
                "revoked_by": str(revoker.id),
                "reason": reason,
            },
            request=request,
        )

    def remove(self, *, request=None):
        """Member self-removes their tag (soft delete)."""
        self.transition_to("removed")
        AuditLog.log(
            self.member.user,
            "tag.removed",
            "member_tag",
            self.id,
            details={"tag_slug": self.tag.slug},
            request=request,
        )

    def request_verification(self, *, evidence_note="", request=None):
        """Member requests verification of a self-claimed tag."""
        if evidence_note:
            self.evidence_note = evidence_note
        self.transition_to("pending", extra_update_fields=("evidence_note",) if evidence_note else ())
        AuditLog.log(
            self.member.user,
            "tag.request_verify",
            "member_tag",
            self.id,
            details={"tag_slug": self.tag.slug, "status": ["self_claimed", "pending"]},
            request=request,
        )

    def re_request(self, *, evidence_note="", request=None):
        """Re-request after rejection. Allowed, but flagged after 3 rejections."""
        if evidence_note:
            self.evidence_note = evidence_note
        self.transition_to("pending", extra_update_fields=("evidence_note",) if evidence_note else ())
        AuditLog.log(
            self.member.user,
            "tag.re_requested",
            "member_tag",
            self.id,
            details={
                "tag_slug": self.tag.slug,
                "rejection_count": self.rejection_count,
                "flagged": self.rejection_count >= 3,
            },
            request=request,
        )

    @property
    def is_flagged(self) -> bool:
        """True if this tag has been rejected 3+ times (visible to admins)."""
        return (self.rejection_count or 0) >= 3

    # ── Internal helpers ──────────────────────────────────────────────

    def _check_verifier_role(self, verifier):
        """Enforce tier-based authorization for verification/revocation."""
        if self.tag.tier == "admin_verified":
            if not verifier.is_admin:
                raise PermissionDenied("Only admins can verify/revoke admin-verified tags (e.g. clergy).")
        elif self.tag.tier == "coordinator_verified":
            if not verifier.is_coordinator:
                raise PermissionDenied("Only coordinators or admins can verify/revoke this tag.")

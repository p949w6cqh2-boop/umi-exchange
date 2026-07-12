"""
Report/flag abuse + coordinator moderation queue.

Flag: a member reports a need, an offer, or another member ("fake need,
bad actor") with a reason; open flags route to the community's coordinator
queue where every action is audited (§8.3).

Safe-fail by design: "hiding" content moves it to an existing terminal
status (need → closed, offer → withdrawn) — nothing is ever deleted.

State machine:
    open → resolved | dismissed   (both terminal)
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.state import StateMachineMixin

REASON_CHOICES = [
    ("fake_or_scam", "Fake or scam"),
    ("inappropriate", "Inappropriate content"),
    ("safety", "Safety concern"),
    ("spam", "Spam or duplicate"),
    ("other", "Other"),
]

RESOLUTION_CHOICES = [
    ("", "—"),
    ("content_hidden", "Content hidden"),
    ("no_action", "Reviewed — no action needed"),
]


class Flag(StateMachineMixin, models.Model):
    """A member's report against exactly one need, offer, or member."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("resolved", "Resolved"),
        ("dismissed", "Dismissed"),
    ]

    VALID_TRANSITIONS = {
        "open": {"resolved", "dismissed"},
        "resolved": set(),  # terminal
        "dismissed": set(),  # terminal
    }

    TRANSITION_TIMESTAMPS = {
        "resolved": "resolved_at",
        "dismissed": "resolved_at",
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="flags")
    reporter = models.ForeignKey("communities.Member", on_delete=models.CASCADE, related_name="flags_submitted")

    # Exactly one target (enforced by clean() + a DB check constraint).
    need = models.ForeignKey("needs.Need", null=True, blank=True, on_delete=models.CASCADE, related_name="flags")
    offer = models.ForeignKey("offers.Offer", null=True, blank=True, on_delete=models.CASCADE, related_name="flags")
    member = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.CASCADE, related_name="flags_received"
    )

    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    detail = models.TextField(
        blank=True,
        default="",
        help_text="Optional context for coordinators. Please don't include personal details.",
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    resolution = models.CharField(max_length=20, choices=RESOLUTION_CHOICES, blank=True, default="")
    resolution_note = models.TextField(blank=True, default="")
    resolved_by = models.ForeignKey(
        "communities.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flags_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "moderation_flag"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["community", "status"], name="moderation_comm_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                name="moderation_flag_one_target",
                condition=(
                    models.Q(need__isnull=False, offer__isnull=True, member__isnull=True)
                    | models.Q(need__isnull=True, offer__isnull=False, member__isnull=True)
                    | models.Q(need__isnull=True, offer__isnull=True, member__isnull=False)
                ),
            ),
            # One OPEN flag per reporter per target — re-reporting after a
            # coordinator resolves/dismisses is allowed.
            models.UniqueConstraint(
                fields=["reporter", "need"],
                condition=models.Q(status="open", need__isnull=False),
                name="moderation_open_per_need",
            ),
            models.UniqueConstraint(
                fields=["reporter", "offer"],
                condition=models.Q(status="open", offer__isnull=False),
                name="moderation_open_per_offer",
            ),
            models.UniqueConstraint(
                fields=["reporter", "member"],
                condition=models.Q(status="open", member__isnull=False),
                name="moderation_open_per_member",
            ),
        ]

    def __str__(self):
        return f"Flag[{self.target_type}] {self.get_reason_display()} ({self.status})"

    # ── Target helpers ────────────────────────────────────────────────

    @property
    def target(self):
        return self.need or self.offer or self.member

    @property
    def target_type(self) -> str:
        if self.need_id:
            return "need"
        if self.offer_id:
            return "offer"
        return "member"

    @property
    def target_label(self) -> str:
        """Short display label for the coordinator queue (title / display name)."""
        if self.need_id:
            return self.need.title
        if self.offer_id:
            return self.offer.title
        return self.member.display_name

    @property
    def target_url(self) -> str:
        if self.need_id:
            return self.need.get_absolute_url()
        if self.offer_id:
            return self.offer.get_absolute_url()
        return ""

    # ── Validation ────────────────────────────────────────────────────

    def clean(self):
        super().clean()
        targets = [t for t in (self.need, self.offer, self.member) if t is not None]
        if len(targets) != 1:
            raise ValidationError("A flag must point at exactly one need, offer, or member.")
        target = targets[0]
        target_community_id = target.community_id
        if target_community_id != self.community_id:
            raise ValidationError("Flag target must belong to the flag's community.")
        if self.reporter_id and self.reporter.community_id != self.community_id:
            raise ValidationError("Reporter must belong to the flag's community.")
        # No self-flagging: your own content is yours to edit or remove.
        if self.need is not None and self.need.requester_id == self.reporter_id:
            raise ValidationError("You cannot report your own need.")
        if self.offer is not None and self.offer.offerer_id == self.reporter_id:
            raise ValidationError("You cannot report your own offer.")
        if self.member is not None and self.member_id == self.reporter_id:
            raise ValidationError("You cannot report yourself.")

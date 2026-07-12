"""Community moderation — flags raised by members, reviewed by coordinators.

A platform holding vulnerable people must let a neighbour say "this isn't
right" and route that to a human the community already trusts (threat-model
follow-up; Jasiah's P1, 2026-07-12). Flags reference their target the same
way the audit log does — type string + UUID — every model here has a UUID pk.
"""

import uuid

from django.db import models


class Flag(models.Model):
    TARGET_CHOICES = [("need", "Need"), ("offer", "Offer"), ("member", "Member")]
    REASON_CHOICES = [
        ("fake", "Seems fake or misleading"),
        ("unsafe", "Unsafe or threatening"),
        ("spam", "Spam or off-topic"),
        ("other", "Something else"),
    ]
    STATUS_CHOICES = [("open", "Open"), ("resolved", "Resolved"), ("dismissed", "Dismissed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="flags")
    reporter = models.ForeignKey("communities.Member", on_delete=models.PROTECT, related_name="flags_raised")
    target_type = models.CharField(max_length=12, choices=TARGET_CHOICES)
    target_id = models.UUIDField()
    reason = models.CharField(max_length=12, choices=REASON_CHOICES)
    # Short, member-authored. The form coaches against names/private details;
    # the coordinator can see the flagged content itself.
    detail = models.CharField(max_length=500, blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="open")
    resolved_by = models.ForeignKey(
        "communities.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="flags_resolved"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=20, blank=True)  # hide / dismiss / keep

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "moderation_flag"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["community", "status"], name="mod_flag_comm_status_idx"),
            models.Index(fields=["target_type", "target_id"], name="mod_flag_target_idx"),
        ]
        constraints = [
            # One OPEN flag per reporter per target — report once, not a pile-on.
            models.UniqueConstraint(
                fields=["reporter", "target_type", "target_id"],
                condition=models.Q(status="open"),
                name="mod_flag_one_open_per_reporter",
            ),
        ]

    def __str__(self):
        return f"{self.get_reason_display()} · {self.target_type} · {self.status}"

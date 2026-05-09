"""
Match model — umi:Match entity.
Implements the protocol state machine (Section 4.3) with contact revelation (Section 8.2).
This is the most important model in the entire application.
"""
import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Match(models.Model):
    """
    State machine transitions (UMI Protocol Section 4.3):
        proposed → accepted | cancelled | expired
        accepted → fulfilled | unfulfilled | cancelled
        fulfilled, unfulfilled, cancelled, expired → (terminal)
    """
    VALID_TRANSITIONS = {
        "proposed": ["accepted", "cancelled", "expired"],
        "accepted": ["fulfilled", "unfulfilled", "cancelled"],
        "fulfilled": [],
        "unfulfilled": [],
        "cancelled": [],
        "expired": [],
    }

    STATUS_CHOICES = [
        ("proposed", "Proposed"), ("accepted", "Accepted"), ("fulfilled", "Fulfilled"),
        ("unfulfilled", "Unfulfilled"), ("cancelled", "Cancelled"), ("expired", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    need = models.ForeignKey("needs.Need", on_delete=models.CASCADE, related_name="matches")
    offer = models.ForeignKey("offers.Offer", on_delete=models.SET_NULL, null=True, blank=True, related_name="matches")
    proposed_by = models.ForeignKey("communities.Member", on_delete=models.CASCADE, related_name="proposed_matches")
    status = models.CharField(max_length=12, default="proposed", choices=STATUS_CHOICES)
    notes = models.TextField(blank=True)
    rating = models.SmallIntegerField(null=True, blank=True)  # 1-5, coordinator only
    proposed_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    custom = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "matches_match"
        ordering = ["-proposed_at"]

    def __str__(self):
        return f"Match {self.id} ({self.status}): {self.need.title}"

    def transition_to(self, new_status):
        """
        Enforce the protocol state machine. Raises ValidationError on invalid transition.
        Cascades status changes to the linked need and offer.
        """
        valid = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in valid:
            raise ValidationError(f"Cannot transition match from '{self.status}' to '{new_status}'.")

        old_status = self.status
        self.status = new_status
        now = timezone.now()

        if new_status == "accepted":
            self.accepted_at = now
            # Cascade: need → matched, offer → matched
            self.need.status = "matched"
            self.need.save(update_fields=["status", "updated_at"])
            if self.offer:
                self.offer.status = "matched"
                self.offer.save(update_fields=["status", "updated_at"])

        elif new_status == "fulfilled":
            self.fulfilled_at = now
            self.need.status = "fulfilled"
            self.need.fulfilled_at = now
            self.need.save(update_fields=["status", "fulfilled_at", "updated_at"])
            if self.offer:
                self.offer.status = "fulfilled"
                self.offer.save(update_fields=["status", "updated_at"])

        elif new_status == "cancelled":
            self.cancelled_at = now
            # If cancelling from accepted, re-open need and offer
            if old_status == "accepted":
                self.need.status = "open"
                self.need.save(update_fields=["status", "updated_at"])
                if self.offer:
                    self.offer.status = "active"
                    self.offer.save(update_fields=["status", "updated_at"])

        elif new_status == "unfulfilled":
            self.need.status = "open"
            self.need.save(update_fields=["status", "updated_at"])
            if self.offer:
                self.offer.status = "active"
                self.offer.save(update_fields=["status", "updated_at"])

        self.save()

    def get_contact_info_for(self, requesting_member):
        """
        Contact revelation logic (UMI Protocol Section 8.2).
        Returns contact info dict ONLY if:
        1. Match status is 'accepted' or 'fulfilled'
        2. Requesting member is a participant or coordinator
        Returns None otherwise.
        """
        if self.status not in ("accepted", "fulfilled"):
            return None

        is_requester = self.need.requester == requesting_member
        is_offerer = self.offer and self.offer.offerer == requesting_member
        is_coordinator = requesting_member and requesting_member.is_coordinator

        if not (is_requester or is_offerer or is_coordinator):
            return None

        # Determine the OTHER party's info
        if is_requester:
            other_member = self.offer.offerer if self.offer else None
            other_pref = self.offer.contact_pref if self.offer else "in_app"
        else:
            other_member = self.need.requester
            other_pref = self.need.contact_pref

        if not other_member:
            return None

        info = {"display_name": other_member.display_name, "preference": other_pref}
        if other_pref in ("email", "any") and other_member.user.email:
            info["email"] = other_member.user.email
        if other_pref in ("phone", "any") and other_member.user.phone:
            info["phone"] = other_member.user.phone
        return info

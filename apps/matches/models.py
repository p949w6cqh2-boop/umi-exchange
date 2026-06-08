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
        ("proposed", "Proposed"),
        ("accepted", "Accepted"),
        ("fulfilled", "Fulfilled"),
        ("unfulfilled", "Unfulfilled"),
        ("cancelled", "Cancelled"),
        ("expired", "Expired"),
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

    @staticmethod
    def _contact_dict(member, pref):
        info = {"display_name": member.display_name, "preference": pref}
        if pref in ("email", "any") and member.user.email:
            info["email"] = member.user.email
        if pref in ("phone", "any") and member.user.phone:
            info["phone"] = member.user.phone
        return info

    def get_contact_info_for(self, requesting_member):
        """
        Contact revelation logic (UMI Protocol Section 8.2).
        Returns contact info ONLY if:
        1. Match status is 'accepted' or 'fulfilled'
        2. Requesting member is a participant or a coordinator
        Returns None otherwise.

        Participants see the OTHER party's details. A coordinator (oversight)
        sees BOTH parties, exposed under a ``parties`` list on the returned dict
        while keeping the flat shape for backward compatibility.
        """
        if self.status not in ("accepted", "fulfilled"):
            return None
        if requesting_member is None:
            return None

        requester = self.need.requester
        requester_pref = self.need.contact_pref
        # The offering party is the offer owner, or — for an offer-less direct
        # volunteer match — the member who proposed it.
        if self.offer is not None:
            offering_member = self.offer.offerer
            offering_pref = self.offer.contact_pref
        else:
            offering_member = self.proposed_by
            offering_pref = "in_app"

        is_requester = requester == requesting_member
        is_offerer = offering_member == requesting_member
        is_coordinator = requesting_member.is_coordinator

        if not (is_requester or is_offerer or is_coordinator):
            return None

        # Participants see the counterpart.
        if is_requester:
            return self._contact_dict(offering_member, offering_pref) if offering_member else None
        if is_offerer:
            return self._contact_dict(requester, requester_pref)

        # Coordinator (not a participant): reveal both parties for oversight.
        parties = [self._contact_dict(requester, requester_pref)]
        if offering_member:
            parties.append(self._contact_dict(offering_member, offering_pref))
        primary = dict(parties[0])
        primary["parties"] = parties
        return primary

"""
Federation Stage A data model (docs/federation-design.md §8): instance
identity (FederationPeer) + the pairwise, community-scoped, human-approved
relationship (FederationLink). No data flows in Stage A — links only.
"""

import uuid

from django.db import models

from apps.common.state import StateMachineMixin


class FederationPeer(models.Model):
    """A known remote instance. The JWK is pinned at approval time (§3.3);
    an unauthenticated handshake may never overwrite a non-pending peer's key."""

    STATUS_CHOICES = [("pending", "Pending"), ("active", "Active"), ("blocked", "Blocked")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Identity is the instance_id (thumbprint); base_url is peer-supplied and
    # advisory, so it is NOT unique — a self-signed doc must never be able to
    # collide on someone else's URL and 500 the handshake.
    base_url = models.URLField(max_length=200, blank=True, default="")
    instance_id = models.CharField(max_length=64, unique=True)  # RFC 7638 JWK thumbprint
    jwk = models.JSONField(default=dict)  # pinned public key (OKP/Ed25519)
    label = models.CharField(max_length=200, blank=True, default="")
    locality = models.CharField(max_length=100, blank=True, default="")
    capabilities = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, default="pending", choices=STATUS_CHOICES)
    # Inbound pairing state (peer-level: the requesting side names a community,
    # ours is chosen by the approving admin — §3.3).
    pairing_salt = models.CharField(max_length=64, blank=True, default="")
    pairing_hash = models.CharField(max_length=64, blank=True, default="")
    pairing_expires_at = models.DateTimeField(null=True, blank=True)
    requested_communities = models.JSONField(default=list, blank=True)  # [{"uuid","label"}] — labels only, no PII
    approved_by = models.ForeignKey(
        "communities.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="federation_peers_approved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "federation_peer"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label or self.base_url} ({self.status})"

    def is_pairing_expired(self):
        from django.utils import timezone

        return bool(self.pairing_expires_at and self.pairing_expires_at < timezone.now())


class FederationLink(StateMachineMixin, models.Model):
    """One community ↔ one remote community over one peer. State machine per
    §3.3: suspended keeps keys (operator pause); revoked is terminal."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("revoked", "Revoked"),
    ]
    VALID_TRANSITIONS = {
        "pending": {"active", "revoked"},
        "active": {"suspended", "revoked"},
        "suspended": {"active", "revoked"},
        "revoked": set(),  # terminal — resuming requires a fresh handshake
    }
    TRANSITION_TIMESTAMPS = {"revoked": "revoked_at"}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    peer = models.ForeignKey(FederationPeer, on_delete=models.CASCADE, related_name="links")
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="federation_links")
    remote_community_uuid = models.UUIDField(null=True, blank=True)
    remote_community_label = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=12, default="pending", choices=STATUS_CHOICES)
    requested_by_us = models.BooleanField(default=False)
    # Outbound pairing state (we minted the code; the peer proves possession
    # in its signed confirm — §3.3 steps 4-8). Consumed on activation.
    pairing_code_hash = models.CharField(max_length=64, blank=True, default="")
    pairing_expires_at = models.DateTimeField(null=True, blank=True)
    # Link-scoped pepper for the Stage C blind self-match token (§7). Derived
    # from the pairing code at activation; secret material, never exported.
    pairing_pepper = models.BinaryField(null=True, blank=True, editable=False)
    approved_by = models.ForeignKey(
        "communities.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="federation_links_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "federation_link"
        ordering = ["-created_at"]
        unique_together = [["peer", "community", "remote_community_uuid"]]
        indexes = [models.Index(fields=["community", "status"])]

    def __str__(self):
        return f"{self.community.slug} ↔ {self.peer.base_url} ({self.status})"

    def is_pairing_expired(self):
        from django.utils import timezone

        return bool(self.pairing_expires_at and self.pairing_expires_at < timezone.now())

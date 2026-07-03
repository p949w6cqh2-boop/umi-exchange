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


class FederatedShare(models.Model):
    """One local record (Need or Offer) advertised to one link (Stage B, §8).
    The row is redacted-by-construction — it holds no PII, only the alias
    remote_uuid, the gating consent, and the signed consent receipt. Discovery
    exposes only §2.2 fields derived from the linked record at serve time."""

    STATUS_CHOICES = [("active", "Active"), ("revoked", "Revoked"), ("expired", "Expired")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.ForeignKey(FederationLink, on_delete=models.CASCADE, related_name="shares")
    need = models.ForeignKey(
        "needs.Need", on_delete=models.CASCADE, null=True, blank=True, related_name="federated_shares"
    )
    offer = models.ForeignKey(
        "offers.Offer", on_delete=models.CASCADE, null=True, blank=True, related_name="federated_shares"
    )
    # The participant's consent gating this share (§4.1) — PROTECT so a consent
    # backing a live share cannot be deleted out from under it.
    consent = models.ForeignKey("consent.Consent", on_delete=models.PROTECT, related_name="federated_shares")
    remote_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)  # unlinkable alias
    receipt_jws = models.TextField(blank=True, default="")  # signed consent receipt (§4.2)
    status = models.CharField(max_length=10, default="active", choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "federation_share"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(need__isnull=False, offer__isnull=True) | models.Q(need__isnull=True, offer__isnull=False)
                ),
                name="federated_share_exactly_one_record",
            ),
            models.UniqueConstraint(fields=["link", "need"], name="uniq_share_link_need"),
            models.UniqueConstraint(fields=["link", "offer"], name="uniq_share_link_offer"),
        ]

    def __str__(self):
        return f"share {self.remote_uuid} → {self.link_id} ({self.status})"

    @property
    def record(self):
        return self.need or self.offer


class ShadowListing(models.Model):
    """An inbound redacted discovery row pulled from a peer (Stage B slice 2,
    §2.2/§4.4). Holds NO PII by construction — only the coarse §2.2 fields and
    a short TTL. Nothing here is treated as durable: it is refreshed on each
    poll and shredded when it expires or disappears from the peer's feed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.ForeignKey(FederationLink, on_delete=models.CASCADE, related_name="shadows")
    kind = models.CharField(max_length=8)  # "need" | "offer"
    remote_uuid = models.UUIDField()  # the peer's per-share alias
    category = models.CharField(max_length=100, blank=True, default="")
    urgency = models.CharField(max_length=10, blank=True, default="")
    locality = models.CharField(max_length=100, blank=True, default="")
    freshness = models.CharField(max_length=10, blank=True, default="")
    radius_km = models.IntegerField(null=True, blank=True)
    receipt_jws = models.TextField(blank=True, default="")
    fetched_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "federation_shadow"
        ordering = ["-fetched_at"]
        constraints = [models.UniqueConstraint(fields=["link", "remote_uuid"], name="uniq_shadow_link_remote")]
        indexes = [models.Index(fields=["expires_at"])]

    def __str__(self):
        return f"shadow {self.kind}:{self.remote_uuid} ← {self.link_id}"

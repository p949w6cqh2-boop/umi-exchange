"""
Audit log — append-only, hashed IPs, non-deletable.
UMI Protocol Section 8.3: all state-changing operations MUST be logged.
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    # Dotted event names (e.g. "match.contact_revealed", "case.opened_emergency").
    # Legacy create/read/update/delete values remain valid. (§10.1)
    action = models.CharField(max_length=32)
    resource_type = models.CharField(max_length=50)
    resource_id = models.UUIDField()
    details = models.JSONField(null=True, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_auditlog"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.action}] {self.resource_type}:{self.resource_id} by {self.user_id}"

    def save(self, *args, **kwargs):
        """Append-only (Section 8.3): allow the initial INSERT, never an UPDATE."""
        if not self._state.adding:
            raise PermissionDenied("Audit log entries are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Append-only (Section 8.3): entries can never be deleted."""
        raise PermissionDenied("Audit log entries are append-only and cannot be deleted.")

    @classmethod
    def log(cls, user, action, resource_type, resource_id, details=None, request=None):
        """Create an audit entry. IP is SHA-256 hashed with the secret key as salt.

        IP extraction + hashing is delegated to ``services.ip_hash`` so this path
        and ``services.emit`` share ONE source of IP truth (``client_ip``, which
        trims the trusted X-Real-IP and falls back to REMOTE_ADDR). Previously
        this method re-derived the IP inline without the trim, so the same real
        IP could hash two different ways depending on which path logged it.
        """
        # Match services.emit's hard cap (§10.1): fail loud, never silently
        # truncate or let Postgres raise DataError on the varchar(32) column.
        if len(action) > 32:
            raise ValueError(f"audit action too long (>32): {action!r}")

        # Lazy import: services imports this module, so a top-level import cycles.
        from apps.audit.services import ip_hash

        cls.objects.create(
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_hash=ip_hash(request),
        )

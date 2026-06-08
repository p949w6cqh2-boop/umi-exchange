"""
Audit log — append-only, hashed IPs, non-deletable.
UMI Protocol Section 8.3: all state-changing operations MUST be logged.
"""

import hashlib

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=10)  # create, read, update, delete
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
        """Create an audit entry. IP is SHA-256 hashed with the secret key as salt."""
        ip_hash = ""
        if request:
            ip = request.META.get("HTTP_X_REAL_IP", request.META.get("REMOTE_ADDR", ""))
            if ip:
                salted = f"{ip}:{settings.SECRET_KEY}"
                ip_hash = hashlib.sha256(salted.encode()).hexdigest()

        cls.objects.create(
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_hash=ip_hash,
        )

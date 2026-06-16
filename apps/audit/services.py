"""
Canonical audit emitter (§10.1) — the single way new code writes audit rows.
Moved here from apps/casework/audit.py now that apps/audit may change;
casework keeps a thin shim so nothing breaks.

Rules it enforces:
  * dotted action names, hard-capped at 32 chars (raises, never truncates);
  * user stored only when authenticated (else NULL = system event);
  * IPs stored as salted SHA-256 hashes, never raw (Part A §8.3).
"""

import hashlib

from django.conf import settings

from apps.accounts.ratelimit import client_ip

from .models import AuditLog


def ip_hash(request) -> str:
    """Salted SHA-256 of the client IP, matching AuditLog.log().

    Uses the reverse-proxy-set client IP (never the client-spoofable
    left-most X-Forwarded-For) and salts with SECRET_KEY so the hashes
    cannot be reversed with a precomputed (rainbow) table.
    """
    if request is None:
        return ""
    ip = client_ip(request)
    if not ip:
        return ""
    salted = f"{ip}:{settings.SECRET_KEY}"
    return hashlib.sha256(salted.encode()).hexdigest()


def emit(action: str, resource, *, user=None, request=None, details=None):
    """emit("match.expired", match, user=None, details={"after_days": 14})"""
    if len(action) > 32:
        raise ValueError(f"audit action too long (>32): {action!r}")
    return AuditLog.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        resource_type=resource.__class__.__name__.lower(),
        resource_id=resource.pk,
        details=details or None,
        ip_hash=ip_hash(request),
    )

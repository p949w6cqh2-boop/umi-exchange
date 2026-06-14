"""
Canonical audit emitter (§10.1) — the single way new code writes audit rows.
Moved here from apps/casework/audit.py now that apps/audit may change;
casework keeps a thin shim so nothing breaks.

Rules it enforces:
  * dotted action names, hard-capped at 32 chars (raises, never truncates);
  * user stored only when authenticated (else NULL = system event);
  * IPs stored as SHA-256 hashes, never raw (Part A §8.3).
"""
import hashlib

from .models import AuditLog


def ip_hash(request) -> str:
    if request is None:
        return ""
    ip = (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
          or request.META.get("REMOTE_ADDR", ""))
    return hashlib.sha256(ip.encode()).hexdigest() if ip else ""


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

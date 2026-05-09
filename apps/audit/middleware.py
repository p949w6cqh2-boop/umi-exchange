"""
Audit middleware — logs all state-changing HTTP requests (POST, PUT, PATCH, DELETE).
UMI Protocol Section 8.3: all state-changing operations MUST be logged.

This middleware provides automatic logging as a safety net. Views should ALSO
call AuditLog.log() explicitly for business-level events (match transitions, etc.).
"""
import logging

from .models import AuditLog

logger = logging.getLogger("apps.audit")

# Paths to exclude from audit logging (high-frequency, non-sensitive)
EXCLUDED_PATHS = frozenset([
    "/health/",
    "/notifications/count/",
    "/notifications/mark-read/",
    "/admin/jsi18n/",
])


class AuditMiddleware:
    """
    Middleware that creates an AuditLog entry for every state-changing request
    (POST, PUT, PATCH, DELETE) that returns a successful response (2xx or 3xx).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log state-changing methods
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return response

        # Skip excluded paths
        if request.path in EXCLUDED_PATHS:
            return response

        # Only log successful operations (2xx, 3xx)
        if response.status_code >= 400:
            return response

        # Skip if user is not authenticated
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return response

        try:
            # Determine resource type from URL path
            resource_type = self._extract_resource_type(request.path)

            AuditLog.log(
                user=request.user,
                action=request.method.lower(),
                resource_type=resource_type,
                resource_id="00000000-0000-0000-0000-000000000000",  # Placeholder; views log specific IDs
                details={
                    "method": request.method,
                    "path": request.path,
                    "source": "middleware",
                },
                request=request,
            )
        except Exception:
            # Audit logging must never break the request
            logger.exception("Failed to create audit log entry")

        return response

    @staticmethod
    def _extract_resource_type(path):
        """Extract a human-readable resource type from the URL path."""
        parts = [p for p in path.strip("/").split("/") if p]
        # Map known URL segments to resource types
        resource_map = {
            "auth": "auth",
            "join": "community_join",
            "needs": "need",
            "offers": "offer",
            "matches": "match",
            "settings": "settings",
            "dashboard": "dashboard",
            "household": "household",
            "account": "account",
        }
        for part in parts:
            if part in resource_map:
                return resource_map[part]
        return parts[0] if parts else "unknown"

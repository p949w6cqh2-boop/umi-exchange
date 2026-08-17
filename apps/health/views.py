"""
Health check endpoint — returns 200 when app + database are reachable.
Used by load balancers, uptime monitors (UptimeRobot), and deployment scripts.
Optional token protection via HEALTH_CHECK_TOKEN env var.
"""

from django.conf import settings
from django.db import connection
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.crypto import constant_time_compare
from django.views import View


class HealthCheckView(View):
    """
    GET /health/ — returns {"status": "ok", "db": "ok"} or 503 on failure.
    If HEALTH_CHECK_TOKEN is set, requires ?token=<value> parameter.
    """

    def get(self, request):
        # Optional token auth (constant-time comparison to avoid leaking the
        # token via response timing).
        token = getattr(settings, "HEALTH_CHECK_TOKEN", "")
        if token and not constant_time_compare(request.GET.get("token", ""), token):
            return HttpResponseForbidden("Forbidden")

        checks = {"status": "ok", "db": "unknown", "cache": "unknown"}
        status_code = 200

        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["db"] = "ok"
        except Exception as e:
            checks["db"] = f"error: {type(e).__name__}"
            checks["status"] = "degraded"
            status_code = 503

        # Redis/cache check
        try:
            from django.core.cache import cache

            cache.set("_health", "1", 10)
            if cache.get("_health") == "1":
                checks["cache"] = "ok"
            else:
                checks["cache"] = "error: read mismatch"
        except Exception:
            checks["cache"] = "not configured"

        return JsonResponse(checks, status=status_code)

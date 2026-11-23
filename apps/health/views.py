"""
Health check endpoint — returns 200 when app + database are reachable.
Used by load balancers, uptime monitors (UptimeRobot), and deployment scripts.
Optional token protection via HEALTH_CHECK_TOKEN env var.

It also names the commit the running image was built from (`commit`), so a deploy can be
verified from outside the host: health and status codes alone cannot tell "deployed" from
"believed deployed" (the 2026-07-27 deploy served the old tree with every probe green).
"""

import re

from django.conf import settings
from django.db import connection
from django.http import HttpResponseForbidden, JsonResponse
from django.utils.crypto import constant_time_compare
from django.views import View

_COMMIT = re.compile(r"[0-9a-f]{7,40}")


def running_commit():
    """The image's build commit, or "unknown". Only a commit hash is ever echoed: an image built
    without --build-arg GIT_SHA, or handed something else, says "unknown" rather than guessing."""
    sha = (getattr(settings, "GIT_SHA", "") or "").strip().lower()
    return sha if _COMMIT.fullmatch(sha) else "unknown"


class HealthCheckView(View):
    """
    GET /health/ — returns {"status": "ok", "db": "ok", "cache": "ok", "commit": "<sha>"} or 503 on failure.
    If HEALTH_CHECK_TOKEN is set, requires ?token=<value> parameter.
    """

    def get(self, request):
        # Optional token auth (constant-time comparison to avoid leaking the
        # token via response timing).
        token = getattr(settings, "HEALTH_CHECK_TOKEN", "")
        if token and not constant_time_compare(request.GET.get("token", ""), token):
            return HttpResponseForbidden("Forbidden")

        checks = {"status": "ok", "db": "unknown", "cache": "unknown", "commit": running_commit()}
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

        # Redis/cache check. Production keeps sessions and the auth rate limiter in this cache,
        # so a cache that fails is sign-in failing: report it and 503, like the database. It
        # used to say "not configured" with a 200, so monitoring saw a healthy site while
        # nobody could sign in (2026-10 bug hunt). The local default (LocMem) cannot fail here.
        try:
            from django.core.cache import cache

            cache.set("_health", "1", 10)
            if cache.get("_health") == "1":
                checks["cache"] = "ok"
            else:
                checks["cache"] = "error: read mismatch"
                checks["status"] = "degraded"
                status_code = 503
        except Exception as e:
            checks["cache"] = f"error: {type(e).__name__}"
            checks["status"] = "degraded"
            status_code = 503

        return JsonResponse(checks, status=status_code)

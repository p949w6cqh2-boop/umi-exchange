"""Template context for the idle sign-out warning (apps/accounts/idle.py)."""

from django.conf import settings


def idle_timeout(request):
    return {"idle_timeout_seconds": settings.SESSION_IDLE_TIMEOUT_SECONDS}

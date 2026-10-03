"""Template context for the idle sign-out warning (apps/accounts/idle.py) and for codes by
phone (apps/accounts/phone.py), which every page that offers them must hide while it is off."""

from django.conf import settings

from . import phone


def idle_timeout(request):
    return {"idle_timeout_seconds": settings.SESSION_IDLE_TIMEOUT_SECONDS}


def phone_codes(request):
    return {"phone_codes_enabled": phone.enabled(), "phone_codes_channels": phone.channels()}

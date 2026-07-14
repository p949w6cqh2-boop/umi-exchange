"""Development settings."""

from .base import *  # noqa: F401, F403

# Demo/dev toggle: DEBUG=0 lets a seeded demo run with the real 403/404 pages
# (Django shows technical pages under DEBUG). Defaults on for development.
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
INSTALLED_APPS += ["debug_toolbar"] if False else []  # Set True to enable

# Use standard static files storage (no manifest required) for dev/test
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

# ── Override cache to in-memory (no Redis required for dev/test) ──
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ── Rate limiting in dev/test ──
# RATELIMIT_ENABLE (no D) is the THIRD-PARTY django_ratelimit flag; False here
# disables its login/register decorators in dev. The in-house fixed-window
# limiter (apps/accounts/ratelimit.py) reads RATELIMIT_ENABLED (with a D) and is
# deliberately left ON in dev/test — the throttle tests (join/tags/casework/
# federation) rely on it. LocMemCache keeps it per-process and harmless locally.
RATELIMIT_ENABLE = False

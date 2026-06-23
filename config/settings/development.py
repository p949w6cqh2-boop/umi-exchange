"""Development settings."""

from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
INSTALLED_APPS += ["debug_toolbar"] if False else []  # Set True to enable

# Use standard static files storage (no manifest required) for dev/test
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

# ── Override cache to in-memory (no Redis required for dev/test) ──
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ── Disable rate limiting in dev/test (it depends on cache backend) ──
RATELIMIT_ENABLE = False

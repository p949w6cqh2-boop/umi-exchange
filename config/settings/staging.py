"""
Staging settings — inherits production security, but with distinct env markers.
Deploy via: DJANGO_SETTINGS_MODULE=config.settings.staging
"""

from .production import *  # noqa: F401, F403

# Staging-specific overrides
SENTRY_ENVIRONMENT = "staging"

# Staging hosts come from the environment — no real domain is registered yet, so a
# hardcoded default would be a promise we can't keep (pipeline §B5).
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost"])

# Optionally relax HSTS for staging
SECURE_HSTS_SECONDS = 3600  # 1 hour (not 1 year)
SECURE_HSTS_PRELOAD = False

# Use a separate database (set via DATABASE_URL env var)
# No code change needed; just point DATABASE_URL to the staging DB.

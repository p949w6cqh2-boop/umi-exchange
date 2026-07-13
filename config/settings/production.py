"""
Production settings — security hardened, Sentry-integrated, structured logging.
All security headers pass Mozilla Observatory A+ when combined with Caddy.
"""

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *  # noqa: F401, F403

DEBUG = False

# ── Fail fast on insecure secrets ────────────────────
# In production we must never fall back to the development defaults: an
# insecure SECRET_KEY undermines all signing, and an empty ENCRYPTION_KEY
# silently turns field encryption into a no-op. Refuse to start instead.
_INSECURE_SECRET_KEY = "dev-only-insecure-key-change-in-production-please"
if not SECRET_KEY or SECRET_KEY == _INSECURE_SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a unique secret value in production; "
        "the insecure development default is not allowed."
    )
if not ENCRYPTION_KEYS and not ENCRYPTION_KEY:
    raise ImproperlyConfigured(
        "ENCRYPTION_KEYS (preferred, comma-separated, primary first) or the legacy single "
        "ENCRYPTION_KEY must be set in production; an empty key silently disables encryption "
        "of sensitive fields."
    )
if FEDERATION_ENABLED and not FEDERATION_PRIVATE_KEY:
    raise ImproperlyConfigured(
        "FEDERATION_ENABLED=True requires FEDERATION_PRIVATE_KEY (an Ed25519 private JWK; "
        "generate one with `manage.py federation_keygen`). Refusing to start with an "
        "unsigned federation identity."
    )
if FEDERATION_ENABLED and "locmem" in CACHES["default"]["BACKEND"].lower():
    raise ImproperlyConfigured(
        "FEDERATION_ENABLED=True requires a shared cache (set REDIS_URL). With the per-process "
        "LocMemCache, the signed-request replay (jti) guard and rate limits are not atomic across "
        "gunicorn workers — a replay landing on another worker would be accepted."
    )

# ── Security Headers ─────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Reverse proxy (Caddy) support
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# ── Content Security Policy ──────────────────────────
# The policy now lives in base.py as CONTENT_SECURITY_POLICY (django-csp 4.x
# dict), enforced in every environment. The old flat CSP_* settings here were
# dead in django-csp 4.x (dict-only) — removed so the app's own outdated-config
# system check passes.

# ── Sentry (optional: only active if SENTRY_DSN is set) ──
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,  # 10% of requests for performance monitoring
        send_default_pii=False,  # Never send PII to Sentry
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        release=env("GIT_SHA", default="unknown"),
    )

# ── Health Check Token ────────────────────────────────
HEALTH_CHECK_TOKEN = env("HEALTH_CHECK_TOKEN", default="")

# ── Logging (structured, rotated, Sentry-aware) ──────
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {module} {message}",
            "style": "{",
        },
        "json": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "umi.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "umi-errors.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 10,
            "formatter": "verbose",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["console", "file", "error_file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"level": "WARNING", "propagate": True},
        "django.request": {"level": "ERROR", "propagate": True},
        "django.security": {"level": "WARNING", "propagate": True},
        "apps": {"level": "INFO", "propagate": True},
    },
}


# ── Email delivery ────────────────────────────────────────────────────────
# In production, send real mail over SMTP the moment credentials are present.
# If SMTP creds are set but the backend is still the console default (e.g. the
# operator copied .env.example verbatim), switch to real delivery. An explicit
# non-console EMAIL_BACKEND is always respected. Delivery is consented per user
# (User.email_notifications).
if EMAIL_HOST_USER and EMAIL_BACKEND.endswith("console.EmailBackend"):  # noqa: F405
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

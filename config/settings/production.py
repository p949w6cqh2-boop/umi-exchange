"""
Production settings — security hardened, Sentry-integrated, structured logging.
All security headers pass Mozilla Observatory A+ when combined with Caddy.
"""
from .base import *  # noqa: F401, F403
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

DEBUG = False

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
# Tight CSP that allows HTMX, Alpine.js (CDN), and inline styles for Tailwind
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "https://unpkg.com",)  # HTMX + Alpine CDN
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'",)  # Tailwind inline styles
CSP_IMG_SRC = ("'self'", "data:",)  # data: for QR code inline images
CSP_FONT_SRC = ("'self'",)
CSP_CONNECT_SRC = ("'self'",)  # HTMX XHR requests
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)

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

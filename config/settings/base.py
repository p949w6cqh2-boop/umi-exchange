"""
UMI Exchange — Base Settings
Shared across all environments. Environment-specific overrides in development.py / production.py.
"""

from pathlib import Path

import environ

env = environ.Env()
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read .env file if it exists (won't crash if missing)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("SECRET_KEY", default="dev-only-insecure-key-change-in-production-please")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
SITE_URL = env("SITE_URL", default="http://localhost:8000")
ENCRYPTION_KEY = env("ENCRYPTION_KEY", default="")
UMI_CONFORMANCE_LEVEL = env("UMI_CONFORMANCE_LEVEL", default="core")
DEBUG = env.bool("DEBUG", default=False)


# ── Apps ──────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party (required)
    "rest_framework",
    "django_htmx",
    "guardian",
    # Project apps
    "apps.accounts",
    "apps.households",
    "apps.communities",
    "apps.needs",
    "apps.offers",
    "apps.matches",
    "apps.notifications",
    "apps.dashboard",
    "apps.audit",
    "apps.consent",
    "apps.people",
    "apps.casework",
    "apps.health",
]

# Optional: Django-Q2 (for background tasks — not required for basic operation)
try:
    import django_q  # noqa: F401

    INSTALLED_APPS.append("django_q")
except ImportError:
    pass

# Optional: 2FA (django-two-factor-auth)
ENABLE_2FA = False
try:
    import django_otp  # noqa: F401
    import two_factor  # noqa: F401

    INSTALLED_APPS += [
        "django_otp",
        "django_otp.plugins.otp_totp",
        "django_otp.plugins.otp_static",
        "two_factor",
    ]
    ENABLE_2FA = True
except ImportError:
    pass  # 2FA not installed; features disabled gracefully

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.casework.middleware.SensitiveSessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

# Optional: OTP middleware for 2FA (must come after AuthenticationMiddleware)
if ENABLE_2FA:
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "django_otp.middleware.OTPMiddleware",
    )

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ── Auth ──────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/join/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True

# Use Argon2 if its backing library is installed, else fall back to PBKDF2.
# NOTE: import the `argon2` library itself — importing the hasher class always
# succeeds even when the library is missing, which silently broke auth before.
try:
    import argon2  # noqa: F401

    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.Argon2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ]
except ImportError:
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
        "django.contrib.auth.hashers.Argon2PasswordHasher",
    ]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
]

# ── Database ──────────────────────────────────────────
DATABASES = {"default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Cache / Sessions ──────────────────────────────────
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    try:
        import django_redis  # noqa: F401

        CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": REDIS_URL}}
        SESSION_ENGINE = "django.contrib.sessions.backends.cache"
        SESSION_CACHE_ALIAS = "default"
    except ImportError:
        pass  # Redis not installed; use default cache

# ── Django-Q2 ─────────────────────────────────────────
Q_CLUSTER = {
    "name": "umi",
    "workers": 2,
    "recycle": 360,
    "timeout": 300,
    "retry": 360,  # Must be > timeout to avoid premature task re-triggers
    "orm": "default",  # Use ORM broker (works without Redis)
}

# ── Templates ─────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.communities.context_processors.umi_context",
            ],
        },
    },
]

# ── Static ────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}

# ── Email ─────────────────────────────────────────────
# Console backend for dev; set EMAIL_BACKEND to django.core.mail.backends.smtp.EmailBackend
# in production and configure SMTP settings via environment variables.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@umifoundation.org")
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# SMTP settings (only used when EMAIL_BACKEND is smtp)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)

# Subject prefix for admin error emails
EMAIL_SUBJECT_PREFIX = env("EMAIL_SUBJECT_PREFIX", default="[UMI] ")

# ── REST Framework ────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}

# ── Rate Limiting ─────────────────────────────────────
RATELIMIT_USE_CACHE = "default"

# ── Health Check ──────────────────────────────────────
HEALTH_CHECK_TOKEN = env("HEALTH_CHECK_TOKEN", default="")

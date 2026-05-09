"""
UMI Exchange — Base Settings
Shared across all environments. Environment-specific overrides in development.py / production.py.
"""
import environ
from pathlib import Path

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
DEBUG = env.bool("DEBUG", default=True)

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
    "apps.health",
]

# Optional: 2FA — packages installed, but opt-in per user.
# Users enable TOTP via their account settings page.
try:
    import django_otp  # noqa: F401
    INSTALLED_APPS += [
        "django_otp",
        "django_otp.plugins.otp_totp",
        "django_otp.plugins.otp_static",
        "two_factor",
        "two_factor.plugins.phonenumber",
    ]
    TWO_FACTOR_AVAILABLE = True
except ImportError:
    TWO_FACTOR_AVAILABLE = False

# Deployment-time flag: require 2FA for coordinators/admins.
# Set via env var; defaults to False (opt-in only).
REQUIRE_2FA_FOR_COORDINATORS = env.bool("REQUIRE_2FA_FOR_COORDINATORS", default=False)

# Optional: Django-Q2 (for background tasks — not required for basic operation)
try:
    import django_q  # noqa: F401
    INSTALLED_APPS.append("django_q")
except ImportError:
    pass

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.audit.middleware.AuditMiddleware",
]

# 2FA middleware — inserted after AuthenticationMiddleware (required by django-otp)
try:
    import django_otp  # noqa: F401
    auth_idx = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    MIDDLEWARE.insert(auth_idx + 1, "django_otp.middleware.OTPMiddleware")
except (ImportError, ValueError):
    pass

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# ── Auth ──────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/join/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True

# Use Argon2 if available, fallback to PBKDF2
try:
    from django.contrib.auth.hashers import Argon2PasswordHasher  # noqa: F401
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.Argon2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ]
except Exception:
    pass  # Use Django defaults

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
    "recycle": 500,
    "timeout": 120,
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
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@umifoundation.org")

# ── REST Framework ────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 20,
}

# ── Rate Limiting ─────────────────────────────────────
RATELIMIT_USE_CACHE = "default" if REDIS_URL else None

# ── Health Check ──────────────────────────────────────
HEALTH_CHECK_TOKEN = env("HEALTH_CHECK_TOKEN", default="")

# ── 2FA (django-two-factor-auth) ──────────────────────
LOGIN_URL = "two_factor:login" if TWO_FACTOR_AVAILABLE else "/auth/login/"
TWO_FACTOR_PATCH_ADMIN = False  # Don't force 2FA on admin login
TWO_FACTOR_CALL_GATEWAY = None  # Phone 2FA not supported in Core
TWO_FACTOR_SMS_GATEWAY = None

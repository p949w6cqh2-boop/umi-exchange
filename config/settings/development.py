"""Development settings."""
from .base import *  # noqa: F401, F403

DEBUG = True
INSTALLED_APPS += ["debug_toolbar"] if False else []  # Set True to enable

# Use standard non-manifest storage for local development and testing
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


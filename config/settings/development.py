"""Development settings."""
from .base import *  # noqa: F401, F403

DEBUG = True
INSTALLED_APPS += ["debug_toolbar"] if False else []  # Set True to enable

# Use standard static files storage (no manifest required) for dev/test
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

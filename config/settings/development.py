"""Development settings."""
from .base import *  # noqa: F401, F403

DEBUG = True
INSTALLED_APPS += ["debug_toolbar"] if False else []  # Set True to enable

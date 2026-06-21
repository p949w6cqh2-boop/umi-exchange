from django.apps import AppConfig


class TagsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tags"
    verbose_name = "Member Tags"

    def ready(self):
        from . import signals  # noqa: F401 — register signal handlers

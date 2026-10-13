from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .ratelimit import remember_device

        # Every sign-in marks its browser as known to the account (ratelimit.KNOWN_DEVICE_COOKIE).
        user_logged_in.connect(remember_device, dispatch_uid="accounts.remember_device")

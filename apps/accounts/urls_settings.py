"""Account settings URLs — profile, household management, optional 2FA setup."""
from django.urls import path, include
from . import views

urlpatterns = [
    path("", views.SettingsView.as_view(), name="account-settings"),
]

# 2FA setup URLs — only available if django-two-factor-auth is installed
try:
    from two_factor.urls import urlpatterns as tf_urls
    urlpatterns += [
        path("two-factor/", include(tf_urls)),
    ]
except ImportError:
    pass

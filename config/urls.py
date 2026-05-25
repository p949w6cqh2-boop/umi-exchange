"""UMI Exchange — Root URL Configuration."""
from django.contrib import admin
from django.urls import include, path

from apps.communities.views import LandingView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", LandingView.as_view(), name="landing"),
    path("health/", include("apps.health.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("join/", include("apps.households.urls_join")),
    path("c/<slug:slug>/dashboard/", include("apps.dashboard.urls")),
    path("c/", include("apps.communities.urls")),
    path("account/", include("apps.accounts.urls_settings")),
    path("notifications/", include("apps.notifications.urls")),
    path("technology/", include("apps.communities.urls_tech")),
]

from django.conf import settings

if getattr(settings, "ENABLE_2FA", False):
    from two_factor.urls import urlpatterns as tf_urls
    urlpatterns.insert(1, path("", include(tf_urls)))

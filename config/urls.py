"""UMI Exchange — Root URL Configuration."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.communities.views import LandingView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", LandingView.as_view(), name="landing"),
    path("health/", include("apps.health.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("join/", include("apps.households.urls_join")),
    path("hub/", include("apps.hub.urls")),
    path("c/<slug:slug>/cases/", include(("apps.casework.urls", "casework"), namespace="casework")),
    path("c/<slug:slug>/tags/", include(("apps.tags.urls", "tags"), namespace="tags")),
    path("c/<slug:slug>/moderation/", include(("apps.moderation.urls", "moderation"), namespace="moderation")),
    path("c/", include("apps.communities.urls")),
    path("account/", include("apps.accounts.urls_settings")),
    path("consent/", include("apps.consent.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("technology/", include("apps.communities.urls_tech")),
    path("", include("apps.communities.urls_mission")),
]

# Federation surface exists only when explicitly enabled (design: default OFF;
# flag off ⇒ routes absent, matching the threat model's containment posture).
if settings.FEDERATION_ENABLED:
    urlpatterns += [
        path(".well-known/umi-federation", include("apps.federation.urls_wellknown")),
        path("federation/v1/", include(("apps.federation.urls", "federation"), namespace="federation")),
        path(
            "c/<slug:slug>/federation/",
            include(("apps.federation.urls_admin", "federation_admin"), namespace="federation_admin"),
        ),
    ]

# Conditional 2FA URLs (only if django-two-factor-auth is installed)
if getattr(settings, "ENABLE_2FA", False):
    try:
        from two_factor.urls import urlpatterns as tf_urls

        urlpatterns += [
            path("", include(tf_urls)),
        ]
    except ImportError:
        pass

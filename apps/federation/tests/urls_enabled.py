"""Test URLconf with federation routes registered (prod registers them only
when FEDERATION_ENABLED=True; tests opt in via @pytest.mark.urls)."""

from django.urls import include, path

from config.urls import urlpatterns as base_urlpatterns

urlpatterns = [
    *base_urlpatterns,
    path(".well-known/umi-federation", include("apps.federation.urls_wellknown")),
    path("federation/v1/", include(("apps.federation.urls", "federation"), namespace="federation")),
    path(
        "c/<slug:slug>/federation/",
        include(("apps.federation.urls_admin", "federation_admin"), namespace="federation_admin"),
    ),
]

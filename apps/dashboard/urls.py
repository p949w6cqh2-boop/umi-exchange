"""
Dashboard URL patterns.
These routes are included from apps/communities/urls.py under community slug prefixes.
This module exists for modularity and discoverability, but the actual URL registration
happens in the community urlconf since dashboard views are scoped to a community.

Usage (in communities/urls.py):
    from apps.dashboard.views import DashboardView, DashboardExportView
    path("<slug:slug>/dashboard/", DashboardView.as_view(), name="community-dashboard"),
    path("<slug:slug>/dashboard/export/", DashboardExportView.as_view(), name="dashboard-export"),
"""
from django.urls import path
from .views import DashboardView, DashboardExportView

# These patterns would be used if dashboard gets its own URL prefix.
# Currently they are registered under communities/urls.py for slug scoping.
app_name = "dashboard"
urlpatterns = [
    # Registered via communities/urls.py for community-scoped routing:
    # path("", DashboardView.as_view(), name="index"),
    # path("export/", DashboardExportView.as_view(), name="export"),
]

from django.urls import path

from .views import FederationSettingsView

app_name = "federation_admin"

urlpatterns = [
    path("", FederationSettingsView.as_view(), name="settings"),
]

from django.urls import path

from .views import DashboardExportView, DashboardView

urlpatterns = [
    path("", DashboardView.as_view(), name="community-dashboard"),
    path("export/", DashboardExportView.as_view(), name="dashboard-export"),
]

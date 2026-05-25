from django.urls import path
from .views import DashboardView, DashboardExportView

urlpatterns = [
    path("", DashboardView.as_view(), name="community-dashboard"),
    path("export/", DashboardExportView.as_view(), name="dashboard-export"),
]

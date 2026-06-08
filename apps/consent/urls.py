from django.urls import path

from . import views

urlpatterns = [
    path("", views.ConsentListView.as_view(), name="consent-list"),
    path("<uuid:pk>/revoke/", views.ConsentRevokeView.as_view(), name="consent-revoke"),
]

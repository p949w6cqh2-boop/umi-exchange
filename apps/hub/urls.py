from django.urls import path

from . import views

app_name = "hub"

urlpatterns = [
    path("", views.HubResolverView.as_view(), name="index"),
    path("<slug:slug>/", views.HubView.as_view(), name="community"),
]

from django.urls import path

from . import views

app_name = "moderation"

urlpatterns = [
    path("", views.ModerationQueueView.as_view(), name="queue"),
    path("flag/", views.FlagCreateView.as_view(), name="flag"),
    path("<uuid:pk>/resolve/", views.FlagResolveView.as_view(), name="resolve"),
]

from django.urls import path

from . import views

urlpatterns = [
    path("flag/", views.FlagCreateView.as_view(), name="flag"),
    path("queue/", views.ModerationQueueView.as_view(), name="queue"),
    path("<uuid:pk>/resolve/", views.FlagResolveView.as_view(), name="resolve"),
    path("<uuid:pk>/dismiss/", views.FlagDismissView.as_view(), name="dismiss"),
]

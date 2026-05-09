from django.urls import path
from . import views
urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("mark-read/", views.MarkAllReadView.as_view(), name="notifications-mark-read"),
    path("count/", views.UnreadCountView.as_view(), name="notifications-count"),
]

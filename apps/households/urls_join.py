"""URLs under /join/ — community join + household management."""
from django.urls import path

from apps.communities.views import JoinCommunityView

from . import views

urlpatterns = [
    path("", JoinCommunityView.as_view(), name="community-join"),
    path("household/create/", views.HouseholdCreateView.as_view(), name="household-create"),
    path("household/join/", views.HouseholdJoinView.as_view(), name="household-join"),
]

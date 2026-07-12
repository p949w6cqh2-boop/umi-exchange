from django.urls import path

from apps.dashboard.views import DashboardExportView, DashboardView
from apps.matches.views import MatchDetailView, MatchProposeView, MatchUpdateView
from apps.needs.views import NeedCreateView, NeedDeleteView, NeedDetailView
from apps.offers.views import OfferCreateView, OfferDeleteView, OfferDetailView

from . import views

urlpatterns = [
    path("create/", views.CommunityCreateView.as_view(), name="community-create"),
    path("<slug:slug>/", views.FeedView.as_view(), name="community-feed"),
    path("<slug:slug>/settings/", views.CommunitySettingsView.as_view(), name="community-settings"),
    path("<slug:slug>/welcome/", views.CommunityWelcomeView.as_view(), name="community-welcome"),
    path("<slug:slug>/leave/", views.LeaveCommunityView.as_view(), name="community-leave"),
    path("<slug:slug>/settings/qr/", views.JoinCodeQRView.as_view(), name="join-code-qr"),
    path("<slug:slug>/dashboard/", DashboardView.as_view(), name="community-dashboard"),
    path("<slug:slug>/dashboard/export/", DashboardExportView.as_view(), name="dashboard-export"),
    # Needs
    path("<slug:slug>/needs/new/", NeedCreateView.as_view(), name="need-create"),
    path("<slug:slug>/needs/<uuid:pk>/", NeedDetailView.as_view(), name="need-detail"),
    path("<slug:slug>/needs/<uuid:pk>/delete/", NeedDeleteView.as_view(), name="need-delete"),
    # Offers
    path("<slug:slug>/offers/new/", OfferCreateView.as_view(), name="offer-create"),
    path("<slug:slug>/offers/<uuid:pk>/", OfferDetailView.as_view(), name="offer-detail"),
    path("<slug:slug>/offers/<uuid:pk>/delete/", OfferDeleteView.as_view(), name="offer-delete"),
    # Matches
    path("<slug:slug>/matches/propose/", MatchProposeView.as_view(), name="match-propose"),
    path("<slug:slug>/matches/<uuid:pk>/", MatchDetailView.as_view(), name="match-detail"),
    path("<slug:slug>/matches/<uuid:pk>/update/", MatchUpdateView.as_view(), name="match-update"),
]

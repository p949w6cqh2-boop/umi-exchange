from django.urls import path

from .views import (
    AttestationsQueryView,
    ConsentRevocationsView,
    DiscoveryView,
    HandshakeConfirmView,
    HandshakeView,
    MatchEventsView,
    MatchSyncView,
    ProposalsView,
)

app_name = "federation"

urlpatterns = [
    path("handshake", HandshakeView.as_view(), name="handshake"),
    path("handshake/confirm", HandshakeConfirmView.as_view(), name="handshake-confirm"),
    path("discovery", DiscoveryView.as_view(), name="discovery"),
    path("consent/revocations", ConsentRevocationsView.as_view(), name="consent-revocations"),
    path("proposals", ProposalsView.as_view(), name="proposals"),
    path("matches/<uuid:match_uuid>/events", MatchEventsView.as_view(), name="match-events"),
    path("matches/<uuid:match_uuid>", MatchSyncView.as_view(), name="match-sync"),
    path("attestations/query", AttestationsQueryView.as_view(), name="attestations-query"),
]

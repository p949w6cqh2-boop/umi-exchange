from django.urls import path

from .views import ConsentRevocationsView, DiscoveryView, HandshakeConfirmView, HandshakeView

app_name = "federation"

urlpatterns = [
    path("handshake", HandshakeView.as_view(), name="handshake"),
    path("handshake/confirm", HandshakeConfirmView.as_view(), name="handshake-confirm"),
    path("discovery", DiscoveryView.as_view(), name="discovery"),
    path("consent/revocations", ConsentRevocationsView.as_view(), name="consent-revocations"),
]

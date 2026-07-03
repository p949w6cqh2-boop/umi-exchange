from django.urls import path

from .views import DiscoveryView, HandshakeConfirmView, HandshakeView

app_name = "federation"

urlpatterns = [
    path("handshake", HandshakeView.as_view(), name="handshake"),
    path("handshake/confirm", HandshakeConfirmView.as_view(), name="handshake-confirm"),
    path("discovery", DiscoveryView.as_view(), name="discovery"),
]

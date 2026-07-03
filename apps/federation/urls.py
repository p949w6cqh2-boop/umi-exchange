from django.urls import path

from .views import HandshakeConfirmView, HandshakeView

app_name = "federation"

urlpatterns = [
    path("handshake", HandshakeView.as_view(), name="handshake"),
    path("handshake/confirm", HandshakeConfirmView.as_view(), name="handshake-confirm"),
]

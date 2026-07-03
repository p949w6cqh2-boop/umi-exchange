from django.urls import path

from .views import WellKnownView

urlpatterns = [
    path("", WellKnownView.as_view(), name="federation-wellknown"),
]

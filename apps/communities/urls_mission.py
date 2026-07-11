"""Public, login-exempt mission pages — the heart, story, and honest comparison.
These render for logged-out visitors; the needs board stays auth-gated as ever."""

from django.urls import path

from .views import AboutView, BeliefsView, PrivacyView, WhyUmiView

urlpatterns = [
    path("about/", AboutView.as_view(), name="about"),
    path("what-we-believe/", BeliefsView.as_view(), name="beliefs"),
    path("why-umi/", WhyUmiView.as_view(), name="why-umi"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
]

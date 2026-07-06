from django.urls import path

from .views import (
    FederatedAttestView,
    FederatedListingsView,
    FederatedMatchesView,
    FederatedOfferPickerView,
    FederatedProposeView,
    FederatedShareToggleView,
    FederationSettingsView,
)

app_name = "federation_admin"

urlpatterns = [
    path("", FederationSettingsView.as_view(), name="settings"),
    path("listings", FederatedListingsView.as_view(), name="listings"),
    path("listings/<uuid:shadow_id>/offers", FederatedOfferPickerView.as_view(), name="listing-offers"),
    path("listings/<uuid:shadow_id>/propose", FederatedProposeView.as_view(), name="listing-propose"),
    path("matches", FederatedMatchesView.as_view(), name="matches"),
    path("share", FederatedShareToggleView.as_view(), name="share-toggle"),
    path("matches/<uuid:fmatch_id>/attest", FederatedAttestView.as_view(), name="attest"),
]

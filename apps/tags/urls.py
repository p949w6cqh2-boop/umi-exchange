from django.urls import path

from . import views

urlpatterns = [
    path("", views.MemberTagListView.as_view(), name="my-tags"),
    path("claim/", views.TagClaimView.as_view(), name="claim"),
    path("queue/", views.VerificationQueueView.as_view(), name="queue"),
    path("<uuid:pk>/request-verify/", views.TagRequestVerifyView.as_view(), name="request-verify"),
    path("<uuid:pk>/remove/", views.TagRemoveView.as_view(), name="remove"),
    path("<uuid:pk>/verify/", views.TagVerifyView.as_view(), name="verify"),
    path("<uuid:pk>/reject/", views.TagRejectView.as_view(), name="reject"),
    path("<uuid:pk>/revoke/", views.TagRevokeView.as_view(), name="revoke"),
]

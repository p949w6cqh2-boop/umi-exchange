"""Manager surfaces only in S2 — the public /p/ index and page views arrive in
S3 on this same mount."""

from django.urls import path

from .views import (
    ArchiveView,
    ManageListView,
    PageCreateView,
    PageEditView,
    PreviewView,
    PublishView,
    RestoreView,
    ToggleLandingView,
    UnpublishView,
)

urlpatterns = [
    path("manage/", ManageListView.as_view(), name="manage"),
    path("manage/new/", PageCreateView.as_view(), name="create"),
    path("manage/preview/", PreviewView.as_view(), name="preview"),
    path("manage/<uuid:pk>/edit/", PageEditView.as_view(), name="edit"),
    path("manage/<uuid:pk>/publish/", PublishView.as_view(), name="publish"),
    path("manage/<uuid:pk>/unpublish/", UnpublishView.as_view(), name="unpublish"),
    path("manage/<uuid:pk>/archive/", ArchiveView.as_view(), name="archive"),
    path("manage/<uuid:pk>/restore/", RestoreView.as_view(), name="restore"),
    path("manage/<uuid:pk>/toggle-landing/", ToggleLandingView.as_view(), name="toggle-landing"),
]

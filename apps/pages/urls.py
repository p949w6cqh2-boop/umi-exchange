"""One mount, two faces: the manager (S2, §E) and the read surfaces (S3, §I).
The manage/ routes stay first — "manage" is a reserved slug (form-enforced),
so the page catch-all can never shadow them."""

from django.urls import path

from .views import (
    ArchiveView,
    ManageListView,
    PageCreateView,
    PageEditView,
    PagesIndexView,
    PageView,
    PreviewView,
    PublishView,
    RestoreView,
    ToggleLandingView,
    UnhideView,
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
    path("manage/<uuid:pk>/unhide/", UnhideView.as_view(), name="unhide"),
    path("", PagesIndexView.as_view(), name="index"),
    path("<slug:page_slug>/", PageView.as_view(), name="view"),
]

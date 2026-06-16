from django.urls import path

from . import views

app_name = "casework"

urlpatterns = [
    path("", views.CaseListView.as_view(), name="list"),
    path("new/", views.CaseCreateView.as_view(), name="create"),
    # Offline-capable visit capture (design §3.6, item 4)
    path("visit/", views.VisitCaptureView.as_view(), name="visit"),
    path("visit/sw.js", views.ServiceWorkerView.as_view(), name="sw"),
    path("visit/manifest.json", views.VisitManifestView.as_view(), name="visit-manifest"),
    path("sync/", views.SyncView.as_view(), name="sync"),
    path("reauth/", views.ReauthView.as_view(), name="reauth"),
    path("validate/", views.ValidateFieldView.as_view(), name="validate"),
    path("followups/", views.MyFollowUpsView.as_view(), name="followups-mine"),
    path("followups/<uuid:pk>/status/", views.FollowUpStatusView.as_view(), name="followup-status"),
    path("<uuid:pk>/", views.CaseDetailView.as_view(), name="detail"),
    path("<uuid:pk>/status/", views.CaseStatusView.as_view(), name="status"),
    path("<uuid:pk>/assign/", views.CaseAssignView.as_view(), name="assign"),
    path("<uuid:pk>/handoffs/<uuid:handoff_id>/ack/", views.HandoffAckView.as_view(), name="handoff-ack"),
    path("<uuid:pk>/export/", views.CaseExportView.as_view(), name="export"),
    path("<uuid:pk>/notes/new/", views.NoteCreateView.as_view(), name="note-create"),
    path("<uuid:pk>/notes/<uuid:note_id>/finalize/", views.NoteFinalizeView.as_view(), name="note-finalize"),
    path("<uuid:pk>/notes/<uuid:note_id>/amend/", views.NoteAmendView.as_view(), name="note-amend"),
    path("<uuid:pk>/notes/<uuid:note_id>/discard/", views.NoteDiscardView.as_view(), name="note-discard"),
    path("<uuid:pk>/followups/new/", views.FollowUpCreateView.as_view(), name="followup-create"),
    path("<uuid:pk>/grants/new/", views.GrantCreateView.as_view(), name="grant-create"),
    path("<uuid:pk>/grants/<uuid:grant_id>/revoke/", views.GrantRevokeView.as_view(), name="grant-revoke"),
]

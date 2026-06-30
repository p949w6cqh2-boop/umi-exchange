# Routes reference (generated)

> **Generated from the live URLconf** by `scripts/gen_routes.py` — do not hand-edit.
> Regenerate: `.venv/bin/python scripts/gen_routes.py > docs/routes.md`.
>
> There is **no OpenAPI/Swagger**: UMI Exchange is server-rendered HTML + HTMX with
> **no REST API** (DRF was removed in PR #16), so this table is the route contract.
>
> **Method / Path / View / Name** come from URL introspection. **Auth** is read off
> each view's `LoginRequiredMixin` (`login` vs `public`). Finer role-gating
> (coordinator / admin / owner / case participant) lives in `dispatch()` /
> `get_object()` / `apps/casework/access.py::case_access()` logic — **not** a mixin —
> so it is NOT in the Auth column; read the view. Namespaced includes (`cases/`,
> `tags/`) resolve **before** the `c/` communities catch-all.

| Method | Path | View | Auth | Name |
|---|---|---|---|---|
| GET | `/` | LandingView | public | `landing` |
| GET | `/health/` | HealthCheckView | public | `health-check` |
| GET,POST | `/auth/register/` | RegisterView | public | `register` |
| GET,POST | `/auth/login/` | UMILoginView | public | `login` |
| GET,POST | `/auth/logout/` | UMILogoutView | public | `logout` |
| GET,POST | `/auth/password/change/` | PasswordChangeView | public | `password_change` |
| GET | `/auth/password/change/done/` | PasswordChangeDoneView | public | `password_change_done` |
| GET,POST | `/auth/password/reset/` | PasswordResetView | public | `password_reset` |
| GET | `/auth/password/reset/done/` | PasswordResetDoneView | public | `password_reset_done` |
| GET,POST | `/auth/password/reset/<uidb64>/<token>/` | PasswordResetConfirmView | public | `password_reset_confirm` |
| GET | `/auth/password/reset/complete/` | PasswordResetCompleteView | public | `password_reset_complete` |
| GET,POST | `/join/` | JoinCommunityView | login | `community-join` |
| GET,POST | `/join/household/create/` | HouseholdCreateView | login | `household-create` |
| GET,POST | `/join/household/join/` | HouseholdJoinView | login | `household-join` |
| GET | `/c/<slug:slug>/cases/` | CaseListView | login | `list` |
| GET,POST | `/c/<slug:slug>/cases/new/` | CaseCreateView | login | `create` |
| GET,POST | `/c/<slug:slug>/cases/visit/` | VisitCaptureView | login | `visit` |
| GET | `/c/<slug:slug>/cases/visit/sw.js` | ServiceWorkerView | login | `sw` |
| GET | `/c/<slug:slug>/cases/visit/manifest.json` | VisitManifestView | login | `visit-manifest` |
| POST | `/c/<slug:slug>/cases/sync/` | SyncView | login | `sync` |
| GET,POST | `/c/<slug:slug>/cases/reauth/` | ReauthView | login | `reauth` |
| POST | `/c/<slug:slug>/cases/validate/` | ValidateFieldView | login | `validate` |
| GET | `/c/<slug:slug>/cases/followups/` | MyFollowUpsView | login | `followups-mine` |
| POST | `/c/<slug:slug>/cases/followups/<uuid:pk>/status/` | FollowUpStatusView | login | `followup-status` |
| GET | `/c/<slug:slug>/cases/<uuid:pk>/` | CaseDetailView | login | `detail` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/status/` | CaseStatusView | login | `status` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/assign/` | CaseAssignView | login | `assign` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/handoffs/<uuid:handoff_id>/ack/` | HandoffAckView | login | `handoff-ack` |
| GET | `/c/<slug:slug>/cases/<uuid:pk>/export/` | CaseExportView | login | `export` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/notes/new/` | NoteCreateView | login | `note-create` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/notes/<uuid:note_id>/finalize/` | NoteFinalizeView | login | `note-finalize` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/notes/<uuid:note_id>/amend/` | NoteAmendView | login | `note-amend` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/notes/<uuid:note_id>/discard/` | NoteDiscardView | login | `note-discard` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/followups/new/` | FollowUpCreateView | login | `followup-create` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/grants/new/` | GrantCreateView | login | `grant-create` |
| POST | `/c/<slug:slug>/cases/<uuid:pk>/grants/<uuid:grant_id>/revoke/` | GrantRevokeView | login | `grant-revoke` |
| GET | `/c/<slug:slug>/tags/` | MemberTagListView | login | `my-tags` |
| POST | `/c/<slug:slug>/tags/claim/` | TagClaimView | login | `claim` |
| GET | `/c/<slug:slug>/tags/queue/` | VerificationQueueView | login | `queue` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/request-verify/` | TagRequestVerifyView | login | `request-verify` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/remove/` | TagRemoveView | login | `remove` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/verify/` | TagVerifyView | login | `verify` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/reject/` | TagRejectView | login | `reject` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/revoke/` | TagRevokeView | login | `revoke` |
| GET,POST | `/c/create/` | CommunityCreateView | login | `community-create` |
| GET | `/c/<slug:slug>/` | FeedView | login | `community-feed` |
| GET,POST | `/c/<slug:slug>/settings/` | CommunitySettingsView | login | `community-settings` |
| GET | `/c/<slug:slug>/settings/qr/` | JoinCodeQRView | login | `join-code-qr` |
| GET | `/c/<slug:slug>/dashboard/` | DashboardView | login | `community-dashboard` |
| GET | `/c/<slug:slug>/dashboard/export/` | DashboardExportView | login | `dashboard-export` |
| GET,POST | `/c/<slug:slug>/needs/new/` | NeedCreateView | login | `need-create` |
| GET | `/c/<slug:slug>/needs/<uuid:pk>/` | NeedDetailView | login | `need-detail` |
| GET,POST | `/c/<slug:slug>/needs/<uuid:pk>/delete/` | NeedDeleteView | login | `need-delete` |
| GET,POST | `/c/<slug:slug>/offers/new/` | OfferCreateView | login | `offer-create` |
| GET | `/c/<slug:slug>/offers/<uuid:pk>/` | OfferDetailView | login | `offer-detail` |
| GET,POST | `/c/<slug:slug>/offers/<uuid:pk>/delete/` | OfferDeleteView | login | `offer-delete` |
| POST | `/c/<slug:slug>/matches/propose/` | MatchProposeView | login | `match-propose` |
| GET | `/c/<slug:slug>/matches/<uuid:pk>/` | MatchDetailView | login | `match-detail` |
| POST | `/c/<slug:slug>/matches/<uuid:pk>/update/` | MatchUpdateView | login | `match-update` |
| GET,POST | `/account/` | SettingsView | login | `account-settings` |
| GET | `/consent/` | ConsentListView | login | `consent-list` |
| POST | `/consent/<uuid:pk>/revoke/` | ConsentRevokeView | login | `consent-revoke` |
| GET | `/notifications/` | NotificationListView | login | `notification-list` |
| POST | `/notifications/mark-read/` | MarkAllReadView | login | `notifications-mark-read` |
| GET | `/notifications/count/` | UnreadCountView | login | `notifications-count` |
| GET | `/notifications/recent/` | RecentNotificationsView | login | `notifications-recent` |
| GET | `/technology/` | TechnologyView | public | `technology` |
| GET,POST | `/account/login/` | LoginView | public | `login` |
| GET,POST | `/account/two_factor/setup/` | SetupView | public | `setup` |
| GET | `/account/two_factor/qrcode/` | QRGeneratorView | public | `qr` |
| GET | `/account/two_factor/setup/complete/` | SetupCompleteView | public | `setup_complete` |
| GET,POST | `/account/two_factor/backup/tokens/` | BackupTokensView | public | `backup_tokens` |
| GET | `/account/two_factor/` | ProfileView | public | `profile` |
| GET,POST | `/account/two_factor/disable/` | DisableView | public | `disable` |

_74 routes, generated from the live URLconf by `scripts/gen_routes.py`._

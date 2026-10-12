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
| GET | `/.well-known/security.txt` | SecurityTxtView | public | `security-txt` |
| GET | `/health/` | HealthCheckView | public | `health-check` |
| GET,POST | `/auth/register/` | RegisterView | public | `register` |
| GET,POST | `/auth/login/` | UMILoginView | public | `login` |
| GET,POST | `/auth/login/otp/` | OTPVerifyView | public | `login-otp` |
| GET,POST | `/auth/logout/` | UMILogoutView | public | `logout` |
| GET | `/auth/still-here/` | StillHereView | public | `idle-ping` |
| GET | `/auth/verify/pending/` | VerifyPendingView | login | `verify-pending` |
| POST | `/auth/verify/send/` | VerifySendView | login | `verify-send` |
| GET | `/auth/verify/<str:token>/` | VerifyEmailView | public | `verify-email` |
| GET | `/auth/email/confirm/<str:token>/` | ConfirmAddEmailView | public | `account-confirm-email` |
| GET,POST | `/auth/recover/code/` | RecoveryCodeRedeemView | public | `recovery-code-redeem` |
| GET,POST | `/auth/phone/send/` | PhoneSendView | login | `phone-send` |
| GET,POST | `/auth/phone/confirm/` | PhoneConfirmView | login | `phone-confirm` |
| GET,POST | `/auth/recover/phone/` | PhoneRecoverView | public | `phone-recover` |
| GET,POST | `/auth/recover/phone/code/` | PhoneRecoverCodeView | public | `phone-recover-code` |
| POST | `/auth/recovery-code/new/` | RecoveryCodeNewView | login | `recovery-code-new` |
| GET,POST | `/auth/password/change/` | PasswordChangeView | public | `password_change` |
| GET | `/auth/password/change/done/` | PasswordChangeDoneView | public | `password_change_done` |
| GET,POST | `/auth/username/recover/` | UsernameRecoveryView | public | `username_recovery` |
| GET | `/auth/username/recover/done/` | UsernameRecoveryDoneView | public | `username_recovery_done` |
| GET,POST | `/auth/password/reset/` | PasswordResetView | public | `password_reset` |
| GET | `/auth/password/reset/done/` | PasswordResetDoneView | public | `password_reset_done` |
| GET,POST | `/auth/password/reset/<uidb64>/<token>/` | PasswordResetConfirmView | public | `password_reset_confirm` |
| GET | `/auth/password/reset/complete/` | PasswordResetCompleteView | public | `password_reset_complete` |
| GET,POST | `/staff/unlock/` | StaffUnlockView | login | `staff-unlock` |
| GET,POST | `/join/` | JoinCommunityView | login | `community-join` |
| GET,POST | `/join/household/create/` | HouseholdCreateView | login | `household-create` |
| GET,POST | `/join/household/join/` | HouseholdJoinView | login | `household-join` |
| GET | `/hub/` | HubResolverView | login | `index` |
| GET | `/hub/<slug:slug>/` | HubView | login | `community` |
| GET | `/hub/<slug:slug>/pulse` | HubPulseView | login | `pulse` |
| GET | `/hub/<slug:slug>/spotlight` | HubSpotlightView | login | `spotlight` |
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
| GET | `/c/<slug:slug>/moderation/` | ModerationQueueView | login | `queue` |
| POST | `/c/<slug:slug>/moderation/flag/` | FlagCreateView | login | `flag` |
| POST | `/c/<slug:slug>/moderation/<uuid:pk>/resolve/` | FlagResolveView | login | `resolve` |
| POST | `/c/<slug:slug>/moderation/block/` | BlockCreateView | login | `block` |
| POST | `/c/<slug:slug>/moderation/unblock/` | BlockDeleteView | login | `unblock` |
| GET | `/c/<slug:slug>/moderation/blocks/` | BlockListView | login | `blocks` |
| POST | `/c/<slug:slug>/moderation/reinstate/` | ReinstateMemberView | login | `reinstate` |
| GET | `/c/<slug:slug>/tags/` | MemberTagListView | login | `my-tags` |
| POST | `/c/<slug:slug>/tags/claim/` | TagClaimView | login | `claim` |
| GET | `/c/<slug:slug>/tags/queue/` | VerificationQueueView | login | `queue` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/request-verify/` | TagRequestVerifyView | login | `request-verify` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/remove/` | TagRemoveView | login | `remove` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/verify/` | TagVerifyView | login | `verify` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/reject/` | TagRejectView | login | `reject` |
| POST | `/c/<slug:slug>/tags/<uuid:pk>/revoke/` | TagRevokeView | login | `revoke` |
| GET | `/c/<slug:slug>/p/manage/` | ManageListView | public | `manage` |
| GET,POST | `/c/<slug:slug>/p/manage/new/` | PageCreateView | public | `create` |
| POST | `/c/<slug:slug>/p/manage/preview/` | PreviewView | public | `preview` |
| GET,POST | `/c/<slug:slug>/p/manage/<uuid:pk>/edit/` | PageEditView | public | `edit` |
| POST | `/c/<slug:slug>/p/manage/<uuid:pk>/publish/` | PublishView | public | `publish` |
| POST | `/c/<slug:slug>/p/manage/<uuid:pk>/unpublish/` | UnpublishView | public | `unpublish` |
| POST | `/c/<slug:slug>/p/manage/<uuid:pk>/archive/` | ArchiveView | public | `archive` |
| POST | `/c/<slug:slug>/p/manage/<uuid:pk>/restore/` | RestoreView | public | `restore` |
| POST | `/c/<slug:slug>/p/manage/<uuid:pk>/toggle-landing/` | ToggleLandingView | public | `toggle-landing` |
| POST | `/c/<slug:slug>/p/manage/<uuid:pk>/unhide/` | UnhideView | public | `unhide` |
| GET | `/c/<slug:slug>/p/` | PagesIndexView | public | `index` |
| GET | `/c/<slug:slug>/p/<slug:page_slug>/` | PageView | public | `view` |
| GET,POST | `/c/create/` | CommunityCreateView | login | `community-create` |
| GET | `/c/<slug:slug>/` | FeedView | login | `community-feed` |
| GET,POST | `/c/<slug:slug>/settings/` | CommunitySettingsView | login | `community-settings` |
| POST | `/c/<slug:slug>/members/vouch/` | VouchMemberView | login | `member-vouch` |
| POST | `/c/<slug:slug>/members/reset/` | CoordinatorResetView | login | `member-reset` |
| GET,POST | `/c/<slug:slug>/intake/register/` | IntakeRegisterView | login | `intake-register` |
| GET | `/c/<slug:slug>/vouch/` | VouchPageView | login | `member-vouch-page` |
| GET | `/c/<slug:slug>/welcome/` | CommunityWelcomeView | login | `community-welcome` |
| GET,POST | `/c/<slug:slug>/resources/` | ResourceListView | login | `community-resources` |
| POST | `/c/<slug:slug>/leave/` | LeaveCommunityView | login | `community-leave` |
| GET | `/c/<slug:slug>/settings/qr/` | JoinCodeQRView | login | `join-code-qr` |
| GET | `/c/<slug:slug>/dashboard/` | DashboardView | login | `community-dashboard` |
| GET | `/c/<slug:slug>/dashboard/export/` | DashboardExportView | login | `dashboard-export` |
| GET | `/c/<slug:slug>/activity/` | CoordinatorActivityView | login | `community-activity` |
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
| GET | `/about/` | AboutView | public | `about` |
| GET | `/what-we-believe/` | BeliefsView | public | `beliefs` |
| GET | `/why-umi/` | WhyUmiView | public | `why-umi` |
| GET | `/privacy/` | PrivacyView | public | `privacy` |
| GET | `/terms/` | TermsView | public | `terms` |
| GET | `/protocol/` | ProtocolView | public | `protocol` |
| GET | `/protocol/spec.md` | ProtocolSpecRawView | public | `protocol-spec` |
| GET,POST | `/account/two_factor/setup/` | SetupView | public | `setup` |
| GET | `/account/two_factor/qrcode/` | QRGeneratorView | public | `qr` |
| GET | `/account/two_factor/setup/complete/` | SetupCompleteView | public | `setup_complete` |
| GET,POST | `/account/two_factor/backup/tokens/` | BackupTokensView | public | `backup_tokens` |
| GET | `/account/two_factor/` | ProfileView | public | `profile` |
| GET,POST | `/account/two_factor/disable/` | DisableView | public | `disable` |

_127 routes, generated from the live URLconf by `scripts/gen_routes.py`._

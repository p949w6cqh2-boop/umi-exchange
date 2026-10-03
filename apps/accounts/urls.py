from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import ConfirmedEmailPasswordResetForm

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.UMILoginView.as_view(), name="login"),
    path("login/otp/", views.OTPVerifyView.as_view(), name="login-otp"),
    path("logout/", views.UMILogoutView.as_view(), name="logout"),
    # Idle sign-out's keep-alive (apps/accounts/idle.py).
    path("still-here/", views.StillHereView.as_view(), name="idle-ping"),
    # Human verification (docs/specs/human-verification.md, A+C)
    path("verify/pending/", views.VerifyPendingView.as_view(), name="verify-pending"),
    path("verify/send/", views.VerifySendView.as_view(), name="verify-send"),
    path("verify/<str:token>/", views.VerifyEmailView.as_view(), name="verify-email"),
    # Adding an email to an account that started without one. Separate route AND
    # separate token salt from verify/ above: that token carries only a uid, so a
    # shared salt would let an old registration link be replayed here to attach
    # an attacker-chosen address. docs/specs/account-recovery.md §A.
    path("email/confirm/<str:token>/", views.ConfirmAddEmailView.as_view(), name="account-confirm-email"),
    # The printed recovery code (docs/specs/account-recovery.md §B). The redeem path sits
    # under RATELIMIT_AUTH_PATHS: throttled on the client IP AND the submitted username.
    path("recover/code/", views.RecoveryCodeRedeemView.as_view(), name="recovery-code-redeem"),
    # Codes by phone (docs/specs/phone-codes.md); every one is a 404 while the feature is off.
    path("phone/send/", views.PhoneSendView.as_view(), name="phone-send"),
    path("phone/confirm/", views.PhoneConfirmView.as_view(), name="phone-confirm"),
    path("recover/phone/", views.PhoneRecoverView.as_view(), name="phone-recover"),
    path("recover/phone/code/", views.PhoneRecoverCodeView.as_view(), name="phone-recover-code"),
    path("recovery-code/new/", views.RecoveryCodeNewView.as_view(), name="recovery-code-new"),
    # Password change (logged in)
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url="/auth/password/change/done/",
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),
    # Username recovery (logged out)
    path(
        "username/recover/",
        views.UsernameRecoveryView.as_view(),
        name="username_recovery",
    ),
    path(
        "username/recover/done/",
        views.UsernameRecoveryDoneView.as_view(),
        name="username_recovery_done",
    ),
    # Password reset (logged out)
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            # Confirmed addresses only — docs/specs/email-confirmation.md, #172.
            form_class=ConfirmedEmailPasswordResetForm,
            template_name="accounts/password_reset.html",
            email_template_name="emails/password_reset_email.txt",
            success_url="/auth/password/reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password/reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/auth/password/reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
